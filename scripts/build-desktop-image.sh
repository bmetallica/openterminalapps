#!/usr/bin/env bash
# Baut OTAs Basisimage und prüft es gegen den Vertrag mit dem Agent.
#
#   scripts/build-desktop-image.sh              baut ota/base-desktop:1
#   scripts/build-desktop-image.sh --pruefen    baut und prüft danach
#   scripts/build-desktop-image.sh --nur-pruefen
#
# Dies ist das **Vorgabe-Image**: Debian 13 + XFCE + Selkies, ohne KasmVNC.
# Das ältere `images/base-xfce` (Ubuntu + KasmVNC) bleibt daneben bestehen,
# solange Arbeitsplätze darauf laufen; sein Skript ist `build-base-image.sh`.
#
# Die Prüfung ist keine Formsache. Sie misst die Punkte, an denen dieser Weg
# in der Entwicklung tatsächlich gescheitert ist — jeder Fall hier stand
# einmal für einen halben Tag Fehlersuche.

set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TAG="${OTA_DESKTOP_TAG:-ota/base-desktop:1}"
CN="ota-desktop-pruef-$$"
PW="pruef-geheim-2026"

pass=0; fail=0
ok()  { printf '  \033[32m✓\033[0m %s\n' "$1"; pass=$((pass+1)); }
bad() { printf '  \033[31m✗\033[0m %s\n' "$1" >&2; fail=$((fail+1)); }
# Ein Befehl im Container, als Nutzer. `bash -lc`, weil die Skripte des Images
# es auch so tun.
imc() { docker exec "$CN" bash -lc "$1" 2>/dev/null; }

# Den Firmenproxy an den Build durchreichen, falls einer gesetzt ist.
#
# Docker kennt diese Namen vorab: Sie wirken in jedem `RUN`, ohne dass im
# Dockerfile ein `ARG` steht, und landen **nicht** im fertigen Image. Ohne sie
# scheitert hinter einem Firmenproxy schon das erste `apt-get update`, und im
# Protokoll steht ein Zeitablauf statt eines Grundes.
#
# Gelesen wird aus `deploy/.env`, und zwar von hier aus. Frueher stand an
# dieser Stelle der Hinweis, man moege die Datei vorher selbst einlesen — ein
# Schritt, den man genau einmal vergisst, und dann scheitert der Bau hinter
# dem Proxy, ohne dass der Grund irgendwo steht. Was in der Umgebung schon
# gesetzt ist, gewinnt.
if [ -f "$ROOT/deploy/.env" ]; then
  # Nur die drei Proxy-Zeilen, nicht die ganze Datei: Dort stehen Geheimnisse,
  # und die haben in der Umgebung eines Bauskripts nichts verloren.
  for zeile in $(grep -E '^OTA_(HTTP|HTTPS|NO)_PROXY=' "$ROOT/deploy/.env" 2>/dev/null); do
    name="${zeile%%=*}"; wert="${zeile#*=}"
    [ -z "$wert" ] && continue
    eval ": \${$name:=\$wert}" && export "$name"
  done
fi

proxy_argumente() {
  for paar in "http_proxy:${OTA_HTTP_PROXY:-${http_proxy:-}}" \
              "https_proxy:${OTA_HTTPS_PROXY:-${https_proxy:-}}" \
              "no_proxy:${OTA_NO_PROXY:-${no_proxy:-}}"; do
    name="${paar%%:*}"; wert="${paar#*:}"
    [ -z "$wert" ] && continue
    printf -- '--build-arg %s=%s --build-arg %s=%s ' \
      "$name" "$wert" "$(echo "$name" | tr a-z A-Z)" "$wert"
  done
}

bauen() {
  echo "Baue $TAG …"
  docker build $(proxy_argumente) -t "$TAG" "$ROOT/images/base-desktop" || return 1
  # `:test` bleibt als Zweitname, damit die Testvorlagen weiterlaufen.
  docker tag "$TAG" ota/base-desktop:test
  echo
  docker images --format '{{.Repository}}:{{.Tag}}  {{.Size}}' | grep -F "ota/base-desktop"
  echo
}

pruefen() {
  echo "Prüfe $TAG"
  echo
  docker rm -f "$CN" >/dev/null 2>&1
  docker run -d --name "$CN" --shm-size=512m \
    -e VNC_PW="$PW" -e VNC_USER=ota -e VNC_RESOLUTION=1280x720 \
    -e OTA_LOGIN=pruefnutzer \
    "$TAG" >/dev/null || { bad "Der Container startete nicht"; return 1; }

  # --- Der Vertrag mit dem Agent ----------------------------------------
  #
  # Genau die Prüfung, die der Agent macht: Antwortet Port 8080?
  BEREIT=0
  for i in $(seq 1 90); do
    imc '(exec 3<>/dev/tcp/127.0.0.1/8080)' && { BEREIT=1; break; }
    sleep 1
  done
  [ "$BEREIT" = "1" ] && ok "Selkies nimmt auf 8080 an (nach ${i}s)" \
                      || bad "Selkies war nach 90s nicht erreichbar"
  if [ "$BEREIT" != "1" ]; then
    docker logs "$CN" --tail 20 >&2; docker rm -f "$CN" >/dev/null 2>&1; return 1
  fi

  # Traefik setzt den Header davor; ohne ihn darf nichts herauskommen.
  [ "$(imc "curl -s -o /dev/null -w %{http_code} http://127.0.0.1:8080/")" = "401" ] \
    && ok "Ohne Anmeldung: 401" || bad "Ohne Anmeldung kam nicht 401"
  [ "$(imc "curl -s -o /dev/null -w %{http_code} -u ota:$PW http://127.0.0.1:8080/")" = "200" ] \
    && ok "Mit Anmeldung: 200" || bad "Mit Anmeldung kam nicht 200"

  # --- Kein Kasm ---------------------------------------------------------
  [ -z "$(imc 'ls /usr/bin/kasmvnc* /usr/bin/Xvnc 2>/dev/null')" ] \
    && ok "Kein KasmVNC im Image" || bad "Es liegt noch KasmVNC im Image"

  # --- Der Mensch --------------------------------------------------------
  [ "$(imc 'id -un')" = "ota" ] && ok "Konto heisst ota" || bad "Konto heisst nicht ota"
  [ "$(imc 'id -u')" = "1000" ] && ok "Kennung ist 1000" || bad "Kennung ist nicht 1000"
  [ "$(imc 'echo $HOME')" = "/home/ota" ] && ok "Zuhause ist /home/ota" \
    || bad "Zuhause ist nicht /home/ota"
  # Der Agent liest genau diesen Wert aus dem Image (_heimat_aus_env).
  [ "$(docker image inspect "$TAG" --format '{{range .Config.Env}}{{if eq (index (split . "=") 0) "HOME"}}{{index (split . "=") 1}}{{end}}{{end}}')" = "/home/ota" ] \
    && ok "Das Image nennt sein Zuhause nach aussen" \
    || bad "HOME fehlt in der Image-Konfiguration — der Agent mountet dann falsch"
  [ "$(imc 'readlink /home/pruefnutzer')" = "/home/ota" ] \
    && ok "Verweis unter dem Anmeldenamen" || bad "Der Verweis fehlt"

  # --- Der Mauszeiger ----------------------------------------------------
  #
  # Ohne XCURSOR_SIZE leitet libXcursor die Groesse aus der Bildschirmgroesse
  # ab (min/48). Der Rahmen des Xvfb ist 3840x2160 gross und waechst mit dem
  # Browserfenster — ein Zeiger, der danach geladen wird, kaeme dreimal so
  # gross heraus und bliebe es.
  GROESSE=$(imc 'python3 -c "
import ctypes
x=ctypes.CDLL(\"libX11.so.6\"); c=ctypes.CDLL(\"libXcursor.so.1\")
x.XOpenDisplay.restype=ctypes.c_void_p
c.XcursorGetDefaultSize.argtypes=[ctypes.c_void_p]; c.XcursorGetDefaultSize.restype=ctypes.c_int
print(c.XcursorGetDefaultSize(x.XOpenDisplay(b\":1\")))"')
[ "$GROESSE" = "24" ] && ok "Zeigergroesse festgenagelt (24)" \
                      || bad "Zeigergroesse haengt an der Bildschirmgroesse ($GROESSE)"

  # --- GStreamer ---------------------------------------------------------
  imc 'gst-inspect-1.0 webrtcbin >/dev/null' && ok "webrtcbin vorhanden" \
    || bad "webrtcbin fehlt — ohne ihn kommt keine Verbindung zustande"
  imc 'gst-inspect-1.0 x264enc >/dev/null' && ok "x264enc vorhanden" \
    || bad "x264enc fehlt — ohne ihn gibt es kein Bild"
  imc 'python3 -c "import gi; gi.require_version(\"GstWebRTC\",\"1.0\"); from gi.repository import GstWebRTC"' \
    && ok "GStreamer-Bindungen für Python" \
    || bad "GstWebRTC fehlt in Python — daran ist der Wechsel auf Debian zuerst gescheitert"

  # --- Werkzeuge, an denen die Zwischenablage haengt ---------------------
  FEHLT=""
  for w in xsel xclip autocutsel clipnotify xdotool wmctrl xprop; do
    imc "command -v $w >/dev/null" || FEHLT="$FEHLT $w"
  done
  [ -z "$FEHLT" ] && ok "Alle Werkzeuge da (Zwischenablage, Fenster)" \
                  || bad "Es fehlen:$FEHLT"

  # `cvt` liefert weder Ubuntu noch Debian; das Image bringt eine eigene
  # Rechnung mit, geprueft am Referenzwert fuer 1920x1080.
  imc "cvt -r 1920 1080 60 | grep -q '138.50  1920 1968 2000 2080'" \
    && ok "cvt rechnet richtig" || bad "cvt liefert die falsche Modeline"

  # --- Was der Browser bekommt ------------------------------------------
  TURN=$(imc "curl -s -u ota:$PW http://127.0.0.1:8080/turn")
  case "$TURN" in
    *stun.l.google.com*) bad "Die TURN-Auskunft nennt Googles STUN-Server" ;;
    *) ok "Kein fremder STUN in der TURN-Auskunft" ;;
  esac
  [ -z "$(imc "grep -o '<v-btn class=\"fab-container\"' /opt/gst-web/index.html")" ] \
    && ok "Selkies' eigener Leistenknopf ist entfernt" \
    || bad "Der Leistenknopf liegt wieder unter OTAs Griff"

  docker rm -f "$CN" >/dev/null 2>&1

  # --- Betriebsart "Einzelne App" ---------------------------------------
  echo
  echo "Prüfe die Betriebsart „Einzelne App“"
  docker rm -f "$CN" >/dev/null 2>&1
  docker run -d --name "$CN" --shm-size=512m \
    -e VNC_PW="$PW" -e VNC_USER=ota -e OTA_MODE=single_app \
    "$TAG" >/dev/null
  for i in $(seq 1 60); do imc '[ -e /tmp/.X11-unix/X1 ]' && break; sleep 1; done
  imc 'DISPLAY=:1 xfce4-terminal & sleep 6' >/dev/null 2>&1
  sleep 4
  LAEUFT=$(imc 'ps -eo args --no-headers | awk "{print \$1}" | xargs -n1 basename 2>/dev/null | sort -u | tr "\n" " "')
  case "$LAEUFT" in
    *xfce4-panel*|*xfdesktop*) bad "Der Schreibtisch läuft mit, obwohl nur eine Anwendung gemeint ist" ;;
    *xfwm4*) ok "Nur der Fenstermanager, kein Schreibtisch" ;;
    *) bad "Der Fenstermanager läuft nicht — die Anwendung bekäme keinen Rahmen" ;;
  esac
  ZUSTAND=$(imc 'export DISPLAY=:1 XAUTHORITY=$HOME/.Xauthority; F=$(wmctrl -l | awk "\$2 != -1" | head -1 | cut -d" " -f1); xprop -id $F _NET_WM_STATE')
  case "$ZUSTAND" in
    *FULLSCREEN*) ok "Die Anwendung steht formatfüllend" ;;
    *) bad "Die Anwendung ist nicht formatfüllend ($ZUSTAND)" ;;
  esac
  docker rm -f "$CN" >/dev/null 2>&1

  echo
  echo "─────────────────────────────────────"
  printf '  bestanden: %s   fehlgeschlagen: %s\n' "$pass" "$fail"
  [ "$fail" = "0" ]
}

case "${1:-}" in
  --nur-pruefen) pruefen ;;
  --pruefen)     bauen && pruefen ;;
  *)             bauen ;;
esac
