#!/usr/bin/env bash
# Spielt eine Datenbanksicherung zurück.
#
# Warum das kein Knopf in der Oberfläche ist: Die Datenbank trägt die
# Anmeldung, mit der man gerade in der Oberfläche steht. Sie unter der
# laufenden Anwendung auszutauschen bricht jede offene Verbindung mittendrin.
# Das Skript hält die Dienste deshalb selbst an und startet sie danach wieder.
#
# Aufruf:
#   ./scripts/restore-db.sh                      # neueste Sicherung
#   ./scripts/restore-db.sh <pfad/zur/datei>     # bestimmte Sicherung
#   ./scripts/restore-db.sh --list               # vorhandene Sicherungen

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# shellcheck disable=SC1091
set -a; [ -f deploy/.env ] && . deploy/.env; set +a

BACKUP_ROOT="${OTA_BACKUP_ROOT:-/srv/ota/backups}"
DB_DIR="$BACKUP_ROOT/database"
DB_CONTAINER="${OTA_DB_CONTAINER:-ota-db}"
DB_USER="${POSTGRES_USER:-ota}"
DB_NAME="${POSTGRES_DB:-ota}"
COMPOSE="docker compose -f deploy/docker-compose.yml --env-file deploy/.env"

red()  { printf '\033[31m%s\033[0m\n' "$*"; }
grn()  { printf '\033[32m%s\033[0m\n' "$*"; }
info() { printf '  %s\n' "$*"; }

list_backups() {
  if ! compgen -G "$DB_DIR/*.sql.zst" > /dev/null; then
    red "Keine Datenbanksicherungen unter $DB_DIR"
    exit 1
  fi
  echo "Vorhandene Datenbanksicherungen:"
  # shellcheck disable=SC2012
  ls -1t "$DB_DIR"/*.sql.zst | while read -r f; do
    printf '  %-12s %s\n' "$(du -h "$f" | cut -f1)" "$f"
  done
}

[ "${1:-}" = "--list" ] && { list_backups; exit 0; }

if [ -n "${1:-}" ]; then
  ARCHIVE="$1"
else
  # shellcheck disable=SC2012
  ARCHIVE=$(ls -1t "$DB_DIR"/*.sql.zst 2>/dev/null | head -1 || true)
fi

[ -n "$ARCHIVE" ] && [ -f "$ARCHIVE" ] || {
  red "Keine Sicherung gefunden."
  echo "  Mit --list die vorhandenen anzeigen."
  exit 1
}

echo
echo "Datenbank wiederherstellen"
echo "────────────────────────────────────────────────────────"
info "Quelle:    $ARCHIVE ($(du -h "$ARCHIVE" | cut -f1))"
info "Ziel:      Datenbank '$DB_NAME' im Container $DB_CONTAINER"
info "Erstellt:  $(date -r "$ARCHIVE" '+%d.%m.%Y %H:%M')"
echo
red "Der aktuelle Inhalt der Datenbank wird ersetzt."
echo "  Nutzer, Gruppen, Workspaces, Zuweisungen und das Audit-Log"
echo "  gehen auf den Stand dieser Sicherung zurück."
echo "  Profile auf der Platte sind davon NICHT betroffen."
echo

if [ "${OTA_ASSUME_YES:-}" != "1" ]; then
  read -r -p "Zum Fortfahren den Datenbanknamen eingeben ($DB_NAME): " ANSWER
  [ "$ANSWER" = "$DB_NAME" ] || { echo "Abgebrochen."; exit 1; }
fi

echo
echo "1/5  Sicherheitskopie des jetzigen Standes"
mkdir -p "$DB_DIR"
SAFETY="$DB_DIR/vor-wiederherstellung-$(date -u +%Y-%m-%dT%H-%M-%SZ).sql.zst"
docker exec "$DB_CONTAINER" pg_dump -U "$DB_USER" -d "$DB_NAME" \
  --clean --if-exists --no-owner --no-privileges \
  | zstd -q -3 -c > "$SAFETY"
info "abgelegt unter $SAFETY ($(du -h "$SAFETY" | cut -f1))"

echo
echo "2/5  Anwendung anhalten"
# Nur API und Agent: Der Datenbank-Container muss laufen, und Traefik soll
# weiterhin eine verständliche Fehlerseite ausliefern statt gar nichts.
$COMPOSE stop api agent >/dev/null 2>&1
info "api und agent gestoppt, db und traefik laufen weiter"

echo
echo "3/5  Offene Verbindungen beenden"
docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d postgres -q -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity
   WHERE datname = '$DB_NAME' AND pid <> pg_backend_pid();" >/dev/null 2>&1 || true
info "erledigt"

echo
echo "4/5  Sicherung einspielen"
if zstd -dq -c "$ARCHIVE" \
   | docker exec -i "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" \
       -v ON_ERROR_STOP=1 -q > /tmp/ota-restore.log 2>&1; then
  info "eingespielt"
else
  red "Fehlgeschlagen. Letzte Zeilen:"
  tail -12 /tmp/ota-restore.log | sed 's/^/    /'
  echo
  echo "  Der Stand von vorher liegt unverändert unter:"
  echo "    $SAFETY"
  echo "  Zurück damit:"
  echo "    $0 $SAFETY"
  $COMPOSE start api agent >/dev/null 2>&1
  exit 1
fi

echo
echo "5/5  Anwendung starten"
$COMPOSE start api agent >/dev/null 2>&1
for _ in $(seq 1 20); do
  [ "$(docker inspect ota-api --format '{{.State.Health.Status}}' 2>/dev/null)" = healthy ] && break
  sleep 3
done
STATE=$(docker inspect ota-api --format '{{.State.Health.Status}}' 2>/dev/null || echo unbekannt)
info "ota-api: $STATE"

echo
if [ "$STATE" = "healthy" ]; then
  grn "Wiederherstellung abgeschlossen."
  echo "  Alle Anmeldungen sind erneuert — bestehende Sitzungen im Browser"
  echo "  müssen sich neu anmelden."
  echo "  Der Stand von vorher bleibt unter $SAFETY liegen."
else
  red "Die Anwendung ist nach der Wiederherstellung nicht gesund."
  echo "  Logs ansehen:  docker logs ota-api --tail 40"
  echo "  Zurück:        $0 $SAFETY"
  exit 1
fi
