#!/usr/bin/env bash
# Startet die Sitzung: X mit KasmVNC auf :1, XFCE darin, danach das
# Startskript des abgeleiteten Images.
#
# **Der Vertrag mit OTA** — hier steht, worauf sich der Agent verlässt:
#
#   * KasmVNC nimmt auf 6901 Verbindungen an. Daran erkennt der Agent, dass
#     die Session bereit ist (`_wait_ready`, /dev/tcp/127.0.0.1/6901).
#   * `$HOME/.vnc/self.pem` und `$HOME/.vnc/passwd` und `$HOME/.kasmpasswd`
#     liegen bereit. Weitere Displays startet der Agent selbst und greift
#     genau auf diese drei Dateien zurück (apps.py, START_DISPLAY).
#   * `/dockerstartup/custom_startup.sh` wird ausgeführt und **neu gestartet,
#     wenn es sich beendet**. Ein Arbeitsplatz überdeckt es mit einem Skript,
#     das nur wartet; ein Einzelanwendungs-Image legt dort seine Anwendung ab.
#   * Das Passwort kommt aus `VNC_PW`, zusätzliche Schalter aus `VNCOPTIONS`.
#
# Wer hier etwas ändert, ändert es für jeden Arbeitsplatz. Die drei Punkte
# oben sind deshalb keine Bequemlichkeit, sondern die Schnittstelle.

set -e

export HOME=${HOME:-/home/kasm-user}
export DISPLAY=${DISPLAY:-:1}
export XAUTHORITY=$HOME/.Xauthority
STARTUPDIR=${STARTUPDIR:-/dockerstartup}
DISPLAY_NUM=${DISPLAY#:}
VNC_PORT=${VNC_PORT:-5901}
VNC_WEB_PORT=${VNC_WEB_PORT:-6901}
VNC_RESOLUTION=${VNC_RESOLUTION:-1280x720}
VNC_COL_DEPTH=${VNC_COL_DEPTH:-24}

mkdir -p "$HOME/.vnc" "$HOME/Desktop"

# --- Passwort ------------------------------------------------------------
#
# Ohne VNC_PW gäbe es einen Bildschirm ohne Schloss. Das ist kein sinnvoller
# Rückfall: Lieber gar nicht starten als offen starten.
if [ -z "${VNC_PW:-}" ]; then
  echo "VNC_PW fehlt — ohne Passwort wird nicht gestartet." >&2
  exit 1
fi
VNC_VIEW_ONLY_PW=${VNC_VIEW_ONLY_PW:-$(head -c 18 /dev/urandom | base64 | tr -d '/+=')}

# Das Passwort landet in `.kasmpasswd`, und der Name darin ist **kasm_user**
# mit Unterstrich. Das ist keine Schreibweise, sondern die Schnittstelle: OTA
# setzt vor dem Stream einen Basic-Auth-Header mit genau diesem Namen
# (`vnc_user` im Agent, `_traefik_labels` in der API). Mit `kasm-user` stünde
# der Bildschirm da und fragte nach einem Passwort, das niemand kennt.
#
# Eine `.vnc/passwd` im alten RFB-Format wird bewusst **nicht** angelegt. Der
# Agent gibt sie beim Start weiterer Displays an (`-rfbauth`), aber KasmVNC
# nimmt eine fehlende Datei hin, solange `-KasmPasswordFile` gesetzt ist —
# gemessen, nicht vermutet. Und ein Werkzeug, das dieses Format schreibt,
# bringt KasmVNC gar nicht mehr mit.
rm -f "$HOME/.kasmpasswd"
printf '%s\n%s\n\n' "$VNC_PW" "$VNC_PW" | kasmvncpasswd -u kasm_user -wo "$HOME/.kasmpasswd"
printf '%s\n%s\n\n' "$VNC_VIEW_ONLY_PW" "$VNC_VIEW_ONLY_PW" | kasmvncpasswd -u kasm_viewer -r "$HOME/.kasmpasswd"
chmod 600 "$HOME/.kasmpasswd"

# --- Zertifikat ----------------------------------------------------------
#
# Selbst ausgestellt und im Zuhause abgelegt. Nach aussen ist es nie
# sichtbar: Vor dem Container steht Traefik mit dem richtigen Zertifikat.
# Es liegt hier, weil KasmVNC ohne TLS gar nicht erst hört (-sslOnly).
if [ ! -s "$HOME/.vnc/self.pem" ]; then
  # Schlüssel und Zertifikat in **eine** Datei — genau das erwarten die
  # Aufrufe -cert und -key, hier wie im Agent (apps.py).
  openssl req -x509 -nodes -newkey rsa:2048 -days 3650 \
    -subj "/C=DE/O=OpenTerminalApps/CN=$(hostname)" \
    -keyout "$HOME/.vnc/self.pem" -out "$HOME/.vnc/self.pem" 2>/dev/null
  chmod 600 "$HOME/.vnc/self.pem"
fi

# --- Reste eines harten Endes wegräumen ----------------------------------
#
# Das Zuhause überlebt den Container. Wurde der vorige hart beendet, liegen
# dort noch eine PID-Datei und im /tmp ein Sperrfile — Xvnc weigert sich dann
# mit "server already running". Genau daran ist ein Neustart nach `docker rm
# -f` schon gescheitert.
rm -f "$HOME/.vnc/"*.pid "$HOME/.vnc/"*.log 2>/dev/null || true
rm -f "/tmp/.X${DISPLAY_NUM}-lock" "/tmp/.X11-unix/X${DISPLAY_NUM}" 2>/dev/null || true

# Das X-Cookie zuerst — ohne es kann keine Anwendung das Display öffnen.
touch "$XAUTHORITY"
xauth add "$DISPLAY" MIT-MAGIC-COOKIE-1 "$(mcookie)" 2>/dev/null || true

# --- Xvnc ----------------------------------------------------------------
#
# VNCOPTIONS reicht OTA durch (Bandbreite, Qualität, DLP_ClipDelay). Es ist
# absichtlich nicht in Anführungszeichen: Es sind mehrere Schalter.
# shellcheck disable=SC2086
/usr/bin/Xvnc "$DISPLAY" \
  -depth "$VNC_COL_DEPTH" -geometry "$VNC_RESOLUTION" \
  -httpd /usr/share/kasmvnc/www -sslOnly \
  -interface 0.0.0.0 -websocketPort "$VNC_WEB_PORT" -rfbport "$VNC_PORT" \
  -desktop "OpenTerminalApps" \
  -cert "$HOME/.vnc/self.pem" -key "$HOME/.vnc/self.pem" \
  -auth "$XAUTHORITY" \
  -KasmPasswordFile "$HOME/.kasmpasswd" \
  -SendCutText 1 -AcceptCutText 1 -SendPrimary 0 \
  -FrameRate 24 -Log '*:stdout:30' \
  ${VNCOPTIONS:-} \
  > /tmp/xvnc.log 2>&1 &
XVNC_PID=$!

for i in $(seq 1 60); do
  [ -e "/tmp/.X11-unix/X${DISPLAY_NUM}" ] && break
  sleep 0.5
done
if [ ! -e "/tmp/.X11-unix/X${DISPLAY_NUM}" ]; then
  echo "Xvnc kam nicht hoch:" >&2
  tail -30 /tmp/xvnc.log >&2
  exit 1
fi

# --- XFCE ----------------------------------------------------------------
#
# Ein eigener Sitzungsbus, weil im Container keiner läuft. Ohne ihn meckern
# xfdesktop, xiccd und der Polkit-Agent bei jedem Start in die Logs — und
# Thunar öffnet keine zweite Instanz.
if [ -z "${DBUS_SESSION_BUS_ADDRESS:-}" ]; then
  eval "$(dbus-launch --sh-syntax)" 2>/dev/null || true
fi
export DBUS_SESSION_BUS_ADDRESS

xsetroot -solid '#1b2733' 2>/dev/null || true
startxfce4 > /tmp/xfce.log 2>&1 &

# `autocutsel` gleicht die beiden X-Auswahlpuffer ab. Ohne das ist die
# Zwischenablage im Container je nach Anwendung mal PRIMARY, mal CLIPBOARD —
# und beim Einfügen kommt die vorletzte Auswahl heraus.
#
# **Mit `&`, nicht nur mit `-fork`.** Der Schalter verspricht, sich in den
# Hintergrund zu verabschieden, tut es hier aber nicht: Der Prozess bleibt
# Kind der Startshell, und die wartet auf ihn. Gemessen am 2026-09-02 — das
# Startskript blieb an dieser Zeile stehen, und alles danach lief nie. Am
# auffälligsten: `custom_startup.sh`, also das, was ein abgeleitetes Image
# überhaupt starten soll. Gemerkt hat es niemand, weil der Port zu diesem
# Zeitpunkt längst offen ist und die Prüfung genau daran hing.
autocutsel -selection CLIPBOARD -fork > /dev/null 2>&1 &
autocutsel -selection PRIMARY -fork > /dev/null 2>&1 &

# --- Das Startskript des abgeleiteten Images -----------------------------
#
# Es wird beaufsichtigt: Beendet es sich, wird es neu gestartet. Ein
# Arbeitsplatz überdeckt es mit einem Skript, das nur wartet — genau darauf
# baut `WORKSPACE_STARTUP` im Agent auf.
trap 'kill $XVNC_PID 2>/dev/null; exit 0' TERM INT

if [ -x "$STARTUPDIR/custom_startup.sh" ]; then
  while kill -0 "$XVNC_PID" 2>/dev/null; do
    "$STARTUPDIR/custom_startup.sh" || true
    sleep 3
  done
else
  wait "$XVNC_PID"
fi

wait "$XVNC_PID" 2>/dev/null || true
