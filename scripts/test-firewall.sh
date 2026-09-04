#!/usr/bin/env bash
# Prüft die Netzabsicherung der Arbeitsplätze — **von innen**.
#
# **Warum von innen.** Ein Regelwerk zu lesen beweist nichts. In Fassung 1
# dieses Umbaus standen vier fremde Regeln vor `DOCKER-USER` und liessen alles
# durch; das Regelwerk sah trotzdem vollständig aus. Und `internal`-Netze sind
# erst dann dicht, wenn auch die Brücke des Wirts keine Adresse hat — auch das
# sieht man dem Regelwerk nicht an, sondern nur der Verbindung.
#
# **Nur TCP-Proben, kein `ping`.** Ein Arbeitsplatz läuft mit `cap_drop: ALL`
# und hat kein `NET_RAW`; `ping` scheitert dort **immer**, auch wenn das Ziel
# erreichbar ist. Eine Prüfreihe, die damit misst, meldet „abgeschottet", wo
# nichts abgeschottet ist.
#
# Die Reihe stellt ihren Vorzustand selbst her: eigene Profile, eigene
# Vorlagen, eigene Sitzungen — und räumt sie hinterher weg.
#
# Aufruf:  ./scripts/test-firewall.sh [basis-url]

set -uo pipefail

BASE="${1:-https://192.168.66.224:8443}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CA="$ROOT/deploy/certs/ota-ca.crt"
TMP="$(mktemp -d)"

if [ -f "$ROOT/deploy/.env" ]; then
  while IFS= read -r zeile; do
    case "$zeile" in ''|'#'*) continue;; *=*) ;; *) continue;; esac
    name="${zeile%%=*}"
    [ -n "${!name:-}" ] || export "$name=${zeile#*=}"
  done < "$ROOT/deploy/.env"
fi

ADMIN_USER="${OTA_TEST_ADMIN:-notfall}"
ADMIN_PW="${OTA_TEST_ADMIN_PW:?OTA_TEST_ADMIN_PW fehlt. Trag es in deploy/.env ein.}"
POOL="${OTA_SESSION_POOL:-10.99.0.0/16}"
TURN_HOST="${OTA_TURN_HOST:-}"
NAT_MIN="${OTA_NAT_MIN:-30000}"

pass=0; fail=0
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; pass=$((pass+1)); }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$1" >&2; fail=$((fail+1)); }
info() { printf '    %s\n' "$1"; }

api()  { curl -s --cacert "$CA" -b "$TMP/jar" -c "$TMP/jar" "${@:2}"; }
jqp()  { python3 -c "import sys,json;d=json.load(sys.stdin);print($1)" 2>/dev/null; }

PROFILE=(); VORLAGEN=(); SITZUNGEN=()

aufraeumen() {
  for s in "${SITZUNGEN[@]:-}"; do
    [ -n "$s" ] && api x -X DELETE "$BASE/api/sessions/$s" >/dev/null 2>&1
  done
  sleep 3
  for v in "${VORLAGEN[@]:-}"; do
    [ -n "$v" ] && api x -X DELETE "$BASE/api/templates/$v" >/dev/null 2>&1
  done
  for p in "${PROFILE[@]:-}"; do
    [ -n "$p" ] && api x -X DELETE "$BASE/api/netprofiles/$p" >/dev/null 2>&1
  done
  rm -rf "$TMP"
}
trap aufraeumen EXIT

echo "Netzabsicherung der Arbeitsplätze"
echo

if ! docker ps --format '{{.Names}}' | grep -q '^ota-firewall$'; then
  echo "  (übersprungen — der Router ota-firewall läuft nicht)"
  exit 0
fi

api x -X POST "$BASE/api/auth/login" -H 'Content-Type: application/json' \
    -d "{\"username\":\"$ADMIN_USER\",\"password\":\"$ADMIN_PW\"}" >/dev/null

# Ein Abbild, in dem Selkies steckt — daran haengt, dass die Sitzung hochkommt.
ABBILD=$(docker exec ota-db psql -U "${POSTGRES_USER:-ota}" -d "${POSTGRES_DB:-ota}" -tAc \
  "select image_ref from templates where stream_engine='selkies' and mode='workspace' limit 1;" \
  2>/dev/null | tr -d ' ')
if [ -z "$ABBILD" ]; then
  echo "  (übersprungen — keine Selkies-Vorlage vorhanden)"
  exit 0
fi

# ---------------------------------------------------------------- Vorbereiten
profil() {  # profil <name> <stufe> <regeln-json>
  api x -X POST "$BASE/api/netprofiles" -H 'Content-Type: application/json' \
    -d "{\"name\":\"$1\",\"stufe\":\"$2\",\"regeln\":$3,\"begruendung\":\"Prüfreihe\"}" \
    | jqp "d['id']"
}
vorlage() {  # vorlage <name> <profil-id>
  # `persistence_scope: none` — die Reihe braucht **zwei** Arbeitsplaetze
  # gleichzeitig, und zwei Sitzungen desselben Menschen mit demselben Zuhause
  # laesst OTA zu Recht nicht zu: Sie geraeten sich darin in die Quere. Ohne
  # Zuhause stellt sich die Frage nicht, und es bleibt nichts liegen.
  api x -X POST "$BASE/api/templates" -H 'Content-Type: application/json' \
    -d "{\"friendly_name\":\"$1\",\"image_ref\":\"$ABBILD\",\"cores\":2,\
\"memory_bytes\":2147483648,\"mode\":\"workspace\",\"idle_minutes\":15,\
\"persistence_scope\":\"none\",\"net_profile_id\":\"$2\"}" | jqp "d['id']"
}
sitzung() {  # sitzung <vorlagen-id>
  # Die Antwort geht in eine Datei und nicht in eine Variable: Diese Funktion
  # wird in einer Kommando-Ersetzung aufgerufen, und die laeuft in einer
  # eigenen Shell — eine Zuweisung darin waere draussen nie zu sehen.
  api x -X POST "$BASE/api/sessions" -H 'Content-Type: application/json' \
    -d "{\"template_id\":\"$1\"}" > "$TMP/letzte.json"
  jqp "d['id']" < "$TMP/letzte.json"
}
drin() {  # drin <sitzung> <befehl…> — im Arbeitsplatz ausfuehren
  docker exec "ota-s-${1:0:12}" bash -c "${*:2}" 2>/dev/null
}
offen() {  # offen <sitzung> <ziel> <port>
  drin "$1" "timeout 4 bash -c 'exec 3<>/dev/tcp/$2/$3' 2>/dev/null && echo JA || echo NEIN"
}

echo "Vorbereiten (zwei Arbeitsplätze mit verschiedenen Profilen)"
P_ZU=$(profil "pruef-abgeschottet-$$" abgeschottet \
  '[{"ziel":"example.com","ports":"80,443","protokoll":"tcp","notiz":"Prüfreihe"}]')
P_NETZ=$(profil "pruef-internet-$$" internet '[]')
PROFILE=("$P_ZU" "$P_NETZ")
[ -n "$P_ZU" ] && [ -n "$P_NETZ" ] && ok "Zwei Netzprofile angelegt" || { bad "Profile nicht anlegbar"; exit 1; }

V_ZU=$(vorlage "Prüfung abgeschottet $$" "$P_ZU")
V_NETZ=$(vorlage "Prüfung Internet $$" "$P_NETZ")
VORLAGEN=("$V_ZU" "$V_NETZ")
[ -n "$V_ZU" ] && [ -n "$V_NETZ" ] && ok "Zwei Vorlagen angelegt" || { bad "Vorlagen nicht anlegbar"; exit 1; }

S_ZU=$(sitzung "$V_ZU"); SITZUNGEN=("$S_ZU")
S_NETZ=$(sitzung "$V_NETZ"); SITZUNGEN=("$S_ZU" "$S_NETZ")
[ -n "$S_ZU" ] && [ -n "$S_NETZ" ] && ok "Zwei Arbeitsplätze gestartet" \
  || { bad "Sitzungen nicht startbar: $(head -c 300 "$TMP/letzte.json")"; exit 1; }
sleep 8

A_ZU=$(docker inspect "ota-s-${S_ZU:0:12}" --format '{{range $k,$v := .NetworkSettings.Networks}}{{$v.IPAddress}}{{end}}' 2>/dev/null)
A_NETZ=$(docker inspect "ota-s-${S_NETZ:0:12}" --format '{{range $k,$v := .NetworkSettings.Networks}}{{$v.IPAddress}}{{end}}' 2>/dev/null)
info "abgeschottet: $A_ZU   internet: $A_NETZ"

# ------------------------------------------------------------------ Trennung
echo
echo "Trennung"

[ "$(offen "$S_NETZ" "$A_ZU" 8080)" = "NEIN" ] \
  && ok "Der Nachbararbeitsplatz ist nicht erreichbar" \
  || bad "Ein Arbeitsplatz erreicht den Bildschirm des anderen ($A_ZU:8080)"

# Der Wirt. Erst über seine LAN-Adresse, dann über die Brücke des eigenen
# Netzes — die zweite ist die, die man vergisst.
if [ -n "$TURN_HOST" ]; then
  [ "$(offen "$S_NETZ" "$TURN_HOST" 22)" = "NEIN" ] \
    && ok "SSH des Wirts ist nicht erreichbar" || bad "SSH des Wirts ist offen"
fi
BRUECKE="${A_NETZ%.*}.1"
[ "$(offen "$S_NETZ" "$BRUECKE" 22)" = "NEIN" ] \
  && ok "Die Brücke des eigenen Netzes trägt keine Adresse ($BRUECKE)" \
  || bad "Der Wirt ist über die Brücke $BRUECKE erreichbar"

LAN="${TURN_HOST%.*}.1"
[ "$(offen "$S_NETZ" "$LAN" 80)" = "NEIN" ] \
  && ok "Das Firmennetz ist nicht erreichbar ($LAN)" || bad "Das Firmennetz ist offen"

# ------------------------------------------------------------ Was laufen muss
echo
echo "Was trotzdem laufen muss"

if [ -n "$TURN_HOST" ]; then
  [ "$(offen "$S_NETZ" "$TURN_HOST" 3478)" = "JA" ] \
    && ok "Der TURN-Server ist erreichbar — sonst käme kein Bild an" \
    || bad "TURN ist nicht erreichbar"
  [ "$(offen "$S_NETZ" "$TURN_HOST" "${OTA_HTTPS_PORT:-8443}")" = "JA" ] \
    && ok "OTA selbst ist erreichbar (Zwischenablage-Erweiterung)" \
    || bad "OTA ist aus dem Arbeitsplatz nicht erreichbar"
fi

[ "$(drin "$S_NETZ" 'getent hosts example.com >/dev/null && echo JA || echo NEIN')" = "JA" ] \
  && ok "Namensauflösung funktioniert" || bad "Keine Namensauflösung"

FREMD=$(drin "$S_NETZ" 'timeout 4 python3 -c "
import socket
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.settimeout(3)
try:
    s.sendto(bytes.fromhex(\"abcd01000001000000000000076578616d706c6503636f6d0000010001\"),(\"8.8.8.8\",53))
    s.recvfrom(512); print(\"JA\")
except Exception: print(\"NEIN\")"')
[ "$FREMD" = "NEIN" ] && ok "Ein fremder Resolver antwortet nicht" \
                      || bad "8.8.8.8 ist erreichbar — Namensfreigaben sind damit wirkungslos"

# ------------------------------------------------------------------- Stufen
echo
echo "Die Stufen"

[ "$(offen "$S_NETZ" 1.1.1.1 443)" = "JA" ] \
  && ok "Stufe „internet\": das Internet ist erreichbar" || bad "Stufe „internet\" kommt nicht hinaus"
[ "$(offen "$S_ZU" 1.1.1.1 443)" = "NEIN" ] \
  && ok "Stufe „abgeschottet\": das Internet ist zu" || bad "Stufe „abgeschottet\" kommt hinaus"

# Freigabe nach Namen: Sie fuellt sich beim Beantworten, nicht auf Vorrat.
# `|| true`, **nicht** `|| echo 000`: curl schreibt den Code bei Zeitablauf
# selbst („000"), und ein zweites Echo ergaebe „000000" — ein Vergleich, der
# immer scheitert. Genau darauf ist diese Reihe beim ersten Lauf hereingefallen.
NAME_OK=$(drin "$S_ZU" 'curl -s -m8 -o /dev/null -w "%{http_code}" http://example.com/ || true')
[ "$NAME_OK" = "200" ] \
  && ok "Freigabe nach Namen greift (example.com trotz „abgeschottet\")" \
  || bad "Die Freigabe nach Namen greift nicht (bekam $NAME_OK)"
NAME_ZU=$(drin "$S_ZU" 'curl -s -m8 -o /dev/null -w "%{http_code}" http://debian.org/ || true')
[ "$NAME_ZU" = "000" ] \
  && ok "Ein nicht freigegebener Name bleibt zu" \
  || bad "debian.org war erreichbar, obwohl nicht freigegeben (bekam $NAME_ZU)"

# --------------------------------------------------------------- Portfreigabe
echo
echo "Portfreigabe über den Wirt"

BENUTZER=$(api x "$BASE/api/auth/me" | jqp "d['id']")
F=$(api x -X POST "$BASE/api/firewall/forwards" -H 'Content-Type: application/json' \
   -d "{\"user_id\":\"$BENUTZER\",\"template_id\":\"$V_NETZ\",\"innen\":8080,\
\"protokoll\":\"tcp\",\"notiz\":\"Prüfreihe\",\"tage\":1}")
PORT=$(jqp "d['aussen']" <<<"$F")
if [ -z "$PORT" ]; then
  bad "Portfreigabe nicht anlegbar: $(head -c 160 <<<"$F")"
else
  sleep 4
  CODE=$(curl -s -m8 -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/" || true)
  # Selkies antwortet mit 401 — das ist seine eigene Anmeldung, und genau das
  # beweist, dass der Weg steht.
  [ "$CODE" != "000" ] \
    && ok "Der freigegebene Port antwortet von aussen (HTTP $CODE auf $PORT)" \
    || bad "Der freigegebene Port $PORT antwortet nicht"
  api x -X DELETE "$BASE/api/firewall/forwards/$(jqp "d['id']" <<<"$F")" >/dev/null
  sleep 3
  CODE2=$(curl -s -m5 -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/" || true)
  [ "$CODE2" = "000" ] && ok "Nach dem Entfernen ist der Port wieder zu" \
                       || bad "Der Port antwortet noch (HTTP $CODE2)"
fi

# ------------------------------------------------------- Nach einem Neustart
echo
echo "Nach einem Neustart des Routers"
#
# Der Fall, den man beim Bauen vergisst: Ein neu erzeugter Container bekommt
# nur die Netze aus der Compose-Datei — alle Sitzungsnetze sind weg, und jeder
# Arbeitsplatz hängt in der Luft. Genau das ist beim Bauen passiert.
docker restart ota-firewall >/dev/null 2>&1
sleep 12
docker exec ota-agent curl -s -m 20 -X POST -H "X-Agent-Token: ${OTA_AGENT_TOKEN:-}" \
  http://127.0.0.1:8100/firewall/abgleich >/dev/null 2>&1
sleep 5

[ "$(offen "$S_NETZ" 1.1.1.1 443)" = "JA" ] \
  && ok "Der Arbeitsplatz ist wieder am Netz" \
  || bad "Nach dem Neustart hat der Arbeitsplatz kein Netz mehr"
if [ -n "$TURN_HOST" ]; then
  [ "$(offen "$S_NETZ" "$TURN_HOST" 22)" = "NEIN" ] \
    && ok "Und der Wirt ist weiterhin zu" || bad "Nach dem Neustart ist der Wirt offen"
fi

echo
echo "─────────────────────────────────────"
printf '  bestanden: %s   fehlgeschlagen: %s\n' "$pass" "$fail"
[ "$fail" = "0" ]
