#!/usr/bin/env bash
# /srv/ota komplett auf eine andere Platte ziehen — Zuhause, Laufwerke,
# Ablage, Sicherungen, Laufzeitdaten, Paketquelle. Handbuch, Kapitel 40.
#
#   sudo scripts/srv-umziehen.sh /storage/srv                 umziehen nach /storage/srv/ota
#   sudo scripts/srv-umziehen.sh --nur-kopieren /storage/srv  nur vorkopieren (im laufenden Betrieb)
#   sudo scripts/srv-umziehen.sh --aufraeumen                 alte Kopie löschen (fragt)
#   sudo scripts/srv-umziehen.sh --zurueck                    wieder auf die alte Platte
#
# **Der Pfad bleibt /srv/ota.** Die Daten liegen danach unter <Ziel>/ota, und
# ein Bind-Mount (in /etc/fstab) hängt sie wieder unter /srv/ota ein. An OTA
# ändert sich nichts — und das muss so sein: Angehaltene Root-Arbeitsplätze
# behalten ihren Container, und der kennt sein Zuhause unter /srv/ota/… fest.
# Mit neuen Pfaden in deploy/.env fänden sie es beim Fortsetzen nicht mehr.
#
# Ablauf:
#   1. Vorkopie im laufenden Betrieb (rsync). Dauert, stört niemanden.
#   2. Prüfen, dass kein Arbeitsplatz läuft. Laufende vorher selbst anhalten;
#      angehaltene Root-Arbeitsplätze dürfen bleiben.
#   3. OTA anhalten (nur die Dienste von OTA), letzter Abgleich (Sekunden bis
#      Minuten), /srv/ota → /srv/ota.vor-umzug, Bind-Mount einhängen und in
#      /etc/fstab eintragen, OTA wieder starten. Klappt etwas nicht, wird
#      zurückgedreht.
#   4. Die alte Kopie bleibt liegen, bis --aufraeumen sie löscht. Erst dann
#      ist der Platz auf der alten Platte frei.
#
#   --ja   nicht nachfragen
set -uo pipefail

SRV=/srv/ota
ALT=/srv/ota.vor-umzug

[ "$(id -u)" = 0 ] || { echo "Bitte als root ausführen (sudo)." >&2; exit 1; }
command -v rsync >/dev/null || { echo "rsync fehlt: apt install rsync" >&2; exit 1; }

NUR_KOPIEREN=0 JA=0 AUFRAEUMEN=0 ZURUECK=0 BASIS=""
while [ $# -gt 0 ]; do
  case "$1" in
    --nur-kopieren) NUR_KOPIEREN=1 ;;
    --ja) JA=1 ;;
    --aufraeumen) AUFRAEUMEN=1 ;;
    --zurueck) ZURUECK=1 ;;
    -h|--help) sed -n '2,29p' "$0"; exit 0 ;;
    -*) echo "Unbekannte Option: $1" >&2; exit 1 ;;
    *) BASIS=${1%/} ;;
  esac
  shift
done

kopf() { printf '\n\033[1m== %s ==\033[0m\n' "$1"; }
fragen() {
  [ "$JA" = 1 ] && return 0
  local a; read -r -p "$1 [j/N] " a; [ "$a" = j ] || [ "$a" = J ]
}
eingehaengt() { mountpoint -q "$SRV"; }
fstab_zeile() { awk -v z="$SRV" '$2 == z && $0 !~ /^#/' /etc/fstab; }

# ------------------------------------------------------------ Container
# Wer hat etwas unter /srv/ota eingehängt und läuft (oder ist pausiert)?
nutzer_von_srv() {
  local c
  for c in $(docker ps -q); do
    docker inspect -f '{{.Name}}|{{index .Config.Labels "com.docker.compose.project"}}|{{index .Config.Labels "ota.session_id"}}|{{range .Mounts}}{{.Source}} {{end}}' "$c"
  done | awk -F'|' -v s="$SRV" '{ n = split($4, m, " "); for (i = 1; i <= n; i++) if (m[i] == s || index(m[i], s "/") == 1) { print; break } }'
}
# Die Dienste von OTA: das Compose-Projekt „ota" und OTA-Git (legt der Agent an).
ota_dienste() {
  docker ps -q --filter label=com.docker.compose.project=ota
  docker ps -q --filter name='^ota-git$'
}
GESTOPPT=()
ota_anhalten() {
  mapfile -t GESTOPPT < <(ota_dienste | sort -u)
  [ ${#GESTOPPT[@]} -eq 0 ] && return 0
  echo "  Halte ${#GESTOPPT[@]} Dienste von OTA an …"
  docker stop -t 60 "${GESTOPPT[@]}" >/dev/null
}
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
ota_starten() {
  [ ${#GESTOPPT[@]} -eq 0 ] && return 0
  echo "  Starte OTA wieder …"
  # Erst die Datenbank, dann der Rest — sonst geben API und Keycloak auf.
  docker start ota-db >/dev/null 2>&1 && gesund_warten ota-db 120
  docker start "${GESTOPPT[@]}" >/dev/null || return 1
  local c ok=0
  for c in ota-db ota-api ota-agent; do
    docker inspect "$c" >/dev/null 2>&1 || continue
    if gesund_warten "$c" 240; then echo "  $c: bereit"; else echo "  $c: nicht bereit"; ok=1; fi
  done
  return $ok
}

# ------------------------------------------------------------ Kopieren
kopieren() { # <Quelle> <Ziel>
  mkdir -p "$2"
  local fortschritt=() rc=0
  [ -t 1 ] && fortschritt=(--info=progress2 --no-inc-recursive)
  rsync -aHAXS --numeric-ids --delete "${fortschritt[@]}" "$1"/ "$2"/ || rc=$?
  # 24: Dateien verschwanden während des Kopierens — im laufenden Betrieb normal.
  [ "$rc" = 24 ] && { echo "  (Einige Dateien verschwanden beim Kopieren — im laufenden Betrieb normal.)"; rc=0; }
  return "$rc"
}
# Der letzte Abgleich, OTA steht. rsync vergleicht nur Größe und Zeit auf die
# Sekunde; deshalb zusätzlich jede Datei neu, deren ctime jünger ist als der
# Beginn der ersten Vorkopie (wie in daten-umziehen.sh).
abgleich() { # <Quelle> <Ziel> <Marke>
  kopieren "$1" "$2" >/dev/null || return 1
  (cd "$1" && find . -newercm "$3" \( -type f -o -type l \) -print0) \
    | rsync -aHAXS --numeric-ids -I --from0 --files-from=- "$1"/ "$2"/
}
unterschiede() { # <Quelle> <Ziel> — wie viele Einträge noch abweichen
  rsync -aHAXS --numeric-ids --delete -n --itemize-changes "$1"/ "$2"/ \
    | grep -v '^\.d\.\.t\.\.\.\.\.\. ' | grep -c . || true
}

# ------------------------------------------------------------ Einhängen
einhaengen() { # <Daten>
  local daten=$1
  mkdir -p "$SRV" && chmod 755 "$SRV"
  # Fehlt beim Booten die große Platte, bliebe /srv/ota ein leeres Verzeichnis
  # auf der Systemplatte, und OTA legte dort frische, leere Zuhause an. Das
  # unveränderliche Verzeichnis darunter lässt das scheitern, statt es still
  # zu tun.
  chattr +i "$SRV" 2>/dev/null || echo "  (chattr +i ging nicht — kein Schutz gegen leeres /srv/ota beim Booten)"
  local vorher; vorher=$(stat -c %m "$daten" 2>/dev/null)
  local optionen=bind
  [ -n "$vorher" ] && [ "$vorher" != / ] && optionen="bind,x-systemd.requires-mounts-for=$vorher"
  [ -n "$(fstab_zeile)" ] || {
    cp /etc/fstab /etc/fstab.vor-srv-umzug
    printf '# OTA: Daten liegen auf %s (scripts/srv-umziehen.sh)\n%s %s none %s 0 0\n' \
      "$daten" "$daten" "$SRV" "$optionen" >> /etc/fstab
  }
  systemctl daemon-reload 2>/dev/null || true
  mount "$SRV"
}
aushaengen() {
  eingehaengt && umount "$SRV"
  if [ -n "$(fstab_zeile)" ]; then
    sed -i -e '\|^# OTA: Daten liegen auf .*srv-umziehen|d' \
           -e "\|^[^#][^ ]* $SRV none bind|d" /etc/fstab
  fi
  systemctl daemon-reload 2>/dev/null || true
  [ -d "$SRV" ] && { chattr -i "$SRV" 2>/dev/null; rmdir "$SRV"; }
}

# ------------------------------------------------------------ Aufräumen
if [ "$AUFRAEUMEN" = 1 ]; then
  [ -d "$ALT" ] || { echo "Keine alte Kopie ($ALT) da."; exit 0; }
  eingehaengt || { echo "$SRV ist nicht eingehängt — die alte Kopie ist noch die einzige. Abbruch."; exit 1; }
  echo "Alte Kopie: $ALT ($(du -sh "$ALT" 2>/dev/null | cut -f1))"
  echo "Die Daten liegen jetzt auf $(findmnt -no SOURCE "$SRV")."
  fragen "Alte Kopie endgültig löschen?" || exit 0
  rm -rf --one-file-system "$ALT" && echo "Gelöscht."
  exit 0
fi

# ------------------------------------------------------------ Zurück
if [ "$ZURUECK" = 1 ]; then
  eingehaengt || { echo "$SRV ist kein Bind-Mount — nichts zurückzudrehen."; exit 0; }
  kopf "Zurück auf die Systemplatte"
  echo "Die Daten wandern von $(findmnt -no SOURCE "$SRV") zurück nach $SRV."
  [ -n "$(nutzer_von_srv | awk -F'|' '$2 != "ota" && $1 != "/ota-git"')" ] && {
    echo "Es laufen noch Arbeitsplätze:"; nutzer_von_srv | awk -F'|' '$2 != "ota" && $1 != "/ota-git" {print "  " $1}'
    echo "Bitte erst anhalten."; exit 1; }
  fragen "OTA dafür kurz anhalten?" || exit 0
  ziel=$ALT
  [ -d "$ziel" ] || ziel=/srv/ota.zurueck
  marke=$ziel.ota-umzug; [ -f "$marke" ] || touch "$marke"
  kopieren "$SRV" "$ziel" || exit 1
  ota_anhalten
  abgleich "$SRV" "$ziel" "$marke" || { ota_starten; exit 1; }
  aushaengen
  mv "$ziel" "$SRV" && rm -f "$marke"
  ota_starten || echo "OTA ist nicht vollständig hochgekommen — bitte docker ps prüfen."
  echo "Fertig. Die Kopie auf der großen Platte liegt noch unter dem Mount-Quellpfad; löschen von Hand, wenn alles läuft."
  exit 0
fi

# ------------------------------------------------------------ Umziehen
[ -n "$BASIS" ] || { echo "Ziel fehlt, z. B.: sudo $0 /storage/srv" >&2; exit 1; }
case "$BASIS" in /*) ;; *) echo "Bitte einen absoluten Pfad angeben." >&2; exit 1 ;; esac
DATEN=$BASIS/ota
MARKE=$DATEN.ota-umzug

eingehaengt && { echo "$SRV ist schon eingehängt ($(findmnt -no SOURCE "$SRV")) — der Umzug ist bereits erledigt."; exit 0; }
[ -d "$SRV" ] || { echo "$SRV gibt es nicht." >&2; exit 1; }
[ -L "$SRV" ] && { echo "$SRV ist ein Verweis — bitte von Hand klären." >&2; exit 1; }
[ -e "$ALT" ] && { echo "$ALT gibt es schon — ein früherer Umzug? Bitte erst klären." >&2; exit 1; }
case "$(readlink -f "$BASIS" 2>/dev/null || echo "$BASIS")/" in
  "$SRV"/*) echo "Das Ziel liegt in $SRV selbst." >&2; exit 1 ;;
esac
mkdir -p "$BASIS" || exit 1
if [ -d "$DATEN" ] && [ -n "$(ls -A "$DATEN")" ] && [ ! -f "$MARKE" ]; then
  echo "$DATEN ist nicht leer und keine Vorkopie dieses Skripts. Abbruch." >&2; exit 1
fi
[ "$(stat -c %d "$BASIS")" = "$(stat -c %d "$SRV")" ] && \
  echo "Hinweis: $BASIS liegt auf derselben Platte wie $SRV — Platz wird so nicht frei."
case "$(stat -f -c %T "$BASIS")" in
  overlayfs) echo "Das Ziel liegt in einem Overlay — kein Ort für Daten." >&2; exit 1 ;;
  nfs*|cifs|smb*|fuse*) echo "Hinweis: Das Ziel ist ein Netzlaufwerk ($(stat -f -c %T "$BASIS")). Besitzer, xattrs und Docker-Daten der Root-Arbeitsplätze brauchen ein lokales Dateisystem (ext4/xfs)." ;;
esac

kopf "Umzug von $SRV nach $DATEN"
braucht=$(du -sk "$SRV" 2>/dev/null | cut -f1)
schon=0; [ -d "$DATEN" ] && schon=$(du -sk "$DATEN" 2>/dev/null | cut -f1)
frei=$(df -k --output=avail "$BASIS" | tail -1)
echo "  Belegt: $((braucht / 1024 / 1024)) GB, frei am Ziel: $((frei / 1024 / 1024)) GB"
if [ "$((braucht - schon))" -gt "$frei" ]; then echo "Zu wenig Platz am Ziel." >&2; exit 1; fi

kopf "1. Vorkopie im laufenden Betrieb"
[ -f "$MARKE" ] || touch "$MARKE"
kopieren "$SRV" "$DATEN" || { echo "Kopieren fehlgeschlagen." >&2; exit 1; }
if [ "$NUR_KOPIEREN" = 1 ]; then
  echo; echo "Vorkopie fertig. Umschalten später mit: sudo $0 $BASIS"
  exit 0
fi

kopf "2. Laufen noch Arbeitsplätze?"
fremd=$(nutzer_von_srv | awk -F'|' '$2 != "ota" && $1 != "/ota-git"')
if [ -n "$fremd" ]; then
  echo "Diese Container nutzen $SRV und laufen noch:"
  echo "$fremd" | awk -F'|' '{print "  " substr($1, 2) ($3 != "" ? "  (Arbeitsplatz)" : "")}'
  echo "Bitte anhalten (Betrieb → Arbeitsplätze) und das Skript erneut starten."
  echo "Die Vorkopie bleibt; der nächste Lauf ist schneller."
  exit 1
fi
echo "  Keiner. Angehaltene Root-Arbeitsplätze finden ihr Zuhause danach am selben Pfad."

kopf "3. Umschalten"
echo "OTA ist dafür kurz nicht erreichbar (je nach Änderungen seit der Vorkopie Sekunden bis Minuten)."
fragen "Jetzt umschalten?" || exit 0

ota_anhalten
# Noch einmal: In der Zwischenzeit könnte jemand einen Platz gestartet haben.
fremd=$(nutzer_von_srv)
if [ -n "$fremd" ]; then
  echo "Nach dem Anhalten nutzen noch Container $SRV:"; echo "$fremd" | awk -F'|' '{print "  " substr($1, 2)}'
  ota_starten; exit 1
fi

zurueckdrehen() {
  echo "Drehe zurück …"
  local laufend; laufend=$(ota_dienste | sort -u)
  [ -n "$laufend" ] && docker stop $laufend >/dev/null
  if [ -d "$ALT" ]; then aushaengen; mv "$ALT" "$SRV"; fi
  ota_starten
  echo "OTA läuft wieder vom alten Ort. Die Kopie unter $DATEN bleibt (Marke: $MARKE)."
  exit 1
}

echo "  Letzter Abgleich …"
abgleich "$SRV" "$DATEN" "$MARKE" || { echo "Abgleich fehlgeschlagen."; ota_starten; exit 1; }
rest=$(unterschiede "$SRV" "$DATEN")
if [ "$rest" != 0 ]; then
  echo "  Nach dem Abgleich weichen noch $rest Einträge ab — Abbruch, nichts umgeschaltet."
  rsync -aHAXS --numeric-ids --delete -n --itemize-changes "$SRV"/ "$DATEN"/ | head -20
  ota_starten; exit 1
fi
echo "  Ziel stimmt mit $SRV überein."

mv "$SRV" "$ALT" || { ota_starten; exit 1; }
einhaengen "$DATEN" || zurueckdrehen
eingehaengt && [ -d "$SRV/profiles" ] || zurueckdrehen
echo "  $SRV kommt jetzt von $DATEN."
rm -f "$MARKE"

ota_starten || zurueckdrehen

kopf "Fertig"
cat <<EOF
  Daten:          $DATEN
  Eingehängt:     $SRV (Bind-Mount, Eintrag in /etc/fstab; Sicherung: /etc/fstab.vor-srv-umzug)
  Alte Kopie:     $ALT — belegt die Systemplatte noch.

Bitte jetzt einen Arbeitsplatz starten und prüfen, ob das Zuhause da ist.
Läuft alles, gibt dies den Platz frei:

  sudo $0 --aufraeumen

Zurück ginge es, solange die alte Kopie da ist, mit: sudo $0 --zurueck
EOF
