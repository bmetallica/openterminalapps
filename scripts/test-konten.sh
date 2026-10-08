#!/usr/bin/env bash
# Prüft die Konten der zentralen Anmeldung (Handbuch Kapitel 18, 2026-10-08):
#
#   * Ein Konto, das die Verwaltung anlegt, entsteht in Keycloak — mit dem
#     Passwort, das die Verwaltung vergibt, und auf Wunsch der Pflicht, es
#     beim ersten Anmelden zu ändern. Lokal kommt es nicht herein.
#   * Ändern, Passwort setzen, zweiten Faktor zurücksetzen, Löschen wirken
#     in Keycloak; Löschen sperrt dort, erneutes Anlegen verknüpft wieder.
#   * Mein Konto: Passwort und zweiter Faktor über Keycloak; die lokalen
#     Wege sind für solche Konten zu.
#   * Ein lokales Bestandskonto zieht beim Anmelden mit **seinem** Passwort
#     um. Das Notfallkonto bleibt lokal.
#   * /login sagt, ob es noch lokale Konten gibt; ohne leitet es weiter.
#   * Eine Uhr: Keycloaks SSO-Sitzung lebt so lange wie OTAs; OTA haelt sie
#     wach und endet mit ihr.
#
# Konten mit Verzeichnis (AD/LDAP) prüft scripts/test-ldap.sh.
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
NEU="ota-pruef-konto"
ALT="ota-pruef-umzug"
PW1="Erstes-Passwort-2026!"
PW2="Eigenes-Passwort-2026!"

api()  { curl -sk -b "$TMP/admin.jar" -c "$TMP/admin.jar" "$@"; }
code() { curl -sk -o /dev/null -w '%{http_code}' "$@"; }
jqp()  { python3 -c "import sys,json;d=json.load(sys.stdin);print($1)" 2>/dev/null; }
kc()   { python3 "$ROOT/scripts/kc_anmelden.py" "$BASE" "$@"; }
uid_von() { api "$BASE/api/admin/users" | jqp "next((u['id'] for u in d if u['username'] == '$1'), '')"; }
lokal_an() {  # lokal_an <jar> <name> <passwort> -> http-Code
  curl -sk -c "$1" -b "$1" -o /dev/null -w '%{http_code}' -X POST "$BASE/api/auth/login" \
    -H 'Content-Type: application/json' -d "{\"username\":\"$2\",\"password\":\"$3\"}"
}

aufraeumen() {
  for n in "$NEU" "$ALT"; do
    u=$(uid_von "$n"); [ -n "$u" ] && api -X DELETE "$BASE/api/admin/users/$u" >/dev/null
  done
  rm -rf "$TMP"
}
trap aufraeumen EXIT

echo "Konten der zentralen Anmeldung"
expect "200" "$(lokal_an "$TMP/admin.jar" "$ADMIN" "$ADMIN_PW")" "Notfallkonto meldet sich lokal an"
for n in "$NEU" "$ALT"; do u=$(uid_von "$n"); [ -n "$u" ] && api -X DELETE "$BASE/api/admin/users/$u" >/dev/null; done

# ------------------------------------------------------------ Anlegen
echo
echo "Anlegen in OTA → Konto in Keycloak"
ANT=$(api -H 'Content-Type: application/json' -X POST "$BASE/api/admin/users" \
  -d "{\"username\":\"$NEU\",\"email\":\"$NEU@ota.invalid\",\"display_name\":\"Prüf Konto\",\"password\":\"$PW1\",\"passwort_wechseln\":true,\"group_ids\":[]}")
expect "keycloak" "$(jqp "d.get('auth_provider')" <<<"$ANT")" "Das neue Konto gehört der zentralen Anmeldung"
expect "409" "$(lokal_an "$TMP/x.jar" "$NEU" "$PW1")" "Lokal kommt es nicht herein"
grep -q "neues Passwort" <<<"$(kc "$NEU" "$PW1" "$TMP/k1.jar")" \
  && ok "Keycloak verlangt beim ersten Anmelden ein neues Passwort" \
  || bad "Keycloak verlangte kein neues Passwort"
grep -q "^ok $NEU" <<<"$(kc "$NEU" "$PW1" "$TMP/k2.jar" --neu "$PW2")" \
  && ok "Nach dem Wechsel ist es bei OTA angemeldet" || bad "Anmeldung nach dem Wechsel scheiterte"
expect "zentral" "$(curl -sk -b "$TMP/k2.jar" "$BASE/api/auth/konto" | jqp "d.get('art')")" \
  "Mein Konto erkennt es als Konto der zentralen Anmeldung"

# ------------------------------------------------------------ Mein Konto
echo
echo "Mein Konto"
expect "409" "$(code -b "$TMP/k2.jar" -X POST "$BASE/api/auth/password" -H 'Content-Type: application/json' \
  -d '{"current_password":"x","new_password":"y"}')" "Das lokale Passwortformular gilt für dieses Konto nicht"
expect "409" "$(code -b "$TMP/k2.jar" -X POST "$BASE/api/auth/totp/setup")" \
  "OTAs eigener zweiter Faktor auch nicht"
ZIEL=$(curl -sk -o /dev/null -w '%{redirect_url}' "$BASE/api/auth/oidc/start?next=/&aktion=UPDATE_PASSWORD")
grep -q "kc_action=UPDATE_PASSWORD" <<<"$ZIEL" && ok "„Passwort ändern“ führt zu Keycloak (kc_action)" \
  || bad "Keine Aktion im Sprung zu Keycloak: $ZIEL"
expect "400" "$(code "$BASE/api/auth/oidc/start?aktion=delete_account")" "Eine fremde Aktion wird abgelehnt"
grep -q "^ok" <<<"$(kc "$NEU" "$PW2" "$TMP/k2.jar" --aktion UPDATE_PASSWORD --neu "$PW1")" \
  && ok "Passwort über Keycloak geändert" || bad "Passwortänderung über Keycloak scheiterte"
grep -q "^ok" <<<"$(kc "$NEU" "$PW1" "$TMP/k3.jar")" && ok "Das neue Passwort gilt" \
  || bad "Das neue Passwort gilt nicht"

# ------------------------------------------------------------ Eine Uhr
echo
echo "SSO bleibt, solange OTA angemeldet ist"
keks() {  # keks <jar> -> Wert von ota_kcwach (leer, wenn keiner)
  python3 - "$1" <<'PY'
import sys
for z in open(sys.argv[1]):
    f = z.rstrip("\n").split("\t")
    if len(f) == 7 and f[5] == "ota_kcwach":
        print(f[6])
PY
}
keks_setzen() {  # keks_setzen <jar> <wert>
  python3 - "$1" "$2" <<'PY'
import sys
pfad, wert = sys.argv[1], sys.argv[2]
zeilen = []
for z in open(pfad):
    f = z.rstrip("\n").split("\t")
    if len(f) == 7 and f[5] == "ota_kcwach":
        f[6] = wert
        z = "\t".join(f) + "\n"
    zeilen.append(z)
open(pfad, "w").writelines(zeilen)
PY
}
realm_frist() {
  docker exec ota-api python -c "from ota import keycloak; print(keycloak.ruf('GET', '').json()['ssoSessionIdleTimeout'])"
}
W=$(keks "$TMP/k3.jar")
[ -n "$W" ] && ok "Nach der Anmeldung über Keycloak liegt das Wach-Cookie im Browser" \
  || bad "Kein Wach-Cookie nach der Anmeldung"
FRIST=$(api "$BASE/api/admin/settings" | jqp "d['auth_idle_minutes']")
expect "$((FRIST * 60))" "$(realm_frist)" "Keycloaks SSO-Leerlauf = OTAs Anmeldefrist ($FRIST Minuten)"
keks_setzen "$TMP/k3.jar" "1000.${W#*.}"
expect "200" "$(curl -sk -b "$TMP/k3.jar" -c "$TMP/k3.jar" -o /dev/null -w '%{http_code}' "$BASE/api/auth/me")" \
  "Nach fünf Minuten frischt die nächste Anfrage Keycloak auf"
NEU_STEMPEL=$(keks "$TMP/k3.jar"); NEU_STEMPEL=${NEU_STEMPEL%%.*}
[ "${NEU_STEMPEL:-0}" -gt $(( $(date +%s) - 60 )) ] && ok "… und der Zeitpunkt im Cookie ist frisch" \
  || bad "Zeitpunkt im Cookie nicht erneuert: $NEU_STEMPEL"
keks_setzen "$TMP/k3.jar" "1000.kaputt"
expect "401" "$(curl -sk -b "$TMP/k3.jar" -o /dev/null -w '%{http_code}' "$BASE/api/auth/me")" \
  "Kennt Keycloak die Sitzung nicht mehr, endet auch die bei OTA"
ANDERE=$([ "$FRIST" = "240" ] && echo 480 || echo 240)
api -X PUT "$BASE/api/admin/settings" -H 'Content-Type: application/json' -d "{\"auth_idle_minutes\": $ANDERE}" >/dev/null
expect "$((ANDERE * 60))" "$(realm_frist)" "Ändert die Verwaltung die Frist, zieht Keycloak mit ($ANDERE Minuten)"
api -X PUT "$BASE/api/admin/settings" -H 'Content-Type: application/json' -d "{\"auth_idle_minutes\": $FRIST}" >/dev/null
expect "$((FRIST * 60))" "$(realm_frist)" "… und zurück ($FRIST Minuten)"

# ------------------------------------------------------------ Verwaltung
echo
echo "Ändern, Passwort, Sperren, Löschen"
UID_NEU=$(uid_von "$NEU")
USERS_GID=$(api "$BASE/api/admin/groups" | jqp "next((g['id'] for g in d if g['slug'] == 'users'), '')")
expect "200" "$(code -b "$TMP/admin.jar" -X PUT "$BASE/api/admin/users/$UID_NEU" -H 'Content-Type: application/json' \
  -d "{\"username\":\"$NEU\",\"email\":\"$NEU@ota.invalid\",\"display_name\":\"Prüf Geändert\",\"password\":\"$PW2\",\"passwort_wechseln\":false,\"group_ids\":[\"$USERS_GID\"]}")" \
  "Die Verwaltung ändert Name, Gruppe und Passwort"
rm -f "$TMP/k4.jar"
grep -q "^ok" <<<"$(kc "$NEU" "$PW2" "$TMP/k4.jar")" && ok "Das gesetzte Passwort gilt in Keycloak" \
  || bad "Das gesetzte Passwort gilt nicht"
GR=$(curl -sk -b "$TMP/k4.jar" "$BASE/api/auth/me" | jqp "','.join(d['groups'])")
grep -q "users" <<<"$GR" && ok "Die Gruppe kommt beim Anmelden aus Keycloak zurück ($GR)" \
  || bad "Gruppe nach dem Anmelden: '$GR'"
expect "200" "$(code -b "$TMP/admin.jar" -X POST "$BASE/api/admin/users/$UID_NEU/reset-totp")" \
  "Zweiten Faktor zurücksetzen geht für ein Keycloak-Konto"
expect "200" "$(code -b "$TMP/admin.jar" -X PUT "$BASE/api/admin/users/$UID_NEU" -H 'Content-Type: application/json' \
  -d "{\"username\":\"$NEU\",\"email\":\"$NEU@ota.invalid\",\"is_active\":false,\"group_ids\":[]}")" "Deaktivieren"
grep -q "disabled" <<<"$(kc "$NEU" "$PW2" "$TMP/k5.jar")" && ok "Deaktiviert kommt es bei Keycloak nicht herein" \
  || bad "Deaktiviertes Konto kam herein"
api -X DELETE "$BASE/api/admin/users/$UID_NEU" | grep -q "gesperrt" \
  && ok "Löschen sperrt das Konto in Keycloak" || bad "Löschen meldet keine Sperre"
ANT=$(api -H 'Content-Type: application/json' -X POST "$BASE/api/admin/users" \
  -d "{\"username\":\"$NEU\",\"email\":\"$NEU@ota.invalid\",\"password\":\"$PW1\",\"passwort_wechseln\":false,\"group_ids\":[]}")
expect "keycloak" "$(jqp "d.get('auth_provider')" <<<"$ANT")" "Wieder anlegen verknüpft das gesperrte Konto"
grep -q "^ok" <<<"$(kc "$NEU" "$PW1" "$TMP/k6.jar")" && ok "… und entsperrt es mit dem neuen Passwort" \
  || bad "Wieder angelegtes Konto kam nicht herein"
expect "400" "$(code -b "$TMP/admin.jar" -X POST "$BASE/api/admin/users" -H 'Content-Type: application/json' \
  -d '{"username":"ota-pruef-ohne-pw","email":"ota-pruef-ohne-pw@ota.invalid","group_ids":[]}')" \
  "Ohne Startpasswort entsteht kein Konto"

# ------------------------------------------------------------ Umzug
echo
echo "Umzug eines lokalen Bestandskontos"
"$ROOT/scripts/lokales-testkonto.sh" "$ALT" "$PW1" "$ALT@ota.invalid" users >/dev/null
expect "True" "$(curl -sk "$BASE/api/auth/anmeldung" | jqp "d['lokale_konten']")" \
  "/login weiss, dass es noch lokale Konten gibt"
expect "200" "$(lokal_an "$TMP/u.jar" "$ALT" "$PW1")" "Das lokale Konto meldet sich an"
# Aus einem früheren Lauf liegt das Konto in Keycloak womöglich gesperrt da
# (Löschen sperrt dort nur). Hier ausdrücklich so herrichten, dann zuerst den
# Fall prüfen, dass ein gesperrtes Konto gleichen Namens den Umzug aufhält.
kc_konto() {  # kc_konto an|aus — das Keycloak-Konto $ALT (wenn es eines gibt)
  docker exec -i -e N="$ALT" -e P="$PW1" -e A="$1" ota-api python - <<'PY'
import os
from ota import keycloak
k = keycloak.konto_finden(os.environ["N"])
if k is None and os.environ["A"] == "aus":
    k = {"id": keycloak.konto_anlegen(os.environ["N"], email=os.environ["N"] + "@ota.invalid",
                                      anzeigename="", passwort=os.environ["P"], wechseln=False)}
if k is not None:
    keycloak.konto_profil(str(k["id"]), anzeigename="", email=os.environ["N"] + "@ota.invalid",
                          aktiv=os.environ["A"] == "an", verzeichnis=False)
    keycloak.konto_passwort(str(k["id"]), os.environ["P"], False)
PY
}
kc_konto aus
expect "409" "$(code -b "$TMP/u.jar" -X POST "$BASE/api/auth/umziehen" -H 'Content-Type: application/json' \
  -d "{\"password\":\"$PW1\"}")" "Ein gesperrtes Keycloak-Konto gleichen Namens hält den Umzug auf"
expect "200" "$(code -b "$TMP/u.jar" "$BASE/api/auth/me")" "… und das lokale Konto bleibt angemeldet"
kc_konto an
WEITER=$(curl -sk -b "$TMP/u.jar" -c "$TMP/u.jar" -X POST "$BASE/api/auth/umziehen" \
  -H 'Content-Type: application/json' -d "{\"password\":\"$PW1\"}" | jqp "d.get('weiter','')")
grep -q "login_hint=$ALT" <<<"$WEITER" && ok "Es zieht um, weiter zur zentralen Anmeldung mit Namen" \
  || bad "Umzug: $WEITER"
expect "401" "$(code -b "$TMP/u.jar" "$BASE/api/auth/me")" "Die lokale Sitzung ist danach zu Ende"
grep -q "^ok $ALT" <<<"$(kc "$ALT" "$PW1" "$TMP/u2.jar")" \
  && ok "In Keycloak gilt das Passwort — kein Einmal-Passwort" || bad "Anmeldung nach dem Umzug scheiterte"
expect "409" "$(lokal_an "$TMP/u3.jar" "$ALT" "$PW1")" "Lokal kommt es danach nicht mehr herein"
expect "409" "$(code -b "$TMP/admin.jar" -X POST "$BASE/api/auth/umziehen" -H 'Content-Type: application/json' \
  -d "{\"password\":\"$ADMIN_PW\"}")" "Das Notfallkonto zieht nicht um"

echo
printf '  bestanden: %d   fehlgeschlagen: %d\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
