#!/usr/bin/env bash
# Prüft Sicherung und Wiederherstellung (plan.md §11.2).
#
# Der Test greift bewusst in ein echtes Profil ein: Er legt eine Markierung
# hinein, stellt zurück und prüft, ob sie verschwunden ist. Eine
# Wiederherstellung, die man nur ansieht, ist nicht geprüft.

set -uo pipefail

BASE="${1:-https://192.168.66.224:8443}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CA="$ROOT/deploy/certs/ota-ca.crt"
JAR="$(mktemp)"
trap 'rm -f "$JAR"' EXIT

USER_NAME="${OTA_TEST_ADMIN:-bmetallica}"
USER_PW="${OTA_TEST_ADMIN_PW:-OtaStart2026!xyz}"

pass=0; fail=0
ok()  { printf '  \033[32m✓\033[0m %s\n' "$1"; pass=$((pass+1)); }
bad() { printf '  \033[31m✗\033[0m %s\n' "$1"; fail=$((fail+1)); }
api() { curl -s --cacert "$CA" -b "$JAR" -c "$JAR" "$@"; }
jqp() { python3 -c "import sys,json;d=json.load(sys.stdin);print($1)" 2>/dev/null; }

echo "Sicherung und Wiederherstellung gegen $BASE"
echo

api -X POST "$BASE/api/auth/login" -H 'Content-Type: application/json' \
    -d "{\"username\":\"$USER_NAME\",\"password\":\"$USER_PW\"}" >/dev/null

# ------------------------------------------------------------------ Ablage
ST=$(api "$BASE/api/backups/storage")
WRITABLE=$(echo "$ST" | jqp "d['writable']")
[ "$WRITABLE" = "True" ] && ok "Sicherungsverzeichnis ist beschreibbar" \
                         || bad "Sicherungsverzeichnis nicht beschreibbar"
echo "$ST" | jqp "d['path']" | grep -q . && ok "Ablage: $(echo "$ST" | jqp "d['path']") ($(echo "$ST" | jqp "d['fstype']"))" \
                         || bad "Kein Pfad gemeldet"

# ------------------------------------------------- Rechte: kein Admin, kein Zugriff
TEST_USER="ota-testnutzer"
TEST_PW="TestNutzer2026!ab"
UJAR="$(mktemp)"
api "$BASE/api/admin/users" | grep -q "$TEST_USER" || {
  GID=$(api "$BASE/api/admin/groups" | jqp "[g['id'] for g in d if g['slug']=='users'][0]")
  api -X POST "$BASE/api/admin/users" -H 'Content-Type: application/json' \
      -d "{\"username\":\"$TEST_USER\",\"password\":\"$TEST_PW\",\"group_ids\":[\"$GID\"]}" >/dev/null
}
curl -s --cacert "$CA" -c "$UJAR" -X POST "$BASE/api/auth/login" \
     -H 'Content-Type: application/json' \
     -d "{\"username\":\"$TEST_USER\",\"password\":\"$TEST_PW\"}" >/dev/null
CODE=$(curl -s --cacert "$CA" -b "$UJAR" -o /dev/null -w '%{http_code}' "$BASE/api/backups")
[ "$CODE" = "403" ] && ok "Normaler Nutzer kommt nicht an die Sicherungen (403)" \
                    || bad "Normaler Nutzer bekam $CODE statt 403"
CODE=$(curl -s --cacert "$CA" -b "$UJAR" -o /dev/null -w '%{http_code}' \
       -X POST "$BASE/api/backups/run" -H 'Content-Type: application/json' -d '{}')
[ "$CODE" = "403" ] && ok "Normaler Nutzer kann keine Sicherung auslösen (403)" \
                    || bad "Sicherung auslösen ergab $CODE statt 403"
rm -f "$UJAR"

# --------------------------------------------------------------- Sicherung
BEFORE=$(api "$BASE/api/backups" | jqp "len(d)")
api -X POST "$BASE/api/backups/run" -H 'Content-Type: application/json' \
    -d "{\"username\":\"$USER_NAME\"}" >/dev/null
sleep 2
AFTER=$(api "$BASE/api/backups" | jqp "len(d)")
[ "$AFTER" -gt "$BEFORE" ] && ok "Sicherung angelegt ($BEFORE → $AFTER)" \
                           || bad "Keine neue Sicherung entstanden"

LAST=$(api "$BASE/api/backups" | jqp "d[0]")
STATUS=$(api "$BASE/api/backups" | jqp "d[0]['status']")
SIZE=$(api "$BASE/api/backups" | jqp "d[0]['size_bytes']")
BID=$(api "$BASE/api/backups" | jqp "d[0]['id']")
FILES=$(api "$BASE/api/backups" | jqp "d[0]['file_count']")
[ "$STATUS" = "ok" ] && ok "Sicherung erfolgreich, $((SIZE/1024)) KB, $FILES Einträge" \
                     || bad "Sicherung mit Status $STATUS"

PATHV=$(api "$BASE/api/backups" | jqp "d[0]['path'] or ''")
[ -n "$PATHV" ] && [ -f "$PATHV" ] && ok "Archiv liegt auf der Platte" \
                                   || bad "Archiv fehlt: $PATHV"
tar --zstd -tf "$PATHV" >/dev/null 2>&1 && ok "Archiv ist lesbar" || bad "Archiv beschädigt"

# ------------------------------------- Schutz: keine Wiederherstellung bei Session
PROFILE="/srv/ota/profiles/$USER_NAME/user"
SESSIONS=$(api "$BASE/api/sessions" | jqp "len(d)")
if [ "$SESSIONS" -gt 0 ]; then
  MSG=$(api -X POST "$BASE/api/backups/$BID/restore" | jqp "d.get('detail','')")
  echo "$MSG" | grep -qi "session" && ok "Wiederherstellung bei laufender Session abgelehnt" \
                                   || bad "Laufende Session wurde nicht erkannt: $MSG"
  for s in $(api "$BASE/api/sessions" | jqp "' '.join(x['id'] for x in d)"); do
    api -X DELETE "$BASE/api/sessions/$s" >/dev/null
  done
  sleep 3
  ok "Sessions für den Test beendet"
else
  ok "Keine laufende Session — Schutzprüfung übersprungen"
fi

# --------------------------------------------------------- Wiederherstellung
MARK="$PROFILE/PRUEFMARKE-$$.txt"
echo "diese Datei darf nach der Wiederherstellung nicht mehr da sein" > "$MARK"
[ -f "$MARK" ] && ok "Markierung ins Profil gelegt" || bad "Markierung liess sich nicht anlegen"

MSG=$(api -X POST "$BASE/api/backups/$BID/restore" | jqp "d.get('status') or d.get('detail','')")
echo "$MSG" | grep -qi "wiederhergestellt" && ok "Wiederherstellung gemeldet" \
                                           || bad "Wiederherstellung: $MSG"

[ ! -f "$MARK" ] && ok "Markierung ist verschwunden — die Wiederherstellung hat gewirkt" \
                 || bad "Markierung noch vorhanden — wirkungslos"

ASIDE=$(ls -d "/srv/ota/profiles/$USER_NAME"/user.vor-wiederherstellung-* 2>/dev/null | tail -1)
[ -n "$ASIDE" ] && [ -f "$ASIDE/$(basename "$MARK")" ] \
  && ok "Bisheriger Stand wurde beiseitegelegt, mit Markierung darin" \
  || bad "Kein brauchbarer Sicherheitsstand hinterlegt"

OWNER=$(stat -c '%u:%g' "$PROFILE" 2>/dev/null)
[ "$OWNER" = "1000:1000" ] && ok "Eigentümer nach der Wiederherstellung korrekt (1000:1000)" \
                           || bad "Eigentümer ist $OWNER statt 1000:1000"

# Aufräumen: die Sicherheitsstände des Tests wieder entfernen.
rm -rf "/srv/ota/profiles/$USER_NAME"/user.vor-wiederherstellung-* 2>/dev/null

# ------------------------------------------------------------------ Zeitplan
POL=$(api "$BASE/api/backups/policy")
echo "$POL" | jqp "d['keep_daily']" | grep -q . && ok "Zeitplan abrufbar (behält $(echo "$POL" | jqp "d['keep_daily']") tägliche Stände)" \
                                               || bad "Zeitplan nicht abrufbar"
api -X PUT "$BASE/api/backups/policy" -H 'Content-Type: application/json' \
    -d '{"is_enabled":false,"hour":3,"minute":30,"weekdays":[],"include_profiles":true,"include_containers":false,"include_database":true,"keep_daily":7,"keep_weekly":4}' >/dev/null
ENABLED=$(api "$BASE/api/backups/policy" | jqp "d['is_enabled']")
[ "$ENABLED" = "False" ] && ok "Zeitplan lässt sich ändern" || bad "Zeitplan liess sich nicht ändern"

echo
echo "─────────────────────────────────────"
printf '  bestanden: %d   fehlgeschlagen: %d\n' "$pass" "$fail"
[ "$fail" -eq 0 ] || exit 1
