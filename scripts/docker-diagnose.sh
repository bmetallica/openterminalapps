#!/usr/bin/env bash
# Warum ist Docker auf diesem Wirt so langsam? Sammelt, misst und gibt am Ende
# Hinweise. Ändert nichts — nur lesen, zählen, messen.
#
#   sudo scripts/docker-diagnose.sh            Bericht auf den Bildschirm
#                                              und nach /tmp/docker-diagnose-<Zeit>.txt
#
# Jeder Befehl hat ein Zeitlimit, damit ein hängendes Docker das Skript nicht
# mit aufhält. Dauert ein einfacher Aufruf wie `docker ps` Sekunden, steht das
# schon in der ersten Messung.
set -uo pipefail

[ "$(id -u)" = 0 ] || { echo "Bitte als root ausführen (sudo), sonst fehlen Protokolle und Zähler." >&2; exit 1; }
BERICHT="/tmp/docker-diagnose-$(date +%Y%m%d-%H%M%S).txt"
exec > >(tee "$BERICHT") 2>&1

HINWEISE=()
hinweis() { HINWEISE+=("$1"); }
kopf() { printf '\n\033[1m== %s ==\033[0m\n' "$1"; }
z() { timeout "${2:-30}" bash -c "$1" 2>&1 || echo "(abgebrochen oder Fehler: $?)"; }
# messen <Name> <Befehl>: Dauer in Millisekunden
messen() {
  local beginn ende
  beginn=$(date +%s%N)
  timeout 120 bash -c "$2" >/dev/null 2>&1
  ende=$(date +%s%N)
  local ms=$(( (ende - beginn) / 1000000 ))
  printf '  %-34s %7d ms%s\n' "$1" "$ms" "$([ $code -eq 124 ] && echo '   (nach 120 s abgebrochen!)')" >&2
  echo "$ms"
}

echo "Docker-Diagnose $(hostname) — $(date)"

# ------------------------------------------------------------------ Antwortzeiten
kopf "Antwortzeiten von Docker (normal: unter 200 ms, info unter 1 s)"
T_PS=$(messen "docker ps" "docker ps -q")
messen "docker ps -a" "docker ps -aq" >/dev/null
T_NET=$(messen "docker network ls" "docker network ls -q")
T_INFO=$(messen "docker info" "docker info")
messen "docker inspect (bis 50 laufende)" 'docker ps -q | head -50 | xargs -r docker inspect' >/dev/null
T_DF=$(messen "docker system df" "docker system df")
[ "${T_PS:-0}" -gt 2000 ] && hinweis "docker ps braucht ${T_PS} ms — der Daemon selbst ist langsam (siehe Last, Platte, dockerd)."
[ "${T_INFO:-0}" -gt 5000 ] && hinweis "docker info braucht ${T_INFO} ms."
[ "${T_DF:-0}" -gt 10000 ] && hinweis "docker system df braucht $((T_DF / 1000)) s — Docker rechnet dafür die Größe jeder Schicht aus; das ist langsam bei langsamer Platte oder viel Build-Cache. OTA fragt die Größe von Arbeitsplätzen auf dieselbe Weise ab."
[ "${T_NET:-0}" -gt 2000 ] && hinweis "docker network ls braucht ${T_NET} ms — viele Netze oder ein überlasteter Daemon."

# ------------------------------------------------------------------ System
kopf "System"
z "uptime"
CPUS=$(nproc)
echo "CPUs: $CPUS"
LAST=$(cut -d' ' -f1 /proc/loadavg)
awk -v l="$LAST" -v c="$CPUS" 'BEGIN { exit !(l > c * 1.5) }' && hinweis "Last $LAST bei $CPUS CPUs — der Wirt ist überlastet."
z "free -h"
SWAP_BELEGT=$(free -m | awk '/^Swap:/ {print $3}')
# Belegter Swap allein sagt wenig: Der Kernel lagert selten Genutztes auch
# bei freiem RAM aus. Knapp ist es erst, wenn kaum Speicher verfügbar ist.
VERF_PROZENT=$(awk '/^MemTotal:/ {t=$2} /^MemAvailable:/ {a=$2} END {print int(a * 100 / t)}' /proc/meminfo)
if [ "${SWAP_BELEGT:-0}" -gt 1024 ] && [ "${VERF_PROZENT:-100}" -lt 15 ]; then
  hinweis "${SWAP_BELEGT} MB Swap belegt und nur ${VERF_PROZENT} % RAM verfügbar — Speicher wird knapp, alles wird langsam."
fi
kopf "Druck (PSI): wie viel Zeit Prozesse auf CPU, Platte, Speicher warten"
for r in cpu io memory; do
  [ -r /proc/pressure/$r ] && printf '  %-7s %s\n' "$r" "$(head -1 /proc/pressure/$r)"
done
IO_PSI=$(awk '/^some/ {split($3,a,"="); print int(a[2])}' /proc/pressure/io 2>/dev/null || echo 0)
if [ "${IO_PSI:-0}" -ge 20 ]; then
  hinweis "Prozesse warten ${IO_PSI} % der Zeit auf die Platte (io avg60) — die Platte ist der Engpass."
elif [ "${IO_PSI:-0}" -ge 5 ]; then
  hinweis "Prozesse warten ${IO_PSI} % der Zeit auf die Platte (io avg60) — spürbar; auf einem gesunden Wirt liegt der Wert nahe 0."
fi
MEM_PSI=$(awk '/^some/ {split($3,a,"="); print int(a[2])}' /proc/pressure/memory 2>/dev/null || echo 0)
[ "${MEM_PSI:-0}" -ge 10 ] && hinweis "Speicherdruck ${MEM_PSI} % (memory avg60) — zu wenig RAM."
kopf "vmstat (5 Sekunden; wa = Warten auf die Platte, si/so = Swap)"
z "vmstat 1 5" 15
kopf "Die Prozesse mit der meisten CPU"
z "ps -eo pid,pcpu,pmem,etime,comm --sort=-pcpu | head -15"
kopf "Die Prozesse mit dem meisten Speicher"
z "ps -eo pid,pmem,rss,comm --sort=-rss | head -10"
kopf "Prozesse im Zustand D (warten auf die Platte, sollte 0 sein)"
D=$(ps -eo stat,pid,comm | awk '$1 ~ /^D/' | tee /dev/stderr | wc -l)
echo "Anzahl: $D"
[ "$D" -gt 3 ] && hinweis "$D Prozesse hängen im Zustand D — die Platte antwortet nicht schnell genug (dmesg prüfen)."

# ------------------------------------------------------------------ Platte
kopf "Platte"
ROOTDIR=$(timeout 30 docker info -f '{{.DockerRootDir}}' 2>/dev/null || echo /var/lib/docker)
echo "Docker-Verzeichnis: $ROOTDIR"
z "df -hT '$ROOTDIR' / /srv 2>/dev/null"
z "df -i '$ROOTDIR'"
VOLL=$(df --output=pcent "$ROOTDIR" | tail -1 | tr -dc 0-9)
[ "${VOLL:-0}" -ge 90 ] && hinweis "Das Dateisystem von $ROOTDIR ist zu ${VOLL} % voll — Docker wird ab ~90 % zäh."
IVOLL=$(df --output=ipcent "$ROOTDIR" | tail -1 | tr -dc 0-9)
[ "${IVOLL:-0}" -ge 90 ] && hinweis "Die Inodes von $ROOTDIR sind zu ${IVOLL} % belegt."
GERAET=$(df --output=source "$ROOTDIR" | tail -1)
echo "Gerät: $GERAET"
if command -v iostat >/dev/null; then
  kopf "iostat (5 Sekunden; %util nahe 100 und hohe await-Werte = Platte am Limit)"
  z "iostat -dxm 1 5" 15
else
  echo "(iostat fehlt — apt install sysstat, dann genauer)"
fi
FSTYP=$(df --output=fstype "$ROOTDIR" | tail -1 | tr -d ' ')
# dd meldet den Durchsatz in der letzten Zeile ("…, 13,7 MB/s"); in MB/s umrechnen.
mbs() { LC_ALL=C awk '{ gsub(",", ".", $(NF-1)); v = $(NF-1) + 0
               if ($NF == "kB/s") v /= 1000; else if ($NF == "GB/s") v *= 1000
               print v }'; }
schreibtest() {
  local dir=$1 datei="$1/.ota-diagnose-$$" gross klein
  kopf "Schreibtest unter $dir (normal: SSD > 200 MB/s, HDD > 80 MB/s)"
  gross=$(timeout 120 dd if=/dev/zero of="$datei" bs=1M count=256 oflag=direct conv=fsync 2>&1 | tail -1)
  echo "  256 MB am Stück:          ${gross:-(nach 120 s abgebrochen)}"
  # 500 kleine, synchrone Schreibvorgänge — so schreiben containerd und
  # Datenbanken ihre Metadaten. Gesund: Hunderte bis Tausende je Sekunde.
  local beginn ende
  beginn=$(date +%s%N)
  klein=$(timeout 60 dd if=/dev/zero of="$datei" bs=4k count=500 oflag=direct,dsync 2>&1 | tail -1)
  ende=$(date +%s%N)
  rm -f "$datei"
  local ms=$(( (ende - beginn) / 1000000 )) iops=0
  if echo "$klein" | grep -q 'kopiert\|copied'; then
    [ "$ms" -gt 0 ] && iops=$(( 500 * 1000 / ms ))
    echo "  500 × 4 KB synchron:      $klein  (≈ $iops Schreibvorgänge/s)"
  else
    echo "  500 × 4 KB synchron:      nach 60 s nicht fertig — unter 9 Schreibvorgänge/s"
  fi
  local g; g=$(echo "$gross" | grep -q 'kopiert\|copied' && echo "$gross" | mbs || echo 0)
  LC_ALL=C awk -v g="$g" 'BEGIN { exit !(g < 80) }' &&
    hinweis "Nur ${g} MB/s beim Schreiben unter $dir — die Platte ist sehr langsam (in einer VM: Speicher des Hypervisors prüfen, z. B. HDD, Netzspeicher oder Cache-Modus des virtuellen Laufwerks)."
  [ "$iops" -lt 100 ] &&
    hinweis "Nur $([ "$iops" -gt 0 ] && echo "$iops" || echo "unter 9") synchrone Schreibvorgänge/s unter $dir (gesund: > 500) — jeder Container-Start, jede Image-Schicht und jede Datenbank wartet darauf. Das ist sehr wahrscheinlich der Hauptgrund."
}
schreibtest "$ROOTDIR"
# Mit dem containerd-Image-Speicher (Speichertreiber overlayfs) liegen Images
# und Container-Schichten nicht unter DockerRootDir, sondern unter
# /var/lib/containerd — oft auf einer anderen Platte.
if [ -d /var/lib/containerd ] && [ "$(stat -c %d /var/lib/containerd)" != "$(stat -c %d "$ROOTDIR")" ]; then
  echo "(/var/lib/containerd liegt auf $(df --output=source /var/lib/containerd | tail -1) — dort liegen Images und Container-Schichten)"
  schreibtest /var/lib/containerd
fi
if [ "$FSTYP" = btrfs ]; then
  hinweis "$ROOTDIR liegt auf btrfs. btrfs schreibt jede Änderung an eine neue Stelle (Copy-on-Write) und ist bei vielen fsync — Datenbanken in Volumes — deutlich langsamer als ext4/xfs; in einer VM auf einem qcow2-Abbild kommt ein zweites Copy-on-Write dazu. Für Volumes mit Datenbanken hilft 'chattr +C' auf ein leeres Verzeichnis, besser ext4 oder xfs."
fi

# ------------------------------------------------------------------ Docker selbst
kopf "Docker"
z "docker version -f 'Client {{.Client.Version}}, Server {{.Server.Version}}'"
z "docker info -f 'Speichertreiber: {{.Driver}} | Cgroup: {{.CgroupDriver}} v{{.CgroupVersion}} | Logs: {{.LoggingDriver}} | Container: {{.Containers}} ({{.ContainersRunning}} laufen) | Images: {{.Images}}'"
z "docker info 2>/dev/null | grep -iE 'runtimes|default runtime|warning'"
kopf "Wie viel es gibt"
N_CONT=$(docker ps -aq 2>/dev/null | wc -l); N_LAUF=$(docker ps -q 2>/dev/null | wc -l)
N_NETZ=$(docker network ls -q 2>/dev/null | wc -l); N_VOL=$(docker volume ls -q 2>/dev/null | wc -l)
N_IMG=$(docker images -aq 2>/dev/null | wc -l); N_DANGLING=$(docker images -qf dangling=true 2>/dev/null | wc -l)
N_OTANETZ=$(docker network ls --format '{{.Name}}' 2>/dev/null | grep -c '^ota-n-' || true)
echo "  Container: $N_CONT ($N_LAUF laufen)   Netze: $N_NETZ (davon Sitzungsnetze: $N_OTANETZ)"
echo "  Volumes: $N_VOL   Images: $N_IMG (ohne Namen: $N_DANGLING)"
[ "$N_NETZ" -gt 200 ] && hinweis "$N_NETZ Docker-Netze — jedes kostet Regeln in iptables, und Netzaufrufe werden langsam."
[ "$((N_CONT - N_LAUF))" -gt 100 ] && hinweis "$((N_CONT - N_LAUF)) gestoppte Container — 'docker container prune' nach Prüfung."
[ "$N_DANGLING" -gt 100 ] && hinweis "$N_DANGLING Images ohne Namen — 'docker image prune' gibt Platz frei."
kopf "Belegung (docker system df)"
z "docker system df" 120
BUILD=$(timeout 60 docker system df --format '{{.Type}} {{.Size}}' 2>/dev/null | awk '/Build Cache/ {print $3}')
echo "Build-Cache: ${BUILD:-?}"
case "${BUILD:-}" in *GB) [ "${BUILD%%.*}" -ge 50 ] 2>/dev/null && hinweis "Build-Cache ${BUILD} — 'docker builder prune' gibt Platz frei und entlastet die Platte." ;; esac
kopf "Die größten Protokolle von Containern (json-file)"
z "find '$ROOTDIR/containers' -name '*-json.log' -size +100M -printf '%s %p\n' 2>/dev/null | sort -rn | head -10 | awk '{printf \"  %6d MB  %s\n\", \$1/1048576, \$2}'"
GROSS=$(find "$ROOTDIR/containers" -name '*-json.log' -size +1G 2>/dev/null | wc -l)
[ "$GROSS" -gt 0 ] && hinweis "$GROSS Container-Protokolle über 1 GB — Logrotation fehlt bei diesen Containern."
kopf "dockerd und containerd"
for p in dockerd containerd; do
  PID=$(pgrep -xo "$p" || true)
  [ -n "$PID" ] || { echo "  $p läuft nicht?"; continue; }
  printf '  %-11s PID %s  CPU %s %%  RSS %s MB  Threads %s  offene Dateien %s  läuft seit %s\n' "$p" "$PID" \
    "$(ps -o pcpu= -p "$PID" | tr -d ' ')" "$(( $(ps -o rss= -p "$PID") / 1024 ))" \
    "$(ls /proc/"$PID"/task | wc -l)" "$(ls /proc/"$PID"/fd 2>/dev/null | wc -l)" "$(ps -o etime= -p "$PID" | tr -d ' ')"
done
DCPU=$(ps -o pcpu= -p "$(pgrep -xo dockerd)" 2>/dev/null | tr -d ' ' | cut -d. -f1)
[ "${DCPU:-0}" -ge 80 ] && hinweis "dockerd selbst rechnet mit ${DCPU} % CPU — meist viele Container/Netze oder ein Fehler in einer Schleife (Protokoll unten)."
kopf "Protokoll des Docker-Dienstes, letzte Stunde (Fehler, Warnungen, Zeitüberschreitungen)"
if command -v journalctl >/dev/null; then
  z "journalctl -u docker -u containerd --since '1 hour ago' --no-pager 2>/dev/null | grep -iE 'error|warn|timeout|deadline|slow|failed' | tail -30"
  N_FEHLER=$(journalctl -u docker --since '1 hour ago' --no-pager 2>/dev/null | grep -ciE 'error|timeout|deadline' || true)
  echo "Fehler/Zeitüberschreitungen in der letzten Stunde: $N_FEHLER"
  [ "${N_FEHLER:-0}" -gt 50 ] && hinweis "$N_FEHLER Fehler im Protokoll von dockerd in einer Stunde — die Meldungen oben ansehen."
fi

# ------------------------------------------------------------------ Netz
kopf "Netz: Regeln und Namensräume (viele Netze = viele Regeln = langsame Netzaufrufe)"
IPT=$(timeout 30 iptables-save 2>/dev/null | wc -l)
NFT=$(timeout 30 nft list ruleset 2>/dev/null | wc -l)
NETNS=$(ls /run/docker/netns 2>/dev/null | wc -l)
VETH=$(ip -o link show type veth 2>/dev/null | wc -l)
BR=$(ip -o link show type bridge 2>/dev/null | wc -l)
echo "  iptables-Zeilen: $IPT   nft-Zeilen: $NFT   Netz-Namensräume: $NETNS   veth: $VETH   Bridges: $BR"
[ "$IPT" -gt 20000 ] && hinweis "$IPT Zeilen in iptables — Docker baut bei jedem Netzaufruf daran; das bremst stark."
z "iptables -L DOCKER-USER -n 2>/dev/null | wc -l | xargs echo '  Regeln in DOCKER-USER:'"
kopf "conntrack (volle Tabelle = verworfene Verbindungen)"
z "cat /proc/sys/net/netfilter/nf_conntrack_count /proc/sys/net/netfilter/nf_conntrack_max 2>/dev/null | paste -sd/ | xargs echo '  belegt/maximal:'"

# ------------------------------------------------------------------ Sysbox, Kernel
kopf "Sysbox (Root-Arbeitsplätze)"
for p in sysbox-mgr sysbox-fs; do
  PID=$(pgrep -xo "$p" || true)
  [ -n "$PID" ] && printf '  %-11s CPU %s %%  RSS %s MB\n' "$p" "$(ps -o pcpu= -p "$PID" | tr -d ' ')" "$(( $(ps -o rss= -p "$PID") / 1024 ))"
done
command -v journalctl >/dev/null && z "journalctl -u sysbox -u sysbox-mgr -u sysbox-fs --since '1 hour ago' --no-pager 2>/dev/null | grep -iE 'error|fail|timeout' | tail -10"
kopf "Overlay-Einhängungen"
OVL=$(grep -c ' overlay ' /proc/mounts)
echo "  $OVL"
kopf "Kernel-Meldungen: Plattenfehler, hängende Aufgaben, Speichermangel"
z "dmesg -T 2>/dev/null | grep -iE 'I/O error|blocked for more than|hung_task|oom|out of memory|ext4.*error|xfs.*error|btrfs.*error|nvme.*(timeout|reset)|ata[0-9].*(error|reset)|scsi.*error' | tail -20"
DM=$(dmesg 2>/dev/null | grep -ciE 'I/O error|blocked for more than|nvme.*timeout' || true)
[ "${DM:-0}" -gt 0 ] && hinweis "$DM Kernel-Meldungen zu Plattenfehlern oder hängenden Aufgaben — die Platte prüfen (smartctl -a)."
OOM=$(dmesg 2>/dev/null | grep -ciE 'out of memory|oom-kill' || true)
[ "${OOM:-0}" -gt 0 ] && hinweis "$OOM Mal hat der Kernel Prozesse wegen Speichermangel beendet."
if command -v smartctl >/dev/null; then
  kopf "SMART der Platte"
  DISK=$(lsblk -no pkname "$GERAET" 2>/dev/null | head -1)
  [ -n "$DISK" ] && z "smartctl -H /dev/$DISK | tail -2"
fi
kopf "Virtualisierung"
z "systemd-detect-virt 2>/dev/null || echo unbekannt"
z "grep -m1 'model name' /proc/cpuinfo"
STEAL=$(vmstat 1 3 | tail -1 | awk '{print $NF}')
[ "${STEAL:-0}" -ge 10 ] && hinweis "Steal ${STEAL} % — der Hypervisor gibt dieser VM nicht genug CPU."

# ------------------------------------------------------------------ Ergebnis
kopf "Ergebnis"
if [ ${#HINWEISE[@]} -eq 0 ]; then
  echo "  Nichts Auffälliges gefunden. Die Antwortzeiten oben zeigen, ob Docker gerade langsam ist;"
  echo "  war es nur während eines Updates langsam, das Skript dann noch einmal laufen lassen."
else
  for h in "${HINWEISE[@]}"; do echo "  • $h"; done
fi
echo
echo "Bericht: $BERICHT"
