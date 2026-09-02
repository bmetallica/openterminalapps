"""Zwischenablage-Bruecke zwischen den Displays eines Arbeitsplatzes.

Das Problem (plan.md §10.4): Jedes X-Display hat seine eigene Zwischenablage.
Kopieren in VS Code auf :1 und Einfuegen in IntelliJ auf :3 funktioniert ohne
Gegenmassnahme nicht — obwohl beide im selben Container laufen. Genau das
erwartet niemand.

Die Bruecke spiegelt die CLIPBOARD-Auswahl zwischen allen offenen Displays —
Text und Bilder (``image/png``). Bilder brauchen eine eigene Behandlung: Ein
Bild kommt nicht als Text heraus, und wer nur ``xclip -o`` fragt, haelt die
Zwischenablage faelschlich fuer leer. Ein Screenshot waere dann in der
Nachbaranwendung unerreichbar, ohne dass irgendwo etwas dazu stuende.

PRIMARY wird **nicht** gespiegelt, und das ist Absicht: Das ist die
fluechtige Markierung, nicht die Zwischenablage. Wer in einer Anwendung Text
markiert, wuerde sonst die Markierung in jeder anderen ueberschreiben.

Ereignisse statt Abfragen — wenn das Image es hergibt. ``clipnotify -l``
meldet jede Aenderung der Auswahl, statt dass die Bruecke im halben
Sekundentakt nachfragt. Es liegt in OTAs eigenem Basisimage
(``images/base-xfce``); die Kasm-Images bringen es nicht mit. Die Bruecke
entscheidet deshalb **im Container** und nicht hier: Ist ``clipnotify`` da,
wartet sie auf Ereignisse; ist es nicht da, bleibt es bei der Abfrage. Beide
Wege teilen sich denselben Abgleich darunter — was sich aendert, ist
ausschliesslich das Warten.

Der Unterschied ist nicht die Last (acht Aufrufe je Sekunde tun keinem weh),
sondern die Verzoegerung: Bei einer Abfrage im halben Sekundentakt liegt
zwischen Kopieren und Einfuegen bis zu eine halbe Sekunde, in der die
Nachbaranwendung noch den alten Inhalt hat. Wer schnell genug ist, fuegt das
Vorherige ein — und das sieht aus wie ein Fehler, der nicht reproduzierbar
ist. Ueber Ereignisse sind es Millisekunden.
"""

from __future__ import annotations

BRIDGE = r'''#!/usr/bin/env bash
# OTA Zwischenablage-Bruecke. Wird vom Agent gestartet und gestoppt.
set -u

export HOME=${HOME:-/home/kasm-user}
export XAUTHORITY=$HOME/.Xauthority

INTERVAL=@INTERVAL@
STATE=/tmp/ota-clipboard-state
PIDFILE=/tmp/ota-clipboard.pid
FIFO=/tmp/ota-clipboard.events
# Sicherheitsnetz: So lange wird hoechstens auf ein Ereignis gewartet. Geht
# eines verloren — ein Display verschwindet mitten im Kopieren —, faellt die
# Bruecke danach von selbst wieder in den Takt, statt stehenzubleiben.
MAXWARTEN=5

echo $$ > "$PIDFILE"

# Ereignisse oder Abfragen? Das entscheidet sich hier, im Container, und
# nicht beim Agent: Nur hier ist zu sehen, ob `clipnotify` vorhanden ist.
EREIGNISSE=0
if command -v clipnotify >/dev/null 2>&1; then
  EREIGNISSE=1
  rm -f "$FIFO"
  mkfifo "$FIFO" 2>/dev/null || EREIGNISSE=0
fi
if [ "$EREIGNISSE" = "1" ]; then
  # Beide Richtungen offenhalten. Sonst kehrt `read` jedes Mal zurueck,
  # wenn der letzte Schreiber die Roehre schliesst — und aus dem Warten
  # wuerde eine Endlosschleife mit voller Last.
  exec 9<>"$FIFO"
  echo "bridge: ereignisgesteuert (clipnotify)" >&2
else
  echo "bridge: Abfrage alle ${INTERVAL}s (clipnotify fehlt im Image)" >&2
fi

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

# Welche Art Inhalt gerade auf der Zwischenablage liegt. Ein Bild kommt
# nicht als Text heraus — wer nur `xclip -o` fragt, bekommt nichts und haelt
# die Zwischenablage fuer leer. Ein Screenshot aus einer Anwendung waere dann
# in der Nachbaranwendung unerreichbar, ohne dass irgendwo etwas dazu stuende.
clip_type() {   # clip_type <display> -> "image/png" oder "text"
  if timeout 2 xclip -d ":$1" -selection clipboard -t TARGETS -o 2>/dev/null \
     | grep -qx "image/png"; then
    echo "image/png"
  else
    echo "text"
  fi
}

read_clip() {   # read_clip <display> <typ> <datei>
  if [ "$2" = "image/png" ]; then
    timeout 4 xclip -d ":$1" -selection clipboard -t image/png -o > "$3" 2>/dev/null
  else
    timeout 2 xclip -d ":$1" -selection clipboard -o > "$3" 2>/dev/null
  fi
  [ -s "$3" ]
}

write_clip() {  # write_clip <display> <datei> <typ>
  # xclip haelt die Auswahl, bis eine andere Anwendung sie uebernimmt.
  # Deshalb im Hintergrund und ohne auf das Ende zu warten.
  if [ "$3" = "image/png" ]; then
    timeout 4 xclip -d ":$1" -selection clipboard -t image/png -i < "$2" 2>/dev/null &
  else
    timeout 2 xclip -d ":$1" -selection clipboard -i < "$2" 2>/dev/null &
  fi
}

# Je Display eine Wache. `clipnotify -l` beendet sich nicht, sondern schreibt
# bei jeder Aenderung eine Zeile — daraus wird hier der Name des Displays.
#
# Die Wachen werden bei jedem Durchlauf nachgezogen, denn Displays kommen und
# gehen: Der Agent macht eines auf, sobald eine Anwendung startet, und wieder
# zu, wenn sie endet.
WACHEN=""

wachen_pflegen() {
  local offen; offen=" $(displays | tr '\n' ' ')"
  local neu="" eintrag d pid

  for d in $(displays); do
    pid=""
    for eintrag in $WACHEN; do
      case "$eintrag" in "$d":*) pid="${eintrag#*:}" ;; esac
    done
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      neu="$neu $d:$pid"
      continue
    fi
    ( DISPLAY=":$d" clipnotify -l -s clipboard 2>/dev/null \
        | while read -r _; do echo "$d" >&9; done ) &
    neu="$neu $d:$!"
  done

  # Wachen fuer Displays, die es nicht mehr gibt, beenden.
  for eintrag in $WACHEN; do
    d="${eintrag%%:*}"; pid="${eintrag#*:}"
    case "$offen" in
      *" $d "*) ;;
      *) kill "$pid" 2>/dev/null || true ;;
    esac
  done

  WACHEN="$neu"
}

warten() {
  if [ "$EREIGNISSE" != "1" ]; then
    sleep "$INTERVAL"
    return
  fi
  wachen_pflegen
  read -t "$MAXWARTEN" -r _ <&9 || true
  # Ein einziges Kopieren loest oft mehrere Ereignisse aus — erst PRIMARY,
  # dann CLIPBOARD, bei manchen Anwendungen noch ein drittes. Kurz
  # nachfassen und den Rest wegraeumen, sonst laeuft der Abgleich drei Mal
  # fuer denselben Inhalt.
  sleep 0.05
  while read -t 0.05 -r _ <&9; do :; done
}

while true; do
  warten

  ds=$(displays)
  [ -z "$ds" ] && continue

  # Wer hat etwas Neues? Das erste Display mit abweichendem Inhalt gewinnt.
  source_display=""
  source_type=""
  for d in $ds; do
    t=$(clip_type "$d")
    read_clip "$d" "$t" "$STATE.neu" || continue
    h=$(md5sum < "$STATE.neu" | cut -d' ' -f1)
    # Der Typ gehoert in die Pruefsumme: Sonst gaelte ein Bild, das zufaellig
    # dieselben Bytes hat wie der letzte Text, als schon bekannt.
    h="$t:$h"
    if [ "$h" != "$last_hash" ]; then
      source_display="$d"
      source_type="$t"
      mv -f "$STATE.neu" "$STATE"
      last_hash="$h"
      break
    fi
  done
  rm -f "$STATE.neu"

  [ -z "$source_display" ] && continue

  # Auf alle uebrigen Displays uebertragen. Der Schleifenschutz steckt in
  # last_hash: Was wir gerade geschrieben haben, gilt beim naechsten
  # Durchlauf als bekannt und loest keine weitere Runde aus.
  for d in $ds; do
    [ "$d" = "$source_display" ] && continue
    write_clip "$d" "$STATE" "$source_type"
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
  PID=$(cat "$PIDFILE")
  # Die ganze Prozessgruppe, nicht nur die Bruecke selbst.
  #
  # Sie startet je Display eine Wache (`clipnotify -l`) als Kindprozess.
  # Stirbt nur die Bruecke, bleiben die Wachen als Waisen zurueck und halten
  # eine Roehre offen, die niemand mehr liest. Die Bruecke wird mit `setsid`
  # gestartet und ist damit Fuehrerin ihrer Gruppe — deshalb geht das.
  kill -- "-$PID" 2>/dev/null || kill "$PID" 2>/dev/null || true
  rm -f "$PIDFILE"
fi
rm -f /tmp/ota-clipboard.events
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
