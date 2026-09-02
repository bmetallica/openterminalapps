#!/usr/bin/env bash
# Benennt Profile und eigene Ablagen von Anmeldenamen auf Kennungen um.
#
#   scripts/migrate-profilpfade.sh          Probelauf — aendert nichts
#   scripts/migrate-profilpfade.sh --tun    wirklich umbenennen
#
# **Warum das sein muss.** Die Verzeichnisse hiessen nach dem Anmeldenamen.
# Das ging so lange gut, wie OTA die Namen selbst vergab; seit die Konten aus
# Keycloak kommen, zieht OTA einen dort geaenderten Namen nach — und ab diesem
# Moment zeigt der Pfad woanders hin. Wer umbenannt wird, faende ein leeres
# Zuhause, waehrend das alte danebenliegt und niemand dort sucht.
#
# Danach heissen die Verzeichnisse nach `users.id` — einer Kennung, die sich
# nie aendert und die es fuer **jedes** Konto gibt, auch fuer das lokale
# Notfallkonto. Daneben legt der Agent bei jedem Start einen Verweis unter dem
# Anmeldenamen an, damit im Dateisystem trotzdem jemand etwas findet.
#
# **Laeuft nicht, solange eine Session offen ist.** Ein Verzeichnis unter einem
# offenen Bind-Mount umzubenennen fuehrt zu einem Container, der in ein
# Verzeichnis schreibt, das es nicht mehr gibt.

set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
[ -f "$ROOT/deploy/.env" ] && { set -a; . "$ROOT/deploy/.env"; set +a; }

PROFILE="${OTA_PROFILES_ROOT:-/srv/ota/profiles}"
ABLAGEN="${OTA_USERFILES_ROOT:-/srv/ota/userfiles}"
COMPOSE="docker compose -f $ROOT/deploy/docker-compose.yml --env-file $ROOT/deploy/.env"
TUN=0
[ "${1:-}" = "--tun" ] && TUN=1

ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
info() { printf '  · %s\n' "$1"; }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$1" >&2; }

echo "Profilpfade auf Kennungen umstellen"
[ "$TUN" = "1" ] && echo "  (es wird wirklich umbenannt)" || echo "  (Probelauf — nichts wird geaendert)"
echo

# ------------------------------------------------ Sicherheitsabfragen
LAEUFT=$(docker ps --filter "label=ota.session_id" --format '{{.Names}}' | wc -l)
if [ "${LAEUFT:-0}" -gt 0 ]; then
  bad "Es laufen noch $LAEUFT Session-Container."
  echo "     Ein Verzeichnis unter einem offenen Bind-Mount umzubenennen ist der" >&2
  echo "     sicherste Weg in einen Container, der ins Leere schreibt." >&2
  echo "     Erst alle Sessions beenden, dann noch einmal." >&2
  exit 1
fi
ok "Keine Session offen"

KONTEN=$($COMPOSE exec -T db psql -U "${POSTGRES_USER:-ota}" -d "${POSTGRES_DB:-ota}" \
  -tAF'|' -c "SELECT id, username FROM users ORDER BY username" 2>/dev/null)
if [ -z "$KONTEN" ]; then
  bad "Keine Konten gelesen — laeuft die Datenbank?"
  exit 1
fi
ok "$(echo "$KONTEN" | grep -c .) Konten gelesen"
echo

umziehen() {  # umziehen <wurzel> <name> <kennung>
  local wurzel="$1" name="$2" kennung="$3"
  local alt="$wurzel/$name" neu="$wurzel/$kennung"

  # Schon umgezogen? Dann nur den Verweis nachziehen.
  if [ -d "$neu" ] && [ ! -L "$neu" ]; then
    if [ ! -e "$wurzel/$name" ]; then
      [ "$TUN" = "1" ] && ln -s "$kennung" "$wurzel/$name"
      info "$name: schon umgezogen, Verweis $( [ "$TUN" = 1 ] && echo gesetzt || echo fehlt )"
    else
      info "$name: schon umgezogen"
    fi
    return
  fi

  if [ ! -d "$alt" ] || [ -L "$alt" ]; then
    info "$name: nichts vorhanden"
    return
  fi

  if [ "$TUN" = "1" ]; then
    mv "$alt" "$neu" && ln -s "$kennung" "$alt" \
      && ok "$name → $kennung  (Verweis gesetzt)" \
      || bad "$name liess sich nicht umbenennen"
  else
    local groesse; groesse=$(du -sh "$alt" 2>/dev/null | cut -f1)
    ok "$name → $kennung  ($groesse)"
  fi
}

for wurzel in "$PROFILE" "$ABLAGEN"; do
  [ -d "$wurzel" ] || continue
  echo "$wurzel"
  while IFS='|' read -r kennung name; do
    [ -z "$kennung" ] && continue
    umziehen "$wurzel" "$name" "$kennung"
  done <<< "$KONTEN"
  echo
done

# Was uebrig bleibt, gehoert zu keinem Konto mehr. Es wird **nicht** angefasst
# — dort koennen die Daten eines geloeschten Menschen liegen, und die
# wegzuraeumen ist eine Entscheidung, keine Nebenwirkung.
for wurzel in "$PROFILE" "$ABLAGEN"; do
  [ -d "$wurzel" ] || continue
  for eintrag in "$wurzel"/*; do
    [ -e "$eintrag" ] || continue
    [ -L "$eintrag" ] && continue
    local_name=$(basename "$eintrag")
    if ! cut -d'|' -f1,2 --output-delimiter=$'\n' <<< "$KONTEN" | grep -qx "$local_name"; then
      info "$wurzel/$local_name gehoert zu keinem Konto — bleibt unangetastet"
    fi
  done
done

echo
[ "$TUN" = "1" ] && echo "Fertig." || echo "Probelauf. Mit --tun wirklich ausfuehren."
