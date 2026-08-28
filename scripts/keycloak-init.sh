#!/usr/bin/env bash
# Richtet den OTA-Realm im **mitgelieferten** Keycloak ein.
#
# Idempotent: Was schon da ist, bleibt. Das Skript lässt sich nach jedem
# Update gefahrlos erneut aufrufen — genauso wie scripts/setup-env.sh.
#
# Läuft **nicht** gegen ein fremdes Keycloak (OTA_IDP_MODE=vorhanden). Dort ist
# OTA Gast: Realm und Dienstkonto legt die dortige Verwaltung an, und dieses
# Skript hätte weder die Rechte noch das Recht dazu (auth-roadmap.md §5b).
#
#   scripts/keycloak-init.sh          einrichten oder ergänzen
#   scripts/keycloak-init.sh zeigen   nur nachsehen, nichts ändern

set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
[ -f "$ROOT/deploy/.env" ] && { set -a; . "$ROOT/deploy/.env"; set +a; }

MODE="${OTA_IDP_MODE:-mitgeliefert}"
REALM="${OTA_KEYCLOAK_REALM:-ota}"
ADMIN="${KEYCLOAK_ADMIN_USER:-setup}"
ADMIN_PW="${KEYCLOAK_ADMIN_PW:-}"
SECRET="${OTA_KEYCLOAK_SECRET:-}"
# Von aussen über Traefik; im Container-Netz ginge es auch, aber so ist es
# derselbe Weg, den die API später nimmt.
BASE="${OTA_KEYCLOAK_INIT_URL:-http://ota-keycloak:8080/auth}"

ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
info() { printf '  · %s\n' "$1"; }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$1" >&2; }

if [ "$MODE" != "mitgeliefert" ]; then
  echo "OTA_IDP_MODE=$MODE — der Realm gehört jemand anderem, hier wird nichts angelegt."
  exit 0
fi

if [ -z "$ADMIN_PW" ] || [ -z "$SECRET" ]; then
  bad "KEYCLOAK_ADMIN_PW oder OTA_KEYCLOAK_SECRET fehlt. Erst: make setup"
  exit 1
fi

# Alle Aufrufe laufen aus einem Container im selben Netz — der Agent hat
# curl an Bord und liegt ohnehin in `internal`.
kc() {  # kc <methode> <pfad> [daten]
  local method="$1" path="$2" data="${3:-}"
  if [ -n "$data" ]; then
    docker exec -i ota-agent curl -s -o /tmp/kc.out -w '%{http_code}' \
      -X "$method" "$BASE$path" \
      -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
      -d "$data"
  else
    docker exec -i ota-agent curl -s -o /tmp/kc.out -w '%{http_code}' \
      -X "$method" "$BASE$path" -H "Authorization: Bearer $TOKEN"
  fi
}
kc_body() { docker exec -i ota-agent cat /tmp/kc.out; }

jq_py() { python3 -c "import sys,json;d=json.load(sys.stdin);print($1)" 2>/dev/null; }

# ------------------------------------------------------------ anmelden
TOKEN=$(docker exec -i ota-agent curl -s \
  -d "client_id=admin-cli" -d "username=$ADMIN" \
  --data-urlencode "password=$ADMIN_PW" -d "grant_type=password" \
  "$BASE/realms/master/protocol/openid-connect/token" \
  | jq_py "d.get('access_token','')")

if [ -z "$TOKEN" ]; then
  bad "Anmeldung am Keycloak fehlgeschlagen. Läuft er? docker logs ota-keycloak"
  exit 1
fi
ok "Am Keycloak angemeldet"

if [ "${1:-}" = "zeigen" ]; then
  kc GET "/admin/realms/$REALM" >/dev/null
  echo "Realm $REALM:"; kc_body | python3 -m json.tool 2>/dev/null | head -12
  kc GET "/admin/realms/$REALM/clients" >/dev/null
  echo "Clients:"; kc_body | jq_py "[c['clientId'] for c in d]"
  exit 0
fi

# -------------------------------------------------------------- Realm
CODE=$(kc GET "/admin/realms/$REALM")
if [ "$CODE" = "200" ]; then
  info "Realm $REALM gibt es schon"
else
  CODE=$(kc POST "/admin/realms" "$(cat <<JSON
{"realm":"$REALM","enabled":true,"displayName":"OpenTerminalApps",
 "loginTheme":"keycloak","sslRequired":"external",
 "registrationAllowed":false,"resetPasswordAllowed":false,
 "bruteForceProtected":true,"permanentLockout":false,
 "maxFailureWaitSeconds":900,"failureFactor":5,
 "loginWithEmailAllowed":true,"duplicateEmailsAllowed":false}
JSON
)")
  [ "$CODE" = "201" ] && ok "Realm $REALM angelegt" || { bad "Realm anlegen: HTTP $CODE $(kc_body)"; exit 1; }
fi

# ------------------------------------------------- Gruppen in den Token
#
# Ohne diesen Bereich stünde im Token keine Gruppenzugehörigkeit — und
# genau daran hängt später der Zugriff auf Anwendungen.
CODE=$(kc GET "/admin/realms/$REALM/client-scopes")
if kc_body | jq_py "[s['name'] for s in d]" | grep -q "ota-groups"; then
  info "Bereich ota-groups gibt es schon"
else
  CODE=$(kc POST "/admin/realms/$REALM/client-scopes" "$(cat <<'JSON'
{"name":"ota-groups","protocol":"openid-connect",
 "attributes":{"include.in.token.scope":"true","display.on.consent.screen":"false"},
 "protocolMappers":[{
   "name":"groups","protocol":"openid-connect",
   "protocolMapper":"oidc-group-membership-mapper",
   "config":{"claim.name":"groups","full.path":"false",
             "id.token.claim":"true","access.token.claim":"true",
             "userinfo.token.claim":"true"}}]}
JSON
)")
  [ "$CODE" = "201" ] && ok "Bereich ota-groups angelegt (Gruppen im Token)" \
                      || bad "Bereich anlegen: HTTP $CODE $(kc_body)"
fi

# ------------------------------------------------------------ Clients
#
#   ota-manager  Dienstkonto. Damit verwaltet OTA den Realm.
#   ota          Die Anmeldung von OTA selbst (ab Etappe B).
#   ota-tests    Nur für die Prüfreihen: Benutzername und Passwort direkt
#                gegen ein Token, ohne Browser (auth-roadmap.md §5e).
# Anlegen **oder ergänzen**. Das Ergänzen ist der Teil, der später zählt:
# Kommt eine Einstellung dazu — etwa die Rückkanal-Abmeldung —, soll ein
# erneuter Lauf sie nachtragen, statt achselzuckend „gibt es schon" zu sagen.
# Zusammengeführt wird feldweise; was in Keycloak steht und uns nicht
# interessiert, bleibt unangetastet.
client_anlegen() {  # client_anlegen <clientId> <json>
  local id="$1" body="$2"
  kc GET "/admin/realms/$REALM/clients?clientId=$id" >/dev/null
  local vorhanden; vorhanden=$(kc_body)

  if [ "$(echo "$vorhanden" | jq_py "len(d)")" = "0" ]; then
    local code; code=$(kc POST "/admin/realms/$REALM/clients" "$body")
    [ "$code" = "201" ] && ok "Client $id angelegt" || bad "Client $id: HTTP $code $(kc_body)"
    return 0
  fi

  local kid; kid=$(echo "$vorhanden" | jq_py "d[0]['id']")
  local zusammen
  zusammen=$(echo "$vorhanden" | NEU="$body" python3 -c "
import json, os, sys
alt = json.load(sys.stdin)[0]
neu = json.loads(os.environ['NEU'])
# Verschachteltes wird verschmolzen, nicht ersetzt: Attribute, die jemand von
# Hand gesetzt hat, sollen einen Lauf dieses Skripts ueberleben.
for k, v in neu.items():
    if isinstance(v, dict) and isinstance(alt.get(k), dict):
        alt[k] = {**alt[k], **v}
    else:
        alt[k] = v
print(json.dumps(alt))")

  local code; code=$(kc PUT "/admin/realms/$REALM/clients/$kid" "$zusammen")
  case "$code" in
    204) ok "Client $id auf Stand gebracht" ;;
    *)   bad "Client $id ergänzen: HTTP $code $(kc_body)" ;;
  esac
}

client_anlegen ota-manager "$(cat <<JSON
{"clientId":"ota-manager","name":"OTA — Verwaltung","enabled":true,
 "publicClient":false,"secret":"$SECRET",
 "serviceAccountsEnabled":true,"standardFlowEnabled":false,
 "directAccessGrantsEnabled":false,"protocol":"openid-connect"}
JSON
)"

client_anlegen ota "$(cat <<JSON
{"clientId":"ota","name":"OpenTerminalApps","enabled":true,
 "publicClient":false,"secret":"$SECRET-app",
 "standardFlowEnabled":true,"directAccessGrantsEnabled":false,
 "serviceAccountsEnabled":false,"protocol":"openid-connect",
 "redirectUris":["/*"],"webOrigins":["+"],
 "defaultClientScopes":["profile","email","roles","ota-groups"],
 "attributes":{
   "backchannel.logout.url":"http://api:8000/api/auth/oidc/backchannel",
   "backchannel.logout.session.required":"false",
   "backchannel.logout.revoke.offline.tokens":"false"}}
JSON
)"

client_anlegen ota-tests "$(cat <<JSON
{"clientId":"ota-tests","name":"OTA — Prüfreihen","enabled":true,
 "publicClient":false,"secret":"$SECRET-tests",
 "standardFlowEnabled":false,"directAccessGrantsEnabled":true,
 "serviceAccountsEnabled":false,"protocol":"openid-connect",
 "defaultClientScopes":["profile","email","roles","ota-groups"]}
JSON
)"

# ------------------------------------------- Rechte des Dienstkontos
#
# Bewusst benannt und nicht "realm-admin": Was OTA nicht braucht, bekommt es
# nicht. `manage-realm` ist die einzige breite Berechtigung, und sie ist
# unvermeidlich — die LDAP-Anbindung liegt unter `components` und hängt genau
# daran (auth-roadmap.md §5.5). Sie gilt nur für diesen Realm; `master` bleibt
# ausserhalb.
RECHTE="manage-users view-users query-users query-groups \
        manage-clients view-clients query-clients \
        view-realm manage-realm view-events"

kc GET "/admin/realms/$REALM/clients?clientId=ota-manager" >/dev/null
MGR_ID=$(kc_body | jq_py "d[0]['id']")
kc GET "/admin/realms/$REALM/clients?clientId=realm-management" >/dev/null
RM_ID=$(kc_body | jq_py "d[0]['id']")
kc GET "/admin/realms/$REALM/clients/$MGR_ID/service-account-user" >/dev/null
SA_ID=$(kc_body | jq_py "d['id']")

if [ -z "$MGR_ID" ] || [ -z "$RM_ID" ] || [ -z "$SA_ID" ]; then
  bad "Dienstkonto nicht gefunden — Rechte nicht gesetzt"
  exit 1
fi

kc GET "/admin/realms/$REALM/clients/$RM_ID/roles" >/dev/null
ROLLEN=$(kc_body | RECHTE="$RECHTE" python3 -c "
import json, os, sys
gesucht = set(os.environ['RECHTE'].split())
alle = json.load(sys.stdin)
print(json.dumps([{'id': r['id'], 'name': r['name']}
                  for r in alle if r['name'] in gesucht]))")

CODE=$(kc POST "/admin/realms/$REALM/users/$SA_ID/role-mappings/clients/$RM_ID" "$ROLLEN")
case "$CODE" in
  204|409) ok "Dienstkonto hat seine Rechte ($(echo "$ROLLEN" | jq_py "len(d)") Rollen)" ;;
  *)       bad "Rechte setzen: HTTP $CODE $(kc_body)" ;;
esac

# --------------------------------------------- Zweite Stufe je Gruppe
#
# In OTA war das ein Feld an der Gruppe (`require_totp`). In Keycloak ist es
# ein Anmeldefluss mit einer Bedingung — und Gruppen taugen dort nicht als
# Bedingung, Rollen schon. Also: eine Realm-Rolle `zweiter-faktor`, und wer
# sie trägt, muss beim Anmelden einen zweiten Faktor vorzeigen. OTA hängt sie
# später an die Gruppen, die sie verlangen (auth-roadmap.md §5.3).
#
# Der Fluss ist eine **Kopie** des eingebauten und nicht der eingebaute
# selbst. Das ist kein Ordnungssinn: Keycloak lässt eingebaute Flüsse nicht
# ändern, und ein eigener lässt sich im Zweifel mit einem Handgriff wieder
# abhängen — `browserFlow` zurück auf `browser`, und alles ist wie vorher.

rolle_anlegen() {
  kc GET "/admin/realms/$REALM/roles/zweiter-faktor" >/dev/null
  if [ "$?" = "0" ] && [ "$(kc GET "/admin/realms/$REALM/roles/zweiter-faktor")" = "200" ]; then
    info "Rolle zweiter-faktor gibt es schon"
    return 0
  fi
  local code; code=$(kc POST "/admin/realms/$REALM/roles" \
    '{"name":"zweiter-faktor","description":"Verlangt beim Anmelden einen zweiten Faktor"}')
  case "$code" in
    201|409) ok "Rolle zweiter-faktor steht bereit" ;;
    *)       bad "Rolle anlegen: HTTP $code $(kc_body)" ;;
  esac
}

fluss_einrichten() {
  kc GET "/admin/realms/$REALM/authentication/flows" >/dev/null
  if kc_body | jq_py "[f['alias'] for f in d]" | grep -q "ota-browser"; then
    info "Anmeldefluss ota-browser gibt es schon"
  else
    local code; code=$(kc POST "/admin/realms/$REALM/authentication/flows/browser/copy" \
      '{"newName":"ota-browser"}')
    [ "$code" = "201" ] && ok "Anmeldefluss ota-browser angelegt" \
                        || { bad "Fluss kopieren: HTTP $code $(kc_body)"; return 1; }
  fi

  kc GET "/admin/realms/$REALM/authentication/flows/ota-browser/executions" >/dev/null
  local schritte; schritte=$(kc_body)

  # Die Rollenbedingung, falls sie noch fehlt.
  if ! echo "$schritte" | jq_py "[e.get('providerId') for e in d]" | grep -q "conditional-user-role"; then
    local zweig; zweig=$(python3 -c "
import urllib.parse; print(urllib.parse.quote('ota-browser Browser - Conditional 2FA'))")
    kc POST "/admin/realms/$REALM/authentication/flows/$zweig/executions/execution" \
      '{"provider":"conditional-user-role"}' >/dev/null
    kc GET "/admin/realms/$REALM/authentication/flows/ota-browser/executions" >/dev/null
    schritte=$(kc_body)
    ok "Rollenbedingung in den 2FA-Zweig gesetzt"
  fi

  # Und jetzt die Anforderungen. Die Bedingung „user configured" muss **aus**
  # sein: Sie liesse den zweiten Faktor nur für die gelten, die ihn schon
  # haben — und damit könnte ihn jeder umgehen, indem er ihn nicht einrichtet.
  local id
  for eintrag in \
    "conditional-user-role:REQUIRED" \
    "conditional-user-configured:DISABLED" \
    "conditional-credential:DISABLED" \
    "auth-otp-form:REQUIRED"
  do
    local provider="${eintrag%%:*}" wunsch="${eintrag##*:}"
    id=$(echo "$schritte" | PROVIDER="$provider" python3 -c "
import json, os, sys
p = os.environ['PROVIDER']
# Nur im 2FA-Zweig: 'user configured' steht auch im Organisations-Zweig, und
# den fassen wir nicht an.
treffer = [e['id'] for e in json.load(sys.stdin)
           if e.get('providerId') == p and e['level'] >= 2 and e['index'] < 90]
print(treffer[-1] if treffer else '')")
    [ -z "$id" ] && continue
    kc PUT "/admin/realms/$REALM/authentication/flows/ota-browser/executions" \
      "{\"id\":\"$id\",\"requirement\":\"$wunsch\"}" >/dev/null
  done

  # Die Bedingung braucht ihren Wert — sonst steht sie da und prüft nichts.
  #
  # Frisch gelesen und nicht aus `$schritte`: Die Kennungen der Schritte
  # ändern sich, sobald an den Anforderungen geschraubt wurde, und mit einer
  # veralteten Kennung geht die Konfiguration ins Leere. Gemessen am
  # 2026-08-28: Der Zweig stand richtig, die Bedingung war leer, und damit
  # hätte die zweite Stufe für **niemanden** gegriffen.
  kc GET "/admin/realms/$REALM/authentication/flows/ota-browser/executions" >/dev/null
  id=$(kc_body | jq_py "
next((e['id'] for e in d if e.get('providerId') == 'conditional-user-role'), '')")

  if [ -z "$id" ]; then
    bad "Die Rollenbedingung ist nicht auffindbar"
    return 1
  fi

  kc GET "/admin/realms/$REALM/authentication/executions/$id" >/dev/null
  if kc_body | grep -q "authenticationConfig"; then
    info "Rollenbedingung ist bereits eingestellt"
  else
    local code; code=$(kc POST "/admin/realms/$REALM/authentication/executions/$id/config" \
      '{"alias":"ota-zweiter-faktor","config":{"condUserRole":"zweiter-faktor","negate":"false"}}')
    case "$code" in
      201) ok "Rollenbedingung eingestellt (zweiter-faktor)" ;;
      *)   bad "Rollenbedingung einstellen: HTTP $code $(kc_body)"; return 1 ;;
    esac
  fi

  # Zuletzt binden. Erst hier wird es scharf.
  kc GET "/admin/realms/$REALM" >/dev/null
  if [ "$(kc_body | jq_py "d.get('browserFlow','')")" = "ota-browser" ]; then
    info "Anmeldefluss ist gebunden"
  else
    local code; code=$(kc PUT "/admin/realms/$REALM" \
      "{\"realm\":\"$REALM\",\"browserFlow\":\"ota-browser\"}")
    [ "$code" = "204" ] && ok "Anmeldefluss gebunden — die zweite Stufe greift" \
                        || bad "Fluss binden: HTTP $code $(kc_body)"
  fi
}

rolle_anlegen
fluss_einrichten

echo
echo "Bereit. Realm: $REALM"
echo "  Verwaltung : $BASE/admin/$REALM/console/"
echo "  Erstkonto  : $ADMIN  (nur zum Einrichten — OTA benutzt ota-manager)"
