"""Startet einzelne Anwendungen auf eigenen X-Displays im selben Container.

Das ist der Kern des Arbeitsplatz-Modells (plan.md §9.2): ein Container je
Nutzer, jede Anwendung formatfuellend auf einem eigenen Display, gestartet
erst bei Bedarf.
"""

from __future__ import annotations

import shlex

# Vorlage fuer einen zusaetzlichen KasmVNC-Server.
#
# Wichtig ist die Reihenfolge: Erst das X-Cookie anlegen, dann Xvnc starten.
# Ohne Cookie kann keine Anwendung das Display oeffnen ("Authorization
# required, but no authorization protocol specified").
START_DISPLAY = r"""
set -e
export HOME=${HOME:-/home/kasm-user}
export XAUTHORITY=$HOME/.Xauthority

DISPLAY_NUM=@DISPLAY@
PORT=@PORT@
GEOMETRY=@GEOMETRY@

if [ -e /tmp/.X11-unix/X$DISPLAY_NUM ]; then
  echo "display-exists"
  exit 0
fi

xauth add :$DISPLAY_NUM MIT-MAGIC-COOKIE-1 "$(mcookie)"

nohup /usr/bin/Xvnc :$DISPLAY_NUM \
  -depth 24 -httpd /usr/share/kasmvnc/www -sslOnly \
  -interface 0.0.0.0 -websocketPort $PORT -rfbport $((5900 + DISPLAY_NUM)) \
  -geometry $GEOMETRY -desktop "@TITLE@" \
  -cert $HOME/.vnc/self.pem -key $HOME/.vnc/self.pem \
  -auth $XAUTHORITY -rfbauth $HOME/.vnc/passwd \
  -KasmPasswordFile $HOME/.kasmpasswd \
  -SendCutText 1 -AcceptCutText 1 -SendPrimary @SEND_PRIMARY@ \
  -DLP_ClipDelay 0 \
  -DLP_ClipTypes chromium/x-web-custom-data,text/html,image/png \
  -FrameRate 24 -DynamicQualityMin 4 -DynamicQualityMax 7 \
  -Log '*:stdout:30' \
  > /tmp/ota-display-$DISPLAY_NUM.log 2>&1 &

for i in $(seq 1 40); do
  [ -e /tmp/.X11-unix/X$DISPLAY_NUM ] && break
  sleep 0.25
done
[ -e /tmp/.X11-unix/X$DISPLAY_NUM ] || { echo "display-failed"; exit 1; }

# Ein schlanker Fenstermanager je Display. Ohne ihn hat die Anwendung keine
# Dekoration und laesst sich nicht maximieren; die volle XFCE-Sitzung mit
# Desktop und Panel braucht eine formatfuellende Anwendung dagegen nicht.
DISPLAY=:$DISPLAY_NUM nohup xfwm4 --compositor=off \
  > /tmp/ota-wm-$DISPLAY_NUM.log 2>&1 &
sleep 1

echo "display-ready"
"""

# Dasselbe fuer Selkies: ein eigener Bildschirm je Anwendung, aber mit Xvfb
# und einer eigenen Selkies-Instanz statt eines Xvnc.
#
# **Warum ueberhaupt eine zweite Instanz.** Selkies uebertraegt genau ein
# Display. Mehrere Anwendungen nebeneinander auf einem Bildschirm waeren ein
# anderes Arbeitsplatzmodell als das, was OTA bietet — hier bekommt jede
# Anwendung ihren eigenen Bildschirm, formatfuellend, umschaltbar in der
# Leiste. Also laeuft je Anwendung ein eigener Strom auf einem eigenen Port,
# und Traefik hat dafuer schon eine Route.
#
# Die Kennungen der Prozesse werden abgelegt. Ein Abgleich ueber den Namen
# scheitert hier: "pkill -f" durchsucht ganze Kommandozeilen und faende dieses
# Skript, dessen Text die gesuchten Namen enthaelt.
START_SELKIES_DISPLAY = r"""
set -e
export HOME=${HOME:-/home/ota}
export XAUTHORITY=$HOME/.Xauthority
DISPLAY_NUM=@DISPLAY@
PORT=@PORT@
GEOMETRY=@GEOMETRY@
BREITE=${GEOMETRY%%x*}
HOEHE=${GEOMETRY##*x}

if [ -e /tmp/.X11-unix/X$DISPLAY_NUM ]; then
  echo "display-exists"
  exit 0
fi

xauth add :$DISPLAY_NUM MIT-MAGIC-COOKIE-1 "$(mcookie)"

# Grosszuegiger Rahmen und nicht die Startgroesse: Selkies passt die Aufloesung
# an das Browserfenster an, und ein Xvfb laesst sich nur innerhalb dessen
# vergroessern, was er beim Start bekommen hat.
nohup Xvfb :$DISPLAY_NUM -screen 0 3840x2160x24   -dpms -s 0 -ac -noreset -nolisten tcp   +extension COMPOSITE +extension DAMAGE +extension RANDR +extension RENDER   +extension MIT-SHM +extension XFIXES +extension XTEST   > /tmp/ota-xvfb-$DISPLAY_NUM.log 2>&1 &
echo $! > /tmp/ota-xvfb-$DISPLAY_NUM.pid

for i in $(seq 1 60); do
  [ -e /tmp/.X11-unix/X$DISPLAY_NUM ] && break
  sleep 0.5
done
if [ ! -e /tmp/.X11-unix/X$DISPLAY_NUM ]; then
  echo "display-failed"
  tail -20 /tmp/ota-xvfb-$DISPLAY_NUM.log >&2 || true
  exit 1
fi

DISPLAY=:$DISPLAY_NUM xrandr --output screen --mode "${BREITE}x${HOEHE}" 2>/dev/null || true

# Ein Fenstermanager, aber kein Schreibtisch: Eine formatfuellende Anwendung
# braucht Rahmen und Groessenverwaltung, keine Leiste. `--compositor=off`,
# weil ohne GPU jeder Bildaufbau in Software passiert und diese Rechenzeit dem
# Kodierer gehoert.
DISPLAY=:$DISPLAY_NUM nohup xfwm4 --compositor=off   > /tmp/ota-wm-$DISPLAY_NUM.log 2>&1 &
sleep 1

# Die Anmeldung ist dieselbe wie beim Hauptbildschirm — Traefik setzt denselben
# Header vor jede Route dieser Sitzung.
export SELKIES_ENABLE_BASIC_AUTH=true
export SELKIES_BASIC_AUTH_USER="${VNC_USER:-ota}"
export SELKIES_BASIC_AUTH_PASSWORD="$VNC_PW"

DISPLAY=:$DISPLAY_NUM nohup selkies-gstreamer   --addr=0.0.0.0 --port="$PORT" --enable_https=false   --web_root=/opt/gst-web --enable_resize=true   --turn_host="${SELKIES_TURN_HOST:-}"   --turn_port="${SELKIES_TURN_PORT:-3478}"   --turn_protocol="${SELKIES_TURN_PROTOCOL:-udp}"   --turn_shared_secret="${SELKIES_TURN_SHARED_SECRET:-}"   --stun_host="${SELKIES_STUN_HOST:-${SELKIES_TURN_HOST:-}}"   --stun_port="${SELKIES_STUN_PORT:-${SELKIES_TURN_PORT:-3478}}"   --encoder="${SELKIES_ENCODER:-x264enc}"   --framerate="${SELKIES_FRAMERATE:-30}"   > /tmp/ota-selkies-$DISPLAY_NUM.log 2>&1 &
echo $! > /tmp/ota-selkies-$DISPLAY_NUM.pid

for i in $(seq 1 90); do
  (echo > /dev/tcp/127.0.0.1/$PORT) 2>/dev/null && break
  sleep 0.5
done
if ! (echo > /dev/tcp/127.0.0.1/$PORT) 2>/dev/null; then
  echo "display-failed"
  tail -20 /tmp/ota-selkies-$DISPLAY_NUM.log >&2 || true
  exit 1
fi

echo "display-ready"
"""

STOP_SELKIES_DISPLAY = r"""
export HOME=${HOME:-/home/ota}
export XAUTHORITY=$HOME/.Xauthority
for was in selkies xvfb; do
  DATEI=/tmp/ota-$was-@DISPLAY@.pid
  if [ -f "$DATEI" ]; then
    PID=$(cat "$DATEI" 2>/dev/null)
    [ -n "$PID" ] && kill "$PID" 2>/dev/null || true
    rm -f "$DATEI"
  fi
done
pkill -f "xfwm4.*:@DISPLAY@" 2>/dev/null || true
rm -f /tmp/.X11-unix/X@DISPLAY@ 2>/dev/null || true
echo "display-stopped"
"""

START_APP = r"""
set -e
export HOME=${HOME:-/home/kasm-user}
export XAUTHORITY=$HOME/.Xauthority
export DISPLAY=:@DISPLAY@

# Laeuft auf diesem Display schon eine Anwendung? Ein Abgleich ueber den
# Prozessnamen scheitert hier: "pgrep -f" durchsucht ganze Kommandozeilen
# und findet dabei DIESES Skript, dessen Text den Anwendungsnamen enthaelt —
# das Skript haelt sich dann selbst fuer die laufende Anwendung.
#
# Gezaehlt werden deshalb Fenster, aber nicht alle: Die zweite Spalte von
# "wmctrl -l" ist die Arbeitsflaeche, und -1 heisst "klebt ueberall" — das
# tragen Hintergrundbild, Panels und Benachrichtigungen. Auf Display :1 laeuft
# die volle XFCE-Sitzung, dort ist immer mindestens das Hintergrundfenster
# "Desktop" da. Ohne diesen Filter meldete das Skript auf :1 stets
# "already-running" und startete die Anwendung nie — gemessen am 2026-08-27:
# VS Code liess sich im Arbeitsplatz nicht oeffnen, der Bildschirm blieb leer.
if wmctrl -l 2>/dev/null | awk '$2 != -1' | grep -q .; then
  echo "already-running"
  exit 0
fi

# Die Anwendung bekommt einen hohen oom_score_adj, die Infrastruktur nicht.
#
# Warum: Alle Anwendungen eines Nutzers teilen sich ein Speicherlimit. Reisst
# eine davon es, sucht der Kernel ein Opfer — und ohne Zutun trifft es gern
# den groessten Prozess. Das kann Xvnc sein oder die Aufsicht des Containers;
# dann stirbt der ganze Arbeitsplatz an einer einzigen Anwendung.
#
# Der Wert wird in einer Zwischen-Shell gesetzt, die sich danach durch die
# Anwendung ersetzt (`exec`). So erben ihn auch alle Kindprozesse — bei
# Electron sind das ein Dutzend. Erhoehen darf jeder Prozess fuer sich selbst;
# Senken braeuchte CAP_SYS_RESOURCE, und genau deshalb wird nur erhoeht.
nohup bash -c 'echo 500 > /proc/self/oom_score_adj 2>/dev/null; exec @COMMAND@' \
  > /tmp/ota-app-@SLUG@.log 2>&1 &
echo $! > /tmp/ota-app-@SLUG@.pid

for i in $(seq 1 60); do
  if DISPLAY=:@DISPLAY@ wmctrl -l 2>/dev/null | awk '$2 != -1' | grep -q .; then
    break
  fi
  sleep 0.5
done

# Fenster formatfuellend setzen, damit der Stream nicht an den Raendern
# den leeren Desktop zeigt.
WIN=$(DISPLAY=:@DISPLAY@ wmctrl -l 2>/dev/null | awk '$2 != -1' | head -1 | cut -d' ' -f1)
if [ -n "$WIN" ]; then
  DISPLAY=:@DISPLAY@ wmctrl -i -r "$WIN" -b add,maximized_vert,maximized_horz 2>/dev/null || true
fi

# --- Die Aufsicht ueber diese Anwendung ---------------------------------
#
# Sie haelt drei Dinge gerade, solange es das Display gibt:
#
#   * **geschlossen** — die Anwendung wird neu gestartet. Wer sie ueber ihr
#     eigenes Fensterkreuz schliesst, saehe sonst fuer den Rest der Sitzung
#     eine leere Flaeche: Auf diesem Display laeuft nichts als sie, und es
#     gibt keine Leiste, ueber die man sie zurueckholt.
#   * **minimiert** — sie kommt wieder hoch. Aus demselben Grund.
#   * **nicht mehr formatfuellend** — sie wird es wieder.
#
# Beendet wird die Aufsicht nicht eigens: Sie laeuft, solange der X-Socket
# existiert, und der verschwindet beim Abbau des Displays (stop_script bzw.
# stop_selkies_script). Wer die Anwendung ueber OTA beendet, beendet damit
# auch ihren Bildschirm — und die Aufsicht startet sie nicht wieder.
#
# Das Skript wird in eine Datei geschrieben statt in ein `bash -c`: Der
# Startbefehl ist bereits fuer die Shell gequotet, und ihn ein zweites Mal
# durch eine Zeichenkette zu schleusen ginge bei jedem Anfuehrungszeichen
# schief. Im Heredoc mit gequotetem Begrenzer bleibt er unangetastet, bis die
# Aufsicht ihn ausfuehrt.
cat > /tmp/ota-aufsicht-@SLUG@.sh <<'AUFSICHT'
export XAUTHORITY=$HOME/.Xauthority
while [ -e /tmp/.X11-unix/X@DISPLAY@ ]; do
  sleep 2

  PID=$(cat /tmp/ota-app-@SLUG@.pid 2>/dev/null)
  if [ -z "$PID" ] || ! kill -0 "$PID" 2>/dev/null; then
    nohup bash -c 'echo 500 > /proc/self/oom_score_adj 2>/dev/null; exec @COMMAND@' \
      > /tmp/ota-app-@SLUG@.log 2>&1 &
    echo $! > /tmp/ota-app-@SLUG@.pid
    sleep 3
    continue
  fi

  FENSTER=$(wmctrl -l 2>/dev/null | awk '$2 != -1' | head -1 | cut -d' ' -f1)
  [ -z "$FENSTER" ] && continue

  # Ohne `xprop` liesse sich der Zustand nicht lesen, und die Aufsicht wuerde
  # alle zwei Sekunden blind maximieren. Dann lieber nichts tun.
  command -v xprop > /dev/null 2>&1 || continue
  ZUSTAND=$(xprop -id "$FENSTER" _NET_WM_STATE 2>/dev/null || true)
  case "$ZUSTAND" in
    *_NET_WM_STATE_HIDDEN*) wmctrl -i -a "$FENSTER" 2>/dev/null || true ;;
  esac
  case "$ZUSTAND" in
    *_NET_WM_STATE_MAXIMIZED_VERT*) : ;;
    *) wmctrl -i -r "$FENSTER" -b add,maximized_vert,maximized_horz 2>/dev/null || true ;;
  esac
done
AUFSICHT
chmod +x /tmp/ota-aufsicht-@SLUG@.sh
DISPLAY=:@DISPLAY@ nohup bash /tmp/ota-aufsicht-@SLUG@.sh \
  > /tmp/ota-aufsicht-@DISPLAY@.log 2>&1 &

echo "app-started"
"""

STOP_DISPLAY = r"""
export HOME=${HOME:-/home/kasm-user}
export XAUTHORITY=$HOME/.Xauthority
pkill -f "Xvnc :@DISPLAY@" 2>/dev/null || true
pkill -f "xfwm4.*:@DISPLAY@" 2>/dev/null || true
rm -f /tmp/.X11-unix/X@DISPLAY@ 2>/dev/null || true
echo "display-stopped"
"""


def _fill(template: str, **values: str | int) -> str:
    """Setzt @NAME@-Platzhalter ein.

    Bewusst nicht str.format(): Das Skript ist Bash und steckt voller
    geschweifter Klammern, die format() als Platzhalter missversteht.
    """
    out = template
    for key, value in values.items():
        out = out.replace(f"@{key.upper()}@", str(value))
    return out


def display_script(display: int, port: int, geometry: str, title: str,
                   send_primary: bool, engine: str = "kasmvnc") -> list[str]:
    """Macht einen Bildschirm auf — je nach Maschine mit Xvnc oder mit Xvfb.

    Beide Wege sind gleich gebaut: ein Bildschirm je Anwendung, ein eigener
    Port, formatfuellend. Nur was darauf lauscht, ist ein anderes Programm.
    """
    if engine == "selkies":
        return ["bash", "-lc", _fill(
            START_SELKIES_DISPLAY,
            display=display, port=port, geometry=geometry,
        )]
    return ["bash", "-lc", _fill(
        START_DISPLAY,
        display=display, port=port, geometry=geometry, title=title,
        send_primary=1 if send_primary else 0,
    )]


def app_script(display: int, slug: str, command: str) -> list[str]:
    # Der Startbefehl kommt aus der Vorlage und wird vom Administrator
    # gepflegt. Er wird trotzdem zerlegt und wieder zusammengesetzt, damit
    # keine Steuerzeichen in die Shell durchrutschen.
    parts = shlex.split(command)
    safe = " ".join(shlex.quote(p) for p in parts)
    return ["bash", "-lc", _fill(
        START_APP,
        display=display, slug=shlex.quote(slug).strip("'"),
        command=safe,
    )]


def stop_selkies_script(display: int) -> list[str]:
    """Baut einen Selkies-Bildschirm ab: erst der Strom, dann der X-Server."""
    return ["bash", "-lc", _fill(STOP_SELKIES_DISPLAY, display=display)]


def stop_script(display: int) -> list[str]:
    return ["bash", "-lc", _fill(STOP_DISPLAY, display=display)]
