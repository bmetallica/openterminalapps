#!/usr/bin/env bash
# Erzeugt die Konfiguration des TURN-Servers aus deploy/.env und aus den
# **tatsaechlichen** Subnetzen dieser Anlage.
#
# Warum es dieses Skript gibt: Die Sperrliste stand bis zum 2026-09-10 fest im
# Compose-Bestand, mit geratenen Bereichen. Einer davon lautete
# `192.168.0.0-192.168.15.255` — und der war gleich zweimal falsch:
#
#   * Er sperrte **nichts** von dem, was er sperren sollte. Docker legt die
#     Netze dieses Projekts irgendwo in seinem Vorrat an; auf der
#     Entwicklungsmaschine landete `ota_uplink` auf 192.168.32.0/20, also
#     ausserhalb des Bereichs.
#   * Er brach jede Anlage, deren LAN in 192.168.0.x oder 192.168.1.x liegt —
#     also die haeufigste Adressierung ueberhaupt. coturn antwortete dort auf
#     die Erlaubnis fuer den eigenen Browser mit „403 Forbidden IP", und im
#     Browser stand nichts. Gefunden am 2026-09-10 auf einer frischen Anlage
#     unter 192.168.1.22.
#
# Geraten wird deshalb nichts mehr. Gesperrt werden:
#
#   * die universell unbrauchbaren Bereiche (0.x, Rueckkanal, Link-Local)
#   * die **konkreten** Subnetze von `ota_internal` und `ota_public` — dort
#     stehen Datenbank, Keycloak und der Agent, und dorthin soll niemand ueber
#     den Umweg eines Relays gelangen
#
# **`ota_uplink` steht ausdruecklich nicht darin.** Von dort kommt der
# Arbeitsplatz: Sein Verkehr erreicht den TURN-Dienst hinter der NAT des
# Routers, also unter dessen Uplink-Adresse. Wer dieses Netz sperrt, sperrt
# den Bildstrom aus, den er gerade aufbauen will.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ZIEL="$ROOT/deploy/turn/turnserver.conf"
[ -f "$ROOT/deploy/.env" ] && { set -a; . "$ROOT/deploy/.env"; set +a; }

bereich() {  # bereich <cidr> -> "erste-letzte"
  python3 - "$1" <<'PY'
import ipaddress, sys
try:
    n = ipaddress.ip_network(sys.argv[1], strict=False)
except ValueError:
    sys.exit(0)
if n.version == 4:
    print(f"{n.network_address}-{n.broadcast_address}")
PY
}

# Die Subnetze der eigenen Netze — sofern es sie schon gibt. Beim allerersten
# `make up` existieren sie noch nicht; dann bleibt die Liste kurz, und der
# zweite Durchgang in `make up` traegt sie nach.
GESPERRT=""
for netz in ota_internal ota_public; do
  for cidr in $(docker network inspect "$netz" \
      --format '{{range .IPAM.Config}}{{.Subnet}} {{end}}' 2>/dev/null); do
    B="$(bereich "$cidr")"
    [ -n "$B" ] && GESPERRT="$GESPERRT$B
"
  done
done

mkdir -p "$(dirname "$ZIEL")"
{
  echo "# ERZEUGT von scripts/turn-config.sh — Aenderungen hier gehen beim"
  echo "# naechsten \`make up\` verloren. Bitte das Skript aendern."
  echo
  echo "listening-port=${OTA_TURN_PORT:-3478}"
  # Beide Adressen ausdruecklich und nicht 0.0.0.0: Der Host hat neben dem
  # Firmennetz ein Dutzend Docker-Bruecken, und coturn boete sonst
  # Relay-Kandidaten in Netzen an, die kein Browser erreicht.
  echo "listening-ip=${OTA_TURN_HOST:-127.0.0.1}"
  echo "relay-ip=${OTA_TURN_HOST:-127.0.0.1}"
  echo "min-port=${OTA_TURN_MIN:-49160}"
  echo "max-port=${OTA_TURN_MAX:-49260}"
  echo "realm=openterminalapps"
  # Kurzlebige Anmeldedaten aus einem HMAC statt eines festen Passworts.
  echo "use-auth-secret"
  echo "static-auth-secret=${OTA_TURN_SECRET:-}"
  echo "no-tls"
  echo "no-dtls"
  echo "no-cli"
  echo "no-multicast-peers"
  echo
  echo "# Universell unbrauchbar."
  echo "denied-peer-ip=0.0.0.0-0.255.255.255"
  echo "denied-peer-ip=127.0.0.0-127.255.255.255"
  echo "denied-peer-ip=169.254.0.0-169.254.255.255"
  if [ -n "$GESPERRT" ]; then
    echo
    echo "# Die eigenen Netze dieser Anlage, aus \`docker network inspect\`."
    printf '%s' "$GESPERRT" | while read -r b; do
      [ -n "$b" ] && echo "denied-peer-ip=$b"
    done
  fi
  echo
  echo "${OTA_TURN_LOG:-simple-log}"
  echo "log-file=stdout"
} > "$ZIEL"

# Das Geheimnis steht in dieser Datei — sie bleibt so eng wie moeglich.
#
# **Aber nicht root:root 0600.** Der coturn-Container laeuft als `nobody`
# (65534:65533) und konnte die Datei dann nicht lesen; im Protokoll stand
# „Cannot find config file", und der Dienst startete mit **Vorgabewerten** —
# also ohne Sperrliste und ohne feste Relay-Adresse. Ein Rechtefehler, der wie
# eine fehlende Datei aussieht und in einer offenen Konfiguration endet.
#
# Also: lesbar fuer genau diesen Nutzer, fuer sonst niemanden.
chown 65534:65533 "$ZIEL" 2>/dev/null || true
chmod 600 "$ZIEL"

ANZAHL=$(printf '%s' "$GESPERRT" | grep -c . || true)
if [ "${ANZAHL:-0}" -gt 0 ]; then
  echo "  turnserver.conf erzeugt (${ANZAHL} eigene Netze gesperrt)"
else
  echo "  turnserver.conf erzeugt (eigene Netze noch nicht angelegt)"
fi
