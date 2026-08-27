#!/usr/bin/env bash
# Erzeugt eine lokale CA und ein davon signiertes Serverzertifikat für OTA.
#
# Warum eine CA statt eines nackten selbstsignierten Zertifikats?
# Das Root-Zertifikat wird einmal importiert. Danach kann das Serverzertifikat
# beliebig oft getauscht werden, ohne dass jemand etwas neu vertrauen muss.
#
# Später durch ein echtes Zertifikat ersetzen: einfach ota.crt/ota.key
# überschreiben und Traefik neu laden. Die CA wird dann nicht mehr gebraucht.

set -euo pipefail

CERT_DIR="${CERT_DIR:-$(cd "$(dirname "$0")/.." && pwd)/deploy/certs}"
DAYS_CA="${DAYS_CA:-3650}"
DAYS_LEAF="${DAYS_LEAF:-825}"   # über 825 Tage lehnen Apple-Plattformen ab

mkdir -p "$CERT_DIR"
cd "$CERT_DIR"

# Alle Namen und Adressen, unter denen OTA erreichbar sein soll.
# SAN ist Pflicht — moderne Browser ignorieren den Common Name vollständig.
HOSTNAME_SHORT="$(hostname -s)"
EXTRA_DNS="${OTA_DNS:-}"
EXTRA_IP="${OTA_IP:-}"

SAN="DNS:localhost,DNS:${HOSTNAME_SHORT},DNS:${HOSTNAME_SHORT}.local,IP:127.0.0.1"
for ip in $(hostname -I 2>/dev/null); do
  case "$ip" in
    172.1[6-9].*|172.2[0-9].*|172.3[01].*) continue ;;   # Docker-Bridges auslassen
    *:*) continue ;;                                      # IPv6 auslassen
  esac
  SAN="${SAN},IP:${ip}"
done
[ -n "$EXTRA_DNS" ] && SAN="${SAN},DNS:${EXTRA_DNS}"
[ -n "$EXTRA_IP" ]  && SAN="${SAN},IP:${EXTRA_IP}"

echo "SAN: $SAN"

# ---- CA nur anlegen, wenn sie noch nicht existiert ----
if [ ! -f ota-ca.key ]; then
  echo "==> Lege lokale CA an"
  openssl genrsa -out ota-ca.key 4096 2>/dev/null
  openssl req -x509 -new -nodes -key ota-ca.key -sha256 -days "$DAYS_CA" \
    -out ota-ca.crt \
    -subj "/O=OpenTerminalApps/CN=OpenTerminalApps Lokale CA" \
    -addext "basicConstraints=critical,CA:TRUE,pathlen:0" \
    -addext "keyUsage=critical,keyCertSign,cRLSign"
else
  echo "==> CA vorhanden, wird wiederverwendet"
fi

# ---- Serverzertifikat immer neu ausstellen ----
echo "==> Stelle Serverzertifikat aus"
openssl genrsa -out ota.key 2048 2>/dev/null
openssl req -new -key ota.key -out ota.csr \
  -subj "/O=OpenTerminalApps/CN=${HOSTNAME_SHORT}"

cat > ota.ext <<EXT
basicConstraints=CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=${SAN}
EXT

openssl x509 -req -in ota.csr -CA ota-ca.crt -CAkey ota-ca.key -CAcreateserial \
  -out ota.crt -days "$DAYS_LEAF" -sha256 -extfile ota.ext 2>/dev/null

rm -f ota.csr ota.ext ota-ca.srl
chmod 600 ota.key ota-ca.key
chmod 644 ota.crt ota-ca.crt

echo
echo "==> Fertig in $CERT_DIR"
openssl x509 -in ota.crt -noout -subject -dates -ext subjectAltName
echo
echo "Damit der Browser keine Warnung zeigt, einmalig ota-ca.crt importieren:"
echo "  Linux : sudo cp $CERT_DIR/ota-ca.crt /usr/local/share/ca-certificates/ota-ca.crt && sudo update-ca-certificates"
echo "  Firefox: Einstellungen > Datenschutz > Zertifikate anzeigen > Import (Haken 'Websites')"
echo "  Chrome : Einstellungen > Datenschutz > Zertifikate > Autoritaeten > Importieren"
