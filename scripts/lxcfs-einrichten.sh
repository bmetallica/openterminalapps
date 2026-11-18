#!/usr/bin/env bash
# LXCFS auf dem Wirt: `free`, `htop`, `uptime` im Arbeitsplatz zeigen dessen
# Grenzen statt der des Wirts (Handbuch Kapitel 11, agent/otaagent/lxcfs.py).
#
# Läuft bei jedem `make up` / `make update` und tut nur, was fehlt:
#
#   1. Paket `lxcfs` installieren, wenn es fehlt.
#   2. Eigene Startoptionen (systemd-Ergänzung `ota.conf`):
#        --enable-cfs      Kerne nach der CPU-Quote, nicht nach dem Cpuset
#        --enable-loadavg  Load je Container
#        --enable-pidfd    sicherer Bezug auf Prozesse
#   3. Dienst einschalten und starten.
#
# **LXCFS wird nie neu gestartet, solange Container es benutzen.** Ein neu
# gestartetes LXCFS ist ein neues Dateisystem; die alten Einhängepunkte in
# laufenden Containern liefern dann nur noch Fehler, bis der Arbeitsplatz neu
# startet. Geänderte Optionen gelten in dem Fall erst nach dem nächsten
# Neustart des Wirts — das Skript sagt es. (Debians Paket-Updates laden
# LXCFS ohnehin nur neu, per SIGUSR1, ohne es auszuhängen.)
#
# Abschalten: OTA_LXCFS=aus in deploy/.env. Neue Arbeitsplätze bekommen es
# dann nicht mehr; ein laufendes LXCFS bleibt, bis es jemand stoppt.
#
#   sudo scripts/lxcfs-einrichten.sh            # einrichten
#   sudo scripts/lxcfs-einrichten.sh --pruefen  # nur zeigen, nichts ändern
set -uo pipefail

cd "$(dirname "$0")/.."
NUR_PRUEFEN=0
[ "${1:-}" = "--pruefen" ] && NUR_PRUEFEN=1

if grep -qsE '^OTA_LXCFS=(aus|0|nein|off)' deploy/.env; then
  echo "  LXCFS: abgeschaltet (OTA_LXCFS in deploy/.env)"
  exit 0
fi

DROPIN=/etc/systemd/system/lxcfs.service.d/ota.conf
SOLL='[Service]
# Von OTA (scripts/lxcfs-einrichten.sh). Optionen siehe dort.
ExecStart=
ExecStart=/usr/bin/lxcfs --enable-cfs --enable-loadavg --enable-pidfd /var/lib/lxcfs'

bereit() { [ -r /var/lib/lxcfs/proc/meminfo ] && head -1 /var/lib/lxcfs/proc/meminfo >/dev/null 2>&1; }
benutzt() {  # Hat irgendein Container LXCFS-Dateien eingehängt (auch nachgerüstete)?
  # Jeder Prozess des Wirts sieht LXCFS unter /var/lib/lxcfs — das zählt nicht.
  cat /proc/[0-9]*/mountinfo 2>/dev/null \
    | awk '/ - fuse.lxcfs / && $5 != "/var/lib/lxcfs" { f = 1 } END { exit !f }'
}

if [ "$NUR_PRUEFEN" = 1 ]; then
  command -v lxcfs >/dev/null && echo "  Paket: $(dpkg-query -W -f='${Version}' lxcfs 2>/dev/null)" || echo "  Paket: fehlt"
  [ -f "$DROPIN" ] && echo "  Optionen: OTA" || echo "  Optionen: Vorgabe des Pakets"
  bereit && echo "  Dienst: läuft, /var/lib/lxcfs bereit" || echo "  Dienst: nicht bereit"
  exit 0
fi

if [ "$(id -u)" != 0 ]; then
  echo "  LXCFS: nicht eingerichtet (braucht root — sudo make …)"
  exit 0
fi

if ! command -v lxcfs >/dev/null; then
  if ! command -v apt-get >/dev/null; then
    echo "  LXCFS: kein apt — bitte von Hand installieren (Paket lxcfs), dann erneut."
    exit 0
  fi
  echo "  LXCFS wird installiert …"
  if ! DEBIAN_FRONTEND=noninteractive apt-get install -y -q lxcfs >/tmp/ota-lxcfs.log 2>&1; then
    echo "  LXCFS: Installation gescheitert (siehe /tmp/ota-lxcfs.log) — Arbeitsplätze laufen ohne."
    exit 0
  fi
fi

neu=0
if [ "$(cat "$DROPIN" 2>/dev/null)" != "$SOLL" ]; then
  mkdir -p "$(dirname "$DROPIN")"
  printf '%s\n' "$SOLL" > "$DROPIN"
  systemctl daemon-reload
  neu=1
fi
systemctl enable lxcfs >/dev/null 2>&1 || true

if systemctl is-active -q lxcfs; then
  if [ "$neu" = 1 ]; then
    if benutzt; then
      echo "  LXCFS: neue Optionen gelten nach dem nächsten Neustart des Wirts"
      echo "         (Container benutzen es gerade — ein Neustart von LXCFS träfe sie)."
    else
      systemctl restart lxcfs
    fi
  fi
else
  systemctl start lxcfs || true
fi

for _ in $(seq 1 10); do bereit && break; sleep 0.5; done
if bereit; then
  echo "  LXCFS bereit: neue Arbeitsplätze sehen ihre eigenen Grenzen (free, htop, uptime)."
else
  echo "  LXCFS: Dienst läuft nicht (journalctl -u lxcfs) — Arbeitsplätze laufen ohne."
fi
