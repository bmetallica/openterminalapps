#!/usr/bin/env bash
# Prüft OTA-Git (Handbuch Kapitel 27, 2026-10-21).
#
#   * Einschalten im Menü: Forgejo läuft unter der Subdomain hinter Traefik,
#     mit Zertifikat der OTA-CA. OTA selbst bleibt, wie es ist. Die Eingänge
#     für Arbeitsplätze (443, 2222) sind auf dem Host nicht veröffentlicht.
#   * Anmeldung über Keycloak, nur für berechtigte Gruppen; das Konto legt
#     OTA vorher an, die erste Anmeldung verknüpft es. OTA-Admins sind dort
#     Admins. Wer die Gruppe verliert oder deaktiviert wird, ist gesperrt.
#   * Im Arbeitsplatz: clone/commit/push ohne Passwort, Name aus OTA, die
#     eigene .gitconfig gewinnt, ein fremder Server bekommt nichts, SSH über
#     2222 geht. Endet der Arbeitsplatz, ist das Token widerrufen. Ein
#     Root-Arbeitsplatz bekommt beim Fortsetzen ein neues. Die Vorlage kann
#     es abschalten.
#   * Eine andere Subdomain: Forgejo zieht um. Ausschalten hält an, Daten
#     bleiben. Ein Reverse Proxy davor (nginx) erreicht Git mit Host und SNI.
#   * Die Sicherung enthält Datenbank und Repositories.
#
# Stellt am Ende her, was vorher eingestellt war, und räumt die Prüfkonten,
# -gruppen, -vorlagen und -repositories ab. Forgejo, seine Datenbank und das
# Volume bleiben (Ausschalten löscht nie).
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
[ -f "$ROOT/deploy/.env" ] && [ -z "${OTA_TEST_ADMIN_PW:-}" ] && { set -a; . "$ROOT/deploy/.env"; set +a; }

pass=0; fail=0
ok()  { printf '  \033[32m✓\033[0m %s\n' "$1"; pass=$((pass+1)); }
bad() { printf '  \033[31m✗\033[0m %s\n' "$1"; fail=$((fail+1)); }
expect() { if [ "$2" = "$1" ]; then ok "$3 ($2)"; else bad "$3 — erwartet $1, bekommen $2"; fi; }

B="${OTA_BASE:-https://192.168.66.224:8443}"
CA="$ROOT/deploy/certs/ota-ca.crt"
TMP="$(mktemp -d)"
ADMIN="${OTA_TEST_ADMIN:-notfall}"
ADMIN_PW="${OTA_TEST_ADMIN_PW:?OTA_TEST_ADMIN_PW fehlt}"
DOMAIN="git.ota.test"
DOMAIN2="git2.ota.test"
PW="Git-Pruef-2026!x"
MIT="ota-pruef-git"; OHNE="ota-pruef-nogit"
PROXY_CN="ota-pruef-git-proxy"; PROXY_BILD="nginx:1.27-alpine"

api() { curl -sk -b "$TMP/a.jar" -c "$TMP/a.jar" -H 'Content-Type: application/json' "$@"; }
jqp() { python3 -c "import sys,json;d=json.load(sys.stdin);print($1)" 2>/dev/null; }
uid() { api "$B/api/admin/users" | jqp "next((u['id'] for u in d if u['username'] == '$1'), '')"; }
gid() { api "$B/api/admin/groups" | jqp "next((g['id'] for g in d if g['name'] == '$1'), '')"; }
fj() {  # fj <python-ausdruck mit r = httpx-Antwort> <methode> <pfad> [json] — Forgejo-API als ota-admin
  docker exec -i -e M="$2" -e P="$3" -e J="${4:-}" ota-api python - "$1" <<'PY'
import httpx, json, os, sys
a = ("ota-admin", os.environ["OTA_GIT_ADMIN_PW"])
r = httpx.request(os.environ["M"], "http://ota-git:3000/api/v1" + os.environ["P"], auth=a,
                  json=json.loads(os.environ["J"]) if os.environ["J"] else None, timeout=20)
print(eval(sys.argv[1]))
PY
}
fj_nutzer() { fj "next((str(u['$2']) for u in r.json() if u['login'] == '$1'), 'fehlt')" GET "/admin/users?limit=200"; }
traefik_ip() { docker inspect ota-traefik -f '{{(index .NetworkSettings.Networks "ota_public").IPAddress}}'; }
sso() {  # sso <name> [domain] -> JSON von git_anmelden.py, frische SSO-Sitzung
  rm -f "$TMP/$1.jar"
  python3 "$ROOT/scripts/kc_anmelden.py" "$B" "$1" "$PW" "$TMP/$1.jar" >/dev/null 2>&1
  python3 "$ROOT/scripts/git_anmelden.py" "${2:-$DOMAIN}" "$(traefik_ip)" "$TMP/$1.jar"
}
container_von() {
  local c=""
  for _ in $(seq 1 60); do
    c=$(docker ps --filter "label=ota.session_id=$1" --filter status=running --format '{{.Names}}' | head -1)
    [ -n "$c" ] && break; sleep 3
  done
  echo "$c"
}
starten() {  # starten <template-id> -> session-id
  local sid=""
  for _ in 1 2 3; do
    sid=$(api -X POST "$B/api/sessions" -d "{\"template_id\":\"$1\"}" | jqp "d.get('id','')")
    [ -n "$sid" ] && break; sleep 5
  done
  echo "$sid"
}
im() { docker exec -u 1000 -w /tmp -e GIT_TERMINAL_PROMPT=0 "$C" sh -c "$1"; }
token_gilt() {  # token_gilt <token> -> HTTP-Code
  docker exec -e T="$1" ota-api python -c "import httpx,os;print(httpx.get('http://ota-git:3000/api/v1/user',headers={'Authorization':'token '+os.environ['T']}).status_code)"
}

VORHER=""; SID=""; RSID=""; RTID=""; T=""; TVORHER=""; BACKUP_ID=""
aufraeumen() {
  echo
  echo "Aufräumen"
  [ -n "$SID" ] && api -X DELETE "$B/api/sessions/$SID" >/dev/null
  if [ -n "$RSID" ]; then
    api -X DELETE "$B/api/sessions/$RSID" >/dev/null
    api -X DELETE "$B/api/admin/arbeitsplaetze/$RSID" >/dev/null
  fi
  [ -n "$RTID" ] && api -X DELETE "$B/api/templates/$RTID" >/dev/null
  [ -n "$TVORHER" ] && api -X PUT "$B/api/templates/$T" -d @"$TMP/vorlage.json" >/dev/null
  [ -n "$BACKUP_ID" ] && api -X DELETE "$B/api/backups/$BACKUP_ID" >/dev/null
  docker rm -f "$PROXY_CN" >/dev/null 2>&1
  docker rmi "$PROXY_BILD" >/dev/null 2>&1
  fj "r.status_code" DELETE "/repos/$ADMIN/pruef-repo" >/dev/null 2>&1
  for k in $(fj "' '.join(str(k['id']) for k in r.json() if k['title'] == 'ota-pruef')" GET "/users/$ADMIN/keys" 2>/dev/null); do
    fj "r.status_code" DELETE "/admin/users/$ADMIN/keys/$k" >/dev/null 2>&1
  done
  for n in "$MIT" "$OHNE"; do
    u=$(uid "$n"); [ -n "$u" ] && api -X DELETE "$B/api/admin/users/$u" >/dev/null
    fj "r.status_code" DELETE "/admin/users/$n?purge=true" >/dev/null 2>&1
  done
  for g in git-pruef git-pruef-admin; do
    x=$(gid "$g"); [ -n "$x" ] && api -X DELETE "$B/api/admin/groups/$x" >/dev/null
  done
  if [ -n "$VORHER" ]; then
    api -X PUT "$B/api/admin/git" -d "$(jqp "json.dumps({k: d[k] for k in ('domain','gruppen','ota_url')})" <<<"$VORHER")" >/dev/null
    if [ "$(jqp "str(d['an'])" <<<"$VORHER")" = "True" ]; then
      api -X POST "$B/api/admin/git/an" >/dev/null
    else
      api -X POST "$B/api/admin/git/aus" >/dev/null
    fi
    ok "Einstellungen von OTA-Git wie vorher (an: $(jqp "d['an']" <<<"$VORHER"))"
  fi
  rm -rf "$TMP"
  echo
  printf '  bestanden: %d   fehlgeschlagen: %d\n' "$pass" "$fail"
  [ "$fail" -eq 0 ] || exit 1
}
trap aufraeumen EXIT

echo "OTA-Git gegen $B"
curl -sk -c "$TMP/a.jar" -o /dev/null -X POST "$B/api/auth/login" -H 'Content-Type: application/json' \
  -d "{\"username\":\"$ADMIN\",\"password\":\"$ADMIN_PW\"}"
VORHER=$(api "$B/api/admin/git")
[ -n "$(jqp "d['an']" <<<"$VORHER")" ] || { bad "Kein Zugriff auf /api/admin/git"; VORHER=""; exit 1; }
# Reste eines abgebrochenen Laufs, damit Konten und Gruppen frisch entstehen.
for n in "$MIT" "$OHNE"; do u=$(uid "$n"); [ -n "$u" ] && api -X DELETE "$B/api/admin/users/$u" >/dev/null; done
for g in git-pruef git-pruef-admin; do x=$(gid "$g"); [ -n "$x" ] && api -X DELETE "$B/api/admin/groups/$x" >/dev/null; done

# ------------------------------------------------------------------ Einschalten
echo
echo "Einschalten"
G=$(api -X POST "$B/api/admin/groups" -d '{"name":"git-pruef","permissions":[]}' | jqp "d['id']")
api -X PUT "$B/api/admin/git" -d "{\"domain\":\"$DOMAIN\",\"ota_url\":\"$B\",\"gruppen\":[\"$G\"]}" >/dev/null
R=$(api -X POST "$B/api/admin/git/an")
expect "True" "$(jqp "str(d['an'])" <<<"$R")" "OTA-Git ist an"
expect "healthy" "$(jqp "d['dienst'].get('gesund')" <<<"$R")" "Forgejo meldet sich gesund"
CODE=$(curl -s --cacert "$CA" --resolve "$DOMAIN:8443:192.168.66.224" "https://$DOMAIN:8443/user/login" -o "$TMP/login.html" -w '%{http_code}')
expect "200" "$CODE" "Unter der Subdomain antwortet Forgejo, Zertifikat von der OTA-CA"
grep -q "user/oauth2/ota" "$TMP/login.html" && ok "… mit der Anmeldung über Keycloak" || bad "Kein Knopf für die Anmeldung über Keycloak"
expect "200" "$(curl -sk -o /dev/null -w '%{http_code}' "$B/healthz")" "OTA selbst bleibt erreichbar"
expect "401" "$(curl -sk -o /dev/null -w '%{http_code}' "$B/api/auth/me")" "… und /api gehört weiter OTA"
PORTS=$(docker port ota-traefik | grep -cE '^(443|2222)/')
expect "0" "$PORTS" "Die Eingänge für Arbeitsplätze (443, 2222) sind auf dem Host nicht veröffentlicht"

# ------------------------------------------------------------------ Konten
echo
echo "Konten und Anmeldung"
api -X POST "$B/api/admin/users" -d "{\"username\":\"$MIT\",\"email\":\"$MIT@ota.invalid\",\"password\":\"$PW\",\"passwort_wechseln\":false,\"group_ids\":[\"$G\"]}" >/dev/null
api -X POST "$B/api/admin/users" -d "{\"username\":\"$OHNE\",\"email\":\"$OHNE@ota.invalid\",\"password\":\"$PW\",\"passwort_wechseln\":false,\"group_ids\":[]}" >/dev/null
expect "False" "$(fj_nutzer "$MIT" prohibit_login)" "Das Mitglied hat ein Forgejo-Konto, bevor es sich anmeldet"
expect "fehlt" "$(fj_nutzer "$OHNE" login)" "Wer nicht darf, bekommt keines"
R=$(sso "$MIT")
expect "ZUGANG" "$(jqp "d['ergebnis']" <<<"$R")" "Das Mitglied kommt über Keycloak hinein"
expect "$MIT" "$(jqp "d.get('login')" <<<"$R")" "… in sein vorbereitetes Konto (nicht in ein zweites)"
expect "False" "$(jqp "str(d.get('is_admin'))" <<<"$R")" "… ohne Verwaltung"
expect "VERWEIGERT" "$(jqp "d['ergebnis']" <<<"$(sso "$OHNE")")" "Wer nicht in der Gruppe ist, wird von Keycloak abgewiesen"

GA=$(api -X POST "$B/api/admin/groups" -d '{"name":"git-pruef-admin","permissions":["admin"]}' | jqp "d['id']")
U=$(uid "$MIT")
api -X PUT "$B/api/admin/users/$U" -d "{\"username\":\"$MIT\",\"email\":\"$MIT@ota.invalid\",\"is_active\":true,\"group_ids\":[\"$G\",\"$GA\"]}" >/dev/null
expect "True" "$(jqp "str(d.get('is_admin'))" <<<"$(sso "$MIT")")" "OTA-Admin ist in Forgejo Admin"
api -X PUT "$B/api/admin/users/$U" -d "{\"username\":\"$MIT\",\"email\":\"$MIT@ota.invalid\",\"is_active\":true,\"group_ids\":[\"$G\"]}" >/dev/null
expect "False" "$(fj_nutzer "$MIT" is_admin)" "… und verliert es mit der Rolle"

api -X PUT "$B/api/admin/users/$U" -d "{\"username\":\"$MIT\",\"email\":\"$MIT@ota.invalid\",\"is_active\":true,\"group_ids\":[]}" >/dev/null
expect "True" "$(fj_nutzer "$MIT" prohibit_login)" "Aus der Gruppe genommen: in Forgejo gesperrt, nicht gelöscht"
expect "VERWEIGERT" "$(jqp "d['ergebnis']" <<<"$(sso "$MIT")")" "… und Keycloak lässt nicht mehr hinein"
api -X PUT "$B/api/admin/users/$U" -d "{\"username\":\"$MIT\",\"email\":\"$MIT@ota.invalid\",\"is_active\":true,\"group_ids\":[\"$G\"]}" >/dev/null
expect "False" "$(fj_nutzer "$MIT" prohibit_login)" "Wieder in der Gruppe: entsperrt"
api -X PUT "$B/api/admin/users/$U" -d "{\"username\":\"$MIT\",\"email\":\"$MIT@ota.invalid\",\"is_active\":false,\"group_ids\":[\"$G\"]}" >/dev/null
expect "True" "$(fj_nutzer "$MIT" prohibit_login)" "In OTA deaktiviert: gesperrt"

# ------------------------------------------------------------------ Arbeitsplatz
echo
echo "Im Arbeitsplatz"
fj "r.status_code" POST "/admin/users/$ADMIN/repos" '{"name":"pruef-repo","auto_init":true,"private":true}' >/dev/null
T=$(api "$B/api/templates" | jqp "next(t['id'] for t in d if t['is_enabled'] and t['klasse'] == 'standard')")
SID=$(starten "$T"); C=$(container_von "$SID")
[ -n "$C" ] && ok "Arbeitsplatz läuft ($C)" || { bad "Arbeitsplatz kam nicht hoch"; exit 1; }
NETZ_TRAEFIK=$(docker inspect ota-traefik -f "{{(index .NetworkSettings.Networks \"ota-n-${SID:0:12}\").IPAddress}}" 2>/dev/null)
expect "$NETZ_TRAEFIK $DOMAIN # ota-git" "$(docker exec "$C" grep ' # ota-git$' /etc/hosts)" "Die Subdomain zeigt auf Traefik im eigenen Sitzungsnetz"
im "rm -rf pruef-repo; git clone -q https://$DOMAIN/$ADMIN/pruef-repo.git && cd pruef-repo && echo eins > a.txt && git add a.txt && git commit -qm aus-dem-platz && git push -q" \
  && ok "clone, commit und push ohne Passwort" || bad "clone/push scheiterte"
expect "$(api "$B/api/auth/me" | jqp "d.get('display_name') or d['username']")" "$(im 'cd pruef-repo && git log -1 --format=%an')" "Autor ist der Name aus OTA"
expect "Eigener Name" "$(im 'printf "[user]\n\tname = Eigener Name\n" > /tmp/gc; GIT_CONFIG_GLOBAL=/tmp/gc git config user.name')" "Die eigene .gitconfig gewinnt"
FREMD=$(im 'printf "protocol=https\nhost=github.com\n\n" | GIT_ASKPASS=/bin/false git credential fill 2>&1 | grep -c "^password=" || true')
expect "0" "$FREMD" "Ein fremder Server bekommt keine Zugangsdaten"
im 'rm -f /tmp/k /tmp/k.pub; ssh-keygen -q -t ed25519 -N "" -f /tmp/k' && KEY=$(im 'cat /tmp/k.pub')
fj "r.status_code" POST "/admin/users/$ADMIN/keys" "{\"title\":\"ota-pruef\",\"key\":\"$KEY\"}" >/dev/null
im "timeout 20 ssh -i /tmp/k -p 2222 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -T git@$DOMAIN 2>&1" | grep -q "successfully authenticated" \
  && ok "SSH über 2222 aus dem Arbeitsplatz" || bad "SSH aus dem Arbeitsplatz scheiterte"
im "rm -rf /tmp/s; GIT_SSH_COMMAND='ssh -i /tmp/k -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null' git clone -q ssh://git@$DOMAIN:2222/$ADMIN/pruef-repo.git /tmp/s && test -f /tmp/s/a.txt" \
  && ok "git clone über SSH" || bad "git clone über SSH scheiterte"
TOK=$(docker exec "$C" cat /etc/ota-git/token)
expect "200" "$(token_gilt "$TOK")" "Das Token des Arbeitsplatzes gilt"
api -X DELETE "$B/api/sessions/$SID" >/dev/null; SID=""
expect "401" "$(token_gilt "$TOK")" "Arbeitsplatz beendet: Token widerrufen"

echo
echo "Vorlage ohne Git"
api "$B/api/templates" | jqp "json.dumps(next(t for t in d if t['id'] == '$T'))" > "$TMP/vorlage.json"; TVORHER=1
jqp "json.dumps(dict(d, git_vorkonfig=False))" < "$TMP/vorlage.json" > "$TMP/ohne.json"
api -X PUT "$B/api/templates/$T" -d @"$TMP/ohne.json" >/dev/null
SID=$(starten "$T"); C=$(container_von "$SID")
expect "nein" "$(docker exec "$C" sh -c 'test -e /etc/ota-git && echo ja || echo nein')" "Abgeschaltet: nichts eingerichtet"
api -X DELETE "$B/api/sessions/$SID" >/dev/null; SID=""
api -X PUT "$B/api/templates/$T" -d @"$TMP/vorlage.json" >/dev/null; TVORHER=""

# ------------------------------------------------------------------ Root
echo
echo "Root-Arbeitsplatz: anhalten und fortsetzen"
RTID=$(api -X POST "$B/api/templates" -d '{"friendly_name":"Prüfung Git Root","image_ref":"ota/base-desktop-root:1","cores":2,"memory_bytes":4294967296,"klasse":"root","platz_grenze_gb":20,"stream_engine":"selkies","mode":"workspace","persistence_scope":"template"}' | jqp "d['id']")
RSID=$(starten "$RTID"); C=$(container_von "$RSID")
[ -n "$C" ] && ok "Root-Arbeitsplatz läuft" || bad "Root-Arbeitsplatz kam nicht hoch"
# Ein Basisimage von vor dem 2026-10-21 hat kein git (Kapitel 27). Dann wie ein
# Mensch im Root-Arbeitsplatz: nachinstallieren.
docker exec "$C" sh -c 'command -v git >/dev/null || { apt-get update -q >/dev/null 2>&1; apt-get install -y -q git >/dev/null 2>&1; }'
expect "1" "$(docker exec ota-db psql -U ota -tAc "select count(*) from git_tokens where session_id = '$RSID'")" "Das Token ist vermerkt"
im "rm -rf r; git clone -q https://$DOMAIN/$ADMIN/pruef-repo.git r && cd r && echo zwei > b.txt && git add b.txt && git commit -qm root && git push -q" \
  && ok "push aus dem Root-Arbeitsplatz" || bad "push aus dem Root-Arbeitsplatz scheiterte"
TOK=$(docker exec "$C" cat /etc/ota-git/token)
api -X DELETE "$B/api/sessions/$RSID" >/dev/null
expect "401" "$(token_gilt "$TOK")" "Angehalten: Token widerrufen"
starten "$RTID" >/dev/null; C=$(container_von "$RSID")
TOK2=$(docker exec "$C" cat /etc/ota-git/token)
[ -n "$TOK2" ] && [ "$TOK2" != "$TOK" ] && ok "Fortgesetzt: ein neues Token" || bad "Kein neues Token nach dem Fortsetzen"
im "cd r && git pull -q && test -f a.txt" && ok "… und es gilt (pull)" || bad "pull nach dem Fortsetzen scheiterte"

# ------------------------------------------------------------------ Proxy
echo
echo "Hinter einem Reverse Proxy"
openssl req -x509 -newkey rsa:2048 -nodes -keyout "$TMP/p.key" -out "$TMP/p.crt" -days 1 -subj "/CN=$DOMAIN" 2>/dev/null
cat > "$TMP/nginx.conf" <<EOF
events {}
http {
  server {
    listen 8443 ssl;
    ssl_certificate /p/p.crt; ssl_certificate_key /p/p.key;
    location / {
      proxy_pass https://192.168.66.224:8443;
      proxy_set_header Host \$host;
      proxy_ssl_server_name on;
      proxy_ssl_name \$host;
    }
  }
}
EOF
chmod 644 "$TMP"/p.* "$TMP/nginx.conf"
docker run -d --name "$PROXY_CN" -p 127.0.0.1:18444:8443 -v "$TMP/nginx.conf:/etc/nginx/nginx.conf:ro" \
  -v "$TMP:/p:ro" "$PROXY_BILD" >/dev/null 2>&1
sleep 3
curl -sk --resolve "$DOMAIN:18444:127.0.0.1" "https://$DOMAIN:18444/user/login" | grep -q "user/oauth2/ota" \
  && ok "Über den Proxy mit Host und SNI: Forgejo" || bad "Über den Proxy kein Forgejo"
curl -sk --resolve "ota.ota.test:18444:127.0.0.1" "https://ota.ota.test:18444/healthz" -o /dev/null -w '%{http_code}' | grep -q 200 \
  && ok "… und unter einem anderen Namen weiter OTA" || bad "Über den Proxy kein OTA"

# ------------------------------------------------------------------ Subdomain
echo
echo "Andere Subdomain"
api -X PUT "$B/api/admin/users/$U" -d "{\"username\":\"$MIT\",\"email\":\"$MIT@ota.invalid\",\"is_active\":true,\"group_ids\":[\"$G\"]}" >/dev/null
R=$(api -X PUT "$B/api/admin/git" -d "{\"domain\":\"$DOMAIN2\"}")
expect "$DOMAIN2" "$(jqp "d['dienst'].get('domain')" <<<"$R")" "Forgejo läuft unter $DOMAIN2"
expect "ZUGANG" "$(jqp "d['ergebnis']" <<<"$(sso "$MIT" "$DOMAIN2")")" "Anmeldung unter der neuen Subdomain"
api -X PUT "$B/api/admin/git" -d "{\"domain\":\"$DOMAIN\"}" >/dev/null

# ------------------------------------------------------------------ Aus/an
echo
echo "Aus und wieder an"
R=$(api -X POST "$B/api/admin/git/aus")
expect "exited" "$(jqp "d['dienst'].get('container')" <<<"$R")" "Ausgeschaltet: Container angehalten"
expect "False" "$(api "$B/api/webapps" | jqp "str(any(a.get('verwaltet') == 'git' for a in d))")" "… die Kachel ist weg"
R=$(api -X POST "$B/api/admin/git/an")
expect "healthy" "$(jqp "d['dienst'].get('gesund')" <<<"$R")" "Wieder an"
expect "True" "$(fj "str(r.status_code == 200)" GET "/repos/$ADMIN/pruef-repo/contents/b.txt")" "Das Repository samt Push aus dem Root-Arbeitsplatz ist noch da"

# ------------------------------------------------------------------ Sicherung
echo
echo "Sicherung"
R=$(docker exec -w /app -e PYTHONPATH=/app ota-api python -c "
from ota.db import SessionLocal
from ota.routers.backups import run_git_backup
b = run_git_backup(SessionLocal(), 'manual', 'pruef'); print(b.id, b.status, b.path)")
BACKUP_ID=$(cut -d' ' -f1 <<<"$R")
expect "ok" "$(cut -d' ' -f2 <<<"$R")" "Sicherung von OTA-Git"
(set +o pipefail; zstd -dc "$(cut -d' ' -f3 <<<"$R")/daten.tar.zst" | tar t 2>/dev/null | grep -q "pruef-repo.git") \
  && ok "… mit den Repositories" || bad "Repositories fehlen in der Sicherung"
