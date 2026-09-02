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
#     über 8080, das Bild selbst aber als WebRTC über UDP. Dafür läuft in
#     diesem Container ein TURN-Server; der Agent reicht dessen Ports nach
#     aussen durch, und `SELKIES_TURN_HOST` sagt dem Browser, wohin.
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

# --- TURN --------------------------------------------------------------
#
# Ohne ihn bliebe das Bild schwarz. Der Browser und dieser Container haben
# keinen gemeinsamen Weg: Session-Container liegen in einem internen
# Docker-Netz, der Browser sitzt im Firmennetz. WebRTC sammelt Kandidaten, und
# der einzige, den beide Seiten erreichen können, ist der über einen
# vermittelnden TURN-Server.
#
# `SELKIES_TURN_HOST` muss die Adresse sein, unter der der **Browser** diesen
# Container erreicht — also der Host, auf dem OTA läuft, nicht die
# Container-IP. Der Agent setzt sie beim Start.
TURN_PORT=${SELKIES_TURN_PORT:-3478}
TURN_MIN=${TURN_MIN_PORT:-65500}
TURN_MAX=${TURN_MAX_PORT:-65510}
TURN_USER=${SELKIES_TURN_USERNAME:-selkies}
TURN_PW=${SELKIES_TURN_PASSWORD:-$VNC_PW}

if [ -n "${SELKIES_TURN_HOST:-}" ]; then
  cat > /tmp/turnserver.conf <<TURNCONF
# Alles unter /tmp: Der Prozess läuft als Nutzer 1000, und coturn legt sonst
# seine PID unter /var/run ab — dort darf er nicht schreiben und beendet sich
# mit "Cannot create pid file". Aufgefallen ist das nicht am Fehler, sondern
# am schwarzen Bild: Ohne TURN kommt keine WebRTC-Verbindung zustande.
pidfile=/tmp/turnserver.pid
log-file=/tmp/turnserver-detail.log
simple-log
listening-port=${TURN_PORT}
listening-ip=0.0.0.0
relay-ip=0.0.0.0
external-ip=${SELKIES_TURN_HOST}
min-port=${TURN_MIN}
max-port=${TURN_MAX}
lt-cred-mech
user=${TURN_USER}:${TURN_PW}
realm=openterminalapps
no-tls
no-dtls
no-cli
no-multicast-peers
# Nur vermitteln, nicht als offener Relay dienen: Ohne diese Zeilen stünde im
# Firmennetz ein Server, über den sich beliebiger Verkehr umleiten liesse.
denied-peer-ip=0.0.0.0-0.255.255.255
denied-peer-ip=127.0.0.0-127.255.255.255
denied-peer-ip=169.254.0.0-169.254.255.255
allowed-peer-ip=127.0.0.1
TURNCONF
  turnserver -c /tmp/turnserver.conf > /tmp/turnserver.log 2>&1 &
  echo "TURN läuft auf ${SELKIES_TURN_HOST}:${TURN_PORT} (${TURN_MIN}-${TURN_MAX})" >&2
else
  echo "SELKIES_TURN_HOST fehlt — ohne TURN bleibt der Strom voraussichtlich schwarz" >&2
fi

# --- Selkies -------------------------------------------------------------
#
# `--enable_https=false`, weil Traefik davor TLS beendet. `--enable_resize`,
# damit der ferne Bildschirm mit dem Fenster wächst — dasselbe Verhalten wie
# `resize=remote` beim bisherigen Weg.
#
# Der GStreamer-Unterbau liegt unter /opt/gstreamer und wird über `gst-env` in
# die Umgebung geholt; das System-GStreamer bleibt unangetastet.
# shellcheck disable=SC1091
. /opt/gstreamer/gst-env

export SELKIES_ENABLE_BASIC_AUTH=true
export SELKIES_BASIC_AUTH_USER="${VNC_USER:-kasm_user}"
export SELKIES_BASIC_AUTH_PASSWORD="$VNC_PW"
export SELKIES_TURN_HOST SELKIES_TURN_PORT="$TURN_PORT"
export SELKIES_TURN_USERNAME="$TURN_USER" SELKIES_TURN_PASSWORD="$TURN_PW"
export SELKIES_TURN_PROTOCOL="${SELKIES_TURN_PROTOCOL:-udp}"

selkies-gstreamer \
  --addr=0.0.0.0 \
  --port="$PORT" \
  --enable_https=false \
  --web_root=/opt/gst-web \
  --enable_resize=true \
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
