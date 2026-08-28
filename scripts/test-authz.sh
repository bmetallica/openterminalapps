#!/usr/bin/env bash
# Autorisierungstests. Prueft, dass ein normaler Nutzer beweisbar nichts
# Administratives tun und keine fremde Session sehen kann.
#
# Aufruf:  ./scripts/test-authz.sh [basis-url]

set -uo pipefail

BASE="${1:-https://192.168.66.224:8443}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CA="$ROOT/deploy/certs/ota-ca.crt"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

ADMIN_USER="${OTA_TEST_ADMIN:-notfall}"
ADMIN_PW="${OTA_TEST_ADMIN_PW:?OTA_TEST_ADMIN_PW fehlt. Trag es in deploy/.env ein.}"
TEST_USER="ota-testnutzer"
TEST_PW="TestNutzer2026!ab"

pass=0; fail=0
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; pass=$((pass+1)); }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$1"; fail=$((fail+1)); }

api()  { curl -s --cacert "$CA" -b "$1" -c "$1" "${@:2}"; }
code() { curl -s --cacert "$CA" -b "$1" -o /dev/null -w '%{http_code}' "${@:2}"; }

expect() {  # expect <erwartet> <ist> <beschreibung>
  if [ "$2" = "$1" ]; then ok "$3 ($2)"; else bad "$3 — erwartet $1, bekommen $2"; fi
}

laufende_session() {  # laufende_session <vorlagen-id> — gibt die Session-ID
  # Herstellen statt voraussetzen. Vorher hing das Ergebnis davon ab, was ein
  # vorheriger Lauf hinterlassen hatte: Lief zufällig keine Session, meldeten
  # zwei Abschnitte "keine laufende Session" — ein Fehlschlag, der nichts mit
  # dem Geprüften zu tun hat.
  local vorlage="$1" sid
  sid=$(api "$TMP/admin.jar" "$BASE/api/sessions" | jqp "
next((s['id'] for s in d if s['template_id'] == '$vorlage' and s['status'] == 'running'), '')")
  if [ -z "$sid" ]; then
    sid=$(api "$TMP/admin.jar" -X POST "$BASE/api/sessions" \
          -H 'Content-Type: application/json' -d "{\"template_id\":\"$vorlage\"}" \
          | jqp "d.get('id','')")
    sleep 18
  fi
  printf '%s' "$sid"
}

jqp() {  # jqp <python-ausdruck ueber d> — liest JSON von stdin
  python3 -c "import sys,json;d=json.load(sys.stdin);print($1)" 2>/dev/null
}

echo "OTA Autorisierungstests gegen $BASE"
echo

# ---------------------------------------------------------------- Anmeldung
login() {  # login <jar> <user> <pw>
  api "$1" -X POST "$BASE/api/auth/login" -H 'Content-Type: application/json' \
      -d "{\"username\":\"$2\",\"password\":\"$3\"}" >/dev/null
}

echo "Anmeldung"
login "$TMP/admin.jar" "$ADMIN_USER" "$ADMIN_PW"
IS_ADMIN=$(api "$TMP/admin.jar" "$BASE/api/auth/me" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("is_admin"))' 2>/dev/null)
expect "True" "$IS_ADMIN" "Administrator ist angemeldet"

expect "401" "$(code /dev/null "$BASE/api/auth/me")" "Ohne Cookie kein Zugriff auf /me"

# Ein unbekannter Name muss genauso lange brauchen wie ein bekannter. Sonst
# laesst sich die Nutzerliste abfragen, ohne je hereinzukommen.
tmg() {  # tmg <benutzername> -> Dauer eines Anmeldeversuchs in Millisekunden
  curl -s --cacert "$CA" -o /dev/null -w '%{time_total}' -X POST "$BASE/api/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"username\":\"$1\",\"password\":\"garantiert-falsch-9911\"}" \
    | python3 -c "import sys;print(int(float(sys.stdin.read()) * 1000))"
}
T_REAL=0; T_FAKE=0
for _ in 1 2 3; do
  T_REAL=$((T_REAL + $(tmg "$ADMIN_USER")))
  T_FAKE=$((T_FAKE + $(tmg "gibtesnicht-$RANDOM")))
done
T_REAL=$((T_REAL / 3)); T_FAKE=$((T_FAKE / 3))

# Verglichen wird das Verhaeltnis, nicht die Differenz in Millisekunden.
# Der Befund, um den es geht, ist eine Groessenordnung: Ohne Argon2-Durchlauf
# antwortet ein unbekannter Name in ein bis zwei Millisekunden statt in
# hundertfuenfzig. Eine feste Schranke in Millisekunden misst dagegen vor
# allem, wie beschaeftigt der Host gerade ist — sie schlug am 2026-08-28 bei
# 230 gegen 167 Millisekunden an, und daran war nichts falsch ausser der
# Schranke.
[ "${T_FAKE:-0}" -ge $((T_REAL / 2)) ] \
  && ok "Unbekanntes Konto verrät sich nicht über die Dauer (${T_REAL}ms vs ${T_FAKE}ms)" \
  || bad "Unbekanntes Konto antwortet auffällig schneller: ${T_REAL}ms vs ${T_FAKE}ms"

expect "401" "$(curl -s --cacert "$CA" -o /dev/null -w '%{http_code}' -X POST "$BASE/api/auth/login" \
  -H 'Content-Type: application/json' -d "{\"username\":\"$ADMIN_USER\",\"password\":\"falsch\"}")" \
  "Falsches Passwort wird abgelehnt"

# ------------------------------------------------------- Testnutzer anlegen
echo
echo "Testnutzer vorbereiten"
USERS_GID=$(api "$TMP/admin.jar" "$BASE/api/admin/groups" \
  | python3 -c 'import sys,json;print([g["id"] for g in json.load(sys.stdin) if g["slug"]=="users"][0])')

EXISTING=$(api "$TMP/admin.jar" "$BASE/api/admin/users" \
  | python3 -c "import sys,json;m=[u['id'] for u in json.load(sys.stdin) if u['username']=='$TEST_USER'];print(m[0] if m else '')")

if [ -n "$EXISTING" ]; then
  api "$TMP/admin.jar" -X PUT "$BASE/api/admin/users/$EXISTING" -H 'Content-Type: application/json' \
    -d "{\"username\":\"$TEST_USER\",\"password\":\"$TEST_PW\",\"group_ids\":[\"$USERS_GID\"]}" >/dev/null
else
  api "$TMP/admin.jar" -X POST "$BASE/api/admin/users" -H 'Content-Type: application/json' \
    -d "{\"username\":\"$TEST_USER\",\"password\":\"$TEST_PW\",\"group_ids\":[\"$USERS_GID\"]}" >/dev/null
fi
# Ein zweiter Faktor aus einem frueheren Lauf wuerde die Anmeldung mit blossem
# Passwort abweisen — und der ganze Rest scheiterte an einem 401, das nichts
# mit dem zu tun haette, was gerade geprueft wird. Der Test stellt seinen
# Vorzustand selbst her.
TEST_UID=$(api "$TMP/admin.jar" "$BASE/api/admin/users" \
  | jqp "next((u['id'] for u in d if u['username'] == '$TEST_USER'), '')")
[ -n "$TEST_UID" ] && api "$TMP/admin.jar" -X POST \
  "$BASE/api/admin/users/$TEST_UID/reset-totp" >/dev/null

ok "Testnutzer $TEST_USER steht bereit (nur Gruppe users, ohne zweiten Faktor)"

login "$TMP/user.jar" "$TEST_USER" "$TEST_PW"
# Wechsel des Passworts ist erzwungen, blockiert die Anmeldung aber nicht.
U_ADMIN=$(api "$TMP/user.jar" "$BASE/api/auth/me" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("is_admin"))' 2>/dev/null)
expect "False" "$U_ADMIN" "Testnutzer ist kein Administrator"

# ---------------------------------------------------- Admin-Endpunkte sperren
echo
echo "Admin-Endpunkte gegen normalen Nutzer"
for path in /api/admin/users /api/admin/groups /api/admin/host /api/admin/images /api/admin/audit; do
  expect "403" "$(code "$TMP/user.jar" "$BASE$path")" "GET $path verweigert"
done
expect "403" "$(code "$TMP/user.jar" -X POST "$BASE/api/templates" -H 'Content-Type: application/json' \
  -d '{"friendly_name":"Schmuggel","image_ref":"alpine","cores":1,"memory_bytes":268435456}')" \
  "POST /api/templates verweigert"

# --------------------------------------------------------- fremde Session
echo
echo "Fremde Session"
SID=$(api "$TMP/admin.jar" "$BASE/api/sessions" \
  | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d[0]["id"] if d else "")')

# Ohne laufende Session lässt sich der wichtigste Teil nicht prüfen. Statt
# ihn zu überspringen, stellt der Test den Zustand selbst her — sonst hängt
# das Ergebnis davon ab, was ein vorheriger Test hinterlassen hat.
if [ -z "$SID" ]; then
  TPL=$(api "$TMP/admin.jar" "$BASE/api/templates" \
    | python3 -c 'import sys,json;d=json.load(sys.stdin);print(next((t["id"] for t in d if t["is_enabled"]), ""))')
  if [ -n "$TPL" ]; then
    SID=$(api "$TMP/admin.jar" -X POST "$BASE/api/sessions" \
      -H 'Content-Type: application/json' -d "{\"template_id\":\"$TPL\"}" \
      | python3 -c 'import sys,json;print(json.load(sys.stdin).get("id",""))')
    [ -n "$SID" ] && { echo "  (Session für die Prüfung gestartet)"; sleep 18; }
  fi
fi

if [ -n "$SID" ]; then
  expect "200" "$(code "$TMP/admin.jar" "$BASE/s/$SID/")" "Eigentümer erreicht seine Session"
  expect "403" "$(code "$TMP/user.jar"  "$BASE/s/$SID/")" "Fremder Nutzer wird abgewiesen"
  expect "401" "$(code /dev/null        "$BASE/s/$SID/")" "Ohne Anmeldung abgewiesen"
  expect "404" "$(code "$TMP/user.jar" -X DELETE "$BASE/api/sessions/$SID")" \
    "Fremde Session löschen nicht möglich"

  # `sessions.view_all` ist fuer eine Rolle wie „Support" gedacht: sehen, was
  # laeuft, und im Notfall beenden. Es darf **nicht** reichen, um an einem
  # fremden Bildschirm zu sitzen — dort steht ein offenes Terminal und ein
  # entsperrter Passwortspeicher. Bis zum 2026-08-27 reichte es.
  SUP="ota-pruef-support"
  SUP_GID=$(api "$TMP/admin.jar" -X POST "$BASE/api/admin/groups" \
    -H 'Content-Type: application/json' \
    -d '{"name":"OTA-Prüfung Support","permissions":["sessions.view_all"]}' \
    | jqp "d.get('id','')")
  if [ -n "$SUP_GID" ]; then
    api "$TMP/admin.jar" -X POST "$BASE/api/admin/users" -H 'Content-Type: application/json' \
      -d "{\"username\":\"$SUP\",\"password\":\"$TEST_PW\",\"group_ids\":[\"$SUP_GID\"]}" >/dev/null
    login "$TMP/sup.jar" "$SUP" "$TEST_PW"

    SEEN=$(api "$TMP/sup.jar" "$BASE/api/sessions?all_users=true" | jqp "len(d)")
    [ "${SEEN:-0}" -gt 0 ] && ok "Support sieht fremde Sessions in der Liste ($SEEN)" \
                           || bad "Support sieht die fremde Session nicht — Recht wirkt nicht"
    expect "403" "$(code "$TMP/sup.jar" "$BASE/s/$SID/")" \
      "Support kommt trotzdem nicht auf den fremden Bildschirm"

    SUP_UID=$(api "$TMP/admin.jar" "$BASE/api/admin/users" \
      | jqp "next((u['id'] for u in d if u['username'] == '$SUP'), '')")
    [ -n "$SUP_UID" ] && api "$TMP/admin.jar" -X DELETE "$BASE/api/admin/users/$SUP_UID" >/dev/null
    api "$TMP/admin.jar" -X DELETE "$BASE/api/admin/groups/$SUP_GID" >/dev/null
  else
    bad "Support-Gruppe für die Prüfung liess sich nicht anlegen"
  fi
  SEEN=$(api "$TMP/user.jar" "$BASE/api/sessions?all_users=true" \
    | python3 -c 'import sys,json;print(len(json.load(sys.stdin)))')
  expect "0" "$SEEN" "all_users=true zeigt einem Nutzer nichts Fremdes"
else
  bad "Keine laufende Session zum Prüfen vorhanden"
fi

# ------------------------------------------ Sichtbarkeit einer Anwendung
# Eine Anwendung im Arbeitsplatz kann auf Gruppen eingeschraenkt werden — etwa
# eine, fuer die nur ein Teil der Belegschaft eine Lizenz hat. Geprueft wird
# beides: dass sie aus der Liste verschwindet, **und** dass ein direkter Aufruf
# sie nicht startet. Nur das zweite ist die Absicherung.
echo
echo "Sichtbarkeit einer Anwendung"

WS=$(api "$TMP/admin.jar" "$BASE/api/templates" | python3 -c '
import sys, json
d = json.load(sys.stdin)
print(next((t["id"] for t in d if t["mode"] == "workspace" and t["apps"]), ""))')

if [ -z "$WS" ]; then
  bad "Kein Arbeitsplatz mit Anwendungen zum Prüfen vorhanden"
else
  CATALOG=$(api "$TMP/admin.jar" "$BASE/api/templates/$WS")
  APP=$(echo "$CATALOG" | jqp "d['apps'][0]['slug']")

  # Eine Gruppe, in der niemand ist. Damit ist die Anwendung fuer den
  # Testnutzer gesperrt, ohne dass sonst jemand etwas davon merkt.
  LOCK=$(api "$TMP/admin.jar" -X POST "$BASE/api/admin/groups" \
    -H 'Content-Type: application/json' \
    -d '{"name":"OTA-Prüfung Lizenz","permissions":[]}' | jqp "d.get('id','')")
  if [ -z "$LOCK" ]; then
    LOCK=$(api "$TMP/admin.jar" "$BASE/api/admin/groups" \
      | jqp "next((g['id'] for g in d if g['name'] == 'OTA-Prüfung Lizenz'), '')")
  fi

  # Katalog unveraendert zurueckschreiben, nur mit Gruppe an der ersten App.
  # Die Reihenfolge bleibt, sonst wandern die Displaynummern.
  BODY=$(echo "$CATALOG" | LOCK="$LOCK" APP="$APP" python3 -c '
import json, os, sys
d = json.load(sys.stdin)
out = []
for a in d["apps"]:
    out.append({
        "slug": a["slug"], "name": a["name"], "icon": a["icon"],
        "exec_cmd": a.get("exec_cmd", ""), "exec_args": a.get("exec_args", ""),
        "is_enabled": a["is_enabled"], "fixed_display": a.get("fixed_display"),
        "group_ids": [os.environ["LOCK"]] if a["slug"] == os.environ["APP"] else [],
    })
print(json.dumps(out))')

  # exec_cmd steht nicht in AppOut — aus der Erkennung nachziehen.
  BODY=$(api "$TMP/admin.jar" "$BASE/api/templates/$WS/apps/discover" \
    | BODY="$BODY" python3 -c '
import json, os, sys
found = {a["slug"]: a for a in json.load(sys.stdin)}
out = []
for a in json.loads(os.environ["BODY"]):
    src = found.get(a["slug"], {})
    a["exec_cmd"] = a["exec_cmd"] or src.get("exec_cmd", "/bin/true")
    a["exec_args"] = a["exec_args"] or src.get("exec_args", "")
    out.append(a)
print(json.dumps(out))')

  api "$TMP/admin.jar" -X PUT "$BASE/api/templates/$WS/apps" \
    -H 'Content-Type: application/json' -d "$BODY" >/dev/null

  SEES=$(api "$TMP/user.jar" "$BASE/api/templates" | APP="$APP" python3 -c '
import json, os, sys
d = json.load(sys.stdin)
print(sum(1 for t in d for a in t["apps"] if a["slug"] == os.environ["APP"]))')
  expect "0" "$SEES" "Eingeschränkte Anwendung steht nicht mehr in der Liste"

  ADMIN_SEES=$(api "$TMP/admin.jar" "$BASE/api/templates/$WS" | APP="$APP" python3 -c '
import json, os, sys
d = json.load(sys.stdin)
print(sum(1 for a in d["apps"] if a["slug"] == os.environ["APP"]))')
  expect "1" "$ADMIN_SEES" "Der Administrator sieht sie weiterhin"

  # Ein PUT, das die Gruppenzuweisung nicht erwaehnt, darf sie nicht
  # loeschen. Am 2026-08-28 tat es das — und der Arbeitsplatz verschwand
  # wortlos von jedem Dashboard, weil ein anderer Test eine Einstellung
  # geaendert und die Zuweisung dabei nicht mitgeschickt hatte.
  GROUPS_BEFORE=$(api "$TMP/admin.jar" "$BASE/api/templates/$WS" | jqp "len(d['group_ids'])")
  api "$TMP/admin.jar" -X PUT "$BASE/api/templates/$WS" -H 'Content-Type: application/json' \
    -d "$(api "$TMP/admin.jar" "$BASE/api/templates/$WS" | python3 -c '
import json, sys
d = json.load(sys.stdin)
keep = ("friendly_name","description","icon","categories","mode","image_ref","cores",
        "memory_bytes","x_res","y_res","idle_minutes","idle_action","persistence_scope",
        "rights","env","start_script","is_enabled")
print(json.dumps({k: d[k] for k in keep if k in d}))')" >/dev/null
  GROUPS_AFTER=$(api "$TMP/admin.jar" "$BASE/api/templates/$WS" | jqp "len(d['group_ids'])")
  expect "$GROUPS_BEFORE" "$GROUPS_AFTER" \
    "Ein PUT ohne Zuweisung lässt sie stehen"

  # Und jetzt der Teil, der zaehlt: eine eigene, laufende Session des
  # Testnutzers, und ein Aufruf mit dem gesperrten Kuerzel.
  USID=$(api "$TMP/user.jar" -X POST "$BASE/api/sessions" \
    -H 'Content-Type: application/json' -d "{\"template_id\":\"$WS\"}" \
    | jqp "d.get('id','')")
  if [ -n "$USID" ]; then
    for _ in 1 2 3 4 5 6 7 8 9 10 11 12; do
      # Aus der Liste lesen: Eine einzelne Session hat keinen eigenen
      # GET-Endpunkt. Der frühere Aufruf lief in „Method Not Allowed" und
      # wartete deshalb jedes Mal die vollen 36 Sekunden ab, ohne je etwas
      # zu erfahren.
      ST=$(api "$TMP/user.jar" "$BASE/api/sessions" | jqp "
next((s['status'] for s in d if s['id'] == '$USID'), '')")
      [ "$ST" = "running" ] && break
      sleep 3
    done
    expect "403" "$(code "$TMP/user.jar" -X POST "$BASE/api/sessions/$USID/apps/$APP")" \
      "Direkter Start der gesperrten Anwendung wird abgewiesen"

    OTHER=$(echo "$CATALOG" | APP="$APP" python3 -c '
import json, os, sys
d = json.load(sys.stdin)
print(next((a["slug"] for a in d["apps"]
            if a["slug"] != os.environ["APP"] and a["is_enabled"]
            and not a.get("blocked_reason")), ""))')
    if [ -n "$OTHER" ]; then
      OUT=$(api "$TMP/user.jar" -X POST "$BASE/api/sessions/$USID/apps/$OTHER")
      RC=$(code "$TMP/user.jar" -X POST "$BASE/api/sessions/$USID/apps/$OTHER")
      # Ausdruecklich 200 und nicht „irgendwas ausser 403": Ein 404 hat den
      # Test einmal bestehen lassen, obwohl die Session gar nicht mehr da war
      # — die Prueflogik war dann eine Kulisse.
      expect "200" "$RC" "Eine freie Anwendung ($OTHER) bleibt startbar"
      [ "$RC" = "200" ] || echo "    Antwort: $(echo "$OUT" | head -c 200)"
    fi
    USER_CNAME="ota-s-$(echo "$USID" | cut -c1-12)"
  else
    bad "Testnutzer konnte keine eigene Session starten"
  fi

  # Aufräumen: Gruppe löschen. Dabei muss die Kennung aus dem Katalog
  # verschwinden — sonst stünde dort dauerhaft eine Gruppe, die es nicht gibt.
  api "$TMP/admin.jar" -X DELETE "$BASE/api/admin/groups/$LOCK" >/dev/null
  FREED=$(api "$TMP/admin.jar" "$BASE/api/templates/$WS" | APP="$APP" python3 -c '
import json, os, sys
d = json.load(sys.stdin)
print(next((len(a["group_ids"]) for a in d["apps"] if a["slug"] == os.environ["APP"]), -1))')
  expect "0" "$FREED" "Gelöschte Gruppe verschwindet aus dem Katalog"

  SEES=$(api "$TMP/user.jar" "$BASE/api/templates" | APP="$APP" python3 -c '
import json, os, sys
d = json.load(sys.stdin)
print(sum(1 for t in d for a in t["apps"] if a["slug"] == os.environ["APP"]))')
  expect "1" "$SEES" "Danach ist die Anwendung wieder für alle da"
fi

# ------------------------------------------------------- Container-Härtung
# Der Container aus dem vorigen Abschnitt laeuft noch. Was ihn einsperrt, steht
# in seiner Docker-Konfiguration — und genau dort wird nachgesehen, statt es zu
# glauben.
echo
echo "Container-Härtung"

# Ausdruecklich der Container des **Testnutzers**. Der eines Administrators
# laeuft absichtlich lockerer — dort waere die Pruefung wertlos.
CNAME="${USER_CNAME:-}"
if [ -z "$CNAME" ] || ! docker inspect "$CNAME" >/dev/null 2>&1; then
  bad "Kein Session-Container des Testnutzers zum Prüfen vorhanden"
else
  INSPECT=$(docker inspect "$CNAME")

  grep -q '"no-new-privileges:true"' <<<"$INSPECT" \
    && ok "no-new-privileges ist gesetzt" \
    || bad "no-new-privileges fehlt — sudo liefe an"

  DROPPED=$(echo "$INSPECT" | jqp "','.join(d[0]['HostConfig']['CapDrop'] or [])")
  expect "ALL" "$DROPPED" "Alle Linux-Fähigkeiten entzogen"

  # SYS_ADMIN erlaubt Einhaengungen und eigene Namespaces und ist damit
  # praktisch gleichbedeutend mit root auf dem Host. Sie stand hier bis zum
  # 2026-08-27 ohne Begruendung im Code.
  ADDED=$(echo "$INSPECT" | jqp "','.join(d[0]['HostConfig']['CapAdd'] or [])")
  case "$ADDED" in
    *SYS_ADMIN*) bad "SYS_ADMIN ist wieder gesetzt ($ADDED)" ;;
    *)           ok "Kein SYS_ADMIN (hinzugefügt: ${ADDED:-nichts})" ;;
  esac

  PIDS=$(echo "$INSPECT" | jqp "d[0]['HostConfig']['PidsLimit']")
  [ "${PIDS:-0}" -gt 0 ] && ok "Prozesszahl begrenzt ($PIDS)" \
                         || bad "Keine Grenze für die Prozesszahl"

  SECCOMP=$(echo "$INSPECT" | jqp "','.join(d[0]['HostConfig']['SecurityOpt'] or [])")
  case "$SECCOMP" in
    *seccomp=unconfined*) bad "seccomp ist abgeschaltet" ;;
    *)                    ok "seccomp-Standardfilter aktiv" ;;
  esac

  PRIV=$(echo "$INSPECT" | jqp "d[0]['HostConfig']['Privileged']")
  expect "False" "$PRIV" "Container läuft nicht privilegiert"

  # Das Sessionnetz darf die Datenbank nicht erreichen. Sonst waere jede Lücke
  # in einer Anwendung im Arbeitsplatz gleich eine Lücke in den Nutzerdaten.
  if docker exec "$CNAME" bash -c 'timeout 3 bash -c "</dev/tcp/ota-db/5432"' 2>/dev/null; then
    bad "Der Session-Container erreicht die Datenbank"
  else
    ok "Der Session-Container erreicht die Datenbank nicht"
  fi
fi


# Und die Gegenprobe: Der Container eines Administrators laeuft absichtlich
# ohne diese beiden Sperren, sonst liefe dort kein sudo. Faellt das zusammen,
# ist entweder die Haertung kaputt oder das Nachinstallieren.
#
# Der Container **dieses** Kontos, nicht irgendein anderer. Vorher wurde der
# erste genommen, der nicht dem Testnutzer gehoert — und sobald ein drittes
# Konto eine Session hatte, war das ein beliebiger. Gemeldet wurde dann eine
# kaputte Haertung, wo nur der falsche Container betrachtet wurde.
ADMIN_SID=$(api "$TMP/admin.jar" "$BASE/api/sessions" | jqp "
next((s['id'] for s in d if s['status'] == 'running'), '')")
ACNAME=""
[ -n "$ADMIN_SID" ] && ACNAME="ota-s-$(echo "$ADMIN_SID" | cut -c1-12)"
if [ -n "$ACNAME" ]; then
  docker inspect "$ACNAME" | grep -q '"no-new-privileges:true"' \
    && bad "Der Container des Administrators ist mitgehärtet — sudo liefe dort nicht" \
    || ok "Der Container des Administrators bleibt bewusst offen (sudo)"
fi

[ -n "${USID:-}" ] && api "$TMP/user.jar" -X DELETE "$BASE/api/sessions/$USID" >/dev/null

# ---------------------------------------------------- Zentrale Identität
#
# Etappe A der auth-roadmap: Keycloak steht im Stack, **ohne** dass sich an
# der Anmeldung etwas ändert. Geprüft wird genau das — es läuft, OTA darf
# darin, was es braucht, und der Anmeldeweg ist unberührt.
echo
echo "Zentrale Identität"

CODE=$(code "$TMP/user.jar" "$BASE/api/admin/identity/keycloak")
expect "403" "$CODE" "Der Zustand des Identity Providers ist nichts für jeden"

KC=$(api "$TMP/admin.jar" "$BASE/api/admin/identity/keycloak")
ERR=$(echo "$KC" | jqp "str(d['erreichbar'])")
expect "True" "$ERR" "Keycloak ist erreichbar"
expect "ota" "$(echo "$KC" | jqp "d['realm']")" "Der eigene Realm ist eingerichtet"

for f in konten gruppen clients verzeichnis; do
  HAT=$(echo "$KC" | jqp "str(d['faehigkeiten']['$f'])")
  expect "True" "$HAT" "Das Dienstkonto darf: $f"
done

# `verzeichnis` ist der Punkt, an dem `manage-realm` hängt (§5.5). Ohne dieses
# Recht liesse sich die AD-Anbindung später nicht über OTA konfigurieren, und
# es fiele erst dort auf.
FEHLER=$(echo "$KC" | jqp "str(d['fehler'])")
expect "None" "$FEHLER" "Keine fehlenden Rechte gemeldet"

# Die eigene CA muss **ohne Anmeldung** abholbar sein. Sonst wäre es ein
# Kreis: Wer der Anlage noch nicht traut, kann sich bei ihr nicht anmelden —
# und ohne die CA kann eine fremde Anwendung ihr nicht trauen.
CACODE=$(curl -s --cacert "$CA" -o "$TMP/geholt.crt" -w '%{http_code}' "$BASE/ca.crt")
expect "200" "$CACODE" "Die eigene CA ist ohne Anmeldung abholbar"
openssl x509 -in "$TMP/geholt.crt" -noout -subject >/dev/null 2>&1 \
  && ok "Und sie ist ein gültiges Zertifikat" \
  || bad "Was da kommt, ist kein Zertifikat"
grep -q "PRIVATE KEY" "$TMP/geholt.crt" \
  && bad "Es kommt ein privater Schlüssel mit!" \
  || ok "Ohne privaten Schlüssel"

HZ=$(curl -s --cacert "$CA" "$BASE/healthz")
grep -q '"keycloak":"ok"' <<<"$HZ" \
  && ok "healthz meldet Keycloak" \
  || bad "healthz meldet Keycloak nicht: $HZ"

# Und der eigentliche Anspruch dieser Etappe: Es hat sich nichts geändert.
CODE=$(curl -s --cacert "$CA" -o /dev/null -w '%{http_code}' \
  -X POST "$BASE/api/auth/login" -H 'Content-Type: application/json' \
  -d "{\"username\":\"$ADMIN_USER\",\"password\":\"$ADMIN_PW\"}")
expect "200" "$CODE" "Die Anmeldung läuft unverändert über OTA"

# ------------------------------------------- Übernahme und Notzugang
#
# Etappe E. Das Einzige im ganzen Umbau, das ein **bestehendes** Konto
# verändert — deshalb hier die meisten Prüfungen auf das, was nicht passieren
# darf.
echo
echo "Übernahme und Notzugang"

NOTFALL=$(api "$TMP/admin.jar" "$BASE/api/admin/identity/notfallkonto")
expect "True" "$(jqp "str(d['brauchbar'])" <<<"$NOTFALL")" "Ein Notfallkonto ist bestimmt und brauchbar"
NOTFALL_NAME=$(jqp "d['name']" <<<"$NOTFALL")

# Der Notzugang ist ein lokales Konto — und muss es bleiben.
HERK=$(api "$TMP/admin.jar" "$BASE/api/admin/users" | jqp "
next((u['auth_provider'] for u in d if u['username'] == '$NOTFALL_NAME'), '')")
expect "local" "$HERK" "Er meldet sich lokal an, ohne Keycloak"

# Und er darf nicht übernommen werden. Ein Ausweg, der durch dieselbe Tür
# führt wie der Weg hinein, ist keiner.
OFFEN=$(api "$TMP/admin.jar" "$BASE/api/admin/identity/uebernahme" | jqp "
','.join(u['username'] for u in d.get('uebernommen', []))")
case ",$OFFEN," in
  *",$NOTFALL_NAME,"*) bad "Das Notfallkonto stünde zur Übernahme an" ;;
  *) ok "Das Notfallkonto steht nicht zur Übernahme an" ;;
esac

# Ohne bestimmtes Notfallkonto verweigert die Übernahme die Arbeit.
api "$TMP/admin.jar" -X PUT "$BASE/api/admin/identity/notfallkonto" \
  -H 'Content-Type: application/json' -d '{"name":""}' >/dev/null
CODE=$(code "$TMP/admin.jar" -X POST "$BASE/api/admin/identity/uebernahme")
expect "409" "$CODE" "Ohne Notfallkonto läuft keine Übernahme"
api "$TMP/admin.jar" -X PUT "$BASE/api/admin/identity/notfallkonto" \
  -H 'Content-Type: application/json' -d "{\"name\":\"$NOTFALL_NAME\"}" >/dev/null
WIEDER=$(api "$TMP/admin.jar" "$BASE/api/admin/identity/notfallkonto" | jqp "d['name']")
expect "$NOTFALL_NAME" "$WIEDER" "Das Notfallkonto steht wieder"

# Ein übernommenes Konto hat hier kein Passwort mehr — und der Versuch sagt,
# wo der richtige Eingang ist, statt „falsches Passwort" zu behaupten.
UEBER=$(api "$TMP/admin.jar" "$BASE/api/admin/users" | jqp "
next((u['username'] for u in d if u['auth_provider'] == 'keycloak'), '')")
if [ -n "$UEBER" ]; then
  ANTWORT=$(curl -s --cacert "$CA" -X POST "$BASE/api/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"username\":\"$UEBER\",\"password\":\"völlig-egal\"}")
  grep -q "zentrale Anmeldung" <<<"$ANTWORT" \
    && ok "Ein übernommenes Konto wird an die zentrale Anmeldung verwiesen" \
    || bad "Die Meldung hilft nicht weiter: $ANTWORT"

  KEIN_HASH=$(docker compose -f deploy/docker-compose.yml --env-file deploy/.env \
    exec -T db psql -U "${POSTGRES_USER:-ota}" -d "${POSTGRES_DB:-ota}" -tAc \
    "SELECT COALESCE(password_hash,'—') FROM users WHERE username='$UEBER'" 2>/dev/null | tr -d ' \r')
  expect "—" "$KEIN_HASH" "Und der lokale Hash ist weg, nicht bloss übergangen"
else
  bad "Kein übernommenes Konto vorhanden — Prüfung nicht aussagekräftig"
fi

# Der Rückweg gilt nur für übernommene Konten.
ANTWORT=$(api "$TMP/admin.jar" -X POST "$BASE/api/admin/identity/uebernahme/zuruecknehmen" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"$NOTFALL_NAME\",\"password\":\"Egal-Aber-Lang-2026!\"}")
grep -q "gar kein übernommenes Konto" <<<"$ANTWORT" \
  && ok "Der Rückweg fasst nur übernommene Konten an" \
  || bad "Der Rückweg griff nach einem lokalen Konto: $ANTWORT"

CODE=$(code "$TMP/user.jar" "$BASE/api/admin/identity/uebernahme")
expect "403" "$CODE" "Ein normaler Nutzer sieht die Übernahme nicht"

# ------------------------------------------------ Fremde Anwendungen
#
# Etappe D. Eine Anwendung anzulegen heisst, in Keycloak einen OIDC-Client zu
# erzeugen — und darin steht, wohin die Identität der Nutzer fliesst. Geprüft
# werden deshalb vor allem die beiden Schlösser (§5d): das Recht und die Liste
# erlaubter Ziele.
echo
echo "Fremde Anwendungen"

CODE=$(code "$TMP/user.jar" -X POST "$BASE/api/webapps" \
  -H 'Content-Type: application/json' \
  -d '{"name":"Fremd","url":"https://x.example/","redirect_uri":"https://x.example/cb"}')
expect "403" "$CODE" "Ohne das eigene Recht entsteht keine Anwendung"

VORHER=$(api "$TMP/admin.jar" "$BASE/api/admin/settings" | jqp "
__import__('json').dumps(d.get('app_origins') or [])")

# Erstes Schloss: die Liste. Leer heisst nichts erlaubt — nicht alles.
api "$TMP/admin.jar" -X PUT "$BASE/api/admin/settings" -H 'Content-Type: application/json' \
  -d '{"app_origins":[]}' >/dev/null
ANTWORT=$(api "$TMP/admin.jar" -X POST "$BASE/api/webapps" -H 'Content-Type: application/json' \
  -d '{"name":"Pruef","url":"https://pruef.example/","redirect_uri":"https://pruef.example/cb"}')
grep -q "kein Ziel freigegeben" <<<"$ANTWORT" \
  && ok "Eine leere Liste erlaubt nichts, nicht alles" \
  || bad "Ohne Freigabe entstand etwas: $ANTWORT"

api "$TMP/admin.jar" -X PUT "$BASE/api/admin/settings" -H 'Content-Type: application/json' \
  -d '{"app_origins":["https://pruef.example"]}' >/dev/null

ANTWORT=$(api "$TMP/admin.jar" -X POST "$BASE/api/webapps" -H 'Content-Type: application/json' \
  -d '{"name":"Umleitung","url":"https://pruef.example/","redirect_uri":"https://sammel-server.example/abholen"}')
grep -q "erlaubter Ziele" <<<"$ANTWORT" \
  && ok "Ein Ziel neben der Liste wird abgelehnt" \
  || bad "Ein fremdes Ziel wurde angenommen: $ANTWORT"

ANTWORT=$(api "$TMP/admin.jar" -X POST "$BASE/api/webapps" -H 'Content-Type: application/json' \
  -d '{"name":"Platzhalter","url":"https://pruef.example/","redirect_uri":"https://pruef.example/*"}')
grep -q "Platzhalter" <<<"$ANTWORT" \
  && ok "Ein Platzhalter in der Adresse ebenso" \
  || bad "Ein Platzhalter kam durch: $ANTWORT"

NEU=$(api "$TMP/admin.jar" -X POST "$BASE/api/webapps" -H 'Content-Type: application/json' \
  -d '{"name":"Prüfanwendung","url":"https://pruef.example/","redirect_uri":"https://pruef.example/oauth/callback"}')
APP_ID=$(jqp "d.get('id','')" <<<"$NEU")
CLIENT=$(jqp "d.get('client_id','')" <<<"$NEU")
GEHEIM=$(jqp "d.get('client_secret') or ''" <<<"$NEU")

if [ -z "$APP_ID" ]; then
  bad "Die Anwendung liess sich nicht anlegen: $NEU"
else
  ok "Anwendung angelegt ($CLIENT)"
  [ ${#GEHEIM} -ge 20 ] && ok "Das Geheimnis kommt einmal zurück (${#GEHEIM} Zeichen)" \
                        || bad "Kein Geheimnis in der Antwort"

  NOCHMAL=$(api "$TMP/admin.jar" "$BASE/api/webapps" | jqp "
next((str(a.get('client_secret')) for a in d if a['id'] == '$APP_ID'), '')")
  expect "None" "$NOCHMAL" "Und danach nie wieder"

  # Der Client muss in Keycloak wirklich stehen — und nur die eingetragene
  # Adresse annehmen. Das ist die Schranke, die zählt: Sie liegt nicht in OTA.
  KCC=$(docker exec -i ota-agent curl -s -o /dev/null -w '%{http_code}' \
    "http://ota-keycloak:8080/auth/realms/ota/protocol/openid-connect/auth?client_id=$CLIENT&response_type=code&scope=openid&redirect_uri=https%3A%2F%2Fpruef.example%2Foauth%2Fcallback&state=x")
  expect "200" "$KCC" "Keycloak kennt den Client und nimmt seine Adresse an"

  KCF=$(docker exec -i ota-agent curl -s -o /dev/null -w '%{http_code}' \
    "http://ota-keycloak:8080/auth/realms/ota/protocol/openid-connect/auth?client_id=$CLIENT&response_type=code&scope=openid&redirect_uri=https%3A%2F%2Fsammel-server.example%2Fweg&state=x")
  expect "400" "$KCF" "Eine fremde Adresse weist Keycloak zurück"

  # Sichtbarkeit je Gruppe.
  GID=$(api "$TMP/admin.jar" "$BASE/api/admin/groups" | jqp "
next((g['id'] for g in d if g['name'] == 'admins'), '')")
  if [ -n "$GID" ]; then
    api "$TMP/admin.jar" -X PUT "$BASE/api/webapps/$APP_ID" -H 'Content-Type: application/json' \
      -d "{\"name\":\"Prüfanwendung\",\"url\":\"https://pruef.example/\",
           \"redirect_uri\":\"https://pruef.example/oauth/callback\",
           \"description\":\"\",\"icon\":\"◇\",\"is_enabled\":true,\"sort_order\":0,
           \"group_ids\":[\"$GID\"]}" >/dev/null
    SIEHT=$(api "$TMP/user.jar" "$BASE/api/webapps" | jqp "
str(len([a for a in d if a['id'] == '$APP_ID']))")
    expect "0" "$SIEHT" "Wer nicht in der Gruppe ist, sieht die Kachel nicht"
  fi

  api "$TMP/admin.jar" -X DELETE "$BASE/api/webapps/$APP_ID" >/dev/null
  WEGKC=$(docker exec -i ota-agent curl -s -o /dev/null -w '%{http_code}' \
    "http://ota-keycloak:8080/auth/realms/ota/protocol/openid-connect/auth?client_id=$CLIENT&response_type=code&scope=openid&redirect_uri=https%3A%2F%2Fpruef.example%2Foauth%2Fcallback&state=x")
  [ "$WEGKC" != "200" ] && ok "Löschen nimmt den Zugang in Keycloak mit ($WEGKC)" \
                        || bad "Der Client lebt in Keycloak weiter"
fi

# Die Liste wieder auf den alten Stand — dieser Test hinterlässt keine Spuren.
api "$TMP/admin.jar" -X PUT "$BASE/api/admin/settings" -H 'Content-Type: application/json' \
  -d "{\"app_origins\": $VORHER}" >/dev/null
ZURUECK=$(api "$TMP/admin.jar" "$BASE/api/admin/settings" | jqp "
__import__('json').dumps(d.get('app_origins') or [])")
expect "$VORHER" "$ZURUECK" "Die Liste erlaubter Ziele steht wieder wie vorher"

# ------------------------------------------- Anmeldung über Keycloak
#
# Etappe B: Ein Token von Keycloak wird zum Nachweis. Das ist die Stelle, an
# der Nachlässigkeit teuer wird — deshalb wird hier nicht nur der glückliche
# Fall geprüft, sondern vor allem die Ablehnungen.
echo
echo "Anmeldung über Keycloak"

KC_SECRET="${OTA_KEYCLOAK_SECRET:-}"
KC_INT="http://ota-keycloak:8080/auth"

if [ -z "$KC_SECRET" ]; then
  bad "OTA_KEYCLOAK_SECRET fehlt — die Keycloak-Prüfungen entfallen"
else
  # Ein Konto, das es nur in Keycloak gibt.
  KT=$(docker exec -i ota-agent curl -s -d "client_id=ota-manager" \
        --data-urlencode "client_secret=$KC_SECRET" -d "grant_type=client_credentials" \
        "$KC_INT/realms/ota/protocol/openid-connect/token" | jqp "d.get('access_token','')")

  docker exec -i ota-agent curl -s -X POST "$KC_INT/admin/realms/ota/users" \
    -H "Authorization: Bearer $KT" -H 'Content-Type: application/json' \
    -d '{"username":"kc-pruef","enabled":true,"emailVerified":true,
         "email":"kc-pruef@ota.test","firstName":"Kirsten","lastName":"Probe",
         "requiredActions":[],
         "credentials":[{"type":"password","value":"KcPruef2026!xy","temporary":false}]}' \
    >/dev/null 2>&1

  ID_TOKEN=$(docker exec -i ota-agent curl -s -d "client_id=ota-tests" \
    --data-urlencode "client_secret=$KC_SECRET-tests" -d "grant_type=password" \
    -d "username=kc-pruef" --data-urlencode "password=KcPruef2026!xy" -d "scope=openid" \
    "$KC_INT/realms/ota/protocol/openid-connect/token" | jqp "d.get('id_token','')")

  if [ -z "$ID_TOKEN" ]; then
    bad "Kein ID-Token von Keycloak — Direct Access Grants aus?"
  else
    ok "Keycloak stellt ein ID-Token aus (Weg der Prüfreihen, §5e)"

    rm -f "$TMP/kc.jar"
    CODE=$(curl -s --cacert "$CA" -c "$TMP/kc.jar" -o /dev/null -w '%{http_code}' \
      -X POST "$BASE/api/auth/oidc/token" -H 'Content-Type: application/json' \
      -d "{\"id_token\":\"$ID_TOKEN\"}")
    expect "200" "$CODE" "Ein gültiges Token wird zur OTA-Sitzung"

    WER=$(api "$TMP/kc.jar" "$BASE/api/auth/me" | jqp "d.get('username','')")
    expect "kc-pruef" "$WER" "Und die Sitzung gehört dem richtigen Menschen"

    HERKUNFT=$(api "$TMP/admin.jar" "$BASE/api/admin/users" | jqp "
next((u['auth_provider'] for u in d if u['username'] == 'kc-pruef'), '')")
    expect "keycloak" "$HERKUNFT" "Das Konto ist als Keycloak-Konto geführt"

    # Die zweite Stufe gehört nach Keycloak. Ein Keycloak-Konto darf hier
    # nicht zusätzlich in OTAs eigene TOTP-Einrichtung geschickt werden.
    ZWEITE=$(api "$TMP/kc.jar" "$BASE/api/auth/me" | jqp "str(d.get('must_setup_totp'))")
    expect "False" "$ZWEITE" "Keycloak-Konten landen nicht in OTAs eigener zweiter Stufe"
  fi

  # Und jetzt die Ablehnungen.
  CODE=$(curl -s --cacert "$CA" -o /dev/null -w '%{http_code}' \
    -X POST "$BASE/api/auth/oidc/token" -H 'Content-Type: application/json' \
    -d '{"id_token":"nicht.mal.ein-token"}')
  expect "401" "$CODE" "Unsinn wird abgewiesen"

  # Ein selbstgebautes Token mit derselben Struktur, aber fremder Signatur.
  GEFAELSCHT=$(python3 -c "
import base64, json
def b(x): return base64.urlsafe_b64encode(json.dumps(x).encode()).rstrip(b'=').decode()
print(b({'alg':'RS256','kid':'egal'}) + '.' +
      b({'sub':'11111111-1111-1111-1111-111111111111','preferred_username':'eindringling',
         'iss':'http://ota-keycloak:8080/auth/realms/ota','aud':'ota','exp':99999999999,'iat':1}) +
      '.Zm9v')")
  CODE=$(curl -s --cacert "$CA" -o /dev/null -w '%{http_code}' \
    -X POST "$BASE/api/auth/oidc/token" -H 'Content-Type: application/json' \
    -d "{\"id_token\":\"$GEFAELSCHT\"}")
  expect "401" "$CODE" "Ein selbstgebautes Token ohne gültige Signatur ebenso"

  DA=$(api "$TMP/admin.jar" "$BASE/api/admin/users" | jqp "
str(len([u for u in d if u['username'] == 'eindringling']))")
  expect "0" "$DA" "Und es entsteht dabei kein Konto"

  # Der Rückkanal nimmt nur Abmeldetoken an — ein gewöhnliches ID-Token
  # dürfte sonst jeden aus seiner Sitzung werfen.
  if [ -n "${ID_TOKEN:-}" ]; then
    CODE=$(curl -s --cacert "$CA" -o /dev/null -w '%{http_code}' \
      -X POST "$BASE/api/auth/oidc/backchannel" \
      --data-urlencode "logout_token=$ID_TOKEN")
    expect "400" "$CODE" "Der Rückkanal nimmt kein gewöhnliches Token als Abmeldung"
  fi

  # Ein lokales Konto wird nicht übernommen, auch nicht mit gleichem Namen.
  docker exec -i ota-agent curl -s -X POST "$KC_INT/admin/realms/ota/users" \
    -H "Authorization: Bearer $KT" -H 'Content-Type: application/json' \
    -d "{\"username\":\"$ADMIN_USER\",\"enabled\":true,\"emailVerified\":true,
         \"email\":\"doppel@ota.test\",\"firstName\":\"Doppel\",\"lastName\":\"Gaenger\",
         \"requiredActions\":[],
         \"credentials\":[{\"type\":\"password\",\"value\":\"Fremdes-Passwort-2026!\",\"temporary\":false}]}" \
    >/dev/null 2>&1
  DOPPEL=$(docker exec -i ota-agent curl -s -d "client_id=ota-tests" \
    --data-urlencode "client_secret=$KC_SECRET-tests" -d "grant_type=password" \
    -d "username=$ADMIN_USER" --data-urlencode "password=Fremdes-Passwort-2026!" -d "scope=openid" \
    "$KC_INT/realms/ota/protocol/openid-connect/token" | jqp "d.get('id_token','')")
  if [ -n "$DOPPEL" ]; then
    CODE=$(curl -s --cacert "$CA" -o /dev/null -w '%{http_code}' \
      -X POST "$BASE/api/auth/oidc/token" -H 'Content-Type: application/json' \
      -d "{\"id_token\":\"$DOPPEL\"}")
    expect "403" "$CODE" "Ein gleichnamiges lokales Konto wird nicht übernommen"

    IMMERNOCH=$(api "$TMP/admin.jar" "$BASE/api/admin/users" | jqp "
next((u['auth_provider'] for u in d if u['username'] == '$ADMIN_USER'), '')")
    expect "local" "$IMMERNOCH" "Und es bleibt ein lokales Konto"
  else
    bad "Der Doppelgänger liess sich in Keycloak nicht anlegen"
  fi

  # Aufräumen: der Doppelgänger hat in Keycloak nichts verloren.
  DID=$(docker exec -i ota-agent curl -s "$KC_INT/admin/realms/ota/users?username=$ADMIN_USER" \
        -H "Authorization: Bearer $KT" | jqp "d[0]['id'] if d else ''")
  [ -n "$DID" ] && docker exec -i ota-agent curl -s -X DELETE \
    "$KC_INT/admin/realms/ota/users/$DID" -H "Authorization: Bearer $KT" >/dev/null 2>&1
fi

# ------------------------------------------------------- Einmal-Skripte
#
# Der Fall: Ein neues Golden Image braucht eine Aenderung im Zuhause, die das
# Skeleton nicht mehr erreicht. Gemessen wird die ganze Kette — anlegen,
# einmal laufen, **nicht** zweimal laufen, Fehler festhalten, zuruecksetzen.
echo
echo "Einmal-Skripte"

WS_E=$(api "$TMP/admin.jar" "$BASE/api/templates" | jqp "
next((t['id'] for t in d if t['mode'] == 'workspace'), '')")

CODE=$(code "$TMP/user.jar" "$BASE/api/templates/$WS_E/once")
expect "403" "$CODE" "Ein normaler Nutzer sieht die Einmal-Skripte nicht"

MARKE="einmal-$$"
SC=$(api "$TMP/admin.jar" -X POST "$BASE/api/templates/$WS_E/once" \
      -H 'Content-Type: application/json' \
      -d "{\"name\":\"Pruefung $MARKE\",\"body\":\"echo $MARKE > \\\"\$HOME/einmal.txt\\\"\\n\"}" \
     | jqp "d.get('id','')")

if [ -z "$SC" ]; then
  bad "Das Einmal-Skript liess sich nicht anlegen"
else
  ok "Einmal-Skript angelegt"

  SID_E=$(api "$TMP/admin.jar" "$BASE/api/sessions" | jqp "
next((s['id'] for s in d if s['template_id'] == '$WS_E' and s['status'] == 'running'), '')")
  [ -n "$SID_E" ] && api "$TMP/admin.jar" -X DELETE "$BASE/api/sessions/$SID_E" >/dev/null
  sleep 4
  NEU=$(api "$TMP/admin.jar" -X POST "$BASE/api/sessions" -H 'Content-Type: application/json' \
         -d "{\"template_id\":\"$WS_E\"}" | jqp "d.get('id','')")
  sleep 12

  CN_E="ota-s-$(echo "$NEU" | cut -c1-12)"
  DA=$(docker exec "$CN_E" sh -c 'cat /home/kasm-user/einmal.txt 2>/dev/null' | tr -d '\r\n')
  expect "$MARKE" "$DA" "Es läuft beim ersten Start"

  GEZAEHLT=$(api "$TMP/admin.jar" "$BASE/api/templates/$WS_E/once" | jqp "
str(next((x['ran_count'] for x in d if x['id'] == '$SC'), 0))")
  expect "1" "$GEZAEHLT" "OTA hat den Lauf verbucht"

  # Und jetzt der Kern: beim zweiten Start passiert nichts mehr.
  docker exec "$CN_E" sh -c 'echo VON-HAND > /home/kasm-user/einmal.txt'
  api "$TMP/admin.jar" -X DELETE "$BASE/api/sessions/$NEU" >/dev/null
  sleep 4
  NEU2=$(api "$TMP/admin.jar" -X POST "$BASE/api/sessions" -H 'Content-Type: application/json' \
          -d "{\"template_id\":\"$WS_E\"}" | jqp "d.get('id','')")
  sleep 12
  CN_E2="ota-s-$(echo "$NEU2" | cut -c1-12)"
  NOCHMAL=$(docker exec "$CN_E2" sh -c 'cat /home/kasm-user/einmal.txt 2>/dev/null' | tr -d '\r\n')
  expect "VON-HAND" "$NOCHMAL" "Beim zweiten Start läuft es nicht noch einmal"

  # Zuruecksetzen nimmt nur die Notiz zurueck — ausgefuehrt wird beim Start.
  ZURUECK=$(api "$TMP/admin.jar" -X POST "$BASE/api/templates/$WS_E/once/$SC/again" \
            | jqp "str(d.get('count', 0))")
  expect "1" "$ZURUECK" "„Nochmal“ setzt die Buchführung zurück"

  api "$TMP/admin.jar" -X DELETE "$BASE/api/templates/$WS_E/once/$SC" >/dev/null
  WEG=$(api "$TMP/admin.jar" "$BASE/api/templates/$WS_E/once" | jqp "
str(len([x for x in d if x['id'] == '$SC']))")
  expect "0" "$WEG" "Gelöscht ist gelöscht"
  docker exec "$CN_E2" sh -c 'rm -f /home/kasm-user/einmal.txt' 2>/dev/null || true
fi

# ---------------------------------------------------- Die beiden Ablagen
#
# Sie sind bewusst getrennt: Die gemeinsame gehoert der Verwaltung und liegt
# in den Containern nur lesbar, die eigene gehoert je einem Menschen und ist
# beschreibbar. Geprueft wird beides — und vor allem, dass keiner in die des
# anderen sieht.
echo
echo "Ablagen"

echo "Vom Nutzer $(basename x)" > "$TMP/eigen.txt"
echo "Vom Administrator" > "$TMP/adm.txt"

CODE=$(code "$TMP/user.jar" "$BASE/api/shared")
expect "403" "$CODE" "Die gemeinsame Ablage ist für einen normalen Nutzer zu"
CODE=$(code "$TMP/user.jar" "$BASE/api/shared/file?path=egal")
expect "403" "$CODE" "Auch einzelne Dateien daraus"
CODE=$(code "$TMP/admin.jar" "$BASE/api/shared")
expect "200" "$CODE" "Der Administrator kommt weiterhin heran"

api "$TMP/user.jar" -F "file=@$TMP/eigen.txt" "$BASE/api/files/upload" >/dev/null
api "$TMP/admin.jar" -F "file=@$TMP/adm.txt" "$BASE/api/files/upload" >/dev/null

U_SIEHT=$(api "$TMP/user.jar" "$BASE/api/files" | jqp "
','.join(sorted(e['name'] for e in d['entries']))")
A_SIEHT=$(api "$TMP/admin.jar" "$BASE/api/files" | jqp "
','.join(sorted(e['name'] for e in d['entries']))")

case "$U_SIEHT" in
  *eigen.txt*) ok "Der Nutzer sieht seine eigene Datei ($U_SIEHT)" ;;
  *) bad "Der Nutzer sieht seine eigene Datei nicht ($U_SIEHT)" ;;
esac
case "$U_SIEHT" in
  *adm.txt*) bad "Der Nutzer sieht die Ablage des Administrators ($U_SIEHT)" ;;
  *) ok "Und nicht die des Administrators" ;;
esac
case "$A_SIEHT" in
  *eigen.txt*) bad "Der Administrator sieht die Ablage des Nutzers ($A_SIEHT)" ;;
  *) ok "Der Administrator sieht die des Nutzers ebenso wenig" ;;
esac

# Und der eigentliche Zweck: der Weg in den Container und wieder heraus.
WS_A=$(api "$TMP/admin.jar" "$BASE/api/templates" | jqp "
next((t['id'] for t in d if t['mode'] == 'workspace'), '')")
SID_A=$(laufende_session "$WS_A")

if [ -z "$SID_A" ]; then
  bad "Keine laufende Session für die Ablage-Prüfung"
else
  CN_A="ota-s-$(echo "$SID_A" | cut -c1-12)"
  DRIN=$(docker exec "$CN_A" sh -c 'cat /mnt/austausch/adm.txt 2>/dev/null' | tr -d '\r\n')
  expect "Vom Administrator" "$DRIN" "Was im Browser landet, liegt im Container"

  MARKE="von-innen-$$"
  docker exec -u 1000 "$CN_A" sh -c "echo $MARKE > /mnt/austausch/rueckweg.txt" 2>/dev/null
  RAUS=$(api "$TMP/admin.jar" "$BASE/api/files/file?path=rueckweg.txt" | tr -d '\r\n')
  expect "$MARKE" "$RAUS" "Und was der Container schreibt, sieht der Browser"

  SCHREIBT=$(docker exec -u 1000 "$CN_A" sh -c 'touch /mnt/ota/darf-nicht 2>&1' | grep -c "Read-only")
  expect "1" "${SCHREIBT:-0}" "Die gemeinsame Ablage bleibt im Container schreibgeschützt"

  api "$TMP/admin.jar" -X DELETE "$BASE/api/files?path=rueckweg.txt" >/dev/null
  api "$TMP/admin.jar" -X DELETE "$BASE/api/files?path=adm.txt" >/dev/null
fi

api "$TMP/user.jar" -X DELETE "$BASE/api/files?path=eigen.txt" >/dev/null
REST=$(api "$TMP/user.jar" "$BASE/api/files" | jqp "str(len(d['entries']))")
expect "0" "$REST" "Löschen räumt die eigene Ablage wieder"

# ------------------------------------------- Anwendung ohne Display
# Stirbt das X-Display einer Anwendung, kehrte der Startaufruf zurück, ohne
# etwas zu tun: Der Eintrag sagte „läuft". Damit war die Anwendung für immer
# tot — der Tab zeigte einen abgerissenen Stream, und der Startknopf im
# Dashboard bewirkte nichts. Gemessen am 2026-08-28.
echo
echo "Anwendung, deren Display verschwunden ist"

WS_D=$(api "$TMP/admin.jar" "$BASE/api/templates" | jqp "
next((t['id'] for t in d if t['mode'] == 'workspace' and t['apps']), '')")
SID_D=$(laufende_session "$WS_D")
APP_D=$(api "$TMP/admin.jar" "$BASE/api/templates/$WS_D" | jqp "
next((a['slug'] for a in d['apps'] if a['is_enabled'] and not a.get('blocked_reason')), '')")

if [ -z "$SID_D" ] || [ -z "$APP_D" ]; then
  bad "Keine laufende Session für die Prüfung"
else
  CN_D="ota-s-$(echo "$SID_D" | cut -c1-12)"
  api "$TMP/admin.jar" -X POST "$BASE/api/sessions/$SID_D/apps/$APP_D" >/dev/null
  sleep 5
  D_NUM=$(api "$TMP/admin.jar" "$BASE/api/sessions" | jqp "
next((str(st['display_num']) for s in d if s['id'] == '$SID_D'
      for st in s['streams'] if st['app_slug'] == '$APP_D'), '')")

  if [ -z "$D_NUM" ]; then
    bad "Die Anwendung liess sich nicht starten"
  else
    ok "$APP_D läuft auf Display :$D_NUM"

    # Am Rücken von OTA vorbei kappen — wie ein Absturz der Anwendung.
    # Der Klammertrick verhindert, dass das Muster die eigene Kommandozeile
    # trifft; ohne ihn bringt pkill die aufrufende Shell um.
    docker exec "$CN_D" sh -c "pkill -f '[X]vnc :$D_NUM'; exit 0" >/dev/null 2>&1
    sleep 3
    WEG=$(docker exec "$CN_D" sh -c "ls /tmp/.X11-unix/X$D_NUM 2>/dev/null | wc -l")
    expect "0" "${WEG:-?}" "Das Display ist weg"

    GLAUBT=$(api "$TMP/admin.jar" "$BASE/api/sessions" | jqp "
next((st['status'] for s in d if s['id'] == '$SID_D'
      for st in s['streams'] if st['app_slug'] == '$APP_D'), '')")
    ok "OTA führt es noch als „$GLAUBT“ — es weiss es ja nicht besser"

    # Und jetzt der Punkt: Der Start muss das merken und neu aufmachen.
    api "$TMP/admin.jar" -X POST "$BASE/api/sessions/$SID_D/apps/$APP_D" >/dev/null
    sleep 6
    DA=$(docker exec "$CN_D" sh -c "ls /tmp/.X11-unix/X$D_NUM 2>/dev/null | wc -l")
    expect "1" "${DA:-?}" "Ein erneuter Start macht das Display wieder auf"
  fi
fi

# ---------------------------------------- Session ohne Container
# Eine Session, deren Container verschwunden ist, darf nicht im Weg stehen.
# Sie zählt sonst als „live", der nächste Startversuch bekommt sie zurück
# statt einer neuen — und der Arbeitsplatz lässt sich stundenlang nicht mehr
# starten, während die Oberfläche „starting" zeigt. Gemessen am 2026-08-28.
echo
echo "Session, deren Container verschwunden ist"

WS_L=$(api "$TMP/admin.jar" "$BASE/api/templates" | jqp "
next((t['id'] for t in d if t['mode'] == 'workspace' and t['apps']), '')")
SID_L=$(api "$TMP/admin.jar" "$BASE/api/sessions" | jqp "
next((s['id'] for s in d if s['template_id'] == '$WS_L'), '')")
if [ -z "$SID_L" ]; then
  SID_L=$(api "$TMP/admin.jar" -X POST "$BASE/api/sessions" -H 'Content-Type: application/json' \
    -d "{\"template_id\":\"$WS_L\"}" | jqp "d.get('id','')")
fi

if [ -z "$SID_L" ]; then
  bad "Keine Session für die Prüfung"
else
  CN_L="ota-s-$(echo "$SID_L" | cut -c1-12)"
  # Am Rücken von OTA vorbei entfernen — genau wie es ein fremder Aufräumer
  # oder ein Neustart des Docker-Dienstes täte.
  docker rm -f "$CN_L" >/dev/null 2>&1
  STAND=$(api "$TMP/admin.jar" "$BASE/api/sessions" | jqp "
next((s['status'] for s in d if s['id'] == '$SID_L'), 'weg')")
  ok "Die Datenbank führt sie noch als „$STAND“ — sie weiß es ja nicht besser"

  NEU=$(api "$TMP/admin.jar" -X POST "$BASE/api/sessions" -H 'Content-Type: application/json' \
    -d "{\"template_id\":\"$WS_L\"}")
  SID_N=$(echo "$NEU" | jqp "d.get('id','')")
  if [ -n "$SID_N" ] && [ "$SID_N" != "$SID_L" ]; then
    ok "Der nächste Start bekommt eine neue Session statt der Leiche"
  else
    bad "Der Start gab die tote Session zurück: $(echo "$NEU" | head -c 140)"
  fi
  ALT=$(api "$TMP/admin.jar" "$BASE/api/sessions?all_users=true" | jqp "
next((s['status'] for s in d if s['id'] == '$SID_L'), 'weg')")
  case "$ALT" in
    running|starting|paused) bad "Die alte Session gilt weiter als lebendig ($ALT)" ;;
    *)                       ok "Und die alte ist geschlossen ($ALT)" ;;
  esac
fi

# ------------------------------------------------------- Skeleton-Profil
# Womit ein Zuhause anfaengt. Geprueft wird beides: dass ein durchgesetzter
# Pfad bei jedem Start ankommt, und dass niemand aus dem Skeleton herauskommt.
echo
echo "Skeleton-Profil"

WS_S=$(api "$TMP/admin.jar" "$BASE/api/templates" | jqp "
next((t['id'] for t in d if t['mode'] == 'workspace' and t['apps']), '')")
SKEL="$BASE/api/templates/$WS_S/skeleton"
MARKE="ota-pruef-skeleton-$RANDOM"

if [ -z "$WS_S" ]; then
  bad "Kein Arbeitsplatz für die Skeleton-Prüfung"
else
  printf 'Skeleton war hier\n' > "$TMP/$MARKE"
  api "$TMP/admin.jar" -X POST "$SKEL/upload?path=" -F "file=@$TMP/$MARKE" >/dev/null
  api "$TMP/admin.jar" "$SKEL" | grep -q "$MARKE" \
    && ok "Datei liegt im Skeleton" \
    || bad "Die Datei kam nicht im Skeleton an"

  # Punktdateien sind der Normalfall — ein Skeleton besteht grösstenteils
  # aus ihnen. Die gemeinsame Ablage lehnt sie ab, hier müssen sie durch.
  printf 'x\n' > "$TMP/.ota-pruef-punkt"
  api "$TMP/admin.jar" -X POST "$SKEL/upload?path=" -F "file=@$TMP/.ota-pruef-punkt" >/dev/null
  api "$TMP/admin.jar" "$SKEL" | grep -q "ota-pruef-punkt" \
    && ok "Punktdateien sind erlaubt" \
    || bad "Eine Punktdatei wurde abgelehnt — ein Skeleton besteht daraus"

  # Kein Weg nach draussen. Dieselbe Prüfung wie bei der Ablage, denn es ist
  # dieselbe Art Fehler.
  OUT=$(api "$TMP/admin.jar" "$SKEL?path=../../etc")
  grep -q "nicht erlaubt\|ausserhalb" <<<"$OUT" \
    && ok "Ein Pfad nach draussen wird abgelehnt" \
    || bad "Der Ausbruchsversuch ging durch: $(echo "$OUT" | head -c 100)"

  expect "403" "$(code "$TMP/user.jar" "$SKEL")" \
    "Das Skeleton ist für einen normalen Nutzer gesperrt"

  # Und jetzt der Weg in den Container: durchsetzen, Session neu starten,
  # nachsehen.
  VORHER=$(api "$TMP/admin.jar" "$BASE/api/templates/$WS_S" | jqp "
__import__('json').dumps(d.get('skeleton_enforce') or [])")
  api "$TMP/admin.jar" -X PUT "$BASE/api/templates/$WS_S" \
    -H 'Content-Type: application/json' \
    -d "$(api "$TMP/admin.jar" "$BASE/api/templates/$WS_S" | MARKE="$MARKE" python3 -c '
import json, os, sys
d = json.load(sys.stdin)
keep = ("friendly_name","description","icon","categories","mode","image_ref","cores",
        "memory_bytes","x_res","y_res","idle_minutes","idle_action","persistence_scope",
        "rights","env","start_script","is_enabled","group_ids")
b = {k: d[k] for k in keep if k in d}
b["skeleton_enforce"] = [os.environ["MARKE"]]
print(json.dumps(b))')" >/dev/null

  SID_S=$(api "$TMP/admin.jar" "$BASE/api/sessions" | jqp "
next((s['id'] for s in d if s['template_id'] == '$WS_S'), '')")
  # Erst wirklich weg, dann neu. Zwei Sessions auf demselben Zuhause weist
  # OTA ab (plan.md §15.2) — und ein DELETE, das noch nachläuft, sieht für
  # den nächsten Start genauso aus wie eine laufende zweite Session. Der
  # Testlauf meldete dann „keine Session", und daran war nichts falsch
  # ausser der Wartezeit.
  if [ -n "$SID_S" ]; then
    ALT="ota-s-$(echo "$SID_S" | cut -c1-12)"
    api "$TMP/admin.jar" -X DELETE "$BASE/api/sessions/$SID_S" >/dev/null
    for _ in $(seq 1 20); do
      docker inspect "$ALT" >/dev/null 2>&1 || break
      sleep 2
    done
  fi

  ANTWORT=$(api "$TMP/admin.jar" -X POST "$BASE/api/sessions" -H 'Content-Type: application/json' \
    -d "{\"template_id\":\"$WS_S\"}")
  SID_S=$(echo "$ANTWORT" | jqp "d.get('id','')")
  [ -z "$SID_S" ] && echo "    Start abgelehnt: $(echo "$ANTWORT" | head -c 160)"

  # Auf den Container warten statt auf gut Glück ein paar Sekunden zu
  # schlafen. Ein `sleep 4` hat hier einmal danebengegriffen — und der
  # Folgetest suchte dann einen Container, den es nie gab.
  CN_S=""
  for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
    CN_S=$(docker ps --filter "label=ota.session_id" --format '{{.Names}}' \
      | grep "$(echo "$SID_S" | cut -c1-12)" | head -1)
    [ -n "$CN_S" ] && break
    sleep 3
  done
  if [ -n "$CN_S" ]; then
    docker exec "$CN_S" test -f "/home/kasm-user/$MARKE" \
      && ok "Der durchgesetzte Pfad ist beim Start im Zuhause" \
      || bad "Der durchgesetzte Pfad kam nicht an"
    OWNER=$(docker exec "$CN_S" stat -c '%u:%g' "/home/kasm-user/$MARKE" 2>/dev/null)
    expect "1000:1000" "$OWNER" "Und gehört dem Nutzer, nicht root"
  else
    bad "Keine Session zum Prüfen des Skeletons"
  fi

  # Aufräumen: Datei löschen — dabei muss die Kennung aus „durchsetzen"
  # verschwinden, sonst stünde dort ein Pfad, den es nicht mehr gibt.
  api "$TMP/admin.jar" -X DELETE "$SKEL?path=$MARKE" >/dev/null
  REST=$(api "$TMP/admin.jar" "$BASE/api/templates/$WS_S" | jqp "len(d.get('skeleton_enforce') or [])")
  expect "0" "$REST" "Eine gelöschte Datei verschwindet aus „durchsetzen“"
  api "$TMP/admin.jar" -X DELETE "$SKEL?path=.ota-pruef-punkt" >/dev/null

  api "$TMP/admin.jar" -X PUT "$BASE/api/templates/$WS_S" \
    -H 'Content-Type: application/json' \
    -d "$(api "$TMP/admin.jar" "$BASE/api/templates/$WS_S" | VORHER="$VORHER" python3 -c '
import json, os, sys
d = json.load(sys.stdin)
keep = ("friendly_name","description","icon","categories","mode","image_ref","cores",
        "memory_bytes","x_res","y_res","idle_minutes","idle_action","persistence_scope",
        "rights","env","start_script","is_enabled","group_ids")
b = {k: d[k] for k in keep if k in d}
b["skeleton_enforce"] = json.loads(os.environ["VORHER"])
print(json.dumps(b))')" >/dev/null
fi

# ------------------------------------------------- Session einfrieren
# Der kurze Weg zu einem Golden Image: im eigenen Arbeitsplatz einrichten,
# dann einfrieren. Geprüft wird vor allem, was dabei **nicht** mitkommt.
echo
echo "Session einfrieren"

WS_F=$(api "$TMP/admin.jar" "$BASE/api/templates" | jqp "
next((t['id'] for t in d if t['mode'] == 'workspace' and t['apps']), '')")
SID_F=$(api "$TMP/admin.jar" "$BASE/api/sessions" | jqp "
next((s['id'] for s in d if s['template_id'] == '$WS_F' and s['status'] == 'running'), '')")

CN_F=""
if [ -n "$SID_F" ]; then
  CN_F="ota-s-$(echo "$SID_F" | cut -c1-12)"
  # Die Datenbank kann eine Session als laufend fuehren, deren Container es
  # nicht mehr gibt — etwa nach einem abgebrochenen Lauf. Dann ist nicht das
  # Einfrieren kaputt, sondern der Vorzustand.
  docker inspect "$CN_F" >/dev/null 2>&1 || CN_F=""
fi

if [ -z "$CN_F" ]; then
  ok "Kein eigener Arbeitsplatz am Laufen — Einfrieren übersprungen"
else

  # Etwas, das nach einem Geheimnis aussieht. Die Vorschau muss es finden.
  docker exec -u 0 "$CN_F" sh -c 'mkdir -p /root/.ssh && echo x > /root/.ssh/id_pruef' \
    >/dev/null 2>&1

  # Und die sudo-Ausnahme. Sie steht normalerweise dort, weil der Container
  # einem Administrator gehoert — aber der Test soll nicht davon abhaengen,
  # was ein vorheriger Lauf hinterlassen hat.
  docker exec -u 0 "$CN_F" sh -c \
    'mkdir -p /etc/sudoers.d && echo "# OTA" > /etc/sudoers.d/ota-admin' >/dev/null 2>&1

  VOR=$(api "$TMP/admin.jar" "$BASE/api/templates/$WS_F/freeze/preview")
  grep -q "id_pruef" <<<"$VOR" \
    && ok "Die Vorschau findet eine Datei, die nach einem Geheimnis aussieht" \
    || bad "Die Vorschau übersah /root/.ssh/id_pruef"

  grep -q "/etc/sudoers.d/ota-admin" <<<"$VOR" \
    && ok "Die sudo-Ausnahme steht als „wird entfernt“ in der Vorschau" \
    || bad "Die sudo-Ausnahme fehlt in der Vorschau"

  # Das Zuhause ist ein Bind-Mount und darf gar nicht erst auftauchen.
  grep -q "/home/kasm-user" <<<"$VOR" \
    && bad "Das Zuhause steht in der Vorschau — es gehört nicht ins Image" \
    || ok "Das Zuhause taucht in der Vorschau nicht auf"

  # Und ohne ausdrückliche Bestätigung wird abgelehnt. Eine Vorschau, die man
  # übergehen kann, ist Dekoration.
  OUT=$(api "$TMP/admin.jar" -X POST "$BASE/api/templates/$WS_F/freeze" \
    -H 'Content-Type: application/json' -d '{"comment":"Prüfung"}')
  grep -q "nach einem Geheimnis aus" <<<"$OUT" \
    && ok "Ohne ausdrückliche Bestätigung wird nicht eingefroren" \
    || bad "Es wurde trotz Fund eingefroren: $(echo "$OUT" | head -c 120)"

  # Der Container wird hinter OTAs Rücken pausiert: Die Datenbank sagt „läuft",
  # der Container nicht. `docker commit` haengt auf einem pausierten Container
  # unbegrenzt — ohne Fehler, ohne Meldung, einfach Stillstand. Der Agent muss
  # das selbst merken; er darf der Sicht der API nicht trauen.
  docker pause "$CN_F" >/dev/null 2>&1

  # Einmal richtig einfrieren und nachsehen, dass die sudo-Ausnahme **nicht**
  # im Image landet, aber danach im laufenden Container wieder da ist. Wer ein
  # Image baut, soll dabei nicht sein eigenes `sudo` verlieren.
  OUT=$(api "$TMP/admin.jar" -X POST "$BASE/api/templates/$WS_F/freeze" \
    -H 'Content-Type: application/json' \
    -d '{"comment":"Prüflauf","trotz_geheimnissen":true}')
  IMG=$(echo "$OUT" | jqp "d.get('image_ref') or ''")
  docker unpause "$CN_F" >/dev/null 2>&1   # falls es doch scheiterte
  if [ -n "$IMG" ]; then
    ok "Eingefroren als $IMG"
    grep -q "pausiert und wurde dafür aufgeweckt" <<<"$OUT" \
      && ok "Der pausierte Container wurde erkannt und aufgeweckt" \
      || bad "Die Pause blieb unbemerkt — das hätte hängen müssen"
    docker run --rm --entrypoint test "$IMG" -f /etc/sudoers.d/ota-admin \
      && bad "Die sudo-Ausnahme ist mit eingefroren — jeder bekäme root" \
      || ok "Die sudo-Ausnahme ist nicht im Image"
    docker exec "$CN_F" test -f /etc/sudoers.d/ota-admin \
      && ok "Im laufenden Container liegt sie wieder da" \
      || bad "Dem Administrator wurde sein sudo genommen"
    # Aufräumen über die Schnittstelle statt mit `docker rmi`: So verschwindet
    # auch der Eintrag, und der Test hinterlässt keine „Prüflauf"-Fassung in
    # der Liste des Administrators.
    BID_F=$(echo "$OUT" | jqp "d.get('id','')")
    RES=$(api "$TMP/admin.jar" -X DELETE "$BASE/api/templates/$WS_F/builds/$BID_F")
    grep -q "entfernt" <<<"$RES" \
      && ok "Die Prüf-Fassung lässt sich wieder entfernen" \
      || bad "Die Prüf-Fassung blieb stehen: $(echo "$RES" | head -c 120)"
    docker rmi -f "$IMG" >/dev/null 2>&1

    # Und die aktive Fassung bleibt, was auch immer man anklickt.
    CUR=$(api "$TMP/admin.jar" "$BASE/api/templates/$WS_F/builds" | jqp "
next((b['id'] for b in d if b['is_current']), '')")
    if [ -n "$CUR" ]; then
      RES=$(api "$TMP/admin.jar" -X DELETE "$BASE/api/templates/$WS_F/builds/$CUR")
      grep -q "in Betrieb" <<<"$RES" \
        && ok "Die aktive Fassung lässt sich nicht löschen" \
        || bad "Die aktive Fassung liess sich löschen — der nächste Start bräche ab"
    fi
  else
    bad "Einfrieren schlug fehl: $(echo "$OUT" | head -c 160)"
  fi

  docker exec -u 0 "$CN_F" rm -rf /root/.ssh >/dev/null 2>&1

  expect "403" "$(code "$TMP/user.jar" "$BASE/api/templates/$WS_F/freeze/preview")" \
    "Einfrieren ist für einen normalen Nutzer gesperrt"
fi

# ------------------------------------------------- Ereignisstrom des Builds
echo
echo "Ereignisstrom des Builds"

WS_B=$(api "$TMP/admin.jar" "$BASE/api/templates" | jqp "
next((t['id'] for t in d if t['mode'] == 'workspace'), '')")
LAST_B=$(api "$TMP/admin.jar" "$BASE/api/templates/$WS_B/builds" | jqp "d[0]['id'] if d else ''")

if [ -n "$LAST_B" ]; then
  # Ein abgeschlossener Build: Der Strom muss das gesammelte Protokoll
  # nachliefern und sich dann von selbst schliessen, statt offen zu bleiben.
  OUT=$(timeout 20 curl -s --cacert "$CA" -b "$TMP/admin.jar" -N \
    "$BASE/api/templates/$WS_B/builds/$LAST_B/stream")
  grep -q "^event: end" <<<"$OUT" \
    && ok "Der Strom schliesst sich nach einem fertigen Build" \
    || bad "Kein Schlussereignis — die Verbindung bliebe offen"
  grep -q '^data: {"chunk"' <<<"$OUT" \
    && ok "Das Protokoll kommt als Zuwachs statt als Ganzes" \
    || bad "Keine Protokoll-Ereignisse im Strom"
  if grep -q "event: status" <<<"$OUT"; then
    ok "Der Zustand wird gemeldet"
  else
    # Mit Anfang des Stroms, sonst ist der Befund nicht nachvollziehbar:
    # Diese Prüfung schlug einmal fehl, während der Strom von Hand geprüft
    # genau dieses Ereignis als allererste Zeile lieferte.
    bad "Kein Zustandsereignis im Strom — Anfang: $(echo "$OUT" | head -c 120 | tr '\n' '|')"
  fi

  expect "403" "$(code "$TMP/user.jar" "$BASE/api/templates/$WS_B/builds/$LAST_B/stream")" \
    "Der Strom ist für einen normalen Nutzer gesperrt"
else
  ok "Kein Build vorhanden — Strom-Prüfung übersprungen"
fi

# ------------------------------------------------- Zustand und Kennzahlen
echo
echo "Zustand und Kennzahlen"

HEALTH=$(curl -s --cacert "$CA" "$BASE/healthz")
grep -q '"db":"ok"' <<<"$HEALTH" \
  && ok "healthz prüft die Datenbank und meldet sie erreichbar" \
  || bad "healthz sagt nichts über die Datenbank: $HEALTH"
grep -q '"agent":"ok"' <<<"$HEALTH" \
  && ok "healthz prüft den Agent und meldet ihn erreichbar" \
  || bad "healthz sagt nichts über den Agent: $HEALTH"

# Kennzahlen verraten, wie viele Menschen hier arbeiten und wann. Nichts
# fuers offene Netz.
expect "401" "$(code /dev/null "$BASE/metrics")" "Kennzahlen ohne Anmeldung verweigert"
expect "403" "$(code "$TMP/user.jar" "$BASE/metrics")" "Kennzahlen für einen normalen Nutzer verweigert"

METRICS=$(api "$TMP/admin.jar" "$BASE/metrics")
grep -q "^ota_users " <<<"$METRICS" \
  && ok "Kennzahlen enthalten die Kontenzahl" \
  || bad "Kennzahlen ohne ota_users"
grep -q "^ota_agent_up 1" <<<"$METRICS" \
  && ok "Kennzahlen melden den Agent als erreichbar" \
  || bad "ota_agent_up fehlt oder steht auf 0"
grep -q "^# TYPE ota_sessions gauge" <<<"$METRICS" \
  && ok "Format ist Prometheus-lesbar (HELP/TYPE je Messwert)" \
  || bad "Kein TYPE-Kopf im Kennzahlen-Format"

if [ -n "${OTA_METRICS_TOKEN:-}" ]; then
  RC=$(curl -s --cacert "$CA" -o /dev/null -w '%{http_code}' \
    -H "Authorization: Bearer $OTA_METRICS_TOKEN" "$BASE/metrics")
  expect "200" "$RC" "Sammler kommt mit Merkmal herein"
  RC=$(curl -s --cacert "$CA" -o /dev/null -w '%{http_code}' \
    -H "Authorization: Bearer garantiert-falsch" "$BASE/metrics")
  expect "401" "$RC" "Falsches Merkmal wird abgewiesen"
fi

# ------------------------------------------------------------ Platz
echo
echo "Platz im Zuhause"

USAGE=$(api "$TMP/admin.jar" "$BASE/api/admin/users/$ADMIN_USER/usage")
BYTES=$(echo "$USAGE" | jqp "d.get('bytes', -1)")
[ "${BYTES:-0}" -gt 0 ] && ok "Belegter Platz gemessen ($((BYTES / 1024 / 1024)) MB)" \
                        || bad "Der Platz liess sich nicht messen: $USAGE"

QUOTA=$(echo "$USAGE" | jqp "d.get('quota_bytes', 0)")
[ "${QUOTA:-0}" -gt 0 ] && ok "Ein Kontingent ist gesetzt ($((QUOTA / 1024 / 1024 / 1024)) GB)" \
                        || ok "Kein Kontingent gesetzt — die Grenze ist abgeschaltet"

expect "403" "$(code "$TMP/user.jar" "$BASE/api/admin/users/$ADMIN_USER/usage")" \
  "Fremden Platzverbrauch abfragen verweigert"

# Der Punkt der ganzen Übung: eine verständliche Ablehnung statt eines
# Containers, der irgendwann beim Schreiben stehenbleibt. Dafür muss das
# Zuhause wirklich über der Grenze liegen — deshalb legt der Test dort einen
# Klotz ab und räumt ihn hinterher weg.
BEFORE=$(api "$TMP/admin.jar" "$BASE/api/admin/settings" | jqp "d['profile_quota_gb']")
PROFILE_ROOT="${OTA_PROFILES_ROOT:-/srv/ota/profiles}"
BALLAST="$PROFILE_ROOT/$ADMIN_USER/ota-pruef-ballast.bin"

if fallocate -l 2G "$BALLAST" 2>/dev/null || \
   dd if=/dev/zero of="$BALLAST" bs=1M count=2048 status=none 2>/dev/null; then
  api "$TMP/admin.jar" -X PUT "$BASE/api/admin/settings" -H 'Content-Type: application/json' \
    -d '{"profile_quota_gb":1}' >/dev/null
  sleep 6   # der Einstellungspuffer haelt fuenf Sekunden

  USED=$(api "$TMP/admin.jar" "$BASE/api/admin/users/$ADMIN_USER/usage" | jqp "d['bytes']")
  [ "${USED:-0}" -gt 1073741824 ] \
    && ok "Der Ballast wird mitgezählt ($((USED / 1024 / 1024)) MB > 1 GB)" \
    || bad "Der Ballast fehlt in der Messung ($USED)"

  # Ausdruecklich eine Vorlage **ohne** laufende Session: Laeuft schon eine,
  # gibt der Start sie zurueck, ohne den Preflight anzufassen — und das ist
  # richtig so, denn dabei wird nichts neu belegt.
  LIVE_TPLS=$(api "$TMP/admin.jar" "$BASE/api/sessions" | jqp "
','.join(s['template_id'] for s in d)")
  TPL_Q=$(api "$TMP/admin.jar" "$BASE/api/templates" | LIVE_TPLS="$LIVE_TPLS" python3 -c '
import json, os, sys
live = set(filter(None, os.environ["LIVE_TPLS"].split(",")))
d = json.load(sys.stdin)
print(next((t["id"] for t in d
            if t["is_enabled"] and t["persistence_scope"] != "none"
            and t["id"] not in live), ""))')
  if [ -n "$TPL_Q" ]; then
    OUT=$(api "$TMP/admin.jar" -X POST "$BASE/api/sessions" -H 'Content-Type: application/json' \
      -d "{\"template_id\":\"$TPL_Q\"}")
    grep -q "Zuhause belegt" <<<"$OUT" \
      && ok "Volles Kontingent lehnt den Start mit einer verständlichen Meldung ab" \
      || bad "Das Kontingent hielt nichts auf: $(echo "$OUT" | head -c 160)"
  else
    bad "Keine freie Vorlage für die Kontingent-Prüfung gefunden"
  fi

  rm -f "$BALLAST"
  api "$TMP/admin.jar" -X PUT "$BASE/api/admin/settings" -H 'Content-Type: application/json' \
    -d "{\"profile_quota_gb\":${BEFORE:-20}}" >/dev/null
  AFTER=$(api "$TMP/admin.jar" "$BASE/api/admin/settings" | jqp "d['profile_quota_gb']")
  expect "${BEFORE:-20}" "$AFTER" "Kontingent wieder auf den alten Wert gesetzt"

  # Und die Messung darf den Ballast nicht weiter mitschleppen. Der Puffer im
  # Agent haelt zehn Minuten — deshalb fragt die Verwaltung frisch.
  USED=$(api "$TMP/admin.jar" "$BASE/api/admin/users/$ADMIN_USER/usage" | jqp "d['bytes']")
  [ "${USED:-0}" -lt 1073741824 ] \
    && ok "Nach dem Aufräumen ist der Platz wieder frei ($((USED / 1024 / 1024)) MB)" \
    || bad "Der Ballast liegt noch im Profil ($USED)"
else
  ok "Kein Schreibzugriff auf die Profile — Kontingent-Prüfung übersprungen"
fi

# ----------------------------------------------------------- Zwischenablage
echo
echo "Zwischenablage-Voraussetzungen"
HDRS=$(curl -sI --cacert "$CA" "$BASE/")
grep -qi 'permissions-policy.*clipboard-read' <<<"$HDRS" \
  && ok "Permissions-Policy erlaubt clipboard-read" || bad "Permissions-Policy fehlt oder verbietet clipboard-read"
grep -qi 'permissions-policy.*clipboard-write' <<<"$HDRS" \
  && ok "Permissions-Policy erlaubt clipboard-write" || bad "clipboard-write fehlt"
grep -qi "frame-ancestors 'self'" <<<"$HDRS" \
  && ok "CSP erlaubt das eigene iframe" || bad "CSP frame-ancestors fehlt"
[ "$(curl -s --cacert "$CA" -o /dev/null -w '%{ssl_verify_result}' "$BASE/")" = "0" ] \
  && ok "TLS-Kette gültig (Secure Context vorhanden)" || bad "TLS-Kette ungültig"

# --------------------------------------------------------------------------
# Zweiter Faktor
#
# Am Wegwerf-Konto, nicht am echten: Der Test schaltet ihn ein, benutzt einen
# Rueckfallcode und schaltet ihn wieder ab. Ein Test, der das Konto eines
# Menschen anfasst, waere ein Test, den niemand zweimal laufen laesst.
# --------------------------------------------------------------------------
echo

otp() {  # otp <geheimnis> -> aktueller Zeitcode
  docker compose -f "$ROOT/deploy/docker-compose.yml" exec -T -e S="$1" api \
    python -c "import pyotp,os;print(pyotp.TOTP(os.environ['S']).now())" 2>/dev/null | tr -d '\r'
}

SETUP=$(curl -s --cacert "$CA" -b "$TMP/user.jar" -X POST "$BASE/api/auth/totp/setup")
SECRET=$(echo "$SETUP" | jqp "d.get('secret','')")
[ -n "$SECRET" ] && ok "Einrichtung liefert ein Geheimnis" || bad "Keine Einrichtung möglich"
grep -q "<svg" <<<"$SETUP" && ok "Einrichtungscode kommt als Bild mit" \
                               || bad "Kein Einrichtungscode im Ergebnis"

CODES=$(curl -s --cacert "$CA" -b "$TMP/user.jar" -X POST "$BASE/api/auth/totp/activate" \
  -H 'Content-Type: application/json' \
  -d "{\"secret\":\"$SECRET\",\"code\":\"$(otp "$SECRET")\"}")
N=$(echo "$CODES" | jqp "len(d.get('codes',[]))")
[ "${N:-0}" -eq 10 ] && ok "Zehn Rückfallcodes bei der Einrichtung" \
                     || bad "Rückfallcodes fehlen (bekam ${N:-0})"
RC=$(echo "$CODES" | jqp "d['codes'][0]")

# Ohne Code kommt niemand mehr herein.
OUT=$(curl -s --cacert "$CA" -X POST "$BASE/api/auth/login" -H 'Content-Type: application/json' \
  -d "{\"username\":\"$TEST_USER\",\"password\":\"$TEST_PW\"}")
grep -q "Code aus deiner App" <<<"$OUT" \
  && ok "Anmeldung ohne zweiten Faktor wird abgelehnt" \
  || bad "Anmeldung ohne zweiten Faktor ging durch"

# Mit Rückfallcode schon — und danach ist dieser Code verbraucht.
OUT=$(curl -s --cacert "$CA" -X POST "$BASE/api/auth/login" -H 'Content-Type: application/json' \
  -d "{\"username\":\"$TEST_USER\",\"password\":\"$TEST_PW\",\"totp\":\"$RC\"}")
LEFT=$(echo "$OUT" | jqp "d.get('recovery_left',-1)")
[ "$LEFT" = "9" ] && ok "Rückfallcode lässt herein und wird verbraucht (9 übrig)" \
                  || bad "Rückfallcode wirkte nicht (übrig: $LEFT)"

OUT=$(curl -s --cacert "$CA" -X POST "$BASE/api/auth/login" -H 'Content-Type: application/json' \
  -d "{\"username\":\"$TEST_USER\",\"password\":\"$TEST_PW\",\"totp\":\"$RC\"}")
grep -q "stimmt nicht" <<<"$OUT" \
  && ok "Derselbe Rückfallcode wirkt kein zweites Mal" \
  || bad "Ein verbrauchter Rückfallcode ging erneut durch"

# Fehlversuche beim zweiten Faktor muessen mitzaehlen. Ohne das ist ein
# sechsstelliger Code bei bekanntem Passwort beliebig oft ratbar.
LOCKED=""
for _ in 1 2 3 4 5 6 7 8 9; do
  OUT=$(curl -s --cacert "$CA" -X POST "$BASE/api/auth/login" -H 'Content-Type: application/json' \
    -d "{\"username\":\"$TEST_USER\",\"password\":\"$TEST_PW\",\"totp\":\"000000\"}")
  case "$OUT" in *"Fehlversuche"*) LOCKED="ja"; break ;; esac
done
[ -n "$LOCKED" ] && ok "Raten am zweiten Faktor sperrt das Konto" \
                 || bad "Der zweite Faktor liess sich unbegrenzt raten"

# Sperre wieder aufheben, sonst scheitert alles Folgende daran.
docker compose -f "$ROOT/deploy/docker-compose.yml" exec -T db \
  psql -U ota -d ota -c \
  "UPDATE users SET locked_until = NULL, failed_logins = 0 WHERE username = '$TEST_USER';" \
  >/dev/null 2>&1

# Der Zwang je Gruppe. Er wirkt beim **Start einer Session**, nicht bei der
# Anmeldung: Wer sich nicht anmelden kann, kommt nicht an „Mein Konto" und
# kann den zweiten Faktor gar nicht erst einrichten.
USERS_GID_2=$(api "$TMP/admin.jar" "$BASE/api/admin/groups" \
  | jqp "next((g['id'] for g in d if g['slug'] == 'users'), '')")
api "$TMP/admin.jar" -X PUT "$BASE/api/admin/groups/$USERS_GID_2" \
  -H 'Content-Type: application/json' \
  -d '{"name":"users","priority":100,"permissions":[],"require_totp":true}' >/dev/null

# Ein zweiter Testnutzer ohne zweiten Faktor — der erste hat gerade einen.
ZWANG="ota-pruef-zwang"
api "$TMP/admin.jar" -X POST "$BASE/api/admin/users" -H 'Content-Type: application/json' \
  -d "{\"username\":\"$ZWANG\",\"password\":\"$TEST_PW\",\"group_ids\":[\"$USERS_GID_2\"]}" \
  >/dev/null
login "$TMP/zwang.jar" "$ZWANG" "$TEST_PW"

FLAG=$(api "$TMP/zwang.jar" "$BASE/api/auth/me" | jqp "d.get('must_setup_totp')")
expect "True" "$FLAG" "Die Anmeldung gelingt und sagt, dass der Faktor fehlt"

TPL_Z=$(api "$TMP/zwang.jar" "$BASE/api/templates" | jqp "
next((t['id'] for t in d if t['is_enabled']), '')")
if [ -n "$TPL_Z" ]; then
  OUT=$(api "$TMP/zwang.jar" -X POST "$BASE/api/sessions" -H 'Content-Type: application/json' \
    -d "{\"template_id\":\"$TPL_Z\"}")
  grep -q "zweite Faktor Pflicht" <<<"$OUT" \
    && ok "Ohne zweiten Faktor startet kein Arbeitsplatz" \
    || bad "Der Zwang hielt nichts auf: $(echo "$OUT" | head -c 140)"
fi

# Zurückstellen, sonst gilt der Zwang für alle folgenden Läufe.
api "$TMP/admin.jar" -X PUT "$BASE/api/admin/groups/$USERS_GID_2" \
  -H 'Content-Type: application/json' \
  -d '{"name":"users","priority":100,"permissions":[],"require_totp":false}' >/dev/null
FLAG=$(api "$TMP/zwang.jar" "$BASE/api/auth/me" | jqp "d.get('must_setup_totp')")
expect "False" "$FLAG" "Ohne Zwang ist der Hinweis wieder weg"
ZWANG_UID=$(api "$TMP/admin.jar" "$BASE/api/admin/users" \
  | jqp "next((u['id'] for u in d if u['username'] == '$ZWANG'), '')")
[ -n "$ZWANG_UID" ] && api "$TMP/admin.jar" -X DELETE "$BASE/api/admin/users/$ZWANG_UID" >/dev/null

# Der Weg fuer den Fall, dass Telefon **und** Rueckfallcodes weg sind: Ein
# Administrator nimmt den zweiten Faktor ab. Ohne das kaeme der Mensch nie
# wieder herein.
OUT=$(api "$TMP/admin.jar" -X POST "$BASE/api/admin/users/$TEST_UID/reset-totp")
grep -q "entfernt" <<<"$OUT" \
  && ok "Ein Administrator kann den zweiten Faktor abnehmen" \
  || bad "Der zweite Faktor liess sich nicht abnehmen: $(echo "$OUT" | head -c 120)"
STATE=$(api "$TMP/user2.jar" -X POST "$BASE/api/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"$TEST_USER\",\"password\":\"$TEST_PW\"}" \
  | jqp "d.get('totp_enabled')")
expect "False" "$STATE" "Danach genügt wieder das Passwort"
# Ausdruecklich mit dem frischen Merkmal: Das Abnehmen beendet alle Sitzungen
# des Kontos, und die alte Kekstuete ist danach wertlos — was ein 401 gaebe
# statt des 403, um das es hier geht.
expect "403" "$(code "$TMP/user2.jar" -X POST "$BASE/api/admin/users/$TEST_UID/reset-totp")" \
  "Ein normaler Nutzer kann das nicht"

# Den zweiten Faktor fuer die folgenden Pruefungen wieder einrichten und
# danach frisch anmelden — mit Code, denn ab jetzt verlangt das Konto einen.
SETUP=$(api "$TMP/user2.jar" -X POST "$BASE/api/auth/totp/setup")
SECRET=$(echo "$SETUP" | jqp "d.get('secret','')")
api "$TMP/user2.jar" -X POST "$BASE/api/auth/totp/activate" -H 'Content-Type: application/json' \
  -d "{\"secret\":\"$SECRET\",\"code\":\"$(otp "$SECRET")\"}" >/dev/null
rm -f "$TMP/user.jar"
api "$TMP/user.jar" -X POST "$BASE/api/auth/login" -H 'Content-Type: application/json' \
  -d "{\"username\":\"$TEST_USER\",\"password\":\"$TEST_PW\",\"totp\":\"$(otp "$SECRET")\"}" \
  >/dev/null

# Abschalten verlangt Passwort UND Code.
OUT=$(curl -s --cacert "$CA" -b "$TMP/user.jar" -X DELETE "$BASE/api/auth/totp" \
  -H 'Content-Type: application/json' -d "{\"password\":\"$TEST_PW\",\"code\":\"000000\"}")
grep -q "stimmt nicht" <<<"$OUT" \
  && ok "Abschalten ohne gültigen Code wird verweigert" \
  || bad "Zweiter Faktor liess sich ohne Code abschalten"

curl -s --cacert "$CA" -b "$TMP/user.jar" -X DELETE "$BASE/api/auth/totp" \
  -H 'Content-Type: application/json' \
  -d "{\"password\":\"$TEST_PW\",\"code\":\"$(otp "$SECRET")\"}" >/dev/null
STATE=$(curl -s --cacert "$CA" -b "$TMP/user.jar" "$BASE/api/auth/me" | jqp "d.get('totp_enabled')")
[ "$STATE" = "False" ] && ok "Abschalten mit Passwort und Code gelingt" \
                       || bad "Zweiter Faktor blieb an"

echo
echo "─────────────────────────────────────"
printf '  bestanden: %d   fehlgeschlagen: %d\n' "$pass" "$fail"
[ "$fail" -eq 0 ] || exit 1
