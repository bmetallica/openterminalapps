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
if [ ! -f "$CONF" ]; then
  bad "Es gibt keine erzeugte turnserver.conf — scripts/turn-config.sh nicht gelaufen?"
else
  # 1. Die eigene Adresse darf in keinem gesperrten Bereich liegen. Genau das
  #    war der Fehler, und genau das sieht man der Datei nicht an.
  DRIN=$(python3 - "$CONF" "${OTA_TURN_HOST:-}" <<'PY'
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
    && ok "Die eigene Adresse ${OTA_TURN_HOST:-(keine)} steht in keinem gesperrten Bereich" \
    || bad "Die eigene Adresse ${OTA_TURN_HOST} liegt im gesperrten Bereich $DRIN — coturn lehnt jede Erlaubnis mit 403 ab"

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
