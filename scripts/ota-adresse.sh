#!/usr/bin/env bash
# Die Adresse dieser OTA-Anlage für Prüfreihen und Messskripte — statt einer
# fest eingetragenen Adresse, die nur auf einer bestimmten Maschine stimmt.
#
#   ota-adresse.sh        https://<host>:8443   (OTA_BASE, wenn gesetzt)
#   ota-adresse.sh host   <host>
#   ota-adresse.sh ki     der KI-Server für die Prüfreihen (OTA_TEST_KI_URL)
#
# Gesucht wird in der Umgebung, dann in deploy/.env (OTA_BASE, OTA_TEST_KI_URL,
# OTA_TURN_BIND, OTA_TURN_HOST), zuletzt die erste Adresse von `hostname -I`.
# deploy/.env wird gelesen, nicht ausgeführt.
set -u
ENV_DATEI="$(cd "$(dirname "$0")/.." && pwd)/deploy/.env"

wert() {  # wert NAME — aus der Umgebung, sonst aus deploy/.env
  local v="${!1:-}"
  if [ -z "$v" ] && [ -r "$ENV_DATEI" ]; then
    v=$(grep -E "^$1=" "$ENV_DATEI" | tail -n1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")
  fi
  printf '%s' "$v"
}

host() {
  local h
  h=$(wert OTA_TURN_BIND); [ -n "$h" ] || h=$(wert OTA_TURN_HOST)
  [ -n "$h" ] || h=$(hostname -I 2>/dev/null | awk '{print $1}')
  printf '%s' "${h:-localhost}"
}

case "${1:-basis}" in
  host) host ;;
  ki)
    k=$(wert OTA_TEST_KI_URL)
    [ -n "$k" ] || echo "ota-adresse.sh: OTA_TEST_KI_URL ist nicht gesetzt (Umgebung oder deploy/.env)" >&2
    printf '%s' "$k" ;;
  *)
    b=$(wert OTA_BASE)
    [ -n "$b" ] || b="https://$(host):8443"
    printf '%s' "$b" ;;
esac
