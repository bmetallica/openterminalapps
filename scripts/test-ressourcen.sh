#!/usr/bin/env bash
# Prüft, dass geänderte Ressourcen auch vorhandene Container erreichen
# (Handbuch Kapitel 5, 2026-10-08).
#
# Bis dahin galten CPU und RAM nur für Container, die nach der Änderung
# entstanden. Jetzt zieht der Agent sie mit `docker update` nach — laufend,
# pausiert und angehalten —, außer wenn ein laufender Container mehr RAM
# belegt, als die neue Grenze erlaubt: Dann gilt die CPU sofort und der RAM
# ab dem nächsten Start.
#
# Startet eine eigene Session mit dem Notfallkonto, ändert den Workspace und
# eine Abweichung je Nutzer und stellt am Ende beides wieder her.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
[ -f "$ROOT/deploy/.env" ] && { set -a; . "$ROOT/deploy/.env"; set +a; }

pass=0; fail=0
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; pass=$((pass+1)); }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$1"; fail=$((fail+1)); }
expect() { if [ "$2" = "$1" ]; then ok "$3"; else bad "$3 — erwartet $1, bekommen $2"; fi; }

BASE="${1:-https://192.168.66.224:8443}"
TMP="$(mktemp -d)"
ADMIN="${OTA_TEST_ADMIN:-notfall}"
ADMIN_PW="${OTA_TEST_ADMIN_PW:?OTA_TEST_ADMIN_PW fehlt}"
GIB=$((1024 * 1024 * 1024))

api() { curl -sk -b "$TMP/a.jar" -c "$TMP/a.jar" -H 'Content-Type: application/json' "$@"; }
jqp() { python3 -c "import sys,json;d=json.load(sys.stdin);print($1)" 2>/dev/null; }

SID=""; T=""; ME=""
aufraeumen() {
  [ -n "$SID" ] && api -X DELETE "$BASE/api/sessions/$SID" >/dev/null
  if [ -n "$T" ] && [ -f "$TMP/vorher.json" ]; then
    api -X PUT "$BASE/api/templates/$T" -d @"$TMP/vorher.json" >/dev/null
    api -X PUT "$BASE/api/templates/$T/overrides" \
      -d "{\"scope\":\"user\",\"target_id\":\"$ME\",\"cores\":null,\"memory_bytes\":null}" >/dev/null
  fi
  rm -rf "$TMP"
}
trap aufraeumen EXIT

echo "Ressourcen vorhandener Container"
curl -sk -c "$TMP/a.jar" -o /dev/null -X POST "$BASE/api/auth/login" -H 'Content-Type: application/json' \
  -d "{\"username\":\"$ADMIN\",\"password\":\"$ADMIN_PW\"}"
ME=$(api "$BASE/api/auth/me" | jqp "d['id']")

# Ein leichter Workspace, der eingeschaltet ist und keiner der Root-Klasse —
# Root-Arbeitsplätze prüft scripts/test-root-arbeitsplatz.sh.
T=$(api "$BASE/api/templates" | jqp "next((t['id'] for t in d if t['is_enabled'] and t['klasse'] == 'standard' and t['mode'] == 'app'), next(t['id'] for t in d if t['is_enabled'] and t['klasse'] == 'standard'))")
[ -n "$T" ] || { bad "Kein Workspace zum Prüfen gefunden"; exit 1; }
api "$BASE/api/templates" | jqp "json.dumps(next(t for t in d if t['id'] == '$T'))" > "$TMP/vorher.json"
for n in 1 2 3; do
  SID=$(api -X POST "$BASE/api/sessions" -d "{\"template_id\":\"$T\"}" | jqp "d.get('id','')")
  [ -n "$SID" ] && break
  sleep 5
done
[ -n "$SID" ] || { bad "Session ließ sich nicht starten"; exit 1; }
C=$(docker ps -a --format '{{.Names}}' | grep "^ota-s-${SID:0:12}" | head -1)
grenzen() { docker inspect "$C" --format '{{.HostConfig.NanoCpus}} {{.HostConfig.Memory}}'; }
mit() {  # mit <Kerne> <Bytes> -> „<NanoCpus> <Bytes>"
  python3 -c "print(int($1 * 1e9), $2)"
}
echo "  (Session ${SID:0:8} in $C)"

aendern() {  # aendern <Kerne> <Bytes> -> Hinweis aus der Antwort
  jqp "json.dumps(dict(d, cores=$1, memory_bytes=$2))" < "$TMP/vorher.json" > "$TMP/neu.json"
  api -X PUT "$BASE/api/templates/$T" -d @"$TMP/neu.json" | jqp "d.get('ressourcen_hinweis') or ''"
}
abweichung() {  # abweichung <Kerne|null> <Bytes|null> -> status
  api -X PUT "$BASE/api/templates/$T/overrides" \
    -d "{\"scope\":\"user\",\"target_id\":\"$ME\",\"cores\":$1,\"memory_bytes\":$2}" | jqp "d['status']"
}

echo
echo "Laufend"
H=$(aendern 3.0 $((3 * GIB)))
expect "$(mit 3.0 $((3 * GIB)))" "$(grenzen)" "Workspace größer gestellt: der laufende Container folgt"
grep -q "sofort angepasst" <<<"$H" && ok "Die Antwort sagt es ($H)" || bad "Hinweis: '$H'"
H=$(abweichung 1.0 $((GIB + GIB / 2)))
expect "$(mit 1.0 $((GIB + GIB / 2)))" "$(grenzen)" "Abweichung je Nutzer: der Container folgt"
grep -q "sofort angepasst" <<<"$H" && ok "… und die Antwort sagt es" || bad "Hinweis: '$H'"
H=$(abweichung 0.5 $((8 * 1024 * 1024)))
expect "$(mit 0.5 $((GIB + GIB / 2)))" "$(grenzen)" "RAM unter dem Verbrauch: CPU sofort, RAM bleibt"
grep -q "ab dem nächsten Start" <<<"$H" && ok "… und die Antwort sagt, wann er gilt" || bad "Hinweis: '$H'"
H=$(abweichung null null)
expect "$(mit 3.0 $((3 * GIB)))" "$(grenzen)" "Abweichung entfernt: wieder die Werte des Workspaces"

echo
echo "Pausiert"
api -X POST "$BASE/api/sessions/$SID/pause" >/dev/null
expect "paused" "$(docker inspect "$C" --format '{{.State.Status}}')" "Session pausiert"
aendern "$(jqp "d['cores']" < "$TMP/vorher.json")" "$(jqp "d['memory_bytes']" < "$TMP/vorher.json")" >/dev/null
expect "$(mit "$(jqp "d['cores']" < "$TMP/vorher.json")" "$(jqp "d['memory_bytes']" < "$TMP/vorher.json")")" \
  "$(grenzen)" "Zurück auf die alten Werte: auch der pausierte Container folgt"

echo
printf '  bestanden: %d   fehlgeschlagen: %d\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
