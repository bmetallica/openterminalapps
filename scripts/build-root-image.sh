#!/usr/bin/env bash
# Baut das Basisimage für Root-Arbeitsplätze: `ota/base-desktop-root:1`.
#
# Setzt `ota/base-desktop:1` voraus (baut `make up` bzw.
# `scripts/build-desktop-image.sh`). Mit `--pruefen` startet es das fertige
# Image einmal unter Sysbox und prüft, dass darin Docker und Compose laufen.
#
#   scripts/build-root-image.sh            # bauen
#   scripts/build-root-image.sh --pruefen  # bauen und unter Sysbox prüfen
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TAG="${OTA_ROOT_TAG:-ota/base-desktop-root:1}"
BASIS="${OTA_DESKTOP_TAG:-ota/base-desktop:1}"
CN="ota-root-pruef-$$"

# Der Firmenproxy wie in build-desktop-image.sh — nur die drei Zeilen.
if [ -f "$ROOT/deploy/.env" ]; then
  for zeile in $(grep -E '^OTA_(HTTP|HTTPS|NO)_PROXY=' "$ROOT/deploy/.env" 2>/dev/null); do
    name="${zeile%%=*}"; wert="${zeile#*=}"
    [ -z "$wert" ] && continue
    eval ": \${$name:=\$wert}" && export "$name"
  done
fi
proxy_argumente() {
  for paar in "http_proxy:${OTA_HTTP_PROXY:-${http_proxy:-}}" \
              "https_proxy:${OTA_HTTPS_PROXY:-${https_proxy:-}}" \
              "no_proxy:${OTA_NO_PROXY:-${no_proxy:-}}"; do
    name="${paar%%:*}"; wert="${paar#*:}"
    [ -z "$wert" ] && continue
    printf -- '--build-arg %s=%s --build-arg %s=%s ' \
      "$name" "$wert" "$(echo "$name" | tr a-z A-Z)" "$wert"
  done
}

if ! docker image inspect "$BASIS" >/dev/null 2>&1; then
  echo "Das Desktop-Basisimage $BASIS fehlt. Erst:  scripts/build-desktop-image.sh" >&2
  exit 1
fi

echo "Baue $TAG auf $BASIS …"
# shellcheck disable=SC2046
docker build $(proxy_argumente) --build-arg BASIS="$BASIS" -t "$TAG" \
  "$ROOT/images/base-desktop-root" || exit 1

[ "${1:-}" = "--pruefen" ] || exit 0

echo
echo "Prüfe unter Sysbox …"
if ! docker info 2>/dev/null | grep sysbox-runc >/dev/null; then
  echo "  Sysbox fehlt auf diesem Wirt — Prüfung übersprungen (Kapitel 25)." >&2
  exit 0
fi
trap 'docker rm -f "$CN" >/dev/null 2>&1' EXIT
docker run -d --name "$CN" --runtime=sysbox-runc -e OTA_DOCKER=1 \
  --entrypoint /bin/bash "$TAG" -c '
    dockerd >/var/log/dockerd.log 2>&1 &
    sleep 600' >/dev/null || exit 1
ok=1
for _ in $(seq 1 40); do
  docker exec "$CN" test -S /var/run/docker.sock 2>/dev/null && break; sleep 0.5
done
docker exec -u 1000 "$CN" docker info --format '  dockerd {{.ServerVersion}}, {{.Driver}}' || ok=0
docker exec -u 1000 "$CN" docker compose version || ok=0
docker exec -u 1000 "$CN" sudo -n true && echo "  sudo ohne Kennwort: ja" || ok=0
[ "$ok" = 1 ] && echo "  ✓ Docker, Compose und sudo im Image" || { echo "  ✗ Prüfung fehlgeschlagen" >&2; exit 1; }
