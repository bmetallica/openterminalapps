#!/usr/bin/env bash
# Prüft IDE-AI (Handbuch Kapitel 28, 2026-10-22).
#
#   * Einstellungen: Modelle vom KI-Server abrufen, speichern, prüfen, was
#     nicht taugt (Adresse, Antwortlänge ≥ Kontextfenster), ein Modell testen.
#     Der API-Schlüssel verlässt den Server nie.
#   * Paketquelle: beide Pakete liegen dort, der Agent bekommt die Datei.
#   * Im Arbeitsplatz (jede Vorlage mit VS Code, VSCodium oder JetBrains-IDE):
#     config.yaml mit OTAs Marke, Kontextfenster und Antwortlänge wie
#     eingestellt, Telemetrie aus, Pakete installiert und verknüpft — VS Code
#     und VSCodium im Editor, JetBrains im Zuhause. Die Firewall lässt den
#     KI-Server durch, und eine Frage aus dem Arbeitsplatz bekommt Antwort.
#   * Eine eigene config.yaml (ohne Marke) bleibt unangetastet.
#   * Continues leere Standarddatei (models: []) ersetzt OTA.
#   * Ausgeschaltet: Verknüpfungen und OTAs Konfiguration sind beim nächsten
#     Start weg, die Firewall gibt den Server nicht mehr frei.
#
# Der KI-Server: OTA_TEST_KI_URL (Vorgabe http://192.168.66.225:8080) und
# OTA_TEST_KI_MODELL (Vorgabe Hauptmodell). Stellt am Ende her, was vorher
# eingestellt war.
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
KI="${OTA_TEST_KI_URL:-http://192.168.66.225:8080}"
MODELL="${OTA_TEST_KI_MODELL:-Hauptmodell}"

api() { curl -sk -b "$TMP/a.jar" -c "$TMP/a.jar" -H 'Content-Type: application/json' "$@"; }
code() { curl -sk -o /dev/null -w '%{http_code}' -b "$TMP/a.jar" -H 'Content-Type: application/json' "$@"; }
jqp() { python3 -c "import sys,json;d=json.load(sys.stdin);print($1)" 2>/dev/null; }
container_von() {
  local c=""
  for _ in $(seq 1 60); do
    c=$(docker ps --filter "label=ota.session_id=$1" --filter status=running --format '{{.Names}}' | head -1)
    [ -n "$c" ] && break; sleep 3
  done
  echo "$c"
}
starten() {
  local sid=""
  for _ in 1 2 3; do
    sid=$(api -X POST "$B/api/sessions" -d "{\"template_id\":\"$1\"}" | jqp "d.get('id','')")
    [ -n "$sid" ] && break; sleep 5
  done
  echo "$sid"
}
beenden() { [ -n "$1" ] && api -X DELETE "$B/api/sessions/$1" >/dev/null; }
heim() { docker exec "$1" sh -c 'getent passwd 1000 | cut -d: -f6'; }
# Wartet, bis die Pakete im Hintergrund installiert sind (oder 3 Minuten).
warten_auf_pakete() {
  for _ in $(seq 1 60); do
    docker exec "$1" sh -c 'pgrep -f "dpkg -i /tmp/ota-ide-ai" >/dev/null' || {
      docker exec "$1" sh -c "dpkg-query -W ota-ide-ai-vscode ota-ide-ai-jetbrains" >/dev/null 2>&1 && return; }
    sleep 3
  done
}

VORHER=""; SID=""
aufraeumen() {
  echo
  echo "Aufräumen"
  beenden "$SID"
  if [ -n "$VORHER" ]; then
    jqp "json.dumps({k: v for k, v in d.items() if k not in ('api_key_gesetzt', 'fassungen')})" \
      <<<"$VORHER" > "$TMP/vorher.json"
    expect "200" "$(code -X PUT "$B/api/admin/ide-ai" -d @"$TMP/vorher.json")" "Einstellungen von IDE-AI wie vorher"
  fi
  rm -rf "$TMP"
  echo
  printf '  bestanden: %d   fehlgeschlagen: %d\n' "$pass" "$fail"
  [ "$fail" -eq 0 ] || exit 1
}
trap aufraeumen EXIT

echo "IDE-AI gegen $B, KI-Server $KI ($MODELL)"
curl -sk -c "$TMP/a.jar" -o /dev/null -X POST "$B/api/auth/login" -H 'Content-Type: application/json' \
  -d "{\"username\":\"$ADMIN\",\"password\":\"$ADMIN_PW\"}"
VORHER=$(api "$B/api/admin/ide-ai")
[ -n "$(jqp "d['an']" <<<"$VORHER")" ] || { bad "Kein Zugriff auf /api/admin/ide-ai"; VORHER=""; exit 1; }

# ------------------------------------------------------------------ Einstellungen
echo
echo "Einstellungen"
R=$(api -X POST "$B/api/admin/ide-ai/modelle" -d "{\"url\":\"$KI\"}")
expect "True" "$(jqp "str('$MODELL' in [m['id'] for m in d])" <<<"$R")" "Modelle abgerufen, $MODELL ist dabei"
expect "400" "$(code -X PUT "$B/api/admin/ide-ai" -d '{"url":"ftp://x"}')" "Eine Adresse ohne http(s) wird abgewiesen"
expect "400" "$(code -X PUT "$B/api/admin/ide-ai" -d "{\"url\":\"$KI\",\"modelle\":[{\"id\":\"$MODELL\",\"kontext\":2048,\"max_tokens\":2048}]}")" \
  "Antwortlänge ≥ Kontextfenster wird abgewiesen"
R=$(api -X PUT "$B/api/admin/ide-ai" -d "{\"url\":\"$KI\",\"api_key\":\"pruef-schluessel\",\"an\":true,\
\"modelle\":[{\"id\":\"$MODELL\",\"kontext\":32768,\"max_tokens\":2048}],\"regeln\":\"Antworte auf Deutsch.\",\"werkzeuge\":true}")
expect "$KI/v1" "$(jqp "d['url']" <<<"$R")" "Gespeichert, /v1 ergänzt"
expect "True" "$(jqp "str(d['api_key_gesetzt'] and 'api_key' not in d and 'pruef-schluessel' not in json.dumps(d))" <<<"$R")" \
  "Der API-Schlüssel kommt nicht zurück"
expect "False" "$(api "$B/api/firewall/global" | jqp "str(any('IDE-AI' in r.get('notiz','') for r in d))")" \
  "Die Freigabe steht nicht in der Liste, die man bearbeitet"
# llama.cpp nimmt jeden Schlüssel an; ein vLLM mit --api-key prüft ihn.
api -X PUT "$B/api/admin/ide-ai" -d '{"api_key":""}' >/dev/null
R=$(api -X POST "$B/api/admin/ide-ai/testen" -d "{\"modell\":\"$MODELL\"}")
expect "True" "$(jqp "str(d.get('ok'))" <<<"$R")" "Testfrage an $MODELL ($(jqp "d.get('ms')" <<<"$R") ms)"
R=$(api "$B/api/admin/ide-ai")
VS=$(jqp "d['fassungen'].get('vscode','')" <<<"$R"); JBV=$(jqp "d['fassungen'].get('jetbrains','')" <<<"$R")
[ -n "$VS" ] && [ -n "$JBV" ] && ok "Beide Pakete in der Paketquelle ($VS, $JBV)" || bad "Pakete fehlen in der Paketquelle"
expect "200" "$(docker exec ota-agent python -c "
import os, urllib.request
r = urllib.request.urlopen(urllib.request.Request('http://ota-repo:8200/pakete/ota-ide-ai-vscode/$VS/datei',
    headers={'X-Agent-Token': os.environ['OTA_AGENT_TOKEN']}))
print(r.status)")" "Der Agent bekommt die Paketdatei"
expect "403" "$(docker exec ota-agent python -c "
import urllib.request, urllib.error
try: urllib.request.urlopen('http://ota-repo:8200/pakete/ota-ide-ai-vscode/$VS/datei'); print(200)
except urllib.error.HTTPError as e: print(e.code)")" "… und ohne Token niemand"

# ------------------------------------------------------------------ Arbeitsplätze
TPLS=$(docker exec ota-db psql -U ota -d ota -At -c "select id || '|' || slug from templates where is_enabled and klasse = 'standard'")
GEPRUEFT=0
for zeile in $TPLS; do
  T="${zeile%%|*}"; NAME="${zeile#*|}"
  IMG=$(docker exec ota-db psql -U ota -d ota -At -c "select image_ref from templates where id = '$T'")
  HAT=$(docker run --rm --entrypoint sh "$IMG" -c 'ls -d /usr/share/codium /usr/share/code /opt/*/product-info.json 2>/dev/null | head -1' 2>/dev/null)
  [ -n "$HAT" ] || continue
  GEPRUEFT=$((GEPRUEFT+1))
  echo
  echo "Im Arbeitsplatz $NAME"
  SID=$(starten "$T"); C=$(container_von "$SID")
  [ -n "$C" ] && ok "läuft ($C)" || { bad "kam nicht hoch"; SID=""; continue; }
  H=$(heim "$C")
  expect "# Verwaltet von OTA (IDE-AI). Änderungen hier überschreibt OTA beim nächsten Start." \
    "$(docker exec "$C" head -1 "$H/.continue/config.yaml" 2>/dev/null)" "config.yaml mit OTAs Marke"
  K=$(docker exec "$C" cat "$H/.continue/config.yaml" 2>/dev/null)
  grep -q "contextLength: 32768" <<<"$K" && grep -q "maxTokens: 2048" <<<"$K" && grep -q "apiBase: $KI/v1" <<<"$K" \
    && ok "… mit Server, Kontextfenster und Antwortlänge" || bad "config.yaml passt nicht: $(head -c 300 <<<"$K")"
  expect "1000" "$(docker exec "$C" stat -c %u "$H/.continue/config.yaml")" "… sie gehört dem Menschen"
  expect "False" "$(docker exec "$C" cat "$H/.continue/index/globalContext.json" | jqp "str(d['sharedConfig']['allowAnonymousTelemetry'])")" \
    "Telemetrie von Continue aus"
  warten_auf_pakete "$C"
  if docker exec "$C" test -d /usr/share/codium/resources/app/extensions -o -d /usr/share/code/resources/app/extensions; then
    expect "/usr/share/ota-ide-ai/vscode/continue" \
      "$(docker exec "$C" sh -c 'readlink /usr/share/codium/resources/app/extensions/ota-continue || readlink /usr/share/code/resources/app/extensions/ota-continue')" \
      "Continue in VS Code/VSCodium verknüpft"
    expect "/usr/share/ota-ide-ai/vscode/ota" \
      "$(docker exec "$C" sh -c 'readlink /usr/share/codium/resources/app/extensions/ota-ide-ai || readlink /usr/share/code/resources/app/extensions/ota-ide-ai')" \
      "… und OTAs Erweiterung daneben (Continue rechts, Copilot aus)"
    expect "secondarySidebar" \
      "$(docker exec "$C" python3 -c 'import json;print(*json.load(open("/usr/share/ota-ide-ai/vscode/continue/package.json"))["contributes"]["viewsContainers"])' 2>/dev/null | grep -o secondarySidebar)" \
      "Continue sitzt in der zweiten Seitenleiste"
  fi
  for JBDIR in $(docker exec "$C" sh -c 'for f in /opt/*/product-info.json; do [ -f "$f" ] && sed -n "s/.*\"dataDirectoryName\": *\"\([^\"]*\)\".*/\1/p" "$f" | head -1; done'); do
    expect "/usr/share/ota-ide-ai/jetbrains/continue-intellij-extension" \
      "$(docker exec "$C" readlink "$H/.local/share/JetBrains/$JBDIR/ota-continue")" "Continue für $JBDIR im Zuhause verknüpft"
  done
  if docker exec "$C" test -d /usr/share/ota-ide-ai/jetbrains/continue-intellij-extension; then
    J=/usr/share/ota-ide-ai/jetbrains/continue-intellij-extension
    # Continue setzt die Rechte auf continue-binary selbst — nur als Eigentümer.
    expect "$(docker exec "$C" stat -c %u "$H")" "$(docker exec "$C" stat -c %u "$J/core/linux-x64/continue-binary")" \
      "continue-binary gehört dem Menschen"
    # Ab 2026.2 ist JCEF ein eigenes Plugin; ohne die Abhängigkeit bleibt Continue leer.
    expect "com.intellij.modules.jcef" \
      "$(docker exec "$C" python3 -c 'import glob,zipfile
for j in glob.glob("'"$J"'/lib/continue-intellij-extension-*.jar"):
    z=zipfile.ZipFile(j)
    if "META-INF/plugin.xml" in z.namelist() and "com.intellij.modules.jcef" in z.read("META-INF/plugin.xml").decode(): print("com.intellij.modules.jcef")' 2>/dev/null)" \
      "JetBrains-Plugin meldet JCEF an"
  fi
  expect "200" "$(docker exec -u 1000 "$C" curl -s -m 15 -o /dev/null -w '%{http_code}' "$KI/v1/models")" \
    "Die Firewall lässt den KI-Server durch"
  A=$(docker exec -u 1000 "$C" curl -s -m 180 "$KI/v1/chat/completions" -H 'Content-Type: application/json' \
    -d "{\"model\":\"$MODELL\",\"max_tokens\":2048,\"messages\":[{\"role\":\"user\",\"content\":\"Antworte nur mit: OK\"}]}" \
    | jqp "d['choices'][0]['message']['content'].strip()")
  [ -n "$A" ] && ok "Eine Frage aus dem Arbeitsplatz bekommt Antwort ($A)" || bad "Keine Antwort aus dem Arbeitsplatz"

  # Eine eigene Datei: OTA fasst sie nicht an.
  docker exec -u 1000 "$C" sh -c "printf 'name: meins\nversion: 1.0.0\nschema: v1\n' > '$H/.continue/config.yaml'"
  beenden "$SID"; SID=""
  # Das Zuhause bleibt: nächster Start, gleiche Datei.
  SID=$(starten "$T"); C=$(container_von "$SID")
  expect "name: meins" "$(docker exec "$C" head -1 "$H/.continue/config.yaml" 2>/dev/null)" "Eine eigene config.yaml bleibt unangetastet"
  # Continues eigene Leerdatei (Continue lief, bevor IDE-AI an war): OTA ersetzt sie.
  docker exec -u 1000 "$C" sh -c "printf 'name: Main Config\nversion: 1.0.0\nschema: v1\nmodels: []\n' > '$H/.continue/config.yaml'"
  beenden "$SID"; SID=""
  SID=$(starten "$T"); C=$(container_von "$SID")
  expect "# Verwaltet von OTA (IDE-AI). Änderungen hier überschreibt OTA beim nächsten Start." \
    "$(docker exec "$C" head -1 "$H/.continue/config.yaml" 2>/dev/null)" "Continues leere Standarddatei ersetzt OTA"
  docker exec "$C" rm -f "$H/.continue/config.yaml"
  beenden "$SID"; SID=""
done
[ "$GEPRUEFT" -gt 0 ] || bad "Keine Vorlage mit VS Code, VSCodium oder JetBrains-IDE gefunden"

# ------------------------------------------------------------------ Aus
echo
echo "Ausgeschaltet"
T=$(docker exec ota-db psql -U ota -d ota -At -c "select id from templates where is_enabled and slug = 'arbeitsplatz'")
if [ -n "$T" ]; then
  # Erst einmal an: config.yaml und Verknüpfung im Zuhause entstehen …
  SID=$(starten "$T"); C=$(container_von "$SID"); H=$(heim "$C")
  expect "ja" "$(docker exec "$C" sh -c "test -e '$H/.continue/config.yaml' && echo ja || echo nein")" "Vorher: config.yaml da"
  beenden "$SID"; SID=""
  # … dann aus: Das Zuhause bleibt, aber OTA räumt beim Start weg, was es
  # angelegt hat.
  api -X PUT "$B/api/admin/ide-ai" -d '{"an":false}' >/dev/null
  SID=$(starten "$T"); C=$(container_von "$SID"); H=$(heim "$C")
  expect "nein" "$(docker exec "$C" sh -c "test -e '$H/.continue/config.yaml' && echo ja || echo nein")" "Keine config.yaml"
  expect "0" "$(docker exec "$C" sh -c "ls -d '$H'/.local/share/JetBrains/*/ota-continue 2>/dev/null | wc -l")" "Keine Verknüpfung im Zuhause"
  expect "0" "$(docker exec "$C" sh -c 'ls -d /usr/share/code*/resources/app/extensions/ota-* 2>/dev/null | wc -l')" \
    "Keine Verknüpfung in VS Code/VSCodium (Copilot wieder da)"
  expect "000" "$(docker exec -u 1000 "$C" curl -s -m 8 -o /dev/null -w '%{http_code}' "$KI/v1/models")" \
    "Die Firewall gibt den KI-Server nicht mehr frei"
  beenden "$SID"; SID=""
fi
