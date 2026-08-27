#!/usr/bin/env bash
# Kopiert ein Kasm-Profil in einen OTA-Arbeitsplatz.
#
# KOPIERT, nicht verschoben: Kasm bleibt danach unangetastet lauffähig und
# ist weiterhin die Rückfallebene. Das Skript ist idempotent — ein zweiter
# Lauf gleicht nur die Unterschiede ab.
#
#   ./scripts/migrate-kasm-profile.sh --dry-run bmetallica
#   ./scripts/migrate-kasm-profile.sh bmetallica
#   ./scripts/migrate-kasm-profile.sh --verify bmetallica

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
set -a; [ -f "$ROOT/deploy/.env" ] && . "$ROOT/deploy/.env"; set +a

KASM_ROOT="${KASM_PROFILES_ROOT:-/srv/kasm_profiles}"
OTA_ROOT="${OTA_PROFILES_ROOT:-/srv/ota/profiles}"
SCOPE="${OTA_PROFILE_SCOPE:-user}"

DRY=0; VERIFY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1; shift ;;
    --verify)  VERIFY=1; shift ;;
    -*) echo "Unbekannte Option: $1"; exit 1 ;;
    *) USERNAME="$1"; shift ;;
  esac
done

[ -n "${USERNAME:-}" ] || { echo "Aufruf: $0 [--dry-run|--verify] <benutzername>"; exit 1; }

SRC="$KASM_ROOT/$USERNAME"
DST="$OTA_ROOT/$USERNAME/$SCOPE"

red() { printf '\033[31m%s\033[0m\n' "$*"; }
grn() { printf '\033[32m%s\033[0m\n' "$*"; }
inf() { printf '  %s\n' "$*"; }

[ -d "$SRC" ] || { red "Kein Kasm-Profil unter $SRC"; exit 1; }

command -v rsync >/dev/null 2>&1 || {
  red "rsync fehlt."
  echo "  Es wird für den Abgleich gebraucht — cp kann weder Ausschlüsse noch"
  echo "  erweiterte Attribute und wäre bei einem zweiten Lauf nicht idempotent."
  echo "  Nachinstallieren:  apt-get install -y rsync"
  exit 1
}

# Was nicht mitkommt. Alles davon ist neu erzeugbar, gehört einer anderen
# Installation oder wäre nach dem Umzug sogar schädlich.
EXCLUDES=(
  # Caches — bei Editor- und Browserprofilen der grösste Posten
  '.cache/' '*/Cache/' '*/Cache_Data/' '*/CachedData/' '*/CachedProfilesData/'
  '*/Code Cache/' '*/GPUCache/' '*/ShaderCache/' '*/GrShaderCache/'
  '*/DawnCache/' '*/blob_storage/' '*/Crash Reports/' '*/logs/'
  '__pycache__/' 'node_modules/'
  # Service-Worker-Cache der Editor-Erweiterungen. Im gemessenen Profil der
  # mit Abstand grösste Posten (193 MB) und vollständig nachladbar. Der Rest
  # von WebStorage — IndexedDB, LocalStorage — kommt mit, dort steht echter
  # Zustand von Erweiterungen.
  '*/CacheStorage/'
  # Heruntergeladene Erweiterungspakete, jederzeit neu beziehbar
  '*/CachedExtensionVSIXs/'
  # Von Chrome nachgeladene Modelle und Listen — zusammen über 90 MB
  '*/component_crx_cache/' '*/WasmTtsEngine/' '*/Safe Browsing/'
  '*/OnDeviceHeadSuggestModel/' '*/optimization_guide_model_store/'
  '*/Dictionaries/'
  # Absturzabbild aus einer alten Sitzung
  'core.*'
  # Laufzeitkram, der zur alten Sitzung gehört und im neuen Container stört
  '.Xauthority' '.ICEauthority' '*.sock' '*.lock' '.X11-unix/'
  # KasmVNC-Zugangsdaten: OTA vergibt pro Session ein eigenes Geheimnis.
  # Das alte mitzunehmen wäre schlicht falsch.
  '.kasmpasswd' '.vnc/'
)

RSYNC_ARGS=(-aHAX --info=stats2 --human-readable)
for e in "${EXCLUDES[@]}"; do RSYNC_ARGS+=(--exclude="$e"); done

echo
echo "Kasm-Profil nach OTA übernehmen"
echo "────────────────────────────────────────────────────────"
inf "Nutzer:  $USERNAME"
inf "Quelle:  $SRC  ($(du -sh "$SRC" 2>/dev/null | cut -f1))"
inf "Ziel:    $DST"

# ------------------------------------------------------------------ prüfen
if [ "$VERIFY" = "1" ]; then
  echo
  echo "Abnahme"
  fail=0
  chk() { if eval "$2" >/dev/null 2>&1; then printf '  \033[32m✓\033[0m %s\n' "$1"; else printf '  \033[31m✗\033[0m %s\n' "$1"; fail=1; fi }

  chk "Profil vorhanden"                    "[ -d '$DST' ]"
  chk "VS-Code-Einstellungen übernommen"    "[ -f '$DST/.config/Code/User/settings.json' ]"
  chk "Extensions übernommen"               "[ -d '$DST/.vscode/extensions' ]"
  chk "SSH-Schlüssel übernommen"            "[ -d '$DST/.ssh' ]"
  chk "GPG-Verzeichnis übernommen"          "[ -d '$DST/.gnupg' ]"
  chk "XFCE-Einstellungen übernommen"       "[ -d '$DST/.config/xfce4' ]"
  chk "Continue-Konfiguration übernommen"   "[ -d '$DST/.continue' ]"
  chk "Kein Absturzabbild mitgekommen"      "! ls '$DST'/core.* 2>/dev/null | grep -q ."
  chk "Kein altes VNC-Passwort mitgekommen" "[ ! -f '$DST/.kasmpasswd' ]"
  chk "Eigentümer ist 1000:1000"            "[ \"\$(stat -c '%u:%g' '$DST')\" = '1000:1000' ]"

  if [ -f "$DST/.config/Code/User/settings.json" ]; then
    echo
    inf "Inhalt von settings.json:"
    sed 's/^/    /' "$DST/.config/Code/User/settings.json" | head -20
  fi
  echo
  [ "$fail" = "0" ] && grn "Abnahme bestanden." || red "Abnahme unvollständig."
  exit "$fail"
fi

# ------------------------------------------------------------ Probedurchlauf
if [ "$DRY" = "1" ]; then
  echo
  echo "Probelauf — es wird nichts geschrieben"
  rsync "${RSYNC_ARGS[@]}" --dry-run "$SRC/" "$DST/" | tail -14
  echo
  inf "Ohne --dry-run wird tatsächlich kopiert."
  exit 0
fi

# ------------------------------------------------------------------ warnen
if docker ps --filter "label=ota.session_id" --format '{{.Names}}' | grep -q .; then
  red "Es läuft mindestens eine OTA-Session."
  echo "  Ein Profil unter einem geöffneten Editor auszutauschen führt auf beiden"
  echo "  Seiten zu Datenverlust. Beende die Sessions zuerst."
  exit 1
fi

# ------------------------------------------------------------------- sichern
if [ -d "$DST" ] && [ -n "$(ls -A "$DST" 2>/dev/null)" ]; then
  ASIDE="$DST.vor-migration-$(date -u +%Y-%m-%dT%H-%M-%SZ)"
  echo
  echo "1/3  Bisheriges OTA-Profil beiseitelegen"
  mv "$DST" "$ASIDE"
  inf "liegt unter $ASIDE"
fi

echo
echo "2/3  Kopieren"
mkdir -p "$DST"
rsync "${RSYNC_ARGS[@]}" "$SRC/" "$DST/" | tail -8

echo
echo "3/3  Eigentümer setzen"
# Die Kasm-Images laufen als Nutzer 1000; ohne das kann der Container nicht
# in sein eigenes Home schreiben.
chown -R 1000:1000 "$DST"
inf "$(stat -c '%u:%g' "$DST") auf $(find "$DST" | wc -l) Einträgen"

echo
grn "Übernommen: $(du -sh "$DST" | cut -f1) — Kasm bleibt unverändert."
echo "  Prüfen mit:  $0 --verify $USERNAME"
