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

# --- Selkies -------------------------------------------------------------
#
# `--enable_https=false`, weil Traefik davor TLS beendet. `--enable_resize`,
# damit der ferne Bildschirm mit dem Fenster wächst — dasselbe Verhalten wie
# `resize=remote` beim bisherigen Weg.
#
# GStreamer kommt aus der Distribution (Debian 13 liefert 1.26) und nicht mehr
# aus einem vorgebauten Bündel. Deshalb ist hier auch nichts mehr in die
# Umgebung zu holen: Der Versuch mit dem Ubuntu-Bündel scheiterte daran, dass
# dessen `gi/overrides` für Python 3.12 übersetzt ist und Debian 3.13 hat.
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
