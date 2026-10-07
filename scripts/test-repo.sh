#!/usr/bin/env bash
# Prüft die eigene Paketquelle (Handbuch Kapitel 26) gegen die laufende Anlage.
#
#   * Steuerdienst erreichbar, Spiegel veröffentlicht, Schlüssel abrufbar
#   * Eigenes Paket: Hochladen, Doppelt (409), Kaputt (422), Löschen
#   * Snapshots: anlegen, unter snap/<name>/ abrufbar, „Bauen gegen" schützt
#     vor dem Löschen, löschen
#   * Ein Debian-13-Arbeitsplatz bekommt die Quelle eingetragen und
#     installiert das eigene Paket **von hier**, nicht aus dem Internet
#   * Betriebsart „nur": die Internetquellen sind abgeschaltet
#   * Bildbauer: Eintragen am Anfang, Austragen am Ende des Dockerfiles
#   * Kein Debian 13 (Ubuntu): es wird nichts eingetragen
#   * Root-Arbeitsplatz: Fortsetzen trägt die Quelle neu ein (falls Sysbox)
#
# Ohne OTA_REPO=1 wird übersprungen statt rot. Ein Vollspiegel ist nicht
# nötig — ein kleiner OTA_REPO_FILTER mit `hello` reicht.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
[ -f "$ROOT/deploy/.env" ] && { set -a; . "$ROOT/deploy/.env"; set +a; }

pass=0; fail=0
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; pass=$((pass+1)); }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$1"; fail=$((fail+1)); }
info() { printf '    %s\n' "$1"; }

BASE_URL="${OTA_BASE:-https://127.0.0.1:${OTA_HTTPS_PORT:-8443}}"
TMP="$(mktemp -d)"
ADMIN="${OTA_TEST_ADMIN:-notfall}"
ADMIN_PW="${OTA_TEST_ADMIN_PW:?OTA_TEST_ADMIN_PW fehlt. Trag es in deploy/.env ein.}"
IMAGE="${OTA_DESKTOP_TAG:-ota/base-desktop:1}"
ROOT_IMAGE="${OTA_ROOT_TAG:-ota/base-desktop-root:1}"
PAKET="ota-repo-pruefung"
SNAP="pruefung-$$"

api()  { curl -sk -b "$TMP/jar" -c "$TMP/jar" "$@"; }
jqp()  { python3 -c "import sys,json;d=json.load(sys.stdin);print($1)" 2>/dev/null; }
als_root() { docker exec -u 0 "$1" sh -c "$2" 2>&1; }

echo "Eigene Paketquelle (Kapitel 26)"
if [ "${OTA_REPO:-0}" != "1" ]; then
  echo "  (übersprungen — OTA_REPO ist nicht 1)"
  exit 0
fi

TID=""; SID=""; RTID=""; RSID=""; VORHER=""
einstellen() {
  api -X PUT -H 'Content-Type: application/json' "$BASE_URL/api/paketquellen/einstellungen" \
    -d "$1" -o /dev/null -w '%{http_code}'
}
aufraeumen() {
  # Ein gewöhnlicher Arbeitsplatz endet über /api/sessions; ein Root-Platz
  # würde dort nur angehalten — er wird über die Verwaltung gelöscht.
  [ -n "$SID" ] && api -X DELETE "$BASE_URL/api/sessions/$SID" >/dev/null 2>&1
  [ -n "$RSID" ] && api -X DELETE "$BASE_URL/api/admin/arbeitsplaetze/$RSID" >/dev/null 2>&1
  for t in "$TID" "$RTID"; do
    [ -n "$t" ] && api -X DELETE "$BASE_URL/api/templates/$t" >/dev/null 2>&1
  done
  [ -n "$VORHER" ] && einstellen "$VORHER" >/dev/null
  api -X DELETE "$BASE_URL/api/paketquellen/snapshots/$SNAP" >/dev/null 2>&1
  for k in $(api "$BASE_URL/api/paketquellen/pakete" \
             | jqp "' '.join(p['schluessel'] for p in d if p['name']=='$PAKET')"); do
    api -X DELETE "$BASE_URL/api/paketquellen/pakete/$k" >/dev/null 2>&1
  done
  rm -rf "$TMP"
}
trap aufraeumen EXIT

code=$(curl -sk -c "$TMP/jar" -o /dev/null -w '%{http_code}' -X POST "$BASE_URL/api/auth/login" \
  -H 'Content-Type: application/json' -d "{\"username\":\"$ADMIN\",\"password\":\"$ADMIN_PW\"}")
[ "$code" = "200" ] || { bad "Anmeldung als $ADMIN scheiterte ($code)"; exit 1; }

# ------------------------------------------------------------------ Dienst
echo
echo "Dienst"
STATUS=$(api "$BASE_URL/api/paketquellen")
[ "$(jqp "d['erreichbar']" <<<"$STATUS")" = "True" ] && ok "Steuerdienst erreichbar" \
  || { bad "Steuerdienst nicht erreichbar"; exit 1; }
VORHER=$(jqp "__import__('json').dumps(d['einstellungen'])" <<<"$STATUS")
VEROEFF=$(jqp "len(d['status']['veroeffentlicht'])" <<<"$STATUS")
[ "${VEROEFF:-0}" -ge 1 ] && ok "$VEROEFF Veröffentlichungen" || bad "Nichts veröffentlicht"
[ "$(curl -sk -o /dev/null -w '%{http_code}' "$BASE_URL/repo/ota-repo.asc")" = "200" ] \
  && ok "Öffentlicher Schlüssel unter /repo/ota-repo.asc" || bad "Schlüssel nicht abrufbar"
[ "$(curl -sk -o /dev/null -w '%{http_code}' "$BASE_URL/repo/ota/dists/ota/InRelease")" = "200" ] \
  && ok "Eigenes Repo signiert (InRelease)" || bad "Eigenes Repo ohne InRelease"
[ "$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE_URL/api/paketquellen/abgleich" -k)" = "401" ] \
  && ok "Abgleich ohne Anmeldung: 401" || bad "Abgleich ohne Anmeldung möglich"
[ "$(einstellen '{"modus":"vielleicht"}')" = "422" ] && ok "Unbekannte Betriebsart: 422" \
  || bad "Unbekannte Betriebsart angenommen"

# ----------------------------------------------------------- Eigene Pakete
echo
echo "Eigene Pakete"
mkdir -p "$TMP/pkg/DEBIAN" "$TMP/pkg/usr/share/$PAKET"
printf 'Package: %s\nVersion: 1.0\nArchitecture: all\nMaintainer: OTA <repo@ota.invalid>\nDescription: Prüfpaket von test-repo.sh\n' \
  "$PAKET" > "$TMP/pkg/DEBIAN/control"
echo "von-hier-$$" > "$TMP/pkg/usr/share/$PAKET/marke"
dpkg-deb --build --root-owner-group "$TMP/pkg" "$TMP/$PAKET.deb" >/dev/null
echo "kein paket" > "$TMP/kaputt.deb"
hoch() { api -F "datei=@$1" -o /dev/null -w '%{http_code}' "$BASE_URL/api/paketquellen/pakete"; }
[ "$(hoch "$TMP/$PAKET.deb")" = "200" ] && ok "Hochgeladen" || bad "Hochladen scheiterte"
[ "$(hoch "$TMP/$PAKET.deb")" = "409" ] && ok "Dasselbe noch einmal: 409" || bad "Doppelt angenommen"
[ "$(hoch "$TMP/kaputt.deb")" = "422" ] && ok "Kein gültiges .deb: 422" || bad "Kaputtes Paket angenommen"
# Ein präpariertes Paket, von Hand zusammengesetzt (dpkg-deb baut so etwas
# nicht): Name und Fassung landen in aptlys Abfragesprache und dürfen dort
# nichts ausrichten. Abgewiesen wird es doppelt — von dpkg-deb und vom Dienst.
mkdir -p "$TMP/boese/c"
printf 'Package: x), $Version (%% *\nVersion: 1\nArchitecture: all\nMaintainer: x <x@x>\nDescription: x\n' \
  > "$TMP/boese/c/control"
( cd "$TMP/boese" && echo 2.0 > debian-binary && tar czf control.tar.gz -C c ./control \
  && tar czf data.tar.gz -T /dev/null && ar rc "$TMP/boese.deb" debian-binary control.tar.gz data.tar.gz )
[ "$(hoch "$TMP/boese.deb")" = "422" ] && ok "Paketname mit Abfragezeichen: 422" \
  || bad "Präparierter Paketname angenommen"
[ "$(api -X DELETE -o /dev/null -w '%{http_code}' "$BASE_URL/api/paketquellen/pakete/a_1_all%7Cx")" = "400" ] \
  && ok "Löschschlüssel mit Abfragezeichen: 400" || bad "Präparierter Löschschlüssel angenommen"
api "$BASE_URL/api/paketquellen/pakete" | jqp "[p['von'] for p in d if p['name']=='$PAKET'][0]" \
  | grep -q "$ADMIN" && ok "Liste nennt, wer es hochgeladen hat" || bad "Hochladender fehlt"
curl -sk "$BASE_URL/repo/ota/dists/ota/main/binary-amd64/Packages" | grep -q "^Package: $PAKET" \
  && ok "Im eigenen Repo veröffentlicht" || bad "Nicht im Packages-Index"

# --------------------------------------------------------------- Snapshots
echo
echo "Snapshots"
[ "$(api -H 'Content-Type: application/json' -X POST "$BASE_URL/api/paketquellen/snapshots" \
     -d "{\"name\":\"$SNAP\",\"notiz\":\"test-repo.sh\"}" -o /dev/null -w '%{http_code}')" = "200" ] \
  && ok "Snapshot $SNAP angelegt" || bad "Snapshot nicht anlegbar"
curl -sk "$BASE_URL/repo/snap/$SNAP/ota/dists/ota/main/binary-amd64/Packages" | grep -q "^Package: $PAKET" \
  && ok "Unter snap/$SNAP/ abrufbar, mit dem eigenen Paket" || bad "Snapshot nicht veröffentlicht"
[ "$(api -H 'Content-Type: application/json' -X POST "$BASE_URL/api/paketquellen/snapshots" \
     -d '{"name":"../boese"}' -o /dev/null -w '%{http_code}')" = "422" ] \
  && ok "Ungültiger Name: 422" || bad "Ungültiger Name angenommen"
einstellen "{\"modus\":\"zuerst\",\"bau_snapshot\":\"$SNAP\",\"alter_gelb\":7,\"alter_rot\":30}" >/dev/null
[ "$(api -X DELETE -o /dev/null -w '%{http_code}' "$BASE_URL/api/paketquellen/snapshots/$SNAP")" = "409" ] \
  && ok "Gegen ihn wird gebaut — Löschen verweigert (409)" || bad "Bau-Snapshot ließ sich löschen"

# Der Bildbauer: dasselbe Skript wie im Arbeitsplatz, am Anfang ein-, am Ende
# ausgetragen — das fertige Image trägt keine Spur der Anlage.
DOCKERFILE=$(docker exec -i ota-agent python - <<PY 2>&1
import json, urllib.request
from otaagent import builder
quellen = json.loads(urllib.request.urlopen(urllib.request.Request(
    "http://repo:8200/quellen", headers={"X-Agent-Token": __import__("os").environ["OTA_AGENT_TOKEN"]})).read())
repo = {"modus": "zuerst", "quellen": quellen["quellen"], "schluessel": quellen["schluessel"], "ca": ""}
print(builder.render_dockerfile(base_image="$IMAGE", apt_packages=["$PAKET"], vscode_extensions=[],
      setup_script="", start_command="", repo=repo, repo_snapshot="$SNAP"))
PY
)
EIN=$(grep -n "base64 -d | sh" <<<"$DOCKERFILE" | head -1 | cut -d: -f1)
APT=$(grep -n "apt-get install" <<<"$DOCKERFILE" | head -1 | cut -d: -f1)
AUS=$(grep -n "base64 -d | sh" <<<"$DOCKERFILE" | tail -1 | cut -d: -f1)
[ -n "$EIN" ] && [ -n "$APT" ] && [ "$EIN" -lt "$APT" ] && [ "$APT" -lt "$AUS" ] \
  && ok "Bildbauer: eintragen → apt-get install → austragen" \
  || bad "Bildbauer: Reihenfolge stimmt nicht ($EIN/$APT/$AUS) $(head -c 300 <<<"$DOCKERFILE")"
# Das Skript trägt die Quellen selbst noch einmal base64-verpackt — alle
# Blöcke auspacken, zwei Ebenen tief.
EINSKRIPT=$(grep "base64 -d | sh" <<<"$DOCKERFILE" | head -1 | python3 -c '
import base64, re, sys
text = sys.stdin.read()
for _ in range(2):
    for blk in re.findall(r"[A-Za-z0-9+/=]{40,}", text):
        try:
            text += "\n" + base64.b64decode(blk).decode()
        except Exception:
            pass
print(text)')
grep -q "snap/$SNAP/" <<<"$EINSKRIPT" && ok "Bildbauer baut gegen den festgehaltenen Stand" \
  || bad "Bau-Snapshot nicht im Skript"
einstellen "$VORHER" >/dev/null

# ---------------------------------------------------------- Arbeitsplatz
echo
echo "Debian-13-Arbeitsplatz"
neu_vorlage() {  # NAME IMAGE KLASSE
  api -H 'Content-Type: application/json' -X POST "$BASE_URL/api/templates" -d "{
    \"friendly_name\": \"$1\", \"image_ref\": \"$2\", \"cores\": 1,
    \"memory_bytes\": 2147483648, \"klasse\": \"$3\", \"platz_grenze_gb\": 20,
    \"stream_engine\": \"selkies\", \"mode\": \"workspace\", \"persistence_scope\": \"template\"}" \
    | jqp "d['id']"
}
starten() { api -H 'Content-Type: application/json' -X POST "$BASE_URL/api/sessions" -d "{\"template_id\":\"$1\"}"; }

einstellen "{\"modus\":\"zuerst\",\"bau_snapshot\":\"\",\"alter_gelb\":7,\"alter_rot\":30}" >/dev/null
TID=$(neu_vorlage "Prüfung Paketquelle" "$IMAGE" standard)
START=$(starten "$TID")
SID=$(jqp "d['id']" <<<"$START")
if [ "$(jqp "d['status']" <<<"$START")" != "running" ]; then
  bad "Start scheiterte: $(jqp "d.get('detail')" <<<"$START")"
else
  CN="ota-s-${SID:0:12}"
  als_root "$CN" 'test -s /etc/apt/sources.list.d/00-ota-repo.sources && test -s /etc/apt/keyrings/ota-repo.asc' >/dev/null \
    && ok "Quelle und Schlüssel eingetragen" || bad "Nicht eingetragen"
  als_root "$CN" 'grep -q "Pin-Priority: 900" /etc/apt/preferences.d/ota-repo' >/dev/null \
    && ok "Betriebsart zuerst: eigene Quelle bevorzugt (900)" || bad "Kein Vorrang eingetragen"
  UPD=$(als_root "$CN" 'apt-get update 2>&1')
  grep -q "/repo/ota ota InRelease" <<<"$UPD" && ! grep -qE "^(E|W): .*ota-repo|NO_PUBKEY" <<<"$UPD" \
    && ok "apt-get update: eigene Quelle signiert und vertraut (OTA-CA)" \
    || bad "apt-get update: $(grep -E '^(E|W):' <<<"$UPD" | head -2)"
  INST=$(als_root "$CN" "DEBIAN_FRONTEND=noninteractive apt-get install -y $PAKET 2>&1; cat /usr/share/$PAKET/marke")
  grep -q "von-hier-$$" <<<"$INST" && ok "Eigenes Paket installiert" || bad "Eigenes Paket fehlt: $(tail -2 <<<"$INST")"
  grep -q "/repo/" <<<"$(als_root "$CN" "apt-get install --reinstall -y --print-uris hello 2>&1")" \
    && ok "Debian-Paket kommt aus dem Spiegel, nicht von deb.debian.org" \
    || info "hello nicht im Spiegel (OTA_REPO_FILTER?) — übersprungen"
  api -X DELETE "$BASE_URL/api/sessions/$SID" >/dev/null; SID=""

  einstellen "{\"modus\":\"nur\",\"bau_snapshot\":\"\",\"alter_gelb\":7,\"alter_rot\":30}" >/dev/null
  START=$(starten "$TID"); SID=$(jqp "d['id']" <<<"$START"); CN="ota-s-${SID:0:12}"
  NUR=$(als_root "$CN" 'ls /etc/apt/sources.list.d/; apt-get update 2>&1 | grep -c deb.debian.org')
  grep -q "debian.sources.ota-aus" <<<"$NUR" && [ "$(tail -1 <<<"$NUR")" = "0" ] \
    && ok "Betriebsart nur: Internetquellen abgeschaltet, kein Ruf zu deb.debian.org" \
    || bad "Betriebsart nur: $NUR"
  api -X DELETE "$BASE_URL/api/sessions/$SID" >/dev/null; SID=""
  einstellen "$VORHER" >/dev/null
fi

# ---------------------------------------------------------- Kein Debian 13
echo
echo "Kein Debian 13"
FREMD=""
for i in ubuntu:latest ubuntu:24.04 kasmweb/vs-code:1.18.0-rolling-weekly; do
  docker image inspect "$i" >/dev/null 2>&1 && { FREMD="$i"; break; }
done
if [ -z "$FREMD" ]; then
  info "kein Ubuntu-Image vorhanden — übersprungen"
else
  docker exec ota-agent python -c "
from otaagent.paketquelle import einrichten_skript
print(einrichten_skript({'modus':'nur','quellen':[{'prefix':'ota','dist':'ota','comp':'main'}],'schluessel':'x','ca':''}))" \
    > "$TMP/skript.sh"
  AUS=$(docker run --rm -u 0 --entrypoint sh -v "$TMP/skript.sh:/s.sh:ro" "$FREMD" -c \
    'A=$(ls /etc/apt/sources.list.d | md5sum); sh /s.sh; B=$(ls /etc/apt/sources.list.d | md5sum); [ "$A" = "$B" ] && echo UNVERAENDERT' 2>&1)
  grep -q "kein Debian 13" <<<"$AUS" && grep -q UNVERAENDERT <<<"$AUS" \
    && ok "$FREMD: nichts eingetragen, nichts abgeschaltet" || bad "$FREMD: $AUS"
fi

# ---------------------------------------------------------- Root-Fortsetzen
echo
echo "Root-Arbeitsplatz: Fortsetzen"
if ! docker info 2>/dev/null | grep -q sysbox-runc || ! docker image inspect "$ROOT_IMAGE" >/dev/null 2>&1; then
  info "Sysbox oder $ROOT_IMAGE fehlt — übersprungen"
else
  RTID=$(neu_vorlage "Prüfung Paketquelle Root" "$ROOT_IMAGE" root)
  START=$(starten "$RTID"); RSID=$(jqp "d['id']" <<<"$START"); RCN="ota-s-${RSID:0:12}"
  als_root "$RCN" 'test -s /etc/apt/sources.list.d/00-ota-repo.sources' >/dev/null \
    && ok "Beim Start eingetragen" || bad "Beim Start nicht eingetragen"
  api -X DELETE "$BASE_URL/api/sessions/$RSID" >/dev/null   # = anhalten
  einstellen "{\"modus\":\"aus\",\"bau_snapshot\":\"\",\"alter_gelb\":7,\"alter_rot\":30}" >/dev/null
  starten "$RTID" >/dev/null                                   # = fortsetzen
  als_root "$RCN" 'test -e /etc/apt/sources.list.d/00-ota-repo.sources || echo WEG' | grep -q WEG \
    && ok "Fortsetzen nimmt die aktuelle Einstellung (aus → ausgetragen)" \
    || bad "Fortsetzen hat die alte Quelle stehen lassen"
  einstellen "$VORHER" >/dev/null
fi

echo
printf '  bestanden: %d   fehlgeschlagen: %d\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
