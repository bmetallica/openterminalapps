#!/bin/bash
# Start eines Root-Arbeitsplatzes: Anlagenwerte, dann `dockerd`, dann der
# Desktop als UID 1000.
set -u

# **Anlagenwerte von jetzt, nicht vom Tag der Erzeugung.** Ein Root-Arbeitsplatz
# wird angehalten und wieder gestartet, nicht neu erzeugt — seine Umgebung
# stammt also vom ersten Start. TURN-Adresse, Proxy und Tastaturlayout können
# sich seitdem geändert haben. Der Agent legt die aktuellen Werte vor jedem
# Start in diese Datei (eingehängt, nur lesbar), und sie gewinnen.
if [ -r /etc/ota/umgebung.sh ]; then
  # shellcheck disable=SC1091
  . /etc/ota/umgebung.sh
fi

if [ "${OTA_DOCKER:-0}" = "1" ]; then
  # Das Protokoll von dockerd gedeckelt: Es liegt im Container und wüchse sonst
  # mit jeder Sitzung, ohne dass es jemand liest.
  if [ -f /var/log/dockerd.log ] && [ "$(stat -c %s /var/log/dockerd.log)" -gt 10485760 ]; then
    mv -f /var/log/dockerd.log /var/log/dockerd.log.1
  fi
  # **Der Router als DNS fuer die inneren Container.** Im Arbeitsplatz steht
  # als Nameserver Dockers eingebauter Resolver 127.0.0.11 — eine
  # Loopback-Adresse, die `dockerd` nicht an seine Container weitergeben kann.
  # Er faellt dann still auf 8.8.8.8 zurueck, und genau den sperrt der Router
  # (fremde Resolver sind zu, sonst waeren Freigaben nach Namen wirkungslos).
  # Gemessen am 2026-10-06: `docker run alpine wget example.com` → „bad
  # address", waehrend dieselbe Abfrage an den Router antwortete. Der Router
  # ist die Standardroute des Arbeitsplatzes. Wer in /etc/docker/daemon.json
  # selbst einen DNS eintraegt, behaelt ihn.
  #
  # Die Adresse kommt vom Agent (`OTA_ROUTER`), nicht aus `ip route`: Die
  # Standardroute setzt der Router erst **nach** dem Start von aussen, und
  # beim ersten Versuch stand hier deshalb gar nichts.
  DNS_ARG=()
  ROUTER="${OTA_ROUTER:-$(ip route 2>/dev/null | awk '/^default/ {print $3; exit}')}"
  if [ -n "$ROUTER" ] && ! grep -qs '"dns"' /etc/docker/daemon.json; then
    DNS_ARG=(--dns "$ROUTER")
  fi
  dockerd "${DNS_ARG[@]}" >> /var/log/dockerd.log 2>&1 &
  DOCKERD_PID=$!
  for _ in $(seq 1 60); do
    [ -S /var/run/docker.sock ] && break
    sleep 0.5
  done
  if [ ! -S /var/run/docker.sock ]; then
    echo "dockerd kam nicht hoch — Arbeitsplatz startet ohne Docker" >&2
    tail -20 /var/log/dockerd.log >&2
  fi
fi

# Der Desktop als 1000, mit der Umgebung von oben. `--init-groups` bringt die
# Gruppe `docker` mit — ohne sie wäre `docker` nur mit `sudo` benutzbar.
#
# **Nicht per `exec`.** Dieses Skript bleibt PID 1, damit es beim Anhalten
# beide geordnet beendet: erst den Desktop, dann `dockerd`, der seinerseits
# die inneren Container stoppt. Mit `exec` war der Desktop PID 1, `dockerd`
# bekam nie ein Signal, und Docker beendete den Arbeitsplatz nach der
# Wartezeit hart (gemessen 2026-10-06: Exit 137) — mitten in laufenden
# inneren Containern, deren Daten der Nutzer behalten will.
export HOME=/home/ota USER=ota LOGNAME=ota
setpriv --reuid=1000 --regid=1000 --init-groups /dockerstartup/desktop_startup.sh &
DESKTOP_PID=$!

# **Alles von 1000, nicht nur das Startskript.** Das Startskript des
# Basisimages wartet im Vordergrund auf `custom_startup.sh` — im Arbeitsplatz
# ein `sleep 3600` —, und Bash fuehrt seinen TERM-Handler erst aus, wenn der
# fertig ist. Gemessen am 2026-10-06: `dockerd` war nach dem Signal sofort weg,
# der Desktop stand nach 20 Sekunden noch. Der Container wird ohnehin
# angehalten; was hier zaehlt, ist dass `dockerd` seine Container geordnet
# beendet und danach niemand mehr auf eine Stunde wartet.
anhalten() {
  pkill -TERM -u 1000 2>/dev/null
  if [ -n "${DOCKERD_PID:-}" ]; then
    kill -TERM "$DOCKERD_PID" 2>/dev/null
    for _ in $(seq 1 60); do kill -0 "$DOCKERD_PID" 2>/dev/null || break; sleep 0.5; done
  fi
  for _ in $(seq 1 10); do pgrep -u 1000 >/dev/null || break; sleep 0.5; done
  pkill -KILL -u 1000 2>/dev/null
  exit 0
}
trap anhalten TERM INT
wait "$DESKTOP_PID"
