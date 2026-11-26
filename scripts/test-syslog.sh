#!/usr/bin/env bash
# Prüft „Protokoll an Syslog“ (Handbuch Kapitel 11):
#
#   * Falsche Eingaben werden abgelehnt; die Testnachricht meldet, was fehlt.
#   * TCP mit Länge (RFC 6587), Zeilenumbruch, UDP und TLS mit eigener CA
#     kommen an, im Format RFC 5424, mit dem Eintrag als JSON.
#   * „Ohne Alltag“ hält erfolgreiche Anmeldungen zurück.
#   * Fällt der Server aus, geht nichts verloren: Was in der Zeit ins
#     Protokoll kam, folgt, sobald er wieder antwortet — genau einmal.
#   * Ein Eintrag, dessen Transaktion später fertig wurde (ältere Zeit als
#     ein schon gesendeter), kommt trotzdem an.
#   * Ein falsches CA-Zertifikat wird erkannt.
#
# Der Syslog-Server ist ein kleiner Lauscher im API-Container (127.0.0.1),
# den die Prüfung selbst startet und beendet.
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
LAUF="$(date +%s)$$"
LOG=/tmp/ota-syslog-pruef.log

api()  { curl -sk -b "$TMP/admin.jar" -c "$TMP/admin.jar" "$@"; }
code() { curl -sk -o /dev/null -w '%{http_code}' -b "$TMP/admin.jar" "$@"; }
jqp()  { python3 -c "import sys,json;d=json.load(sys.stdin);print($1)" 2>/dev/null; }
sql()  { docker exec ota-db psql -U ota -d ota -tAc "$1"; }
setze() { api -X PUT "$BASE/api/admin/syslog" -H 'Content-Type: application/json' -d "$1"; }
testen() { api -X POST "$BASE/api/admin/syslog/test" -H 'Content-Type: application/json' -d "$1"; }
eintrag() {  # eintrag <aktion> <marke> — ein Protokolleintrag, wie ihn die API schreibt
  docker exec ota-api python -c "
from ota.db import SessionLocal
from ota import audit
with SessionLocal() as db:
    audit.record(db, '$1', object_type='pruef', object_id='syslog', marke='$2')
    db.commit()"
}
empfangen() { docker exec ota-api sh -c "cat $LOG 2>/dev/null"; }
anzahl() { docker exec ota-api sh -c "grep -o '$1' $LOG 2>/dev/null | wc -l"; }
warte_auf() {  # warte_auf <marke> — bis zu 20 s
  for _ in $(seq 1 20); do
    [ "$(anzahl "$1")" -ge 1 ] && return 0
    sleep 1
  done
  return 1
}

docker exec -i ota-api sh -c 'cat > /tmp/ota-syslog-lauscher.py' <<'PY'
import socket, ssl, sys, threading
art, port, ziel = sys.argv[1], int(sys.argv[2]), sys.argv[3]
def schreiben(b):
    with open(ziel, "ab") as fh:
        fh.write(b)
if art == "udp":
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", port))
    while True:
        schreiben(s.recv(65536) + b"\n")
s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("127.0.0.1", port)); s.listen(5)
ctx = None
if art == "tls":
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain("/tmp/ota-syslog-pruef.crt", "/tmp/ota-syslog-pruef.key")
def bedienen(c):
    try:
        if ctx:
            c = ctx.wrap_socket(c, server_side=True)
        while True:
            b = c.recv(65536)
            if not b:
                break
            schreiben(b)
    except Exception:
        pass
while True:
    c, _ = s.accept()
    threading.Thread(target=bedienen, args=(c,), daemon=True).start()
PY
lauscher() { docker exec -d ota-api python /tmp/ota-syslog-lauscher.py "$1" "$2" "$LOG"; sleep 1; }
lauscher_aus() {
  # Nur die eigenen Lauscher: an ihrem Skriptnamen, über /proc statt pkill -f.
  docker exec ota-api sh -c 'for p in /proc/[0-9]*; do
    grep -qs "ota-syslog-lauscher" "$p/cmdline" && kill "${p#/proc/}" 2>/dev/null; done; true'
  sleep 1
}

VORHER=""
aufraeumen() {
  lauscher_aus
  if [ -n "$VORHER" ]; then
    sql "UPDATE settings SET value = '$VORHER' WHERE key = 'syslog.ziel'" >/dev/null
  else
    sql "DELETE FROM settings WHERE key IN ('syslog.ziel', 'syslog.stand')" >/dev/null
  fi
  docker exec -u 0 ota-api sh -c "rm -f $LOG /tmp/ota-syslog-lauscher.py /tmp/ota-syslog-pruef.crt /tmp/ota-syslog-pruef.key"
  rm -rf "$TMP"
}
trap aufraeumen EXIT

echo "Protokoll an Syslog"
curl -sk -c "$TMP/admin.jar" -o /dev/null -X POST "$BASE/api/auth/login" -H 'Content-Type: application/json' \
  -d "{\"username\":\"$ADMIN\",\"password\":\"$ADMIN_PW\"}"
VORHER=$(sql "SELECT value FROM settings WHERE key = 'syslog.ziel'")
expect "False" "$(api "$BASE/api/admin/syslog" | jqp "d['an']")" "Ab Werk ausgeschaltet"

expect "400" "$(code -X PUT "$BASE/api/admin/syslog" -H 'Content-Type: application/json' -d '{"an":true,"host":""}')" \
  "Einschalten ohne Server wird abgelehnt"
expect "400" "$(code -X PUT "$BASE/api/admin/syslog" -H 'Content-Type: application/json' -d '{"host":"tcp://x:514"}')" \
  "Server mit Schema und Port wird abgelehnt"
expect "400" "$(code -X PUT "$BASE/api/admin/syslog" -H 'Content-Type: application/json' -d '{"port":70000}')" \
  "Port außerhalb 1–65535 wird abgelehnt"
expect "400" "$(code -X PUT "$BASE/api/admin/syslog" -H 'Content-Type: application/json' -d '{"protokoll":"http"}')" \
  "Unbekanntes Protokoll wird abgelehnt"
expect "400" "$(code -X PUT "$BASE/api/admin/syslog" -H 'Content-Type: application/json' -d '{"ca":"kein zertifikat"}')" \
  "Kein PEM als CA wird abgelehnt"
expect "401" "$(curl -sk -o /dev/null -w '%{http_code}' "$BASE/api/admin/syslog")" "Nur mit Anmeldung"

T=$(testen '{"host":"127.0.0.1","port":5599,"protokoll":"tcp"}')
expect "False" "$(jqp "d['ok']" <<<"$T")" "Testnachricht ohne Server: nicht gesendet"
grep -q "abgelehnt" <<<"$(jqp "d['fehler']" <<<"$T")" && ok "… mit verständlichem Grund" \
  || bad "… mit verständlichem Grund — $(jqp "d['fehler']" <<<"$T")"

# --- TCP, Länge
lauscher tcp 5514
T=$(testen '{"host":"127.0.0.1","port":5514,"protokoll":"tcp","rahmung":"laenge"}')
expect "True" "$(jqp "d['ok']" <<<"$T")" "Testnachricht über TCP angenommen"
warte_auf "syslog.test" && ok "… und angekommen" || bad "… und angekommen"

R=$(setze '{"an":true,"host":"127.0.0.1","port":5514,"protokoll":"tcp","rahmung":"laenge","facility":"authpriv","absender":"ota-pruef","umfang":"ohne_alltag"}')
expect "True" "$(jqp "d['an']" <<<"$R")" "Einschalten"
eintrag "login.ok" "alltag-$LAUF"
eintrag "pruef.syslog" "tcp-$LAUF"
warte_auf "tcp-$LAUF" && ok "Neuer Protokolleintrag kommt an" || bad "Neuer Protokolleintrag kommt an"
expect "0" "$(anzahl "alltag-$LAUF")" "Ohne Alltag: erfolgreiche Anmeldung bleibt in OTA"
ZEILE=$(empfangen | tr -d '\r' | grep -o "[0-9]* <85>1 [^ ]* ota-pruef ota - pruef.syslog - {[^}]*tcp-$LAUF" | head -1)
[ -n "$ZEILE" ] && ok "RFC 5424 mit Länge davor, Facility authpriv, Absender, Aktion als MSGID" \
  || bad "RFC 5424 mit Länge davor — $(empfangen | tail -c 300)"
warte_auf "syslog.eingestellt" && ok "Die Änderung der Einstellung selbst geht mit" \
  || bad "Die Änderung der Einstellung selbst geht mit"
expect "True" "$(sql "SELECT detail->>'ca' = 'false' FROM audit_log WHERE action = 'syslog.eingestellt' ORDER BY ts DESC LIMIT 1" | sed 's/t/True/;s/f/False/')" \
  "Im Protokoll steht nur, ob es eine CA gibt"

# --- Ausfall
lauscher_aus
eintrag "pruef.syslog" "ausfall-$LAUF"
sleep 8
S=$(api "$BASE/api/admin/syslog")
[ "$(jqp "d['lage']['fehler'] is not None" <<<"$S")" = "True" ] && ok "Ausfall wird angezeigt" \
  || bad "Ausfall wird angezeigt — $(jqp "d['lage']" <<<"$S")"
[ "$(jqp "d['rueckstand']" <<<"$S")" -ge 1 ] 2>/dev/null && ok "… mit Rückstand" || bad "… mit Rückstand"
# Ein Eintrag mit älterer Zeit, als die Transaktion lange lief:
docker exec ota-db psql -U ota -d ota -qc "INSERT INTO audit_log (id, ts, action, object_type, detail)
  VALUES (gen_random_uuid(), now() - interval '50 seconds', 'pruef.syslog', 'pruef', '{\"marke\": \"spaet-$LAUF\"}')" >/dev/null
lauscher tcp 5514
warte_auf "ausfall-$LAUF" && ok "Nach dem Ausfall kommt nach, was fehlte" || bad "Nach dem Ausfall kommt nach, was fehlte"
warte_auf "spaet-$LAUF" && ok "Auch ein Eintrag mit älterer Zeit" || bad "Auch ein Eintrag mit älterer Zeit"
sleep 7
expect "1" "$(anzahl "ausfall-$LAUF")" "Genau einmal, nicht doppelt"
expect "1" "$(anzahl "tcp-$LAUF")" "Auch früher Gesendetes nicht noch einmal"
expect "None" "$(api "$BASE/api/admin/syslog" | jqp "d['lage']['fehler']")" "Fehler verschwindet wieder"

# --- Zeilenumbruch
setze '{"rahmung":"zeilenumbruch"}' >/dev/null
eintrag "pruef.syslog" "zeile-$LAUF"
warte_auf "zeile-$LAUF" && ok "TCP mit Zeilenumbruch" || bad "TCP mit Zeilenumbruch"
empfangen | grep -q "^<85>1 .*zeile-$LAUF" && ok "… ohne Länge davor" || bad "… ohne Länge davor"
lauscher_aus

# --- UDP
lauscher udp 5515
setze '{"protokoll":"udp","port":5515,"umfang":"alle"}' >/dev/null
eintrag "login.ok" "udp-alltag-$LAUF"
eintrag "pruef.syslog" "udp-$LAUF"
warte_auf "udp-$LAUF" && ok "UDP kommt an" || bad "UDP kommt an"
warte_auf "udp-alltag-$LAUF" && ok "Umfang „alles“: auch die erfolgreiche Anmeldung" \
  || bad "Umfang „alles“: auch die erfolgreiche Anmeldung"
lauscher_aus

# --- TLS mit eigener CA
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj "/CN=localhost" -addext "subjectAltName=DNS:localhost" \
  -keyout "$TMP/k.pem" -out "$TMP/c.pem" >/dev/null 2>&1
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj "/CN=localhost" -addext "subjectAltName=DNS:localhost" \
  -keyout "$TMP/k2.pem" -out "$TMP/fremd.pem" >/dev/null 2>&1
docker cp "$TMP/c.pem" ota-api:/tmp/ota-syslog-pruef.crt >/dev/null
docker cp "$TMP/k.pem" ota-api:/tmp/ota-syslog-pruef.key >/dev/null
docker exec -u 0 ota-api chmod 644 /tmp/ota-syslog-pruef.crt /tmp/ota-syslog-pruef.key
lauscher tls 6514
CA=$(python3 -c 'import json,sys;print(json.dumps(open(sys.argv[1]).read()))' "$TMP/c.pem")
FREMD=$(python3 -c 'import json,sys;print(json.dumps(open(sys.argv[1]).read()))' "$TMP/fremd.pem")
T=$(testen "{\"host\":\"localhost\",\"port\":6514,\"protokoll\":\"tls\",\"ca\":$FREMD}")
expect "False" "$(jqp "d['ok']" <<<"$T")" "TLS mit falscher CA: abgelehnt"
grep -q "Zertifikat" <<<"$(jqp "d['fehler']" <<<"$T")" && ok "… weil das Zertifikat nicht passt" \
  || bad "… weil das Zertifikat nicht passt — $(jqp "d['fehler']" <<<"$T")"
setze "{\"host\":\"localhost\",\"port\":6514,\"protokoll\":\"tls\",\"ca\":$CA}" >/dev/null
eintrag "pruef.syslog" "tls-$LAUF"
warte_auf "tls-$LAUF" && ok "TLS mit eigener CA kommt an" || bad "TLS mit eigener CA kommt an"

R=$(setze '{"an":false}')
expect "False" "$(jqp "d['an']" <<<"$R")" "Ausschalten"

echo
echo "Ergebnis: $pass bestanden, $fail fehlgeschlagen"
[ "$fail" -eq 0 ]
