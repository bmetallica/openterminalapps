#!/usr/bin/env bash
# Prüft den Medienweg — vom Arbeitsplatz bis zum Bild im Browser.
#
# **Warum als eigene Reihe.** Die teuersten Fehler dieses Projekts lagen genau
# hier, und keine der anderen Reihen hätte sie gefunden: ein TURN hinter einer
# Docker-Bridge, der die falsche Absenderadresse verschickt; ein DTLS-Paket,
# das an einer kleinen MTU zerschellt; ein Client, der seine Adressen aus der
# falschen Pfadwurzel baut. Alle sahen im Browser gleich aus — eine leere
# Fläche — und in keinem Protokoll stand ein Grund.
#
# **Seit 2026-10-07 läuft Selkies 2.0** und streamt über WebSockets durch
# Traefik. Geprüft wird deshalb:
#
#   1. Die Reihe legt sich eine **eigene Vorlage auf dem aktuellen
#      Basisimage** an (`OTA_DESKTOP_TAG`, Vorgabe `ota/base-desktop:1`) —
#      nicht irgendeine vorhandene, die noch ein altes Golden Image mit
#      Selkies 1.6.2 tragen könnte.
#   2. `pruef-selkies.mjs` fährt einen **echten Browser** durch Anmeldung und
#      Start und zählt die dekodierten Bilder: auf dem Arbeitsplatz und auf
#      dem eigenen Bildschirm einer Anwendung.
#   3. `pruef-tastatur.mjs` tippt deutsch und liest im Container nach.
#   4. **TURN** nur, wenn er eingerichtet ist (`OTA_TURN_HOST`): Ihn brauchen
#      nur noch Golden Images auf dem alten Basisimage mit Selkies 1.6.2.
#
# Der Browser läuft in einem eigenen Container im Standardnetz — von dort ist
# der Session-Container **nicht** direkt erreichbar, genau wie von einem
# Arbeitsplatz im Firmennetz.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CN="ota-stream-pruef-$$"
CDP_PORT=9224     # nicht 9223: Ein von Hand gestarteter Prüfbrowser soll
                  # dieser Reihe nicht in die Quere kommen.
BROWSER_IMAGE="${OTA_TEST_BROWSER_IMAGE:-127.0.0.1:5000/ota/arbeitsplatz:v13}"
SLUG="${OTA_TEST_STREAM_SLUG:-}"

pass=0; fail=0
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; pass=$((pass+1)); }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$1" >&2; fail=$((fail+1)); }
info() { printf '    %s\n' "$1"; }

NAT_REGEL=""
VORLAGE_ID=""; JAR=""
aufraeumen() {
  docker rm -f "$CN" >/dev/null 2>&1
  # Die eigene Prüfvorlage. Ihre Sitzungen haben die Prüfskripte beendet; eine
  # Sitzung, die doch übrig blieb, wird vorher beendet.
  if [ -n "$VORLAGE_ID" ] && [ -n "$JAR" ]; then
    for sid in $(curl -sk -b "$JAR" "$BASE_URL/api/sessions" | python3 -c "import sys,json;[print(s['id']) for s in json.load(sys.stdin) if s['template_id']=='$VORLAGE_ID']" 2>/dev/null); do
      curl -sk -b "$JAR" -X DELETE "$BASE_URL/api/sessions/$sid" >/dev/null 2>&1
    done
    curl -sk -b "$JAR" -X DELETE "$BASE_URL/api/templates/$VORLAGE_ID" >/dev/null 2>&1
    rm -f "$JAR"
  fi
  # shellcheck disable=SC2086
  [ -n "$NAT_REGEL" ] && iptables -t nat -D PREROUTING $NAT_REGEL 2>/dev/null
}
trap aufraeumen EXIT

echo "Medienweg (Selkies, Strom, Tastatur — und TURN, falls eingerichtet)"

set -a; . "$ROOT/deploy/.env" 2>/dev/null; set +a

# ------------------------------------------------------------------ TURN
#
# Nur noch fuer Golden Images auf dem alten Basisimage (Selkies 1.6.2, WebRTC).
TURN_DA=""
[ -n "${OTA_TURN_HOST:-}" ] && TURN_DA=1
if [ -n "$TURN_DA" ]; then
  AUSGABE=$(python3 "$ROOT/scripts/pruef-turn.py" 2>&1)
  if grep -q "TURN vermittelt." <<<"$AUSGABE"; then
    ok "TURN vermittelt (Absender stimmt mit der Relay-Adresse überein)"
  else
    bad "TURN vermittelt nicht"
    sed 's/^/    /' <<<"$AUSGABE" | tail -8 >&2
  fi
else
  info "(TURN übersprungen — nicht eingerichtet; Selkies 2.0 braucht ihn nicht)"
fi

# --------------------------------------------------------------- Der Strom
#
# Ohne Vorlage mit Selkies gibt es nichts zu streamen. Gesucht wird sie hier
# und nicht in der .env: Wie der Arbeitsplatz heisst, weiss nur die Datenbank.
# Eine eigene Vorlage auf dem aktuellen Basisimage, mit einer Anwendung im
# Katalog — sie wird am Ende wieder entfernt. Mit OTA_TEST_STREAM_SLUG laesst
# sich stattdessen eine vorhandene pruefen (dann ohne Anwendungsbildschirm).
APP=""
if [ -z "$SLUG" ]; then
  BILD="${OTA_DESKTOP_TAG:-ota/base-desktop:1}"
  if ! docker image inspect "$BILD" >/dev/null 2>&1; then
    echo "  (Strom übersprungen — $BILD fehlt:  scripts/build-desktop-image.sh --pruefen)"
    exit $([ "$fail" = "0" ] && echo 0 || echo 1)
  fi
  BASE_URL="${OTA_BASE:-https://127.0.0.1:${OTA_HTTPS_PORT:-8443}}"
  JAR="$(mktemp)"
  curl -sk -c "$JAR" -o /dev/null -X POST "$BASE_URL/api/auth/login" -H 'Content-Type: application/json' \
    -d "{\"username\":\"${OTA_TEST_ADMIN:-notfall}\",\"password\":\"${OTA_TEST_ADMIN_PW:-}\"}"
  VORLAGE=$(curl -sk -b "$JAR" -H 'Content-Type: application/json' -X POST "$BASE_URL/api/templates" -d "{
    \"friendly_name\": \"Prüfung Medienweg $$\", \"image_ref\": \"$BILD\", \"cores\": 2,
    \"memory_bytes\": 4294967296, \"stream_engine\": \"selkies\", \"mode\": \"workspace\",
    \"persistence_scope\": \"template\"}")
  VORLAGE_ID=$(python3 -c "import sys,json;print(json.load(sys.stdin)['id'])" <<<"$VORLAGE" 2>/dev/null)
  SLUG=$(python3 -c "import sys,json;print(json.load(sys.stdin)['slug'])" <<<"$VORLAGE" 2>/dev/null)
  if [ -z "$VORLAGE_ID" ]; then
    bad "Prüfvorlage liess sich nicht anlegen: $(head -c 200 <<<"$VORLAGE")"
    exit 1
  fi
  curl -sk -b "$JAR" -X PUT -H 'Content-Type: application/json' "$BASE_URL/api/templates/$VORLAGE_ID/apps" \
    -d '[{"slug":"terminal","name":"Terminal","exec_cmd":"xfce4-terminal"}]' >/dev/null
  APP=terminal
fi
info "Vorlage: $SLUG"

if ! docker image inspect "$BROWSER_IMAGE" >/dev/null 2>&1; then
  echo "  (Strom übersprungen — Prüfbrowser $BROWSER_IMAGE liegt nicht vor)"
  exit $([ "$fail" = "0" ] && echo 0 || echo 1)
fi

# **Hinter einer NAT** (OTA_TURN_BIND gesetzt und verschieden) kennt der
# Browser nur die Adresse der Firewall. Den Weg dorthin baut in Wirklichkeit
# die Firewall; hier spielt eine DNAT-Regel auf diesem Host ihre Rolle — nur
# fuer das Netz des Pruefbrowsers und nur fuer die Dauer dieser Reihe. Damit
# prueft die Reihe den Aufbau aus Kapitel 24 von aussen nach innen: Browser
# ueber die veroeffentlichte Adresse, Selkies im Arbeitsplatz ueber die
# Umleitung im Router.
if [ -n "$TURN_DA" ] && [ -n "${OTA_TURN_BIND:-}" ] && [ "${OTA_TURN_BIND}" != "${OTA_TURN_HOST}" ]; then
  BRUECKE=$(docker network inspect bridge --format '{{range .IPAM.Config}}{{.Subnet}}{{end}}' 2>/dev/null)
  if command -v iptables >/dev/null && [ -n "$BRUECKE" ]; then
    NAT_REGEL="-s $BRUECKE -d $OTA_TURN_HOST -p tcp --dport ${OTA_TURN_PORT:-3478} -j DNAT --to-destination $OTA_TURN_BIND:${OTA_TURN_PORT:-3478}"
    # shellcheck disable=SC2086
    iptables -t nat -I PREROUTING 1 $NAT_REGEL \
      && info "NAT nachgestellt: $OTA_TURN_HOST:${OTA_TURN_PORT:-3478} -> $OTA_TURN_BIND (nur fuer $BRUECKE)" \
      || { NAT_REGEL=""; info "NAT liess sich nicht nachstellen — der Browser erreicht $OTA_TURN_HOST nur, wenn die Firewall es weiterleitet"; }
  fi
fi

# `socat` davor, weil Chrome seine Fernsteuerung nur auf dem Rückkanal
# anbietet und `--remote-debugging-address` in neueren Fassungen nichts mehr
# bewirkt. Ohne diesen Umweg kommt puppeteer nicht an den Browser heran.
docker rm -f "$CN" >/dev/null 2>&1
docker run -d --name "$CN" --network bridge --shm-size=1g \
  -p "127.0.0.1:$CDP_PORT:$CDP_PORT" --entrypoint /bin/bash \
  "$BROWSER_IMAGE" -c "
    socat TCP-LISTEN:$CDP_PORT,fork,reuseaddr TCP:127.0.0.1:9222 &
    exec /opt/google/chrome/chrome --headless=new --no-sandbox \
      --disable-dev-shm-usage --disable-gpu --ignore-certificate-errors \
      --autoplay-policy=no-user-gesture-required --user-data-dir=/tmp/chrome \
      --remote-debugging-port=9222 --window-size=1440,900 about:blank" >/dev/null \
  || { bad "Der Prüfbrowser liess sich nicht starten"; exit 1; }

BEREIT=0
for _ in $(seq 1 30); do
  curl -s -m2 "http://127.0.0.1:$CDP_PORT/json/version" >/dev/null 2>&1 && { BEREIT=1; break; }
  sleep 1
done
[ "$BEREIT" = "1" ] || { bad "Der Prüfbrowser antwortet nicht"; exit 1; }

AUSGABE=$(OTA_CDP="http://127.0.0.1:$CDP_PORT" OTA_SLUG="$SLUG" OTA_APP="$APP" \
  OTA_WARTE="${OTA_WARTE:-20}" node "$ROOT/scripts/pruef-selkies.mjs" 2>&1)
if grep -q "Ein Bild kommt an." <<<"$AUSGABE"; then
  ok "Arbeitsplatz: ein Bild kommt an ($(grep -m1 -oE '\[Arbeitsplatz\] [^:]+: [0-9]+ Bilder dekodiert, Bildgroesse [0-9x]+' <<<"$AUSGABE" | cut -d' ' -f2-))"
  grep -oE 'relay/[^ ]+ -> relay/[^ ]+' <<<"$AUSGABE" | head -1 | while read -r p; do info "$p"; done
else
  bad "Arbeitsplatz: kein Bild"
  sed 's/^/    /' <<<"$AUSGABE" | tail -12 >&2
fi
if [ -n "$APP" ]; then
  grep -q "Die Anwendung bringt ein Bild." <<<"$AUSGABE" \
    && ok "Anwendung auf eigenem Bildschirm: ein Bild kommt an ($(grep -m1 -oE '[0-9]+ Bilder dekodiert' <<<"$(grep 'Anwendung' <<<"$AUSGABE")"))" \
    || bad "Anwendung auf eigenem Bildschirm: kein Bild"
fi

# ------------------------------------------------------------- Die Tastatur
#
# Derselbe Pruefbrowser tippt wie eine deutsche Tastatur. Das gehoert zum
# Medienweg, weil es genau dieselbe Art Fehler ist: Im Browser sieht alles
# richtig aus, im Container kommt etwas anderes an, und nirgends steht warum.
if [ -n "${OTA_KEYBOARD_LAYOUT-de}" ] && [ "${OTA_KEYBOARD_LAYOUT-de}" = "de" ]; then
  TIPP=$(OTA_CDP="http://127.0.0.1:$CDP_PORT" OTA_SLUG="$SLUG" \
    node "$ROOT/scripts/pruef-tastatur.mjs" 2>&1)
  if grep -q "TASTATUR STIMMT" <<<"$TIPP"; then
    ok "Umlaute, Shift und AltGr kommen an (aäöüß/Ä@z-)"
  else
    bad "Die Tastatur kommt falsch an"
    grep -E "layout|erwartet|bekommen" <<<"$TIPP" | sed 's/^/    /' >&2
  fi
else
  info "(Tastatur übersprungen — die Prüfung tippt deutsch, das Layout ist ${OTA_KEYBOARD_LAYOUT:-leer})"
fi

# --------------------------------------------------- Die Sperrliste des TURN
#
# Sie ist der Teil des Medienwegs, der am leisesten kaputtgeht: coturn
# antwortet dann mit „403 Forbidden IP", und im Browser steht nichts. Bis zum
# 2026-09-10 stand dort ein **geratener** Bereich (192.168.0.0-192.168.15.255)
# — der sperrte keines der eigenen Netze und brach jede Anlage, deren LAN in
# 192.168.0.x oder 192.168.1.x liegt.
echo
echo "Sperrliste des TURN-Servers"

CONF="$ROOT/deploy/turn/turnserver.conf"
if [ -z "$TURN_DA" ]; then
  info "(übersprungen — kein TURN eingerichtet)"
elif [ ! -f "$CONF" ]; then
  bad "Es gibt keine erzeugte turnserver.conf — scripts/turn-config.sh nicht gelaufen?"
else
  # 1. Die eigene Adresse darf in keinem gesperrten Bereich liegen. Genau das
  #    war der Fehler, und genau das sieht man der Datei nicht an.
  EIGENE="${OTA_TURN_BIND:-${OTA_TURN_HOST:-}}"
  DRIN=$(python3 - "$CONF" "$EIGENE" <<'PY'
import ipaddress, re, sys
konf, wirt = sys.argv[1], sys.argv[2].strip()
if not wirt:
    print(""); raise SystemExit
try:
    adresse = ipaddress.ip_address(wirt)
except ValueError:
    print(""); raise SystemExit
for zeile in open(konf, encoding="utf-8"):
    treffer = re.match(r"\s*denied-peer-ip=([0-9.]+)-([0-9.]+)", zeile)
    if not treffer:
        continue
    von, bis = (ipaddress.ip_address(x) for x in treffer.groups())
    if von <= adresse <= bis:
        print(f"{von}-{bis}")
        break
PY
)
  [ -z "$DRIN" ] \
    && ok "Die eigene Adresse ${EIGENE:-(keine)} steht in keinem gesperrten Bereich" \
    || bad "Die eigene Adresse ${EIGENE} liegt im gesperrten Bereich $DRIN — coturn lehnt jede Erlaubnis mit 403 ab"

  # 2. Und die eigenen Netze *sind* gesperrt. Ohne diese Zeile waere die erste
  #    Prüfung auch mit einer leeren Liste zufrieden.
  INTERN=$(docker network inspect ota_internal \
    --format '{{range .IPAM.Config}}{{.Subnet}}{{end}}' 2>/dev/null)
  if [ -z "$INTERN" ]; then
    info "ota_internal nicht gefunden — Prüfung übersprungen"
  else
    ERWARTET=$(python3 -c "
import ipaddress,sys
n=ipaddress.ip_network('$INTERN')
print(f'{n.network_address}-{n.broadcast_address}')")
    grep -q "denied-peer-ip=$ERWARTET" "$CONF" \
      && ok "Das interne Netz ($INTERN) ist gesperrt" \
      || bad "Das interne Netz $INTERN steht nicht in der Sperrliste"
  fi

  # 3. Der Uplink dagegen **nicht** — von dort kommt der Arbeitsplatz.
  UPLINK=$(docker network inspect ota_uplink \
    --format '{{range .IPAM.Config}}{{.Subnet}}{{end}}' 2>/dev/null)
  if [ -n "$UPLINK" ]; then
    UP_R=$(python3 -c "
import ipaddress,sys
n=ipaddress.ip_network('$UPLINK')
print(f'{n.network_address}-{n.broadcast_address}')")
    grep -q "denied-peer-ip=$UP_R" "$CONF" \
      && bad "Der Uplink $UPLINK ist gesperrt — damit käme kein Bild aus einem Arbeitsplatz" \
      || ok "Der Uplink ($UPLINK) ist offen — von dort kommt der Arbeitsplatz"
  fi
fi

echo
echo "─────────────────────────────────────"
printf '  bestanden: %s   fehlgeschlagen: %s\n' "$pass" "$fail"
[ "$fail" = "0" ]
