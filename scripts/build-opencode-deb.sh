#!/usr/bin/env bash
# Baut das Paket ota-opencode — opencode samt dem Plugin ota-sitzung — und
# legt es auf Wunsch in die eigene Paketquelle.
#
# Handbuch Kapitel 38. Aus der Paketquelle holt der Agent es in jeden
# Arbeitsplatz, für den opencode eingeschaltet ist, und hebt es bei jedem
# Start und Fortsetzen auf die neueste Fassung.
#
#   scripts/build-opencode-deb.sh                 bauen nach dist/pakete/
#   scripts/build-opencode-deb.sh --hochladen     bauen und in die Paketquelle
#   scripts/build-opencode-deb.sh --hochladen --wenn-noetig
#                                                 nur, was dort noch fehlt
#
# Was hineinkommt, steht mit Prüfsumme in packaging/ota-opencode/quellen.
# Eine Änderung an packaging/ota-opencode/ ohne neue Fassung von opencode:
# die Zahl in packaging/ota-opencode/revision erhöhen.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOCHLADEN=""; WENN_NOETIG=""
while [ $# -gt 0 ]; do
  case "$1" in
    --hochladen) HOCHLADEN=1 ;;
    --wenn-noetig) WENN_NOETIG=1 ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
    *) echo "Unbekannt: $1" >&2; exit 2 ;;
  esac
  shift
done

wert() { grep -E "^$1=" "$ROOT/deploy/.env" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '"' ; }
OTA_VERSION="${OTA_VERSION:-$(wert OTA_VERSION)}"
BAUBILD="ota/repo:${OTA_VERSION:-dev}"
PAKET="$ROOT/packaging/ota-opencode"
# shellcheck source=/dev/null
. "$PAKET/quellen"
REVISION="$(tr -d ' \n' < "$PAKET/revision")"
VERSION="${OPENCODE_FASSUNG}-ota${REVISION}"
NAME=ota-opencode
DATEI="${NAME}_${VERSION}_amd64.deb"
AUSGABE="$ROOT/dist/pakete"
VORRAT="$ROOT/dist/opencode-quellen"
mkdir -p "$AUSGABE" "$VORRAT"

in_der_quelle() {
  docker exec ota-repo sh -c 'curl -sf -H "X-Agent-Token: $OTA_AGENT_TOKEN" http://127.0.0.1:8200/pakete' 2>/dev/null \
    | grep -q "\"schluessel\":\"$1\""
}

PROXY=()
for n in OTA_HTTP_PROXY:http_proxy OTA_HTTPS_PROXY:https_proxy OTA_NO_PROXY:no_proxy; do
  w="$(wert "${n%%:*}")"
  [ -n "$w" ] && PROXY+=(-e "${n#*:}=$w" -e "$(echo "${n#*:}" | tr a-z A-Z)=$w")
done

echo "$NAME $VERSION"
if [ -n "$HOCHLADEN" ] && [ -n "$WENN_NOETIG" ] && in_der_quelle "${NAME}_${VERSION}_amd64"; then
  echo "  liegt schon in der Paketquelle — nichts zu tun"
  exit 0
fi
if [ -f "$AUSGABE/$DATEI" ] && [ -n "$WENN_NOETIG" ]; then
  echo "  schon gebaut: $AUSGABE/$DATEI"
else
  docker image inspect "$BAUBILD" >/dev/null 2>&1 \
    || { echo "  Das Bauimage $BAUBILD fehlt — erst 'make up'." >&2; exit 1; }
  docker run --rm -u 0 --entrypoint bash "${PROXY[@]}" \
    -e VERSION="$VERSION" -e URL="$OPENCODE_URL" -e SUMME="$OPENCODE_SHA256" \
    -v "$PAKET:/paket:ro" -v "$VORRAT:/vorrat" -v "$AUSGABE:/aus" \
    "$BAUBILD" -c '
set -euo pipefail
QUELLE="/vorrat/opencode-${VERSION%%-ota*}-linux-x64.tar.gz"
if ! echo "$SUMME  $QUELLE" | sha256sum -c --status 2>/dev/null; then
  echo "  hole ${URL##*/}"
  curl -fsSL --retry 3 -o "$QUELLE.neu" "$URL"
  echo "$SUMME  $QUELLE.neu" | sha256sum -c --status \
    || { echo "  Prüfsumme stimmt nicht: $URL" >&2; rm -f "$QUELLE.neu"; exit 1; }
  mv "$QUELLE.neu" "$QUELLE"
fi
P=/tmp/paket
mkdir -p $P/DEBIAN $P/usr/bin $P/usr/share/ota-opencode/plugins $P/usr/share/doc/ota-opencode
tar -xzf "$QUELLE" -C $P/usr/bin opencode
chmod 0755 $P/usr/bin/opencode
cp -r /paket/plugins/. $P/usr/share/ota-opencode/plugins/
find $P/usr/share/ota-opencode -type d -exec chmod 0755 {} +
find $P/usr/share/ota-opencode -type f -exec chmod 0644 {} +
install -m 0644 /paket/copyright $P/usr/share/doc/ota-opencode/copyright
GROESSE=$(du -sk --exclude=DEBIAN $P | cut -f1)
sed -e "s/@VERSION@/$VERSION/" -e "s/@GROESSE@/$GROESSE/" /paket/control.in > $P/DEBIAN/control
( cd $P && find . -path ./DEBIAN -prune -o -type f -print0 | sort -z | xargs -0 md5sum | sed "s| \./| |" ) > $P/DEBIAN/md5sums
dpkg-deb --root-owner-group -Zxz --build $P "/aus/ota-opencode_${VERSION}_amd64.deb" >/dev/null
'
  echo "  gebaut: $AUSGABE/$DATEI ($(du -h "$AUSGABE/$DATEI" | cut -f1))"
fi
if [ -n "$HOCHLADEN" ]; then
  docker inspect ota-repo >/dev/null 2>&1 \
    || { echo "  Der Dienst ota-repo läuft nicht — erst 'make up'." >&2; exit 1; }
  docker cp "$AUSGABE/$DATEI" "ota-repo:/tmp/$DATEI"
  ANTWORT=$(docker exec ota-repo sh -c "curl -s -w '\n%{http_code}' -H \"X-Agent-Token: \$OTA_AGENT_TOKEN\" \
    -F datei=@/tmp/$DATEI -F von=build-opencode-deb.sh http://127.0.0.1:8200/pakete; rm -f /tmp/$DATEI")
  CODE=$(tail -1 <<<"$ANTWORT")
  case "$CODE" in
    200) echo "  in der Paketquelle: $NAME $VERSION" ;;
    409) echo "  $NAME $VERSION liegt schon in der Paketquelle." \
              "Für eine Änderung: packaging/ota-opencode/revision erhöhen." ;;
    *)   echo "  Hochladen gescheitert ($CODE): $(head -1 <<<"$ANTWORT")" >&2; exit 1 ;;
  esac
fi
