#!/usr/bin/env bash
# Prüft das Zuordnen eines Domänenkontos zu einem bestehenden OTA-Konto
# (Handbuch Kapitel 08, 2026-10-21).
#
# Der Ablauf aus dem Betrieb: Jemand hat ein OTA-Konto mit Arbeitsplätzen.
# Dann meldet er sich mit seinem Domänenkonto (LDAP) an, OTA legt dafür ein
# neues, leeres Konto an, und die Verwaltung ordnet das Domänenkonto dem
# alten zu. Danach:
#
#   * gibt es nur noch das alte Konto — gleiche Kennung, also gleiche
#     Sitzungen, Zuhause und Ablagen — unter dem Namen aus dem Verzeichnis;
#   * meldet es sich über das Verzeichnis an und landet in genau diesem Konto;
#   * ist das bei der Domänenanmeldung entstandene Konto weg;
#   * kommt es mit dem alten Passwort nicht mehr herein, weder lokal noch
#     über das alte Konto in Keycloak (dort nur deaktiviert, nie gelöscht).
#
# Geprüft für beide Arten alter Konten: von OTA in Keycloak angelegt, und
# lokal (Bestand aus der Zeit vor Keycloak). Das Notfallkonto lässt sich
# nicht verknüpfen.
#
# Startet das Testverzeichnis (scripts/ldap-test-server.sh) und räumt es ab.
set -uo pipefail

pass=0; fail=0
A=""
ok()  { printf '  \033[32m✓\033[0m %s\n' "$1"; pass=$((pass+1)); }
bad() { printf '  \033[31m✗\033[0m %s\n' "$1"; fail=$((fail+1)); }
expect() { if [ "$2" = "$1" ]; then ok "$3 ($2)"; else bad "$3 — erwartet $1, bekommen $2"; fi; }

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
[ -f "$ROOT/deploy/.env" ] && [ -z "${OTA_TEST_ADMIN_PW:-}" ] && { set -a; . "$ROOT/deploy/.env"; set +a; }
BASE_URL="${OTA_BASE:-https://192.168.66.224:8443}"
CA="$ROOT/deploy/certs/ota-ca.crt"
TMP="$(mktemp -d)"
ADMIN="${OTA_TEST_ADMIN:-notfall}"
ADMIN_PW="${OTA_TEST_ADMIN_PW:?OTA_TEST_ADMIN_PW fehlt. Trag es in deploy/.env ein.}"
PROFILES="${OTA_PROFILES_ROOT:-/srv/ota/profiles}"
ALT_KC="ota-pruef-altkonto"
ALT_LOKAL="ota-pruef-altlokal"
PW="Altes-Passwort-2026!"

api()  { curl -s --cacert "$CA" -b "$TMP/admin.jar" -c "$TMP/admin.jar" -H 'Content-Type: application/json' "$@"; }
jqp()  { python3 -c "import sys,json;d=json.load(sys.stdin);print($1)" 2>/dev/null; }
anmelden() {  # anmelden <name> <passwort> -> 0 bei Erfolg, Keksdose $TMP/<name>.jar
  rm -f "$TMP/$1.jar"
  python3 "$ROOT/scripts/kc_anmelden.py" "$BASE_URL" "$1" "$2" "$TMP/$1.jar" >/dev/null 2>&1
}
me() { curl -s --cacert "$CA" -b "$TMP/$1.jar" "$BASE_URL/api/auth/me" | jqp "$2"; }
lokal_an() {
  curl -s --cacert "$CA" -o /dev/null -w '%{http_code}' -X POST "$BASE_URL/api/auth/login" \
    -H 'Content-Type: application/json' -d "{\"username\":\"$1\",\"password\":\"$2\"}"
}
uid() { api "$BASE_URL/api/admin/users" | jqp "next((u['id'] for u in d if u['username'] == '$1'), '')"; }
anzahl() { api "$BASE_URL/api/admin/users" | jqp "sum(1 for u in d if u['username'] == '$1')"; }
sub_von() {  # sub_von <name> <suche> — Kennung des Domänenkontos aus der Suche
  api "$BASE_URL/api/admin/users/$2/domaenenkonten?q=$1" | jqp "next((k['sub'] for k in d if k['username'] == '$1'), '')"
}
sitzung_anlegen() {  # sitzung_anlegen <user-id> — eine angehaltene Sitzung, wie sie ein Arbeitsplatz hinterlässt
  docker exec -i -e U="$1" -w /app -e PYTHONPATH=/app ota-api python - <<'PY'
import os, uuid
from sqlalchemy import select
from ota.db import SessionLocal
from ota.models import Session, Template
db = SessionLocal()
t = db.scalars(select(Template)).first()
s = Session(user_id=uuid.UUID(os.environ["U"]), template_id=t.id, status="stopped",
            cores=1, memory_bytes=1024 ** 3, vnc_secret="pruef",
            end_reason="pruef-verknuepfen")
db.add(s); db.commit(); print(s.id)
PY
}
sitzung_von() {  # sitzung_von <session-id> -> user-id
  docker exec -i -e S="$1" -w /app -e PYTHONPATH=/app ota-api python - <<'PY'
import os, uuid
from ota.db import SessionLocal
from ota.models import Session
s = SessionLocal().get(Session, uuid.UUID(os.environ["S"]))
print(s.user_id if s else "")
PY
}

aufraeumen() {
  echo
  echo "Aufräumen"
  for name in lena.brandt ruth.mayer piet.holm "$ALT_KC" "$ALT_LOKAL"; do
    local u; u=$(uid "$name")
    [ -n "$u" ] && api -X DELETE "$BASE_URL/api/admin/users/$u" >/dev/null 2>&1
  done
  api -X DELETE "$BASE_URL/api/admin/identity/keycloak/verzeichnis" >/dev/null 2>&1
  # Nur das Zuhause, das dieser Lauf selbst angelegt hat.
  [[ "${A:-}" =~ ^[0-9a-f-]{36}$ ]] && rm -rf "${PROFILES:?}/$A"
  "$ROOT/scripts/ldap-test-server.sh" stop >/dev/null 2>&1
  ok "Testkonten und Testverzeichnis entfernt"
  rm -rf "$TMP"
  echo
  printf '  bestanden: %d   fehlgeschlagen: %d\n' "$pass" "$fail"
  [ "$fail" -eq 0 ] || exit 1
}
trap aufraeumen EXIT

echo "Domänenkonto zuordnen gegen $BASE_URL"
api -X POST "$BASE_URL/api/auth/login" -d "{\"username\":\"$ADMIN\",\"password\":\"$ADMIN_PW\"}" >/dev/null
for name in lena.brandt ruth.mayer "$ALT_KC" "$ALT_LOKAL"; do
  u=$(uid "$name"); [ -n "$u" ] && api -X DELETE "$BASE_URL/api/admin/users/$u" >/dev/null
done

echo
echo "Testverzeichnis"
"$ROOT/scripts/ldap-test-server.sh" stop >/dev/null 2>&1
"$ROOT/scripts/ldap-test-server.sh" start >/dev/null 2>&1 && ok "Testverzeichnis läuft" \
  || { bad "Testverzeichnis kam nicht hoch"; exit 1; }
docker network connect ota_public ota-ldap-test >/dev/null 2>&1 || true
R=$(api -X PUT "$BASE_URL/api/admin/identity/keycloak/verzeichnis" -d '{
  "server_uri":"ldap://ota-ldap-test:389","base_dn":"ou=people,dc=ota,dc=test",
  "bind_dn":"cn=ota-dienst,dc=ota,dc=test","bind_password":"dienst-geheim-2026",
  "kind":"other","login_attribute":"uid","is_enabled":true}')
expect "True" "$(jqp "str(d.get('eingerichtet'))" <<<"$R")" "Verzeichnis angebunden"

# ------------------------------------------------------------------------
echo
echo "Altes Konto in Keycloak (von OTA angelegt) ← lena.brandt"
R=$(api -X POST "$BASE_URL/api/admin/users" -d "{\"username\":\"$ALT_KC\",\"email\":\"$ALT_KC@ota.invalid\",\"password\":\"$PW\",\"passwort_wechseln\":false,\"group_ids\":[]}")
A=$(jqp "d.get('id','')" <<<"$R")
[ -n "$A" ] && ok "$ALT_KC angelegt" || { bad "$ALT_KC: $R"; exit 1; }
anmelden "$ALT_KC" "$PW" && ok "$ALT_KC meldet sich an" || bad "$ALT_KC kommt nicht herein"
SID=$(sitzung_anlegen "$A")
mkdir -p "$PROFILES/$A/user" && echo "von früher" > "$PROFILES/$A/user/merkzettel.txt"
ok "Er hat eine Sitzung und etwas im Zuhause"

anmelden lena.brandt 'Lena-Pruef-2026!' && ok "lena meldet sich über das Verzeichnis an" || bad "lena kommt nicht herein"
B=$(me lena.brandt "d['id']")
[ -n "$B" ] && [ "$B" != "$A" ] && ok "OTA legt ihr dafür ein neues Konto an" || bad "Kein neues Konto für lena"

K=$(api "$BASE_URL/api/admin/users/$A/domaenenkonten?q=lena")
expect "lena.brandt" "$(jqp "d[0]['username']" <<<"$K")" "Die Suche findet das Domänenkonto"
expect "lena.brandt" "$(jqp "d[0]['ota_konto']['username']" <<<"$K")" "… und nennt das Konto aus ihrer ersten Anmeldung"
expect "[]" "$(api "$BASE_URL/api/admin/users/$A/domaenenkonten?q=$ALT_KC" | jqp "d")" \
  "Konten ohne Verzeichnis tauchen nicht auf"
SUB=$(jqp "d[0]['sub']" <<<"$K")

N=$(uid "$ADMIN")
CODE=$(api -o /dev/null -w '%{http_code}' -X POST "$BASE_URL/api/admin/users/$N/domaenenkonto" -d "{\"sub\":\"$SUB\"}")
expect "409" "$CODE" "Das Notfallkonto (und das eigene) lässt sich nicht verknüpfen"

R=$(api -X POST "$BASE_URL/api/admin/users/$A/domaenenkonto" -d "{\"sub\":\"$SUB\"}")
expect "lena.brandt" "$(jqp "d['username']" <<<"$R")" "Zugeordnet — das alte Konto heisst jetzt wie im Verzeichnis"
expect "lena.brandt" "$(jqp "d['entfernt']['username']" <<<"$R")" "… und das Konto aus der ersten Anmeldung ist entfernt"
expect "1" "$(anzahl lena.brandt)" "Es gibt nur noch ein Konto lena.brandt"
expect "$A" "$(uid lena.brandt)" "… und das ist das alte"
expect "0" "$(anzahl "$ALT_KC")" "Den alten Namen gibt es nicht mehr"

anmelden lena.brandt 'Lena-Pruef-2026!' && ok "lena meldet sich wieder über das Verzeichnis an" || bad "lena kommt nicht mehr herein"
expect "$A" "$(me lena.brandt "d['id']")" "Sie landet im alten Konto"
expect "$A" "$(sitzung_von "$SID")" "Die Sitzung des alten Kontos ist ihre"
[ -f "$PROFILES/$A/user/merkzettel.txt" ] && ok "Das Zuhause des alten Kontos ist ihres" || bad "Zuhause fehlt"
anmelden "$ALT_KC" "$PW" && bad "Das alte Keycloak-Konto kommt noch herein" \
  || ok "Das alte Keycloak-Konto ist deaktiviert"
expect "True" "$(api "$BASE_URL/api/admin/users/$A/domaenenkonten?q=lena" | jqp "str(d[0]['ist_ziel'])")" \
  "Die Suche zeigt: schon zugeordnet"
CODE=$(api -o /dev/null -w '%{http_code}' -X POST "$BASE_URL/api/admin/users/$A/domaenenkonto" -d "{\"sub\":\"$SUB\"}")
expect "409" "$CODE" "Ein Domänenkonto wird nicht ein zweites Mal verknüpft"

# ------------------------------------------------------------------------
echo
echo "Lokales Bestandskonto ← ruth.mayer (noch nie über die Domäne angemeldet)"
"$ROOT/scripts/lokales-testkonto.sh" "$ALT_LOKAL" "$PW" "$ALT_LOKAL@ota.invalid" users >/dev/null
L=$(uid "$ALT_LOKAL")
[ -n "$L" ] && ok "$ALT_LOKAL ist lokal" || bad "Lokales Konto fehlt"
api -X POST "$BASE_URL/api/admin/identity/keycloak/verzeichnis/abgleich?voll=true" >/dev/null
SUB=$(sub_von ruth.mayer "$L")
[ -n "$SUB" ] && ok "ruth steht im Verzeichnis, ohne OTA-Konto" || bad "ruth nicht gefunden"
R=$(api -X POST "$BASE_URL/api/admin/users/$L/domaenenkonto" -d "{\"sub\":\"$SUB\"}")
expect "ruth.mayer" "$(jqp "d['username']" <<<"$R")" "Zugeordnet"
expect "None" "$(jqp "d['entfernt']" <<<"$R")" "… ohne ein Konto zu entfernen"
expect "409" "$(lokal_an ruth.mayer "$PW")" "Das lokale Passwort gilt nicht mehr"
anmelden ruth.mayer 'Ruth-Pruef-2026!' && ok "ruth meldet sich über das Verzeichnis an" || bad "ruth kommt nicht herein"
expect "$L" "$(me ruth.mayer "d['id']")" "Sie landet im alten lokalen Konto"
