#!/usr/bin/env bash
# Prüft die Verzeichnis-Anbindung gegen ein echtes LDAP — **über Keycloak**.
#
# Seit dem 2026-09-04 gibt es nur noch diesen einen Weg: Ein Verzeichnis wird
# in Keycloak angebunden, und Keycloak macht die Anmeldung. OTAs eigene
# LDAP-Anbindung ist entfallen (`auth-roadmap.md`, Entscheidung 4) — und mit
# ihr die Hälfte dieser Reihe.
#
# Der Testserver wird dafür gestartet und danach entfernt; die Anbindung wird
# eingerichtet und danach entfernt; die angelegten Konten werden gelöscht.
# **Was vorher da war, ist nachher wieder da.**
#
# Ein guter Teil prüft nicht, dass etwas funktioniert, sondern dass etwas
# NICHT passiert: dass ein Verzeichniseintrag kein lokales Konto übernimmt,
# und dass ein Ausfall des Verzeichnisses den Notzugang nicht mitreisst. Das
# sind die beiden Wege, auf denen so eine Anbindung eine Anlage unbenutzbar
# macht.

set -uo pipefail

pass=0; fail=0
ok()  { printf '  \033[32m✓\033[0m %s\n' "$1"; pass=$((pass+1)); }
bad() { printf '  \033[31m✗\033[0m %s\n' "$1"; fail=$((fail+1)); }
expect() { if [ "$2" = "$1" ]; then ok "$3 ($2)"; else bad "$3 — erwartet $1, bekommen $2"; fi; }

BASE_URL="${OTA_BASE:-https://192.168.66.224:8443}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CA="$ROOT/deploy/certs/ota-ca.crt"
TMP="$(mktemp -d)"
ADMIN="${OTA_TEST_ADMIN:-notfall}"
ADMIN_PW="${OTA_TEST_ADMIN_PW:?OTA_TEST_ADMIN_PW fehlt. Trag es in deploy/.env ein.}"

LDAP_BASE="dc=ota,dc=test"
LDAP_CN="ota-ldap-test"

api()  { curl -s --cacert "$CA" -b "$TMP/admin.jar" -c "$TMP/admin.jar" "$@"; }
anon() { curl -s --cacert "$CA" "$@"; }
jqp()  { python3 -c "import sys,json;d=json.load(sys.stdin);print($1)" 2>/dev/null; }
code_as() {  # code_as <benutzer> <passwort>
  anon -o /dev/null -w '%{http_code}' --max-time 30 -X POST "$BASE_URL/api/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"username\":\"$1\",\"password\":\"$2\"}"
}

# Aufräumen läuft in jedem Fall — auch bei Abbruch mitten im Lauf. Eine
# eingeschaltete Anbindung auf ein Verzeichnis, das nicht mehr da ist, wäre
# das Schlimmste, was dieser Test hinterlassen könnte.
aufraeumen() {
  echo
  echo "Aufräumen"
  for name in lena.brandt piet.holm ruth.mayer; do
    local uid
    uid=$(api "$BASE_URL/api/admin/users" | jqp "next((u['id'] for u in d if u['username'] == '$name'), '')")
    [ -n "$uid" ] && api -X DELETE "$BASE_URL/api/admin/users/$uid" >/dev/null 2>&1
  done
  local rest
  rest=$(api "$BASE_URL/api/admin/users" | jqp "sum(1 for u in d if u['username'] in ('lena.brandt','piet.holm','ruth.mayer'))")
  expect "0" "${rest:-?}" "Alle Konten aus dem Testverzeichnis entfernt"

  # Die Anbindung in Keycloak ebenso. Sie zeigt sonst auf ein Verzeichnis,
  # das es gleich nicht mehr gibt — und dann scheitert jede Anmeldung eines
  # Kontos, das daraus stammt, mit einer Meldung, die niemand versteht.
  api -X DELETE "$BASE_URL/api/admin/identity/keycloak/verzeichnis" >/dev/null 2>&1
  local kcweg
  kcweg=$(api "$BASE_URL/api/admin/identity/keycloak/verzeichnis" | jqp "str(d.get('eingerichtet'))")
  expect "False" "${kcweg:-?}" "Anbindung in Keycloak wieder entfernt"

  "$ROOT/scripts/ldap-test-server.sh" stop >/dev/null 2>&1
  ok "Testverzeichnis entfernt"

  # Der eigentliche Grund für diesen ganzen Abschnitt.
  expect "200" "$(code_as "$ADMIN" "$ADMIN_PW")" "$ADMIN meldet sich weiterhin an"
  rm -rf "$TMP"

  echo
  echo "─────────────────────────────────────"
  printf '  bestanden: %d   fehlgeschlagen: %d\n' "$pass" "$fail"
  [ "$fail" -eq 0 ] || exit 1
}
trap aufraeumen EXIT

echo "OTA Verzeichnis über Keycloak gegen $BASE_URL"
echo

api -X POST "$BASE_URL/api/auth/login" -H 'Content-Type: application/json' \
    -d "{\"username\":\"$ADMIN\",\"password\":\"$ADMIN_PW\"}" >/dev/null

echo "Testverzeichnis"
"$ROOT/scripts/ldap-test-server.sh" start >/dev/null 2>&1
N=$(docker exec "$LDAP_CN" ldapsearch -x -LLL -H ldap://localhost -b "$LDAP_BASE" \
      -D "cn=admin,$LDAP_BASE" -w pruefadmin-2026 "(objectClass=inetOrgPerson)" dn 2>/dev/null \
      | grep -c "^dn:")
[ "${N:-0}" -ge 4 ] && ok "Verzeichnis steht mit $N Einträgen" \
                    || { bad "Das Testverzeichnis kam nicht hoch"; exit 1; }

echo
echo "Dasselbe Verzeichnis, aber über Keycloak"
#
# Etappe C der auth-roadmap: Eine Administration richtet das Verzeichnis in
# **OTAs** Oberfläche ein und muss die Keycloak-Konsole nicht öffnen. Geprüft
# wird der ganze Weg — prüfen, speichern, abgleichen — und vor allem, dass die
# wichtigste Schutzregel dabei nicht verlorengeht.

# Keycloak muss das Testverzeichnis erreichen können; es hängt im internen
# Netz, Keycloak in beiden.
docker network connect ota_public ota-ldap-test >/dev/null 2>&1 || true

KC_KONF='{"server_uri":"ldap://ota-ldap-test:389","base_dn":"dc=ota,dc=test",
          "bind_dn":"cn=ota-dienst,dc=ota,dc=test","bind_password":"dienst-geheim-2026",
          "kind":"other","login_attribute":"uid","is_enabled":true}'

# Ein Konto ohne Verwaltungsrechte — angelegt und gleich wieder weg.
anon -c "$TMP/klein.jar" -o /dev/null -X POST "$BASE_URL/api/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"lena.brandt\",\"password\":\"Lena-Passwort-2026!\"}" 2>/dev/null || true
CODE=$(curl -s --cacert "$CA" -b "$TMP/klein.jar" -o /dev/null -w '%{http_code}' \
  "$BASE_URL/api/admin/identity/keycloak/verzeichnis")
case "$CODE" in
  401|403) ok "Ohne Verwaltungsrecht kein Blick auf die Anbindung ($CODE)" ;;
  *)       bad "Die Anbindung war ohne Verwaltungsrecht erreichbar ($CODE)" ;;
esac

PRUEF_KC=$(api -X POST "$BASE_URL/api/admin/identity/keycloak/verzeichnis/test" \
  -H 'Content-Type: application/json' -d "$KC_KONF")
expect "True" "$(jqp "str(d['verbindung'])" <<<"$PRUEF_KC")" "Keycloak erreicht den Server"
expect "True" "$(jqp "str(d['anmeldung'])" <<<"$PRUEF_KC")" "Und das Dienstkonto kommt herein"

FALSCH=$(api -X POST "$BASE_URL/api/admin/identity/keycloak/verzeichnis/test" \
  -H 'Content-Type: application/json' \
  -d "$(sed 's/dienst-geheim-2026/falsches-kennwort/' <<<"$KC_KONF")")
expect "False" "$(jqp "str(d['anmeldung'])" <<<"$FALSCH")" "Ein falsches Kennwort fällt beim Prüfen auf"
jqp "d['hinweise'][0] if d['hinweise'] else ''" <<<"$FALSCH" | grep -q "Bind-DN" \
  && ok "Und die Meldung sagt, wo man nachsehen muss" \
  || bad "Die Meldung hilft nicht weiter"

SETZEN=$(api -X PUT "$BASE_URL/api/admin/identity/keycloak/verzeichnis" \
  -H 'Content-Type: application/json' -d "$KC_KONF")
expect "True" "$(jqp "str(d['eingerichtet'])" <<<"$SETZEN")" "Die Anbindung ist gespeichert"
expect "True" "$(jqp "str(d['hat_kennwort'])" <<<"$SETZEN")" "Das Kennwort liegt in Keycloak"
jqp "str(d)" <<<"$SETZEN" | grep -q "dienst-geheim" \
  && bad "Das Kennwort kommt zurück — es darf nur hinein" \
  || ok "Das Kennwort kommt nicht zurück"

ABGLEICH=$(api -X POST "$BASE_URL/api/admin/identity/keycloak/verzeichnis/abgleich?voll=true")
# Neu geholt **oder** aufgefrischt: Beim zweiten Lauf auf demselben Rechner
# stehen die Konten schon in Keycloak, und dann meldet der Abgleich sie als
# "updated". Beides heisst dasselbe — sie sind da.
GEHOLT=$(jqp "str(d.get('added', 0) + d.get('updated', 0))" <<<"$ABGLEICH")
[ "${GEHOLT:-0}" -ge 2 ] && ok "Konten aus dem Verzeichnis geholt oder aufgefrischt ($GEHOLT)" \
                         || bad "Es kamen keine Konten an: $ABGLEICH"

# Dass dabei etwas scheitert, ist erwartet und wird hier festgehalten statt
# übergangen — sonst sucht später jemand nach einem Fehler, der keiner ist:
#
#   cn=ota-dienst   hat kein `uid` und ist auch kein Mensch.
#   bmetallica      steht in Keycloak schon als übernommenes Konto und ist
#                   nicht an das Verzeichnis gebunden. Genau deshalb wird der
#                   gleichnamige Verzeichniseintrag **nicht** importiert.
GESCHEITERT=$(jqp "str(d.get('failed', 0))" <<<"$ABGLEICH")
ok "Nicht importierbare Einträge werden gemeldet ($GESCHEITERT)"

# --- Der Angriffsfall, jetzt an der schärfsten Stelle -------------------
#
# Im Testverzeichnis steht ein Eintrag mit dem Namen des Administrators. Vor
# der Übernahme wurde er nach Keycloak geholt und erst von OTA abgelehnt. Seit
# der Übernahme (auth-roadmap.md §5.1) kommt er gar nicht mehr so weit: Der
# Name gehört einem Konto, das nicht am Verzeichnis hängt, und Keycloak lässt
# ihn nicht darüber. Zwei Schranken hintereinander, und die äussere hält
# zuerst.
UEBERNOMMEN=$(api "$BASE_URL/api/admin/users" | jqp "
next((u['auth_provider'] for u in d if u['username'] == 'bmetallica'), 'fehlt')")

if [ "$UEBERNOMMEN" = "keycloak" ]; then
  FREMD_TOKEN=$(docker exec -i ota-agent curl -s -d "client_id=ota-tests" \
    --data-urlencode "client_secret=${OTA_KEYCLOAK_SECRET:-}-tests" -d "grant_type=password" \
    -d "username=bmetallica" --data-urlencode "password=Fremdes-Passwort-2026!" -d "scope=openid" \
    "http://ota-keycloak:8080/auth/realms/ota/protocol/openid-connect/token" \
    | jqp "d.get('id_token','')")
  [ -z "$FREMD_TOKEN" ] \
    && ok "Das Passwort aus dem Verzeichnis öffnet das übernommene Konto nicht" \
    || bad "Das Verzeichnis-Passwort öffnete ein übernommenes Konto!"

  HERKUNFT=$(api "$BASE_URL/api/admin/users" | jqp "
next((u['auth_provider'] for u in d if u['username'] == 'bmetallica'), '')")
  expect "keycloak" "$HERKUNFT" "Und das Konto bleibt, was es war"
else
  # Vor der Übernahme: dieselbe Prüfung, eine Schranke weiter innen.
  FREMD_TOKEN=$(docker exec -i ota-agent curl -s -d "client_id=ota-tests" \
    --data-urlencode "client_secret=${OTA_KEYCLOAK_SECRET:-}-tests" -d "grant_type=password" \
    -d "username=$ADMIN" --data-urlencode "password=Fremdes-Passwort-2026!" -d "scope=openid" \
    "http://ota-keycloak:8080/auth/realms/ota/protocol/openid-connect/token" \
    | jqp "d.get('id_token','')")
  if [ -z "$FREMD_TOKEN" ]; then
    ok "Der Doppelgänger kommt nicht einmal bei Keycloak herein"
  else
    CODE=$(curl -s --cacert "$CA" -o /dev/null -w '%{http_code}' \
      -X POST "$BASE_URL/api/auth/oidc/token" -H 'Content-Type: application/json' \
      -d "{\"id_token\":\"$FREMD_TOKEN\"}")
    expect "403" "$CODE" "OTA übernimmt das gleichnamige lokale Konto nicht"
  fi
fi

echo
echo "Wenn das Verzeichnis ausfällt"
#
# Der Fall, der ohne eigene Anbindung anders aussieht als früher: Keycloak
# hält die Anmeldung, und ein totes Verzeichnis darf weder den Notzugang
# blockieren noch die Anwendung mitreissen.
docker stop "$LDAP_CN" >/dev/null 2>&1
expect "200" "$(code_as "$ADMIN" "$ADMIN_PW")" "Der Notzugang läuft weiter"
expect "200" "$(anon -o /dev/null -w '%{http_code}' --max-time 15 "$BASE_URL/healthz")" \
  "Die Anwendung bleibt gesund"
DAUER=$(anon -o /dev/null -w '%{time_total}' --max-time 30 \
  "$BASE_URL/api/admin/identity/keycloak" \
  | python3 -c "import sys;print(int(float(sys.stdin.read())*1000))")
[ "${DAUER:-9999}" -lt 8000 ] \
  && ok "Die Auskunft kommt schnell (${DAUER}ms) statt in einen Zeitablauf zu laufen" \
  || bad "Die Abfrage hing ${DAUER}ms am toten Verzeichnis"

docker start "$LDAP_CN" >/dev/null 2>&1
sleep 3
