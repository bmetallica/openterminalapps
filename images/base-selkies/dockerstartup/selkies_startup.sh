#!/usr/bin/env bash
# Startet die Sitzung mit Selkies: Xvfb, XFCE, dann der Strom.
#
# **Der Vertrag mit OTA ist derselbe wie bei KasmVNC**, nur an einem anderen
# Port. Hier steht, worauf sich der Agent verlässt:
#
#   * Der Dienst nimmt auf **8080** Verbindungen an (KasmVNC: 6901). Daran
#     erkennt der Agent, dass die Session bereit ist.
#   * Er verlangt Basic-Auth mit `VNC_USER` und `VNC_PW`. Traefik setzt den
#     Header davor — genau wie beim bisherigen Weg. Der Name der Variablen
#     bleibt `VNC_*`, obwohl hier kein VNC mehr läuft: Der Agent reicht sie
#     unverändert durch, und ein zweiter Satz Namen für dieselbe Sache wäre
#     eine Fehlerquelle ohne Gewinn.
#   * **Der Medienstrom geht nicht durch Traefik.** Das ist der eigentliche
#     Unterschied: Die Weboberfläche und die Signalisierung laufen wie bisher
#     über 8080, das Bild selbst aber als WebRTC über UDP. Vermittelt wird
#     über den TURN-Dienst aus dem Stack; `SELKIES_TURN_HOST` und
#     `SELKIES_TURN_SHARED_SECRET` sagen, wohin und womit. Der Container
#     selbst veröffentlicht keinen einzigen Port.
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

export HOME=${HOME:-/home/kasm-user}
export DISPLAY=${DISPLAY:-:1}
export XAUTHORITY=$HOME/.Xauthority
STARTUPDIR=${STARTUPDIR:-/dockerstartup}
DISPLAY_NUM=${DISPLAY#:}
VNC_RESOLUTION=${VNC_RESOLUTION:-1280x720}
BREITE=${VNC_RESOLUTION%x*}
HOEHE=${VNC_RESOLUTION#*x}
PORT=${SELKIES_PORT:-8080}

if [ -z "${VNC_PW:-}" ]; then
  echo "VNC_PW fehlt — ohne Passwort wird nicht gestartet." >&2
  exit 1
fi

mkdir -p "$HOME/Desktop" "$HOME/.cache"

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
startxfce4 > /tmp/xfce.log 2>&1 &

# Siehe dieselbe Stelle in vnc_startup.sh: `-fork` verzweigt hier nicht, und
# ohne `&` bleibt das ganze Startskript stehen.
autocutsel -selection CLIPBOARD -fork > /dev/null 2>&1 &
autocutsel -selection PRIMARY -fork > /dev/null 2>&1 &

# --- Selkies -------------------------------------------------------------
#
# `--enable_https=false`, weil Traefik davor TLS beendet. `--enable_resize`,
# damit der ferne Bildschirm mit dem Fenster wächst — dasselbe Verhalten wie
# `resize=remote` beim bisherigen Weg.
#
# Der GStreamer-Unterbau liegt unter /opt/gstreamer und wird über `gst-env` in
# die Umgebung geholt; das System-GStreamer bleibt unangetastet.
#
# **Der Medienweg.** Bild und Ton laufen als WebRTC über UDP und damit nicht
# durch Traefik. Browser und Container haben keinen gemeinsamen Weg — die
# Sitzung liegt in einem internen Docker-Netz —, also vermittelt ein
# TURN-Server. Der läuft **nicht hier drin**, sondern als Dienst `turn` im
# Stack, auf dem Netz des Hosts.
#
# Dass er dort und nicht hier läuft, ist die Lehre aus dem ersten Anlauf:
# Ein TURN hinter einer Docker-Bridge meldet die Adresse des Hosts als Relay
# und verschickt die Pakete mit der Container-Adresse als Absender. Der
# Browser verwirft sie und zeigt bis in alle Ewigkeit "Waiting for stream";
# hier drin stand nur "Fatal SSL error" beim DTLS-Handschlag. Nachmessen mit
# `scripts/pruef-turn.py`.
#
# `SELKIES_TURN_SHARED_SECRET` ist dasselbe Geheimnis, das der TURN-Dienst
# kennt. Selkies rechnet sich daraus für jede Sitzung ein kurzlebiges
# Anmeldepaar aus und gibt es dem Browser mit — das Sitzungspasswort bleibt,
# wo es hingehört.
# shellcheck disable=SC1091
. /opt/gstreamer/gst-env

export SELKIES_ENABLE_BASIC_AUTH=true
export SELKIES_BASIC_AUTH_USER="${VNC_USER:-kasm_user}"
export SELKIES_BASIC_AUTH_PASSWORD="$VNC_PW"

TURN_PORT=${SELKIES_TURN_PORT:-3478}
if [ -z "${SELKIES_TURN_HOST:-}" ] || [ -z "${SELKIES_TURN_SHARED_SECRET:-}" ]; then
  echo "SELKIES_TURN_HOST/-SHARED_SECRET fehlt — ohne TURN bleibt der Strom schwarz" >&2
fi

selkies-gstreamer \
  --addr=0.0.0.0 \
  --port="$PORT" \
  --enable_https=false \
  --web_root=/opt/gst-web \
  --enable_resize=true \
  --turn_host="${SELKIES_TURN_HOST:-}" \
  --turn_port="$TURN_PORT" \
  --turn_protocol="${SELKIES_TURN_PROTOCOL:-udp}" \
  --turn_shared_secret="${SELKIES_TURN_SHARED_SECRET:-}" \
  --stun_host="${SELKIES_STUN_HOST:-$SELKIES_TURN_HOST}" \
  --stun_port="${SELKIES_STUN_PORT:-$TURN_PORT}" \
  --encoder="${SELKIES_ENCODER:-x264enc}" \
  --framerate="${SELKIES_FRAMERATE:-30}" \
  > /tmp/selkies.log 2>&1 &
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
