#!/usr/bin/env bash
# Prüft, was mit Zuhause, Ablage und Sicherungen eines gelöschten Kontos
# geschieht (Einstellungen → Löschen von Konten, Handbuch Kapitel 08):
#
#   * „Behalten“ (Vorgabe): alles bleibt auf der Platte.
#   * „Löschen“ mit Frist: Zuhause und Ablage liegen im Papierkorb, die
#     Verweise unter dem Namen sind weg. Nach der Frist löscht der tägliche
#     Lauf sie endgültig, mit den Sicherungen des Kontos.
#   * Frist 0: sofort.
#   * Die Einstellung ist geprüft und steht im Protokoll.
#
# Läuft auf dem Host (braucht /srv/ota und docker exec). Stellt die
# Einstellung am Ende wieder her.
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
PROF="${OTA_PROFILES_ROOT:-/srv/ota/profiles}"
ABL="${OTA_USERFILES_ROOT:-/srv/ota/userfiles}"
SICH="${OTA_BACKUP_ROOT:-/srv/ota/backups}"
NAMEN=(ota-pruef-daten1 ota-pruef-daten2 ota-pruef-daten3)

api()  { curl -sk -b "$TMP/admin.jar" -c "$TMP/admin.jar" "$@"; }
code() { curl -sk -o /dev/null -w '%{http_code}' -b "$TMP/admin.jar" "$@"; }
jqp()  { python3 -c "import sys,json;d=json.load(sys.stdin);print($1)" 2>/dev/null; }
sql()  { docker exec ota-db psql -U ota -d ota -tAc "$1"; }
uid_von() { api "$BASE/api/admin/users" | jqp "next((u['id'] for u in d if u['username'] == '$1'), '')"; }
setzen() { api -X PUT "$BASE/api/admin/settings" -H 'Content-Type: application/json' -d "$1" >/dev/null; }

anlegen() {  # anlegen <name> -> Kennung; legt Zuhause, Ablage, Verweise und eine Sicherung an
  local n=$1 u
  u=$(api -H 'Content-Type: application/json' -X POST "$BASE/api/admin/users" \
    -d "{\"username\":\"$n\",\"email\":\"$n@ota.invalid\",\"display_name\":\"\",\"password\":\"Pruef-Daten-2026!\",\"group_ids\":[]}" \
    | jqp "d.get('id','')")
  mkdir -p "$PROF/$u/user/Documents" "$ABL/$u"
  echo geheim > "$PROF/$u/user/Documents/brief.txt"; echo x > "$ABL/$u/ablage.txt"
  ln -sfn "$u" "$PROF/$n"; ln -sfn "$u" "$ABL/$n"
  mkdir -p "$SICH/profiles"; echo sicherung > "$SICH/profiles/$n-pruef.tar.zst"
  sql "INSERT INTO backups (id, kind, user_id, username, path, status, trigger, started_at, size_bytes, file_count, log)
       VALUES (gen_random_uuid(), 'profile', '$u', '$n', '$SICH/profiles/$n-pruef.tar.zst', 'ok', 'manual', now(), 0, 0, '')" >/dev/null
  echo "$u"
}

VORHER=""
aufraeumen() {
  [ -n "$VORHER" ] && setzen "$VORHER"
  for n in "${NAMEN[@]}"; do
    u=$(uid_von "$n"); [ -n "$u" ] && api -X DELETE "$BASE/api/admin/users/$u" >/dev/null
    rm -f "$PROF/$n" "$ABL/$n" "$SICH/profiles/$n-pruef.tar.zst"
    sql "DELETE FROM backups WHERE username = '$n' AND user_id IS NULL" >/dev/null
  done
  for k in "${KENNUNGEN[@]:-}"; do
    [ -n "$k" ] || continue
    rm -rf "${PROF:?}/$k" "${ABL:?}/$k" "$PROF/.geloescht/$k" "$PROF/.geloescht/$k.json" \
           "$ABL/.geloescht/$k" "$ABL/.geloescht/$k.json"
  done
  rm -rf "$TMP"
}
KENNUNGEN=()
trap aufraeumen EXIT

echo "Daten gelöschter Konten"
curl -sk -c "$TMP/admin.jar" -o /dev/null -X POST "$BASE/api/auth/login" -H 'Content-Type: application/json' \
  -d "{\"username\":\"$ADMIN\",\"password\":\"$ADMIN_PW\"}"
VORHER=$(api "$BASE/api/admin/settings" | jqp "json.dumps({'konto_daten_loeschen': d['konto_daten_loeschen'], 'konto_daten_frist_tage': d['konto_daten_frist_tage']})")
[ -n "$VORHER" ] && ok "Einstellung lesbar: $VORHER" || bad "Einstellung fehlt in /api/admin/settings"
for n in "${NAMEN[@]}"; do u=$(uid_von "$n"); [ -n "$u" ] && api -X DELETE "$BASE/api/admin/users/$u" >/dev/null; done

expect "400" "$(code -X PUT "$BASE/api/admin/settings" -H 'Content-Type: application/json' \
  -d '{"konto_daten_frist_tage": 400}')" "Eine Frist über 365 Tage wird abgelehnt"
expect "400" "$(code -X PUT "$BASE/api/admin/settings" -H 'Content-Type: application/json' \
  -d '{"konto_daten_frist_tage": -1}')" "… eine negative auch"

# ------------------------------------------------------------ Behalten
echo
echo "Behalten"
setzen '{"konto_daten_loeschen": false, "konto_daten_frist_tage": 30}'
K1=$(anlegen "${NAMEN[0]}"); KENNUNGEN+=("$K1")
MELD=$(api -X DELETE "$BASE/api/admin/users/$K1" | jqp "d['status']")
grep -q "bleiben bestehen" <<<"$MELD" && ok "Rückmeldung: Daten bleiben" || bad "Rückmeldung: $MELD"
[ -f "$PROF/$K1/user/Documents/brief.txt" ] && [ -f "$ABL/$K1/ablage.txt" ] \
  && ok "Zuhause und Ablage liegen weiter da" || bad "Zuhause oder Ablage fehlt"

# ------------------------------------------------------------ Mit Frist
echo
echo "Löschen nach 7 Tagen"
setzen '{"konto_daten_loeschen": true, "konto_daten_frist_tage": 7}'
expect "True 7" "$(api "$BASE/api/admin/settings" | jqp "d['konto_daten_loeschen'], d['konto_daten_frist_tage']" | tr -d '(),')" \
  "Einstellung gespeichert"
expect "1" "$(sql "SELECT count(*) FROM audit_log WHERE action = 'settings.konto_daten'
                   AND detail->>'frist_tage' = '7' AND ts > now() - interval '1 minute'")" \
  "Die Regel steht mit ihrem Wert im Protokoll"
K2=$(anlegen "${NAMEN[1]}"); KENNUNGEN+=("$K2")
MELD=$(api -X DELETE "$BASE/api/admin/users/$K2" | jqp "d['status']")
grep -q "Papierkorb" <<<"$MELD" && ok "Rückmeldung nennt Papierkorb und Datum" || bad "Rückmeldung: $MELD"
[ ! -e "$PROF/$K2" ] && [ ! -e "$ABL/$K2" ] && ok "Zuhause und Ablage sind nicht mehr an ihrem Platz" \
  || bad "Zuhause oder Ablage liegt noch an ihrem Platz"
[ ! -L "$PROF/${NAMEN[1]}" ] && [ ! -L "$ABL/${NAMEN[1]}" ] && ok "Die Verweise unter dem Namen sind weg" \
  || bad "Ein Verweis unter dem Namen ist geblieben"
[ -f "$PROF/.geloescht/$K2/user/Documents/brief.txt" ] && [ -f "$ABL/.geloescht/$K2/ablage.txt" ] \
  && ok "Beides liegt im Papierkorb" || bad "Nicht im Papierkorb"
expect "700" "$(stat -c %a "$PROF/.geloescht")" "Der Papierkorb ist nur für root"
expect "1" "$(sql "SELECT count(*) FROM audit_log WHERE action = 'user.daten_entfernt' AND object_id = '${NAMEN[1]}'
                   AND ts > now() - interval '1 minute'")" "Protokoll: Daten entfernt"

papierkorb() { docker exec ota-api python -c "
from ota.db import SessionLocal
from ota import konto_daten
with SessionLocal() as db:
    print(konto_daten.papierkorb_leeren(db))"; }
papierkorb >/dev/null
[ -d "$PROF/.geloescht/$K2" ] && ok "Vor Ablauf der Frist bleibt es im Papierkorb" || bad "Vor der Frist gelöscht"
# Die Frist ablaufen lassen: den Zeitpunkt im Marker acht Tage zurückdrehen.
for r in "$PROF" "$ABL"; do
  python3 - "$r/.geloescht/$K2.json" <<'PY'
import json, sys, time
p = sys.argv[1]; d = json.load(open(p)); d["am"] = int(time.time()) - 8 * 86400; json.dump(d, open(p, "w"))
PY
done
papierkorb >/dev/null
[ ! -e "$PROF/.geloescht/$K2" ] && [ ! -e "$ABL/.geloescht/$K2" ] && [ ! -e "$PROF/.geloescht/$K2.json" ] \
  && ok "Nach der Frist endgültig gelöscht" || bad "Nach der Frist noch da"
[ ! -e "$SICH/profiles/${NAMEN[1]}-pruef.tar.zst" ] && ok "Die Sicherungsdatei ist mit gelöscht" \
  || bad "Die Sicherungsdatei ist noch da"
expect "0" "$(sql "SELECT count(*) FROM backups WHERE username = '${NAMEN[1]}'")" "… und ihre Zeile auch"
expect "1" "$(sql "SELECT count(*) FROM audit_log WHERE action = 'user.daten_geloescht' AND object_id = '${NAMEN[1]}'
                   AND ts > now() - interval '1 minute'")" "Protokoll: endgültig gelöscht"
[ -f "$SICH/profiles/${NAMEN[0]}-pruef.tar.zst" ] && ok "Die Sicherung des Kontos mit „Behalten“ bleibt" \
  || bad "Fremde Sicherung mitgelöscht"

# ------------------------------------------------------------ Sofort
echo
echo "Sofort löschen"
setzen '{"konto_daten_frist_tage": 0}'
K3=$(anlegen "${NAMEN[2]}"); KENNUNGEN+=("$K3")
MELD=$(api -X DELETE "$BASE/api/admin/users/$K3" | jqp "d['status']")
grep -q "jetzt gelöscht" <<<"$MELD" && ok "Rückmeldung: wird jetzt gelöscht" || bad "Rückmeldung: $MELD"
for _ in $(seq 1 20); do [ -e "$PROF/.geloescht/$K3" ] || break; sleep 0.5; done
[ ! -e "$PROF/$K3" ] && [ ! -e "$PROF/.geloescht/$K3" ] && [ ! -e "$ABL/.geloescht/$K3" ] \
  && ok "Zuhause und Ablage sind sofort weg" || bad "Noch nicht gelöscht"
[ ! -e "$SICH/profiles/${NAMEN[2]}-pruef.tar.zst" ] && ok "Die Sicherung auch" || bad "Sicherung noch da"

echo
printf '  bestanden: %d   fehlgeschlagen: %d\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
