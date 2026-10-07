#!/usr/bin/env bash
# Prüft das Paket ota-selkies und seine drei Wege (Handbuch Kapitel 20):
#
#   1. Es liegt in der eigenen Paketquelle, und die API gibt seine Fassung an
#      den Agent weiter.
#   2. **Ein Arbeitsplatz auf einem alten Golden Image mit Selkies 1.6.2**
#      wird mit genau der Funktion des Agents angehoben (`_selkies_heben`):
#      apt aus der eigenen Paketquelle, das alte Selkies verschwindet.
#   3. **Der Bildbauer hebt ein Golden Image an:** Software zeigt 1.6.2 an,
#      ein Bau mit ota-selkies ergibt ein Image mit der neuen Fassung.
#   4. **Ein Root-Arbeitsplatz hebt sich beim Fortsetzen:** Dafür liegt kurz
#      eine Prüffassung (Revision 9999) in der Paketquelle; danach ist sie weg.
#
# Teil 2 und 3 brauchen ein Golden Image auf dem alten Basisimage
# (OTA_ALT_IMAGE, Vorgabe 127.0.0.1:5000/ota/arbeitsplatz-debian-versuch:v1);
# ohne werden sie übersprungen. Teil 4 braucht Sysbox und das Root-Image.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
[ -f "$ROOT/deploy/.env" ] && { set -a; . "$ROOT/deploy/.env"; set +a; }

pass=0; fail=0
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; pass=$((pass+1)); }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$1"; fail=$((fail+1)); }
info() { printf '    %s\n' "$1"; }

BASE_URL="${OTA_BASE:-https://127.0.0.1:${OTA_HTTPS_PORT:-8443}}"
TMP="$(mktemp -d)"
ADMIN="${OTA_TEST_ADMIN:-notfall}"
ADMIN_PW="${OTA_TEST_ADMIN_PW:?OTA_TEST_ADMIN_PW fehlt. Trag es in deploy/.env ein.}"
ALT="${OTA_ALT_IMAGE:-127.0.0.1:5000/ota/arbeitsplatz-debian-versuch:v1}"
ROOT_IMAGE="${OTA_ROOT_TAG:-ota/base-desktop-root:1}"
UPSTREAM=$(grep -oP '^version = "\K[^"]+' "$ROOT/third_party/selkies/pyproject.toml")
SOLL="${UPSTREAM}-ota$(tr -d ' \n' < "$ROOT/packaging/ota-selkies/revision")"
PRUEF="${UPSTREAM}-ota9999"

api() { curl -sk -b "$TMP/jar" -c "$TMP/jar" "$@"; }
jqp() { python3 -c "import sys,json;d=json.load(sys.stdin);print($1)" 2>/dev/null; }
im()  { docker exec -u 0 "$1" sh -c "$2" 2>&1; }

TID=""; SID=""; RTID=""; RSID=""; PRUEF_DA=""
aufraeumen() {
  [ -n "$SID" ] && api -X DELETE "$BASE_URL/api/sessions/$SID" >/dev/null 2>&1
  [ -n "$RSID" ] && api -X DELETE "$BASE_URL/api/admin/arbeitsplaetze/$RSID" >/dev/null 2>&1
  if [ -n "$TID" ]; then
    # Die aktive Fassung laesst die API nicht loeschen, und das Loeschen der
    # Vorlage nimmt keine Images mit — die Tags der eigenen Bauten deshalb
    # hier, nach der Vorlage, selbst entfernen.
    BILDER=$(api "$BASE_URL/api/templates/$TID/builds" | jqp "' '.join(x['image_ref'] for x in d if x.get('image_ref'))")
    for b in $(api "$BASE_URL/api/templates/$TID/builds" | jqp "' '.join(x['id'] for x in d)"); do
      api -X DELETE "$BASE_URL/api/templates/$TID/builds/$b" >/dev/null 2>&1
    done
    api -X DELETE "$BASE_URL/api/templates/$TID" >/dev/null 2>&1
    for r in $BILDER; do docker rmi "$r" "${r#*/}" >/dev/null 2>&1; done
  fi
  [ -n "$RTID" ] && api -X DELETE "$BASE_URL/api/templates/$RTID" >/dev/null 2>&1
  # Die Prüffassung darf nicht liegen bleiben — sonst höbe jeder Root-
  # Arbeitsplatz beim nächsten Fortsetzen auf sie an.
  if [ -n "$PRUEF_DA" ]; then
    api -X DELETE "$BASE_URL/api/paketquellen/pakete/ota-selkies_${PRUEF}_amd64" >/dev/null 2>&1
    rm -f "$ROOT/dist/pakete/ota-selkies_${PRUEF}_amd64.deb"
  fi
  rm -rf "$TMP"
}
trap aufraeumen EXIT

neu_vorlage() {  # NAME IMAGE KLASSE
  api -H 'Content-Type: application/json' -X POST "$BASE_URL/api/templates" -d "{
    \"friendly_name\": \"$1\", \"image_ref\": \"$2\", \"cores\": 2,
    \"memory_bytes\": 4294967296, \"klasse\": \"$3\", \"platz_grenze_gb\": 20,
    \"stream_engine\": \"selkies\", \"mode\": \"workspace\", \"persistence_scope\": \"template\"}" \
    | jqp "d['id']"
}
starten() { api -H 'Content-Type: application/json' -X POST "$BASE_URL/api/sessions" -d "{\"template_id\":\"$1\"}"; }

echo "Das Paket ota-selkies (Kapitel 20)"

code=$(curl -sk -c "$TMP/jar" -o /dev/null -w '%{http_code}' -X POST "$BASE_URL/api/auth/login" \
  -H 'Content-Type: application/json' -d "{\"username\":\"$ADMIN\",\"password\":\"$ADMIN_PW\"}")
[ "$code" = "200" ] || { bad "Anmeldung als $ADMIN scheiterte ($code)"; exit 1; }

# ------------------------------------------------------------ Paketquelle
echo
echo "In der Paketquelle"
api "$BASE_URL/api/paketquellen/pakete" | grep -q "\"ota-selkies_${SOLL}_amd64\"" \
  && ok "ota-selkies $SOLL liegt in der eigenen Paketquelle" \
  || bad "ota-selkies $SOLL fehlt in der Paketquelle (scripts/build-selkies-deb.sh --hochladen)"
QUELLE=$(docker exec ota-repo sh -c 'curl -s -H "X-Agent-Token: $OTA_AGENT_TOKEN" http://127.0.0.1:8200/quellen' | jqp "d.get('selkies','')")
[ "$QUELLE" = "$SOLL" ] && ok "Die Paketquelle meldet sie als neueste ($QUELLE)" \
  || bad "Die Paketquelle meldet '$QUELLE' statt $SOLL"

# ----------------------------------------------- Altes Golden Image anheben
echo
echo "Arbeitsplatz auf einem Golden Image mit Selkies 1.6.2"
if ! docker image inspect "$ALT" >/dev/null 2>&1; then
  info "$ALT fehlt — Teil 2 und 3 übersprungen"
else
  TID=$(neu_vorlage "Prüfung Selkies-Paket" "$ALT" standard)
  STAND=$(api "$BASE_URL/api/templates/$TID/selkies")
  [ "$(jqp "d['im_image']" <<<"$STAND")" = "1.6.2" ] && [ "$(jqp "d['in_quelle']" <<<"$STAND")" = "$SOLL" ] \
    && ok "Software erkennt Selkies 1.6.2 im Image und bietet $SOLL an" \
    || bad "Fassungsanzeige unerwartet: $STAND"

  START=$(starten "$TID"); SID=$(jqp "d['id']" <<<"$START"); CN="ota-s-${SID:0:12}"
  if [ "$(jqp "d['status']" <<<"$START")" != "running" ]; then
    bad "Start scheiterte: $(jqp "d.get('detail')" <<<"$START")"
  else
    im "$CN" 'test -x /opt/selkies/bin/selkies-gstreamer' >/dev/null \
      && ok "Vorher: Selkies 1.6.2 im Container" || bad "Vorher kein Selkies 1.6.2 — falsches Prüfimage?"
    ERG=$(docker exec ota-agent python -c "
import docker
from otaagent import main
c = docker.from_env().containers.get('$CN')
print(main._selkies_heben(c, {'selkies': '$SOLL', 'modus': 'zuerst'}))" 2>&1 | tail -1)
    [ "$ERG" = "True" ] && ok "Der Agent hebt an (aus der eigenen Paketquelle)" || bad "Agent: $ERG"
    [ "$(im "$CN" "dpkg-query -W -f='\${Version}' ota-selkies")" = "$SOLL" ] \
      && ok "Danach: ota-selkies $SOLL installiert" || bad "ota-selkies nicht installiert"
    [ -z "$(im "$CN" 'ls /opt/selkies/bin/selkies-gstreamer /opt/gst-web 2>/dev/null')" ] \
      && ok "Das alte Selkies ist weg (kein selkies-gstreamer, kein gst-web)" \
      || bad "Reste von 1.6.2 liegen noch da"
    ERG2=$(docker exec ota-agent python -c "
import docker
from otaagent import main
c = docker.from_env().containers.get('$CN')
print(main._selkies_heben(c, {'selkies': '$SOLL', 'modus': 'zuerst'}))" 2>&1 | tail -1)
    [ "$ERG2" = "False" ] && ok "Ein zweites Mal: nichts zu tun, kein Neustart" || bad "Zweites Mal: $ERG2"
    api -X DELETE "$BASE_URL/api/sessions/$SID" >/dev/null; SID=""
  fi

  echo
  echo "Bildbauer: Golden Image anheben"
  BAU=$(api -H 'Content-Type: application/json' -X POST "$BASE_URL/api/templates/$TID/builds" \
    -d "{\"apt_packages\":[\"ota-selkies\"],\"comment\":\"Prüfung: anheben\"}")
  BID=$(jqp "d['id']" <<<"$BAU")
  for _ in $(seq 1 90); do
    ST=$(api "$BASE_URL/api/templates/$TID/builds/$BID" | jqp "d['status']")
    case "$ST" in queued|building) sleep 5 ;; *) break ;; esac
  done
  if [ "$ST" = "ok" ]; then
    ok "Bau mit ota-selkies auf dem alten Golden Image gelungen"
    api -X POST "$BASE_URL/api/templates/$TID/builds/$BID/activate" >/dev/null
    STAND=$(api "$BASE_URL/api/templates/$TID/selkies")
    [ "$(jqp "d['im_image']" <<<"$STAND")" = "$SOLL" ] \
      && ok "Danach meldet Software: $SOLL im Image" || bad "Nach dem Bau: $STAND"
  else
    bad "Bau: $ST — $(api "$BASE_URL/api/templates/$TID/builds/$BID" | jqp "d['log'][-400:]")"
  fi
fi

# ------------------------------------------------- Root: beim Fortsetzen
echo
echo "Root-Arbeitsplatz: anheben beim Fortsetzen"
if ! docker info 2>/dev/null | grep sysbox-runc >/dev/null || ! docker image inspect "$ROOT_IMAGE" >/dev/null 2>&1; then
  info "Sysbox oder $ROOT_IMAGE fehlt — übersprungen"
else
  if "$ROOT/scripts/build-selkies-deb.sh" --revision 9999 --hochladen >"$TMP/bau.log" 2>&1; then
    PRUEF_DA=1
    ok "Prüffassung $PRUEF gebaut und in der Paketquelle"
  else
    bad "Prüffassung liess sich nicht bauen: $(tail -3 "$TMP/bau.log")"
  fi
  if [ -n "$PRUEF_DA" ]; then
    RTID=$(neu_vorlage "Prüfung Selkies-Paket Root" "$ROOT_IMAGE" root)
    START=$(starten "$RTID"); RSID=$(jqp "d['id']" <<<"$START"); RCN="ota-s-${RSID:0:12}"
    VORHER=$(im "$RCN" "dpkg-query -W -f='\${Version}' ota-selkies")
    info "beim Start: $VORHER"
    # Was jemand ausserhalb des Zuhauses angelegt hat, muss das Anheben
    # ueberstehen — genau dafuer gibt es das Paket statt „Neu aufsetzen".
    im "$RCN" 'echo bleibt > /opt/ota-pruefmarke' >/dev/null
    api -X DELETE "$BASE_URL/api/sessions/$RSID" >/dev/null           # anhalten
    START2=$(starten "$RTID")                                           # fortsetzen
    [ "$(jqp "d['status']" <<<"$START2")" = "running" ] && ok "Fortgesetzt" \
      || bad "Fortsetzen: $(jqp "d.get('detail')" <<<"$START2")"
    [ "$(im "$RCN" "dpkg-query -W -f='\${Version}' ota-selkies")" = "$PRUEF" ] \
      && ok "Beim Fortsetzen gehoben: $VORHER → $PRUEF" || bad "Nicht gehoben (noch $(im "$RCN" "dpkg-query -W -f='\${Version}' ota-selkies"))"
    [ "$(im "$RCN" 'curl -s -o /dev/null -w %{http_code} http://127.0.0.1:8080/')" = "401" ] \
      && ok "Nach dem Neustart antwortet Selkies wieder (401 ohne Anmeldung)" \
      || bad "Selkies antwortet nach dem Neustart nicht"
    [ "$(im "$RCN" 'cat /opt/ota-pruefmarke')" = "bleibt" ] \
      && ok "Was im Platz installiert war, ist noch da" || bad "Inhalt des Platzes ist weg"
  fi
fi

echo
printf '  bestanden: %d   fehlgeschlagen: %d\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
