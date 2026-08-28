#!/usr/bin/env bash
# Prüft die Verzeichnis-Anbindung (plan.md §9.4) gegen ein echtes LDAP.
#
# Der Testserver wird dafür gestartet und danach entfernt; die Anbindung wird
# eingerichtet und danach abgeschaltet; die angelegten Verzeichniskonten
# werden gelöscht. **Was vorher da war, ist nachher wieder da.**
#
# Die halbe Suite prüft nicht, dass etwas funktioniert, sondern dass etwas
# NICHT passiert: dass ein Verzeichniseintrag kein lokales Konto übernimmt,
# und dass ein Ausfall des Verzeichnisses die lokale Anmeldung nicht
# mitreisst. Das sind die beiden Wege, auf denen so eine Anbindung eine
# Anlage unbenutzbar macht.

set -uo pipefail

pass=0; fail=0
ok()  { printf '  \033[32m✓\033[0m %s\n' "$1"; pass=$((pass+1)); }
bad() { printf '  \033[31m✗\033[0m %s\n' "$1"; fail=$((fail+1)); }
expect() { if [ "$2" = "$1" ]; then ok "$3 ($2)"; else bad "$3 — erwartet $1, bekommen $2"; fi; }

BASE_URL="${OTA_BASE:-https://192.168.66.224:8443}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CA="$ROOT/deploy/certs/ota-ca.crt"
TMP="$(mktemp -d)"
ADMIN="${OTA_TEST_ADMIN:-bmetallica}"
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
  api -X PUT "$BASE_URL/api/admin/identity" -H 'Content-Type: application/json' \
    -d '{"is_enabled": false}' >/dev/null 2>&1
  local aus
  aus=$(api "$BASE_URL/api/admin/identity" | jqp "d.get('is_enabled')")
  [ "$aus" = "False" ] && ok "Anbindung wieder abgeschaltet" \
                       || bad "Die Anbindung blieb eingeschaltet — bitte von Hand prüfen!"

  for name in lena.brandt piet.holm ruth.mayer; do
    local uid
    uid=$(api "$BASE_URL/api/admin/users" | jqp "next((u['id'] for u in d if u['username'] == '$name'), '')")
    [ -n "$uid" ] && api -X DELETE "$BASE_URL/api/admin/users/$uid" >/dev/null 2>&1
  done
  local rest
  rest=$(api "$BASE_URL/api/admin/users" | jqp "sum(1 for u in d if u['auth_provider'] == 'ldap')")
  expect "0" "${rest:-?}" "Alle Verzeichniskonten entfernt"

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

echo "OTA Verzeichnis-Anbindung gegen $BASE_URL"
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

# ------------------------------------------------------------ Einrichten
echo
echo "Einrichten und prüfen"
api -X PUT "$BASE_URL/api/admin/identity" -H 'Content-Type: application/json' -d "{
  \"server_uri\": \"ldap://$LDAP_CN:389\",
  \"tls_mode\": \"none\",
  \"bind_dn\": \"cn=ota-dienst,$LDAP_BASE\",
  \"bind_password\": \"dienst-geheim-2026\",
  \"base_dn\": \"$LDAP_BASE\",
  \"login_attribute\": \"uid\",
  \"group_base_dn\": \"ou=groups,$LDAP_BASE\",
  \"jit_create\": true
}" >/dev/null

GEHEIM=$(api "$BASE_URL/api/admin/identity" | jqp "'bind_password' in d")
expect "False" "$GEHEIM" "Das Kennwort des Dienstkontos kommt nie zurück"
HAT=$(api "$BASE_URL/api/admin/identity" | jqp "d.get('has_bind_password')")
expect "True" "$HAT" "Stattdessen nur die Auskunft, dass eines hinterlegt ist"

PRUEF=$(api -X POST "$BASE_URL/api/admin/identity/test" -H 'Content-Type: application/json' \
  -d '{"probe_login":"ruth.mayer"}')
expect "5" "$(echo "$PRUEF" | jqp "d.get('eintraege')")" "Der Prüf-Knopf findet die Einträge"
grep -q '"entwicklung"' <<<"$PRUEF" \
  && ok "Und die Gruppen des Verzeichnisses" \
  || bad "Die Gruppen fehlen: $(echo "$PRUEF" | head -c 120)"
echo "$PRUEF" | jqp "d['person']['gruppen']" | grep -q "verwaltung" \
  && ok "Für einen einzelnen Namen stimmen die Gruppen" \
  || bad "Die Gruppen von ruth.mayer stimmen nicht"

# Ein leeres Passwort darf nicht durchgehen. Ein LDAP-Bind ohne Passwort gilt
# als anonyme Anmeldung und **gelingt** — wer das übersieht, baut eine
# Anmeldung, bei der ein leeres Feld jeden hereinlässt.
USERS_GID=$(api "$BASE_URL/api/admin/groups" | jqp "next(g['id'] for g in d if g['slug'] == 'users')")
api -X PUT "$BASE_URL/api/admin/identity" -H 'Content-Type: application/json' \
  -d "{\"group_map\": {\"entwicklung\": \"$USERS_GID\"}, \"is_enabled\": true}" >/dev/null
expect "401" "$(code_as lena.brandt '')" "Ein leeres Passwort wird abgelehnt"

# --------------------------------------------------------- Anmelden
echo
echo "Anmelden aus dem Verzeichnis"
ANTWORT=$(anon --max-time 30 -X POST "$BASE_URL/api/auth/login" -H 'Content-Type: application/json' \
  -d '{"username":"lena.brandt","password":"Lena-Pruef-2026!"}')
grep -q '"username": *"lena.brandt"' <<<"$ANTWORT" \
  && ok "Erste Anmeldung legt das Konto an" \
  || bad "Das Konto wurde nicht angelegt: $(echo "$ANTWORT" | head -c 120)"
echo "$ANTWORT" | jqp "d.get('groups')" | grep -q "users" \
  && ok "Die zugeordnete Gruppe greift (entwicklung → users)" \
  || bad "Die Gruppenzuordnung greift nicht"
grep -q '"display_name": *"Lena Brandt"' <<<"$ANTWORT" \
  && ok "Name aus dem Verzeichnis übernommen" \
  || bad "Der Anzeigename fehlt"

expect "401" "$(code_as lena.brandt falsch)" "Falsches Passwort wird abgelehnt"
expect "401" "$(code_as gibtesnicht egal)" "Ein unbekannter Name wird abgelehnt"

ANTWORT=$(anon --max-time 30 -X POST "$BASE_URL/api/auth/login" -H 'Content-Type: application/json' \
  -d '{"username":"piet.holm","password":"Piet-Pruef-2026!"}')
echo "$ANTWORT" | jqp "len(d.get('groups') or [])" | grep -qx "0" \
  && ok "Eine nicht zugeordnete Gruppe (design) bringt keine Rechte mit" \
  || bad "piet.holm bekam Gruppen, die niemand zugeordnet hat"

# ----------------------------------------- Das lokale Konto ist unantastbar
echo
echo "Das lokale Konto bleibt unangetastet"
expect "401" "$(code_as "$ADMIN" 'Fremdes-Passwort-2026!')" \
  "Der gleichnamige Verzeichniseintrag kommt nicht herein"
expect "200" "$(code_as "$ADMIN" "$ADMIN_PW")" \
  "$ADMIN meldet sich weiterhin mit seinem eigenen Passwort an"
ART=$(api "$BASE_URL/api/admin/users" | jqp "next(u['auth_provider'] for u in d if u['username'] == '$ADMIN')")
expect "local" "$ART" "Und bleibt ein lokales Konto"

# --------------------------------------------------------- Abgleich
echo
echo "Abgleich"
docker exec -i "$LDAP_CN" ldapmodify -x -H ldap://localhost \
  -D "cn=admin,$LDAP_BASE" -w pruefadmin-2026 >/dev/null 2>&1 <<LDIF
dn: cn=entwicklung,ou=groups,$LDAP_BASE
changetype: modify
add: member
member: uid=piet.holm,ou=people,$LDAP_BASE
LDIF
api -X POST "$BASE_URL/api/admin/identity/sync" >/dev/null
GRUPPEN=$(api "$BASE_URL/api/admin/users" | jqp "next(len(u['group_ids']) for u in d if u['username'] == 'piet.holm')")
expect "1" "$GRUPPEN" "Eine neue Mitgliedschaft im Verzeichnis kommt an"

docker exec "$LDAP_CN" ldapdelete -x -H ldap://localhost -D "cn=admin,$LDAP_BASE" \
  -w pruefadmin-2026 "uid=piet.holm,ou=people,$LDAP_BASE" >/dev/null 2>&1
ERG=$(api -X POST "$BASE_URL/api/admin/identity/sync")
expect "1" "$(echo "$ERG" | jqp "d.get('deaktiviert')")" "Ein Austritt deaktiviert das Konto"
NOCHDA=$(api "$BASE_URL/api/admin/users" | jqp "sum(1 for u in d if u['username'] == 'piet.holm')")
expect "1" "$NOCHDA" "Gelöscht wird es nicht — das entscheidet ein Mensch"
expect "403" "$(code_as piet.holm 'Piet-Pruef-2026!')" "Und es kommt nicht mehr herein"

# ------------------------------------------------- Ausfall des Verzeichnisses
echo
echo "Wenn das Verzeichnis ausfällt"
docker stop "$LDAP_CN" >/dev/null 2>&1
expect "200" "$(code_as "$ADMIN" "$ADMIN_PW")" "Lokale Anmeldung läuft weiter"
expect "401" "$(code_as lena.brandt 'Lena-Pruef-2026!')" "Verzeichniskonten kommen nicht herein"
DAUER=$(anon -o /dev/null -w '%{time_total}' --max-time 30 -X POST "$BASE_URL/api/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"username":"lena.brandt","password":"Lena-Pruef-2026!"}' \
  | python3 -c "import sys;print(int(float(sys.stdin.read())*1000))")
[ "${DAUER:-9999}" -lt 8000 ] \
  && ok "Die Ablehnung kommt schnell (${DAUER}ms) statt in einen Zeitablauf zu laufen" \
  || bad "Die Anmeldung hing ${DAUER}ms am toten Verzeichnis"
expect "200" "$(anon -o /dev/null -w '%{http_code}' --max-time 15 "$BASE_URL/healthz")" \
  "Die Anwendung bleibt gesund"

docker start "$LDAP_CN" >/dev/null 2>&1
for _ in $(seq 1 20); do
  [ "$(code_as lena.brandt 'Lena-Pruef-2026!')" = "200" ] && break
  sleep 2
done
expect "200" "$(code_as lena.brandt 'Lena-Pruef-2026!')" "Nach der Rückkehr geht es von selbst weiter"
