#!/usr/bin/env bash
# Prüft die Seite Datenschutz (Handbuch Kapitel 42):
#
#   * Die Systemgruppe „datenschutz“ gibt es, mit genau dem Recht
#     datenschutz.pruefen.
#   * Ein Konto in dieser Gruppe sieht Lagebild, Berechtigungen, Zugriffe und
#     Prüfprotokoll; es darf den Datenschutzhinweis ändern und eine Auskunft
#     erstellen — aber nichts verwalten: keine Einstellungen, keine Konten,
#     keine Gruppen, nicht die KI-Nutzung einzelner Menschen, nicht den
#     Inhalt der Fallberichte.
#   * Ein Konto ohne das Recht bekommt 403.
#   * Auskunft nur mit Begründung; Begründung, CSV-Export und die Suche nach
#     einer Person stehen im Prüfprotokoll.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
[ -f "$ROOT/deploy/.env" ] && { set -a; . "$ROOT/deploy/.env"; set +a; }

pass=0; fail=0
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; pass=$((pass+1)); }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$1"; fail=$((fail+1)); }
expect() { if [ "$2" = "$1" ]; then ok "$3"; else bad "$3 — erwartet $1, bekommen $2"; fi; }

BASE="${1:-$("$(dirname "$0")/ota-adresse.sh")}"
TMP="$(mktemp -d)"
ADMIN="${OTA_TEST_ADMIN:-notfall}"
ADMIN_PW="${OTA_TEST_ADMIN_PW:?OTA_TEST_ADMIN_PW fehlt}"
DSB=ota-pruef-dsb
NUTZER=ota-pruef-dsb-nutzer
PW='Pruef-Datenschutz-2026!'
LAUF="$(date +%s)$$"
# Protokolleinträge früherer Läufe tragen denselben Kontonamen: nur ab jetzt zählen.
START="$(date -u +%Y-%m-%dT%H:%M:%S+00)"

api()  { curl -sk -b "$TMP/admin.jar" -c "$TMP/admin.jar" "$@"; }
dsb()  { curl -sk -b "$TMP/dsb.jar" "$@"; }
dcode() { curl -sk -o /dev/null -w '%{http_code}' -b "$TMP/dsb.jar" "$@"; }
ncode() { curl -sk -o /dev/null -w '%{http_code}' -b "$TMP/nutzer.jar" "$@"; }
jqp()  { python3 -c "import sys,json;d=json.load(sys.stdin);print($1)" 2>/dev/null; }
sql()  { docker exec ota-db psql -U ota -d ota -tAc "$1"; }
uid_von() { api "$BASE/api/admin/users" | jqp "next((u['id'] for u in d if u['username'] == '$1'), '')"; }

HINWEIS_VORHER=""
aufraeumen() {
  # Den Datenschutzhinweis so hinterlassen, wie er war.
  if [ -n "$HINWEIS_VORHER" ]; then
    api -X PUT "$BASE/api/dsgvo" -H 'Content-Type: application/json' -d "$HINWEIS_VORHER" >/dev/null
  fi
  for n in "$DSB" "$NUTZER"; do
    u=$(uid_von "$n"); [ -n "$u" ] && api -X DELETE "$BASE/api/admin/users/$u" >/dev/null
  done
  rm -rf "$TMP"
}
trap aufraeumen EXIT

echo "Datenschutz"
curl -sk -c "$TMP/admin.jar" -o /dev/null -X POST "$BASE/api/auth/login" -H 'Content-Type: application/json' \
  -d "{\"username\":\"$ADMIN\",\"password\":\"$ADMIN_PW\"}"
HINWEIS_VORHER=$(api "$BASE/api/dsgvo" | jqp "json.dumps({'text': d['text']})")

expect '["datenschutz.pruefen"]' "$(sql "SELECT permissions::text FROM groups WHERE slug = 'datenschutz' AND is_system")" \
  "Systemgruppe datenschutz mit genau dem Recht datenschutz.pruefen"
expect "True" "$(api "$BASE/api/admin/permissions" | jqp "any(p['key'] == 'datenschutz.pruefen' for p in d)")" \
  "Das Recht steht in der Liste der vergebbaren Rechte"

"$ROOT/scripts/lokales-testkonto.sh" "$DSB" "$PW" "$DSB@ota.invalid" users,datenschutz >/dev/null
"$ROOT/scripts/lokales-testkonto.sh" "$NUTZER" "$PW" "$NUTZER@ota.invalid" users >/dev/null
DSB_ID=$(uid_von "$DSB"); NUTZER_ID=$(uid_von "$NUTZER")
for n in dsb nutzer; do
  name=$DSB; [ "$n" = nutzer ] && name=$NUTZER
  curl -sk -c "$TMP/$n.jar" -o /dev/null -X POST "$BASE/api/auth/login" -H 'Content-Type: application/json' \
    -d "{\"username\":\"$name\",\"password\":\"$PW\"}"
done
expect "True" "$(dsb "$BASE/api/auth/me" | jqp "'datenschutz.pruefen' in d['permissions'] and not d['is_admin']")" \
  "Prüfkonto in der Gruppe datenschutz, ohne Admin"

echo
echo "Was die Gruppe sieht"
LAGE=$(dsb "$BASE/api/datenschutz/lage")
expect "True" "$(jqp "{'protokoll','syslog','ki_statistik','ki_sicherheit','fallberichte','konto_daten','sicherungen','hinweis'} <= {p['id'] for p in d['punkte']}" <<<"$LAGE")" \
  "Lagebild: Protokoll, Syslog, KI-Statistik, KI-Sicherheit, Fallberichte, Konten, Sicherungen, Hinweis"
expect "True" "$(jqp "isinstance(d['hinweise'], list)" <<<"$LAGE")" "Lagebild: Hinweise"
RECHTE=$(dsb "$BASE/api/datenschutz/rechte")
expect "True" "$(jqp "any(g['name'] == 'datenschutz' and any(m['konto'] == '$DSB' for m in g['mitglieder']) for g in d['gruppen'])" <<<"$RECHTE")" \
  "Berechtigungen: Gruppen mit weitreichenden Rechten und ihre Mitglieder"
expect "False" "$(jqp "any(g['name'] == 'users' for g in d['gruppen'])" <<<"$RECHTE")" "… ohne Gruppen ganz ohne weitreichende Rechte"
expect "200" "$(dcode "$BASE/api/datenschutz/protokoll?art=zugriffe")" "Zugriffe"
expect "200" "$(dcode "$BASE/api/datenschutz/protokoll?art=einstellungen&von=2026-01-01")" "Prüfprotokoll mit Filtern"
expect "400" "$(dcode "$BASE/api/datenschutz/protokoll?art=Irgendwas%20anderes")" "Unbekannte Art: 400"
expect "True" "$(dsb "$BASE/api/datenschutz/personen?q=$NUTZER" | jqp "any(p['konto'] == '$NUTZER' for p in d)")" "Personensuche"

echo
echo "Was die Gruppe nicht darf"
expect "403" "$(dcode "$BASE/api/admin/settings")" "Einstellungen: 403"
expect "403" "$(dcode "$BASE/api/admin/users")" "Konten verwalten: 403"
expect "403" "$(dcode "$BASE/api/admin/groups")" "Gruppen verwalten: 403"
expect "403" "$(dcode "$BASE/api/admin/ki-nutzung/personen")" "KI-Nutzung einzelner Menschen: 403"
expect "403" "$(dcode "$BASE/api/admin/ki-sicherheit/faelle")" "Fallberichte der KI-Sicherheit: 403"
expect "403" "$(dcode -X POST -H 'Content-Type: application/json' -d '{"grund":"Neugier, ohne Anlass"}' \
  "$BASE/api/admin/users/$NUTZER_ID/auskunft")" "Auskunft über den Weg der Verwaltung: 403"
expect "403" "$(ncode "$BASE/api/datenschutz/lage")" "Konto ohne das Recht: Lagebild 403"
expect "403" "$(ncode "$BASE/api/datenschutz/protokoll")" "Konto ohne das Recht: Protokoll 403"
expect "200" "$(curl -sk -o /dev/null -w '%{http_code}' -b "$TMP/admin.jar" "$BASE/api/datenschutz/lage")" "Admin sieht die Seite auch"

echo
echo "Auskunft nach Art. 15"
expect "422" "$(dcode -X POST -H 'Content-Type: application/json' -d '{}' "$BASE/api/datenschutz/auskunft/$NUTZER_ID")" \
  "Ohne Begründung: 422"
expect "422" "$(dcode -X POST -H 'Content-Type: application/json' -d '{"grund":"kurz"}' "$BASE/api/datenschutz/auskunft/$NUTZER_ID")" \
  "Zu kurze Begründung: 422"
GRUND="Antrag vom heute, Az. PRUEF-$LAUF"
KOPF=$(dsb -D - -o "$TMP/a.zip" -X POST -H 'Content-Type: application/json' -d "{\"grund\":\"$GRUND\"}" \
  "$BASE/api/datenschutz/auskunft/$NUTZER_ID" | tr -d '\r')
grep -qi "^content-type: application/zip" <<<"$KOPF" && ok "Mit Begründung: ein ZIP" || bad "Kein ZIP: $(head -3 <<<"$KOPF")"
python3 -c 'import zipfile,sys; n=zipfile.ZipFile(sys.argv[1]).namelist(); sys.exit(0 if "konto.json" in n else 1)' "$TMP/a.zip" \
  && ok "… mit konto.json" || bad "… mit konto.json"
expect "1" "$(sql "SELECT count(*) FROM audit_log WHERE action = 'user.auskunft' AND object_id = '$NUTZER_ID' AND actor_name = '$DSB' AND ts >= '$START' AND detail->>'grund' = '$GRUND'")" \
  "Steht mit Name und Begründung im Prüfprotokoll"

echo
echo "Protokoll über die Prüfung selbst"
dsb -o "$TMP/p.csv" "$BASE/api/datenschutz/protokoll.csv?art=einsicht"
head -c 3 "$TMP/p.csv" | od -An -tx1 | grep -q "ef bb bf" && ok "CSV-Export mit BOM für Excel" || bad "CSV-Export mit BOM für Excel"
grep -q "user.auskunft" "$TMP/p.csv" && ok "… enthält die eben erstellte Auskunft" || bad "… enthält die eben erstellte Auskunft"
expect "1" "$(sql "SELECT count(*) FROM audit_log WHERE action = 'datenschutz.protokoll_exportiert' AND actor_name = '$DSB' AND ts >= '$START'")" \
  "Der Export steht im Prüfprotokoll"
dsb -o /dev/null "$BASE/api/datenschutz/protokoll?person=$NUTZER_ID"
dsb -o /dev/null "$BASE/api/datenschutz/protokoll?person=$NUTZER_ID&seite=2"
expect "1" "$(sql "SELECT count(*) FROM audit_log WHERE action = 'datenschutz.protokoll_person' AND actor_name = '$DSB' AND ts >= '$START' AND object_id = '$NUTZER_ID'")" \
  "Suche nach einer Person steht im Prüfprotokoll, einmal statt je Seite"
expect "True" "$(dsb "$BASE/api/datenschutz/protokoll?person=$NUTZER_ID" | jqp "any(e['aktion'] == 'user.auskunft' for e in d['eintraege'])")" \
  "Filter nach Person findet die Auskunft über sie"
expect "True" "$(dsb "$BASE/api/datenschutz/protokoll?art=einsicht" | jqp "d['gesamt'] >= 1 and d['je_seite'] == 100")" \
  "Zugriffe seitenweise, mit Gesamtzahl"

echo
echo "Datenschutzhinweis"
expect "True" "$(dsb "$BASE/api/dsgvo" | jqp "d['darf_schreiben'] and d['sichtbar']")" "Die Gruppe darf den Hinweis ändern"
expect "200" "$(dcode -X PUT "$BASE/api/dsgvo" -H 'Content-Type: application/json' -d "{\"text\":\"## Prüfhinweis $LAUF\"}")" \
  "Hinweis geändert"
expect "1" "$(sql "SELECT count(*) FROM audit_log WHERE action = 'dsgvo.hinweis_geaendert' AND actor_name = '$DSB' AND ts >= '$START'")" "… steht im Prüfprotokoll"
expect "403" "$(ncode -X PUT "$BASE/api/dsgvo" -H 'Content-Type: application/json' -d '{"text":"x"}')" "Konto ohne das Recht darf es nicht"

echo
printf '  bestanden: %d   fehlgeschlagen: %d\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
