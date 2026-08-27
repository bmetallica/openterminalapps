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
export HOME=/home/kasm-user
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

START_APP = r"""
set -e
export HOME=/home/kasm-user
export XAUTHORITY=$HOME/.Xauthority
export DISPLAY=:@DISPLAY@

# Laeuft auf diesem Display schon ein Fenster? Das ist die verlaessliche
# Frage. Ein Abgleich ueber den Prozessnamen scheitert hier: "pgrep -f"
# durchsucht ganze Kommandozeilen und findet dabei DIESES Skript, dessen
# Text den Anwendungsnamen enthaelt — das Skript haelt sich dann selbst
# fuer die laufende Anwendung und beendet sich.
if wmctrl -l 2>/dev/null | grep -q .; then
  echo "already-running"
  exit 0
fi

nohup @COMMAND@ > /tmp/ota-app-@SLUG@.log 2>&1 &

for i in $(seq 1 60); do
  if DISPLAY=:@DISPLAY@ wmctrl -l 2>/dev/null | grep -q .; then
    break
  fi
  sleep 0.5
done

# Fenster formatfuellend setzen, damit der Stream nicht an den Raendern
# den leeren Desktop zeigt.
WIN=$(DISPLAY=:@DISPLAY@ wmctrl -l 2>/dev/null | head -1 | cut -d' ' -f1)
if [ -n "$WIN" ]; then
  DISPLAY=:@DISPLAY@ wmctrl -i -r "$WIN" -b add,maximized_vert,maximized_horz 2>/dev/null || true
fi

echo "app-started"
"""

STOP_DISPLAY = r"""
export HOME=/home/kasm-user
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
                   send_primary: bool) -> list[str]:
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


def stop_script(display: int) -> list[str]:
    return ["bash", "-lc", _fill(STOP_DISPLAY, display=display)]
