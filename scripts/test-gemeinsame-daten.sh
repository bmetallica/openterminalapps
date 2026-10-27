#!/usr/bin/env bash
# Prüft Persistenz „Eigene Einstellungen, gemeinsame Daten" (Handbuch
# Kapitel 5 und 25, 2026-10-27) — mit zwei Root-Arbeitsplätzen desselben
# Kontos, die gleichzeitig laufen.
#
#   * Beide starten, obwohl sie dasselbe gemeinsame Zuhause benutzen.
#   * Jeder hat sein eigenes Zuhause: Einstellungen des einen sieht der
#     andere nicht.
#   * Die Datenordner sind dieselben: Was der eine ablegt, sieht der andere
#     sofort, und es liegt im gemeinsamen Zuhause auf dem Wirt.
#   * Die Ordner gehören 1000, auch die, die Docker sonst als root anlegte.
#   * Ordner, die aus dem Zuhause hinausführen oder versteckt sind, lehnt die
#     API ab.
#
# Legt zwei eigene Vorlagen an und räumt sie samt Arbeitsplätzen, ihrer
# eigenen Zuhause und dem Prüfordner im gemeinsamen Zuhause wieder weg.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
[ -f "$ROOT/deploy/.env" ] && { set -a; . "$ROOT/deploy/.env"; set +a; }

pass=0; fail=0
ok()  { printf '  \033[32m✓\033[0m %s\n' "$1"; pass=$((pass+1)); }
bad() { printf '  \033[31m✗\033[0m %s\n' "$1"; fail=$((fail+1)); }

B="${OTA_BASE:-https://127.0.0.1:${OTA_HTTPS_PORT:-8443}}"
TMP="$(mktemp -d)"
ADMIN="${OTA_TEST_ADMIN:-notfall}"
ADMIN_PW="${OTA_TEST_ADMIN_PW:?OTA_TEST_ADMIN_PW fehlt. Trag es in deploy/.env ein.}"
IMAGE="${OTA_ROOT_TAG:-ota/base-desktop-root:1}"
PRUEF="ota-pruef-daten-$RANDOM"

api()  { curl -sk -b "$TMP/jar" -c "$TMP/jar" -H 'Content-Type: application/json' "$@"; }
code() { curl -sk -o /dev/null -w '%{http_code}' -b "$TMP/jar" -H 'Content-Type: application/json' "$@"; }
jqp()  { python3 -c "import sys,json;d=json.load(sys.stdin);print($1)" 2>/dev/null; }
drin() { docker exec -u 1000 "$1" bash -lc "$2" 2>&1; }
heim() { docker inspect "$1" -f '{{range .Mounts}}{{if eq .Destination "'"$2"'"}}{{.Source}}{{end}}{{end}}'; }

K1=""; K2=""; T1=""; T2=""; S1=""; S2=""; H1=""; H2=""; GEMEINSAM=""
aufraeumen() {
  for s in "$S1" "$S2"; do
    [ -n "$s" ] && api -X DELETE "$B/api/admin/arbeitsplaetze/$s" >/dev/null 2>&1
  done
  for t in "$T1" "$T2"; do
    [ -n "$t" ] && api -X DELETE "$B/api/templates/$t" >/dev/null 2>&1
  done
  # Nur, was dieser Lauf angelegt hat: die beiden eigenen Zuhause (Pfad
  # endet auf die Kennung einer der Probevorlagen) und der Prüfordner.
  for h in "$H1" "$H2"; do
    case "${h##*/}" in "$K1"|"$K2") [ -n "${h##*/}" ] && rm -rf "$h" ;; esac
  done
  [ -n "$GEMEINSAM" ] && rm -rf "${GEMEINSAM:?}/$PRUEF"
  rm -rf "$TMP"
}
trap aufraeumen EXIT

echo "Eigene Einstellungen, gemeinsame Daten"

if ! docker info 2>/dev/null | grep sysbox-runc >/dev/null; then
  echo "  (übersprungen — Sysbox ist auf diesem Wirt nicht eingerichtet, Kapitel 25)"
  exit 0
fi
if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "  (übersprungen — $IMAGE fehlt:  make root-image)"
  exit 0
fi

[ "$(code -c "$TMP/jar" -X POST "$B/api/auth/login" \
  -d "{\"username\":\"$ADMIN\",\"password\":\"$ADMIN_PW\"}")" = "200" ] \
  || { bad "Anmeldung als $ADMIN scheiterte"; exit 1; }

# ------------------------------------------------------------------ Prüfung
echo
echo "Eingaben"
vorlage() {  # $1 Name, $2 Ordnerliste (JSON)
  api -X POST "$B/api/templates" -d "{
    \"friendly_name\": \"$1\", \"image_ref\": \"$IMAGE\",
    \"cores\": 1, \"memory_bytes\": 2147483648, \"klasse\": \"root\",
    \"platz_grenze_gb\": 20, \"stream_engine\": \"selkies\", \"mode\": \"workspace\",
    \"persistence_scope\": \"daten\", \"daten_ordner\": $2}"
}
for boese in '["../raus"]' '[".ssh"]' '["a/../../b"]' '["/etc"]'; do
  # "/etc" wird zu "etc" — relativ, also erlaubt; alles andere nicht.
  c=$(curl -sk -o "$TMP/v.json" -w '%{http_code}' -b "$TMP/jar" -H 'Content-Type: application/json' \
      -X POST "$B/api/templates" -d "{\"friendly_name\":\"Prüfung böse\",\"image_ref\":\"$IMAGE\",
      \"cores\":1,\"memory_bytes\":1073741824,\"persistence_scope\":\"daten\",\"daten_ordner\":$boese}")
  if [ "$boese" = '["/etc"]' ]; then
    [ "$c" = "201" ] && ok "„/etc“ wird zu „etc“ im Zuhause" || bad "„/etc“: $c"
    api -X DELETE "$B/api/templates/$(jqp "d['id']" <"$TMP/v.json")" >/dev/null
  else
    [ "$c" = "422" ] && ok "Abgelehnt: $boese" || bad "Nicht abgelehnt: $boese ($c)"
  fi
done
[ "$(code -X POST "$B/api/templates" -d "{\"friendly_name\":\"x\",\"image_ref\":\"$IMAGE\",
  \"cores\":1,\"memory_bytes\":1073741824,\"persistence_scope\":\"irgendwas\"}")" = "422" ] \
  && ok "Unbekannte Persistenz wird abgelehnt" || bad "Unbekannte Persistenz angenommen"

# ------------------------------------------------------------------ Start
echo
echo "Zwei Root-Arbeitsplätze gleichzeitig"
ORDNER="[\"Desktop\", \"$PRUEF/tief\"]"
T1=$(vorlage "Prüfung Daten A" "$ORDNER" | jqp "d['id']")
T2=$(vorlage "Prüfung Daten B" "$ORDNER" | jqp "d['id']")
K1=$(api "$B/api/templates/$T1" | jqp "d['slug']"); K2=$(api "$B/api/templates/$T2" | jqp "d['slug']")
[ -n "$T1" ] && [ -n "$T2" ] && ok "Zwei Vorlagen mit „Gemeinsame Daten“" || { bad "Vorlagen nicht anlegbar"; exit 1; }
[ "$(api "$B/api/templates/$T1" | jqp "d['daten_ordner']")" = "['Desktop', '$PRUEF/tief']" ] \
  && ok "Ordnerliste gespeichert" || bad "Ordnerliste nicht gespeichert"

starte() {
  api -X POST "$B/api/sessions" -d "{\"template_id\":\"$1\"}" >"$TMP/s.json"
  [ "$(jqp "d.get('status')" <"$TMP/s.json")" = "running" ] && jqp "d['id']" <"$TMP/s.json"
}
S1=$(starte "$T1") && ok "A gestartet" || { bad "A: $(jqp "d.get('detail')" <"$TMP/s.json")"; exit 1; }
S2=$(starte "$T2") && ok "B gestartet, während A läuft" || { bad "B: $(jqp "d.get('detail')" <"$TMP/s.json")"; exit 1; }
C1="ota-s-${S1:0:12}"; C2="ota-s-${S2:0:12}"
[ "$(docker inspect -f '{{.State.Running}}' "$C1")" = "true" ] && ok "A läuft noch" || bad "A läuft nicht mehr"

HOME1=$(drin "$C1" 'echo $HOME'); HOME2=$(drin "$C2" 'echo $HOME')
H1=$(heim "$C1" "$HOME1"); H2=$(heim "$C2" "$HOME2")
GEMEINSAM=$(heim "$C1" "$HOME1/Desktop" | sed 's#/Desktop$##')
[ -n "$H1" ] && [ -n "$H2" ] && [ "$H1" != "$H2" ] \
  && ok "Zwei eigene Zuhause (…/${H1##*/}, …/${H2##*/})" || bad "Zuhause nicht getrennt: $H1 / $H2"
[ "${GEMEINSAM##*/}" = "user" ] && ok "Desktop kommt aus dem gemeinsamen Zuhause" \
  || bad "Desktop kommt von: ${GEMEINSAM:-nirgends}"
[ "$(heim "$C2" "$HOME2/$PRUEF/tief")" = "$GEMEINSAM/$PRUEF/tief" ] \
  && ok "Verschachtelter Ordner in beiden eingehängt" || bad "Verschachtelter Ordner fehlt in B"

# ------------------------------------------------------------------ Innen
echo
echo "Im Arbeitsplatz"
[ "$(drin "$C1" "stat -c %u \$HOME/Desktop \$HOME/$PRUEF \$HOME/$PRUEF/tief" | sort -u)" = "1000" ] \
  && ok "Die Ordner gehören 1000, auch die Zwischenstufe" || bad "Falsche Eigentümer"
drin "$C1" "echo von-a > \$HOME/$PRUEF/tief/notiz.txt" >/dev/null
[ "$(drin "$C2" "cat \$HOME/$PRUEF/tief/notiz.txt")" = "von-a" ] \
  && ok "Was A ablegt, sieht B" || bad "B sieht die Datei von A nicht"
[ "$(cat "$GEMEINSAM/$PRUEF/tief/notiz.txt" 2>/dev/null)" = "von-a" ] \
  && ok "…und sie liegt im gemeinsamen Zuhause auf dem Wirt" || bad "Datei fehlt im gemeinsamen Zuhause"
drin "$C1" 'echo a > $HOME/.ota-pruef-einstellung' >/dev/null
[ "$(drin "$C2" 'test -e $HOME/.ota-pruef-einstellung && echo da || echo weg')" = "weg" ] \
  && ok "Einstellungen von A sind in B nicht zu sehen" || bad "Einstellungen geteilt"
[ ! -e "$GEMEINSAM/.ota-pruef-einstellung" ] \
  && ok "…und nicht im gemeinsamen Zuhause" || bad "Einstellung im gemeinsamen Zuhause"

echo
echo "─────────────────────────────────────"
printf '  bestanden: %s   fehlgeschlagen: %s\n' "$pass" "$fail"
[ "$fail" = "0" ]
