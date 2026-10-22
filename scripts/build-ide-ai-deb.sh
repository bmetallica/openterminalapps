#!/usr/bin/env bash
# Baut die Pakete von IDE-AI — Continue für VS Code/VSCodium und für
# JetBrains-IDEs — und legt sie auf Wunsch in die eigene Paketquelle.
#
# Handbuch Kapitel 28. Aus der Paketquelle holt der Agent sie in jeden
# Arbeitsplatz, in dem es einen passenden Editor gibt, und hebt sie bei jedem
# Start und Fortsetzen auf die neueste Fassung.
#
#   scripts/build-ide-ai-deb.sh                 bauen nach dist/pakete/
#   scripts/build-ide-ai-deb.sh --hochladen     bauen und in die Paketquelle
#   scripts/build-ide-ai-deb.sh --hochladen --wenn-noetig
#                                               nur, was dort noch fehlt
#
# Was hineinkommt, steht mit Prüfsumme in packaging/ota-ide-ai/quellen. Eine
# Änderung an packaging/ota-ide-ai/ ohne neue Fassung von Continue: die Zahl
# in packaging/ota-ide-ai/revision erhöhen.
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
PAKET="$ROOT/packaging/ota-ide-ai"
# shellcheck source=/dev/null
. "$PAKET/quellen"
REVISION="$(tr -d ' \n' < "$PAKET/revision")"
AUSGABE="$ROOT/dist/pakete"
VORRAT="$ROOT/dist/ide-ai-quellen"
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

# bauen <art> <fassung> <url> <sha256>
bauen() {
  local art="$1" fassung="$2" url="$3" summe="$4"
  local version="${fassung}-ota${REVISION}" name="ota-ide-ai-$1"
  local datei="${name}_${version}_amd64.deb"
  echo "$name $version"
  if [ -n "$HOCHLADEN" ] && [ -n "$WENN_NOETIG" ] && in_der_quelle "${name}_${version}_amd64"; then
    echo "  liegt schon in der Paketquelle — nichts zu tun"
    return
  fi
  if [ -f "$AUSGABE/$datei" ] && [ -n "$WENN_NOETIG" ]; then
    echo "  schon gebaut: $AUSGABE/$datei"
  else
    docker image inspect "$BAUBILD" >/dev/null 2>&1 \
      || { echo "  Das Bauimage $BAUBILD fehlt — erst 'make up'." >&2; exit 1; }
    docker run --rm -u 0 --entrypoint bash "${PROXY[@]}" \
      -e ART="$art" -e VERSION="$version" -e URL="$url" -e SUMME="$summe" \
      -v "$PAKET:/paket:ro" -v "$VORRAT:/vorrat" -v "$AUSGABE:/aus" \
      "$BAUBILD" -c '
set -euo pipefail
QUELLE="/vorrat/${URL##*/}"
if ! echo "$SUMME  $QUELLE" | sha256sum -c --status 2>/dev/null; then
  echo "  hole ${URL##*/}"
  curl -fsSL --retry 3 -o "$QUELLE.neu" "$URL"
  echo "$SUMME  $QUELLE.neu" | sha256sum -c --status \
    || { echo "  Prüfsumme stimmt nicht: $URL" >&2; rm -f "$QUELLE.neu"; exit 1; }
  mv "$QUELLE.neu" "$QUELLE"
fi
P=/tmp/paket
mkdir -p $P/DEBIAN $P/usr/lib/ota-ide-ai $P/usr/share/ota-ide-ai/$ART $P/usr/share/doc/ota-ide-ai-$ART
# Auspacken mit den Rechten aus dem Archiv: zipfile allein liesse die
# mitgelieferten Programme (rg, continue-binary) ohne Ausfuehrungsrecht.
python3 - "$QUELLE" "$ART" "$P/usr/share/ota-ide-ai/$ART" <<"PY"
import os, sys, zipfile
quelle, art, ziel = sys.argv[1:]
with zipfile.ZipFile(quelle) as z:
    for i in z.infolist():
        n = i.filename
        if art == "vscode":
            # Eine VSIX: die Erweiterung liegt unter extension/.
            if not n.startswith("extension/"):
                continue
            n = "continue/" + n[len("extension/"):]
        else:
            # Nur Linux x64 — die anderen Plattformen sind gut die Hälfte.
            teile = n.split("/")
            if len(teile) > 2 and teile[1] == "core" and teile[2] != "linux-x64":
                continue
        pfad = os.path.join(ziel, n)
        if n.endswith("/"):
            os.makedirs(pfad, exist_ok=True)
            continue
        os.makedirs(os.path.dirname(pfad), exist_ok=True)
        with z.open(i) as q, open(pfad, "wb") as a:
            a.write(q.read())
        modus = (i.external_attr >> 16) & 0o777
        os.chmod(pfad, 0o755 if modus & 0o111 else 0o644)
PY
find $P/usr/share/ota-ide-ai -type d -exec chmod 0755 {} +
if [ "$ART" = jetbrains ]; then
  # Im Archiv fehlt das Ausfuehrungsrecht; Continue setzt es sonst selbst
  # beim ersten Start — in einem Verzeichnis, das root gehoert, ginge das nicht.
  chmod 0755 $P/usr/share/ota-ide-ai/jetbrains/continue-intellij-extension/core/linux-x64/continue-binary \
             $P/usr/share/ota-ide-ai/jetbrains/continue-intellij-extension/core/linux-x64/rg
fi
install -m 0644 /paket/copyright $P/usr/share/doc/ota-ide-ai-$ART/copyright
# Mit VS Code und VSCodium verknuepft das Paket selbst; ein JetBrains-Plugin
# verknuepft der Agent im Zuhause (siehe packaging/ota-ide-ai/verknuepfen).
if [ "$ART" = vscode ]; then
  install -m 0755 /paket/verknuepfen $P/usr/lib/ota-ide-ai/verknuepfen-vscode
  install -m 0755 /paket/postinst $P/DEBIAN/postinst
else
  rmdir $P/usr/lib/ota-ide-ai $P/usr/lib
fi
install -m 0755 /paket/postrm $P/DEBIAN/postrm
GROESSE=$(du -sk --exclude=DEBIAN $P | cut -f1)
sed -e "s/@VERSION@/$VERSION/" -e "s/@GROESSE@/$GROESSE/" /paket/control-$ART.in > $P/DEBIAN/control
( cd $P && find . -path ./DEBIAN -prune -o -type f -print0 | sort -z | xargs -0 md5sum | sed "s| \./| |" ) > $P/DEBIAN/md5sums
dpkg-deb --root-owner-group -Zxz --build $P "/aus/ota-ide-ai-${ART}_${VERSION}_amd64.deb" >/dev/null
'
    echo "  gebaut: $AUSGABE/$datei ($(du -h "$AUSGABE/$datei" | cut -f1))"
  fi
  if [ -n "$HOCHLADEN" ]; then
    docker inspect ota-repo >/dev/null 2>&1 \
      || { echo "  Der Dienst ota-repo läuft nicht — erst 'make up'." >&2; exit 1; }
    docker cp "$AUSGABE/$datei" "ota-repo:/tmp/$datei"
    ANTWORT=$(docker exec ota-repo sh -c "curl -s -w '\n%{http_code}' -H \"X-Agent-Token: \$OTA_AGENT_TOKEN\" \
      -F datei=@/tmp/$datei -F von=build-ide-ai-deb.sh http://127.0.0.1:8200/pakete; rm -f /tmp/$datei")
    CODE=$(tail -1 <<<"$ANTWORT")
    case "$CODE" in
      200) echo "  in der Paketquelle: $name $version" ;;
      409) echo "  $name $version liegt schon in der Paketquelle." \
                "Für eine Änderung: packaging/ota-ide-ai/revision erhöhen." ;;
      *)   echo "  Hochladen gescheitert ($CODE): $(head -1 <<<"$ANTWORT")" >&2; exit 1 ;;
    esac
  fi
}

bauen vscode "$VSCODE_FASSUNG" "$VSCODE_URL" "$VSCODE_SHA256"
bauen jetbrains "$JETBRAINS_FASSUNG" "$JETBRAINS_URL" "$JETBRAINS_SHA256"
