#!/usr/bin/env bash
# Prüft opencode (Handbuch Kapitel 38) und die Erweiterungen (Kapitel 39) mit
# dem Gedächtnis (eigenes Repo plugin_ota-opencode), von Anfang bis Ende:
#
#   * Einstellungen: an/aus, Prompt-Zusatz global, Zusatzkonfiguration, die
#     Vorschau; Unsinn wird abgewiesen.
#   * Erweiterung: koppeln (falscher Schlüssel abgewiesen), konfigurieren,
#     Embeddings testen, einschalten; Traefik bekommt genau die freigegebenen
#     Wege.
#   * Im Root-Arbeitsplatz: verwaltete Konfiguration mit Marke, Prompt-Zusatz
#     samt Schnipsel der Erweiterung, Token, /etc/hosts, Paket in der
#     festgelegten Fassung. Aus dem Arbeitsplatz erreicht man /mcp, nicht
#     aber den Vertrag /ota/v1.
#   * opencode selbst (mit einem Fake-Modell im Arbeitsplatz): Das Plugin
#     ota-sitzung setzt die echte Sitzung ein, auch aus einem Unteragenten;
#     eine zweite Sitzung sieht nichts davon.
#   * Ansicht in OTA: nur angemeldet, nur der eigene Arbeitsplatz, gefälschte
#     Kopfzeilen aus dem Browser wirken nicht.
#   * Übernahme: ein selbst installiertes opencode wird beim Fortsetzen auf
#     OTAs Fassung umgelenkt, das Original bleibt; ein eigenes Standardmodell
#     in ~/.config/opencode bleibt.
#   * Anhalten widerruft das Token; Fortsetzen gibt ein neues, und das
#     Gedächtnis der Sitzung ist wieder da.
#
# Die Erweiterung: OTA_TEST_GEDAECHTNIS (Vorgabe /opt/plugin_ota-opencode);
# fehlt sie, wird nur opencode geprüft. Der KI-Server für die Embeddings:
# OTA_TEST_KI_URL (Vorgabe http://192.168.66.225:8080), Modell
# OTA_TEST_EMBED_MODELL (Vorgabe nomic-embed-text). Stellt am Ende her, was
# vorher eingestellt war. OTA_TEST_BEHALTEN=1 lässt den Arbeitsplatz stehen.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
[ -f "$ROOT/deploy/.env" ] && { set -a; . "$ROOT/deploy/.env"; set +a; }

pass=0; fail=0
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; pass=$((pass+1)); }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$1"; fail=$((fail+1)); }
info() { printf '    %s\n' "$1"; }
expect() { if [ "$2" = "$1" ]; then ok "$3 ($2)"; else bad "$3 — erwartet $1, bekommen $2"; fi; }

B="${OTA_BASE:-https://127.0.0.1:${OTA_HTTPS_PORT:-8443}}"
TMP="$(mktemp -d)"
ADMIN="${OTA_TEST_ADMIN:-notfall}"
ADMIN_PW="${OTA_TEST_ADMIN_PW:?OTA_TEST_ADMIN_PW fehlt}"
KI="${OTA_TEST_KI_URL:-http://192.168.66.225:8080}"
EMBED="${OTA_TEST_EMBED_MODELL:-nomic-embed-text}"
PLUGIN="${OTA_TEST_GEDAECHTNIS:-/opt/plugin_ota-opencode}"
IMAGE="${OTA_ROOT_TAG:-ota/base-desktop-root:1}"

api()  { curl -sk -b "$TMP/a.jar" -c "$TMP/a.jar" -H 'Content-Type: application/json' "$@"; }
code() { curl -sk -o /dev/null -w '%{http_code}' -b "$TMP/a.jar" -H 'Content-Type: application/json' "$@"; }
jqp()  { python3 -c "import sys,json;d=json.load(sys.stdin);print($1)" 2>/dev/null; }
im()   { docker exec "$CN" sh -c "$1" 2>&1; }
gdb()  { docker exec ota-gedaechtnis-db psql -U gedaechtnis -d gedaechtnis -At -c "SET ota.system = 'an'; $1" 2>/dev/null | tail -n +2; }

VORHER_OC=""; VORHER_KI=""; GEKOPPELT_VORHER=""; TID=""; SID=""; CN=""
aufraeumen() {
  echo
  echo "Aufräumen"
  if [ -n "${OTA_TEST_BEHALTEN:-}" ]; then
    info "Arbeitsplatz $CN und Vorlage bleiben (OTA_TEST_BEHALTEN)"; SID=""; TID=""
  fi
  [ -n "$SID" ] && api -X DELETE "$B/api/admin/arbeitsplaetze/$SID" >/dev/null 2>&1
  [ -n "$TID" ] && api -X DELETE "$B/api/templates/$TID" >/dev/null 2>&1
  if [ -n "$VORHER_OC" ]; then
    jqp "json.dumps({k: d[k] for k in ('an','gruppen','standard','klein','prompt','prompt_gruppen','zusatz')})" \
      <<<"$VORHER_OC" > "$TMP/oc.json"
    expect "200" "$(code -X PUT "$B/api/admin/opencode" -d @"$TMP/oc.json")" "opencode wie vorher"
  fi
  if [ -n "$VORHER_KI" ]; then
    jqp "json.dumps({k: v for k, v in d.items() if k not in ('api_key_gesetzt', 'fassungen')})" \
      <<<"$VORHER_KI" > "$TMP/ki.json"
    expect "200" "$(code -X PUT "$B/api/admin/ide-ai" -d @"$TMP/ki.json")" "IDE-AI wie vorher"
  fi
  if [ -d "$PLUGIN" ] && [ -z "$GEKOPPELT_VORHER" ]; then
    code -X DELETE "$B/api/admin/erweiterungen/gedaechtnis" >/dev/null
    info "Erweiterung entkoppelt (war vorher nicht gekoppelt); ihr Compose läuft weiter"
  fi
  rm -rf "$TMP"
  echo
  printf '  bestanden: %d   fehlgeschlagen: %d\n' "$pass" "$fail"
  [ "$fail" -eq 0 ] || exit 1
}
trap aufraeumen EXIT

echo "opencode und Erweiterungen gegen $B"
expect "200" "$(curl -sk -c "$TMP/a.jar" -o /dev/null -w '%{http_code}' -X POST "$B/api/auth/login" \
  -H 'Content-Type: application/json' -d "{\"username\":\"$ADMIN\",\"password\":\"$ADMIN_PW\"}")" "Anmeldung als $ADMIN"
VORHER_OC=$(api "$B/api/admin/opencode")
VORHER_KI=$(api "$B/api/admin/ide-ai")
[ -n "$(jqp "d['an']" <<<"$VORHER_OC")" ] || { bad "Kein Zugriff auf /api/admin/opencode"; VORHER_OC=""; exit 1; }

# ------------------------------------------------------------------ Einstellungen
echo
echo "Einstellungen"
if [ -z "$(jqp "d['url']" <<<"$VORHER_KI")" ] || [ "$(jqp "len(d['modelle'])" <<<"$VORHER_KI")" = "0" ]; then
  api -X PUT "$B/api/admin/ide-ai" -d "{\"url\":\"$KI\",\"modelle\":[{\"id\":\"Hauptmodell\",\"kontext\":65536,\"max_tokens\":12288}]}" >/dev/null
  info "IDE-AI: KI-Server $KI eingetragen (für den Test)"
fi
expect "400" "$(code -X PUT "$B/api/admin/opencode" -d '{"zusatz":"{kein json"}')" "Zusatzkonfiguration ohne gültiges JSON abgewiesen"
expect "400" "$(code -X PUT "$B/api/admin/opencode" -d '{"zusatz":"{\"mcp\":{}}"}')" "mcp in der Zusatzkonfiguration abgewiesen"
R=$(api -X PUT "$B/api/admin/opencode" -d '{"an":true,"prompt":"PRUEF-GLOBAL für {nutzer}","zusatz":"{\"agent\":{\"title\":{\"model\":\"ota/Hauptmodell\"}}}"}')
expect "True" "$(jqp "str(d['an'])" <<<"$R")" "opencode eingeschaltet"
FASSUNG=$(jqp "d['fassung']" <<<"$R")
[ -n "$FASSUNG" ] && ok "ota-opencode in der Paketquelle ($FASSUNG)" || bad "ota-opencode fehlt in der Paketquelle"
expect "400" "$(code -X PUT "$B/api/admin/opencode" -d '{"mcp":[{"name":"X!","typ":"entfernt","url":"http://a"}]}')" "MCP-Server mit ungültigem Namen abgewiesen"
expect "400" "$(code -X PUT "$B/api/admin/opencode" -d '{"mcp":[{"name":"ftp","typ":"entfernt","url":"ftp://a"}]}')" "MCP-Server ohne http(s) abgewiesen"
R=$(api -X PUT "$B/api/admin/opencode" -d '{"mcp":[
  {"name":"pruefmcp","typ":"entfernt","an":true,"gruppen":[],"url":"http://127.0.0.1:9200/mcp","kopf":"X-Pruef-Key","praefix":"Token ","freigeben":false,"schluessel":"pruef-mcp-schluessel-123"},
  {"name":"nurgruppe","typ":"lokal","an":true,"gruppen":["00000000-0000-4000-8000-0000000000aa"],"befehl":["echo","x"],"variable":"PRUEF_TOKEN","schluessel":"lokal-geheim"}]}')
expect "True" "$(jqp "str(d['mcp'][0]['schluessel_gesetzt'] and 'pruef-mcp-schluessel' not in json.dumps(d))" <<<"$R")" \
  "MCP-Server gespeichert, der Schlüssel kommt nicht zurück"
R=$(api -X PUT "$B/api/admin/opencode" -d "$(jqp "json.dumps({'mcp': [{k: v for k, v in m.items() if k != 'schluessel_gesetzt'} for m in d['mcp']]})" <<<"$R")")
expect "True" "$(jqp "str(d['mcp'][0]['schluessel_gesetzt'])" <<<"$R")" "Speichern ohne Schlüssel behält ihn"
expect "True False" "$(docker exec ota-api python -c "
from ota.db import SessionLocal
from ota import opencode
from ota.models import User, Group
with SessionLocal() as db:
    e = opencode.einstellungen(db)
    ohne = User(username='x'); ohne.groups = []
    mit = User(username='y'); g = Group(name='g'); g.id = __import__('uuid').UUID('00000000-0000-4000-8000-0000000000aa'); mit.groups = [g]
    print('nurgruppe' in [m['name'] for m in opencode.mcp_fuer(e, mit)], 'nurgruppe' in [m['name'] for m in opencode.mcp_fuer(e, ohne)])")" \
  "Gruppensteuerung je MCP-Server (Mitglied ja, Nichtmitglied nein)"
V=$(api -X POST "$B/api/admin/opencode/vorschau" -d '{}')
grep -q "PRUEF-GLOBAL für $ADMIN" <<<"$(jqp "d['anweisungen']" <<<"$V")" && ok "Vorschau: Prompt-Zusatz mit Platzhalter" || bad "Vorschau ohne Prompt-Zusatz"
jqp "d['config']" <<<"$V" | grep -q '"title"' && ok "Vorschau: Zusatzkonfiguration eingemischt" || bad "Zusatzkonfiguration fehlt"
expect "True" "$(api "$B/api/firewall/zustand" >/dev/null; docker exec ota-api python -c "
from ota.db import SessionLocal
from ota import ide_ai
with SessionLocal() as db: print(ide_ai.freigabe(db) is not None)")" "Firewall gibt den KI-Server frei, solange opencode an ist"

# ------------------------------------------------------------------ Erweiterung
ERW=""
if [ -d "$PLUGIN" ]; then
  echo
  echo "Erweiterung: Gedächtnis ($PLUGIN)"
  GEKOPPELT_VORHER=$(api "$B/api/admin/erweiterungen" | jqp "'ja' if any(e['slug']=='gedaechtnis' for e in d) else ''")
  ( cd "$PLUGIN" && ./setup.sh >/dev/null && docker compose up -d --build >/dev/null 2>&1 )
  for _ in $(seq 1 40); do
    [ "$(docker inspect ota-gedaechtnis -f '{{.State.Health.Status}}' 2>/dev/null)" = healthy ] && break; sleep 3
  done
  expect "healthy" "$(docker inspect ota-gedaechtnis -f '{{.State.Health.Status}}' 2>/dev/null)" "Dienst läuft (eigenes Compose)"
  expect "" "$(docker port ota-gedaechtnis 2>/dev/null)" "… ohne Port auf dem Host"
  SCHLUESSEL=$(sed -n 's/^GEDAECHTNIS_KOPPLUNGSSCHLUESSEL=//p' "$PLUGIN/.env")
  expect "400" "$(code -X POST "$B/api/admin/erweiterungen" -d '{"adresse":"http://ota-gedaechtnis:8080","schluessel":"falsch"}')" \
    "Koppeln mit falschem Schlüssel abgewiesen"
  R=$(api -X POST "$B/api/admin/erweiterungen" -d "{\"adresse\":\"http://ota-gedaechtnis:8080\",\"schluessel\":\"$SCHLUESSEL\"}")
  expect "gedaechtnis" "$(jqp "d['slug']" <<<"$R")" "gekoppelt"
  R=$(api -X PUT "$B/api/admin/erweiterungen/gedaechtnis/konfiguration" -d "{\"einbettung_url\":\"$KI/v1\",\
\"einbettung_modell\":\"$EMBED\",\"praefix_eintrag\":\"search_document: \",\"praefix_suche\":\"search_query: \",\"speichern_fragen\":false}")
  expect "$EMBED" "$(jqp "d['einbettung_modell']" <<<"$R")" "konfiguriert"
  R=$(api -X POST "$B/api/admin/erweiterungen/gedaechtnis/testen")
  expect "True" "$(jqp "str(d.get('ok'))" <<<"$R")" "Embeddings vom KI-Server ($(jqp "d.get('dimension')" <<<"$R") Dimensionen, $(jqp "d.get('ms')" <<<"$R") ms)"
  R=$(api -X PUT "$B/api/admin/erweiterungen/gedaechtnis" -d '{"an":true,"gruppen":[]}')
  expect "True" "$(jqp "str(d['an'])" <<<"$R")" "eingeschaltet"
  ROUTEN="$ROOT/deploy/traefik/dynamic/erweiterungen.yml"
  sleep 2
  grep -q 'PathPrefix(`/gedaechtnis/mcp`)' "$ROUTEN" 2>/dev/null && ok "Traefik: Weg aus den Arbeitsplätzen nur zu /mcp" || bad "Traefik-Route fehlt"
  grep -q 'PathPrefix(`/x/gedaechtnis/ansicht/`)' "$ROUTEN" 2>/dev/null && ok "Traefik: Ansicht hinter forwardAuth" || bad "Ansichts-Route fehlt"
  # Reste früherer Läufe (dasselbe Konto, dasselbe Zuhause) weg.
  gdb "DELETE FROM eintrag WHERE inhalt LIKE 'Pruef-Eintrag%' OR inhalt = 'Von Hand aus dem Arbeitsplatz'" >/dev/null
  ERW=1
fi

# ------------------------------------------------------------------ normaler Arbeitsplatz mit Editor
# Dort installiert IDE-AI im Hintergrund gleichzeitig sein Paket. Bis zum
# 2026-11-02 scheiterte opencode dann an der Sperre von dpkg.
echo
echo "Im normalen Arbeitsplatz mit Editor (IDE-AI installiert gleichzeitig)"
ED_TID=""
for zeile in $(docker exec ota-db psql -U ota -d ota -At -c "select id || '|' || image_ref from templates where is_enabled and klasse = 'standard'"); do
  IMG="${zeile#*|}"
  docker run --rm --entrypoint sh "$IMG" -c 'command -v dpkg >/dev/null && ls -d /usr/share/codium /usr/share/code /opt/*/product-info.json 2>/dev/null | head -1' 2>/dev/null | grep -q . \
    && { ED_TID="${zeile%%|*}"; break; }
done
if [ -z "$ED_TID" ] || [ "$(jqp "d['an']" <<<"$VORHER_KI")" != "True" ]; then
  info "(übersprungen — keine Vorlage mit Editor und dpkg, oder IDE-AI aus)"
else
  ED_SID=$(api -X POST "$B/api/sessions" -d "{\"template_id\":\"$ED_TID\"}" | jqp "d['id']")
  ED_CN="ota-s-${ED_SID:0:12}"
  for _ in $(seq 1 80); do
    docker exec "$ED_CN" dpkg-query -W -f='${Version}' ota-opencode 2>/dev/null | grep -q "$FASSUNG" && break; sleep 3
  done
  expect "$FASSUNG" "$(docker exec "$ED_CN" dpkg-query -W -f='${Version}' ota-opencode 2>/dev/null)" "opencode installiert, obwohl IDE-AI gleichzeitig installiert"
  docker logs ota-agent --since 5m 2>&1 | grep "$ED_CN" | grep -q "Sperre\|lock" \
    && info "(dpkg war belegt — der Agent hat gewartet)"
  api -X DELETE "$B/api/sessions/$ED_SID" >/dev/null
fi

# ------------------------------------------------------------------ Arbeitsplatz
echo
echo "Im Root-Arbeitsplatz"
if ! docker info 2>/dev/null | grep -q sysbox-runc || ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  info "(übersprungen — Sysbox oder $IMAGE fehlt)"; exit 0
fi
TID=$(api -X POST "$B/api/templates" -d "{\"friendly_name\": \"Prüfung opencode\", \"image_ref\": \"$IMAGE\",
  \"cores\": 2, \"memory_bytes\": 4294967296, \"klasse\": \"root\", \"platz_grenze_gb\": 20,
  \"stream_engine\": \"selkies\", \"mode\": \"workspace\", \"persistence_scope\": \"template\"}" | jqp "d['id']")
[ -n "$TID" ] && ok "Vorlage angelegt" || { bad "Vorlage nicht anlegbar"; exit 1; }
SID=$(api -X POST "$B/api/sessions" -d "{\"template_id\":\"$TID\"}" | jqp "d['id']")
CN="ota-s-${SID:0:12}"
for _ in $(seq 1 60); do [ "$(docker inspect "$CN" -f '{{.State.Running}}' 2>/dev/null)" = true ] && break; sleep 3; done
[ "$(docker inspect "$CN" -f '{{.State.Running}}' 2>/dev/null)" = true ] && ok "läuft ($CN)" || { bad "kam nicht hoch"; exit 1; }
H=$(docker exec "$CN" sh -c 'getent passwd 1000 | cut -d: -f6'); H="${H:-/root}"

expect "// Verwaltet von OTA (opencode). Änderungen hier überschreibt OTA beim nächsten Start." \
  "$(im 'head -1 /etc/opencode/opencode.jsonc')" "verwaltete Konfiguration mit Marke"
grep -q "PRUEF-GLOBAL für $ADMIN" <<<"$(im 'cat /etc/opencode/ota-anweisungen.md')" && ok "Prompt-Zusatz im Arbeitsplatz" || bad "Prompt-Zusatz fehlt"
fassung_drin() { docker exec "$CN" dpkg-query -W -f='${Version}' ota-opencode 2>/dev/null; }
for _ in $(seq 1 60); do fassung_drin | grep -q "$FASSUNG" && break; sleep 3; done
expect "$FASSUNG" "$(fassung_drin)" "Paket ota-opencode installiert"
im '/usr/bin/opencode --version' | grep -q "${FASSUNG%%-ota*}" && ok "opencode $(im '/usr/bin/opencode --version')" || bad "opencode läuft nicht"
im 'test -f /usr/share/ota-opencode/plugins/ota-sitzung/index.js' && ok "Plugin ota-sitzung mitgeliefert" || bad "Plugin fehlt"
expect "pruef-mcp-schluessel-123" "$(im 'cat /etc/opencode/ota-mcp/pruefmcp')" "Schlüssel des MCP-Servers als eigene Datei"
grep -q '"X-Pruef-Key": "Token {file:/etc/opencode/ota-mcp/pruefmcp}"' <<<"$(im 'cat /etc/opencode/opencode.jsonc')" \
  && ok "MCP-Server in der Konfiguration, Schlüssel nur als Verweis" || bad "MCP-Server fehlt in der Konfiguration"
im 'grep -q pruef-mcp-schluessel /etc/opencode/opencode.jsonc' && bad "Schlüssel steht im Klartext in der Konfiguration" || ok "… nicht im Klartext"
docker exec -i "$CN" sh -c 'cat > /tmp/kopf.py' <<'PY'
from http.server import BaseHTTPRequestHandler, HTTPServer
class K(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _antwort(self):
        open("/tmp/mcp-kopf.log", "a").write(str(self.headers.get("X-Pruef-Key")) + "\n")
        self.send_response(404); self.end_headers()
    do_GET = do_POST = _antwort
HTTPServer(("127.0.0.1", 9200), K).serve_forever()
PY
im 'nohup python3 /tmp/kopf.py >/dev/null 2>&1 &'
sleep 1
# --standalone: ein eigener Server nur für diesen Aufruf. Sonst bliebe
# opencodes Hintergrunddienst mit dieser Umgebung stehen, und die Aufrufe
# mit dem Fake-Modell weiter unten hängten sich an ihn.
im 'cd /tmp; timeout 90 opencode run --standalone --model ota/x hallo >/dev/null 2>&1 || true'
grep -q "Token pruef-mcp-schluessel-123" <<<"$(im 'cat /tmp/mcp-kopf.log 2>/dev/null')" \
  && ok "opencode schickt den Schlüssel an den MCP-Server" || bad "Schlüssel kam nicht an: $(im 'cat /tmp/mcp-kopf.log 2>/dev/null' | head -2)"

if [ -n "$ERW" ]; then
  grep -q "## Erweiterung: Gedächtnis für opencode" <<<"$(im 'cat /etc/opencode/ota-anweisungen.md')" \
    && ok "Schnipsel der Erweiterung im Prompt-Zusatz" || bad "Schnipsel der Erweiterung fehlt"
  TOKEN=$(im 'cat /etc/ota/erweiterungen/gedaechtnis/token')
  [ ${#TOKEN} -ge 32 ] && ok "Token im Arbeitsplatz (/etc/ota/erweiterungen)" || bad "Token fehlt"
  im 'grep -q " ota-erweiterungen # ota-erweiterungen$" /etc/hosts' && ok "/etc/hosts: ota-erweiterungen → Traefik" || bad "/etc/hosts ohne Eintrag"
  grep -q '"gedaechtnis_memory_save": "ask"' <<<"$(im 'cat /etc/opencode/opencode.jsonc')" \
    && bad "Rückfrage beim Speichern trotz speichern_fragen=false" || ok "Keine Rückfrage (so eingestellt)"
  # Aus dem Arbeitsplatz, mit python3 (curl gibt es im Root-Image nicht).
  docker exec -i "$CN" sh -c 'cat > /tmp/holen.py' <<'PY'
import json, sys, urllib.error, urllib.request
url, daten = sys.argv[1], (sys.argv[2].encode() if len(sys.argv) > 2 else None)
kopf = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
if daten:
    kopf["Authorization"] = "Bearer " + open("/etc/ota/erweiterungen/gedaechtnis/token").read().strip()
try:
    r = urllib.request.urlopen(urllib.request.Request(url, data=daten, headers=kopf), timeout=10)
    print(r.status if not daten else r.read().decode())
except urllib.error.HTTPError as e:
    print(e.code)
except Exception as e:
    print("FEHLER", e)
PY
  MCP() { docker exec "$CN" python3 /tmp/holen.py http://ota-erweiterungen:8091/gedaechtnis/mcp "$1" 2>&1; }
  R=$(MCP '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"memory_save","arguments":{"content":"Von Hand aus dem Arbeitsplatz","ota_sitzung":"ses_handtest"}}}')
  grep -qE "Saved as|Updated similar" <<<"$R" && ok "MCP aus dem Arbeitsplatz erreichbar, Token gilt" || bad "MCP nicht erreichbar: ${R:0:200}"
  expect "404" "$(docker exec "$CN" python3 /tmp/holen.py http://ota-erweiterungen:8091/gedaechtnis/ota/v1/manifest)" \
    "Der Vertrag /ota/v1 ist aus dem Arbeitsplatz nicht erreichbar"
  expect "404" "$(docker exec "$CN" python3 /tmp/holen.py http://ota-erweiterungen:8091/gedaechtnis/ansicht/konto)" \
    "… die Ansicht auch nicht"

  echo
  echo "opencode mit Fake-Modell im Arbeitsplatz"
  # Über exec, nicht docker cp: Bei Sysbox lehnt Docker das Archiv ab.
  docker exec -i "$CN" sh -c 'cat > /tmp/pruefmodell.py' < "$ROOT/scripts/opencode-pruefmodell.py"
  im 'nohup python3 /tmp/pruefmodell.py >/tmp/pruefmodell.log 2>&1 &'
  sleep 2
  OC='export OPENCODE_CONFIG_CONTENT='"'"'{"provider":{"pruef":{"npm":"@ai-sdk/openai-compatible","options":{"baseURL":"http://127.0.0.1:9100/v1","apiKey":"x"},"models":{"fake":{"name":"Fake","tool_call":true}}}}}'"'"'; cd /tmp'
  im "$OC; timeout 120 opencode run -m pruef/fake --title PruefSitzung hallo" >/dev/null
  sleep 3
  im "$OC; timeout 120 opencode run -c -m pruef/fake --auto 'Bitte SPEICHERN'" > "$TMP/run.txt"
  im "$OC; timeout 120 opencode run -c -m pruef/fake --auto 'Bitte UNTER'" >> "$TMP/run.txt"
  im "$OC; timeout 120 opencode run -m pruef/fake --title Zweite --auto 'Bitte SPEICHERN'" >> "$TMP/run.txt"
  SESS=$(gdb "SELECT sitzung || '|' || (SELECT titel FROM sitzung s WHERE s.kennung = e.sitzung AND s.mensch = e.mensch) FROM eintrag e WHERE inhalt = 'Pruef-Eintrag aus opencode' ORDER BY angelegt")
  info "$(tr '\n' ' ' <<<"$SESS")"
  ERSTE=$(head -1 <<<"$SESS" | cut -d'|' -f1)
  grep -q '^ses_' <<<"$ERSTE" && ok "Das Plugin setzt die echte Sitzung ein ($ERSTE), nicht das Gefälschte" || bad "Sitzung nicht gesetzt: $SESS"
  expect "0" "$(gdb "SELECT count(*) FROM eintrag WHERE sitzung = 'GEFAELSCHT'")" "Die vom Modell gefälschte Kennung kommt nicht durch"
  expect "$ERSTE" "$(gdb "SELECT sitzung FROM eintrag WHERE inhalt = 'Pruef-Eintrag aus dem Unteragent'")" \
    "Ein Unteragent schreibt ins Gedächtnis der Wurzelsitzung"
  expect "2" "$(gdb "SELECT count(DISTINCT sitzung) FROM eintrag WHERE inhalt = 'Pruef-Eintrag aus opencode'")" "Eine neue Sitzung hat ihr eigenes Gedächtnis"
  im 'grep -c PRUEF-GLOBAL /tmp/pruefmodell.log' | grep -qv '^0$' \
    && ok "Der Prompt-Zusatz kommt beim Modell an" || bad "Prompt-Zusatz kam beim Modell nicht an"
  im 'grep -c "ota_sitzung" /tmp/pruefmodell.log || true' | grep -q '^0$' \
    && ok "Die Felder ota_* sieht das Modell nicht" || bad "Das Modell sieht die Felder ota_*"

  echo
  echo "Ansicht in OTA"
  expect "401" "$(curl -sk -o /dev/null -w '%{http_code}' "$B/x/gedaechtnis/ansicht/konto")" "Ohne Anmeldung: kein Zugang"
  SEITE=$(api "$B/x/gedaechtnis/ansicht/konto?s=$ERSTE")
  grep -q "Pruef-Eintrag aus opencode" <<<"$SEITE" && grep -q "PruefSitzung" <<<"$SEITE" \
    && ok "Mein Konto → Gedächtnis zeigt die Sitzung" || bad "Ansicht leer: ${SEITE:0:200}"
  expect "200" "$(code "$B/x/gedaechtnis/ansicht/arbeitsplatz/$SID")" "… und je Arbeitsplatz"
  expect "403" "$(code "$B/x/gedaechtnis/ansicht/arbeitsplatz/00000000-0000-4000-8000-000000000000")" "Fremder Arbeitsplatz: abgewiesen"
  FREMD=$(api -H 'X-OTA-Nutzer: 00000000-0000-4000-8000-000000000001' -H 'X-OTA-Signatur: falsch' "$B/x/gedaechtnis/ansicht/konto?s=$ERSTE")
  grep -q "Pruef-Eintrag aus opencode" <<<"$FREMD" && ok "Gefälschte Kopfzeilen aus dem Browser wirken nicht" || bad "Kopfzeilen aus dem Browser kamen durch"
  expect "1" "$(api "$B/api/erweiterungen/ansichten" | jqp "len([a for a in d if a['ort']=='konto'])")" "Ansichten für die Oberfläche"
fi

# ------------------------------------------------------------------ Übernahme, Anhalten, Fortsetzen
echo
echo "Übernahme beim Fortsetzen"
im "mkdir -p $H/.opencode/bin $H/.config/opencode && rm -f $H/.opencode/bin/opencode && printf '#!/bin/sh\necho eigene-fassung\n' > $H/.opencode/bin/opencode && chmod 755 $H/.opencode/bin/opencode"
im "printf '{\n  // eigenes Modell\n  \"model\": \"llama.cpp/Hauptmodell\",\n}\n' > $H/.config/opencode/opencode.jsonc"
api -X POST "$B/api/admin/arbeitsplaetze/$SID/anhalten" >/dev/null
if [ -n "$ERW" ]; then
  expect "0" "$(gdb "SELECT count(*) FROM token WHERE arbeitsplatz = '$SID' AND widerrufen IS NULL")" "Anhalten widerruft das Token"
fi
api -X POST "$B/api/admin/arbeitsplaetze/$SID/starten" >/dev/null
for _ in $(seq 1 40); do im "test -f $H/.opencode/bin/opencode.vor-ota" >/dev/null && break; sleep 3; done
expect "opencode v${FASSUNG%%-ota*}" "$(im "$H/.opencode/bin/opencode --version")" "Eigenes opencode auf OTAs Fassung umgelenkt"
expect "eigene-fassung" "$(im "$H/.opencode/bin/opencode.vor-ota")" "… das Original liegt daneben"
im 'grep -q "^  \"model\"" /etc/opencode/opencode.jsonc' && bad "OTA überschreibt das eigene Standardmodell" \
  || ok "Eigenes Standardmodell bleibt (kein model in der verwalteten Konfiguration)"
if [ -n "$ERW" ]; then
  T2=$(im 'cat /etc/ota/erweiterungen/gedaechtnis/token')
  [ -n "$T2" ] && [ "$T2" != "$TOKEN" ] && ok "Fortsetzen gibt ein neues Token" || bad "Kein neues Token"
  R=$(MCP '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"memory_recall","arguments":{"ota_sitzung":"'"$ERSTE"'"}}}')
  grep -q "Pruef-Eintrag aus opencode" <<<"$R" && ok "Das Gedächtnis der Sitzung ist nach dem Fortsetzen wieder da" || bad "Gedächtnis weg: ${R:0:200}"
fi
