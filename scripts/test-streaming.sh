#!/usr/bin/env bash
# Prüft den Medienweg — TURN und den Strom bis zum Bild.
#
# **Warum als eigene Reihe.** Die teuersten Fehler dieses Projekts lagen genau
# hier, und keine der anderen Reihen hätte sie gefunden: ein TURN hinter einer
# Docker-Bridge, der die falsche Absenderadresse verschickt; ein DTLS-Paket,
# das an einer kleinen MTU zerschellt; ein Client, der seine Adressen aus der
# falschen Pfadwurzel baut. Alle drei sahen im Browser gleich aus — „Waiting
# for stream" — und in keinem Protokoll stand ein Grund.
#
# Zwei Schritte:
#
#   1. `pruef-turn.py` schickt ein Paket durch den TURN und vergleicht den
#      Absender mit der gemeldeten Relay-Adresse.
#   2. `pruef-selkies.mjs` fährt einen **echten Browser** durch Anmeldung und
#      Sitzung und liest aus der WebRTC-Statistik, ob ein Bild ankommt.
#
# Der Browser läuft in einem eigenen Container im Standardnetz — von dort ist
# der Session-Container **nicht** direkt erreichbar, genau wie von einem
# Arbeitsplatz im Firmennetz. Der Medienweg muss also über TURN gehen; ein
# Browser auf dem Server selbst verbände direkt und sähe den Fehler nie.
#
# Ohne konfigurierten TURN wird die Reihe übersprungen statt rot: Eine Anlage
# ohne Selkies braucht ihn nicht.

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

aufraeumen() { docker rm -f "$CN" >/dev/null 2>&1; }
trap aufraeumen EXIT

echo "Medienweg (TURN und Strom)"

set -a; . "$ROOT/deploy/.env" 2>/dev/null; set +a

if [ -z "${OTA_TURN_HOST:-}" ]; then
  echo "  (übersprungen — OTA_TURN_HOST ist nicht gesetzt, also läuft hier kein Selkies)"
  exit 0
fi

# ------------------------------------------------------------------ TURN
AUSGABE=$(python3 "$ROOT/scripts/pruef-turn.py" 2>&1)
if grep -q "TURN vermittelt." <<<"$AUSGABE"; then
  ok "TURN vermittelt (Absender stimmt mit der Relay-Adresse überein)"
else
  bad "TURN vermittelt nicht"
  sed 's/^/    /' <<<"$AUSGABE" | tail -8 >&2
fi

# --------------------------------------------------------------- Der Strom
#
# Ohne Vorlage mit Selkies gibt es nichts zu streamen. Gesucht wird sie hier
# und nicht in der .env: Wie der Arbeitsplatz heisst, weiss nur die Datenbank.
if [ -z "$SLUG" ]; then
  SLUG=$(docker exec ota-db psql -U "${POSTGRES_USER:-ota}" -d "${POSTGRES_DB:-ota}" -tAc \
    "select slug from templates where stream_engine='selkies' and is_enabled and mode='workspace' limit 1;" \
    2>/dev/null | tr -d ' ')
fi
if [ -z "$SLUG" ]; then
  echo "  (Strom übersprungen — keine Vorlage mit Selkies vorhanden)"
  exit $([ "$fail" = "0" ] && echo 0 || echo 1)
fi
info "Vorlage: $SLUG"

if ! docker image inspect "$BROWSER_IMAGE" >/dev/null 2>&1; then
  echo "  (Strom übersprungen — Prüfbrowser $BROWSER_IMAGE liegt nicht vor)"
  exit $([ "$fail" = "0" ] && echo 0 || echo 1)
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

AUSGABE=$(OTA_CDP="http://127.0.0.1:$CDP_PORT" OTA_SLUG="$SLUG" OTA_WARTE=45 \
  node "$ROOT/scripts/pruef-selkies.mjs" 2>&1)
if grep -q "Ein Bild kommt an." <<<"$AUSGABE"; then
  ok "Ein Bild kommt an ($(grep -oE '[0-9]+ Bilder' <<<"$AUSGABE" | head -1))"
  grep -oE 'relay/[^ ]+ -> relay/[^ ]+' <<<"$AUSGABE" | head -1 | while read -r p; do info "$p"; done
else
  bad "Kein Bild"
  sed 's/^/    /' <<<"$AUSGABE" | tail -12 >&2
fi

echo
echo "─────────────────────────────────────"
printf '  bestanden: %s   fehlgeschlagen: %s\n' "$pass" "$fail"
[ "$fail" = "0" ]
