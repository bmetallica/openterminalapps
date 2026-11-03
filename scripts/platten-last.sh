#!/usr/bin/env bash
# Wer belastet die Platte? Misst eine Weile, wie viel jeder Prozess liest und
# schreibt, fasst das je Container zusammen und zeigt, was das Dateisystem im
# Hintergrund tut. Ändert nichts — nur lesen und zählen.
#
#   sudo scripts/platten-last.sh                 /storage, 30 Sekunden
#   sudo scripts/platten-last.sh /pfad 60        anderer Ort, andere Dauer
#
# Die Zähler je Prozess (/proc/<pid>/io) gelten für alle Platten zusammen;
# die Auslastung darunter gilt nur für die Platte unter <Pfad>.
# Prozesse, die während der Messung enden, fehlen in der Tabelle.
set -uo pipefail

[ "$(id -u)" = 0 ] || { echo "Bitte als root ausführen (sudo)." >&2; exit 1; }
ORT=${1:-/storage}
DAUER=${2:-30}
BERICHT="/tmp/platten-last-$(date +%Y%m%d-%H%M%S).txt"
exec > >(tee "$BERICHT") 2>&1
kopf() { printf '\n\033[1m== %s ==\033[0m\n' "$1"; }
z() { timeout "${2:-30}" bash -c "$1" 2>&1 || echo "(abgebrochen oder Fehler: $?)"; }

QUELLE=$(findmnt -no SOURCE -T "$ORT" | sed 's/\[.*//')
FSTYP=$(findmnt -no FSTYPE -T "$ORT")
MNT=$(findmnt -no TARGET -T "$ORT")
DEV=$(basename "$(readlink -f "$QUELLE")")
echo "Plattenlast $(hostname) — $(date)"
echo "Ort: $ORT  →  $QUELLE ($FSTYP, eingehängt auf $MNT), Messdauer $DAUER s"

# Container-ID → Name, für die Zuordnung über die cgroup eines Prozesses.
NAMEN=$(timeout 30 docker ps --no-trunc --format '{{.ID}} {{.Names}}' 2>/dev/null)

# Je Prozess: PID, gelesene und geschriebene Bytes, Gruppe (Container oder Wirt).
schnappschuss() {
  local p id
  for p in /proc/[0-9]*; do
    [ -r "$p/io" ] || continue
    id=$(grep -oE '[0-9a-f]{64}' "$p/cgroup" 2>/dev/null | head -1)
    awk -v pid="${p#/proc/}" -v id="${id:-}" -v comm="$(cat "$p/comm" 2>/dev/null)" '
      /^read_bytes:/ {r=$2} /^write_bytes:/ {w=$2}
      END { if (r != "") print pid, r, w, (id == "" ? "-" : id), comm }' "$p/io" 2>/dev/null
  done
}
platte() { awk -v d="$DEV" '$3 == d {print $4, $6, $7, $8, $10, $11, $13}' /proc/diskstats; }

kopf "Messen ($DAUER s) …"
D_PROBEN=""
A=$(schnappschuss); PA=$(platte); TA=$(date +%s%N)
for ((i = 0; i < DAUER; i += 5)); do
  sleep 5
  # Prozesse, die gerade auf die Platte warten (Zustand D), und worauf.
  D_PROBEN+=$(ps -eo stat=,comm=,wchan:32= | awk '$1 ~ /^D/ {print $2, $3}')$'\n'
done
E=$(schnappschuss); PE=$(platte); TE=$(date +%s%N)
SEK=$(( (TE - TA) / 1000000000 )); [ "$SEK" -gt 0 ] || SEK=1

kopf "Platte $DEV in diesen $SEK s"
read -r r1 sr1 mr1 w1 sw1 mw1 io1 <<<"$PA"
read -r r2 sr2 mr2 w2 sw2 mw2 io2 <<<"$PE"
LC_ALL=C awk -v s="$SEK" -v r=$((r2 - r1)) -v sr=$((sr2 - sr1)) -v mr=$((mr2 - mr1)) \
  -v w=$((w2 - w1)) -v sw=$((sw2 - sw1)) -v mw=$((mw2 - mw1)) -v io=$((io2 - io1)) 'BEGIN {
  printf "  Lesen:      %6.1f Vorgänge/s  %7.2f MB/s  Wartezeit je Vorgang %6.1f ms\n", r/s, sr*512/s/1e6, (r ? mr/r : 0)
  printf "  Schreiben:  %6.1f Vorgänge/s  %7.2f MB/s  Wartezeit je Vorgang %6.1f ms\n", w/s, sw*512/s/1e6, (w ? mw/w : 0)
  printf "  Auslastung: %5.0f %% der Zeit beschäftigt\n", io/(s*10)
}'
AUSL=$(( (io2 - io1) / (SEK * 10) ))

kopf "Wer liest und schreibt am meisten (alle Platten, je Container zusammengefasst)"
{ echo "$NAMEN" | sed "s/^/N /"; echo "$A" | sed "s/^/A /"; echo "$E" | sed "s/^/E /"; } |
LC_ALL=C awk -v s="$SEK" '
  $1 == "N" { name[$2] = $3; next }
  $1 == "A" { ar[$2] = $3; aw[$2] = $4; next }
  $1 == "E" {
    pid = $2; id = $5; comm = $6
    if (!(pid in ar)) { ar[pid] = 0; aw[pid] = 0 }   # neu entstanden
    dr = $3 - ar[pid]; dw = $4 - aw[pid]
    if (dr < 0) dr = 0; if (dw < 0) dw = 0
    g = (id == "-") ? "Wirt: " comm : ((id in name) ? "Container " name[id] : "Container " substr(id, 1, 12))
    R[g] += dr; W[g] += dw
    if (id != "-") { k = g " / " comm; PR[k] += dr; PW[k] += dw }
  }
  END {
    for (g in R) if (R[g] + W[g] > 0) printf "%14.0f %10.2f %10.2f  %s\n", R[g] + W[g], R[g]/s/1e6, W[g]/s/1e6, g
    print "--"
    for (k in PR) if (PR[k] + PW[k] > 0) printf "%14.0f %10.2f %10.2f  %s\n", PR[k] + PW[k], PR[k]/s/1e6, PW[k]/s/1e6, k
  }' > /tmp/.platten-last-$$
printf '  %10s %10s  %s\n' "Lesen MB/s" "Schr. MB/s" "Wer"
sed '/^--$/,$d' /tmp/.platten-last-$$ | sort -rn | head -20 | awk '{ $1 = ""; printf "  %10s %10s  ", $2, $3; $2 = $3 = ""; sub(/^ +/, ""); print }'
kopf "Innerhalb der Container: welche Prozesse"
sed '1,/^--$/d' /tmp/.platten-last-$$ | sort -rn | head -15 | awk '{ $1 = ""; printf "  %10s %10s  ", $2, $3; $2 = $3 = ""; sub(/^ +/, ""); print }'
rm -f /tmp/.platten-last-$$

kopf "Warten auf die Platte (Zustand D, alle 5 s gezählt)"
echo "$D_PROBEN" | awk 'NF {print}' | sort | uniq -c | sort -rn | head -15
[ -z "$(echo "$D_PROBEN" | tr -d '[:space:]')" ] && echo "  (keiner)"

if [ "$FSTYP" = btrfs ]; then
  kopf "btrfs auf $MNT"
  z "findmnt -no OPTIONS '$MNT'"
  echo "-- Hintergrundarbeit:"
  z "btrfs balance status '$MNT'"
  z "btrfs scrub status '$MNT' | grep -iE 'status|started|duration|rate'"
  echo "-- Quotas (kosten bei vielen Dateien und Snapshots sehr viel):"
  QG=$(timeout 30 btrfs qgroup show "$MNT" 2>&1 | head -3)
  echo "$QG"
  echo "-- Subvolumes und Snapshots:"
  SUB=$(timeout 60 btrfs subvolume list "$MNT" 2>/dev/null | wc -l)
  SNAP=$(timeout 60 btrfs subvolume list -s "$MNT" 2>/dev/null | wc -l)
  echo "  $SUB Subvolumes, davon $SNAP Snapshots"
  echo "-- Belegung (Metadaten fast voll = langsam):"
  z "btrfs filesystem usage -T '$MNT' | sed -n '1,25p'" 60
  echo "-- Kernel-Threads von btrfs (CPU-Zeit seit Start):"
  z "ps -eo pid,stat,time,comm | awk 'NR == 1 || /btrfs/'"
fi

kopf "Ergebnis"
HIN=()
[ "${AUSL:-0}" -ge 80 ] && HIN+=("Die Platte war ${AUSL} % der Zeit beschäftigt — sie ist am Limit. Wer sie füllt, steht oben.")
[ "${AUSL:-0}" -lt 30 ] && HIN+=("Die Platte war nur ${AUSL} % der Zeit beschäftigt. Ist sie trotzdem langsam, liegt es eher an der Platte selbst oder am Hypervisor (Cache-Modus, andere VMs auf derselben Platte).")
if [ "$FSTYP" = btrfs ]; then
  echo "$QG" | grep -qiE 'not enabled|nicht aktiviert' || [ -z "$QG" ] ||
    HIN+=("btrfs-Quotas sind eingeschaltet. Bei vielen Dateien und Snapshots macht das jedes Schreiben teuer. Abschalten (btrfs quota disable $MNT) nur nach Prüfung, ob etwas sie braucht.")
  [ "${SNAP:-0}" -gt 50 ] && HIN+=("$SNAP btrfs-Snapshots — jeder hält alte Blöcke fest und macht Schreiben und Löschen teurer (snapper, timeshift?).")
  timeout 30 btrfs balance status "$MNT" 2>/dev/null | grep -qi 'running' && HIN+=("Ein btrfs-Balance läuft — das belastet die Platte stark.")
  timeout 30 btrfs scrub status "$MNT" 2>/dev/null | grep -qiE 'status:\s+running' && HIN+=("Ein btrfs-Scrub läuft — das liest die ganze Platte.")
  findmnt -no OPTIONS "$MNT" | grep -q autodefrag && HIN+=("btrfs ist mit autodefrag eingehängt — bei Datenbanken und VM-Abbildern schreibt das ständig um.")
fi
if [ ${#HIN[@]} -eq 0 ]; then
  echo "  Nichts Eindeutiges. Die Tabellen oben zeigen, wer die Platte nutzt."
else
  printf '  • %s\n' "${HIN[@]}"
fi
echo
echo "Bericht: $BERICHT"
