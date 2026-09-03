#!/usr/bin/env bash
# Prüft Abnahmefall 8 aus plan.md §10.5:
# Kopieren zwischen zwei Anwendungen im selben Arbeitsplatz.
#
# Jedes X-Display hat seine eigene Zwischenablage. Ohne die Brücke aus
# plan.md §10.4 funktioniert dieser Weg nicht — und niemand würde das
# erwarten, weil beide Apps im selben Container laufen.

set -uo pipefail

pass=0; fail=0
ok()  { printf '  \033[32m✓\033[0m %s\n' "$1"; pass=$((pass+1)); }
bad() { printf '  \033[31m✗\033[0m %s\n' "$1"; fail=$((fail+1)); }

BASE="${OTA_BASE:-https://192.168.66.224:8443}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CA="$ROOT/deploy/certs/ota-ca.crt"
JAR="$(mktemp)"

# Abnahmefall 11 haelt den Container kurz an. Bricht der Test dazwischen ab,
# bliebe er eingefroren — und der naechste Lauf scheiterte an einer Meldung,
# die nichts mit der Zwischenablage zu tun hat.
aufraeumen() {
  rm -f "$JAR"
  [ -n "${CN:-}" ] && docker unpause "$CN" >/dev/null 2>&1
  return 0
}
trap aufraeumen EXIT
ADMIN="${OTA_TEST_ADMIN:-notfall}"
ADMIN_PW="${OTA_TEST_ADMIN_PW:?OTA_TEST_ADMIN_PW fehlt. Trag es in deploy/.env ein.}"

api() { curl -s --cacert "$CA" -b "$JAR" -c "$JAR" "$@"; }
jqp() { python3 -c "import sys,json;d=json.load(sys.stdin);print($1)" 2>/dev/null; }

# Der Test braucht einen Arbeitsplatz mit mindestens zwei offenen Apps.
# Statt das vorauszusetzen, stellt er es selbst her — sonst haengt sein
# Ergebnis davon ab, was ein vorheriger Test hinterlassen hat.
ensure_workspace() {
  api -X POST "$BASE/api/auth/login" -H 'Content-Type: application/json' \
      -d "{\"username\":\"$ADMIN\",\"password\":\"$ADMIN_PW\"}" >/dev/null

  sid=$(api "$BASE/api/sessions" | jqp "next((s['id'] for s in d if s['template_mode']=='workspace'), '')")
  if [ -z "$sid" ]; then
    local tpl
    tpl=$(api "$BASE/api/templates" | jqp "next((t['id'] for t in d if t['mode']=='workspace' and t['is_enabled']), '')")
    [ -z "$tpl" ] && return 1
    sid=$(api -X POST "$BASE/api/sessions" -H 'Content-Type: application/json' \
              -d "{\"template_id\":\"$tpl\"}" | jqp "d.get('id','')")
    [ -z "$sid" ] && return 1
    echo "  Arbeitsplatz gestartet, warte auf Bereitschaft…"
    sleep 20
  fi
  SID="$sid"

  local open
  open=$(api "$BASE/api/sessions" | jqp "len(next((s['streams'] for s in d if s['id']=='$sid'), []))")
  local slugs
  slugs=$(api "$BASE/api/templates" | jqp "' '.join(a['slug'] for t in d for a in t['apps'] if a['is_enabled'] and not a['blocked_reason'])")
  for slug in $slugs; do
    [ "${open:-0}" -ge 2 ] && break
    api -X POST "$BASE/api/sessions/$sid/apps/$slug" >/dev/null 2>&1
    sleep 6
    open=$(api "$BASE/api/sessions" | jqp "len(next((s['streams'] for s in d if s['id']=='$sid'), []))")
  done
  return 0
}

# Der Container, der zu **diesem** Konto gehoert — nicht einfach der erste,
# den `docker ps` nennt.
#
# Auf einem Host, auf dem gerade auch die Autorisierungstests gelaufen sind,
# steht die Session eines Testnutzers vorn in der Liste. Der Rest dieses
# Skripts fragt die API nach dieser Session, findet sie nicht (sie gehoert ja
# einem anderen) und meldet „keine laufende Anwendung" — ein Fehlschlag, der
# nichts mit der Zwischenablage zu tun hat. Gemessen am 2026-08-28.
mein_container() {
  api "$BASE/api/sessions" | jqp "
next(('ota-s-' + s['id'][:12] for s in d if s['status'] == 'running'), '')"
}

api -X POST "$BASE/api/auth/login" -H 'Content-Type: application/json' \
    -d "{\"username\":\"$ADMIN\",\"password\":\"$ADMIN_PW\"}" >/dev/null

SID=""
CN=$(mein_container)
DISPLAY_COUNT=0
[ -n "$CN" ] && DISPLAY_COUNT=$(docker exec "$CN" bash -c 'ls /tmp/.X11-unix/ 2>/dev/null | wc -l' 2>/dev/null || echo 0)

if [ "${DISPLAY_COUNT:-0}" -lt 2 ]; then
  echo "Weniger als zwei Displays offen — der Test stellt den Zustand selbst her."
  ensure_workspace || { echo "Kein Arbeitsplatz verfügbar."; exit 1; }
  sleep 4
  CN=$(mein_container)
fi

if [ -z "$SID" ] && [ -n "$CN" ]; then
  SID=$(docker inspect -f '{{ index .Config.Labels "ota.session_id" }}' "$CN" 2>/dev/null)
  # Ohne Anmeldung geht der Rest nicht — ensure_workspace hat sie u. U. nicht
  # gebraucht, weil schon alles lief.
  api -X POST "$BASE/api/auth/login" -H 'Content-Type: application/json' \
      -d "{\"username\":\"$ADMIN\",\"password\":\"$ADMIN_PW\"}" >/dev/null
fi

if [ -z "$CN" ]; then
  echo "Keine laufende Session gefunden." 
  exit 1
fi

echo "Zwischenablage-Brücke im Container $CN"
echo

DISPLAYS=$(docker exec "$CN" bash -c 'ls /tmp/.X11-unix/ 2>/dev/null | sed "s/^X//"' | tr '\n' ' ')
echo "  Offene Displays: $DISPLAYS"

COUNT=$(echo "$DISPLAYS" | wc -w)
if [ "$COUNT" -lt 2 ]; then
  bad "Weniger als zwei Displays offen — für diesen Test mindestens zwei Apps starten"
  exit 1
fi
ok "$COUNT Displays offen"

RUNNING=$(docker exec "$CN" bash -c \
  '[ -f /tmp/ota-clipboard.pid ] && kill -0 "$(cat /tmp/ota-clipboard.pid)" 2>/dev/null && echo ja || echo nein')
[ "$RUNNING" = "ja" ] && ok "Brücke läuft" || bad "Brücke läuft nicht"

# Der klassische Desktop liegt auf :1 — dem Display, das das Kasm-Basisimage
# selbst aufmacht. Er ist eine zusaetzliche Ansicht neben den einzeln
# gestreamten Anwendungen. Ohne Leiste und Fenstermanager waere er ein
# schwarzes Bild mit Mauszeiger, und genau das war er einmal: xfce4-panel
# fehlte im gebauten Image.
DESK=$(docker exec "$CN" bash -c \
  'for p in xfwm4 xfce4-panel xfdesktop; do pgrep -x "$p" >/dev/null && printf "%s " "$p"; done')
case "$DESK" in
  *xfwm4*xfce4-panel*xfdesktop*)
    ok "Klassischer Desktop auf :1 vollständig ($DESK)" ;;
  *)
    bad "Dem Desktop auf :1 fehlt etwas — vorhanden: ${DESK:-nichts}" ;;
esac

FIRST=$(echo "$DISPLAYS" | awk '{print $1}')
SECOND=$(echo "$DISPLAYS" | awk '{print $2}')

check_direction() {  # check_direction <von> <nach> <text> <beschreibung>
  local from="$1" to="$2" text="$3" label="$4"
  docker exec -u 1000 "$CN" bash -c "
    export XAUTHORITY=$HOME/.Xauthority
    printf '%s' \"$text\" | timeout 3 xclip -d :$from -selection clipboard -i" 2>/dev/null
  sleep 2.5
  local got
  got=$(docker exec -u 1000 "$CN" bash -c "
    export XAUTHORITY=$HOME/.Xauthority
    timeout 3 xclip -d :$to -selection clipboard -o 2>/dev/null")
  if [ "$got" = "$text" ]; then ok "$label"; else bad "$label — bekam: [$got]"; fi
}

check_direction "$FIRST" "$SECOND" "Einfacher Text" \
  ":$FIRST → :$SECOND, einfacher Text"
check_direction "$SECOND" "$FIRST" "Rückweg funktioniert auch" \
  ":$SECOND → :$FIRST, Gegenrichtung"
# Backslashes bewusst nicht im Text: Sie durchlaufen hier zwei Shells und
# machen den Test unzuverlässig, ohne etwas über die Brücke auszusagen.
check_direction "$FIRST" "$SECOND" "Umlaute äöü ÄÖÜ ß und Zeichen: {}[]()<>@#" \
  ":$FIRST → :$SECOND, Umlaute und Sonderzeichen"

# Mehrzeiliger Code mit Tabulatoren — der Alltagsfall beim Programmieren.
MULTI='def gruss(name):
	return f"Hallo {name}"'
docker exec -u 1000 "$CN" bash -c "
  export XAUTHORITY=$HOME/.Xauthority
  printf '%s' '$MULTI' | timeout 3 xclip -d :$FIRST -selection clipboard -i" 2>/dev/null
sleep 2.5
GOT=$(docker exec -u 1000 "$CN" bash -c "
  export XAUTHORITY=$HOME/.Xauthority
  timeout 3 xclip -d :$SECOND -selection clipboard -o 2>/dev/null")
[ "$GOT" = "$MULTI" ] && ok "Mehrzeiliger Code mit Tabulator bleibt erhalten" \
                      || bad "Mehrzeiliger Code verändert — bekam: [$GOT]"


# ------------------------------------------- Auflösung je Anwendung
# Eine Anwendung darf eine eigene Auflösung bekommen — eine
# Entwicklungsumgebung braucht mehr Fläche als ein Terminal. Sie gilt ab dem
# **nächsten** Start dieser Anwendung, wie alle Ressourcen in OTA; ein
# laufendes Display wird nicht umgestellt. Genau das prüft dieser Abschnitt:
# setzen, Anwendung neu starten, nachmessen, zurückstellen.
echo
echo "Auflösung je Anwendung"

TPL_RES=$(api "$BASE/api/sessions" | jqp "next((s['template_id'] for s in d if s['id'] == '$SID'), '')")
APP_RES=$(api "$BASE/api/sessions" | jqp "
next((st['app_slug'] for s in d if s['id'] == '$SID' for st in s['streams']), '')")

katalog() {  # katalog <slug> <x> <y> — schreibt den Katalog neu.
             # "leer" statt einer Zahl loescht den Wert; ein leeres Argument
             # wuerde sonst auf den gespeicherten zurueckfallen, und das
             # Zuruecknehmen ginge stillschweigend ins Leere.
  api "$BASE/api/templates/$TPL_RES/apps/discover" \
    | ZIEL="$1" X="${2:-}" Y="${3:-}" python3 -c '
import json, os, sys
ziel, x, y = os.environ["ZIEL"], os.environ["X"], os.environ["Y"]
raus = []
for a in json.load(sys.stdin):
    if not a["is_enabled"] or a.get("missing"):
        continue
    e = {k: a[k] for k in
         ("slug", "name", "icon", "exec_cmd", "exec_args", "fixed_display", "group_ids")}
    e["is_enabled"] = True
    if a["slug"] == ziel:
        e["x_res"] = None if x == "leer" else (int(x) if x else a.get("x_res"))
        e["y_res"] = None if y == "leer" else (int(y) if y else a.get("y_res"))
    else:
        e["x_res"], e["y_res"] = a.get("x_res"), a.get("y_res")
    raus.append(e)
print(json.dumps(raus))'
}

if [ -z "$TPL_RES" ] || [ -z "$APP_RES" ]; then
  bad "Keine laufende Anwendung zum Prüfen der Auflösung"
else
  api -X PUT "$BASE/api/templates/$TPL_RES/apps" -H 'Content-Type: application/json' \
    -d "$(katalog "$APP_RES" 1600 900)" >/dev/null

  api -X DELETE "$BASE/api/sessions/$SID/apps/$APP_RES" >/dev/null
  sleep 3
  api -X POST "$BASE/api/sessions/$SID/apps/$APP_RES" >/dev/null
  sleep 8

  D_RES=$(api "$BASE/api/sessions" | jqp "
next((str(st['display_num']) for s in d if s['id'] == '$SID'
      for st in s['streams'] if st['app_slug'] == '$APP_RES'), '')")
  HAVE=$(docker exec "$CN" bash -c "DISPLAY=:$D_RES xdpyinfo 2>/dev/null | awk '/dimensions/ {print \$2}'")
  [ "$HAVE" = "1600x900" ] \
    && ok "$APP_RES startet mit seiner eigenen Auflösung ($HAVE auf :$D_RES)" \
    || bad "$APP_RES startete mit $HAVE statt 1600x900"

  # Zurückstellen und wieder erben lassen.
  api -X PUT "$BASE/api/templates/$TPL_RES/apps" -H 'Content-Type: application/json' \
    -d "$(katalog "$APP_RES" leer leer)" >/dev/null
  ERBT=$(api "$BASE/api/templates/$TPL_RES" | jqp "
next((a['x_res'] for a in d['apps'] if a['slug'] == '$APP_RES'), 'fehlt')")
  [ "$ERBT" = "None" ] \
    && ok "Ohne eigenen Wert erbt die Anwendung die des Arbeitsplatzes" \
    || bad "Die eigene Auflösung liess sich nicht zurücknehmen ($ERBT)"

  api -X DELETE "$BASE/api/sessions/$SID/apps/$APP_RES" >/dev/null
  sleep 2
  api -X POST "$BASE/api/sessions/$SID/apps/$APP_RES" >/dev/null
  sleep 8
fi

# ------------------------------------------------ Abnahmefall 6: Bild
# Ein Bild kommt nicht als Text aus der Zwischenablage. Wer nur `xclip -o`
# fragt, bekommt nichts und hält sie für leer — ein Screenshot wäre in der
# Nachbaranwendung unerreichbar, ohne dass irgendwo etwas dazu stünde.
echo
echo "Abnahmefall 6 — Bild zwischen zwei Anwendungen"
MADE=$(docker exec -u 1000 "$CN" bash -c "
  export XAUTHORITY=$HOME/.Xauthority
  command -v import >/dev/null 2>&1 && \
    timeout 10 import -display :$FIRST -window root -resize 40x40 /tmp/ota-bild.png \
      >/dev/null 2>&1 && echo import && exit 0
  command -v xwd >/dev/null 2>&1 && command -v convert >/dev/null 2>&1 && \
    timeout 10 bash -c 'xwd -display :$FIRST -root -silent | convert xwd:- -resize 40x40 png:/tmp/ota-bild.png' \
      >/dev/null 2>&1 && echo xwd && exit 0
  # Notnagel: ein winziges PNG von Hand. Es geht um den Weg, nicht um das Motiv.
  printf 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==' \
    | base64 -d > /tmp/ota-bild.png && echo eingebaut")
if [ -n "$MADE" ]; then
  echo "  Bildquelle: $MADE"
  docker exec -u 1000 "$CN" bash -c "
    export XAUTHORITY=$HOME/.Xauthority
    timeout 5 xclip -d :$FIRST -selection clipboard -t image/png -i < /tmp/ota-bild.png" 2>/dev/null
  sleep 3
  SIZE_IN=$(docker exec "$CN" bash -c 'wc -c < /tmp/ota-bild.png')
  SIZE_OUT=$(docker exec -u 1000 "$CN" bash -c "
    export XAUTHORITY=$HOME/.Xauthority
    timeout 5 xclip -d :$SECOND -selection clipboard -t image/png -o 2>/dev/null | wc -c")
  if [ "${SIZE_OUT:-0}" = "${SIZE_IN:-1}" ]; then
    ok "Ein Bild kommt unverändert auf dem anderen Display an ($SIZE_OUT Bytes)"
  elif [ "${SIZE_OUT:-0}" -gt 0 ]; then
    bad "Das Bild kam verändert an: $SIZE_OUT von $SIZE_IN Bytes"
  else
    bad "Das Bild kam nicht an — die Brücke trägt nur Text"
  fi

  # Und danach muss Text weiterhin gehen: Der Typwechsel darf die Brücke
  # nicht in einem Zustand zurücklassen, in dem sie nur noch Bilder kennt.
  check_direction "$SECOND" "$FIRST" "wieder Text nach dem Bild" \
    "Nach dem Bild funktioniert Text weiterhin"
  docker exec "$CN" rm -f /tmp/ota-bild.png 2>/dev/null
else
  bad "Kein Bild für die Prüfung erzeugbar"
fi

# --------------------------------------------------- Abnahmefall 5: 1 MB
# „Kommt an oder scheitert mit Meldung, nie stumm." Der stumme Fall ist der
# schlimme: Wer 1 MB kopiert und nichts bekommt, sucht den Fehler bei sich.
echo
echo "Abnahmefall 5 — sehr grosser Inhalt"
docker exec -u 1000 "$CN" bash -c "
  export XAUTHORITY=$HOME/.Xauthority
  head -c 1000000 /dev/urandom | base64 | head -c 1000000 > /tmp/ota-gross.txt
  timeout 5 xclip -d :$FIRST -selection clipboard -i < /tmp/ota-gross.txt" 2>/dev/null
sleep 4
CMP=$(docker exec -u 1000 "$CN" bash -c "
  export XAUTHORITY=$HOME/.Xauthority
  timeout 5 xclip -d :$SECOND -selection clipboard -o 2>/dev/null | wc -c")
SRC=$(docker exec "$CN" bash -c 'wc -c < /tmp/ota-gross.txt')
if [ "${CMP:-0}" = "${SRC:-1}" ]; then
  ok "1 MB kommt vollständig an ($CMP Bytes)"
elif [ "${CMP:-0}" -gt 0 ]; then
  bad "1 MB kam abgeschnitten an: $CMP von $SRC Bytes — und zwar stumm"
else
  bad "1 MB kam gar nicht an — und zwar stumm"
fi
docker exec "$CN" rm -f /tmp/ota-gross.txt 2>/dev/null

# --------------------------------------------- Abnahmefall 9: PRIMARY
# Markieren und mit der mittleren Maustaste einfügen. Innerhalb eines
# Displays macht X das selbst — geprüft wird, dass es im Container überhaupt
# funktioniert und dass die Brücke es **nicht** über Displays hinweg
# verschleppt: PRIMARY ist die flüchtige Auswahl, nicht die Zwischenablage.
echo
echo "Abnahmefall 9 — PRIMARY"
docker exec -u 1000 "$CN" bash -c "
  export XAUTHORITY=$HOME/.Xauthority
  printf '%s' 'markiert-mit-der-maus' | timeout 3 xclip -d :$FIRST -selection primary -i" 2>/dev/null
sleep 1
PRIM=$(docker exec -u 1000 "$CN" bash -c "
  export XAUTHORITY=$HOME/.Xauthority
  timeout 3 xclip -d :$FIRST -selection primary -o 2>/dev/null")
[ "$PRIM" = "markiert-mit-der-maus" ] \
  && ok "PRIMARY funktioniert auf demselben Display" \
  || bad "PRIMARY kam nicht an — bekam: [$PRIM]"

sleep 2
OTHER=$(docker exec -u 1000 "$CN" bash -c "
  export XAUTHORITY=$HOME/.Xauthority
  timeout 3 xclip -d :$SECOND -selection primary -o 2>/dev/null")
[ "$OTHER" != "markiert-mit-der-maus" ] \
  && ok "PRIMARY wird bewusst nicht über Displays gespiegelt" \
  || bad "PRIMARY wurde mitgespiegelt — jede Markierung überschriebe die Auswahl nebenan"

# ------------------------------- Abnahmefall 11: nach Pause und Fortsetzen
# Eine pausierte und wieder gestartete Session hat neue Prozesse, aber
# dieselben Displays. Läuft die Brücke danach nicht wieder an, funktioniert
# die Zwischenablage still nicht mehr — und niemand bringt das mit der Pause
# in Verbindung.
echo
echo "Abnahmefall 11 — nach Pause und Fortsetzen"
api -X POST "$BASE/api/sessions/$SID/pause" >/dev/null
sleep 3
# Die Aktion heisst "unpause", nicht "resume". Der Test hat das zuerst falsch
# geraten und daraufhin gemeldet, die Bruecke laufe nicht mehr — sie war nur
# noch eingefroren, weil `docker pause` alle Prozesse anhaelt.
api -X POST "$BASE/api/sessions/$SID/unpause" >/dev/null
for _ in 1 2 3 4 5 6 7 8 9 10; do
  # Aus der Liste: Eine einzelne Session hat keinen eigenen GET-Endpunkt.
  ST=$(api "$BASE/api/sessions" 2>/dev/null | jqp "
next((s['status'] for s in d if s['id'] == '$SID'), '')")
  [ "$ST" = "running" ] && break
  sleep 3
done
# Die Brücke hängt an einer App-Aktion. Ein Blick in den Container genügt.
sleep 4
AFTER=$(docker exec "$CN" bash -c \
  '[ -f /tmp/ota-clipboard.pid ] && kill -0 "$(cat /tmp/ota-clipboard.pid)" 2>/dev/null && echo ja || echo nein' \
  2>/dev/null)
if [ "$AFTER" = "ja" ]; then
  ok "Die Brücke läuft nach dem Fortsetzen weiter"
  check_direction "$FIRST" "$SECOND" "nach der Pause" \
    "Zwischenablage funktioniert nach Pause und Fortsetzen"
else
  bad "Nach dem Fortsetzen läuft die Brücke nicht mehr"
fi

# --------------------------- Abnahmefall 10: Zwischenablage abgeschaltet
# „Beide Richtungen bleiben wirkungslos, das Panel sagt warum." Geprüft wird
# hier der Teil im Container: Ist die Zwischenablage in der Vorlage aus, darf
# die Brücke nicht laufen — sonst wanderte Text weiter zwischen den
# Anwendungen, während die Oberfläche behauptet, sie sei aus.
echo
echo "Abnahmefall 10 — Zwischenablage in der Vorlage abgeschaltet"
TPL_ID=$(api "$BASE/api/sessions" | jqp "next((s['template_id'] for s in d if s['id']=='$SID'), '')")
RIGHTS_BEFORE=$(api "$BASE/api/templates/$TPL_ID" | jqp "__import__('json').dumps(d['rights'])")
SLUG_ANY=$(api "$BASE/api/templates/$TPL_ID" | jqp "
next((a['slug'] for a in d['apps'] if a['is_enabled'] and not a['blocked_reason']), '')")

if [ -n "$TPL_ID" ] && [ -n "$SLUG_ANY" ]; then
  api -X PUT "$BASE/api/templates/$TPL_ID" -H 'Content-Type: application/json' \
       -d "$(api "$BASE/api/templates/$TPL_ID" | python3 -c '
import json, sys
d = json.load(sys.stdin)
d["rights"] = dict(d.get("rights") or {}, clipboardUp=False, clipboardDown=False)
keep = ("friendly_name","description","icon","categories","mode","image_ref","cores",
        "memory_bytes","x_res","y_res","idle_minutes","idle_action","persistence_scope",
        "rights","env","start_script","is_enabled","group_ids")
print(json.dumps({k: d[k] for k in keep if k in d}))')" >/dev/null

  # Die Brücke wird bei jedem App-Start neu entschieden.
  api -X POST "$BASE/api/sessions/$SID/apps/$SLUG_ANY" >/dev/null 2>&1
  sleep 3
  OFF=$(docker exec "$CN" bash -c \
    '[ -f /tmp/ota-clipboard.pid ] && kill -0 "$(cat /tmp/ota-clipboard.pid)" 2>/dev/null && echo ja || echo nein' \
    2>/dev/null)
  [ "$OFF" = "nein" ] \
    && ok "Abgeschaltet heisst abgeschaltet — die Brücke läuft nicht" \
    || bad "Die Brücke läuft weiter, obwohl die Zwischenablage aus ist"

  # Und wieder an, sonst hinterlässt der Test eine stumme Anlage.
  api -X PUT "$BASE/api/templates/$TPL_ID" -H 'Content-Type: application/json' \
    -d "$(api "$BASE/api/templates/$TPL_ID" | RB="$RIGHTS_BEFORE" python3 -c '
import json, os, sys
d = json.load(sys.stdin)
d["rights"] = json.loads(os.environ["RB"])
keep = ("friendly_name","description","icon","categories","mode","image_ref","cores",
        "memory_bytes","x_res","y_res","idle_minutes","idle_action","persistence_scope",
        "rights","env","start_script","is_enabled","group_ids")
print(json.dumps({k: d[k] for k in keep if k in d}))')" >/dev/null
  api -X POST "$BASE/api/sessions/$SID/apps/$SLUG_ANY" >/dev/null 2>&1
  sleep 3
  BACK=$(docker exec "$CN" bash -c \
    '[ -f /tmp/ota-clipboard.pid ] && kill -0 "$(cat /tmp/ota-clipboard.pid)" 2>/dev/null && echo ja || echo nein' \
    2>/dev/null)
  [ "$BACK" = "ja" ] \
    && ok "Nach dem Wiedereinschalten läuft sie wieder" \
    || bad "Die Brücke kam nach dem Wiedereinschalten nicht zurück"
else
  bad "Vorlage oder Anwendung für Abnahmefall 10 nicht gefunden"
fi

echo
echo "─────────────────────────────────────"
printf '  bestanden: %d   fehlgeschlagen: %d\n' "$pass" "$fail"
[ "$fail" -eq 0 ] || exit 1
