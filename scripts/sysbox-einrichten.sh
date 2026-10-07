#!/usr/bin/env bash
# Richtet Sysbox für Root-Arbeitsplätze ein — ohne einen Container anzufassen.
#
# Handbuch Kapitel 25. Auf der Entwicklungsmaschine am 2026-10-06 von Hand so
# durchgeführt; dieses Skript ist derselbe Weg, mit den Prüfungen davor und
# danach.
#
# **Warum ein eigenes Skript und nicht einfach `apt install ./sysbox-ce.deb`:**
# Das Paket will Docker neu starten, um `bip` und `default-address-pools` in
# /etc/docker/daemon.json zu setzen — und verweigert die Einrichtung, solange
# auch nur ein Container existiert („docker rm $(docker ps -a -q) -f"). Diesen
# Befehl schlägt es vor; ausführen tut es ihn nicht, und **niemand sollte das
# tun**. Stehen beide Einträge schon in der daemon.json, braucht das Paket
# keinen Neustart: Es trägt nur die Runtime ein und lässt Docker die
# Konfiguration per SIGHUP neu lesen. Laufende Container bleiben, wie sie sind.
#
# Dieses Skript trägt deshalb vorher die Werte ein, **die heute schon gelten**:
# die Adresse von docker0 und Dockers eingebaute Adressbereiche. Damit ändert
# sich auch beim nächsten echten Neustart von Docker nichts am Netz.
#
#   sudo scripts/sysbox-einrichten.sh                  # einrichten
#   sudo scripts/sysbox-einrichten.sh --live-restore   # dazu "live-restore": true
#   sudo scripts/sysbox-einrichten.sh --pruefen        # nur prüfen, nichts ändern
#
# `--live-restore` lässt Container weiterlaufen, wenn Docker selbst neu startet
# (z. B. bei einem Update des Docker-Pakets). Empfohlen, aber eine eigene
# Entscheidung: Es ändert das Verhalten bei künftigen Docker-Updates.
set -euo pipefail

VERSION="0.7.1"
SHA256="9d6d5484f980d0a17f86c492c1262015c2afb66280bdb97215b79fde6a0261c5"
DEB="sysbox-ce_${VERSION}.linux_amd64.deb"
URL="https://github.com/nestybox/sysbox/releases/download/v${VERSION}/${DEB}"
CFG="/etc/docker/daemon.json"

LIVE_RESTORE=0
NUR_PRUEFEN=0
for arg in "$@"; do
  case "$arg" in
    --live-restore) LIVE_RESTORE=1 ;;
    --pruefen) NUR_PRUEFEN=1 ;;
    *) echo "Unbekannte Option: $arg" >&2; exit 2 ;;
  esac
done

ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
halt() { printf '  \033[31m✗\033[0m %s\n' "$1" >&2; exit 1; }
info() { printf '    %s\n' "$1"; }

[ "$(id -u)" = "0" ] || halt "Bitte als root ausführen (sudo)."

echo "Sysbox ${VERSION} für Root-Arbeitsplätze"
echo

if docker info 2>/dev/null | grep 'sysbox-runc' >/dev/null; then
  ok "Sysbox ist bereits eingerichtet — nichts zu tun."
  systemctl is-active --quiet sysbox && ok "Dienst sysbox läuft" || halt "Dienst sysbox läuft nicht: systemctl status sysbox"
  exit 0
fi

# ------------------------------------------------------------------ Prüfen
echo "Voraussetzungen"
[ "$(dpkg --print-architecture)" = "amd64" ] || halt "Nur amd64 (dieses Skript lädt das amd64-Paket)."
ok "Architektur amd64"

KERN="$(uname -r)"; MAJ="${KERN%%.*}"; REST="${KERN#*.}"; MIN="${REST%%.*}"
if [ "$MAJ" -gt 5 ] || { [ "$MAJ" -eq 5 ] && [ "$MIN" -ge 12 ]; }; then
  ok "Kernel $KERN (ID-gemappte Mounts — Dateirechte im Zuhause stimmen)"
else
  halt "Kernel $KERN ist älter als 5.12. Ohne ID-gemappte Mounts gehörten die Dateien im Zuhause im Container 'nobody'."
fi

docker info >/dev/null 2>&1 || halt "Docker antwortet nicht."
ok "Docker $(docker info --format '{{.ServerVersion}}')"

# Steht bip oder ein Adressbereich als **Startparameter** von dockerd, darf er
# nicht zusätzlich in die daemon.json — dockerd verweigert dann den nächsten
# Start („conflicts between flags and configuration file").
ARGS="$(ps -o args= -C dockerd 2>/dev/null || true)"
if grep -qE -- '--bip|--default-address-pool|--live-restore' <<<"$ARGS"; then
  halt "dockerd läuft mit --bip/--default-address-pool/--live-restore als Startparameter. Bitte diese Werte zuerst in $CFG verschieben (Kapitel 25)."
fi
ok "Keine Netz-Startparameter an dockerd"

BIP="$(ip -4 -o addr show docker0 2>/dev/null | awk '{print $4}' | head -1)"
if [ -z "$BIP" ]; then
  BIP="172.17.0.1/16"
  info "docker0 ohne Adresse — nehme Dockers Vorgabe $BIP"
fi
ok "docker0 liegt auf $BIP — dieser Wert kommt als \"bip\" in die Konfiguration"

VORHER="$(docker ps -q | wc -l)"
ok "$VORHER laufende Container (werden danach wieder gezählt)"

if [ "$NUR_PRUEFEN" = "1" ]; then
  echo
  echo "Nur geprüft, nichts geändert."
  exit 0
fi

# ------------------------------------------------------------- daemon.json
echo
echo "Docker-Konfiguration"
if [ -f "$CFG" ]; then
  SICHER="$CFG.vor-sysbox.$(date +%Y%m%d-%H%M%S)"
  cp -p "$CFG" "$SICHER"
  ok "Bisherige $CFG gesichert nach $SICHER"
fi
mkdir -p "$(dirname "$CFG")"

python3 - "$CFG" "$BIP" "$LIVE_RESTORE" <<'PY'
import json, os, sys
pfad, bip, live = sys.argv[1], sys.argv[2], sys.argv[3] == "1"
daten = {}
if os.path.exists(pfad) and os.path.getsize(pfad) > 0:
    with open(pfad, encoding="utf-8") as fh:
        daten = json.load(fh)
geaendert = []
# Nur ergaenzen, nie ueberschreiben: Was schon dasteht, hat jemand so gewollt.
if not daten.get("bip"):
    daten["bip"] = bip; geaendert.append(f"bip={bip}")
if not daten.get("default-address-pools"):
    # Dockers eingebaute Vorgabe — dieselben Bereiche, die heute schon gelten.
    daten["default-address-pools"] = [
        {"base": "172.17.0.0/12", "size": 16},
        {"base": "192.168.0.0/16", "size": 20},
    ]
    geaendert.append("default-address-pools=Docker-Vorgabe")
if live and not daten.get("live-restore"):
    daten["live-restore"] = True; geaendert.append("live-restore=true")
laufzeiten = daten.setdefault("runtimes", {})
if "sysbox-runc" not in laufzeiten:
    laufzeiten["sysbox-runc"] = {"path": "/usr/bin/sysbox-runc"}
    geaendert.append("runtime sysbox-runc")
# Eingerueckt mit Leerzeichen: Das Paket sucht `^[ ]+"bip"` — ohne Einrueckung
# hielte es die Netzwerte fuer fehlend und verlangte wieder einen Neustart.
with open(pfad, "w", encoding="utf-8") as fh:
    json.dump(daten, fh, indent=4)
    fh.write("\n")
print("    ergänzt: " + (", ".join(geaendert) if geaendert else "nichts"))
PY
ok "$CFG vorbereitet (bip und Adressbereiche stehen fest, kein Neustart nötig)"

# ----------------------------------------------------------------- Paket
echo
echo "Paket"
ARBEIT="$(mktemp -d)"
trap 'rm -rf "$ARBEIT"' EXIT
# Zuerst aus dem Datei-Vorrat der eigenen Paketquelle (Kapitel 26), sonst
# von GitHub. Die Prüfsumme gilt für beide Wege.
REPO_ROOT="${OTA_REPO_ROOT:-$(grep -E '^OTA_REPO_ROOT=' "$(dirname "$0")/../deploy/.env" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '"')}"
VORRAT="${REPO_ROOT:-/srv/ota/repo}/aptly/public/dateien/sysbox/$DEB"
if [ -f "$VORRAT" ]; then
  cp "$VORRAT" "$ARBEIT/$DEB"
  HER="aus dem Datei-Vorrat"
else
  curl -fsSL -o "$ARBEIT/$DEB" "$URL" || halt "Download gescheitert: $URL (Proxy? Kapitel 21)"
  HER="heruntergeladen"
fi
echo "$SHA256  $ARBEIT/$DEB" | sha256sum -c --quiet - || halt "Prüfsumme stimmt nicht — Paket NICHT installiert."
ok "Paket $HER, Prüfsumme stimmt"

# Das Paket meldet ggf., dass die Kernel-Header fehlen. Für Root-Arbeitsplätze
# werden sie nicht gebraucht (sie wären es nur für Programme, die im Container
# Kernelmodule bauen).
DEBIAN_FRONTEND=noninteractive apt-get install -y "$ARBEIT/$DEB"
ok "sysbox-ce installiert"

# ---------------------------------------------------------------- Danach
echo
echo "Kontrolle"
NACHHER="$(docker ps -q | wc -l)"
if [ "$NACHHER" = "$VORHER" ]; then
  ok "Weiterhin $NACHHER laufende Container — keiner wurde angefasst"
else
  halt "Vorher $VORHER, jetzt $NACHHER laufende Container. Bitte sofort prüfen: docker ps -a"
fi
docker info 2>/dev/null | grep 'sysbox-runc' >/dev/null && ok "Docker kennt die Runtime sysbox-runc" \
  || halt "Docker kennt sysbox-runc nicht — kill -HUP \$(pidof dockerd) und erneut prüfen"
systemctl is-active --quiet sysbox && ok "Dienst sysbox läuft" || halt "Dienst sysbox läuft nicht"
if [ "$LIVE_RESTORE" = "1" ]; then
  docker info 2>/dev/null | grep 'Live Restore Enabled: true' >/dev/null && ok "live-restore ist aktiv" \
    || info "live-restore greift nach dem nächsten Neuladen von Docker"
fi

echo
echo "Fertig. Weiter mit:  make up   (baut das Root-Image ota/base-desktop-root:1)"
echo "Sysbox **nicht** automatisch aktualisieren lassen: Ein Update startet die"
echo "Sysbox-Dienste neu und damit alle laufenden Root-Arbeitsplätze. Optional:"
echo "    apt-mark hold sysbox-ce"
