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

# Der Datei-Vorrat der eigenen Paketquelle (Handbuch Kapitel 26). Liegt er
# da, nimmt der Bau clipnotify und die Abhängigkeiten von Selkies von dort
# statt aus dem Internet. Nur das eine Verzeichnis wird gelesen, nicht die
# ganze .env.
OTA_REPO_ROOT="${OTA_REPO_ROOT:-$(grep -E '^OTA_REPO_ROOT=' "$ROOT/deploy/.env" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '"')}"
DATEIEN="${OTA_DATEIEN:-${OTA_REPO_ROOT:-/srv/ota/repo}/aptly/public/dateien}"

vorrat_argumente() {
  if [ -d "$DATEIEN" ] && [ -n "$(ls -A "$DATEIEN" 2>/dev/null)" ]; then
    printf -- '--build-context ota-dateien=%s ' "$DATEIEN"
  fi
}

bauen() {
  echo "Baue $TAG …"
  # Selkies kommt als Paket ota-selkies ins Image (Kapitel 20). Es wird hier
  # gebaut, falls diese Fassung noch fehlt, und in die eigene Paketquelle
  # gelegt — von dort heben sich Root-Arbeitsplätze beim Fortsetzen an.
  "$ROOT/scripts/build-selkies-deb.sh" --wenn-noetig || return 1
  if docker inspect ota-repo >/dev/null 2>&1; then
    "$ROOT/scripts/build-selkies-deb.sh" --hochladen --wenn-noetig || return 1
  else
    echo "  (ota-repo läuft nicht — das Paket kommt erst mit dem nächsten 'make up' in die Paketquelle)"
  fi
  local version paket
  version="$(grep -oP '^version = "\K[^"]+' "$ROOT/third_party/selkies/pyproject.toml")-ota$(tr -d ' \n' < "$ROOT/packaging/ota-selkies/revision")"
  paket="$(mktemp -d)"
  cp "$ROOT/dist/pakete/ota-selkies_${version}_amd64.deb" "$paket/" || return 1
  if [ -n "$(vorrat_argumente)" ]; then
    echo "  Datei-Vorrat: $DATEIEN"
  else
    echo "  Ohne Datei-Vorrat — alles aus dem Internet."
  fi
  docker build $(proxy_argumente) $(vorrat_argumente) \
    --build-context ota-pakete="$paket" \
    -t "$TAG" "$ROOT/images/base-desktop" || { rm -rf "$paket"; return 1; }
  rm -rf "$paket"
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
    -e OTA_LOGIN=pruefnutzer -e OTA_KEYBOARD_LAYOUT=de \
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

  # --- Selkies 2.0 -------------------------------------------------------
  V=$(imc 'dpkg-query -W -f="\${Version}" ota-selkies')
  [ -n "$V" ] && ok "Selkies aus dem Paket ota-selkies $V" || bad "Das Paket ota-selkies ist nicht installiert"
  imc 'grep -q "websockets transport" /tmp/selkies.log' \
    && ok "Streamt über WebSockets (durch Traefik, ohne TURN)" \
    || bad "Kein WebSocket-Transport im Protokoll: $(imc 'grep -m1 starting /tmp/selkies.log')"
  # Die Wege, die 2.0 eingeschaltet mitbringt und OTA bewusst abschaltet —
  # gelesen aus der Umgebung des laufenden Prozesses, nicht aus dem Skript.
  UMG=$(imc 'P=$(pgrep -f "bin/selkies --addr" | head -1); tr "\0" "\n" < /proc/$P/environ')
  ZU=""
  for z in SELKIES_FILE_TRANSFERS=none SELKIES_PRINTING_ENABLED=false SELKIES_ENABLE_SHARING=false \
           SELKIES_COMMAND_ENABLED=false SELKIES_ENABLE_DUAL_MODE=false SELKIES_UI_SHOW_SIDEBAR=false; do
    grep -qx "$z" <<<"$UMG" || ZU="$ZU $z"
  done
  [ -z "$ZU" ] && ok "Dateiübertragung, Drucken, Freigaben, Befehle, Moduswechsel, Seitenleiste: aus" \
               || bad "Nicht gesetzt:$ZU"
  [ "$(imc 'setxkbmap -query | awk "\$1==\"layout:\"{print \$2}"')" = "de" ] \
    && ok "Tastaturlayout vor dem Start gesetzt (de)" \
    || bad "Tastaturlayout ist nicht de — Umlaute verschwänden"

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
