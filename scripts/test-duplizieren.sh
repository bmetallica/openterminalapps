#!/usr/bin/env bash
# Prüft Duplizieren von Vorlagen und eigene Namen (Handbuch Kapitel 3 und 5,
# 2026-10-26).
#
#   * Duplizieren: Einstellungen, Apps, Einmal-Skripte, Zuteilungen, Gruppen
#     und Skeleton kommen mit; die Kopie hat eine eigene Kennung, ist
#     ausgeschaltet und zeigt auf dasselbe Image. Nur wer Vorlagen verwaltet,
#     darf duplizieren.
#   * Ein Image, auf das eine andere Vorlage zeigt, räumt das Löschen alter
#     Fassungen nicht weg.
#   * Eigener Name: gilt nur für den, der ihn setzt; die Vorlage und andere
#     bleiben unberührt; leer setzt zurück. Für eine Vorlage, die man nicht
#     sieht, geht es nicht.
#
# Legt eine eigene Probevorlage an und räumt sie samt Kopie und beider
# Skeletons am Ende wieder weg.
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

QUELLE=""; KOPIE=""; Q_SLUG=""; K_SLUG=""
aufraeumen() {
  for t in "$KOPIE" "$QUELLE"; do
    [ -n "$t" ] && api a -X DELETE "$B/api/templates/$t" >/dev/null
  done
  # Nur die beiden eigenen Skeletons — die Kennungen stammen aus diesem Lauf.
  for s in "$Q_SLUG" "$K_SLUG"; do
    [ -n "$s" ] && docker exec ota-agent rm -rf "/srv/ota/skeletons/$s"
  done
  rm -rf "$TMP"
}
trap aufraeumen EXIT

echo "Duplizieren und eigene Namen"
login a "$ADMIN" "$ADMIN_PW"
"$ROOT/scripts/lokales-testkonto.sh" "$NUTZER" "$NUTZER_PW" "$NUTZER@ota.invalid" users >/dev/null
login u "$NUTZER" "$NUTZER_PW"

USERS=$(api a "$B/api/admin/groups" | jqp "next(g['id'] for g in d if g['slug']=='users')")
NID=$(api a "$B/api/admin/users" | jqp "next(u['id'] for u in d if u['username']=='$NUTZER')")
[ -n "$USERS" ] && [ -n "$NID" ] || { bad "Gruppe users oder Testnutzer fehlt"; exit 1; }
# Ein Image, das es nicht gibt und auf das sonst nichts zeigt: Gestartet wird
# hier nichts, und so misst die Prüfung „anderswo genutzt" nur die Kopie.
ABBILD="ota/pruef-duplikat-$RANDOM:v1"

# ------------------------------------------------------------ Probevorlage
NAME="OTA-Prüfvorlage $RANDOM"
QUELLE=$(api a -X POST "$B/api/templates" -d "{
  \"friendly_name\": \"$NAME\", \"image_ref\": \"$ABBILD\", \"mode\": \"workspace\",
  \"stream_engine\": \"selkies\", \"cores\": 1.5, \"memory_bytes\": 3221225472,
  \"klasse\": \"root\", \"platz_grenze_gb\": 77, \"start_script\": \"echo prüf\",
  \"env\": {\"OTA_PRUEF\": \"1\"}, \"rights\": {\"clipboardUp\": true},
  \"group_ids\": [\"$USERS\"]}" | jqp "d['id']")
[ -n "$QUELLE" ] || { bad "Probevorlage nicht angelegt"; exit 1; }
Q_SLUG=$(api a "$B/api/templates/$QUELLE" | jqp "d['slug']")
api a -X PUT "$B/api/templates/$QUELLE/apps" -d '[
  {"slug":"terminal","name":"Terminal","exec_cmd":"xterm"},
  {"slug":"editor","name":"Editor","exec_cmd":"mousepad","x_res":1920,"y_res":1080}]' >/dev/null
api a -X POST "$B/api/templates/$QUELLE/once" -d '{"name":"Prüfskript","body":"true"}' >/dev/null
api a -X PUT "$B/api/templates/$QUELLE/overrides" \
  -d "{\"scope\":\"user\",\"target_id\":\"$NID\",\"cores\":1}" >/dev/null
api a -X POST "$B/api/templates/$QUELLE/skeleton/dir" -d '{"path":"","name":".config"}' >/dev/null
printf 'hallo\n' > "$TMP/gruss.txt"
curl -sk -b "$TMP/a.jar" -F "file=@$TMP/gruss.txt" \
  "$B/api/templates/$QUELLE/skeleton/upload?path=.config" >/dev/null
curl -sk -b "$TMP/a.jar" -F "file=@$TMP/gruss.txt" \
  "$B/api/templates/$QUELLE/skeleton/upload?app=editor" >/dev/null

# --------------------------------------------------------------- Kopieren
expect 403 "$(code u -X POST "$B/api/templates/$QUELLE/duplizieren" -d '{}')" \
  "Ohne Verwaltungsrecht kein Duplizieren"

api a -X POST "$B/api/templates/$QUELLE/duplizieren" -d '{"friendly_name":""}' > "$TMP/kopie.json"
KOPIE=$(jqp "d.get('id','')" < "$TMP/kopie.json")
K_SLUG=$(jqp "d.get('slug','')" < "$TMP/kopie.json")
[ -n "$KOPIE" ] || { bad "Kopie nicht angelegt: $(head -c 300 "$TMP/kopie.json")"; exit 1; }
expect "$NAME (Kopie)" "$(jqp "d['friendly_name']" < "$TMP/kopie.json")" "Name der Kopie ohne Angabe"
[ "$K_SLUG" != "$Q_SLUG" ] && ok "Eigene Kennung ($K_SLUG)" || bad "Kopie hat dieselbe Kennung"
expect False "$(jqp "d['is_enabled']" < "$TMP/kopie.json")" "Kopie ist ausgeschaltet"
expect None "$(jqp "d.get('ressourcen_hinweis')" < "$TMP/kopie.json")" "Kein Hinweis beim Kopieren"

api a "$B/api/templates/$QUELLE" > "$TMP/q.json"
api a "$B/api/templates/$KOPIE" > "$TMP/k.json"
gleich() {  # gleich <python-ausdruck über d> <beschreibung>
  local q k
  q=$(jqp "$1" < "$TMP/q.json"); k=$(jqp "$1" < "$TMP/k.json")
  if [ -n "$q" ] && [ "$q" = "$k" ]; then ok "$2 gleich ($k)"; else bad "$2 — Quelle $q, Kopie $k"; fi
}
gleich "d['image_ref']" "Image"
gleich "(d['klasse'], d['platz_grenze_gb'], d['cores'], d['memory_bytes'])" "Klasse, Platz, Ressourcen"
gleich "(d['start_script'], d['env'], d['rights'])" "Startskript, Umgebung, Rechte"
gleich "sorted(d['group_ids'])" "Gruppen"
gleich "[(a['slug'], a['name'], a['x_res']) for a in d['apps']]" "App-Katalog"
expect "mousepad,xterm" "$(docker exec ota-db psql -U ota -d ota -tAc \
  "SELECT string_agg(exec_cmd, ',' ORDER BY exec_cmd) FROM template_apps WHERE template_id='$KOPIE'")" \
  "Startbefehle der Apps kopiert"

expect 1 "$(api a "$B/api/templates/$KOPIE/once" | jqp "len(d)")" "Einmal-Skript kopiert"
expect "1.0" "$(api a "$B/api/templates/$KOPIE/overrides" | jqp "next((o['cores'] for o in d if o['target_id']=='$NID'), None)")" \
  "Zuteilung je Nutzer kopiert"
expect "gruss.txt" "$(api a "$B/api/templates/$KOPIE/skeleton?path=.config" | jqp "','.join(e['name'] for e in d['eintraege'])")" \
  "Skeleton kopiert"
expect "gruss.txt" "$(api a "$B/api/templates/$KOPIE/skeleton?app=editor" | jqp "','.join(e['name'] for e in d['eintraege'])")" \
  "Skeleton der Anwendung kopiert"
expect 1000 "$(docker exec ota-agent stat -c %u "/srv/ota/skeletons/$K_SLUG/.config/gruss.txt" 2>/dev/null)" \
  "Kopiertes Skeleton gehört 1000"

# Änderungen an der Kopie lassen die Quelle in Ruhe.
api a -X PUT "$B/api/templates/$KOPIE/apps" -d '[{"slug":"terminal","name":"Terminal","exec_cmd":"xterm"}]' >/dev/null
expect 2 "$(api a "$B/api/templates/$QUELLE" | jqp "len(d['apps'])")" "Quelle behält ihre Apps"

# Mit Namen.
ZWEI=$(api a -X POST "$B/api/templates/$QUELLE/duplizieren" -d '{"friendly_name":"  OTA   Prüfkopie zwei "}')
expect "OTA Prüfkopie zwei" "$(echo "$ZWEI" | jqp "d['friendly_name']")" "Gewählter Name, Leerraum bereinigt"
Z_ID=$(echo "$ZWEI" | jqp "d['id']"); Z_SLUG=$(echo "$ZWEI" | jqp "d['slug']")
[ -n "$Z_ID" ] && api a -X DELETE "$B/api/templates/$Z_ID" >/dev/null
[ -n "$Z_SLUG" ] && docker exec ota-agent rm -rf "/srv/ota/skeletons/$Z_SLUG"

expect 404 "$(code a -X POST "$B/api/templates/00000000-0000-0000-0000-000000000000/duplizieren" -d '{}')" \
  "Unbekannte Vorlage"

# ------------------------------------------------------ Geteiltes Image
expect "True False" "$(docker exec -i -e Q="$QUELLE" -e A="$ABBILD" ota-api python - <<'PY' 2>/dev/null
import os, uuid
from ota.db import SessionLocal
from ota.routers.builds import _anderswo_genutzt
db = SessionLocal()
q = uuid.UUID(os.environ["Q"])
print(_anderswo_genutzt(db, os.environ["A"], q), _anderswo_genutzt(db, "ota/gibt-es-nicht:v1", q))
PY
)" "Image der Kopie gilt als anderswo genutzt, ein fremdes nicht"

# ------------------------------------------------------------ Eigener Name
expect 200 "$(code u -X PUT "$B/api/templates/$QUELLE/mein-name" -d '{"name":"  Mein   Labor "}')" \
  "Nutzer benennt seinen Arbeitsplatz um"
expect "Mein Labor" "$(api u "$B/api/templates" | jqp "next(t['eigener_name'] for t in d if t['id']=='$QUELLE')")" \
  "Nutzer sieht seinen Namen"
expect "$NAME" "$(api u "$B/api/templates" | jqp "next(t['friendly_name'] for t in d if t['id']=='$QUELLE')")" \
  "Name der Vorlage bleibt daneben"
expect None "$(api a "$B/api/templates" | jqp "next(t['eigener_name'] for t in d if t['id']=='$QUELLE')")" \
  "Andere (Admin) sehen ihn nicht"
expect "$NAME" "$(api a "$B/api/templates/$QUELLE" | jqp "d['friendly_name']")" "Vorlage unverändert"
expect "Mein Labor" "$(docker exec ota-db psql -U ota -d ota -tAc \
  "SELECT name FROM eigene_namen WHERE template_id='$QUELLE' AND user_id='$NID'")" \
  "Gespeichert je Nutzer und Vorlage"
expect 422 "$(code u -X PUT "$B/api/templates/$QUELLE/mein-name" -d "{\"name\":\"$(printf 'x%.0s' $(seq 81))\"}")" \
  "Mehr als 80 Zeichen abgelehnt"
expect 404 "$(code u -X PUT "$B/api/templates/$KOPIE/mein-name" -d '{"name":"x"}')" \
  "Nicht für eine Vorlage, die man nicht sieht"
expect 200 "$(code u -X PUT "$B/api/templates/$QUELLE/mein-name" -d '{"name":""}')" "Zurücksetzen"
expect None "$(api u "$B/api/templates" | jqp "next(t['eigener_name'] for t in d if t['id']=='$QUELLE')")" \
  "Nach dem Zurücksetzen wieder der Vorlagenname"
api u -X PUT "$B/api/templates/$QUELLE/mein-name" -d "{\"name\":\"$NAME\"}" >/dev/null
expect 0 "$(docker exec ota-db psql -U ota -d ota -tAc \
  "SELECT count(*) FROM eigene_namen WHERE template_id='$QUELLE'")" \
  "Der Vorlagenname als eigener Name legt keinen Eintrag an"

# Mit der Vorlage geht der Name.
api u -X PUT "$B/api/templates/$QUELLE/mein-name" -d '{"name":"Weg damit"}' >/dev/null
api a -X DELETE "$B/api/templates/$QUELLE" >/dev/null && QUELLE_WEG="$QUELLE" && QUELLE=""
expect 0 "$(docker exec ota-db psql -U ota -d ota -tAc \
  "SELECT count(*) FROM eigene_namen WHERE template_id='$QUELLE_WEG'")" \
  "Gelöschte Vorlage nimmt die eigenen Namen mit"

echo
echo "  bestanden: $pass   fehlgeschlagen: $fail"
[ "$fail" -eq 0 ]
