#!/usr/bin/env bash
# Prüft die Auskunft nach Art. 15 DSGVO (Handbuch Kapitel 08):
#
#   * Nur mit dem Recht, Nutzer zu verwalten; ein Konto ohne bekommt 403,
#     auch für sich selbst.
#   * Das ZIP enthält Stammdaten, Protokoll, Sitzungen, KI-Nutzung,
#     Sicherungen, OTA-Git und die Liste der Dateien.
#   * Es enthält **keine** Geheimnisse: keinen Passwort-Hash, keinen
#     TOTP-Startwert, keine Zugangsdaten von Sitzungen und keinen
#     Dateiinhalt. Ein Verweis aus dem Zuhause hinaus wird nicht verfolgt.
#   * Die Auskunft steht im Protokoll.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
[ -f "$ROOT/deploy/.env" ] && { set -a; . "$ROOT/deploy/.env"; set +a; }

pass=0; fail=0
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; pass=$((pass+1)); }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$1"; fail=$((fail+1)); }
expect() { if [ "$2" = "$1" ]; then ok "$3"; else bad "$3 — erwartet $1, bekommen $2"; fi; }

BASE="${1:-https://192.168.66.224:8443}"
TMP="$(mktemp -d)"
ADMIN="${OTA_TEST_ADMIN:-notfall}"
ADMIN_PW="${OTA_TEST_ADMIN_PW:?OTA_TEST_ADMIN_PW fehlt}"
PROF="${OTA_PROFILES_ROOT:-/srv/ota/profiles}"
ABL="${OTA_USERFILES_ROOT:-/srv/ota/userfiles}"
N=ota-pruef-auskunft
PW='Pruef-Auskunft-2026!'
INHALT="inhalt-$(date +%s)$$"

api()  { curl -sk -b "$TMP/admin.jar" -c "$TMP/admin.jar" "$@"; }
code() { curl -sk -o /dev/null -w '%{http_code}' -b "$TMP/admin.jar" "$@"; }
jqp()  { python3 -c "import sys,json;d=json.load(sys.stdin);print($1)" 2>/dev/null; }
sql()  { docker exec ota-db psql -U ota -d ota -tAc "$1"; }
uid_von() { api "$BASE/api/admin/users" | jqp "next((u['id'] for u in d if u['username'] == '$1'), '')"; }

U=""
aufraeumen() {
  if [ -n "$U" ]; then
    sql "DELETE FROM ki_stunden WHERE user_id = '$U'" >/dev/null
    sql "DELETE FROM backups WHERE username = '$N'" >/dev/null
    api -X DELETE "$BASE/api/admin/users/$U" >/dev/null
    rm -rf "${PROF:?}/$U" "${ABL:?}/$U" "$PROF/.geloescht/$U" "$PROF/.geloescht/$U.json" \
           "$ABL/.geloescht/$U" "$ABL/.geloescht/$U.json"
  fi
  rm -rf "$TMP"
}
trap aufraeumen EXIT

echo "Auskunft nach Art. 15"
curl -sk -c "$TMP/admin.jar" -o /dev/null -X POST "$BASE/api/auth/login" -H 'Content-Type: application/json' \
  -d "{\"username\":\"$ADMIN\",\"password\":\"$ADMIN_PW\"}"
alt=$(uid_von "$N"); [ -n "$alt" ] && api -X DELETE "$BASE/api/admin/users/$alt" >/dev/null
# Ein lokales Konto (wie in test-authz.sh), damit es sich ohne Keycloak
# anmelden kann; nur in der Gruppe users.
"$ROOT/scripts/lokales-testkonto.sh" "$N" "$PW" "$N@ota.invalid" users >/dev/null
U=$(uid_von "$N")
[ -n "$U" ] && ok "Prüfkonto angelegt" || bad "Prüfkonto angelegt"
sql "INSERT INTO audit_log (id, ts, action, object_type, object_id, actor_name, detail)
     VALUES (gen_random_uuid(), now(), 'user.created', 'user', '$U', '$ADMIN', '{}')" >/dev/null
# Anmelden, solange es noch keinen zweiten Faktor hat (unten bekommt es einen).
curl -sk -c "$TMP/nutzer.jar" -o /dev/null -X POST "$BASE/api/auth/login" -H 'Content-Type: application/json' \
  -d "{\"username\":\"$N\",\"password\":\"$PW\"}"

mkdir -p "$PROF/$U/user/Documents" "$ABL/$U"
echo "$INHALT" > "$PROF/$U/user/Documents/brief.txt"
echo "$INHALT" > "$ABL/$U/ablage.txt"
ln -sfn /etc "$PROF/$U/user/ausweg"
chown -R 1000:1000 "$PROF/$U" "$ABL/$U"
sql "UPDATE users SET totp_secret = 'GEHEIMERSTARTWERT' WHERE id = '$U'" >/dev/null
sql "INSERT INTO backups (id, kind, user_id, username, path, status, trigger, started_at, size_bytes, file_count, log)
     VALUES (gen_random_uuid(), 'profile', '$U', '$N', '/srv/ota/backups/profiles/$N-pruef.tar.zst', 'ok', 'manual', now(), 0, 0, '')" >/dev/null
sql "INSERT INTO ki_stunden (stunde, user_id, template_id, server, modell, werkzeug, user_name, arbeitsplatz, anfragen, fehler, verbindungen, ein, aus, dauer_ms, bytes)
     VALUES (date_trunc('hour', now()), '$U', '00000000-0000-0000-0000-000000000000', 'pruef', 'pruef-modell', 'opencode', '$N', '', 3, 0, 0, 10, 20, 30, 40)" >/dev/null

# Ohne Recht: auch nicht für sich selbst.
expect "403" "$(curl -sk -o /dev/null -w '%{http_code}' -b "$TMP/nutzer.jar" "$BASE/api/admin/users/$U/auskunft")" \
  "Ohne Verwaltungsrecht: 403, auch für das eigene Konto"
expect "404" "$(code "$BASE/api/admin/users/00000000-0000-0000-0000-000000000001/auskunft")" "Unbekanntes Konto: 404"

KOPF=$(curl -sk -b "$TMP/admin.jar" -D - -o "$TMP/a.zip" "$BASE/api/admin/users/$U/auskunft" | tr -d '\r')
grep -qi "^content-type: application/zip" <<<"$KOPF" && ok "Ein ZIP" || bad "Ein ZIP — $(head -3 <<<"$KOPF")"
grep -qi "filename=\"auskunft-$N-" <<<"$KOPF" && ok "… mit sprechendem Dateinamen" || bad "… mit sprechendem Dateinamen"
mkdir -p "$TMP/a" && python3 -c 'import zipfile,sys; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])' "$TMP/a.zip" "$TMP/a"
DA=0
for f in liesmich.txt konto.json protokoll.csv terminal.csv sitzungen.csv ki_anfragen.csv ki_stunden.csv \
         software.csv sicherungen.csv git.json dateien.csv; do
  if [ -f "$TMP/a/$f" ]; then DA=$((DA+1)); else bad "$f fehlt"; fi
done
expect "11" "$DA" "Alle elf Dateien da"

expect "$N" "$(jqp "d['username']" < "$TMP/a/konto.json")" "Stammdaten: Anmeldename"
expect "True" "$(jqp "d['zweiter_faktor_lokal']" < "$TMP/a/konto.json")" "… ob ein zweiter Faktor da ist"
ALLES=$(cat "$TMP/a"/*)
for geheim in password_hash totp_secret GEHEIMERSTARTWERT vnc_secret "$INHALT"; do
  grep -q -- "$geheim" <<<"$ALLES" && bad "Enthält $geheim" || ok "Enthält kein $geheim"
done
grep -q "user.created" "$TMP/a/protokoll.csv" && ok "Protokoll: das Anlegen des Kontos" || bad "Protokoll: das Anlegen des Kontos"
grep -q "user/Documents/brief.txt" "$TMP/a/dateien.csv" && ok "Dateiliste: Zuhause" || bad "Dateiliste: Zuhause"
grep -q "ablage;ablage.txt" "$TMP/a/dateien.csv" && ok "Dateiliste: Ablage" || bad "Dateiliste: Ablage"
grep -q "user/ausweg;.*;True" "$TMP/a/dateien.csv" && ok "Verweis aus dem Zuhause hinaus als Verweis gelistet" \
  || bad "Verweis aus dem Zuhause hinaus als Verweis gelistet"
grep -q "passwd" "$TMP/a/dateien.csv" && bad "… und verfolgt (/etc steht drin)" || ok "… und nicht verfolgt"
grep -q "$N-pruef.tar.zst" "$TMP/a/sicherungen.csv" && ok "Sicherungen" || bad "Sicherungen"
grep -q "pruef-modell" "$TMP/a/ki_stunden.csv" && ok "KI-Nutzung" || bad "KI-Nutzung"
head -c 3 "$TMP/a/protokoll.csv" | od -An -tx1 | grep -q "ef bb bf" && ok "CSV mit BOM für Excel" || bad "CSV mit BOM für Excel"
grep -q "Art. 15 Abs. 4" "$TMP/a/liesmich.txt" && ok "liesmich.txt erklärt die Abwägung" || bad "liesmich.txt erklärt die Abwägung"

expect "1" "$(sql "SELECT count(*) FROM audit_log WHERE action = 'user.auskunft' AND object_id = '$U' AND actor_name = '$ADMIN'")" \
  "Steht mit Namen der Verwaltung im Protokoll"

echo
echo "Ergebnis: $pass bestanden, $fail fehlgeschlagen"
[ "$fail" -eq 0 ]
