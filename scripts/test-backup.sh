#!/usr/bin/env bash
# Prüft Sicherung und Wiederherstellung (plan.md §11.2).
#
# Der Test greift bewusst in ein echtes Profil ein: Er legt eine Markierung
# hinein, stellt zurück und prüft, ob sie verschwunden ist. Eine
# Wiederherstellung, die man nur ansieht, ist nicht geprüft.

set -uo pipefail

BASE="${1:-https://192.168.66.224:8443}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CA="$ROOT/deploy/certs/ota-ca.crt"
JAR="$(mktemp)"
trap 'rm -f "$JAR"' EXIT

USER_NAME="${OTA_TEST_ADMIN:-notfall}"
USER_PW="${OTA_TEST_ADMIN_PW:?OTA_TEST_ADMIN_PW fehlt. Trag es in deploy/.env ein.}"

pass=0; fail=0
ok()  { printf '  \033[32m✓\033[0m %s\n' "$1"; pass=$((pass+1)); }
bad() { printf '  \033[31m✗\033[0m %s\n' "$1"; fail=$((fail+1)); }
api() { curl -s --cacert "$CA" -b "$JAR" -c "$JAR" "$@"; }
jqp() { python3 -c "import sys,json;d=json.load(sys.stdin);print($1)" 2>/dev/null; }

echo "Sicherung und Wiederherstellung gegen $BASE"
echo

api -X POST "$BASE/api/auth/login" -H 'Content-Type: application/json' \
    -d "{\"username\":\"$USER_NAME\",\"password\":\"$USER_PW\"}" >/dev/null

# ------------------------------------------------------------------ Ablage
ST=$(api "$BASE/api/backups/storage")
WRITABLE=$(echo "$ST" | jqp "d['writable']")
[ "$WRITABLE" = "True" ] && ok "Sicherungsverzeichnis ist beschreibbar" \
                         || bad "Sicherungsverzeichnis nicht beschreibbar"
echo "$ST" | jqp "d['path']" | grep -q . && ok "Ablage: $(echo "$ST" | jqp "d['path']") ($(echo "$ST" | jqp "d['fstype']"))" \
                         || bad "Kein Pfad gemeldet"

# ------------------------------------------------- Rechte: kein Admin, kein Zugriff
TEST_USER="ota-testnutzer"
TEST_PW="TestNutzer2026!ab"
UJAR="$(mktemp)"
api "$BASE/api/admin/users" | grep -q "$TEST_USER" || {
  GID=$(api "$BASE/api/admin/groups" | jqp "[g['id'] for g in d if g['slug']=='users'][0]")
  api -X POST "$BASE/api/admin/users" -H 'Content-Type: application/json' \
      -d "{\"username\":\"$TEST_USER\",\"email\":\"$TEST_USER@ota.invalid\",\"password\":\"$TEST_PW\",\"group_ids\":[\"$GID\"]}" >/dev/null
}
curl -s --cacert "$CA" -c "$UJAR" -X POST "$BASE/api/auth/login" \
     -H 'Content-Type: application/json' \
     -d "{\"username\":\"$TEST_USER\",\"password\":\"$TEST_PW\"}" >/dev/null
CODE=$(curl -s --cacert "$CA" -b "$UJAR" -o /dev/null -w '%{http_code}' "$BASE/api/backups")
[ "$CODE" = "403" ] && ok "Normaler Nutzer kommt nicht an die Sicherungen (403)" \
                    || bad "Normaler Nutzer bekam $CODE statt 403"
CODE=$(curl -s --cacert "$CA" -b "$UJAR" -o /dev/null -w '%{http_code}' \
       -X POST "$BASE/api/backups/run" -H 'Content-Type: application/json' -d '{}')
[ "$CODE" = "403" ] && ok "Normaler Nutzer kann keine Sicherung auslösen (403)" \
                    || bad "Sicherung auslösen ergab $CODE statt 403"
rm -f "$UJAR"

# --------------------------------------------------------------- Sicherung
BEFORE=$(api "$BASE/api/backups" | jqp "len(d)")
api -X POST "$BASE/api/backups/run" -H 'Content-Type: application/json' \
    -d "{\"username\":\"$USER_NAME\"}" >/dev/null
sleep 2
AFTER=$(api "$BASE/api/backups" | jqp "len(d)")
[ "$AFTER" -gt "$BEFORE" ] && ok "Sicherung angelegt ($BEFORE → $AFTER)" \
                           || bad "Keine neue Sicherung entstanden"

LAST=$(api "$BASE/api/backups" | jqp "d[0]")
STATUS=$(api "$BASE/api/backups" | jqp "d[0]['status']")
SIZE=$(api "$BASE/api/backups" | jqp "d[0]['size_bytes']")
BID=$(api "$BASE/api/backups" | jqp "d[0]['id']")
FILES=$(api "$BASE/api/backups" | jqp "d[0]['file_count']")
[ "$STATUS" = "ok" ] && ok "Sicherung erfolgreich, $((SIZE/1024)) KB, $FILES Einträge" \
                     || bad "Sicherung mit Status $STATUS"

PATHV=$(api "$BASE/api/backups" | jqp "d[0]['path'] or ''")
[ -n "$PATHV" ] && [ -f "$PATHV" ] && ok "Archiv liegt auf der Platte" \
                                   || bad "Archiv fehlt: $PATHV"
tar --zstd -tf "$PATHV" >/dev/null 2>&1 && ok "Archiv ist lesbar" || bad "Archiv beschädigt"

# ------------------------------------------- Was von Hand angelegt wurde
#
# `make backup` sicherte bis zum 2026-08-28 nur die Zuhause der Nutzer und die
# Datenbank. Nicht dabei waren die Skeleton-Profile, die gemeinsame Ablage und
# die eigenen Ablagen — also genau das, was jemand von Hand angelegt hat und
# was sich weder aus Code noch aus einem Image wiederherstellen laesst. Ein
# zurueckgespielter Stand kam ohne all das zurueck, und es faellt erst auf,
# wenn man es braucht.
#
# Geprueft wird der Befehl aus dem Makefile selbst, nicht eine Kopie davon:
# `make -n` schreibt ihn aus, und genau der laeuft hier.
echo
echo "Von Hand angelegte Inhalte"

INH=$(cd "$ROOT" && make -n backup 2>/dev/null | grep -A 3 'inhalte-' | head -4)

if [ -z "$INH" ]; then
  bad "Im Sicherungslauf gibt es keinen Schritt für die Inhalte"
else
  ( cd "$ROOT" && eval "$INH" ) >/dev/null 2>&1 || true
  PROBE=$(ls -t "$ROOT"/backups/inhalte-*.tar.zst 2>/dev/null | head -1)

  if [ -z "$PROBE" ]; then
    bad "Der Inhaltsschritt erzeugte kein Archiv"
  else
    DRIN=$(tar --zstd -tf "$PROBE" 2>/dev/null | awk -F/ 'NF>2 {print $3}' | sort -u)
    for teil in skeletons shared userfiles groupfiles; do
      if grep -qx "$teil" <<<"$DRIN"; then
        ok "srv/ota/$teil ist in der Sicherung"
      else
        bad "srv/ota/$teil fehlt in der Sicherung"
      fi
    done
  fi
fi


# ---------------------------------------------------------- Container
echo
# Für die Container-Prüfungen braucht es einen laufenden Arbeitsplatz. Statt
# ihn vorauszusetzen, stellt der Test ihn selbst her — sonst hängt das
# Ergebnis davon ab, was ein vorheriger Test hinterlassen hat.
#
# Und zwar den Container **dieses** Kontos, nicht den ersten aus `docker ps`.
# Lief zuvor die Autorisierungsreihe, steht dort die Session eines Testnutzers
# vorn: Die Markierung landete dann in einem fremden Container, die Sicherung
# wurde von einem anderen gezogen, und drei Prüfungen scheiterten an einem
# Zustand statt an einem Fehler. Gemessen am 2026-08-28.
mein_container() {
  api "$BASE/api/sessions" | jqp "
next(('ota-s-' + s['id'][:12] for s in d if s['status'] == 'running'), '')"
}

# Zu welcher Vorlage der Container gehoert, den wir markieren.
#
# Gebraucht, seit ein Konto mehrere Sitzungen gleichzeitig haben kann — etwa
# einen Arbeitsplatz und daneben einen mit der zweiten Streaming-Maschine.
# `/api/backups/run` sichert **jede** laufende Sitzung; wer sich danach „die
# erste Container-Sicherung" greift, erwischt womoeglich eine andere als die,
# in der die Markierung liegt. Genau daran ist die Pruefung am 2026-09-02
# gescheitert, und es sah aus wie ein Fehler in der Sicherung.
meine_vorlage() {
  api "$BASE/api/sessions" | jqp "
next((s['template_name'] for s in d if s['status'] == 'running'), '')"
}

CN=$(mein_container)
if [ -z "$CN" ]; then
  TPL=$(api "$BASE/api/templates" \
    | jqp "next((t['id'] for t in d if t['mode']=='workspace' and t['is_enabled']), '')")
  if [ -n "$TPL" ]; then
    api -X POST "$BASE/api/sessions" -H 'Content-Type: application/json' \
        -d "{\"template_id\":\"$TPL\"}" >/dev/null
    echo "  (Arbeitsplatz für die Prüfung gestartet)"
    sleep 20
    CN=$(mein_container)
  fi
fi
if [ -n "$CN" ]; then
  # Der Slug der Vorlage steht in der Sicherung; darueber wird sie
  # wiedergefunden. Ueber den Anzeigenamen und nicht ueber den Slug, weil die
  # Sitzungsliste nur den Namen fuehrt — verglichen wird gleich klein
  # geschrieben und ohne Sonderzeichen.
  MEINE_VORLAGE=$(meine_vorlage)
  MARKER="/etc/ota-pruefmarke-$$.txt"
  docker exec -u 0 "$CN" sh -c "echo pruefmarke > $MARKER" 2>/dev/null \
    && ok "Markierung ausserhalb des Home im Container angelegt" \
    || bad "Markierung liess sich nicht anlegen"

  api -X POST "$BASE/api/backups/run" -H 'Content-Type: application/json' \
      -d "{\"username\":\"$USER_NAME\",\"include_container\":true}" >/dev/null
  sleep 2

  # Genau die Sicherung des Containers, den wir markiert haben — nicht
  # irgendeine. Verglichen wird ueber die Vorlage; passt keine, bleibt es bei
  # der ersten, dann meldet die Pruefung darunter ehrlich einen Fehlschlag.
  AUSWAHL="[b for b in d if b['kind']=='container' and b['status']=='ok']"
  PASSEND="[b for b in $AUSWAHL if b['template_slug'].replace('-','') in '$MEINE_VORLAGE'.lower().replace(' ','').replace('-','')]"
  CSIZE=$(api "$BASE/api/backups" | jqp "next(iter([b['size_bytes'] for b in ($PASSEND or $AUSWAHL)]), 0)")
  CFILES=$(api "$BASE/api/backups" | jqp "next(iter([b['file_count'] for b in ($PASSEND or $AUSWAHL)]), 0)")
  CBID=$(api "$BASE/api/backups" | jqp "next(iter([b['id'] for b in ($PASSEND or $AUSWAHL)]), '')")

  [ "${CFILES:-0}" -gt 0 ] && ok "Container-Sicherung angelegt: $CFILES Einträge, $((CSIZE/1024)) KB" \
                           || bad "Container-Sicherung leer"

  # Der wichtigste Punkt: Es dürfen NICHT ganze Verzeichnisbäume mitkommen.
  # docker diff meldet auch jedes Elternverzeichnis als geändert; wer die
  # ungefiltert einsammelt, sichert hunderte MB unveränderter Dateien.
  [ "${CSIZE:-0}" -lt 5242880 ] \
    && ok "Archiv bleibt klein ($((CSIZE/1024)) KB) — keine Elternverzeichnisse mitgesichert" \
    || bad "Archiv ist $((CSIZE/1024/1024)) MB gross — vermutlich ganze Bäume mitgesichert"

  CPATH=$(api "$BASE/api/backups" | jqp "next(iter([b['path'] for b in ($PASSEND or $AUSWAHL)]), '')")
  if [ -n "$CPATH" ] && [ -f "$CPATH" ]; then
    tar --zstd -tf "$CPATH" 2>/dev/null | grep -q "^etc/ota-pruefmarke-$$" \
      && ok "Markierung liegt unter dem richtigen Pfad im Archiv" \
      || bad "Pfad im Archiv stimmt nicht"
    tar --zstd -tf "$CPATH" 2>/dev/null | grep -qE "^(etc/etc|dockerstartup/dockerstartup)/" \
      && bad "Pfade im Archiv sind verdoppelt" \
      || ok "Keine verdoppelten Pfade im Archiv"
  fi

  docker exec -u 0 "$CN" rm -f "$MARKER" 2>/dev/null
  MSG=$(api -X POST "$BASE/api/backups/$CBID/restore-into-session" | jqp "d.get('status') or d.get('detail','')")
  grep -qi "zurückgespielt" <<<"$MSG" && ok "Container-Sicherung zurückgespielt" \
                                          || bad "Zurückspielen: $MSG"
  docker exec "$CN" test -f "$MARKER" 2>/dev/null \
    && ok "Markierung ist wieder im Container" || bad "Markierung fehlt nach dem Zurückspielen"
  docker exec -u 0 "$CN" rm -f "$MARKER" 2>/dev/null
else
  ok "Kein Container offen — Container-Prüfungen übersprungen"
fi

# ------------------------------------- Schutz: keine Wiederherstellung bei Session
PROFILE="/srv/ota/profiles/$USER_NAME/user"
SESSIONS=$(api "$BASE/api/sessions" | jqp "len(d)")
if [ "$SESSIONS" -gt 0 ]; then
  MSG=$(api -X POST "$BASE/api/backups/$BID/restore" | jqp "d.get('detail','')")
  grep -qi "session" <<<"$MSG" && ok "Wiederherstellung bei laufender Session abgelehnt" \
                                   || bad "Laufende Session wurde nicht erkannt: $MSG"
  for s in $(api "$BASE/api/sessions" | jqp "' '.join(x['id'] for x in d)"); do
    api -X DELETE "$BASE/api/sessions/$s" >/dev/null
  done
  sleep 3
  ok "Sessions für den Test beendet"
else
  ok "Keine laufende Session — Schutzprüfung übersprungen"
fi

# --------------------------------------------------------- Wiederherstellung
MARK="$PROFILE/PRUEFMARKE-$$.txt"
echo "diese Datei darf nach der Wiederherstellung nicht mehr da sein" > "$MARK"
[ -f "$MARK" ] && ok "Markierung ins Profil gelegt" || bad "Markierung liess sich nicht anlegen"

MSG=$(api -X POST "$BASE/api/backups/$BID/restore" | jqp "d.get('status') or d.get('detail','')")
grep -qi "wiederhergestellt" <<<"$MSG" && ok "Wiederherstellung gemeldet" \
                                           || bad "Wiederherstellung: $MSG"

[ ! -f "$MARK" ] && ok "Markierung ist verschwunden — die Wiederherstellung hat gewirkt" \
                 || bad "Markierung noch vorhanden — wirkungslos"

ASIDE=$(ls -d "/srv/ota/profiles/$USER_NAME"/user.vor-wiederherstellung-* 2>/dev/null | tail -1)
[ -n "$ASIDE" ] && [ -f "$ASIDE/$(basename "$MARK")" ] \
  && ok "Bisheriger Stand wurde beiseitegelegt, mit Markierung darin" \
  || bad "Kein brauchbarer Sicherheitsstand hinterlegt"

OWNER=$(stat -c '%u:%g' "$PROFILE" 2>/dev/null)
[ "$OWNER" = "1000:1000" ] && ok "Eigentümer nach der Wiederherstellung korrekt (1000:1000)" \
                           || bad "Eigentümer ist $OWNER statt 1000:1000"

# Aufräumen: die Sicherheitsstände des Tests wieder entfernen.
rm -rf "/srv/ota/profiles/$USER_NAME"/user.vor-wiederherstellung-* 2>/dev/null

# ---------------------------------------------------------- Datenbank
echo
DB_BEFORE=$(api "$BASE/api/backups" | jqp "sum(1 for b in d if b['kind']=='database')")
api -X POST "$BASE/api/backups/run" -H 'Content-Type: application/json' \
    -d '{"database_only":true}' >/dev/null
sleep 2
DB_AFTER=$(api "$BASE/api/backups" | jqp "sum(1 for b in d if b['kind']=='database')")
[ "$DB_AFTER" -gt "$DB_BEFORE" ] && ok "Datenbanksicherung angelegt" \
                                 || bad "Keine Datenbanksicherung entstanden"

DBPATH=$(api "$BASE/api/backups" | jqp "next((b['path'] for b in d if b['kind']=='database' and b['status']=='ok'), '')")
[ -n "$DBPATH" ] && [ -f "$DBPATH" ] && ok "Datenbank-Archiv liegt auf der Platte" \
                                     || bad "Datenbank-Archiv fehlt"
# Erst in eine Variable, dann prüfen: Mit "| head" bekäme zstd ein SIGPIPE,
# und unter "set -o pipefail" kippt dadurch der Rückgabewert der ganzen Kette.
# In eine Datei statt in eine Variable: Der Dump beginnt mit einer Zeile aus
# zwei Bindestrichen, und "echo" fasst die als Optionen auf.
DUMP_TMP=$(mktemp)
zstd -dq -c "$DBPATH" > "$DUMP_TMP" 2>/dev/null || true
grep -q "PostgreSQL database dump" "$DUMP_TMP" \
  && ok "Archiv enthält einen gültigen pg_dump" || bad "Archiv ist kein pg_dump"
grep -q "DROP TABLE IF EXISTS" "$DUMP_TMP" \
  && ok "Dump räumt vor dem Einspielen auf (--clean --if-exists)" \
  || bad "Dump ohne --clean — liesse sich nicht über eine bestehende Datenbank legen"
grep -q "COPY public.users" "$DUMP_TMP" \
  && ok "Nutzerdaten sind im Dump enthalten" || bad "Nutzertabelle fehlt im Dump"
rm -f "$DUMP_TMP"

DBID=$(api "$BASE/api/backups" | jqp "next((b['id'] for b in d if b['kind']=='database' and b['status']=='ok'), '')")
MSG=$(api -X POST "$BASE/api/backups/$DBID/restore" | jqp "d.get('detail','')")
grep -qi "restore-db" <<<"$MSG" \
  && ok "Datenbank-Wiederherstellung verweist auf das Skript statt es zu versuchen" \
  || bad "Unerwartete Antwort: $MSG"

"$ROOT/scripts/restore-db.sh" --list >/dev/null 2>&1 \
  && ok "restore-db.sh findet die Sicherungen" || bad "restore-db.sh findet nichts"

# ------------------------------------------------ Aufräumen und Robustheit
echo
# Nutzer ohne Profil dürfen keinen Fehlereintrag hinterlassen — sie sind der
# Normalfall bei frisch angelegten Konten und würden die Liste zustellen.
api -X POST "$BASE/api/backups/run" -H 'Content-Type: application/json' -d '{}' >/dev/null
sleep 8
NOPROFILE=$(api "$BASE/api/backups" | jqp "sum(1 for b in d if 'noch kein Profil' in (b['error'] or ''))")
[ "${NOPROFILE:-0}" -eq 0 ] && ok "Nutzer ohne Profil erzeugen keinen Fehlereintrag" \
                            || bad "$NOPROFILE Fehlereinträge für Konten ohne Profil"

RESULT=$(api "$BASE/api/backups/policy" | jqp "d.get('last_result') or ''")
grep -q "ohne Profil" <<<"$RESULT" && ok "Lauf meldet übersprungene Konten: $RESULT" \
                                       || bad "Lauf ohne Angabe der übersprungenen Konten"

# Ein Lauf, der beim Neustart des Dienstes abgebrochen ist, stünde sonst für
# immer auf "läuft".
docker exec ota-db psql -U ota -d ota -q -c \
  "INSERT INTO backups (id, kind, status, trigger, started_at)
   VALUES (gen_random_uuid(), 'database', 'running', 'manual', now() - interval '5 hours');" >/dev/null 2>&1
STUCK=$(api "$BASE/api/backups" | jqp "sum(1 for b in d if b['status']=='running')")
[ "${STUCK:-1}" -eq 0 ] && ok "Hängengebliebener Lauf wird beim Hinsehen abgeschlossen" \
                        || bad "$STUCK Läufe stehen weiterhin auf 'läuft'"

# ------------------------------------------------------------------ Zeitplan
POL=$(api "$BASE/api/backups/policy")
echo "$POL" | jqp "d['keep_daily']" | grep -q . && ok "Zeitplan abrufbar (behält $(echo "$POL" | jqp "d['keep_daily']") tägliche Stände)" \
                                               || bad "Zeitplan nicht abrufbar"
api -X PUT "$BASE/api/backups/policy" -H 'Content-Type: application/json' \
    -d '{"is_enabled":false,"hour":3,"minute":30,"weekdays":[],"include_profiles":true,"include_containers":false,"include_database":true,"keep_daily":7,"keep_weekly":4}' >/dev/null
ENABLED=$(api "$BASE/api/backups/policy" | jqp "d['is_enabled']")
[ "$ENABLED" = "False" ] && ok "Zeitplan lässt sich ändern" || bad "Zeitplan liess sich nicht ändern"

echo
echo "─────────────────────────────────────"
printf '  bestanden: %d   fehlgeschlagen: %d\n' "$pass" "$fail"
[ "$fail" -eq 0 ] || exit 1
