#!/usr/bin/env bash
# Prüft „Geheimnisse beim Push erkennen“ in OTA-Git (Handbuch Kapitel 27):
#
#   * Eingeschaltet hängt OTA den Hook in jedes Repository ein, auch in
#     vorhandene, und neue bekommen ihn über die Vorlage sofort.
#   * Ein harmloser Push geht durch, Platzhalter wie „changeme“ zählen nicht.
#   * Sperren weist einen Push mit privatem Schlüssel ab und nennt Datei und
#     Commit; `-o ota.geheimnis=falscher-alarm` lässt ihn durch.
#   * Warnen nimmt an und warnt, Beobachten zählt nur.
#   * In der Datenbank stehen nur Zahlen: keine Dateinamen, keine Repositories.
#   * Ausgeschaltet verschwinden Verweise und Vorlage wieder.
#
# Gepusht wird auf eigene Zweige (pruef-…), damit ein Branch-Schutz auf main
# die Prüfung nicht stört. Braucht laufendes OTA-Git.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
[ -f "$ROOT/deploy/.env" ] && { set -a; . "$ROOT/deploy/.env"; set +a; }

pass=0; fail=0
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; pass=$((pass+1)); }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$1"; fail=$((fail+1)); }
expect() { if [ "$2" = "$1" ]; then ok "$3"; else bad "$3 — erwartet $1, bekommen $2"; fi; }
enthaelt() { if grep -q -- "$2" <<<"$1"; then ok "$3"; else bad "$3 — „$2“ fehlt"; fi; }
fehlt() { if grep -q -- "$2" <<<"$1"; then bad "$3 — „$2“ steht drin"; else ok "$3"; fi; }

BASE="${1:-$("$(dirname "$0")/ota-adresse.sh")}"
TMP="$(mktemp -d)"
ADMIN="${OTA_TEST_ADMIN:-notfall}"
ADMIN_PW="${OTA_TEST_ADMIN_PW:?OTA_TEST_ADMIN_PW fehlt}"
ALT=ota-pruef-geheim-alt
NEU=ota-pruef-geheim-neu
LAUF="$(date +%s)$$"

api()  { curl -sk -b "$TMP/admin.jar" -c "$TMP/admin.jar" "$@"; }
code() { curl -sk -o /dev/null -w '%{http_code}' -b "$TMP/admin.jar" "$@"; }
jqp()  { python3 -c "import sys,json;d=json.load(sys.stdin);print($1)" 2>/dev/null; }
sql()  { docker exec ota-db psql -U ota -d ota -tAc "$1"; }
fj()   { docker exec -i ota-api python - "$@"; }
imgit() { docker exec -u git ota-git sh -c "$1"; }
setze() { api -X PUT "$BASE/api/admin/git/geheimnisse" -H 'Content-Type: application/json' -d "$1"; }
abholen() { docker exec ota-api python -c "
from ota.db import SessionLocal
from ota import git_geheimnisse
with SessionLocal() as db:
    print(git_geheimnisse.abgleichen(db)['pushes'])"; }
summe() { sql "SELECT coalesce(sum(anzahl),0) FROM git_geheimnisse WHERE art = '$1' AND typ = '$2'"; }

# Ein Arbeitsverzeichnis in Forgejo selbst, gegen localhost:3000.
GITPW=$(docker exec ota-api printenv OTA_GIT_ADMIN_PW)
WT=""
push() {  # push <zweig> <datei> <inhalt> [push-option] -> Ausgabe von git push
  docker exec -u git -e PW="$GITPW" -e WT="$WT" -e Z="$1" -e D="$2" -e I="$3" -e O="${4:-}" ota-git sh -c '
    cd "$WT" && printf "%s\n" "$I" > "$D" && git add -A && git commit -qm "pruef $Z" \
    && if [ -n "$O" ]; then git push -o "$O" origin "HEAD:refs/heads/$Z" 2>&1; else git push origin "HEAD:refs/heads/$Z" 2>&1; fi
    echo "EXIT $?"'
}

VORHER=""
aufraeumen() {
  fj "$ALT" "$NEU" <<'PY' >/dev/null
import sys
from ota import git
for n in sys.argv[1:]:
    git._ruf("DELETE", f"/repos/ota-admin/{n}")
PY
  if [ -n "$VORHER" ]; then
    sql "UPDATE settings SET value = '$VORHER' WHERE key = 'git.geheimnisse'" >/dev/null
    sleep 6
    abholen >/dev/null
  fi
  case "$WT" in /tmp/tmp.*/wt) docker exec -u git -e W="${WT%/wt}" ota-git sh -c 'rm -rf -- "$W"' >/dev/null 2>&1 ;; esac
  rm -rf "$TMP"
}
trap aufraeumen EXIT

echo "Geheimnisse beim Push"
curl -sk -c "$TMP/admin.jar" -o /dev/null -X POST "$BASE/api/auth/login" -H 'Content-Type: application/json' \
  -d "{\"username\":\"$ADMIN\",\"password\":\"$ADMIN_PW\"}"
expect "True" "$(api "$BASE/api/admin/git" | jqp "d['an']")" "OTA-Git läuft"
STAND=$(api "$BASE/api/admin/git/geheimnisse")
expect "False" "$(jqp "d['an']" <<<"$STAND")" "Ab Werk ausgeschaltet"
sql "INSERT INTO settings (key, value, updated_at) VALUES ('git.geheimnisse', '{\"v\": {\"an\": false, \"betriebsart\": \"warnen\", \"uebergehen\": true}}', now())
     ON CONFLICT (key) DO NOTHING" >/dev/null
VORHER=$(sql "SELECT value FROM settings WHERE key = 'git.geheimnisse'")

expect "400" "$(code -X PUT "$BASE/api/admin/git/geheimnisse" -H 'Content-Type: application/json' \
  -d '{"betriebsart":"loeschen"}')" "Unbekannte Betriebsart wird abgelehnt"
expect "401" "$(curl -sk -o /dev/null -w '%{http_code}' "$BASE/api/admin/git/geheimnisse/statistik")" \
  "Statistik nur mit Anmeldung"

# Ein Repository von vorher: Es bekommt den Verweis beim Einschalten.
fj "$ALT" <<'PY' >/dev/null
import sys
from ota import git
git._ruf("DELETE", f"/repos/ota-admin/{sys.argv[1]}")
git._ruf("POST", "/user/repos", json={"name": sys.argv[1], "auto_init": True})
PY
R=$(setze '{"an":true,"betriebsart":"sperren","uebergehen":true}')
expect "True" "$(jqp "d['an']" <<<"$R")" "Einschalten"
expect "True" "$(jqp "d['abgleich']['laeuft']" <<<"$R")" "Gleich in Forgejo abgeglichen"
expect "ja" "$(imgit "[ -x /data/git/repositories/ota-admin/$ALT.git/hooks/pre-receive.d/ota-geheimnisse ] && echo ja")" \
  "Vorhandenes Repository hat den Verweis"
fj "$NEU" <<'PY' >/dev/null
import sys
from ota import git
git._ruf("DELETE", f"/repos/ota-admin/{sys.argv[1]}")
git._ruf("POST", "/user/repos", json={"name": sys.argv[1], "auto_init": True})
PY
expect "ja" "$(imgit "[ -x /data/git/repositories/ota-admin/$NEU.git/hooks/pre-receive.d/ota-geheimnisse ] && echo ja")" \
  "Neues Repository hat ihn sofort, über die Vorlage"

WT=$(docker exec -u git -e PW="$GITPW" -e R="$NEU" ota-git sh -c '
  W=$(mktemp -d) && cd "$W" && git clone -q "http://ota-admin:$PW@localhost:3000/ota-admin/$R.git" wt \
  && cd wt && git config user.email pruef@ota.invalid && git config user.name pruef && pwd')
[ -n "$WT" ] && ok "Arbeitskopie in Forgejo" || bad "Arbeitskopie in Forgejo"

# Erst abholen, was schon im Spool liegt (der erste Commit des neuen
# Repositorys, auto_init, ging auch durch den Hook).
abholen >/dev/null
G_VOR=$(summe push geprueft); S_VOR=$(summe push gesperrt); U_VOR=$(summe push uebergangen)
W_VOR=$(summe push gewarnt); Z_VOR=$(summe push gezaehlt); P_VOR=$(summe treffer privater-schluessel)

A=$(push "pruef-$LAUF-a" harmlos.py "db = \"postgres://user:changeme@db/x\"  # $LAUF")
enthaelt "$A" "EXIT 0" "Harmloser Push geht durch (Platzhalter zählt nicht)"
fehlt "$A" "OTA:" "… ohne Meldung"

GEHEIM="x$(od -An -N8 -tx1 /dev/urandom | tr -d ' \n')"
SCHLUESSEL="-----BEGIN OPENSSH PRIVATE KEY-----
$GEHEIM"
B=$(push "pruef-$LAUF-b" geheim.txt "$SCHLUESSEL")
enthaelt "$B" "Push abgewiesen" "Sperren: Push mit privatem Schlüssel abgewiesen"
enthaelt "$B" "geheim.txt" "… mit Dateiname für den, der pusht"
enthaelt "$B" "ota.geheimnis=falscher-alarm" "… und dem Weg für einen Fehlalarm"
fehlt "$B" "$GEHEIM" "… ohne das Geheimnis selbst zu zeigen"
C=$(push "pruef-$LAUF-c" leer.txt "$LAUF" "ota.geheimnis=falscher-alarm")
enthaelt "$C" "übergangen" "Mit Push-Option als Fehlalarm übergangen"
enthaelt "$C" "EXIT 0" "… und angenommen"

setze '{"uebergehen":false}' >/dev/null
D=$(push "pruef-$LAUF-d" ki.py "KEY = \"sk-ant-$LAUF-abcdefghijklmnopqrstuvwxyz\"" "ota.geheimnis=falscher-alarm")
enthaelt "$D" "Push abgewiesen" "Übergehen ausgeschaltet: Push-Option hilft nicht"

setze '{"betriebsart":"warnen"}' >/dev/null
E=$(push "pruef-$LAUF-e" .env "TOKEN=$LAUF")
enthaelt "$E" "Achtung" "Warnen: Hinweis an den, der pusht"
enthaelt "$E" "EXIT 0" "… und angenommen"

setze '{"betriebsart":"beobachten"}' >/dev/null
F=$(push "pruef-$LAUF-f" g.txt "ghp_${LAUF}abcdefghijklmnopqrstuvwxyz0123456789")
enthaelt "$F" "EXIT 0" "Beobachten: angenommen"
fehlt "$F" "OTA:" "… ohne Meldung"

abholen >/dev/null
expect "6" "$(( $(summe push geprueft) - G_VOR ))" "Sechs Pushes geprüft und gezählt"
expect "2" "$(( $(summe push gesperrt) - S_VOR ))" "Zwei gesperrt"
expect "1" "$(( $(summe push uebergangen) - U_VOR ))" "Einer übergangen"
expect "1" "$(( $(summe push gewarnt) - W_VOR ))" "Einer gewarnt"
expect "1" "$(( $(summe push gezaehlt) - Z_VOR ))" "Einer nur gezählt"
expect "2" "$(( $(summe treffer privater-schluessel) - P_VOR ))" "Treffer je Art: zweimal privater Schlüssel"

STAT=$(api "$BASE/api/admin/git/geheimnisse/statistik?tage=1")
[ "$(jqp "d['faelle']" <<<"$STAT")" -ge 5 ] 2>/dev/null && ok "Statistik zählt die Fälle" \
  || bad "Statistik zählt die Fälle — $(jqp "d['faelle']" <<<"$STAT")"
expect "anzahl,art,stunde,typ" "$(sql "SELECT string_agg(column_name, ',' ORDER BY column_name) FROM information_schema.columns WHERE table_name = 'git_geheimnisse'")" \
  "Tabelle hat nur Zeit, Art, Typ und Anzahl"
expect "0" "$(sql "SELECT count(*) FROM git_geheimnisse WHERE typ NOT IN ('geprueft','gezaehlt','gewarnt','gesperrt','uebergangen','gekuerzt','privater-schluessel','cloud-schluessel','git-token','ki-schluessel','chat-token','jwt','passwort-im-code','zugang-in-adresse','env-datei','schluesseldatei')")" \
  "Keine Dateinamen oder Repositories in der Datenbank"
expect "0" "$(imgit 'ls /data/ota/geheimnisse/spool/*.jsonl 2>/dev/null | wc -l')" "Spool ist abgeholt"
[ "$(sql "SELECT count(*) FROM audit_log WHERE action = 'git.geheimnisse_eingestellt' AND ts > now() - interval '5 minutes'")" -ge 4 ] \
  && ok "Jede Änderung steht im Protokoll" || bad "Jede Änderung steht im Protokoll"

setze '{"an":false}' >/dev/null
expect "nein" "$(imgit "[ -e /data/git/repositories/ota-admin/$ALT.git/hooks/pre-receive.d/ota-geheimnisse ] && echo ja || echo nein")" \
  "Ausgeschaltet: Verweis entfernt"
expect "" "$(imgit 'HOME=/data/gitea/home git config --global --get init.templateDir')" "… und die Vorlage abgemeldet"

echo
echo "Ergebnis: $pass bestanden, $fail fehlgeschlagen"
[ "$fail" -eq 0 ]
