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

CN=$(docker ps --filter "label=ota.session_id" --format '{{.Names}}' | head -1)
if [ -z "$CN" ]; then
  echo "Keine laufende Session gefunden. Zuerst einen Arbeitsplatz starten."
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
