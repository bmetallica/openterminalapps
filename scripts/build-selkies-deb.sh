#!/usr/bin/env bash
# Baut das Paket ota-selkies — Selkies aus OTAs Fork samt Abhängigkeiten und
# OTAs Startskripten — und legt es auf Wunsch in die eigene Paketquelle.
#
# Handbuch Kapitel 20. Das Paket ist der **einzige** Weg, auf dem Selkies in
# ein Image kommt: Das Basisimage installiert es, der Bildbauer hebt alte
# Golden Images damit an, und Root-Arbeitsplätze aktualisieren sich beim
# Fortsetzen daraus.
#
#   scripts/build-selkies-deb.sh                 bauen nach dist/pakete/
#   scripts/build-selkies-deb.sh --hochladen     bauen und in die Paketquelle
#   scripts/build-selkies-deb.sh --hochladen --wenn-noetig
#                                                nur, wenn diese Fassung dort fehlt
#   scripts/build-selkies-deb.sh --revision 3    andere OTA-Revision als in
#                                                packaging/ota-selkies/revision
#
# **Eine Änderung selbst einbauen:** am Fork (third_party/selkies), an den
# Startskripten (images/base-desktop/dockerstartup/desktop_startup.sh,
# selkies-starten.sh) oder an packaging/ota-selkies/ — dann die Zahl in
# packaging/ota-selkies/revision um eins erhöhen und mit --hochladen bauen.
# Dieselbe Fassung zweimal nimmt die Paketquelle nicht an; das ist Absicht,
# sonst hätten zwei Arbeitsplätze unter derselben Fassung verschiedenes.
#
# Gebaut wird im Image des Repo-Dienstes (Debian 13, Python 3.13 — dieselbe
# Fassung wie in den Arbeitsplätzen). Die Abhängigkeiten kommen mit Prüfsumme
# aus dem Datei-Vorrat, sonst von PyPI (third_party/selkies/ota-abhaengigkeiten.txt).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOCHLADEN=""; WENN_NOETIG=""; REVISION=""
while [ $# -gt 0 ]; do
  case "$1" in
    --hochladen) HOCHLADEN=1 ;;
    --wenn-noetig) WENN_NOETIG=1 ;;
    --revision) REVISION="$2"; shift ;;
    -h|--help) sed -n '2,27p' "$0"; exit 0 ;;
    *) echo "Unbekannt: $1" >&2; exit 2 ;;
  esac
  shift
done

# Nur die Zeilen aus der .env, die hier gebraucht werden — nicht die ganze
# Datei (Geheimnisse).
wert() { grep -E "^$1=" "$ROOT/deploy/.env" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '"' ; }
OTA_REPO_ROOT="${OTA_REPO_ROOT:-$(wert OTA_REPO_ROOT)}"
OTA_VERSION="${OTA_VERSION:-$(wert OTA_VERSION)}"
BAUBILD="ota/repo:${OTA_VERSION:-dev}"

UPSTREAM=$(grep -oP '^version = "\K[^"]+' "$ROOT/third_party/selkies/pyproject.toml")
REVISION="${REVISION:-$(tr -d ' \n' < "$ROOT/packaging/ota-selkies/revision")}"
VERSION="${UPSTREAM}-ota${REVISION}"
DATEI="ota-selkies_${VERSION}_amd64.deb"
AUSGABE="$ROOT/dist/pakete"
mkdir -p "$AUSGABE"

echo "ota-selkies $VERSION"

# Liegt diese Fassung schon in der Paketquelle? Dann nichts zu tun.
in_der_quelle() {
  docker exec ota-repo sh -c 'curl -sf -H "X-Agent-Token: $OTA_AGENT_TOKEN" http://127.0.0.1:8200/pakete' 2>/dev/null \
    | grep -q "\"schluessel\":\"ota-selkies_${VERSION}_amd64\""
}
if [ -n "$HOCHLADEN" ] && [ -n "$WENN_NOETIG" ] && in_der_quelle; then
  echo "  liegt schon in der Paketquelle — nichts zu tun"
  exit 0
fi

if [ -f "$AUSGABE/$DATEI" ] && [ -n "$WENN_NOETIG" ]; then
  echo "  schon gebaut: $AUSGABE/$DATEI"
else
  docker image inspect "$BAUBILD" >/dev/null 2>&1 \
    || { echo "  Das Bauimage $BAUBILD fehlt — erst 'make up'." >&2; exit 1; }

  RAEDER="${OTA_REPO_ROOT:-/srv/ota/repo}/aptly/public/dateien/selkies/${UPSTREAM}/raeder"
  VORRAT=()
  if [ -d "$RAEDER" ]; then
    echo "  Abhängigkeiten aus dem Datei-Vorrat ($RAEDER)"
    VORRAT=(-v "$RAEDER:/raeder:ro")
  else
    echo "  Abhängigkeiten von PyPI (geprüft gegen ota-abhaengigkeiten.txt)"
  fi
  PROXY=()
  for n in OTA_HTTP_PROXY:http_proxy OTA_HTTPS_PROXY:https_proxy OTA_NO_PROXY:no_proxy; do
    w="$(wert "${n%%:*}")"
    [ -n "$w" ] && PROXY+=(-e "${n#*:}=$w" -e "$(echo "${n#*:}" | tr a-z A-Z)=$w")
  done

  docker run --rm -u 0 --entrypoint bash "${PROXY[@]}" "${VORRAT[@]}" \
    -e VERSION="$VERSION" \
    -v "$ROOT/third_party/selkies:/quelle:ro" \
    -v "$ROOT/packaging/ota-selkies:/paket:ro" \
    -v "$ROOT/images/base-desktop/dockerstartup:/start:ro" \
    -v "$AUSGABE:/aus" \
    "$BAUBILD" -c '
set -euo pipefail
QUELLE=""
[ -d /raeder ] && QUELLE="--no-index --find-links /raeder"
# Die Umgebung entsteht an ihrem endgültigen Ort, damit die Pfade in den
# Startern und in pyvenv.cfg stimmen, wenn das Paket ausgepackt ist.
python3 -m venv /opt/selkies
/opt/selkies/bin/pip install -q --no-cache-dir $QUELLE --require-hashes --no-deps \
  -r /quelle/ota-abhaengigkeiten.txt
cp -r /quelle /tmp/quelle
/opt/selkies/bin/pip install -q --no-cache-dir --no-index --no-deps --no-build-isolation /tmp/quelle
# pip selbst braucht im Arbeitsplatz niemand; es bliebe nur Angriffsfläche.
/opt/selkies/bin/python -m pip uninstall -y -q pip setuptools wheel 2>/dev/null || true
# Und dann prüfen, dass alles da ist und Selkies selbst ohne pip lädt. Die
# Rust-Erweiterungen laden hier nicht: Ihnen fehlen in diesem Bauimage die
# Grafikbibliotheken (libgbm …), die das Paket als Abhängigkeit mitbringt.
# Geladen werden sie in der Prüfung des Basisimages.
/opt/selkies/bin/python -c "
from importlib.metadata import version
for p in (\"selkies\", \"pixelflux\", \"pcmflux\"): print(p, version(p))
import selkies.settings"

P=/tmp/paket
mkdir -p $P/opt $P/dockerstartup $P/DEBIAN
mv /opt/selkies $P/opt/selkies
install -m 0755 /start/desktop_startup.sh /start/selkies-starten.sh $P/dockerstartup/
install -m 0755 /paket/preinst /paket/postinst /paket/postrm $P/DEBIAN/
GROESSE=$(du -sk --exclude=DEBIAN $P | cut -f1)
sed -e "s/@VERSION@/$VERSION/" -e "s/@GROESSE@/$GROESSE/" /paket/control.in > $P/DEBIAN/control
( cd $P && find . -path ./DEBIAN -prune -o -type f -print0 | sort -z | xargs -0 md5sum | sed "s| \./| |" ) > $P/DEBIAN/md5sums
dpkg-deb --root-owner-group -Zxz --build $P "/aus/ota-selkies_${VERSION}_amd64.deb" >/dev/null
'
  echo "  gebaut: $AUSGABE/$DATEI ($(du -h "$AUSGABE/$DATEI" | cut -f1))"
fi

if [ -n "$HOCHLADEN" ]; then
  docker inspect ota-repo >/dev/null 2>&1 \
    || { echo "  Der Dienst ota-repo läuft nicht — erst 'make up'." >&2; exit 1; }
  docker cp "$AUSGABE/$DATEI" "ota-repo:/tmp/$DATEI"
  ANTWORT=$(docker exec ota-repo sh -c "curl -s -w '\n%{http_code}' -H \"X-Agent-Token: \$OTA_AGENT_TOKEN\" \
    -F datei=@/tmp/$DATEI -F von=build-selkies-deb.sh http://127.0.0.1:8200/pakete; rm -f /tmp/$DATEI")
  CODE=$(tail -1 <<<"$ANTWORT")
  case "$CODE" in
    200) echo "  in der Paketquelle: ota-selkies $VERSION" ;;
    409) echo "  ota-selkies $VERSION liegt schon in der Paketquelle." \
              "Für eine Änderung: packaging/ota-selkies/revision erhöhen." ;;
    *)   echo "  Hochladen gescheitert ($CODE): $(head -1 <<<"$ANTWORT")" >&2; exit 1 ;;
  esac
fi
