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
# Mindestens zwölf Zeichen — dieselbe Untergrenze, die OTAs eigene Anmeldung
# seit jeher verlangt (`api/ota/security.py`). Zwei Wege zu derselben Anlage
# sollen nicht verschieden streng sein.
PASSWORTREGEL="${OTA_KC_PASSWORTREGEL:-length(12) and notUsername(undefined) and notEmail(undefined)}"

CODE=$(kc GET "/admin/realms/$REALM")
if [ "$CODE" = "200" ]; then
  info "Realm $REALM gibt es schon"
else
  CODE=$(kc POST "/admin/realms" "$(cat <<JSON
{"realm":"$REALM","enabled":true,"displayName":"OpenTerminalApps",
 "loginTheme":"ota","sslRequired":"external",
 "registrationAllowed":false,"resetPasswordAllowed":false,
 "bruteForceProtected":true,"permanentLockout":false,
 "maxFailureWaitSeconds":900,"failureFactor":5,
 "passwordPolicy":"$PASSWORTREGEL",
 "loginWithEmailAllowed":true,"duplicateEmailsAllowed":false}
JSON
)")
  [ "$CODE" = "201" ] && ok "Realm $REALM angelegt" || { bad "Realm anlegen: HTTP $CODE $(kc_body)"; exit 1; }
fi

# ------------------------------------------------------- Die Passwortregel
#
# Auch für einen Realm, den es schon gibt: Sie fehlte bis zum 2026-09-04, und
# damit war der **Hauptweg** schwächer als der Notzugang — OTAs eigene
# Anmeldung verlangt seit jeher zwölf Zeichen, Keycloak nahm jede Länge
# (`security.md`, M3).
#
# `notUsername` und `notEmail` kosten nichts und schliessen die beiden
# Passwörter aus, die Menschen zuerst einfallen.
kc GET "/admin/realms/$REALM" >/dev/null
IST=$(kc_body | jq_py "d.get('passwordPolicy') or ''")
if [ "$IST" = "$PASSWORTREGEL" ]; then
  info "Passwortregel steht: $PASSWORTREGEL"
else
  CODE=$(kc PUT "/admin/realms/$REALM" "{\"passwordPolicy\":\"$PASSWORTREGEL\"}")
  case "$CODE" in
    20*) ok "Passwortregel gesetzt: $PASSWORTREGEL" ;;
    *)   bad "Passwortregel nicht setzbar: HTTP $CODE $(kc_body)" ;;
  esac
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

# ------------------------------------------------ Passkeys als zweite Stufe
#
# **Warum zwei Unterfluesse und nicht einfach zwei Alternativen.** Der
# naheliegende Weg waere, `auth-otp-form` und `webauthn-authenticator`
# nebeneinander auf ALTERNATIVE zu stellen: „Code oder Passkey, such dir was
# aus." Gemessen am 2026-09-02 gegen dieses Keycloak: Wer die Rolle traegt und
# **noch keins von beiden** eingerichtet hat, kommt dann gar nicht mehr
# herein — die Anmeldung endet mit „Invalid username or password". Also nicht
# nur eine Sperre, sondern eine mit einer irrefuehrenden Meldung. Auch eine
# vorgemerkte Ersteinrichtung (`CONFIGURE_TOTP`) hilft nicht: Vorgemerkte
# Aktionen laufen **nach** der Anmeldung, und so weit kommt es gar nicht.
#
# Deshalb zwei Zweige, beide ALTERNATIVE:
#
#   Bedingung: Rolle „zweiter-faktor"          REQUIRED
#   ├─ ota-passkey                             ALTERNATIVE
#   │    ├─ Bedingung: beim Nutzer eingerichtet  REQUIRED
#   │    └─ WebAuthn                             REQUIRED
#   └─ ota-einmalkennwort                      ALTERNATIVE
#        └─ Einmalkennwort                       REQUIRED
#
# Wer einen Passkey hinterlegt hat, nimmt den ersten Zweig. Wer keinen hat,
# faellt durch — die Bedingung ist dann falsch — und landet im zweiten, wo
# das Einmalkennwort notfalls seine eigene Einrichtung anstoesst. Damit gibt
# es keinen Zustand, in dem niemand mehr hereinkommt.
#
# Einen Passkey hinterlegt man in Keycloaks Kontoverwaltung; die noetige
# Aktion `webauthn-register` ist im Realm ab Werk eingeschaltet.
passkey_einrichten() {
  local zweig; zweig=$(python3 -c "
import urllib.parse; print(urllib.parse.quote('ota-browser Browser - Conditional 2FA'))")

  kc GET "/admin/realms/$REALM/authentication/flows/ota-browser/executions" >/dev/null
  local vorhanden; vorhanden=$(kc_body)

  if ! echo "$vorhanden" | grep -q "ota-passkey"; then
    kc POST "/admin/realms/$REALM/authentication/flows/$zweig/executions/flow" \
      '{"alias":"ota-passkey","type":"basic-flow","description":"Passkey, wenn einer hinterlegt ist"}' \
      >/dev/null
    kc POST "/admin/realms/$REALM/authentication/flows/ota-passkey/executions/execution" \
      '{"provider":"conditional-user-configured"}' >/dev/null
    kc POST "/admin/realms/$REALM/authentication/flows/ota-passkey/executions/execution" \
      '{"provider":"webauthn-authenticator"}' >/dev/null
    ok "Zweig ota-passkey angelegt"
  else
    info "Zweig ota-passkey gibt es schon"
  fi

  kc GET "/admin/realms/$REALM/authentication/flows/ota-browser/executions" >/dev/null
  if ! kc_body | grep -q "ota-einmalkennwort"; then
    kc POST "/admin/realms/$REALM/authentication/flows/$zweig/executions/flow" \
      '{"alias":"ota-einmalkennwort","type":"basic-flow","description":"Einmalkennwort, wenn kein Passkey da ist"}' \
      >/dev/null
    kc POST "/admin/realms/$REALM/authentication/flows/ota-einmalkennwort/executions/execution" \
      '{"provider":"auth-otp-form"}' >/dev/null
    ok "Zweig ota-einmalkennwort angelegt"
  else
    info "Zweig ota-einmalkennwort gibt es schon"
  fi

  # Die Anforderungen. Gewaehlt wird ueber **Ebene und Kennung** — dieselbe
  # Kennung steht seit den Unterfluessen mehrfach im Baum, und mit der
  # falschen ginge die Einstellung ins Leere.
  local eintrag ebene kennung wunsch id
  for eintrag in \
    "2:ota-passkey:ALTERNATIVE" \
    "2:ota-einmalkennwort:ALTERNATIVE" \
    "2:webauthn-authenticator:DISABLED" \
    "3:conditional-user-configured:REQUIRED" \
    "3:webauthn-authenticator:REQUIRED" \
    "3:auth-otp-form:REQUIRED"
  do
    ebene="${eintrag%%:*}"
    kennung="${eintrag#*:}"; kennung="${kennung%%:*}"
    wunsch="${eintrag##*:}"
    kc GET "/admin/realms/$REALM/authentication/flows/ota-browser/executions" >/dev/null
    id=$(kc_body | LVL="$ebene" KEY="$kennung" python3 -c "
import json, os, sys
lvl = int(os.environ['LVL']); key = os.environ['KEY']
t = [e['id'] for e in json.load(sys.stdin)
     if e['level'] == lvl and (e.get('providerId') == key or e.get('displayName') == key)]
print(t[0] if t else '')")
    if [ -z "$id" ]; then
      bad "Schritt $kennung auf Ebene $ebene nicht gefunden"
      return 1
    fi
    kc PUT "/admin/realms/$REALM/authentication/flows/ota-browser/executions" \
      "{\"id\":\"$id\",\"requirement\":\"$wunsch\"}" >/dev/null
  done
  ok "Passkey- und Einmalkennwort-Zweig stehen nebeneinander"

  # Der Name, den der Browser beim Anlegen eines Passkeys anzeigt. Ab Werk
  # steht dort „keycloak", und das sagt niemandem etwas.
  kc GET "/admin/realms/$REALM" >/dev/null
  if [ "$(kc_body | jq_py "d.get('webAuthnPolicyRpEntityName','')")" = "OpenTerminalApps" ]; then
    info "Der Passkey-Name steht bereits auf OpenTerminalApps"
  else
    # `webAuthnPolicyRpId` bleibt leer: Dann leitet Keycloak sie aus dem
    # aufgerufenen Namen ab, und OTA ist bewusst ueber IP **und** Domain
    # erreichbar. Ein fest eingetragener Wert wuerde den jeweils anderen Weg
    # unbrauchbar machen.
    local code; code=$(kc PUT "/admin/realms/$REALM" \
      "{\"realm\":\"$REALM\",\"webAuthnPolicyRpEntityName\":\"OpenTerminalApps\"}")
    [ "$code" = "204" ] && ok "Passkeys melden sich als OpenTerminalApps" \
                        || bad "Passkey-Name setzen: HTTP $code $(kc_body)"
  fi
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
  #
  # `auth-otp-form` steht hier bewusst **nicht** mehr: Seit es Passkeys gibt,
  # liegt es in einem eigenen Unterfluss (siehe `passkey_einrichten`). Auf
  # dieser Ebene wird es abgeschaltet, sonst liefe es zusaetzlich.
  local id
  for eintrag in \
    "conditional-user-role:REQUIRED" \
    "conditional-user-configured:DISABLED" \
    "conditional-credential:DISABLED" \
    "auth-otp-form:DISABLED"
  do
    local provider="${eintrag%%:*}" wunsch="${eintrag##*:}"
    id=$(echo "$schritte" | PROVIDER="$provider" python3 -c "
import json, os, sys
p = os.environ['PROVIDER']
# Genau Ebene 2: 'user configured' steht auch im Organisations-Zweig (Ebene 2,
# anderer Ast) und seit den Passkeys noch einmal auf Ebene 3 im Unterfluss.
# Der Organisations-Ast kommt vor dem Formular-Ast, deshalb der letzte Treffer.
treffer = [e['id'] for e in json.load(sys.stdin)
           if e.get('providerId') == p and e['level'] == 2]
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

  # `authenticatorConfig` mit **t**, nicht `authenticationConfig`. Die
  # Liste der Schritte nennt das Feld anders als der einzelne Schritt, und
  # der falsche Name traf nie zu: Bei jedem Lauf entstand eine neue
  # Konfiguration, die alte blieb verwaist liegen. Gefunden am 2026-09-02.
  kc GET "/admin/realms/$REALM/authentication/executions/$id" >/dev/null
  if kc_body | grep -q "authenticatorConfig"; then
    info "Rollenbedingung ist bereits eingestellt"
  else
    local code; code=$(kc POST "/admin/realms/$REALM/authentication/executions/$id/config" \
      '{"alias":"ota-zweiter-faktor","config":{"condUserRole":"zweiter-faktor","negate":"false"}}')
    case "$code" in
      201) ok "Rollenbedingung eingestellt (zweiter-faktor)" ;;
      *)   bad "Rollenbedingung einstellen: HTTP $code $(kc_body)"; return 1 ;;
    esac
  fi

  passkey_einrichten || return 1

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

# ---------------------------------------------- Das Gewand der Anmeldung
#
# Auch bei einem Realm, den es schon gibt: Sonst saehe nur eine frisch
# aufgesetzte Anlage richtig aus, und jede bestehende bliebe bei Keycloaks
# Blau — mitten im Anmeldeweg von OTA.
thema_setzen() {
  kc GET "/admin/realms/$REALM" >/dev/null
  local jetzt; jetzt=$(kc_body | jq_py "d.get('loginTheme','')")
  if [ "$jetzt" = "ota" ]; then
    info "Anmeldemaske traegt schon das OTA-Gewand"
    return 0
  fi
  local code; code=$(kc PUT "/admin/realms/$REALM" \
    "{\"realm\":\"$REALM\",\"loginTheme\":\"ota\"}")
  case "$code" in
    204) ok "Anmeldemaske auf das OTA-Gewand gestellt" ;;
    *)   bad "Gewand setzen: HTTP $code $(kc_body)" ;;
  esac
}

# ------------------------------------------ Was ein Konto haben muss
#
# Keycloak verlangt ab Werk eine E-Mail-Adresse von jedem Konto. OTA verlangt
# sie nicht — und wo OTA sie nicht kennt, kann sie auch niemand mitgeben.
#
# Die Folge ohne diese Anpassung ist unangenehm und faellt erst spaet auf: Ein
# uebernommenes Konto ohne E-Mail aendert brav sein Passwort und landet dann
# in einer zweiten Maske, die eine Adresse verlangt. Wer keine hat oder keine
# angeben will, kommt nicht weiter. Gemessen am 2026-08-28.
profil_lockern() {
  kc GET "/admin/realms/$REALM/users/profile" >/dev/null
  local profil; profil=$(kc_body)

  if ! grep -q '"name": *"email"' <<<"$profil" && ! grep -q '"name":"email"' <<<"$profil"; then
    info "Das Kontenprofil sieht anders aus als erwartet — unveraendert gelassen"
    return 0
  fi

  local neu
  neu=$(python3 -c "
import json, sys
d = json.load(sys.stdin)
geaendert = False
for a in d.get('attributes', []):
    if a.get('name') == 'email' and a.get('required'):
        a.pop('required', None)
        geaendert = True
print(json.dumps(d) if geaendert else '')" <<<"$profil")

  if [ -z "$neu" ]; then
    info "E-Mail ist bereits keine Pflicht"
    return 0
  fi

  local code; code=$(kc PUT "/admin/realms/$REALM/users/profile" "$neu")
  case "$code" in
    200|204) ok "E-Mail ist keine Pflicht mehr — wie in OTA" ;;
    *)       bad "Kontenprofil aendern: HTTP $code $(kc_body)" ;;
  esac
}

rolle_anlegen
fluss_einrichten
profil_lockern
thema_setzen

echo
echo "Bereit. Realm: $REALM"
echo "  Verwaltung : $BASE/admin/$REALM/console/"
echo "  Erstkonto  : $ADMIN  (nur zum Einrichten — OTA benutzt ota-manager)"
