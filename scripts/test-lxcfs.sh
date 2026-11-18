#!/usr/bin/env bash
# Prüft LXCFS und ota-top (Handbuch Kapitel 11): free, htop und uptime im
# Arbeitsplatz zeigen dessen Grenzen, nicht die des Wirts.
#
#   * Der Agent sieht LXCFS.
#   * Ein normaler Arbeitsplatz: Speicher und Kerne nach seinen Grenzen,
#     ota-top läuft.
#   * Ein Root-Arbeitsplatz (Sysbox), **angelegt ohne LXCFS** — so wie jeder,
#     der vor diesem Update entstand: nach Anhalten und Fortsetzen hat er es,
#     ebenso nach Anhalten und Starten durch die Verwaltung.
#   * Ein neu angelegter Root-Arbeitsplatz hat es von Anfang an und behält es
#     über Anhalten und Fortsetzen.
#
# Ohne LXCFS auf dem Wirt wird übersprungen (sudo scripts/lxcfs-einrichten.sh).
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
[ -f "$ROOT/deploy/.env" ] && { set -a; . "$ROOT/deploy/.env"; set +a; }

pass=0; fail=0
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; pass=$((pass+1)); }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$1"; fail=$((fail+1)); }
expect() { if [ "$2" = "$1" ]; then ok "$3"; else bad "$3 — erwartet $1, bekommen $2"; fi; }

B="${OTA_BASE:-https://127.0.0.1:${OTA_HTTPS_PORT:-8443}}"
TMP="$(mktemp -d)"
ADMIN="${OTA_TEST_ADMIN:-notfall}"
ADMIN_PW="${OTA_TEST_ADMIN_PW:?OTA_TEST_ADMIN_PW fehlt. Trag es in deploy/.env ein.}"
VORLAGE="${OTA_TEST_VORLAGE:-arbeitsplatz}"
ROOT_IMAGE="${OTA_ROOT_TAG:-ota/base-desktop-root:1}"
AUS="${OTA_RUNTIME_ROOT:-/srv/ota/runtime}/lxcfs-aus"

api()  { curl -sk -b "$TMP/a.jar" -c "$TMP/a.jar" -H 'Content-Type: application/json' "$@"; }
jqp()  { python3 -c "import sys,json;d=json.load(sys.stdin);print($1)" 2>/dev/null; }
container_von() {
  local c=""
  for _ in $(seq 1 60); do
    c=$(docker ps --filter "label=ota.session_id=$1" --filter status=running --format '{{.Names}}' | head -1)
    [ -n "$c" ] && break; sleep 3
  done
  echo "$c"
}
# Was der Container sieht: MemTotal in Bytes, Prozessoren in cpuinfo.
sicht() { docker exec "$1" sh -c "awk '/^MemTotal/ {printf \"%.0f\\n\", \$2*1024}' /proc/meminfo; grep -c ^processor /proc/cpuinfo"; }
soll() {  # Grenzen laut Docker: Bytes, Kerne aufgerundet (höchstens die des Wirts)
  docker inspect "$1" -f '{{.HostConfig.Memory}} {{.HostConfig.NanoCpus}}' \
    | awk -v wirt="$(nproc)" '{k=int(($2+999999999)/1e9); if (k>wirt) k=wirt; print $1; print k}'
}
pruefe() {  # pruefe <container> <was>
  local s i
  s=$(soll "$1" | tr '\n' ' '); i=$(sicht "$1" | tr '\n' ' ')
  expect "$s" "$i" "$2: Speicher und Kerne nach den Grenzen ($i)"
}

SID=""; RSID=""; RSID2=""; RTID=""
aufraeumen() {
  rm -f "$AUS"
  [ -n "$SID" ] && api -X DELETE "$B/api/sessions/$SID" >/dev/null 2>&1
  for s in $RSID $RSID2; do api -X DELETE "$B/api/admin/arbeitsplaetze/$s" >/dev/null 2>&1; done
  [ -n "$RTID" ] && api -X DELETE "$B/api/templates/$RTID" >/dev/null 2>&1
  rm -rf "$TMP"
}
trap aufraeumen EXIT

echo "LXCFS und ota-top"
if ! head -1 /var/lib/lxcfs/proc/meminfo >/dev/null 2>&1; then
  echo "  (übersprungen — LXCFS läuft auf diesem Wirt nicht: sudo scripts/lxcfs-einrichten.sh)"
  exit 0
fi
curl -sk -c "$TMP/a.jar" -o /dev/null -X POST "$B/api/auth/login" -H 'Content-Type: application/json' \
  -d "{\"username\":\"$ADMIN\",\"password\":\"$ADMIN_PW\"}"
rm -f "$AUS"

expect "True" "$(docker exec ota-agent python3 -c 'from otaagent import lxcfs; print(lxcfs.verfuegbar())')" \
  "Der Agent sieht LXCFS"

# ------------------------------------------------------------------ normal
echo
echo "Normaler Arbeitsplatz"
T=$(docker exec ota-db psql -U ota -d ota -At -c "select id from templates where slug = '$VORLAGE'")
for _ in 1 2 3; do
  SID=$(api -X POST "$B/api/sessions" -d "{\"template_id\":\"$T\"}" | jqp "d.get('id','')")
  [ -n "$SID" ] && break; sleep 5
done
C=$(container_von "$SID")
if [ -z "$C" ]; then
  bad "Arbeitsplatz $VORLAGE startet nicht"
else
  pruefe "$C" "Normaler Arbeitsplatz"
  docker exec "$C" sh -c 'mount | grep -q "lxcfs on /proc/loadavg"' \
    && ok "Load kommt aus LXCFS" || bad "Load kommt nicht aus LXCFS"
  OT=$(docker exec -u 1000 "$C" ota-top -n 1 2>&1)
  grep -qE "CPU .* (von|of) " <<<"$OT" && ok "ota-top zeigt CPU und Speicher des Arbeitsplatzes" \
    || bad "ota-top: $(head -3 <<<"$OT")"
  api -X DELETE "$B/api/sessions/$SID" >/dev/null; SID=""
fi

# ------------------------------------------------------------------ root
if ! docker info 2>/dev/null | grep -q sysbox-runc || ! docker image inspect "$ROOT_IMAGE" >/dev/null 2>&1; then
  echo
  echo "  (Root-Arbeitsplatz übersprungen — Sysbox oder $ROOT_IMAGE fehlt)"
else
  echo
  echo "Root-Arbeitsplatz von vor LXCFS"
  RTID=$(api -X POST "$B/api/templates" -d "{
    \"friendly_name\": \"Prüfung LXCFS\", \"image_ref\": \"$ROOT_IMAGE\",
    \"cores\": 2, \"memory_bytes\": 3221225472, \"klasse\": \"root\",
    \"platz_grenze_gb\": 20, \"stream_engine\": \"selkies\", \"mode\": \"workspace\",
    \"persistence_scope\": \"template\"}" | jqp "d['id']")
  # So, wie ihn ein OTA ohne LXCFS angelegt hätte.
  touch "$AUS"
  RSID=$(api -X POST "$B/api/sessions" -d "{\"template_id\":\"$RTID\"}" | jqp "d.get('id','')")
  rm -f "$AUS"
  RC=$(container_von "$RSID")
  if [ -z "$RC" ]; then
    bad "Root-Arbeitsplatz startet nicht"
  else
    expect "0" "$(docker inspect "$RC" -f '{{range .Mounts}}{{.Destination}} {{end}}' | grep -c meminfo)" \
      "Angelegt ohne LXCFS-Einhängepunkte (wie ein alter)"
    [ "$(sicht "$RC" | head -1)" != "$(soll "$RC" | head -1)" ] \
      && ok "…und sieht den Speicher des Wirts" || bad "sieht schon seine Grenzen — Test ohne Aussage"
    docker exec "$RC" test -x /usr/local/bin/ota-top && ok "ota-top ist da (Sysbox, über exec)" \
      || bad "ota-top fehlt im Root-Arbeitsplatz"

    api -X DELETE "$B/api/sessions/$RSID" >/dev/null
    expect "exited" "$(docker inspect "$RC" -f '{{.State.Status}}')" "Angehalten"
    R=$(api -X POST "$B/api/sessions" -d "{\"template_id\":\"$RTID\"}" | jqp "d.get('id','')")
    expect "$RSID" "$R" "Fortgesetzt — derselbe Container"
    pruefe "$RC" "Nach dem Fortsetzen"
    docker exec "$RC" sh -c 'cat /proc/meminfo /proc/loadavg /proc/uptime >/dev/null' \
      && ok "Die Dateien lesen sich ohne Fehler" || bad "Lesen scheitert"
    docker exec -u 1000 "$RC" sh -lc 'LC_ALL=C free -b' | awk '/^Mem:/ {print $2}' | grep -qx "$(soll "$RC" | head -1)" \
      && ok "free zeigt die Grenze des Arbeitsplatzes" || bad "free zeigt etwas anderes"

    api -X POST "$B/api/admin/arbeitsplaetze/$RSID/anhalten" >/dev/null
    api -X POST "$B/api/admin/arbeitsplaetze/$RSID/starten" >/dev/null
    pruefe "$RC" "Nach Anhalten und Starten durch die Verwaltung"
    docker restart -t 30 "$RC" >/dev/null
    docker exec ota-agent python3 -c "
import docker; from otaagent import lxcfs
c = docker.from_env().containers.get('$RC'); print(lxcfs.einhaengen(docker.from_env(), c))" >/dev/null
    E=$(docker exec ota-agent python3 -c "
import docker; from otaagent import lxcfs
c = docker.from_env().containers.get('$RC'); print(lxcfs.einhaengen(docker.from_env(), c))")
    expect "schon-da" "$E" "Ein zweites Einhängen tut nichts"
    api -X DELETE "$B/api/admin/arbeitsplaetze/$RSID" >/dev/null; RSID=""
  fi

  echo
  echo "Neuer Root-Arbeitsplatz"
  RSID2=$(api -X POST "$B/api/sessions" -d "{\"template_id\":\"$RTID\"}" | jqp "d.get('id','')")
  RC2=$(container_von "$RSID2")
  if [ -z "$RC2" ]; then
    bad "Neuer Root-Arbeitsplatz startet nicht"
  else
    expect "1" "$(docker inspect "$RC2" -f '{{range .Mounts}}{{.Destination}} {{end}}' | grep -c meminfo)" \
      "LXCFS als Einhängepunkt von Docker"
    pruefe "$RC2" "Neu angelegt"
    api -X DELETE "$B/api/sessions/$RSID2" >/dev/null
    api -X POST "$B/api/sessions" -d "{\"template_id\":\"$RTID\"}" >/dev/null
    pruefe "$RC2" "Nach Anhalten und Fortsetzen"
    K=$(soll "$RC2" | tail -1)
    OT=$(docker exec -u 1000 "$RC2" ota-top -n 1)
    grep -qE "(von|of) ${K}00 %" <<<"$OT" && grep -qE "(zugeteilt|allotted) 2.0 " <<<"$OT" \
      && ok "ota-top: Obergrenze $K Kerne, zugeteilt 2" || bad "ota-top: $(sed -n 3,4p <<<"$OT")"
  fi
fi

echo
echo "  bestanden: $pass   fehlgeschlagen: $fail"
[ "$fail" -eq 0 ]
