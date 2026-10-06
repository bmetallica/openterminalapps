#!/usr/bin/env bash
# Prüft den Root-Arbeitsplatz (Handbuch Kapitel 25) — von innen gemessen.
#
# Was hier steht, ist der ganze Weg, den ein Entwickler geht: anlegen,
# starten, darin root sein und Docker samt Compose benutzen, beenden (= halt
# anhalten), wieder starten und alles wiederfinden, neu aufsetzen. Dazu das,
# was die Verwaltung tut: Platz messen, anhalten, starten, per Webterminal
# hinein, Protokoll exportieren, löschen.
#
# **Und die beiden Fragen, an denen der Weg hängt:**
#   * Ist root im Container auf dem Wirt wirklich unprivilegiert? (Sysbox)
#   * Gelten die Netzregeln des Routers auch für die **inneren** Container?
#     Sonst wäre Docker im Arbeitsplatz ein Weg am Router vorbei.
#
# Ohne Sysbox auf dem Wirt wird übersprungen statt rot: Dann gibt es diese
# Klasse hier nicht.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
[ -f "$ROOT/deploy/.env" ] && { set -a; . "$ROOT/deploy/.env"; set +a; }

pass=0; fail=0
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; pass=$((pass+1)); }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$1"; fail=$((fail+1)); }
info() { printf '    %s\n' "$1"; }

BASE_URL="${OTA_BASE:-https://127.0.0.1:${OTA_HTTPS_PORT:-8443}}"
CA="$ROOT/deploy/certs/ota-ca.crt"
TMP="$(mktemp -d)"
ADMIN="${OTA_TEST_ADMIN:-notfall}"
ADMIN_PW="${OTA_TEST_ADMIN_PW:?OTA_TEST_ADMIN_PW fehlt. Trag es in deploy/.env ein.}"
IMAGE="${OTA_ROOT_TAG:-ota/base-desktop-root:1}"

api()  { curl -sk -b "$TMP/jar" -c "$TMP/jar" "$@"; }
jqp()  { python3 -c "import sys,json;d=json.load(sys.stdin);print($1)" 2>/dev/null; }
drin() { docker exec -u 1000 "$CN" bash -lc "$1" 2>&1; }

TID=""; SID=""; CN=""
aufraeumen() {
  if [ -n "$SID" ]; then
    api -X DELETE "$BASE_URL/api/admin/arbeitsplaetze/$SID" >/dev/null 2>&1
  fi
  if [ -n "$TID" ]; then
    api -X DELETE "$BASE_URL/api/templates/$TID" >/dev/null 2>&1
  fi
  rm -rf "$TMP"
}
trap aufraeumen EXIT

echo "Root-Arbeitsplatz (Sysbox, Docker, Anhalten statt Löschen)"

if ! docker info 2>/dev/null | grep -q sysbox-runc; then
  echo "  (übersprungen — Sysbox ist auf diesem Wirt nicht eingerichtet, Kapitel 25)"
  exit 0
fi
if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "  (übersprungen — $IMAGE fehlt:  make root-image)"
  exit 0
fi

code=$(curl -sk -c "$TMP/jar" -o /dev/null -w '%{http_code}' -X POST "$BASE_URL/api/auth/login" \
  -H 'Content-Type: application/json' -d "{\"username\":\"$ADMIN\",\"password\":\"$ADMIN_PW\"}")
[ "$code" = "200" ] || { bad "Anmeldung als $ADMIN scheiterte ($code)"; exit 1; }

# ------------------------------------------------------------------ Anlegen
echo
echo "Vorlage und Start"
# **Ein eigenes Profil** (`persistence_scope: template`): Laeuft beim Pruefen
# schon ein anderer Arbeitsplatz desselben Kontos — `make test` laesst den der
# Browser-Reihe stehen —, lehnte OTA zu Recht ab, zwei Container auf ein
# Zuhause zu setzen.
TID=$(api -H 'Content-Type: application/json' -X POST "$BASE_URL/api/templates" -d "{
  \"friendly_name\": \"Prüfung Root-Arbeitsplatz\", \"image_ref\": \"$IMAGE\",
  \"cores\": 2, \"memory_bytes\": 4294967296, \"klasse\": \"root\",
  \"platz_grenze_gb\": 20, \"stream_engine\": \"selkies\", \"mode\": \"workspace\",
  \"persistence_scope\": \"template\"}" | jqp "d['id']")
[ -n "$TID" ] && ok "Vorlage der Klasse root angelegt" || { bad "Vorlage nicht anlegbar"; exit 1; }

# Das Recht, ohne einen zweiten Menschen anzulegen: dieselbe Funktion, die die
# API beim Start fragt, mit einem Nutzer ohne Rechte und einem mit.
RECHT=$(docker exec ota-api python -c "
from ota.models import User, Group
from ota.security import darf_root, darf_terminal
ohne = User(username='x'); ohne.groups = [Group(name='g', permissions=[])]
mit = User(username='y'); mit.groups = [Group(name='h', permissions=['arbeitsplatz.root'])]
print(darf_root(ohne), darf_root(mit), darf_terminal(mit))" 2>&1)
[ "$RECHT" = "False True False" ] \
  && ok "Ohne das Recht „Root-Arbeitsplatz nutzen“ kein Start; das Recht gibt kein Terminal" \
  || bad "Rechteprüfung unerwartet: $RECHT"

START=$(api -H 'Content-Type: application/json' -X POST "$BASE_URL/api/sessions" \
  -d "{\"template_id\":\"$TID\"}")
SID=$(jqp "d['id']" <<<"$START")
[ "$(jqp "d['status']" <<<"$START")" = "running" ] && ok "Gestartet" \
  || { bad "Start scheiterte: $(jqp "d.get('detail')" <<<"$START")"; exit 1; }
CN="ota-s-${SID:0:12}"

[ "$(docker inspect "$CN" -f '{{.HostConfig.Runtime}}')" = "sysbox-runc" ] \
  && ok "Läuft unter Sysbox" || bad "Läuft nicht unter Sysbox"
PID=$(docker inspect "$CN" -f '{{.State.Pid}}')
WIRT_UID=$(awk '$1==0 {print $2}' "/proc/$PID/uid_map" 2>/dev/null)
[ -n "$WIRT_UID" ] && [ "$WIRT_UID" != "0" ] \
  && ok "root im Container ist auf dem Wirt UID $WIRT_UID, nicht 0" \
  || bad "root im Container ist root auf dem Wirt"

# ------------------------------------------------------------------ Innen
echo
echo "Im Arbeitsplatz"
[ "$(drin 'sudo -n id -u')" = "0" ] && ok "sudo ohne Kennwort" || bad "kein sudo"
[ "$(drin 'stat -c %u:%g "$HOME"')" = "1000:1000" ] \
  && ok "Das Zuhause gehört 1000:1000 (Bind-Mount unter Sysbox)" || bad "Zuhause hat falsche Rechte"
for _ in $(seq 1 30); do drin 'docker info >/dev/null' >/dev/null && break; sleep 1; done
drin 'docker info --format "{{.ServerVersion}}"' | grep -qE '^[0-9]' \
  && ok "Docker läuft, ohne sudo" || bad "Docker antwortet nicht"
drin 'docker compose version' | grep -q 'Compose' && ok "docker compose ist da" || bad "kein compose"

drin 'mkdir -p ~/ota-pruefung && cd ~/ota-pruefung && printf "services:\n  web:\n    image: nginx:alpine\n    ports: [\"8089:80\"]\n" > compose.yaml && docker compose up -d' >/dev/null
sleep 3
[ "$(drin 'curl -s -o /dev/null -w %{http_code} http://localhost:8089/')" = "200" ] \
  && ok "docker compose up: der Dienst antwortet im Arbeitsplatz unter localhost" \
  || bad "Compose-Dienst antwortet nicht"
drin 'cd ~/ota-pruefung && docker compose down >/dev/null 2>&1; rm -rf ~/ota-pruefung'

# Die inneren Container gehen durch denselben Router wie der Arbeitsplatz.
LAN="${OTA_TURN_BIND:-${OTA_TURN_HOST:-192.168.66.224}}"
INNEN=$(drin "docker run --rm alpine:3.20 sh -c '
  wget -q -T8 -O /dev/null https://example.com && echo I:JA || echo I:NEIN
  nc -z -w3 ${LAN%.*}.1 80 && echo L:JA || echo L:NEIN
  nc -z -w3 $LAN 22 && echo W:JA || echo W:NEIN'")
grep -q "I:JA" <<<"$INNEN" && ok "Innerer Container: Internet über den Router (samt DNS)" \
  || bad "Innerer Container erreicht das Internet nicht"
grep -q "L:NEIN" <<<"$INNEN" && ok "Innerer Container: Firmennetz zu" || bad "Innerer Container erreicht das Firmennetz"
grep -q "W:NEIN" <<<"$INNEN" && ok "Innerer Container: SSH des Wirts zu" || bad "Innerer Container erreicht den Wirt"

# ------------------------------------------------------------ Anhalten
echo
echo "Anhalten statt Löschen"
drin 'sudo sh -c "echo bleibt > /opt/ota-pruefmarke"' >/dev/null
api -X DELETE "$BASE_URL/api/sessions/$SID" >/dev/null
ZUSTAND=$(api "$BASE_URL/api/sessions" | jqp "next((s['status'] for s in d if s['id']=='$SID'), '')")
[ "$ZUSTAND" = "angehalten" ] && ok "Beenden hält an (Status angehalten)" || bad "Status nach Beenden: $ZUSTAND"
EXIT=$(docker inspect "$CN" -f '{{.State.Status}} {{.State.ExitCode}}' 2>/dev/null)
[ "$EXIT" = "exited 0" ] && ok "Container sauber heruntergefahren (Exit 0)" || bad "Container nach Anhalten: ${EXIT:-weg}"

START2=$(api -H 'Content-Type: application/json' -X POST "$BASE_URL/api/sessions" -d "{\"template_id\":\"$TID\"}")
[ "$(jqp "d['id']" <<<"$START2")" = "$SID" ] && ok "Wieder gestartet — dieselbe Kennung, dieselbe Adresse" \
  || bad "Neue Kennung nach dem Fortsetzen"
[ "$(drin 'cat /opt/ota-pruefmarke')" = "bleibt" ] && ok "Was ausserhalb des Zuhauses installiert war, ist noch da" \
  || bad "Installiertes ist weg"
for _ in $(seq 1 30); do drin 'docker info >/dev/null' >/dev/null && break; sleep 1; done
drin 'docker images --format "{{.Repository}}"' | grep -q '^nginx$' \
  && ok "Docker-Images überleben das Anhalten" || bad "Docker-Images sind weg"

# ------------------------------------------------------------ Verwaltung
echo
echo "Verwaltung"
api "$BASE_URL/api/admin/arbeitsplaetze" | jqp "[a['klasse'] for a in d if a['id']=='$SID'][0]" \
  | grep -q root && ok "Steht unter Betrieb → Arbeitsplätze" || bad "Fehlt in der Liste"
GESAMT=$(api "$BASE_URL/api/admin/arbeitsplaetze/$SID/platz" | jqp "d['gesamt']")
[ "${GESAMT:-0}" -gt 0 ] 2>/dev/null && ok "Platz gemessen: $((GESAMT / 1024 / 1024)) MB" || bad "Platz nicht messbar"

api -X POST "$BASE_URL/api/admin/arbeitsplaetze/$SID/anhalten" >/dev/null
[ "$(docker inspect "$CN" -f '{{.State.Status}}')" = "exited" ] \
  && ok "Verwaltung hält an" || bad "Anhalten durch die Verwaltung wirkt nicht"
api -X POST "$BASE_URL/api/admin/arbeitsplaetze/$SID/starten" >/dev/null
[ "$(docker inspect "$CN" -f '{{.State.Status}}')" = "running" ] \
  && ok "Verwaltung startet, ohne dass der Nutzer eine Sitzung öffnet" || bad "Starten durch die Verwaltung wirkt nicht"

# Das Webterminal, wie der Browser es spricht. Der Client läuft in der API,
# weil dort die WebSocket-Bibliothek liegt; gesprochen wird mit der API selbst.
COOKIE=$(awk '$6=="'"${OTA_COOKIE_NAME:-ota_session}"'"{print $7}' "$TMP/jar")
TERM_OUT=$(docker exec -i -e C="$COOKIE" -e SID="$SID" ota-api python - <<'PY' 2>&1
import json, os, time
from websockets.sync.client import connect
url = f"ws://127.0.0.1:8000/api/admin/arbeitsplaetze/{os.environ['SID']}/terminal"
with connect(url, additional_headers={"Cookie": f"ota_session={os.environ['C']}"}) as ws:
    ws.send(json.dumps({"r": [100, 30]}))
    time.sleep(1)
    ws.send(json.dumps({"i": "echo pruef-$((6*7)) $(id -u)\r"}))
    raus, ende = b"", time.time() + 4
    while time.time() < ende:
        try:
            m = ws.recv(timeout=1)
        except TimeoutError:
            continue
        raus += m if isinstance(m, bytes) else m.encode()
print("ROOT42" if "pruef-42 0" in raus.decode(errors="replace") else "NICHT")
PY
)
grep -q ROOT42 <<<"$TERM_OUT" && ok "Webterminal: root-Shell im Arbeitsplatz" || bad "Webterminal: $TERM_OUT"
sleep 1
PROT=$(api "$BASE_URL/api/admin/arbeitsplaetze/$SID/terminal-protokoll")
grep -q 'echo pruef-$((6\*7)) $(id -u)' <<<"$PROT" \
  && ok "Die Eingabe steht im Protokoll, mit Namen" || bad "Eingabe fehlt im Protokoll"
api "$BASE_URL/api/admin/arbeitsplaetze/$SID/terminal-protokoll?format=csv" | head -1 | grep -q '^zeit_utc;' \
  && ok "Export als CSV" || bad "CSV-Export fehlt"

# Ein Terminal in einen Dienst des Stacks darf es nicht geben — auch nicht
# über den Agent direkt.
ABGEWIESEN=$(docker exec -i -e T="${OTA_AGENT_TOKEN:-}" ota-api python - <<'PY' 2>&1
import os
from websockets.sync.client import connect
from websockets.exceptions import InvalidStatus, ConnectionClosed
try:
    with connect("ws://agent:8100/containers/ota-db/terminal",
                 additional_headers={"X-Agent-Token": os.environ["T"]}) as ws:
        ws.recv(timeout=3)
    print("OFFEN")
except (InvalidStatus, ConnectionClosed) as e:
    print("ZU")
except Exception as e:
    print("ZU", type(e).__name__)
PY
)
grep -q "^ZU" <<<"$ABGEWIESEN" && ok "Kein Terminal in Dienste des Stacks (ota-db abgewiesen)" \
  || bad "Terminal in ota-db möglich!"

# ------------------------------------------------------------ Neu aufsetzen
echo
echo "Neu aufsetzen"
api -X POST "$BASE_URL/api/sessions/$SID/neu-aufsetzen" >/dev/null
docker inspect "$CN" >/dev/null 2>&1 && bad "Container nach Neu aufsetzen noch da" || ok "Container weg"
docker volume inspect "ota-platz-docker-$SID" >/dev/null 2>&1 \
  && ok "Docker-Daten bleiben (ohne „auch Docker-Daten löschen“)" || bad "Docker-Daten weg"
api -H 'Content-Type: application/json' -X POST "$BASE_URL/api/sessions" -d "{\"template_id\":\"$TID\"}" \
  | jqp "d['id']" | grep -q "$SID" && ok "Neuer Aufbau mit derselben Kennung" || bad "Andere Kennung nach Neu aufsetzen"
[ -z "$(drin 'cat /opt/ota-pruefmarke 2>/dev/null')" ] && ok "Aus dem Image neu — Installiertes ist weg" \
  || bad "Alter Stand nach Neu aufsetzen"

# ------------------------------------------------------------ Löschen
echo
echo "Löschen"
api -X DELETE "$BASE_URL/api/admin/arbeitsplaetze/$SID" >/dev/null
docker inspect "$CN" >/dev/null 2>&1 && bad "Container nach Löschen noch da" || ok "Container gelöscht"
docker volume inspect "ota-platz-docker-$SID" >/dev/null 2>&1 \
  && bad "Docker-Volume nach Löschen noch da" || ok "Docker-Daten mitgelöscht"
api "$BASE_URL/api/admin/arbeitsplaetze/$SID/terminal-protokoll" | grep -q 'pruef-' \
  && ok "Das Terminal-Protokoll überdauert den Arbeitsplatz" || bad "Protokoll mit dem Arbeitsplatz verschwunden"
SID=""

echo
echo "─────────────────────────────────────"
printf '  bestanden: %s   fehlgeschlagen: %s\n' "$pass" "$fail"
[ "$fail" = "0" ]
