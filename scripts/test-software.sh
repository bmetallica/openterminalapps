#!/usr/bin/env bash
# Prüft das Softwaremonitoring (Handbuch Kapitel 11, 2026-10-21).
#
#   * Die Erfassung liest einen laufenden Arbeitsplatz: die von Hand
#     installierten Debian-Pakete genau wie `apt-mark showmanual`, dazu
#     Programme mit Starteintrag — systemweit und im Zuhause. Versteckte
#     Einträge (NoDisplay) zählen nicht.
#   * Die Whitelist lässt sich aus dem aktuellen Stand befüllen; danach gibt
#     es keine Meldung.
#   * Kommt eine Anwendung dazu, die nicht darauf steht, erscheint sie als
#     Meldung — mit Nutzer und Vorlage — auch für das Dashboard.
#   * Wird sie deinstalliert, verschwindet die Meldung mit der nächsten
#     Erfassung. Wird sie freigegeben, ebenso; wird die Freigabe entzogen,
#     ist sie wieder da.
#
# Startet einen eigenen Arbeitsplatz mit dem Notfallkonto und stellt die
# Whitelist am Ende wieder her, wie sie vorher war.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
[ -f "$ROOT/deploy/.env" ] && [ -z "${OTA_TEST_ADMIN_PW:-}" ] && { set -a; . "$ROOT/deploy/.env"; set +a; }

pass=0; fail=0
ok()  { printf '  \033[32m✓\033[0m %s\n' "$1"; pass=$((pass+1)); }
bad() { printf '  \033[31m✗\033[0m %s\n' "$1"; fail=$((fail+1)); }
expect() { if [ "$2" = "$1" ]; then ok "$3 ($2)"; else bad "$3 — erwartet $1, bekommen $2"; fi; }

BASE="${OTA_BASE:-https://192.168.66.224:8443}"
TMP="$(mktemp -d)"
ADMIN="${OTA_TEST_ADMIN:-notfall}"
ADMIN_PW="${OTA_TEST_ADMIN_PW:?OTA_TEST_ADMIN_PW fehlt}"
WILD="ota-pruef-wildwuchs"

api() { curl -sk -b "$TMP/a.jar" -c "$TMP/a.jar" -H 'Content-Type: application/json' "$@"; }
jqp() { python3 -c "import sys,json;d=json.load(sys.stdin);print($1)" 2>/dev/null; }
erfassen() { api -X POST "$BASE/api/admin/software/erfassen" > "$TMP/erfassen.json"; }
stand() { api "$BASE/api/admin/software" > "$TMP/stand.json"; }
aus_stand() { jqp "$1" < "$TMP/stand.json"; }
meldung() {  # meldung <name> -> True/False
  api "$BASE/api/admin/software/meldungen" | jqp "str(any(m['name'] == '$1' for m in d))"
}
starteintrag() {  # starteintrag <pfad im container> <user> [zusatz]
  printf '[Desktop Entry]\nType=Application\nName=Prüf Wildwuchs\nExec=/bin/true\n%b' "${3:-}" \
    | docker exec -i -u "$2" "$C" sh -c "mkdir -p \"\$(dirname '$1')\" && cat > '$1'"
}

SID=""; C=""
aufraeumen() {
  echo
  echo "Aufräumen"
  [ -n "$SID" ] && api -X DELETE "$BASE/api/sessions/$SID" >/dev/null
  if [ -f "$TMP/whitelist-vorher.txt" ]; then
    api "$BASE/api/admin/software" | jqp "'\n'.join(w['name'] for w in d['whitelist'])" > "$TMP/whitelist-jetzt.txt"
    # Leere Zeilen raus: Ein leeres Muster passt auf alles, und dann bliebe
    # die ganze Befüllung stehen.
    sed -i '/^$/d' "$TMP/whitelist-vorher.txt"
    grep -vxFf "$TMP/whitelist-vorher.txt" "$TMP/whitelist-jetzt.txt" | while read -r n; do
      [ -n "$n" ] && api -X DELETE "$BASE/api/admin/software/whitelist/$n" >/dev/null
    done
    api "$BASE/api/admin/software" | jqp "'\n'.join(w['name'] for w in d['whitelist'])" | sed '/^$/d' > "$TMP/whitelist-nachher.txt"
    if cmp -s "$TMP/whitelist-vorher.txt" "$TMP/whitelist-nachher.txt"; then
      ok "Whitelist wie vorher"
    else
      bad "Whitelist nicht wie vorher ($(wc -l < "$TMP/whitelist-nachher.txt") statt $(wc -l < "$TMP/whitelist-vorher.txt"))"
    fi
  fi
  rm -rf "$TMP"
  echo
  printf '  bestanden: %d   fehlgeschlagen: %d\n' "$pass" "$fail"
  [ "$fail" -eq 0 ] || exit 1
}
trap aufraeumen EXIT

echo "Softwaremonitoring gegen $BASE"
curl -sk -c "$TMP/a.jar" -o /dev/null -X POST "$BASE/api/auth/login" -H 'Content-Type: application/json' \
  -d "{\"username\":\"$ADMIN\",\"password\":\"$ADMIN_PW\"}"
api "$BASE/api/admin/software" | jqp "'\n'.join(w['name'] for w in d['whitelist'])" > "$TMP/whitelist-vorher.txt"

T=$(api "$BASE/api/templates" | jqp "next(t['id'] for t in d if t['is_enabled'] and t['klasse'] == 'standard')")
[ -n "$T" ] || { bad "Kein Workspace zum Prüfen gefunden"; exit 1; }
for n in 1 2 3; do
  SID=$(api -X POST "$BASE/api/sessions" -d "{\"template_id\":\"$T\"}" | jqp "d.get('id','')")
  [ -n "$SID" ] && break
  sleep 5
done
[ -n "$SID" ] || { bad "Arbeitsplatz ließ sich nicht starten"; exit 1; }
for i in $(seq 1 40); do
  C=$(docker ps --filter "label=ota.session_id=$SID" --filter status=running --format '{{.Names}}' | head -1)
  [ -n "$C" ] && break; sleep 3
done
[ -n "$C" ] && ok "Arbeitsplatz läuft ($C)" || { bad "Arbeitsplatz kam nicht hoch"; exit 1; }

echo
echo "Erfassen"
erfassen; stand
expect "True" "$(aus_stand "str(d['letzte']['ok'])")" "Die Erfassung lief"
[ "$(aus_stand "str(d['letzte']['ok'])")" = "True" ] || echo "    $(cat "$TMP/erfassen.json" | head -c 300)"
expect "True" "$(aus_stand "str(any(p['session_id'] == '$SID' for p in d['arbeitsplaetze']))")" \
  "Der Arbeitsplatz steht in der Übersicht"
aus_stand "'\n'.join(sorted(a['name'] for p in d['arbeitsplaetze'] if p['session_id'] == '$SID' for a in p['anwendungen'] if a['quelle'] == 'apt'))" > "$TMP/apt-ota.txt"
sort -u -o "$TMP/apt-ota.txt" "$TMP/apt-ota.txt"
docker exec "$C" apt-mark showmanual | sed 's/:.*//' | tr 'A-Z' 'a-z' | sort -u > "$TMP/apt-echt.txt"  # libegl1:i386 ist libegl1
APT_ECHT=$(wc -l < "$TMP/apt-echt.txt")
# OTA liest extended_states selbst. apt-mark zeigt darüber hinaus einige
# Multi-Arch-Bibliotheken als „von Hand", die dort als automatisch vermerkt
# sind (libaudit1, zlib1g) — die fehlen bei OTA mit Absicht.
NUR_OTA=$(comm -13 "$TMP/apt-echt.txt" "$TMP/apt-ota.txt" | wc -l)
NUR_APT=$(comm -23 "$TMP/apt-echt.txt" "$TMP/apt-ota.txt")
expect "0" "$NUR_OTA" "Jedes Debian-Paket von OTA nennt auch apt-mark showmanual"
# Was fehlt, muss in extended_states als automatisch stehen.
docker exec "$C" cat /var/lib/apt/extended_states | awk '/^Package:/{p=$2} /^Auto-Installed: 1/{print p}' \
  | tr 'A-Z' 'a-z' | sort -u > "$TMP/apt-auto.txt"
OHNE_GRUND=$(comm -23 <(grep . <<<"$NUR_APT" | sort -u) "$TMP/apt-auto.txt")
expect "" "$OHNE_GRUND" "Was apt-mark mehr nennt, ist dort als automatisch vermerkt ($(grep -c . <<<"$NUR_APT") von $APT_ECHT)"
N_DESK=$(aus_stand "sum(1 for p in d['arbeitsplaetze'] if p['session_id'] == '$SID' for a in p['anwendungen'] if a['quelle'] == 'desktop')")
[ "${N_DESK:-0}" -gt 0 ] && ok "Programme mit Starteintrag erfasst ($N_DESK)" || bad "Keine Starteinträge erfasst"

echo
echo "Whitelist aus dem aktuellen Stand"
api -X POST "$BASE/api/admin/software/whitelist/erstbefuellen" >/dev/null
stand
expect "0" "$(aus_stand "sum(1 for m in d['meldungen'] if any(o['session_id'] == '$SID' for o in m['orte']))")" \
  "Danach keine Meldung für diesen Arbeitsplatz"

echo
echo "Wildwuchs: eine neue Anwendung im System"
starteintrag "/usr/share/applications/$WILD.desktop" root
erfassen
expect "True" "$(meldung "$WILD")" "Sie erscheint als Meldung"
M=$(api "$BASE/api/admin/software/meldungen" | jqp "json.dumps(next(m for m in d if m['name'] == '$WILD'))")
expect "$ADMIN" "$(jqp "d['orte'][0]['user']" <<<"$M")" "… mit dem Nutzer"
expect "Prüf Wildwuchs" "$(jqp "d['titel']" <<<"$M")" "… und dem Namen aus dem Starteintrag"

docker exec -u root "$C" rm -f "/usr/share/applications/$WILD.desktop"
erfassen
expect "False" "$(meldung "$WILD")" "Deinstalliert — die Meldung ist weg"

echo
echo "Freigeben und entziehen"
starteintrag "/usr/share/applications/$WILD.desktop" root
erfassen
expect "True" "$(meldung "$WILD")" "Wieder installiert, wieder gemeldet"
api -X POST "$BASE/api/admin/software/whitelist" -d "{\"namen\":[\"$WILD\"]}" >/dev/null
expect "False" "$(meldung "$WILD")" "In die Whitelist übernommen — keine Meldung mehr"
api -X DELETE "$BASE/api/admin/software/whitelist/$WILD" >/dev/null
expect "True" "$(meldung "$WILD")" "Freigabe entzogen — die Meldung ist zurück"
docker exec -u root "$C" rm -f "/usr/share/applications/$WILD.desktop"

echo
echo "Im Zuhause, ohne root"
H=$(docker exec -u 1000 "$C" sh -c 'echo $HOME')
starteintrag "$H/.local/share/applications/$WILD-heim.desktop" 1000
starteintrag "$H/.local/share/applications/$WILD-versteckt.desktop" 1000 'NoDisplay=true\n'
erfassen
expect "True" "$(meldung "$WILD-heim")" "Ein Starteintrag im Zuhause wird gemeldet"
expect "False" "$(meldung "$WILD-versteckt")" "Ein versteckter Eintrag nicht"
docker exec -u 1000 "$C" rm -f "$H/.local/share/applications/$WILD-heim.desktop" \
  "$H/.local/share/applications/$WILD-versteckt.desktop"
erfassen
expect "False" "$(meldung "$WILD-heim")" "Gelöscht — die Meldung ist weg"
