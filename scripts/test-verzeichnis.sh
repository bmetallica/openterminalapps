#!/usr/bin/env bash
# Prüft Gruppen aus dem Verzeichnis und den Zugang zu fremden Anwendungen
# (Handbuch Kapitel 08 und 18, 2026-10-19).
#
#   * Keycloak liest die Gruppen eines OpenLDAP — in beiden verbreiteten
#     Formen (groupOfNames, posixGroup), die Form erkennt OTA selbst.
#   * Eine OTA-Gruppe, gekoppelt an eine Verzeichnisgruppe, bekommt deren
#     Mitglieder: bei der Anmeldung und beim Abgleich. Von Hand Aufgenommene
#     bleiben, auch wenn das Verzeichnis sie nicht nennt.
#   * Eine Verzeichnisgruppe „admins" macht niemanden zum OTA-Admin.
#   * Ein Konto ohne Gruppe sieht auf dem Dashboard einen Hinweis.
#   * Eine Anwendung lässt nur ihre Gruppen herein — per Formular **und** über
#     die SSO-Sitzung aus OTA. Ohne Gruppe niemanden, mit „für alle" jeden.
#   * Wer im Verzeichnis fehlt, wird beim Abgleich deaktiviert, nie gelöscht.
#
# Startet das Testverzeichnis (scripts/ldap-test-server.sh), bindet es an und
# räumt am Ende alles wieder ab. Was vorher da war, ist nachher wieder da.
set -uo pipefail

pass=0; fail=0
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
LDAP_BASE="dc=ota,dc=test"
LDAP_CN="ota-ldap-test"
APP_ZIEL="https://pruef-app.ota.test"
APP_REDIRECT="$APP_ZIEL/oauth/callback"

api()  { curl -s --cacert "$CA" -b "$TMP/admin.jar" -c "$TMP/admin.jar" -H 'Content-Type: application/json' "$@"; }
jqp()  { python3 -c "import sys,json;d=json.load(sys.stdin);print($1)" 2>/dev/null; }
ldap_aendern() {  # ldap_aendern <ldif>
  printf '%b\n' "$1" | docker exec -i "$LDAP_CN" ldapmodify -x -H ldap://localhost \
    -D "cn=admin,$LDAP_BASE" -w pruefadmin-2026 >/dev/null
}
anmelden() {  # anmelden <name> <passwort> -> Keksdose $TMP/<name>.jar, frisch
  rm -f "$TMP/$1.jar"
  local aus
  aus=$(python3 "$ROOT/scripts/kc_anmelden.py" "$BASE_URL" "$1" "$2" "$TMP/$1.jar" 2>&1) \
    || bad "Anmeldung von $1 gescheitert: $aus"
}
me() {  # me <name> <python-ausdruck>
  curl -s --cacert "$CA" -b "$TMP/$1.jar" "$BASE_URL/api/auth/me" | jqp "$2"
}
zur_app() {  # zur_app <name> -> Ergebnis über die SSO-Sitzung aus OTA
  python3 "$ROOT/scripts/kc_app_zugang.py" "$BASE_URL" "$APP_CLIENT" "$APP_REDIRECT" "$TMP/$1.jar"
}
gid() { api "$BASE_URL/api/admin/groups" | jqp "next((g['id'] for g in d if g['name'] == '$1'), '')"; }
uid() { api "$BASE_URL/api/admin/users" | jqp "next((u['id'] for u in d if u['username'] == '$1'), '')"; }

GRUPPE=""; APP_ID=""; APP_CLIENT=""; ORIGINS_VORHER=""; TAKT_VORHER=""
aufraeumen() {
  echo
  echo "Aufräumen"
  [ -n "$APP_ID" ] && api -X DELETE "$BASE_URL/api/webapps/$APP_ID" >/dev/null
  [ -n "$ORIGINS_VORHER" ] && api -X PUT "$BASE_URL/api/admin/settings" \
    -d "{\"app_origins\":$ORIGINS_VORHER}" >/dev/null
  [ -n "$TAKT_VORHER" ] && api -X PUT "$BASE_URL/api/admin/identity/verzeichnis/abgleich" \
    -d "{\"intervall\":$TAKT_VORHER}" >/dev/null
  local g; g=$(gid ki1-pruef); [ -n "$g" ] && api -X DELETE "$BASE_URL/api/admin/groups/$g" >/dev/null
  for name in lena.brandt piet.holm ruth.mayer; do
    local u; u=$(uid "$name")
    [ -n "$u" ] && api -X DELETE "$BASE_URL/api/admin/users/$u" >/dev/null 2>&1
  done
  api -X DELETE "$BASE_URL/api/admin/identity/keycloak/verzeichnis/gruppen" >/dev/null 2>&1
  api -X DELETE "$BASE_URL/api/admin/identity/keycloak/verzeichnis" >/dev/null 2>&1
  local rest; rest=$(api "$BASE_URL/api/admin/identity/keycloak/verzeichnis" | jqp "str(d.get('eingerichtet'))")
  expect "False" "${rest:-?}" "Anbindung wieder entfernt"
  "$ROOT/scripts/ldap-test-server.sh" stop >/dev/null 2>&1
  ok "Testverzeichnis entfernt"
  rm -rf "$TMP"
  echo
  printf '  bestanden: %d   fehlgeschlagen: %d\n' "$pass" "$fail"
  [ "$fail" -eq 0 ] || exit 1
}
trap aufraeumen EXIT

echo "Gruppen aus dem Verzeichnis gegen $BASE_URL"
api -X POST "$BASE_URL/api/auth/login" -d "{\"username\":\"$ADMIN\",\"password\":\"$ADMIN_PW\"}" >/dev/null
ORIGINS_VORHER=$(api "$BASE_URL/api/admin/settings" | python3 -c "import sys,json;print(json.dumps(json.load(sys.stdin)['app_origins']))")
TAKT_VORHER=$(api "$BASE_URL/api/admin/identity/verzeichnis/abgleich" | jqp "d['intervall']")

echo
echo "Testverzeichnis und Anbindung"
"$ROOT/scripts/ldap-test-server.sh" stop >/dev/null 2>&1
"$ROOT/scripts/ldap-test-server.sh" start >/dev/null 2>&1 && ok "Testverzeichnis läuft" \
  || { bad "Testverzeichnis kam nicht hoch"; exit 1; }
docker network connect ota_public "$LDAP_CN" >/dev/null 2>&1 || true
R=$(api -X PUT "$BASE_URL/api/admin/identity/keycloak/verzeichnis" -d '{
  "server_uri":"ldap://ota-ldap-test:389","base_dn":"ou=people,dc=ota,dc=test",
  "bind_dn":"cn=ota-dienst,dc=ota,dc=test","bind_password":"dienst-geheim-2026",
  "kind":"other","login_attribute":"uid","is_enabled":true}')
expect "True" "$(jqp "str(d.get('eingerichtet'))" <<<"$R")" "Verzeichnis in Keycloak angebunden"

echo
echo "Die Form der Gruppen erkennt OTA selbst"
R=$(api -X PUT "$BASE_URL/api/admin/identity/keycloak/verzeichnis/gruppen" \
  -d '{"gruppen_dn":"ou=posix,dc=ota,dc=test","form":"auto"}')
expect "posixGroup" "$(jqp "d.get('form')" <<<"$R")" "memberUid-Gruppen erkannt"
expect "ki-posix" "$(jqp "','.join(d.get('gruppen', []))" <<<"$R")" "… und gefunden"
R=$(api -X PUT "$BASE_URL/api/admin/identity/keycloak/verzeichnis/gruppen" \
  -d '{"gruppen_dn":"ou=groups,dc=ota,dc=test","form":"auto"}')
expect "groupOfNames" "$(jqp "d.get('form')" <<<"$R")" "member-Gruppen (DN) erkannt"
expect "admins,design,entwicklung,hausmeisterei,verwaltung" \
  "$(jqp "','.join(d.get('gruppen', []))" <<<"$R")" "… alle fünf, und die posix-Gruppe ist nicht mehr dabei"
CODE=$(api -o /dev/null -w '%{http_code}' -X PUT "$BASE_URL/api/admin/identity/keycloak/verzeichnis/gruppen" \
  -d '{"gruppen_dn":"ou=groups,dc=ota,dc=test","form":"auto","filter":"cn=ohne-klammern"}')
expect "400" "$CODE" "Ein Filter ohne Klammern wird abgewiesen"

echo
echo "Eine OTA-Gruppe aus einer Verzeichnisgruppe"
R=$(api -X POST "$BASE_URL/api/admin/groups" -d '{"name":"ki1-pruef","permissions":[],"ldap_gruppen":["entwicklung"]}')
GRUPPE=$(jqp "d['id']" <<<"$R")
expect "entwicklung" "$(jqp "','.join(d['ldap_gruppen'])" <<<"$R")" "Gruppe ki1-pruef an entwicklung gekoppelt"
expect "True" "$(jqp "str(d['abgleich']['ok'])" <<<"$R")" "… und gleich abgeglichen"

anmelden lena.brandt 'Lena-Pruef-2026!'
anmelden ruth.mayer 'Ruth-Pruef-2026!'
anmelden piet.holm 'Piet-Pruef-2026!'
expect "True" "$(me lena.brandt "str('ki1-pruef' in d['groups'])")" "lena (entwicklung) ist bei der Anmeldung drin"
expect "True" "$(me ruth.mayer "str('ki1-pruef' in d['groups'])")" "ruth (entwicklung) auch"
expect "False" "$(me piet.holm "str('ki1-pruef' in d['groups'])")" "piet (nicht in entwicklung) nicht"
expect "False" "$(me piet.holm "str(d['is_admin'])")" "Die Verzeichnisgruppe „admins“ macht piet nicht zum Admin"
expect "False" "$(me piet.holm "str('admins' in d['groups'])")" "… und nicht zum Mitglied der OTA-Gruppe admins"
H=$(me piet.holm "d.get('ohne_gruppe_hinweis') or ''")
[ -n "$H" ] && ok "piet hat keine Gruppe und bekommt den Hinweis fürs Dashboard" \
            || bad "Kein Hinweis für ein Konto ohne Gruppe"
expect "" "$(me lena.brandt "d.get('ohne_gruppe_hinweis') or ''")" "lena hat eine Gruppe und keinen Hinweis"

V=$(api "$BASE_URL/api/admin/users" | jqp "next(u for u in d if u['username']=='lena.brandt')")
expect "True" "$(python3 -c "import ast;u=ast.literal_eval('''$V''');print('$GRUPPE' in u['verzeichnis_group_ids'] and '$GRUPPE' not in u['hand_group_ids'])")" \
  "Die Verwaltung sieht: lena ist aus dem Verzeichnis drin, nicht von Hand"

P=$(api "$BASE_URL/api/admin/groups/$GRUPPE/vorschau?ldap=entwicklung,design")
expect "piet.holm" "$(jqp "','.join(d['dazu'])" <<<"$P")" "Vorschau: Mit design käme piet dazu"

echo
echo "Von Hand und aus dem Verzeichnis zugleich"
PIET=$(uid piet.holm)
api -X PUT "$BASE_URL/api/admin/users/$PIET" \
  -d "{\"username\":\"piet.holm\",\"email\":\"piet.holm@ota.test\",\"is_active\":true,\"group_ids\":[\"$GRUPPE\"]}" >/dev/null
anmelden piet.holm 'Piet-Pruef-2026!'
expect "True" "$(me piet.holm "str('ki1-pruef' in d['groups'])")" "piet von Hand aufgenommen — bleibt nach der Anmeldung drin"
LENA=$(uid lena.brandt)
api -X PUT "$BASE_URL/api/admin/users/$LENA" \
  -d "{\"username\":\"lena.brandt\",\"email\":\"lena.brandt@ota.test\",\"is_active\":true,\"group_ids\":[]}" >/dev/null
expect "True" "$(api "$BASE_URL/api/admin/users" | jqp "str('$GRUPPE' in next(u for u in d if u['username']=='lena.brandt')['group_ids'])")" \
  "Ein Speichern ohne die Gruppe nimmt lena nicht heraus, was das Verzeichnis gibt"

echo
echo "Zugang zu einer Anwendung"
api -X PUT "$BASE_URL/api/admin/settings" \
  -d "{\"app_origins\":$(python3 -c "import json;print(json.dumps(json.loads('$ORIGINS_VORHER')+['$APP_ZIEL']))")}" >/dev/null
R=$(api -X POST "$BASE_URL/api/webapps" -d "{\"name\":\"Pruef-App\",\"url\":\"$APP_ZIEL\",
  \"redirect_uri\":\"$APP_REDIRECT\",\"group_ids\":[\"$GRUPPE\"]}")
APP_ID=$(jqp "d.get('id','')" <<<"$R"); APP_CLIENT=$(jqp "d.get('client_id','')" <<<"$R")
[ -n "$APP_ID" ] && ok "Anwendung mit Gruppe ki1-pruef angelegt" || bad "Anwendung nicht angelegt: $R"
expect "ZUGANG" "$(zur_app lena.brandt)" "lena kommt aus ihrer OTA-Sitzung hinein"
rm -f "$TMP/form.jar"
expect "ZUGANG" "$(python3 "$ROOT/scripts/kc_app_zugang.py" "$BASE_URL" "$APP_CLIENT" "$APP_REDIRECT" "$TMP/form.jar" ruth.mayer 'Ruth-Pruef-2026!')" \
  "ruth kommt über das Formular hinein"

echo
echo "Eine Änderung im Verzeichnis"
ldap_aendern "dn: cn=entwicklung,ou=groups,$LDAP_BASE\nchangetype: modify\ndelete: member\nmember: uid=lena.brandt,ou=people,$LDAP_BASE"
R=$(api -X POST "$BASE_URL/api/admin/identity/verzeichnis/abgleich")
expect "True" "$(jqp "str(d['ok'])" <<<"$R")" "Abgleich auf Knopfdruck läuft"
expect "[0, 1]" "$(jqp "str(d['gruppen'].get('ki1-pruef'))" <<<"$R")" "… und meldet: ki1-pruef −1"
expect "False" "$(api "$BASE_URL/api/admin/users" | jqp "str('$GRUPPE' in next(u for u in d if u['username']=='lena.brandt')['group_ids'])")" \
  "lena ist ohne neue Anmeldung aus ki1-pruef heraus"
expect "True" "$(api "$BASE_URL/api/admin/users" | jqp "str('$GRUPPE' in next(u for u in d if u['username']=='piet.holm')['group_ids'])")" \
  "piet (von Hand) bleibt drin"
expect "VERWEIGERT" "$(zur_app lena.brandt)" "lena kommt mit ihrer laufenden SSO-Sitzung nicht mehr in die Anwendung"
rm -f "$TMP/form2.jar"
expect "VERWEIGERT" "$(python3 "$ROOT/scripts/kc_app_zugang.py" "$BASE_URL" "$APP_CLIENT" "$APP_REDIRECT" "$TMP/form2.jar" lena.brandt 'Lena-Pruef-2026!')" \
  "… und über das Formular auch nicht"
L=$(me lena.brandt "str(d.get('username',''))")
expect "lena.brandt" "$L" "In OTA bleibt sie angemeldet"

R=$(api -X PUT "$BASE_URL/api/webapps/$APP_ID" -d "{\"name\":\"Pruef-App\",\"url\":\"$APP_ZIEL\",
  \"redirect_uri\":\"$APP_REDIRECT\",\"group_ids\":[],\"fuer_alle\":false}")
expect "VERWEIGERT" "$(zur_app ruth.mayer)" "Ohne Gruppe lässt die Anwendung niemanden herein"
R=$(api -X PUT "$BASE_URL/api/webapps/$APP_ID" -d "{\"name\":\"Pruef-App\",\"url\":\"$APP_ZIEL\",
  \"redirect_uri\":\"$APP_REDIRECT\",\"group_ids\":[],\"fuer_alle\":true}")
expect "ZUGANG" "$(zur_app lena.brandt)" "Mit „für alle“ kommt jeder Angemeldete hinein"

ZWEI=$(docker exec -w /app -e PYTHONPATH=/app ota-api python -c "
from ota import keycloak as k
api_ = k.ruf
c = k._client('$APP_CLIENT')
print('gebunden' if (c.get('authenticationFlowBindingOverrides') or {}).get('browser') else 'frei')" 2>/dev/null)
expect "frei" "$ZWEI" "„für alle“ braucht keinen eigenen Anmeldefluss"
api -X PUT "$BASE_URL/api/webapps/$APP_ID" -d "{\"name\":\"Pruef-App\",\"url\":\"$APP_ZIEL\",
  \"redirect_uri\":\"$APP_REDIRECT\",\"group_ids\":[\"$GRUPPE\"],\"fuer_alle\":false}" >/dev/null
ZWEI=$(docker exec -w /app -e PYTHONPATH=/app ota-api python -c "
from ota import keycloak as k
c = k._client('$APP_CLIENT')
fid = c['authenticationFlowBindingOverrides']['browser']
alias = k.ruf('GET', f'/authentication/flows/{fid}').json()['alias']
s = k.ruf('GET', f'/authentication/flows/{k._q(alias)}/executions').json()
cfg = [k.ruf('GET', f\"/authentication/config/{x['authenticationConfig']}\").json()['config'].get('condUserRole')
       for x in s if x.get('providerId') == 'conditional-user-role' and x.get('authenticationConfig')]
print('zweiter-faktor' in cfg)" 2>/dev/null)
expect "True" "$ZWEI" "Der Fluss der Anwendung verlangt den zweiten Faktor wie OTA selbst"

echo
echo "Wer im Verzeichnis fehlt"
docker exec "$LDAP_CN" ldapdelete -x -H ldap://localhost -D "cn=admin,$LDAP_BASE" -w pruefadmin-2026 \
  "uid=ruth.mayer,ou=people,$LDAP_BASE" >/dev/null 2>&1
R=$(api -X POST "$BASE_URL/api/admin/identity/verzeichnis/abgleich")
expect "ruth.mayer" "$(jqp "','.join(d['deaktiviert'])" <<<"$R")" "ruth wird beim Abgleich deaktiviert"
expect "False" "$(api "$BASE_URL/api/admin/users" | jqp "str(next(u for u in d if u['username']=='ruth.mayer')['is_active'])")" \
  "… und steht noch da — deaktiviert, nicht gelöscht"

echo
echo "Takt"
expect "15" "$(api -X PUT "$BASE_URL/api/admin/identity/verzeichnis/abgleich" -d '{"intervall":15}' | jqp "d['intervall']")" \
  "Takt auf 15 Minuten"
expect "400" "$(api -o /dev/null -w '%{http_code}' -X PUT "$BASE_URL/api/admin/identity/verzeichnis/abgleich" -d '{"intervall":7}')" \
  "Ein Takt außerhalb der Stufen wird abgewiesen"
expect "True" "$(api "$BASE_URL/api/admin/identity/verzeichnis/abgleich" | jqp "str(d['letzter']['ok'])")" \
  "Der letzte Abgleich steht mit Ergebnis da"
