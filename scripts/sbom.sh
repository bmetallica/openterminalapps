#!/usr/bin/env bash
# Erzeugt eine Stückliste (SBOM) je Image — SPDX **und** CycloneDX.
#
#   scripts/sbom.sh                 alle OTA-Images
#   scripts/sbom.sh ota/api:dev …   nur diese
#
# **Warum erzeugt und nicht gepflegt.** Ein Arbeitsplatz-Image bringt weit
# über tausend Pakete mit. Eine von Hand geführte Liste ist am Tag nach dem
# nächsten `apt upgrade` falsch — und eine falsche Stückliste ist schlimmer
# als keine, weil jemand ihr glaubt. Deshalb liest `syft` das Image selbst.
#
# Gebraucht wird sie, sobald ein Image das Haus verlässt: Wer ein Image
# weitergibt, gibt fremde Software weiter und muss sagen können, welche.
# THIRD-PARTY-NOTICES.md nennt die Lizenzen der Bestandteile, die OTA selbst
# ausmacht; hierher gehört alles, was im Image daneben liegt.
#
# `syft` läuft als Container — nichts zu installieren. Der Docker-Socket geht
# nur lesend hinein: Die Stückliste soll lesen, nicht starten.

set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ZIEL="$ROOT/sbom"
SYFT="${OTA_SYFT_IMAGE:-anchore/syft:latest}"

mkdir -p "$ZIEL"

if [ "$#" -gt 0 ]; then
  IMAGES=("$@")
else
  mapfile -t IMAGES < <(docker images --format '{{.Repository}}:{{.Tag}}' \
    | grep -E '^(ota/|127\.0\.0\.1:5000/ota/)' | grep -v '<none>' | sort -u)
fi

if [ "${#IMAGES[@]}" -eq 0 ]; then
  echo "Keine OTA-Images gefunden. Erst 'make up', dann noch einmal." >&2
  exit 1
fi

echo "Stücklisten nach $ZIEL"
echo

for ref in "${IMAGES[@]}"; do
  name=$(echo "$ref" | tr '/:' '__')
  printf '  %-42s ' "$ref"
  if docker run --rm \
      -v /var/run/docker.sock:/var/run/docker.sock:ro \
      -v "$ZIEL:/sbom" \
      "$SYFT" scan "docker:$ref" \
        -o "spdx-json=/sbom/$name.spdx.json" \
        -o "cyclonedx-json=/sbom/$name.cdx.json" \
      >/dev/null 2>"$ZIEL/.$name.log"; then
    anzahl=$(python3 -c "
import json,sys
d=json.load(open('$ZIEL/$name.spdx.json'))
print(len(d.get('packages',[])))" 2>/dev/null || echo '?')
    printf '\033[32m✓\033[0m %s Pakete\n' "$anzahl"
    rm -f "$ZIEL/.$name.log"
  else
    printf '\033[31m✗\033[0m siehe %s\n' "$ZIEL/.$name.log"
  fi
done

echo
echo "Die Dateien sind erzeugt und gehören nicht ins Repository — sie gelten"
echo "für genau den Stand, aus dem sie stammen, und veralten mit dem nächsten"
echo "Build. Wer ein Image weitergibt, legt die passende Stückliste dazu."
