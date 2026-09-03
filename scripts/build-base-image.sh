#!/usr/bin/env bash
# Baut OTAs eigenes Basisimage — als **Testimage**.
#
#   scripts/build-base-image.sh              baut ota/base-xfce:test
#   scripts/build-base-image.sh --pruefen    baut und prüft es danach
#   scripts/build-base-image.sh --nur-pruefen
#
# Mit OTA_PRUEFE_JAVA=1 kommt Abnahmefall 7 dazu (Java/AWT, stellvertretend
# für IntelliJ). Er läuft nicht von selbst mit, weil er ein JDK in den
# Prüfcontainer nachinstalliert — rund 300 MB und ein bis zwei Minuten. Ins
# **Image** gehört das nicht: Ein Basisimage, von dem jeder Arbeitsplatz
# abstammt, trägt kein JDK mit sich herum, nur damit ein Test es vorfindet.
#
# Es heisst `:test`, keine Vorlage zeigt darauf, und `ota/arbeitsplatz` bleibt
# unberührt. Erst wenn ein Arbeitsplatz darauf nachweislich so läuft wie
# bisher, wird daraus eine Fassung ohne `test` im Namen.
#
# Die Prüfung ist keine Formsache: Sie startet den Container so, wie OTA ihn
# startet, und misst genau die Punkte, auf die sich der Agent verlässt.

set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TAG="${OTA_BASE_TAG:-ota/base-xfce:test}"
CN="ota-base-pruef-$$"

pass=0; fail=0
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; pass=$((pass+1)); }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$1" >&2; fail=$((fail+1)); }

bauen() {
  echo "Baue $TAG …"
  docker build -t "$TAG" "$ROOT/images/base-xfce" || return 1
  echo
  docker images --format '{{.Repository}}:{{.Tag}}  {{.Size}}' | grep -F "$TAG"
  echo
}

pruefen() {
  echo "Prüfe $TAG gegen den Vertrag mit dem Agent"
  echo

  docker rm -f "$CN" >/dev/null 2>&1
  docker run -d --name "$CN" --shm-size=512m \
    -e VNC_PW=pruef-geheim-2026 \
    -e VNCOPTIONS="-PreferBandwidth -DLP_ClipDelay=0" \
    "$TAG" >/dev/null || { bad "Der Container startete nicht"; return 1; }

  # Genau die Prüfung, die der Agent macht (`_wait_ready`).
  BEREIT=0
  for i in $(seq 1 60); do
    if docker exec "$CN" bash -lc '(exec 3<>/dev/tcp/127.0.0.1/6901)' 2>/dev/null; then
      BEREIT=1; break
    fi
    sleep 1
  done
  [ "$BEREIT" = "1" ] && ok "KasmVNC nimmt auf 6901 an (nach ${i}s)" \
                      || bad "KasmVNC war nach 60s nicht erreichbar"

  if [ "$BEREIT" != "1" ]; then
    docker logs "$CN" 2>&1 | tail -30
    docker rm -f "$CN" >/dev/null 2>&1
    return 1
  fi

  # Das Zuhause und die Kennung — der Agent hängt genau dorthin.
  UID_IM=$(docker exec "$CN" id -u kasm-user 2>/dev/null | tr -d '\r')
  [ "$UID_IM" = "1000" ] && ok "kasm-user hat die Kennung 1000" \
                         || bad "kasm-user hat die Kennung $UID_IM"
  docker exec "$CN" test -d /home/kasm-user \
    && ok "Das Zuhause liegt unter /home/kasm-user" \
    || bad "/home/kasm-user fehlt"

  # Die Dateien, aus denen der Agent weitere Displays startet. `.vnc/passwd`
  # ist nicht darunter — siehe vnc_startup.sh: KasmVNC nimmt sie fehlend hin,
  # und das Kasm-Image legt sie auch nur nebenbei an.
  for datei in .vnc/self.pem .kasmpasswd; do
    docker exec "$CN" test -s "/home/kasm-user/$datei" \
      && ok "$datei liegt bereit" || bad "$datei fehlt oder ist leer"
  done

  # Der Name im Passwortspeicher ist die Schnittstelle: OTA setzt vor dem
  # Stream einen Basic-Auth-Header mit `kasm_user` (Unterstrich). Steht dort
  # ein anderer Name, fragt der Bildschirm nach einem Passwort, das niemand
  # kennt — und es sieht aus wie ein kaputter Stream.
  ANGEMELDET=$(docker exec "$CN" bash -lc \
    "curl -sk -o /dev/null -w '%{http_code}' -u kasm_user:pruef-geheim-2026 https://127.0.0.1:6901/")
  expectcode() { [ "$1" = "200" ]; }
  expectcode "$ANGEMELDET" && ok "Anmeldung als kasm_user gelingt (HTTP $ANGEMELDET)" \
                           || bad "Anmeldung als kasm_user gab HTTP $ANGEMELDET"
  ABGEWIESEN=$(docker exec "$CN" bash -lc \
    "curl -sk -o /dev/null -w '%{http_code}' -u kasm_user:falsch https://127.0.0.1:6901/")
  [ "$ABGEWIESEN" = "401" ] && ok "Ein falsches Passwort wird abgewiesen (401)" \
                            || bad "Falsches Passwort gab HTTP $ABGEWIESEN statt 401"

  # Die Werkzeuge, ohne die apps.py nicht arbeiten kann.
  for werkzeug in Xvnc xauth mcookie xfwm4 wmctrl xdotool xsel autocutsel clipnotify; do
    docker exec "$CN" bash -lc "command -v $werkzeug >/dev/null" \
      && ok "$werkzeug ist da" || bad "$werkzeug fehlt"
  done
  docker exec "$CN" test -d /usr/share/kasmvnc/www \
    && ok "Die Weboberfläche liegt unter /usr/share/kasmvnc/www" \
    || bad "/usr/share/kasmvnc/www fehlt"

  # Derselbe Stand der Weboberfläche wie im heutigen Image (dort 1.4.1, die
  # es öffentlich nicht gibt). Die OTA-Oberfläche spricht mit ihr.
  # Aus der Paketverwaltung und nicht aus `Xvnc -version`: Läuft schon ein
  # Xvnc, meldet der Aufruf im selben Container nichts Brauchbares.
  V=$(docker exec "$CN" dpkg-query -W -f='${Version}' kasmvncserver 2>/dev/null \
      | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
  case "$V" in
    1.4.*) ok "KasmVNC $V — derselbe Stand der Weboberfläche wie bisher" ;;
    *)     bad "KasmVNC $V — erwartet wurde 1.4.x" ;;
  esac

  # Ein zweites Display, genau wie der Agent es aufmacht. Das ist der Kern
  # des Arbeitsplatzmodells: eine Anwendung je Display.
  ZWEIT=$(docker exec -u 1000 "$CN" bash -lc '
    export HOME=/home/kasm-user XAUTHORITY=/home/kasm-user/.Xauthority
    xauth add :2 MIT-MAGIC-COOKIE-1 "$(mcookie)" 2>/dev/null
    nohup /usr/bin/Xvnc :2 -depth 24 -httpd /usr/share/kasmvnc/www -sslOnly \
      -interface 0.0.0.0 -websocketPort 6902 -rfbport 5902 -geometry 1280x720 \
      -cert $HOME/.vnc/self.pem -key $HOME/.vnc/self.pem \
      -auth $XAUTHORITY -rfbauth $HOME/.vnc/passwd \
      -KasmPasswordFile $HOME/.kasmpasswd > /tmp/d2.log 2>&1 &
    for i in $(seq 1 40); do [ -e /tmp/.X11-unix/X2 ] && { echo ja; exit 0; }; sleep 0.25; done
    echo nein' | tr -d '\r')
  [ "$ZWEIT" = "ja" ] && ok "Ein zweites Display lässt sich öffnen" \
                      || bad "Das zweite Display kam nicht (siehe /tmp/d2.log)"

  # Und darauf eine Anwendung, formatfüllend — der ganze Weg aus apps.py.
  APP=$(docker exec -u 1000 "$CN" bash -lc '
    export HOME=/home/kasm-user XAUTHORITY=/home/kasm-user/.Xauthority DISPLAY=:2
    nohup xfwm4 --compositor=off >/dev/null 2>&1 &
    sleep 1
    nohup xfce4-terminal >/dev/null 2>&1 &
    for i in $(seq 1 40); do
      wmctrl -l 2>/dev/null | awk "\$2 != -1" | grep -q . && { echo ja; exit 0; }
      sleep 0.5
    done
    echo nein' | tr -d '\r')
  [ "$APP" = "ja" ] && ok "Eine Anwendung öffnet dort ein Fenster" \
                    || bad "Auf :2 kam kein Fenster"

  # Die Zwischenablage — der eigentliche Grund für das eigene Image.
  CLIP=$(docker exec -u 1000 "$CN" bash -lc '
    export DISPLAY=:1 XAUTHORITY=/home/kasm-user/.Xauthority
    echo "hin-und-zurueck" | xsel -i -b && xsel -o -b' | tr -d '\r\n')
  [ "$CLIP" = "hin-und-zurueck" ] && ok "Die Zwischenablage lässt sich setzen und lesen" \
                                  || bad "xsel gab '$CLIP' zurück"

  # clipnotify blockiert, bis sich etwas ändert — genau das ersetzt die
  # Abfrage im halben Sekundentakt.
  MELDET=$(docker exec -u 1000 "$CN" bash -lc '
    export DISPLAY=:1 XAUTHORITY=/home/kasm-user/.Xauthority
    ( sleep 1; echo neu | xsel -i -b ) &
    timeout 10 clipnotify && echo gemeldet || echo stumm' | tr -d '\r\n')
  [ "$MELDET" = "gemeldet" ] && ok "clipnotify meldet eine Änderung, statt zu pollen" \
                             || bad "clipnotify meldete nichts ($MELDET)"

  # Und der eigentliche Gewinn: die Brücke läuft ereignisgesteuert.
  #
  # Geprüft wird mit genau dem Skript, das der Agent in den Container legt —
  # nicht mit einer Nachbildung. Sonst prüfte der Test seine eigene Fassung.
  "$ROOT/scripts/bruecke-ausgeben.py" bridge \
    | docker exec -i -u 1000 "$CN" bash -c \
        'cat > /tmp/ota-clipboard-bridge.sh; chmod +x /tmp/ota-clipboard-bridge.sh'
  docker exec -u 1000 -d "$CN" bash -lc \
    'setsid nohup /tmp/ota-clipboard-bridge.sh > /tmp/ota-clipboard.log 2>&1 < /dev/null &'
  sleep 3

  ART=$(docker exec "$CN" bash -lc 'head -1 /tmp/ota-clipboard.log' | tr -d '\r')
  case "$ART" in
    *ereignisgesteuert*) ok "Die Brücke läuft ereignisgesteuert, nicht im Halbsekundentakt" ;;
    *) bad "Die Brücke meldet: $ART" ;;
  esac

  # Von :1 nach :2 — die eigentliche Aufgabe. Und schnell: Über Ereignisse
  # sind es Millisekunden, im alten Takt bis zu eine halbe Sekunde.
  WORT="brueckentext-$$"
  docker exec -u 1000 "$CN" bash -lc \
    "export DISPLAY=:1 XAUTHORITY=/home/kasm-user/.Xauthority; printf '%s' '$WORT' | xclip -selection clipboard -i" 2>/dev/null
  ANGEKOMMEN=""
  for i in $(seq 1 20); do
    ANGEKOMMEN=$(docker exec -u 1000 "$CN" bash -lc \
      'export DISPLAY=:2 XAUTHORITY=/home/kasm-user/.Xauthority; xclip -selection clipboard -o 2>/dev/null' | tr -d '\r\n')
    [ "$ANGEKOMMEN" = "$WORT" ] && break
    sleep 0.25
  done
  [ "$ANGEKOMMEN" = "$WORT" ] && ok "Kopiert auf :1, eingefügt auf :2 (nach höchstens $((i*250))ms)" \
                              || bad "Auf :2 kam '$ANGEKOMMEN' an"

  # Und wieder aus: Die Wachen sind Kindprozesse und dürfen nicht
  # zurückbleiben, wenn die Brücke endet.
  "$ROOT/scripts/bruecke-ausgeben.py" stop | docker exec -i "$CN" bash >/dev/null 2>&1
  sleep 1
  UEBRIG=$(docker exec "$CN" bash -lc 'pgrep -c clipnotify || true' | tr -d '\r')
  [ "${UEBRIG:-0}" = "0" ] && ok "Nach dem Stoppen bleibt keine Wache zurück" \
                           || bad "$UEBRIG clipnotify-Prozesse blieben übrig"

  # Abnahmefall 7 — Java/AWT, stellvertretend für IntelliJ.
  #
  # Java hat in der Abnahme eine eigene Zeile, weil X11 keinen Speicher hat,
  # in dem etwas liegt: Es gibt einen Besitzer der Auswahl, und AWT bedient
  # die Anfragen aus einem eigenen Thread. Ein Java-Programm, das setzt und
  # sich beendet, hinterlässt nichts — bei Gtk und Electron ist das anders.
  # Deshalb wird hier mit einem laufenden Java-Prozess gemessen.
  if [ "${OTA_PRUEFE_JAVA:-0}" = "1" ]; then
    # Die Brücke wieder anwerfen — sie wurde eben zum Prüfen gestoppt, und
    # ohne sie kommt zwischen :1 und :2 gar nichts an.
    docker exec -u 1000 -d "$CN" bash -lc \
      'setsid nohup /tmp/ota-clipboard-bridge.sh > /tmp/ota-clipboard.log 2>&1 < /dev/null &'
    sleep 2

    echo "  · JDK wird in den Prüfcontainer nachinstalliert …"
    docker exec -u 0 "$CN" bash -lc \
      'apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
       --no-install-recommends default-jdk >/dev/null 2>&1' \
      && ok "JDK im Prüfcontainer vorhanden" || bad "JDK liess sich nicht installieren"

    docker cp "$ROOT/images/base-xfce/pruefung/ClipPruef.java" "$CN:/tmp/ClipPruef.java" >/dev/null
    docker exec -u 0 "$CN" chown 1000:1000 /tmp/ClipPruef.java

    # Java setzt auf :1 und hält den Besitz; danach wird auf :2 gelesen —
    # über die Brücke. Das ist die Richtung, die bei IntelliJ erfahrungsgemäß
    # klemmt.
    JAVATEXT="aus-java-$$ äöü"
    docker exec -u 1000 -d "$CN" bash -lc \
      "export DISPLAY=:1 XAUTHORITY=/home/kasm-user/.Xauthority HOME=/home/kasm-user; \
       java /tmp/ClipPruef.java set '$JAVATEXT' 25000 > /tmp/java-set.log 2>&1"
    AUS_JAVA=""
    for i in $(seq 1 20); do
      sleep 1
      AUS_JAVA=$(docker exec -u 1000 "$CN" bash -lc \
        'export DISPLAY=:2 XAUTHORITY=/home/kasm-user/.Xauthority; xclip -selection clipboard -o 2>/dev/null')
      [ "$AUS_JAVA" = "$JAVATEXT" ] && break
    done
    [ "$AUS_JAVA" = "$JAVATEXT" ] \
      && ok "Java/AWT auf :1 → Brücke → :2 (Abnahmefall 7, Richtung hinaus)" \
      || bad "Aus Java kam '$AUS_JAVA' an ($(docker exec "$CN" cat /tmp/java-set.log 2>/dev/null | head -2))"

    # Und die Gegenrichtung: etwas auf :2 setzen und mit Java auf :1 lesen.
    NACH_JAVA="nach-java-$$ äöü"
    docker exec -u 1000 "$CN" bash -lc \
      "export DISPLAY=:2 XAUTHORITY=/home/kasm-user/.Xauthority; \
       printf '%s' '$NACH_JAVA' | xclip -selection clipboard -i" 2>/dev/null &
    sleep 4
    IN_JAVA=$(docker exec -u 1000 "$CN" bash -lc \
      "export DISPLAY=:1 XAUTHORITY=/home/kasm-user/.Xauthority HOME=/home/kasm-user; \
       java /tmp/ClipPruef.java get 2>/dev/null")
    [ "$IN_JAVA" = "$NACH_JAVA" ] \
      && ok "Brücke → Java/AWT liest den Text (Abnahmefall 7, Richtung herein)" \
      || bad "Java las '$IN_JAVA' statt '$NACH_JAVA'"

    "$ROOT/scripts/bruecke-ausgeben.py" stop | docker exec -i "$CN" bash >/dev/null 2>&1
  else
    echo "  · Abnahmefall 7 (Java/AWT) übersprungen — mit OTA_PRUEFE_JAVA=1 läuft er mit"
  fi

  # Läuft das Startskript **zu Ende**?
  #
  # Der Port allein sagt das nicht: KasmVNC hört, lange bevor das Skript
  # durch ist. Am 2026-09-02 blieb es an `autocutsel` hängen — und damit lief
  # `custom_startup.sh` nie, also genau das, was ein abgeleitetes Image
  # starten soll. Der Container sah dabei kerngesund aus.
  #
  # Geprüft wird deshalb am Ende der Kette: Das Startskript des Images legt
  # eine Datei an, und die muss da sein.
  docker exec -u 0 "$CN" bash -lc \
    'printf "#!/bin/sh\ntouch /tmp/ota-startskript-lief\nwhile true; do sleep 3600; done\n" \
     > /dockerstartup/custom_startup.sh && chmod +x /dockerstartup/custom_startup.sh' \
    >/dev/null 2>&1
  docker restart "$CN" >/dev/null 2>&1
  GELAUFEN=""
  for i in $(seq 1 60); do
    sleep 1
    docker exec "$CN" test -e /tmp/ota-startskript-lief 2>/dev/null && { GELAUFEN=ja; break; }
  done
  [ "$GELAUFEN" = "ja" ] \
    && ok "Das Startskript läuft bis zum Ende durch (custom_startup.sh nach ${i}s)" \
    || bad "custom_startup.sh lief nicht — das Startskript bleibt vorher stehen"

  # Und danach ist der Strom wieder da: Ein Neustart darf ihn nicht kosten.
  BEREIT2=0
  for i in $(seq 1 60); do
    if docker exec "$CN" bash -lc '(exec 3<>/dev/tcp/127.0.0.1/6901)' 2>/dev/null; then
      BEREIT2=1; break
    fi
    sleep 1
  done
  [ "$BEREIT2" = "1" ] && ok "Und nach einem Neustart nimmt KasmVNC wieder an" \
                       || bad "Nach dem Neustart kam KasmVNC nicht zurück"

  # Das Kasm-Label muss leer sein, sonst räumt Kasms Aufräumer das Image weg.
  LABEL=$(docker inspect "$TAG" --format '{{index .Config.Labels "com.kasmweb.image"}}')
  [ -z "$LABEL" ] && ok "Kein com.kasmweb.image-Label — Kasm lässt es stehen" \
                  || bad "com.kasmweb.image ist gesetzt ($LABEL)"

  # Und der Beweis, dass nichts Bestehendes angefasst wurde.
  docker image inspect ota/arbeitsplatz:v13 >/dev/null 2>&1 \
    && ok "ota/arbeitsplatz:v13 liegt unverändert daneben" \
    || bad "ota/arbeitsplatz:v13 ist weg"

  docker rm -f "$CN" >/dev/null 2>&1
}

case "${1:-}" in
  --nur-pruefen) pruefen ;;
  --pruefen)     bauen && pruefen ;;
  *)             bauen ;;
esac

echo
printf '  bestanden: %d   fehlgeschlagen: %d\n' "$pass" "$fail"
[ "$fail" -eq 0 ] || exit 1
