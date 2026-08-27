"""Zwischenablage-Bruecke zwischen den Displays eines Arbeitsplatzes.

Das Problem (plan.md §10.4): Jedes X-Display hat seine eigene Zwischenablage.
Kopieren in VS Code auf :1 und Einfuegen in IntelliJ auf :3 funktioniert ohne
Gegenmassnahme nicht — obwohl beide im selben Container laufen. Genau das
erwartet niemand.

Die Bruecke spiegelt die CLIPBOARD-Auswahl zwischen allen offenen Displays.

Warum Abfragen statt XFIXES-Ereignissen: Das Basisimage bringt weder
``clipnotify`` noch python-xlib mit. Ein Intervall von einer halben Sekunde
ist fuer Menschen nicht spuerbar und kostet bei vier Displays etwa acht
Aufrufe je Sekunde. Sobald ein eigenes Basisimage gebaut wird (Roadmap M5),
gehoert ``clipnotify`` hinein und diese Schleife wird ereignisgesteuert.
"""

from __future__ import annotations

BRIDGE = r'''#!/usr/bin/env bash
# OTA Zwischenablage-Bruecke. Wird vom Agent gestartet und gestoppt.
set -u

export HOME=/home/kasm-user
export XAUTHORITY=$HOME/.Xauthority

INTERVAL=@INTERVAL@
STATE=/tmp/ota-clipboard-state
PIDFILE=/tmp/ota-clipboard.pid

echo $$ > "$PIDFILE"

# Was zuletzt als gemeinsamer Stand galt. Der Vergleich laeuft ueber eine
# Pruefsumme, damit grosse Inhalte nicht bei jedem Durchlauf durch die
# Shell wandern.
last_hash=""

displays() {
  for f in /tmp/.X11-unix/X*; do
    [ -e "$f" ] || continue
    echo "${f##*/X}"
  done
}

read_clip() {   # read_clip <display>
  timeout 2 xclip -d ":$1" -selection clipboard -o 2>/dev/null || true
}

write_clip() {  # write_clip <display> <datei>
  # xclip haelt die Auswahl, bis eine andere Anwendung sie uebernimmt.
  # Deshalb im Hintergrund und ohne auf das Ende zu warten.
  timeout 2 xclip -d ":$1" -selection clipboard -i < "$2" 2>/dev/null &
}

while true; do
  sleep "$INTERVAL"

  ds=$(displays)
  [ -z "$ds" ] && continue

  # Wer hat etwas Neues? Das erste Display mit abweichendem Inhalt gewinnt.
  source_display=""
  for d in $ds; do
    content=$(read_clip "$d")
    [ -z "$content" ] && continue
    h=$(printf '%s' "$content" | md5sum | cut -d' ' -f1)
    if [ "$h" != "$last_hash" ]; then
      source_display="$d"
      printf '%s' "$content" > "$STATE"
      last_hash="$h"
      break
    fi
  done

  [ -z "$source_display" ] && continue

  # Auf alle uebrigen Displays uebertragen. Der Schleifenschutz steckt in
  # last_hash: Was wir gerade geschrieben haben, gilt beim naechsten
  # Durchlauf als bekannt und loest keine weitere Runde aus.
  for d in $ds; do
    [ "$d" = "$source_display" ] && continue
    write_clip "$d" "$STATE"
  done
done
'''

# Beendet wird ausschliesslich ueber die PID-Datei.
#
# "pkill -f ota-clipboard-bridge" waere naheliegend und falsch: Das Muster
# steht auch in der Kommandozeile der Shell, die den Befehl gerade ausfuehrt
# — sie wuerde sich selbst beenden, und zwar wortlos.
STOP = r'''
PIDFILE=/tmp/ota-clipboard.pid
if [ -f "$PIDFILE" ]; then
  kill "$(cat "$PIDFILE")" 2>/dev/null || true
  rm -f "$PIDFILE"
fi
echo "bridge-stopped"
'''


def install_script(interval: float = 0.5) -> list[str]:
    """Schreibt die Bruecke in den Container und startet sie."""
    body = BRIDGE.replace("@INTERVAL@", str(interval))
    # Ueber base64, damit keine Anfuehrungszeichen oder Zeilenumbrueche
    # beim Weg durch zwei Shells verlorengehen.
    import base64
    encoded = base64.b64encode(body.encode()).decode()
    # Alles ueber die PID-Datei, nie ueber Musterabgleich auf Prozessnamen:
    # Das Muster stuende auch in der Kommandozeile dieser Shell selbst.
    return ["bash", "-lc", (
        f"echo {encoded} | base64 -d > /tmp/ota-clipboard-bridge.sh && "
        "chmod +x /tmp/ota-clipboard-bridge.sh && "
        "{ [ -f /tmp/ota-clipboard.pid ] && "
        "  kill \"$(cat /tmp/ota-clipboard.pid)\" 2>/dev/null; } ; "
        "rm -f /tmp/ota-clipboard.pid; "
        "setsid nohup /tmp/ota-clipboard-bridge.sh > /tmp/ota-clipboard.log 2>&1 < /dev/null & "
        "sleep 0.8; "
        "if [ -f /tmp/ota-clipboard.pid ] && "
        "   kill -0 \"$(cat /tmp/ota-clipboard.pid)\" 2>/dev/null; then "
        "  echo bridge-running; else echo bridge-failed; fi"
    )]


def stop_script() -> list[str]:
    return ["bash", "-lc", STOP]
