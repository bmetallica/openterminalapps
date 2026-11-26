#!/usr/bin/env bash
# Prüft den Branch-Schutz als Vorgabe in OTA-Git (Handbuch Kapitel 27):
#
#   * Eingeschaltet bekommt jedes Repository mit Inhalt eine Regel auf seinen
#     Hauptzweig: kein direkter Push, Pflicht-Freigaben wie eingestellt.
#   * Ein leeres Repository nicht (sonst scheiterte der erste Push); es
#     bekommt die Regel, sobald es Inhalt hat.
#   * Ein direkter Commit auf den Zweig wird abgewiesen, auch für Admins.
#   * Wer die Regel entfernt, behält das: OTA setzt sie nicht neu.
#   * Ungültige Werte werden abgelehnt; alles steht im Protokoll.
#
# Fremde Repositories auf der Anlage bleiben unberührt: Sie gelten für die
# Dauer der Prüfung als schon erledigt. Braucht laufendes OTA-Git.
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
A=ota-pruef-schutz-a
B=ota-pruef-schutz-b

api()  { curl -sk -b "$TMP/admin.jar" -c "$TMP/admin.jar" "$@"; }
code() { curl -sk -o /dev/null -w '%{http_code}' -b "$TMP/admin.jar" "$@"; }
jqp()  { python3 -c "import sys,json;d=json.load(sys.stdin);print($1)" 2>/dev/null; }
sql()  { docker exec ota-db psql -U ota -d ota -tAc "$1"; }
# Forgejo als ota-admin, über die API im Container (dort liegt das Passwort).
fj() { docker exec -i ota-api python - "$@"; }
schutz_lauf() { docker exec ota-api python -c "
from ota.db import SessionLocal
from ota import git
with SessionLocal() as db:
    print(','.join(git.branchschutz_setzen(db)['gesetzt']))"; }
regel_von() {  # regel_von <repo> -> "push approvals" oder leer
  fj "$1" <<'PY'
import sys
from ota import git
r = git._ruf("GET", f"/repos/ota-admin/{sys.argv[1]}/branch_protections").json() or []
print(" ".join(f"{p['enable_push']} {p['required_approvals']}" for p in r if p.get("rule_name") == "main"))
PY
}
inhalt() {  # inhalt <repo> -> HTTP-Code eines Commits direkt auf main
  fj "$1" <<'PY'
import base64, sys
from ota import git
repo = f"/repos/ota-admin/{sys.argv[1]}"
alt = git._ruf("GET", f"{repo}/contents/README.md")
body = {"content": base64.b64encode(b"pruef").decode(), "message": "pruef"}
if alt.status_code == 200 and isinstance(alt.json(), dict):
    body["sha"] = alt.json()["sha"]
    print(git._ruf("PUT", f"{repo}/contents/README.md", json=body).status_code)
else:
    print(git._ruf("POST", f"{repo}/contents/README.md", json=body).status_code)
PY
}

VORHER_REGEL=""; VORHER_ERLEDIGT=""
aufraeumen() {
  fj "$A" "$B" <<'PY' >/dev/null
import sys
from ota import git
for n in sys.argv[1:]:
    git._ruf("DELETE", f"/repos/ota-admin/{n}")
PY
  if [ -n "$VORHER_REGEL" ]; then
    sql "UPDATE settings SET value = '$VORHER_REGEL' WHERE key = 'git.branchschutz'" >/dev/null
    sql "UPDATE settings SET value = '$VORHER_ERLEDIGT' WHERE key = 'git.branchschutz_erledigt'" >/dev/null
  fi
  rm -rf "$TMP"
}
trap aufraeumen EXIT

echo "Branch-Schutz als Vorgabe"
curl -sk -c "$TMP/admin.jar" -o /dev/null -X POST "$BASE/api/auth/login" -H 'Content-Type: application/json' \
  -d "{\"username\":\"$ADMIN\",\"password\":\"$ADMIN_PW\"}"
STAND=$(api "$BASE/api/admin/git")
expect "True" "$(jqp "d['an']" <<<"$STAND")" "OTA-Git läuft"
# Die Zeilen anlegen, falls es sie noch nicht gibt, und sich den Stand merken.
api -X PUT "$BASE/api/admin/git" -H 'Content-Type: application/json' -d '{"branchschutz":{"an":false}}' >/dev/null
sql "INSERT INTO settings (key, value, updated_at) VALUES ('git.branchschutz_erledigt', '{\"v\": []}', now())
     ON CONFLICT (key) DO NOTHING" >/dev/null
VORHER_REGEL=$(sql "SELECT value FROM settings WHERE key = 'git.branchschutz'")
VORHER_ERLEDIGT=$(sql "SELECT value FROM settings WHERE key = 'git.branchschutz_erledigt'")

# Alle vorhandenen Repositories gelten als erledigt: Die Prüfung fasst nur ihre eigenen an.
FREMD=$(fj <<'PY'
from ota import git
ids, seite = [], 1
while True:
    d = git._ruf("GET", "/repos/search", params={"limit": 50, "page": seite}).json().get("data") or []
    ids += [r["id"] for r in d]
    if len(d) < 50:
        break
    seite += 1
print(ids)
PY
)
sql "UPDATE settings SET value = jsonb_build_object('v', '$FREMD'::jsonb) WHERE key = 'git.branchschutz_erledigt'" >/dev/null
# Die API hält Einstellungen fünf Sekunden im Speicher; erst danach sieht sie die Liste.
sleep 6

fj "$A" "$B" <<'PY' >/dev/null
import sys
from ota import git
for n in sys.argv[1:]:
    git._ruf("DELETE", f"/repos/ota-admin/{n}")
    git._ruf("POST", "/user/repos", json={"name": n})
PY
expect "201" "$(inhalt "$A")" "Repository A hat Inhalt, B ist leer"

expect "400" "$(code -X PUT "$BASE/api/admin/git" -H 'Content-Type: application/json' \
  -d '{"branchschutz":{"freigaben":6}}')" "Mehr als 5 Freigaben werden abgelehnt"

ERG=$(api -X PUT "$BASE/api/admin/git" -H 'Content-Type: application/json' \
  -d '{"branchschutz":{"an":true,"freigaben":2}}')
expect "True 2" "$(jqp "d['branchschutz']['an'], d['branchschutz']['freigaben']" <<<"$ERG" | tr -d '(),')" \
  "Eingeschaltet, zwei Freigaben"
expect "['ota-admin/$A:main']" "$(jqp "d['ergebnis']['gesetzt']" <<<"$ERG")" \
  "Beim Einschalten sofort gesetzt — nur für A"
expect "False 2" "$(regel_von "$A")" "A: kein direkter Push, zwei Pflicht-Freigaben"
expect "" "$(regel_von "$B")" "B (leer) hat keine Regel"
expect "403" "$(inhalt "$A")" "Ein direkter Commit auf main wird abgewiesen, auch für den Admin"
expect "1" "$(sql "SELECT count(*) FROM audit_log WHERE action = 'git.branchschutz_gesetzt'
                   AND ts > now() - interval '1 minute' AND detail->>'anzahl' = '1'")" \
  "Im Protokoll, mit Anzahl"

echo
echo "Einmal je Repository"
fj "$A" <<'PY' >/dev/null
import sys
from ota import git
git._ruf("DELETE", f"/repos/ota-admin/{sys.argv[1]}/branch_protections/main")
PY
expect "" "$(regel_von "$A")" "Regel von A entfernt (wie es ein Eigentümer täte)"
expect "201" "$(inhalt "$B")" "B bekommt Inhalt"
expect "ota-admin/$B:main" "$(schutz_lauf)" "Der Takt setzt sie für B, nicht wieder für A"
expect "" "$(regel_von "$A")" "A bleibt ohne Regel"
expect "False 2" "$(regel_von "$B")" "B ist geschützt"
expect "" "$(schutz_lauf)" "Ein weiterer Lauf ändert nichts"

echo
printf '  bestanden: %d   fehlgeschlagen: %d\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
