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

jqp() {  # jqp <python-ausdruck ueber d> — liest JSON von stdin
  python3 -c "import sys,json;d=json.load(sys.stdin);print($1)" 2>/dev/null
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

# ------------------------------------------ Sichtbarkeit einer Anwendung
# Eine Anwendung im Arbeitsplatz kann auf Gruppen eingeschraenkt werden — etwa
# eine, fuer die nur ein Teil der Belegschaft eine Lizenz hat. Geprueft wird
# beides: dass sie aus der Liste verschwindet, **und** dass ein direkter Aufruf
# sie nicht startet. Nur das zweite ist die Absicherung.
echo
echo "Sichtbarkeit einer Anwendung"

WS=$(api "$TMP/admin.jar" "$BASE/api/templates" | python3 -c '
import sys, json
d = json.load(sys.stdin)
print(next((t["id"] for t in d if t["mode"] == "workspace" and t["apps"]), ""))')

if [ -z "$WS" ]; then
  bad "Kein Arbeitsplatz mit Anwendungen zum Prüfen vorhanden"
else
  CATALOG=$(api "$TMP/admin.jar" "$BASE/api/templates/$WS")
  APP=$(echo "$CATALOG" | jqp "d['apps'][0]['slug']")

  # Eine Gruppe, in der niemand ist. Damit ist die Anwendung fuer den
  # Testnutzer gesperrt, ohne dass sonst jemand etwas davon merkt.
  LOCK=$(api "$TMP/admin.jar" -X POST "$BASE/api/admin/groups" \
    -H 'Content-Type: application/json' \
    -d '{"name":"OTA-Prüfung Lizenz","permissions":[]}' | jqp "d.get('id','')")
  if [ -z "$LOCK" ]; then
    LOCK=$(api "$TMP/admin.jar" "$BASE/api/admin/groups" \
      | jqp "next((g['id'] for g in d if g['name'] == 'OTA-Prüfung Lizenz'), '')")
  fi

  # Katalog unveraendert zurueckschreiben, nur mit Gruppe an der ersten App.
  # Die Reihenfolge bleibt, sonst wandern die Displaynummern.
  BODY=$(echo "$CATALOG" | LOCK="$LOCK" APP="$APP" python3 -c '
import json, os, sys
d = json.load(sys.stdin)
out = []
for a in d["apps"]:
    out.append({
        "slug": a["slug"], "name": a["name"], "icon": a["icon"],
        "exec_cmd": a.get("exec_cmd", ""), "exec_args": a.get("exec_args", ""),
        "is_enabled": a["is_enabled"], "fixed_display": a.get("fixed_display"),
        "group_ids": [os.environ["LOCK"]] if a["slug"] == os.environ["APP"] else [],
    })
print(json.dumps(out))')

  # exec_cmd steht nicht in AppOut — aus der Erkennung nachziehen.
  BODY=$(api "$TMP/admin.jar" "$BASE/api/templates/$WS/apps/discover" \
    | BODY="$BODY" python3 -c '
import json, os, sys
found = {a["slug"]: a for a in json.load(sys.stdin)}
out = []
for a in json.loads(os.environ["BODY"]):
    src = found.get(a["slug"], {})
    a["exec_cmd"] = a["exec_cmd"] or src.get("exec_cmd", "/bin/true")
    a["exec_args"] = a["exec_args"] or src.get("exec_args", "")
    out.append(a)
print(json.dumps(out))')

  api "$TMP/admin.jar" -X PUT "$BASE/api/templates/$WS/apps" \
    -H 'Content-Type: application/json' -d "$BODY" >/dev/null

  SEES=$(api "$TMP/user.jar" "$BASE/api/templates" | APP="$APP" python3 -c '
import json, os, sys
d = json.load(sys.stdin)
print(sum(1 for t in d for a in t["apps"] if a["slug"] == os.environ["APP"]))')
  expect "0" "$SEES" "Eingeschränkte Anwendung steht nicht mehr in der Liste"

  ADMIN_SEES=$(api "$TMP/admin.jar" "$BASE/api/templates/$WS" | APP="$APP" python3 -c '
import json, os, sys
d = json.load(sys.stdin)
print(sum(1 for a in d["apps"] if a["slug"] == os.environ["APP"]))')
  expect "1" "$ADMIN_SEES" "Der Administrator sieht sie weiterhin"

  # Und jetzt der Teil, der zaehlt: eine eigene, laufende Session des
  # Testnutzers, und ein Aufruf mit dem gesperrten Kuerzel.
  USID=$(api "$TMP/user.jar" -X POST "$BASE/api/sessions" \
    -H 'Content-Type: application/json' -d "{\"template_id\":\"$WS\"}" \
    | jqp "d.get('id','')")
  if [ -n "$USID" ]; then
    for _ in 1 2 3 4 5 6 7 8 9 10 11 12; do
      ST=$(api "$TMP/user.jar" "$BASE/api/sessions/$USID" | jqp "d.get('status','')")
      [ "$ST" = "running" ] && break
      sleep 3
    done
    expect "403" "$(code "$TMP/user.jar" -X POST "$BASE/api/sessions/$USID/apps/$APP")" \
      "Direkter Start der gesperrten Anwendung wird abgewiesen"

    OTHER=$(echo "$CATALOG" | APP="$APP" python3 -c '
import json, os, sys
d = json.load(sys.stdin)
print(next((a["slug"] for a in d["apps"]
            if a["slug"] != os.environ["APP"] and a["is_enabled"]
            and not a.get("blocked_reason")), ""))')
    if [ -n "$OTHER" ]; then
      RC=$(code "$TMP/user.jar" -X POST "$BASE/api/sessions/$USID/apps/$OTHER")
      [ "$RC" != "403" ] && ok "Eine freie Anwendung bleibt startbar ($OTHER, HTTP $RC)" \
                         || bad "Auch die freie Anwendung $OTHER wurde abgewiesen"
    fi
    api "$TMP/user.jar" -X DELETE "$BASE/api/sessions/$USID" >/dev/null
  else
    bad "Testnutzer konnte keine eigene Session starten"
  fi

  # Aufräumen: Gruppe löschen. Dabei muss die Kennung aus dem Katalog
  # verschwinden — sonst stünde dort dauerhaft eine Gruppe, die es nicht gibt.
  api "$TMP/admin.jar" -X DELETE "$BASE/api/admin/groups/$LOCK" >/dev/null
  FREED=$(api "$TMP/admin.jar" "$BASE/api/templates/$WS" | APP="$APP" python3 -c '
import json, os, sys
d = json.load(sys.stdin)
print(next((len(a["group_ids"]) for a in d["apps"] if a["slug"] == os.environ["APP"]), -1))')
  expect "0" "$FREED" "Gelöschte Gruppe verschwindet aus dem Katalog"

  SEES=$(api "$TMP/user.jar" "$BASE/api/templates" | APP="$APP" python3 -c '
import json, os, sys
d = json.load(sys.stdin)
print(sum(1 for t in d for a in t["apps"] if a["slug"] == os.environ["APP"]))')
  expect "1" "$SEES" "Danach ist die Anwendung wieder für alle da"
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
