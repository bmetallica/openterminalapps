#!/usr/bin/env bash
# Prüft die News (Handbuch Kapitel 11, 2026-10-27).
#
#   * Lesen darf jeder Angemeldete, schreiben nur, wer settings.manage hat.
#   * Ein Entwurf bleibt für Nutzer unsichtbar und zählt nicht als neu.
#   * Der Zähler für die Seitenleiste: Veröffentlichen zählt hoch, Öffnen der
#     Seite setzt ihn auf null, eine spätere Korrektur zählt nicht erneut.
#   * Angeheftete Beiträge stehen oben; Anlegen, Ändern und Löschen landen im
#     Protokoll.
#
# Legt eigene Beiträge an und löscht sie am Ende wieder.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
[ -f "$ROOT/deploy/.env" ] && [ -z "${OTA_TEST_ADMIN_PW:-}" ] && { set -a; . "$ROOT/deploy/.env"; set +a; }

pass=0; fail=0
ok()  { printf '  \033[32m✓\033[0m %s\n' "$1"; pass=$((pass+1)); }
bad() { printf '  \033[31m✗\033[0m %s\n' "$1"; fail=$((fail+1)); }
expect() { if [ "$2" = "$1" ]; then ok "$3 ($2)"; else bad "$3 — erwartet $1, bekommen $2"; fi; }

B="${OTA_BASE:-https://192.168.66.224:8443}"
TMP="$(mktemp -d)"
ADMIN="${OTA_TEST_ADMIN:-notfall}"
ADMIN_PW="${OTA_TEST_ADMIN_PW:?OTA_TEST_ADMIN_PW fehlt}"
NUTZER="ota-testnutzer"
NUTZER_PW="TestNutzer2026!ab"

api()  { local j="$1"; shift; curl -sk -b "$TMP/$j.jar" -c "$TMP/$j.jar" -H 'Content-Type: application/json' "$@"; }
code() { local j="$1"; shift; curl -sk -o /dev/null -w '%{http_code}' -b "$TMP/$j.jar" -H 'Content-Type: application/json' "$@"; }
jqp()  { python3 -c "import sys,json;d=json.load(sys.stdin);print($1)" 2>/dev/null; }
login() { api "$1" -X POST "$B/api/auth/login" -d "{\"username\":\"$2\",\"password\":\"$3\"}" >/dev/null; }

EINS=""; ZWEI=""
aufraeumen() {
  for n in "$EINS" "$ZWEI"; do
    [ -n "$n" ] && api a -X DELETE "$B/api/news/$n" >/dev/null
  done
  rm -rf "$TMP"
}
trap aufraeumen EXIT

echo "News"
login a "$ADMIN" "$ADMIN_PW"
"$ROOT/scripts/lokales-testkonto.sh" "$NUTZER" "$NUTZER_PW" "$NUTZER@ota.invalid" users >/dev/null
login u "$NUTZER" "$NUTZER_PW"

expect 401 "$(curl -sk -o /dev/null -w '%{http_code}' "$B/api/news")" "Ohne Anmeldung keine News"
expect 200 "$(code u "$B/api/news")" "Nutzer liest die News"
expect False "$(api u "$B/api/news" | jqp "d['darf_schreiben']")" "… und darf nicht schreiben"
expect True "$(api a "$B/api/news" | jqp "d['darf_schreiben']")" "Verwaltung darf schreiben"
api u -X POST "$B/api/news/gelesen" >/dev/null
expect 0 "$(api u "$B/api/news/ungelesen" | jqp "d['anzahl']")" "Nach dem Öffnen nichts ungelesen"

echo
echo "Rechte"
expect 403 "$(code u -X POST "$B/api/news" -d '{"titel":"x"}')" "Nutzer legt keinen Beitrag an"
expect 422 "$(code a -X POST "$B/api/news" -d '{"titel":""}')" "Leerer Titel abgelehnt"

echo
echo "Entwurf"
EINS=$(api a -X POST "$B/api/news" \
  -d '{"titel":"Prüf-Entwurf","text":"## Wartung\n\n<script>alert(1)</script>","entwurf":true}' | jqp "d['id']")
[ -n "$EINS" ] && ok "Entwurf angelegt" || bad "Entwurf nicht angelegt"
expect None "$(api a "$B/api/news" | jqp "next(b['veroeffentlicht_am'] for b in d['beitraege'] if b['id']=='$EINS')")" \
  "Entwurf hat kein Veröffentlichungsdatum"
expect False "$(api u "$B/api/news" | jqp "any(b['id']=='$EINS' for b in d['beitraege'])")" "Nutzer sieht den Entwurf nicht"
expect 0 "$(api u "$B/api/news/ungelesen" | jqp "d['anzahl']")" "Entwurf zählt nicht als neu"
expect 403 "$(code u -X PUT "$B/api/news/$EINS" -d '{"titel":"x"}')" "Nutzer ändert keinen Beitrag"
expect 403 "$(code u -X DELETE "$B/api/news/$EINS")" "Nutzer löscht keinen Beitrag"

echo
echo "Veröffentlichen"
api a -X PUT "$B/api/news/$EINS" \
  -d '{"titel":"Prüf-Wartung","text":"## Wartung\n\n<script>alert(1)</script>","entwurf":false,"angeheftet":true}' >/dev/null
expect True "$(api u "$B/api/news" | jqp "any(b['id']=='$EINS' for b in d['beitraege'])")" "Nutzer sieht den Beitrag"
expect 1 "$(api u "$B/api/news/ungelesen" | jqp "d['anzahl']")" "Ein Beitrag ungelesen"
expect '<script>alert(1)</script>' \
  "$(api u "$B/api/news" | jqp "next(b['text'] for b in d['beitraege'] if b['id']=='$EINS').split(chr(10))[-1]")" \
  "Text kommt unverändert an (maskiert wird beim Anzeigen)"
api u -X POST "$B/api/news/gelesen" >/dev/null
expect 0 "$(api u "$B/api/news/ungelesen" | jqp "d['anzahl']")" "Nach dem Öffnen gelesen"
api a -X PUT "$B/api/news/$EINS" \
  -d '{"titel":"Prüf-Wartung (korrigiert)","text":"Neu","entwurf":false,"angeheftet":true}' >/dev/null
expect 0 "$(api u "$B/api/news/ungelesen" | jqp "d['anzahl']")" "Korrektur zählt nicht erneut"

echo
echo "Reihenfolge"
ZWEI=$(api a -X POST "$B/api/news" -d '{"titel":"Prüf-Neuer","text":"x"}' | jqp "d['id']")
expect 1 "$(api u "$B/api/news/ungelesen" | jqp "d['anzahl']")" "Zweiter Beitrag ungelesen"
expect "$EINS" "$(api u "$B/api/news" | jqp "d['beitraege'][0]['id']")" "Angehefteter steht oben, obwohl älter"

echo
echo "Protokoll und Löschen"
AKT=$(api a "$B/api/admin/audit?limit=50" | jqp "' '.join(e['action'] for e in d if e.get('object_id') in ('$EINS','$ZWEI'))")
for a in news.created news.updated; do
  grep -qw "$a" <<<"$AKT" && ok "Im Protokoll: $a" || bad "Nicht im Protokoll: $a"
done
expect 200 "$(code a -X DELETE "$B/api/news/$ZWEI")" "Beitrag gelöscht"
expect 404 "$(code a -X PUT "$B/api/news/$ZWEI" -d '{"titel":"x"}')" "Gelöschter ist weg"
grep -qw news.deleted <<<"$(api a "$B/api/admin/audit?limit=20" | jqp "' '.join(e['action'] for e in d)")" \
  && ok "Im Protokoll: news.deleted" || bad "Nicht im Protokoll: news.deleted"
ZWEI=""

echo
printf '  bestanden: %d   fehlgeschlagen: %d\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
