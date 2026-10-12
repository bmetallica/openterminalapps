#!/usr/bin/env bash
# Das Update-Banner auf allen OTA-Seiten an- und abschalten.
#
#   scripts/wartung.sh an     Banner zeigen (macht `make update` am Anfang)
#   scripts/wartung.sh aus    erst warten, bis die API gesund ist, dann weg
#                             (macht `make update` am Ende)
#   scripts/wartung.sh aus --sofort   ohne zu warten
#
# Die Marke steht direkt in der Datenbank (settings, Schlüssel wartung.update):
# Die API startet während des Updates neu, die Datenbank nicht. Jede Seite
# fragt alle 15 Sekunden /api/wartung.
#
# Scheitert ein Update, bleibt das Banner mit Absicht stehen — bis ein Lauf
# gelingt oder jemand `scripts/wartung.sh aus` aufruft.
set -uo pipefail

psql() { docker exec ota-db psql -U "${POSTGRES_USER:-ota}" -d "${POSTGRES_DB:-ota}" -tAc "$1" >/dev/null 2>&1; }

case "${1:-}" in
  an)
    # Beim allerersten `make update` gibt es die Datenbank vielleicht noch
    # nicht — dann eben kein Banner, und kein Fehler.
    if psql "INSERT INTO settings(key, value, updated_at) VALUES ('wartung.update', json_build_object('v', to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"'))::jsonb, now())
             ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()"; then
      echo "  Update-Banner an: Alle OTA-Seiten zeigen es innerhalb von 15 Sekunden."
    fi
    ;;
  aus)
    if [ "${2:-}" != "--sofort" ]; then
      # Erst weg, wenn die neue API wirklich antwortet: Wer neu lädt, soll die
      # neue Fassung bekommen und keine Fehlerseite.
      for _ in $(seq 1 60); do
        [ "$(docker inspect -f '{{.State.Health.Status}}' ota-api 2>/dev/null)" = "healthy" ] && break
        sleep 3
      done
      if [ "$(docker inspect -f '{{.State.Health.Status}}' ota-api 2>/dev/null)" != "healthy" ]; then
        echo "  Die API ist nach drei Minuten nicht gesund — das Update-Banner bleibt." >&2
        echo "  Nachsehen mit 'make logs'; danach: scripts/wartung.sh aus" >&2
        exit 1
      fi
    fi
    psql "DELETE FROM settings WHERE key = 'wartung.update'" \
      && echo "  Update-Banner aus."
    ;;
  *)
    sed -n '2,15p' "$0"; exit 2 ;;
esac
