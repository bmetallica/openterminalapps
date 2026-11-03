#!/usr/bin/env bash
# Datenbanken und Docker-Daten von OTA an einen anderen Ort ziehen — etwa auf
# eine SSD, während die Nutzerdaten auf der großen Platte bleiben. Handbuch,
# Kapitel 40.
#
#   sudo scripts/daten-umziehen.sh --status
#   sudo scripts/daten-umziehen.sh --alle /ssd/ota          alles nach /ssd/ota/<teil>
#   sudo scripts/daten-umziehen.sh --db /ssd/ota/db --platz-docker /schnell/docker
#   sudo scripts/daten-umziehen.sh --db volume              zurück ins Docker-Volume
#   sudo scripts/daten-umziehen.sh --aufraeumen             alte Kopien löschen (fragt)
#
# Teile: --db (Postgres von OTA und Keycloak), --registry, --git (OTA-Git),
# --gedaechtnis (Datenbank der Erweiterung, wenn sie läuft) und
# --platz-docker (Docker-Daten der Root-Arbeitsplätze, ein Verzeichnis je
# Platz). Ziel ist ein Verzeichnis oder das Wort `volume`.
#
# Ablauf je Teil:
#   1. Kopieren im laufenden Betrieb (rsync). Das dauert, stört aber nicht.
#   2. Umschalten: Dienst anhalten, ein zweites rsync (nur noch Änderungen,
#      Sekunden), Ort in deploy/.env eintragen, Dienst neu anlegen, prüfen.
#   3. Die alte Kopie bleibt liegen, bis `--aufraeumen` sie löscht. Bis dahin
#      geht es mit `--<teil> volume` (oder dem alten Pfad) wieder zurück.
#
#   --nur-kopieren   nur Schritt 1 (beliebig oft; danach geht das Umschalten schneller)
#   --ja             nicht nachfragen
#
# Laufende Root-Arbeitsplätze hält das Skript nie an: Es kopiert sie nur
# vor. Umgeschaltet werden sie beim nächsten Fortsetzen — das erledigt der
# Agent, bevor er den Container startet (nur das, was sich seitdem geändert
# hat). Angehaltene schaltet das Skript gleich um.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV="$ROOT/deploy/.env"
COMPOSE=(docker compose -f "$ROOT/deploy/docker-compose.yml" --env-file "$ENV")
# Verzeichnisse, aus denen ein Dienst ausgezogen ist — für --aufraeumen.
# (Alte Volumes findet es auch ohne Liste.)
ALTE_ORTE="$ROOT/deploy/.umzug-alte-orte"

[ "$(id -u)" = 0 ] || { echo "Bitte als root ausführen (sudo)." >&2; exit 1; }
command -v rsync >/dev/null || { echo "rsync fehlt: apt install rsync" >&2; exit 1; }
[ -f "$ENV" ] || { echo "$ENV fehlt." >&2; exit 1; }

declare -A ZIEL=()
NUR_KOPIEREN=0 JA=0 STATUS=0 AUFRAEUMEN=0
TEILE=(db registry git gedaechtnis platz-docker)

while [ $# -gt 0 ]; do
  case "$1" in
    --alle) [ -n "${2:-}" ] || { echo "--alle braucht ein Verzeichnis" >&2; exit 2; }
            for t in "${TEILE[@]}"; do ZIEL[$t]="${2%/}/$t"; done; shift 2 ;;
    --db|--registry|--git|--gedaechtnis|--platz-docker)
            [ -n "${2:-}" ] || { echo "$1 braucht ein Verzeichnis oder 'volume'" >&2; exit 2; }
            ZIEL[${1#--}]="${2%/}"; shift 2 ;;
    --nur-kopieren) NUR_KOPIEREN=1; shift ;;
    --ja) JA=1; shift ;;
    --status) STATUS=1; shift ;;
    --aufraeumen) AUFRAEUMEN=1; shift ;;
    -h|--help) sed -n '2,32p' "$0"; exit 0 ;;
    *) echo "Unbekannt: $1 (--help)" >&2; exit 2 ;;
  esac
done

for t in "${!ZIEL[@]}"; do
  z=${ZIEL[$t]}
  if [ "$z" != volume ] && [ "${z:0:1}" != / ]; then
    echo "--$t: absoluter Pfad oder 'volume' erwartet, nicht '$z'" >&2; exit 2
  fi
done

# ------------------------------------------------------------------ Helfer
kopf() { printf '\n\033[1m== %s ==\033[0m\n' "$1"; }
fragen() {
  [ "$JA" = 1 ] && return 0
  local a; read -r -p "$1 [j/N] " a; [ "$a" = j ] || [ "$a" = J ]
}
env_lesen() { # <Datei> <Schlüssel>
  sed -n "s/^$2=//p" "$1" 2>/dev/null | tail -1
}
env_setzen() { # <Datei> <Schlüssel> <Wert> — vorhandene Zeile ersetzen, sonst anhängen
  local datei=$1 k=$2 v=$3
  if grep -q "^$k=" "$datei"; then
    sed -i "s|^$k=.*|$k=$v|" "$datei"
  else
    printf '%s=%s\n' "$k" "$v" >> "$datei"
  fi
}
quelle_von() { # <Container> <Ziel im Container> — der Ort auf dem Wirt
  docker inspect -f "{{range .Mounts}}{{if eq .Destination \"$2\"}}{{.Source}}{{end}}{{end}}" "$1" 2>/dev/null
}
volume_pfad() { docker volume inspect -f '{{.Mountpoint}}' "$1" 2>/dev/null; }
laeuft() { [ "$(docker inspect -f '{{.State.Running}}' "$1" 2>/dev/null)" = true ]; }
gesund_warten() { # <Container> <Sekunden>
  local i
  for ((i = 0; i < $2; i += 2)); do
    case "$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$1" 2>/dev/null)" in
      healthy|running) return 0 ;;
    esac
    sleep 2
  done
  return 1
}
kopieren() { # <Quelle> <Ziel> — Besitzer, Rechte, Hardlinks, ACLs, xattrs (Overlay-Whiteouts!)
  mkdir -p "$2"
  local fortschritt=()
  [ -t 1 ] && fortschritt=(--info=progress2 --no-inc-recursive)
  local rc=0
  rsync -aHAXS --numeric-ids --delete "${fortschritt[@]}" "$1"/ "$2"/ || rc=$?
  # 24: Dateien verschwanden während des Kopierens — im laufenden Betrieb
  # normal (Temporäres, Logs, WAL). Was fehlt, holt der letzte Abgleich.
  [ "$rc" = 24 ] && { echo "  (Einige Dateien verschwanden beim Kopieren — im laufenden Betrieb normal.)"; rc=0; }
  return "$rc"
}
# Die Marke zeigt den Beginn der ersten Vorkopie. Spätere Läufe lassen sie
# stehen: Der letzte Abgleich kopiert alles neu, was sich seitdem geändert hat.
marke() { [ -f "$1.ota-umzug" ] || touch "$1.ota-umzug"; }
# Der letzte Abgleich, mit angehaltenem Dienst. rsync allein vergleicht
# Größe und Zeit auf die Sekunde — Postgres überschreibt WAL-Dateien gleicher
# Größe aber mehrmals je Sekunde, und so eine Kopie startet nicht (im Test
# „invalid checkpoint record“). Deshalb zusätzlich jede Datei neu, deren
# ctime jünger ist als der Beginn der Vorkopie (<Marke>). Die ctime lässt sich
# nicht zurückstellen, auch nicht beim Auspacken von Image-Schichten.
abgleich() { # <Quelle> <Ziel> <Marke>
  kopieren "$1" "$2" >/dev/null || return 1
  (cd "$1" && find . -newercm "$3" \( -type f -o -type l \) -print0) \
    | rsync -aHAXS --numeric-ids -I --from0 --files-from=- "$1"/ "$2"/
}
ziel_pruefen() { # <Ziel> <Quelle> — leer, unsere Vorkopie, oder nichts dagegen
  local z=$1 q=$2
  [ "$(readlink -f "$z" 2>/dev/null)" = "$(readlink -f "$q")" ] && { echo "  Ziel und Quelle sind derselbe Ort."; return 1; }
  if [ -d "$z" ] && [ -n "$(ls -A "$z" 2>/dev/null)" ] && [ ! -f "$z.ota-umzug" ]; then
    echo "  $z ist nicht leer und keine Vorkopie dieses Skripts — Abbruch für diesen Teil."
    return 1
  fi
  mkdir -p "$(dirname "$z")" || return 1
  case "$(stat -f -c %T "$(dirname "$z")")" in
    btrfs) echo "  Hinweis: Das Ziel liegt auf btrfs — für Datenbanken ist ext4 oder xfs schneller." ;;
    overlayfs) echo "  Das Ziel liegt in einem Overlay — kein Ort für Daten."; return 1 ;;
  esac
  local braucht frei
  braucht=$(du -sk "$q" 2>/dev/null | cut -f1)
  frei=$(df -k --output=avail "$(dirname "$z")" | tail -1)
  if [ "${braucht:-0}" -gt "${frei:-0}" ]; then
    echo "  Zu wenig Platz: $((braucht / 1024)) MB nötig, $((frei / 1024)) MB frei."; return 1
  fi
}

# ------------------------------------------------------------------ Status
zeigen() {
  kopf "Wo die Daten jetzt liegen"
  printf '  %-14s %s\n' db "$(quelle_von ota-db /var/lib/postgresql/data || true)"
  printf '  %-14s %s\n' registry "$(quelle_von ota-registry /var/lib/registry || true)"
  printf '  %-14s %s\n' git "$(quelle_von ota-git /data || echo '(Git ist nicht eingerichtet)')"
  printf '  %-14s %s\n' gedaechtnis "$(quelle_von ota-gedaechtnis-db /var/lib/postgresql/data || echo '(Erweiterung läuft nicht)')"
  local root; root=$(env_lesen "$ENV" OTA_PLATZ_DOCKER_ROOT)
  printf '  %-14s %s\n' platz-docker "${root:-Docker-Volumes}"
  local v
  for v in $(docker volume ls -q --filter label=ota.zweck=docker); do
    printf '      %-48s %s\n' "$v" "$(platz_ort "$v")"
  done
}

# ------------------------------------------------------------------ Root-Arbeitsplätze
# Die Daten eines Volumes: das eingebundene Verzeichnis (neu angelegt unter
# OTA_PLATZ_DOCKER_ROOT) oder das eigene _data — jeweils bis zum Ende eines
# Verweises verfolgt, den ein früherer Umzug dort hinterlassen hat.
platz_anker() { # wo der Verweis hingehört
  local dev; dev=$(docker volume inspect -f '{{index .Options "device"}}' "$1" 2>/dev/null)
  [ -n "$dev" ] && [ "$dev" != "<no value>" ] && { echo "$dev"; return; }
  volume_pfad "$1"
}
platz_ort() { readlink -f "$(platz_anker "$1")"; }
platz_belegt() { # läuft ein Container mit diesem Volume?
  [ -n "$(docker ps -q --filter volume="$1")" ]
}

platz_umziehen() { # <Volume> <Wurzel|volume> — 0: umgeschaltet, 1: Fehler, 2: läuft noch
  local v=$1 wurzel=$2 anker quelle ziel
  anker=$(platz_anker "$v"); quelle=$(readlink -f "$anker")
  if [ "$wurzel" = volume ]; then
    if [ "$anker" != "$(volume_pfad "$v")" ]; then
      echo "  $v wurde schon unter einer Wurzel angelegt — es kann nicht ins Volume zurück, nur an einen anderen Pfad."
      return 1
    fi
    [ -L "$anker" ] || { echo "  $v liegt schon im Volume."; return 0; }
    ziel="$anker.zurueck"
  else
    ziel="$wurzel/$v"
  fi
  [ "$quelle" = "$(readlink -f "$ziel" 2>/dev/null)" ] && { echo "  $v liegt schon dort."; return 0; }
  ziel_pruefen "$ziel" "$quelle" || return 1
  echo "  $v: kopieren …"
  marke "$ziel"
  kopieren "$quelle" "$ziel" || return 1
  [ "$NUR_KOPIEREN" = 1 ] && return 2
  if platz_belegt "$v"; then
    if [ "$wurzel" = volume ]; then
      echo "  $v: Arbeitsplatz läuft — vorkopiert. Zurück ins Volume geht nur angehalten: später erneut aufrufen."
    else
      echo "  $v: Arbeitsplatz läuft — vorkopiert; der Agent schaltet beim nächsten Fortsetzen um."
    fi
    return 2
  fi
  echo "  $v: angehalten — letzter Abgleich und umschalten"
  abgleich "$quelle" "$ziel" "$ziel.ota-umzug" || return 1
  platz_belegt "$v" && { echo "  $v wurde gerade gestartet — beim nächsten Lauf."; return 2; }
  if [ -L "$anker" ]; then
    rm "$anker"
  else
    mv "$anker" "$anker.vor-umzug"
  fi
  if [ "$wurzel" = volume ]; then
    mv "$ziel" "$anker"
  else
    ln -s "$ziel" "$anker"
  fi
  # Die alte Kopie dort, wo sie war (bis --aufraeumen).
  [ "$quelle" != "$anker" ] && [ -d "$quelle" ] && mv "$quelle" "$quelle.vor-umzug"
  rm -f "$ziel.ota-umzug"
  echo "  $v: liegt jetzt in $(platz_ort "$v")"
}

# ------------------------------------------------------------------ Dienste
# <Teil> <Container> <Ziel im Container> <Volume> <.env> <Schlüssel> <Wie neu anlegen> [<Sekunden bis gesund>]
dienst_umziehen() {
  local teil=$1 c=$2 innen=$3 vol=$4 datei=$5 schluessel=$6 neu=$7 frist=${8:-180}
  local wunsch=${ZIEL[$teil]} quelle ziel wert
  kopf "$teil"
  quelle=$(quelle_von "$c" "$innen")
  if [ -z "$quelle" ]; then
    quelle=$(volume_pfad "$vol")
    [ -n "$quelle" ] || {
      echo "  Gibt es hier nicht — nur der Ort wird eingetragen."
      [ "$wunsch" = volume ] && wert="" || { wert=$wunsch; mkdir -p "$wunsch"; }
      [ "$NUR_KOPIEREN" = 1 ] || env_setzen "$datei" "$schluessel" "$wert"
      return 0
    }
  fi
  if [ "$wunsch" = volume ]; then
    docker volume inspect "$vol" >/dev/null 2>&1 || docker volume create "$vol" >/dev/null
    ziel=$(volume_pfad "$vol"); wert=""
    marke "$ziel"
  else
    ziel=$wunsch; wert=$wunsch
  fi
  if [ "$(readlink -f "$quelle")" = "$(readlink -f "$ziel")" ]; then
    echo "  Liegt schon in $ziel."
    env_setzen "$datei" "$schluessel" "$wert"
    return 0
  fi
  [ "$wunsch" = volume ] || ziel_pruefen "$ziel" "$quelle" || return 1
  echo "  Von $quelle"
  echo "  nach $ziel — kopieren im laufenden Betrieb …"
  marke "$ziel"
  kopieren "$quelle" "$ziel" || return 1
  [ "$NUR_KOPIEREN" = 1 ] && { echo "  Vorkopiert."; return 0; }
  fragen "  $teil jetzt umschalten? Der Dienst steht dafür einige Sekunden." || { echo "  Nicht umgeschaltet."; return 0; }
  local lief=0
  laeuft "$c" && lief=1
  [ "$lief" = 1 ] && docker stop -t 30 "$c" >/dev/null
  echo "  Angehalten — letzter Abgleich …"
  if ! abgleich "$quelle" "$ziel" "$ziel.ota-umzug"; then
    echo "  Abgleich gescheitert — der Dienst startet wieder am alten Ort."
    [ "$lief" = 1 ] && docker start "$c" >/dev/null
    return 1
  fi
  local alt; alt=$(env_lesen "$datei" "$schluessel")
  env_setzen "$datei" "$schluessel" "$wert"
  rm -f "$ziel.ota-umzug"
  [ "$lief" = 1 ] || { echo "  Eingetragen; der Dienst lief nicht und startet beim nächsten Mal dort."; return 0; }
  eval "$neu"
  if gesund_warten "$c" "$frist"; then
    echo "  Läuft am neuen Ort. Die alte Kopie bleibt in $quelle, bis --aufraeumen sie löscht."
    case "$quelle" in */volumes/*/_data) ;; *) echo "$quelle" >> "$ALTE_ORTE" ;; esac
  else
    echo "  $c wird nicht gesund — zurück an den alten Ort."
    env_setzen "$datei" "$schluessel" "$alt"
    eval "$neu"
    return 1
  fi
}

[ "$STATUS" = 1 ] && { zeigen; exit 0; }

# ------------------------------------------------------------------ Aufräumen
if [ "$AUFRAEUMEN" = 1 ]; then
  kopf "Alte Kopien"
  for paar in "ota_db_data ota-db /var/lib/postgresql/data" \
              "ota_registry_data ota-registry /var/lib/registry" \
              "ota_git_daten ota-git /data" \
              "ota_gedaechtnis_daten ota-gedaechtnis-db /var/lib/postgresql/data"; do
    set -- $paar
    docker volume inspect "$1" >/dev/null 2>&1 || continue
    [ "$(quelle_von "$2" "$3")" = "$(volume_pfad "$1")" ] && continue   # wird benutzt
    [ -n "$(docker ps -aq --filter volume="$1")" ] && continue
    fragen "  Volume $1 ($(du -sh "$(volume_pfad "$1")" | cut -f1)) wird nicht mehr benutzt — löschen?" &&
      docker volume rm "$1" >/dev/null && echo "  $1 gelöscht."
  done
  for v in $(docker volume ls -q --filter label=ota.zweck=docker); do
    for alt in "$(volume_pfad "$v").vor-umzug" "$(platz_anker "$v").vor-umzug"; do
      [ -d "$alt" ] || continue
      fragen "  $alt ($(du -sh "$alt" | cut -f1)) löschen?" && rm -rf "$alt" && echo "  gelöscht."
    done
  done
  if [ -f "$ALTE_ORTE" ]; then
    BENUTZT=" $(quelle_von ota-db /var/lib/postgresql/data) $(quelle_von ota-registry /var/lib/registry) $(quelle_von ota-git /data) $(quelle_von ota-gedaechtnis-db /var/lib/postgresql/data) "
    BLEIBT=()
    while read -r alt <&3; do
      [ -d "$alt" ] || continue
      case "$BENUTZT" in *" $alt "*) continue ;; esac
      if fragen "  $alt ($(du -sh "$alt" | cut -f1)) wird nicht mehr benutzt — löschen?"; then
        rm -rf "$alt" && echo "  gelöscht."
      else
        BLEIBT+=("$alt")
      fi
    done 3< <(sort -u "$ALTE_ORTE")
    if [ ${#BLEIBT[@]} -gt 0 ]; then printf '%s\n' "${BLEIBT[@]}" > "$ALTE_ORTE"; else rm -f "$ALTE_ORTE"; fi
  fi
  # Vorkopien früherer Wurzeln, deren Volume es nicht mehr gibt.
  for w in $(env_lesen "$ENV" OTA_PLATZ_DOCKER_ROOT); do
    for d in "$w"/ota-platz-docker-*.vor-umzug; do
      [ -d "$d" ] && fragen "  $d löschen?" && rm -rf "$d"
    done
  done
  exit 0
fi

[ ${#ZIEL[@]} -gt 0 ] || { sed -n '2,32p' "$0"; exit 2; }

# ------------------------------------------------------------------ Los
echo "Daten von OTA umziehen — $(date)"
for t in "${TEILE[@]}"; do [ -n "${ZIEL[$t]:-}" ] && printf '  %-14s → %s\n' "$t" "${ZIEL[$t]}"; done
fragen "Weiter?" || exit 0

FEHLER=0
AGENT_NEU=0

# Das Banner (wie bei make update) nur, solange die Datenbank umschaltet.
if [ -n "${ZIEL[db]:-}" ]; then
  [ "$NUR_KOPIEREN" = 1 ] || "$ROOT/scripts/wartung.sh" an
  dienst_umziehen db ota-db /var/lib/postgresql/data ota_db_data "$ENV" OTA_DB_DIR \
    '"${COMPOSE[@]}" up -d --no-deps db >/dev/null' || FEHLER=1
  [ "$NUR_KOPIEREN" = 1 ] || "$ROOT/scripts/wartung.sh" aus
fi
if [ -n "${ZIEL[registry]:-}" ]; then
  dienst_umziehen registry ota-registry /var/lib/registry ota_registry_data "$ENV" OTA_REGISTRY_DIR \
    '"${COMPOSE[@]}" up -d --no-deps registry >/dev/null' || FEHLER=1
fi
if [ -n "${ZIEL[git]:-}" ]; then
  # Den Container von Git legt der Agent an: Er bekommt den neuen Ort und
  # ersetzt den Container, sobald die API nachfragt (beim Start sofort).
  dienst_umziehen git ota-git /data ota_git_daten "$ENV" OTA_GIT_DIR \
    '"${COMPOSE[@]}" up -d --no-deps agent >/dev/null; gesund_warten ota-agent 120; docker restart ota-api >/dev/null' 600 || FEHLER=1
  AGENT_NEU=1
fi
if [ -n "${ZIEL[gedaechtnis]:-}" ]; then
  GD=$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' ota-gedaechtnis-db 2>/dev/null)
  if [ -z "$GD" ] || [ ! -f "$GD/.env" ]; then
    kopf gedaechtnis; echo "  Die Erweiterung läuft hier nicht — übersprungen."
  else
    GP=$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' ota-gedaechtnis-db)
    GC=(docker compose -p "$GP" --project-directory "$GD" --env-file "$GD/.env")
    dienst_umziehen gedaechtnis ota-gedaechtnis-db /var/lib/postgresql/data ota_gedaechtnis_daten \
      "$GD/.env" GEDAECHTNIS_DB_DIR '"${GC[@]}" up -d db >/dev/null' || FEHLER=1
  fi
fi

if [ -n "${ZIEL[platz-docker]:-}" ]; then
  kopf "platz-docker"
  W=${ZIEL[platz-docker]}
  [ "$W" = volume ] || { mkdir -p "$W" && chmod 711 "$W"; }
  OFFEN=()
  for v in $(docker volume ls -q --filter label=ota.zweck=docker); do
    platz_umziehen "$v" "$W"
    case $? in 1) FEHLER=1 ;; 2) OFFEN+=("$v") ;; esac
  done
  [ ${#OFFEN[@]} -eq 0 ] && echo "  Alle Root-Arbeitsplätze sind umgeschaltet."
  if [ "$NUR_KOPIEREN" = 0 ]; then
    # Neue Plätze gleich am neuen Ort. Zurück ins Volume nur, wenn keiner
    # mehr unter der alten Wurzel angelegt ist.
    if [ "$W" = volume ]; then
      ALT=$(env_lesen "$ENV" OTA_PLATZ_DOCKER_ROOT)
      UNTER_WURZEL=0
      for v in $(docker volume ls -q --filter label=ota.zweck=docker); do
        [ "$(platz_anker "$v")" != "$(volume_pfad "$v")" ] && UNTER_WURZEL=1
      done
      if [ -n "$ALT" ] && [ "$UNTER_WURZEL" = 1 ]; then
        echo "  Einige Plätze sind unter $ALT angelegt; OTA_PLATZ_DOCKER_ROOT bleibt gesetzt."
      else
        env_setzen "$ENV" OTA_PLATZ_DOCKER_ROOT ""
      fi
    else
      env_setzen "$ENV" OTA_PLATZ_DOCKER_ROOT "$W"
    fi
    AGENT_NEU=1
  fi
  if [ ${#OFFEN[@]} -gt 0 ]; then
    [ "$NUR_KOPIEREN" = 1 ] && echo "  Vorkopiert: ${OFFEN[*]}" || echo "  Laufend, vorkopiert: ${OFFEN[*]}"
  fi
fi

if [ "$AGENT_NEU" = 1 ] && [ "$NUR_KOPIEREN" = 0 ]; then
  kopf "Agent"
  "${COMPOSE[@]}" up -d --no-deps agent >/dev/null && gesund_warten ota-agent 120 \
    && echo "  Mit dem neuen Ort gestartet." || { echo "  Der Agent wird nicht gesund — 'docker logs ota-agent'."; FEHLER=1; }
fi

zeigen
[ "$FEHLER" = 0 ] || { echo; echo "Nicht alles ist umgezogen — die Meldungen oben."; exit 1; }
