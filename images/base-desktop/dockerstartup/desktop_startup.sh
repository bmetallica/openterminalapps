#!/usr/bin/env bash
# Startet die Sitzung: Xvfb, XFCE, dann der Strom über Selkies.
#
# **Der Vertrag mit OTA** — hier steht, worauf sich der Agent verlässt:
#
#   * Der Dienst nimmt auf **8080** Verbindungen an. Daran erkennt der Agent,
#     dass die Session bereit ist.
#   * Er verlangt Basic-Auth mit `VNC_USER` und `VNC_PW`. Traefik setzt den
#     Header davor — genau wie beim bisherigen Weg. Der Name der Variablen
#     bleibt `VNC_*`, obwohl hier kein VNC mehr läuft: Der Agent reicht sie
#     unverändert durch, und ein zweiter Satz Namen für dieselbe Sache wäre
#     eine Fehlerquelle ohne Gewinn.
#   * **Alles geht durch Traefik.** Selkies 2.0 überträgt Bild, Ton und
#     Eingaben über WebSockets auf demselben Port 8080 wie die Oberfläche.
#     Bis zum 2026-10-07 lief das Bild als WebRTC über UDP und brauchte den
#     TURN-Dienst des Stacks; das ist vorbei. Der Container veröffentlicht
#     keinen einzigen Port.
#   * `/dockerstartup/custom_startup.sh` wird ausgeführt und neu gestartet,
#     wenn es sich beendet. Ein Arbeitsplatz überdeckt es mit einem Skript,
#     das nur wartet.
#   * Das Display ist `:1`, damit der Agent weitere Anwendungen genauso
#     startet wie bisher (apps.py).
#
# Was **nicht** gilt: Es gibt keine `.vnc/passwd`, kein `.kasmpasswd` und
# keinen zweiten X-Server je Anwendung. Selkies überträgt genau ein Display.
# Mehrere Anwendungen nebeneinander laufen deshalb auf demselben Bildschirm —
# das ist der auffälligste Unterschied zum bisherigen Arbeitsplatzmodell und
# der Grund, warum dies vorerst ein Testimage ist.

set -e

export HOME=${HOME:-/home/ota}
export DISPLAY=${DISPLAY:-:1}
export XAUTHORITY=$HOME/.Xauthority
STARTUPDIR=${STARTUPDIR:-/dockerstartup}
DISPLAY_NUM=${DISPLAY#:}
VNC_RESOLUTION=${VNC_RESOLUTION:-1280x720}
BREITE=${VNC_RESOLUTION%x*}
HOEHE=${VNC_RESOLUTION#*x}
PORT=${SELKIES_PORT:-8080}

# Der Agent schickt heute `VNC_PW` und `VNC_USER` — Namen aus der Zeit, als
# KasmVNC das Bild übertrug. Hier läuft kein VNC mehr, und die Namen sollen
# irgendwann `OTA_SESSION_*` heissen. Damit die Umbenennung ohne Bruch geht,
# nimmt dieses Skript schon beide entgegen; der Agent darf nachziehen, wann
# es passt.
VNC_PW=${OTA_SESSION_PW:-${VNC_PW:-}}
VNC_USER=${OTA_SESSION_USER:-${VNC_USER:-ota}}

if [ -z "$VNC_PW" ]; then
  echo "Kein Sitzungspasswort (OTA_SESSION_PW/VNC_PW) — es wird nicht gestartet." >&2
  exit 1
fi

mkdir -p "$HOME/Desktop" "$HOME/.cache"

# --- Der Verweis unter dem Anmeldenamen ----------------------------------
#
# Das Zuhause liegt fest unter /home/ota und wandert nie. Wer aber im
# Dateimanager nachsieht oder `cd /home/<name>` tippt, sucht seinen eigenen
# Namen — deshalb daneben ein Verweis. Dasselbe Muster wie auf dem Host: dort
# wird unter der Kennung gespeichert und ein lesbarer Verweis danebengelegt.
#
# Eine Umbenennung in Keycloak verschiebt damit nur diesen Verweis. Alles, was
# im Profil einen absoluten Pfad gespeichert hat — Editor-Einstellungen,
# virtuelle Umgebungen, `git config` — bleibt gültig. Genau das wäre kaputt,
# wenn das Zuhause selbst den Anmeldenamen trüge.
#
# Der Name kommt von aussen und wird deshalb geprüft: Alles ausser Buchstaben,
# Ziffern, Punkt, Strich und Unterstrich fliegt raus, und `.`/`..` sind keine
# Namen. Ein Verweis ist billig; ein Verweis an einer Stelle, die jemand
# bestimmen darf, wäre es nicht.
if [ -n "${OTA_LOGIN:-}" ]; then
  SAUBER=$(printf '%s' "$OTA_LOGIN" | tr -cd 'A-Za-z0-9._-')
  case "$SAUBER" in
    ""|"."|"..") SAUBER="" ;;
  esac
  if [ -n "$SAUBER" ] && [ "/home/$SAUBER" != "$HOME" ]; then
    ln -sfn "$HOME" "/home/$SAUBER" 2>/dev/null || true
  fi
fi

# --- Reste eines harten Endes wegräumen ----------------------------------
#
# Dasselbe wie im KasmVNC-Startskript und aus demselben Grund: Das Zuhause
# überdauert den Container, und ein Sperrfile von einem hart beendeten
# Vorgänger lässt den X-Server gar nicht erst hochkommen.
rm -f "/tmp/.X${DISPLAY_NUM}-lock" "/tmp/.X11-unix/X${DISPLAY_NUM}" 2>/dev/null || true

touch "$XAUTHORITY"
xauth add "$DISPLAY" MIT-MAGIC-COOKIE-1 "$(mcookie)" 2>/dev/null || true

# --- Der Bildschirm ------------------------------------------------------
#
# Grosszügig dimensioniert und nicht auf die Startgrösse festgenagelt:
# Selkies passt die Auflösung an das Browserfenster an (`--enable-resize`),
# und ein Xvfb lässt sich nur innerhalb dessen vergrössern, was er beim Start
# bekommen hat. 3840x2160 deckt jeden Bildschirm ab, den jemand aufmacht,
# und kostet nichts, solange die Fläche nicht benutzt wird.
Xvfb "$DISPLAY" -screen 0 3840x2160x24 \
  -dpms -s 0 -ac -noreset -nolisten tcp \
  +extension COMPOSITE +extension DAMAGE +extension RANDR +extension RENDER \
  +extension MIT-SHM +extension XFIXES +extension XTEST \
  > /tmp/xvfb.log 2>&1 &
XVFB_PID=$!

for i in $(seq 1 60); do
  [ -e "/tmp/.X11-unix/X${DISPLAY_NUM}" ] && break
  sleep 0.5
done
if [ ! -e "/tmp/.X11-unix/X${DISPLAY_NUM}" ]; then
  echo "Xvfb kam nicht hoch:" >&2
  tail -30 /tmp/xvfb.log >&2
  exit 1
fi

# Die sichtbare Fläche auf die gewünschte Startgrösse setzen. Der Rahmen
# bleibt 3840x2160; der Browser darf ihn später ausfüllen.
xrandr --output screen --mode "${BREITE}x${HOEHE}" 2>/dev/null || true

# --- Ton -----------------------------------------------------------------
#
# Ein eigener PulseAudio-Dienst, weil im Container keiner läuft. Scheitert er,
# ist das kein Grund, die Sitzung abzubrechen — dann gibt es eben keinen Ton,
# und Selkies kommt damit zurecht.
export PULSE_SERVER=${PULSE_SERVER:-unix:/tmp/pulse-socket}
pulseaudio --daemonize=false --exit-idle-time=-1 --disallow-exit \
  --load="module-native-protocol-unix socket=/tmp/pulse-socket" \
  --load="module-null-sink sink_name=ota sink_properties=device.description=OTA" \
  --load="module-always-sink" \
  > /tmp/pulseaudio.log 2>&1 &

# --- XFCE ----------------------------------------------------------------
if [ -z "${DBUS_SESSION_BUS_ADDRESS:-}" ]; then
  eval "$(dbus-launch --sh-syntax)" 2>/dev/null || true
fi
export DBUS_SESSION_BUS_ADDRESS

xsetroot -solid '#1b2733' 2>/dev/null || true

# **Arbeitsplatz oder einzelne Anwendung.** Der Unterschied ist nicht
# Geschmack: Selkies überträgt genau ein Display, und was darauf liegt, sieht
# der Anwender. Hinter einer einzelnen Anwendung sind Leiste und
# Schreibtischsymbole Ballast, den niemand bedienen will — und auf einer
# Maschine ohne GPU kostet der Compositor Rechenzeit, die der Kodierer besser
# gebraucht.
#
# Ganz ohne Fenstermanager geht es nicht: Die Anwendung hätte keinen Rahmen,
# folgte der Bildschirmgrösse nicht und liesse sich nicht formatfüllend
# setzen. `xfwm4` allein ist der kleinste Umfang, der das kann.
if [ "${OTA_MODE:-workspace}" = "single_app" ]; then
  # `--compositor=off`, weil auf einer Maschine ohne GPU jeder Bildaufbau
  # in Software passiert — und diese Rechenzeit gehört dem Kodierer.
  # Kein `--daemon`: Die Option gibt es in Debians xfwm4 nicht, und der
  # Fenstermanager beendete sich damit sofort. Sichtbar war das erst
  # daran, dass `wmctrl` keine Fensterliste bekam.
  xfwm4 --compositor=off > /tmp/xfwm4.log 2>&1 &

  # Sobald ein Fenster da ist, formatfüllend setzen — sonst zeigt der Strom an
  # den Rändern die leere Fläche. Dieselbe Erkennung wie im Agent (apps.py):
  # `wmctrl -l` listet auch Fenster, die "überall kleben" (-1 in der zweiten
  # Spalte) und keine Anwendung sind.
  # **Die Aufsicht über das Fenster.** Sie läuft dauerhaft, nicht einmalig:
  #
  # * `fullscreen` und nicht `maximized` — maximiert bliebe die Titelleiste
  #   stehen, und bei einer einzelnen Anwendung gibt es nichts, wozu man sie
  #   brauchte. Formatfüllend ist ausserdem das, was „nur diese Anwendung"
  #   verspricht.
  # * **Minimiert kommt wieder hoch.** Wer die Anwendung über ihren eigenen
  #   Fensterknopf einklappt, sähe sonst für den Rest der Sitzung eine leere
  #   Fläche und käme mit den Mitteln von OTA nicht mehr heran — es gibt ja
  #   keine Leiste, über die man sie zurückholt.
  # * **Geschlossen kommt sie wieder.** Das erledigt die Aufsicht weiter
  #   unten, die `custom_startup.sh` neu startet, sobald es sich beendet.
  #   Diese Schleife setzt das neue Fenster dann wieder formatfüllend.
  (
    while true; do
      FENSTER=$(wmctrl -l 2>/dev/null | awk '$2 != -1' | head -1 | cut -d' ' -f1)
      if [ -n "$FENSTER" ]; then
        ZUSTAND=$(xprop -id "$FENSTER" _NET_WM_STATE 2>/dev/null || true)
        case "$ZUSTAND" in
          *_NET_WM_STATE_HIDDEN*) wmctrl -i -a "$FENSTER" 2>/dev/null || true ;;
        esac
        case "$ZUSTAND" in
          *_NET_WM_STATE_FULLSCREEN*) : ;;
          *) wmctrl -i -r "$FENSTER" -b add,fullscreen 2>/dev/null || true ;;
        esac
      fi
      sleep 2
    done
  ) &
else
  startxfce4 > /tmp/xfce.log 2>&1 &
fi

# Siehe dieselbe Stelle in vnc_startup.sh: `-fork` verzweigt hier nicht, und
# ohne `&` bleibt das ganze Startskript stehen.
autocutsel -selection CLIPBOARD -fork > /dev/null 2>&1 &
autocutsel -selection PRIMARY -fork > /dev/null 2>&1 &

# --- Tastaturlayout -----------------------------------------------------
#
# **Vor** Selkies, nicht danach. Selkies schickt Zeichen und übersetzt sie im
# Container über die Belegung des X-Servers zurück in Tasten; Xvfb startet mit
# `us`, und darauf verschwinden Umlaute ohne Meldung (gemessen 2026-09-28).
# Bei 1.6.2 setzte der Agent das Layout nachträglich und musste Selkies dafür
# neu starten; der Agent gibt es jetzt beim Anlegen mit.
if [ -n "${OTA_KEYBOARD_LAYOUT:-}" ]; then
  setxkbmap -layout "$OTA_KEYBOARD_LAYOUT" \
    ${OTA_KEYBOARD_VARIANT:+-variant "$OTA_KEYBOARD_VARIANT"} 2>/dev/null || true
fi

# --- Selkies -------------------------------------------------------------
#
# Selkies 2.0 aus OTAs Fork, über WebSockets: Bild, Ton, Eingaben und
# Zwischenablage gehen über Port 8080 durch Traefik. Kein UDP, kein TURN.
# Was eingestellt ist und warum, steht in selkies-starten.sh — dasselbe Skript
# startet auch die Bildschirme der einzelnen Anwendungen.
"$STARTUPDIR/selkies-starten.sh" "$PORT" > /tmp/selkies.log 2>&1 &
SELKIES_PID=$!

# --- Das Startskript des abgeleiteten Images -----------------------------
trap 'kill $SELKIES_PID $XVFB_PID 2>/dev/null; exit 0' TERM INT

if [ -x "$STARTUPDIR/custom_startup.sh" ]; then
  while kill -0 "$XVFB_PID" 2>/dev/null; do
    "$STARTUPDIR/custom_startup.sh" || true
    sleep 3
  done
else
  wait "$XVFB_PID"
fi

wait "$XVFB_PID" 2>/dev/null || true
