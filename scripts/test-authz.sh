#!/usr/bin/env bash
# Autorisierungstests. Prueft, dass ein normaler Nutzer beweisbar nichts
# Administratives tun und keine fremde Session sehen kann.
#
# Aufruf:  ./scripts/test-authz.sh [basis-url]

set -uo pipefail

BASE="${1:-https://192.168.66.224:8443}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CA="$ROOT/deploy/certs/ota-ca.crt"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

ADMIN_USER="${OTA_TEST_ADMIN:-bmetallica}"
ADMIN_PW="${OTA_TEST_ADMIN_PW:?OTA_TEST_ADMIN_PW fehlt. Trag es in deploy/.env ein.}"
TEST_USER="ota-testnutzer"
TEST_PW="TestNutzer2026!ab"

pass=0; fail=0
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; pass=$((pass+1)); }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$1"; fail=$((fail+1)); }

api()  { curl -s --cacert "$CA" -b "$1" -c "$1" "${@:2}"; }
code() { curl -s --cacert "$CA" -b "$1" -o /dev/null -w '%{http_code}' "${@:2}"; }

expect() {  # expect <erwartet> <ist> <beschreibung>
  if [ "$2" = "$1" ]; then ok "$3 ($2)"; else bad "$3 — erwartet $1, bekommen $2"; fi
}

echo "OTA Autorisierungstests gegen $BASE"
echo

# ---------------------------------------------------------------- Anmeldung
login() {  # login <jar> <user> <pw>
  api "$1" -X POST "$BASE/api/auth/login" -H 'Content-Type: application/json' \
      -d "{\"username\":\"$2\",\"password\":\"$3\"}" >/dev/null
}

echo "Anmeldung"
login "$TMP/admin.jar" "$ADMIN_USER" "$ADMIN_PW"
IS_ADMIN=$(api "$TMP/admin.jar" "$BASE/api/auth/me" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("is_admin"))' 2>/dev/null)
expect "True" "$IS_ADMIN" "Administrator ist angemeldet"

expect "401" "$(code /dev/null "$BASE/api/auth/me")" "Ohne Cookie kein Zugriff auf /me"
expect "401" "$(curl -s --cacert "$CA" -o /dev/null -w '%{http_code}' -X POST "$BASE/api/auth/login" \
  -H 'Content-Type: application/json' -d "{\"username\":\"$ADMIN_USER\",\"password\":\"falsch\"}")" \
  "Falsches Passwort wird abgelehnt"

# ------------------------------------------------------- Testnutzer anlegen
echo
echo "Testnutzer vorbereiten"
USERS_GID=$(api "$TMP/admin.jar" "$BASE/api/admin/groups" \
  | python3 -c 'import sys,json;print([g["id"] for g in json.load(sys.stdin) if g["slug"]=="users"][0])')

EXISTING=$(api "$TMP/admin.jar" "$BASE/api/admin/users" \
  | python3 -c "import sys,json;m=[u['id'] for u in json.load(sys.stdin) if u['username']=='$TEST_USER'];print(m[0] if m else '')")

if [ -n "$EXISTING" ]; then
  api "$TMP/admin.jar" -X PUT "$BASE/api/admin/users/$EXISTING" -H 'Content-Type: application/json' \
    -d "{\"username\":\"$TEST_USER\",\"password\":\"$TEST_PW\",\"group_ids\":[\"$USERS_GID\"]}" >/dev/null
else
  api "$TMP/admin.jar" -X POST "$BASE/api/admin/users" -H 'Content-Type: application/json' \
    -d "{\"username\":\"$TEST_USER\",\"password\":\"$TEST_PW\",\"group_ids\":[\"$USERS_GID\"]}" >/dev/null
fi
ok "Testnutzer $TEST_USER steht bereit (nur Gruppe users)"

login "$TMP/user.jar" "$TEST_USER" "$TEST_PW"
# Wechsel des Passworts ist erzwungen, blockiert die Anmeldung aber nicht.
U_ADMIN=$(api "$TMP/user.jar" "$BASE/api/auth/me" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("is_admin"))' 2>/dev/null)
expect "False" "$U_ADMIN" "Testnutzer ist kein Administrator"

# ---------------------------------------------------- Admin-Endpunkte sperren
echo
echo "Admin-Endpunkte gegen normalen Nutzer"
for path in /api/admin/users /api/admin/groups /api/admin/host /api/admin/images /api/admin/audit; do
  expect "403" "$(code "$TMP/user.jar" "$BASE$path")" "GET $path verweigert"
done
expect "403" "$(code "$TMP/user.jar" -X POST "$BASE/api/templates" -H 'Content-Type: application/json' \
  -d '{"friendly_name":"Schmuggel","image_ref":"alpine","cores":1,"memory_bytes":268435456}')" \
  "POST /api/templates verweigert"

# --------------------------------------------------------- fremde Session
echo
echo "Fremde Session"
SID=$(api "$TMP/admin.jar" "$BASE/api/sessions" \
  | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d[0]["id"] if d else "")')

# Ohne laufende Session lässt sich der wichtigste Teil nicht prüfen. Statt
# ihn zu überspringen, stellt der Test den Zustand selbst her — sonst hängt
# das Ergebnis davon ab, was ein vorheriger Test hinterlassen hat.
if [ -z "$SID" ]; then
  TPL=$(api "$TMP/admin.jar" "$BASE/api/templates" \
    | python3 -c 'import sys,json;d=json.load(sys.stdin);print(next((t["id"] for t in d if t["is_enabled"]), ""))')
  if [ -n "$TPL" ]; then
    SID=$(api "$TMP/admin.jar" -X POST "$BASE/api/sessions" \
      -H 'Content-Type: application/json' -d "{\"template_id\":\"$TPL\"}" \
      | python3 -c 'import sys,json;print(json.load(sys.stdin).get("id",""))')
    [ -n "$SID" ] && { echo "  (Session für die Prüfung gestartet)"; sleep 18; }
  fi
fi

if [ -n "$SID" ]; then
  expect "200" "$(code "$TMP/admin.jar" "$BASE/s/$SID/")" "Eigentümer erreicht seine Session"
  expect "403" "$(code "$TMP/user.jar"  "$BASE/s/$SID/")" "Fremder Nutzer wird abgewiesen"
  expect "401" "$(code /dev/null        "$BASE/s/$SID/")" "Ohne Anmeldung abgewiesen"
  expect "404" "$(code "$TMP/user.jar" -X DELETE "$BASE/api/sessions/$SID")" \
    "Fremde Session löschen nicht möglich"
  SEEN=$(api "$TMP/user.jar" "$BASE/api/sessions?all_users=true" \
    | python3 -c 'import sys,json;print(len(json.load(sys.stdin)))')
  expect "0" "$SEEN" "all_users=true zeigt einem Nutzer nichts Fremdes"
else
  bad "Keine laufende Session zum Prüfen vorhanden"
fi

# ----------------------------------------------------------- Zwischenablage
echo
echo "Zwischenablage-Voraussetzungen"
HDRS=$(curl -sI --cacert "$CA" "$BASE/")
echo "$HDRS" | grep -qi 'permissions-policy.*clipboard-read' \
  && ok "Permissions-Policy erlaubt clipboard-read" || bad "Permissions-Policy fehlt oder verbietet clipboard-read"
echo "$HDRS" | grep -qi 'permissions-policy.*clipboard-write' \
  && ok "Permissions-Policy erlaubt clipboard-write" || bad "clipboard-write fehlt"
echo "$HDRS" | grep -qi "frame-ancestors 'self'" \
  && ok "CSP erlaubt das eigene iframe" || bad "CSP frame-ancestors fehlt"
[ "$(curl -s --cacert "$CA" -o /dev/null -w '%{ssl_verify_result}' "$BASE/")" = "0" ] \
  && ok "TLS-Kette gültig (Secure Context vorhanden)" || bad "TLS-Kette ungültig"

# --------------------------------------------------------------------------
# Zweiter Faktor
#
# Am Wegwerf-Konto, nicht am echten: Der Test schaltet ihn ein, benutzt einen
# Rueckfallcode und schaltet ihn wieder ab. Ein Test, der das Konto eines
# Menschen anfasst, waere ein Test, den niemand zweimal laufen laesst.
# --------------------------------------------------------------------------
echo

jqp() {  # jqp <python-ausdruck ueber d> — liest JSON von stdin
  python3 -c "import sys,json;d=json.load(sys.stdin);print($1)" 2>/dev/null
}

otp() {  # otp <geheimnis> -> aktueller Zeitcode
  docker compose -f "$ROOT/deploy/docker-compose.yml" exec -T -e S="$1" api \
    python -c "import pyotp,os;print(pyotp.TOTP(os.environ['S']).now())" 2>/dev/null | tr -d '\r'
}

SETUP=$(curl -s --cacert "$CA" -b "$TMP/user.jar" -X POST "$BASE/api/auth/totp/setup")
SECRET=$(echo "$SETUP" | jqp "d.get('secret','')")
[ -n "$SECRET" ] && ok "Einrichtung liefert ein Geheimnis" || bad "Keine Einrichtung möglich"
echo "$SETUP" | grep -q "<svg" && ok "Einrichtungscode kommt als Bild mit" \
                               || bad "Kein Einrichtungscode im Ergebnis"

CODES=$(curl -s --cacert "$CA" -b "$TMP/user.jar" -X POST "$BASE/api/auth/totp/activate" \
  -H 'Content-Type: application/json' \
  -d "{\"secret\":\"$SECRET\",\"code\":\"$(otp "$SECRET")\"}")
N=$(echo "$CODES" | jqp "len(d.get('codes',[]))")
[ "${N:-0}" -eq 10 ] && ok "Zehn Rückfallcodes bei der Einrichtung" \
                     || bad "Rückfallcodes fehlen (bekam ${N:-0})"
RC=$(echo "$CODES" | jqp "d['codes'][0]")

# Ohne Code kommt niemand mehr herein.
OUT=$(curl -s --cacert "$CA" -X POST "$BASE/api/auth/login" -H 'Content-Type: application/json' \
  -d "{\"username\":\"$TEST_USER\",\"password\":\"$TEST_PW\"}")
echo "$OUT" | grep -q "Code aus deiner App" \
  && ok "Anmeldung ohne zweiten Faktor wird abgelehnt" \
  || bad "Anmeldung ohne zweiten Faktor ging durch"

# Mit Rückfallcode schon — und danach ist dieser Code verbraucht.
OUT=$(curl -s --cacert "$CA" -X POST "$BASE/api/auth/login" -H 'Content-Type: application/json' \
  -d "{\"username\":\"$TEST_USER\",\"password\":\"$TEST_PW\",\"totp\":\"$RC\"}")
LEFT=$(echo "$OUT" | jqp "d.get('recovery_left',-1)")
[ "$LEFT" = "9" ] && ok "Rückfallcode lässt herein und wird verbraucht (9 übrig)" \
                  || bad "Rückfallcode wirkte nicht (übrig: $LEFT)"

OUT=$(curl -s --cacert "$CA" -X POST "$BASE/api/auth/login" -H 'Content-Type: application/json' \
  -d "{\"username\":\"$TEST_USER\",\"password\":\"$TEST_PW\",\"totp\":\"$RC\"}")
echo "$OUT" | grep -q "stimmt nicht" \
  && ok "Derselbe Rückfallcode wirkt kein zweites Mal" \
  || bad "Ein verbrauchter Rückfallcode ging erneut durch"

# Abschalten verlangt Passwort UND Code.
OUT=$(curl -s --cacert "$CA" -b "$TMP/user.jar" -X DELETE "$BASE/api/auth/totp" \
  -H 'Content-Type: application/json' -d "{\"password\":\"$TEST_PW\",\"code\":\"000000\"}")
echo "$OUT" | grep -q "stimmt nicht" \
  && ok "Abschalten ohne gültigen Code wird verweigert" \
  || bad "Zweiter Faktor liess sich ohne Code abschalten"

curl -s --cacert "$CA" -b "$TMP/user.jar" -X DELETE "$BASE/api/auth/totp" \
  -H 'Content-Type: application/json' \
  -d "{\"password\":\"$TEST_PW\",\"code\":\"$(otp "$SECRET")\"}" >/dev/null
STATE=$(curl -s --cacert "$CA" -b "$TMP/user.jar" "$BASE/api/auth/me" | jqp "d.get('totp_enabled')")
[ "$STATE" = "False" ] && ok "Abschalten mit Passwort und Code gelingt" \
                       || bad "Zweiter Faktor blieb an"

echo
echo "─────────────────────────────────────"
printf '  bestanden: %d   fehlgeschlagen: %d\n' "$pass" "$fail"
[ "$fail" -eq 0 ] || exit 1
