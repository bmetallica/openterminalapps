#!/usr/bin/env bash
# Prüft den KI-Durchgang und die Nutzungsstatistik (Handbuch Kapitel 28).
#
#   * Einstellungen: Durchgang und Statistik an; ohne Durchgang keine
#     Statistik; ein weiterer Server mit doppeltem Kürzel wird abgelehnt.
#   * Firewall: Umleitung für die Adresse des KI-Servers, Eingang des
#     Durchgangs nur aus den Sitzungsnetzen.
#   * Im Arbeitsplatz: ki.ota löst sich auf, das Modellverzeichnis kommt vom
#     Durchgang, eine Frage über ki.ota bekommt Antwort (mit Strom, ohne den
#     Nutzungsblock, den nur der Durchgang bestellt hat), eine Frage an die
#     echte Adresse auch (abgefangen). Continue und opencode zeigen auf ki.ota,
#     ohne Schlüssel.
#   * Statistik: Nach spätestens drei Minuten stehen die Anfragen beim
#     Menschen und seinem Arbeitsplatz, mit Tokens.
#   * Ausfall: Liegt ota-ki, nimmt die Firewall die Umleitung heraus, und die
#     echte Adresse antwortet direkt. Danach kommt sie zurück.
#
# Der KI-Server: OTA_TEST_KI_URL (Vorgabe http://192.168.66.225:8080) und
# OTA_TEST_KI_MODELL (Vorgabe Hauptmodell). Stellt am Ende her, was vorher
# eingestellt war, und löscht die Zahlen, die der Test erzeugt hat, nicht —
# sie stehen unter dem Testkonto.
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
VORLAGE="${OTA_TEST_VORLAGE:-arbeitsplatz}"

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
frage() {  # frage <container> <url> <stream:true|false>
  docker exec -u 1000 "$1" curl -s -m 180 "$2/chat/completions" -H 'Content-Type: application/json' \
    -H 'Authorization: Bearer ota' \
    -d "{\"model\":\"$MODELL\",\"stream\":$3,\"max_tokens\":512,\"messages\":[{\"role\":\"user\",\"content\":\"Antworte nur mit: OK\"}]}"
}

VORHER=""; SID=""; USID=""
aufraeumen() {
  echo
  echo "Aufräumen"
  [ -n "$SID" ] && api -X DELETE "$B/api/sessions/$SID" >/dev/null
  [ -n "$USID" ] && curl -sk -b "$TMP/u.jar" -X DELETE "$B/api/sessions/$USID" >/dev/null
  docker start ota-ki >/dev/null 2>&1
  if [ -n "$VORHER" ]; then
    jqp "json.dumps({k: v for k, v in d.items() if k not in ('api_key_gesetzt', 'fassungen', 'ki_url', 'durchgang_aktiv', 'modelle_alle')})" \
      <<<"$VORHER" > "$TMP/vorher.json"
    expect "200" "$(code -X PUT "$B/api/admin/ide-ai" -d @"$TMP/vorher.json")" "Einstellungen von IDE-AI wie vorher"
  fi
  rm -rf "$TMP"
  echo
  printf '  bestanden: %d   fehlgeschlagen: %d\n' "$pass" "$fail"
  [ "$fail" -eq 0 ] || exit 1
}
trap aufraeumen EXIT

echo "KI-Durchgang gegen $B, KI-Server $KI ($MODELL)"
curl -sk -c "$TMP/a.jar" -o /dev/null -X POST "$B/api/auth/login" -H 'Content-Type: application/json' \
  -d "{\"username\":\"$ADMIN\",\"password\":\"$ADMIN_PW\"}"
VORHER=$(api "$B/api/admin/ide-ai")
[ -n "$(jqp "d['an']" <<<"$VORHER")" ] || { bad "Kein Zugriff auf /api/admin/ide-ai"; VORHER=""; exit 1; }
ADMIN_ID=$(api "$B/api/auth/me" | jqp "d.get('id','')")

# ------------------------------------------------------------------ Einstellungen
echo
echo "Einstellungen"
expect "400" "$(code -X PUT "$B/api/admin/ide-ai" -d '{"durchgang":false,"statistik":true}')" \
  "Statistik ohne Durchgang abgelehnt"
expect "400" "$(code -X PUT "$B/api/admin/ide-ai" -d "{\"weitere\":[{\"kuerzel\":\"$(jqp "d['kuerzel']" <<<"$VORHER")\",\"url\":\"$KI\"}]}")" \
  "Weiterer Server mit doppeltem Kürzel abgelehnt"
R=$(api -X PUT "$B/api/admin/ide-ai" -d "{\"an\":true,\"url\":\"$KI\",\"durchgang\":true,\"statistik\":true}")
expect "True" "$(jqp "d['durchgang_aktiv']" <<<"$R")" "Durchgang an"
sleep 3
ST=$(api "$B/api/admin/ki-nutzung/status")
expect "True" "$(jqp "d['firewall']['bereit']" <<<"$ST")" "Firewall meldet den Durchgang bereit"

# ------------------------------------------------------------------ Firewall
echo
echo "Firewall"
HOST=$(python3 -c "from urllib.parse import urlparse;import sys;print(urlparse(sys.argv[1]).hostname)" "$KI")
PORT=$(python3 -c "from urllib.parse import urlparse;import sys;u=urlparse(sys.argv[1]);print(u.port or 80)" "$KI")
docker exec ota-firewall nft list chain inet ota prerouting | grep -q "ip daddr $HOST tcp dport $PORT .*redirect to :8790" \
  && ok "Umleitung $HOST:$PORT → Durchgang steht" || bad "Keine Umleitung für $HOST:$PORT"
docker exec ota-firewall nft list chain inet ota input | grep -q "tcp dport 8790 iifname != \"lo\" ip saddr != " \
  && ok "Der Durchgang ist nur aus den Sitzungsnetzen erreichbar" || bad "Eingangsregel des Durchgangs fehlt"

# ------------------------------------------------------------------ Arbeitsplatz
echo
echo "Im Arbeitsplatz"
T=$(docker exec ota-db psql -U ota -d ota -At -c "select id from templates where slug = '$VORLAGE'")
SID=$(starten "$T"); C=$(container_von "$SID")
[ -n "$C" ] || { bad "Arbeitsplatz $VORLAGE startet nicht"; exit 1; }
ok "Arbeitsplatz läuft ($C)"
sleep 5
GW=$(docker exec "$C" sh -c "ip route | awk '/default/ {print \$3}'")
expect "$GW" "$(docker exec "$C" getent hosts ki.ota | awk '{print $1}')" "ki.ota ist der Router dieses Netzes"
M=$(docker exec -u 1000 "$C" curl -s -m 15 "http://ki.ota:8790/v1/models")
expect "True" "$(jqp "str('$MODELL' in [m['id'] for m in d['data']])" <<<"$M")" "Modellverzeichnis über ki.ota"
A=$(frage "$C" "http://ki.ota:8790/v1" false | jqp "d['choices'][0]['message']['content'].strip()")
[ -n "$A" ] && ok "Frage über ki.ota bekommt Antwort ($A)" || bad "Keine Antwort über ki.ota"
S=$(frage "$C" "http://ki.ota:8790/v1" true)
grep -q '"content"' <<<"$S" && ok "Strom über ki.ota kommt an" || bad "Kein Strom über ki.ota"
if grep -q '"choices":\[\],' <<<"$S" || grep -q '"choices": \[\],' <<<"$S"; then
  bad "Der bestellte Nutzungsblock kam beim Client an"
else
  ok "Der Nutzungsblock, den nur der Durchgang bestellt hat, kam nicht an"
fi
A=$(frage "$C" "$KI/v1" false | jqp "d['choices'][0]['message']['content'].strip()")
[ -n "$A" ] && ok "Frage an die echte Adresse bekommt Antwort ($A) — abgefangen" || bad "Keine Antwort von der echten Adresse"
H=$(docker exec "$C" sh -c 'getent passwd 1000 | cut -d: -f6')
if docker exec "$C" test -f "$H/.continue/config.yaml"; then
  docker exec "$C" grep -q "apiBase: http://ki.ota:8790/v1" "$H/.continue/config.yaml" \
    && ok "Continue zeigt auf ki.ota" || bad "Continue zeigt nicht auf ki.ota"
  docker exec "$C" grep -q "apiKey" "$H/.continue/config.yaml" \
    && bad "In der Continue-Konfiguration steht ein Schlüssel" || ok "Kein Schlüssel in der Continue-Konfiguration"
fi
if docker exec "$C" test -f /etc/opencode/opencode.jsonc; then
  docker exec "$C" grep -q '"baseURL": "http://ki.ota:8790/v1"' /etc/opencode/opencode.jsonc \
    && ok "opencode zeigt auf ki.ota" || bad "opencode zeigt nicht auf ki.ota"
fi

# ------------------------------------------------------------------ Mehrere Server
echo
echo "Mehrere Server"
# Ein zweiter Eintrag für denselben Server — gleiches Modell, anderes Kürzel.
R=$(api -X PUT "$B/api/admin/ide-ai" -d "{\"weitere\":[{\"name\":\"Zweiter\",\"kuerzel\":\"zwei\",\"url\":\"$KI\",\"modelle\":[{\"id\":\"$MODELL\",\"kontext\":8192,\"max_tokens\":512}]}]}")
expect "True" "$(jqp "str('zwei/$MODELL' in [m['id'] for m in d['modelle_alle']])" <<<"$R")" \
  "Gleichnamiges Modell des zweiten Servers heißt zwei/$MODELL"
sleep 3
M=$(docker exec -u 1000 "$C" curl -s -m 15 "http://ki.ota:8790/v1/models")
expect "True" "$(jqp "str('zwei/$MODELL' in [m['id'] for m in d['data']])" <<<"$M")" "Vereinigtes Modellverzeichnis"
A=$(docker exec -u 1000 "$C" curl -s -m 180 "http://ki.ota:8790/v1/chat/completions" -H 'Content-Type: application/json' \
  -d "{\"model\":\"zwei/$MODELL\",\"max_tokens\":512,\"messages\":[{\"role\":\"user\",\"content\":\"Antworte nur mit: OK\"}]}" \
  | jqp "d['choices'][0]['message']['content'].strip()")
[ -n "$A" ] && ok "Frage an zwei/$MODELL bekommt Antwort ($A)" || bad "Keine Antwort von zwei/$MODELL"
expect "404" "$(docker exec -u 1000 "$C" curl -s -m 15 -o /dev/null -w '%{http_code}' "http://ki.ota:8790/v1/chat/completions" \
  -H 'Content-Type: application/json' -d '{"model":"gibt-es-nicht","messages":[]}')" "Unbekanntes Modell: 404 mit Erklärung"

# ------------------------------------------------------------------ Gruppen je Server
echo
echo "Weiterer Server nur für eine Gruppe"
# Ein normaler Mensch (nur Gruppe users); der zweite Server zuerst nur für
# admins, dann für users.
TEST_USER="ki-pruef"; TEST_PW="Ki-$(openssl rand -hex 8)"
"$ROOT/scripts/lokales-testkonto.sh" "$TEST_USER" "$TEST_PW" "$TEST_USER@ota.invalid" users >/dev/null
GID() { api "$B/api/admin/groups" | jqp "[g['id'] for g in d if g['slug'] == '$1'][0]"; }
ADMINS=$(GID admins); USERS=$(GID users)
weiter() {  # weiter <gruppen-kennung>
  api -X PUT "$B/api/admin/ide-ai" -d "{\"weitere\":[{\"name\":\"Zweiter\",\"kuerzel\":\"zwei\",\"url\":\"$KI\",\"gruppen\":[\"$1\"],\"modelle\":[{\"id\":\"$MODELL\",\"kontext\":8192,\"max_tokens\":512}]}]}" >/dev/null
}
weiter "$ADMINS"
curl -sk -c "$TMP/u.jar" -o /dev/null -X POST "$B/api/auth/login" -H 'Content-Type: application/json' \
  -d "{\"username\":\"$TEST_USER\",\"password\":\"$TEST_PW\"}"
for _ in 1 2 3; do
  USID=$(curl -sk -b "$TMP/u.jar" -H 'Content-Type: application/json' -X POST "$B/api/sessions" \
    -d "{\"template_id\":\"$T\"}" | jqp "d.get('id','')")
  [ -n "$USID" ] && break; sleep 5
done
CU=$(container_von "$USID")
if [ -z "$CU" ]; then
  bad "Arbeitsplatz für $TEST_USER startet nicht"
else
  sleep 5
  M=$(docker exec -u 1000 "$CU" curl -s -m 15 "http://ki.ota:8790/v1/models")
  expect "False" "$(jqp "str('zwei/$MODELL' in [m['id'] for m in d['data']])" <<<"$M")" \
    "$TEST_USER sieht den Server der Gruppe admins nicht"
  expect "True" "$(jqp "str('$MODELL' in [m['id'] for m in d['data']])" <<<"$M")" "… den ersten Server aber schon"
  expect "403" "$(docker exec -u 1000 "$CU" curl -s -m 30 -o /dev/null -w '%{http_code}' "http://ki.ota:8790/v1/chat/completions" \
    -H 'Content-Type: application/json' -d "{\"model\":\"zwei/$MODELL\",\"max_tokens\":16,\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}]}")" \
    "Frage an den Server der Gruppe admins: 403"
  M=$(docker exec -u 1000 "$C" curl -s -m 15 "http://ki.ota:8790/v1/models")
  expect "True" "$(jqp "str('zwei/$MODELL' in [m['id'] for m in d['data']])" <<<"$M")" "Administratoren sehen ihn immer"
  HU=$(docker exec "$CU" sh -c 'getent passwd 1000 | cut -d: -f6')
  if docker exec "$CU" test -f /etc/opencode/opencode.jsonc; then
    docker exec "$CU" grep -q "zwei/$MODELL" /etc/opencode/opencode.jsonc \
      && bad "opencode von $TEST_USER kennt den Server der Gruppe admins" \
      || ok "opencode von $TEST_USER bietet ihn nicht an"
  fi
  weiter "$USERS"
  sleep 2
  M=$(docker exec -u 1000 "$CU" curl -s -m 15 "http://ki.ota:8790/v1/models")
  expect "True" "$(jqp "str('zwei/$MODELL' in [m['id'] for m in d['data']])" <<<"$M")" \
    "Für die Gruppe users freigegeben: $TEST_USER sieht ihn sofort"
  A=$(docker exec -u 1000 "$CU" curl -s -m 180 "http://ki.ota:8790/v1/chat/completions" -H 'Content-Type: application/json' \
    -d "{\"model\":\"zwei/$MODELL\",\"max_tokens\":512,\"messages\":[{\"role\":\"user\",\"content\":\"Antworte nur mit: OK\"}]}" \
    | jqp "d['choices'][0]['message']['content'].strip()")
  [ -n "$A" ] && ok "… und bekommt Antwort ($A)" || bad "Keine Antwort für $TEST_USER von zwei/$MODELL"
fi

# ------------------------------------------------------------------ Statistik
echo
echo "Statistik (bis zu drei Minuten)"
N=0
for _ in $(seq 1 36); do
  U=$(api "$B/api/admin/ki-nutzung/nutzer/$ADMIN_ID?von=$(date -u -d '-1 hour' +%Y-%m-%dT%H:%M:%SZ)")
  N=$(jqp "sum(p['anfragen'] for p in d['arbeitsplaetze'])" <<<"$U")
  Z=$(jqp "str(any(m['server'] == 'zwei' for m in d['modelle']))" <<<"$U")
  [ "${N:-0}" -ge 3 ] 2>/dev/null && [ "$Z" = "True" ] && break
  sleep 5
done
[ "${N:-0}" -ge 3 ] 2>/dev/null && ok "Anfragen stehen beim Menschen ($N)" || bad "Anfragen fehlen in der Statistik (${N:-0})"
expect "True" "$(jqp "str(any(p['ein'] > 0 and p['aus'] > 0 for p in d['arbeitsplaetze']))" <<<"$U")" "Mit Tokens"
expect "True" "$(jqp "str(len(d['verlauf']['reihen']) > 0)" <<<"$U")" "Verlauf je Arbeitsplatz"
expect "True" "$Z" "Der zweite Server steht in der Statistik"
UE=$(api "$B/api/admin/ki-nutzung")
expect "True" "$(jqp "str(any(n['user_id'] == '$ADMIN_ID' for n in d['nutzer']))" <<<"$UE")" "Der Mensch steht in der Übersicht"
expect "True" "$(docker exec ota-db psql -U ota -d ota -At -c "select count(*) > 0 from audit_log where action = 'ki.nutzung_angesehen' and object_id = '$ADMIN_ID'" | sed 's/t/True/;s/f/False/')" \
  "Das Ansehen steht im Prüfprotokoll"

# ------------------------------------------------------------------ Ausfall
echo
echo "Ausfall des Durchgangs"
docker stop ota-ki >/dev/null
for _ in $(seq 1 12); do
  docker exec ota-firewall nft list chain inet ota prerouting | grep -q "redirect to :8790" || break
  sleep 3
done
docker exec ota-firewall nft list chain inet ota prerouting | grep -q "redirect to :8790" \
  && bad "Umleitung steht noch, obwohl ota-ki liegt" || ok "Umleitung aufgehoben, solange ota-ki liegt"
A=$(frage "$C" "$KI/v1" false | jqp "d['choices'][0]['message']['content'].strip()")
[ -n "$A" ] && ok "Die echte Adresse antwortet direkt ($A)" || bad "Ohne Durchgang keine Antwort"
docker start ota-ki >/dev/null
for _ in $(seq 1 12); do
  docker exec ota-firewall nft list chain inet ota prerouting | grep -q "redirect to :8790" && break
  sleep 3
done
docker exec ota-firewall nft list chain inet ota prerouting | grep -q "redirect to :8790" \
  && ok "Umleitung wieder gesetzt" || bad "Umleitung kommt nicht zurück"
