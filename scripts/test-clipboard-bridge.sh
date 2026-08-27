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
JAR="$(mktemp)"; trap 'rm -f "$JAR"' EXIT
ADMIN="${OTA_TEST_ADMIN:-bmetallica}"
ADMIN_PW="${OTA_TEST_ADMIN_PW:-OtaStart2026!xyz}"

api() { curl -s --cacert "$CA" -b "$JAR" -c "$JAR" "$@"; }
jqp() { python3 -c "import sys,json;d=json.load(sys.stdin);print($1)" 2>/dev/null; }

# Der Test braucht einen Arbeitsplatz mit mindestens zwei offenen Apps.
# Statt das vorauszusetzen, stellt er es selbst her — sonst haengt sein
# Ergebnis davon ab, was ein vorheriger Test hinterlassen hat.
ensure_workspace() {
  api -X POST "$BASE/api/auth/login" -H 'Content-Type: application/json' \
      -d "{\"username\":\"$ADMIN\",\"password\":\"$ADMIN_PW\"}" >/dev/null

  local sid
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

CN=$(docker ps --filter "label=ota.session_id" --format '{{.Names}}' | head -1)
DISPLAY_COUNT=0
[ -n "$CN" ] && DISPLAY_COUNT=$(docker exec "$CN" bash -c 'ls /tmp/.X11-unix/ 2>/dev/null | wc -l' 2>/dev/null || echo 0)

if [ "${DISPLAY_COUNT:-0}" -lt 2 ]; then
  echo "Weniger als zwei Displays offen — der Test stellt den Zustand selbst her."
  ensure_workspace || { echo "Kein Arbeitsplatz verfügbar."; exit 1; }
  sleep 4
  CN=$(docker ps --filter "label=ota.session_id" --format '{{.Names}}' | head -1)
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

FIRST=$(echo "$DISPLAYS" | awk '{print $1}')
SECOND=$(echo "$DISPLAYS" | awk '{print $2}')

check_direction() {  # check_direction <von> <nach> <text> <beschreibung>
  local from="$1" to="$2" text="$3" label="$4"
  docker exec -u 1000 "$CN" bash -c "
    export HOME=/home/kasm-user XAUTHORITY=/home/kasm-user/.Xauthority
    printf '%s' \"$text\" | timeout 3 xclip -d :$from -selection clipboard -i" 2>/dev/null
  sleep 2.5
  local got
  got=$(docker exec -u 1000 "$CN" bash -c "
    export HOME=/home/kasm-user XAUTHORITY=/home/kasm-user/.Xauthority
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
  export HOME=/home/kasm-user XAUTHORITY=/home/kasm-user/.Xauthority
  printf '%s' '$MULTI' | timeout 3 xclip -d :$FIRST -selection clipboard -i" 2>/dev/null
sleep 2.5
GOT=$(docker exec -u 1000 "$CN" bash -c "
  export HOME=/home/kasm-user XAUTHORITY=/home/kasm-user/.Xauthority
  timeout 3 xclip -d :$SECOND -selection clipboard -o 2>/dev/null")
[ "$GOT" = "$MULTI" ] && ok "Mehrzeiliger Code mit Tabulator bleibt erhalten" \
                      || bad "Mehrzeiliger Code verändert — bekam: [$GOT]"

echo
echo "─────────────────────────────────────"
printf '  bestanden: %d   fehlgeschlagen: %d\n' "$pass" "$fail"
[ "$fail" -eq 0 ] || exit 1
