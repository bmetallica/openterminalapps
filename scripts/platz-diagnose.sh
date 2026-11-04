#!/usr/bin/env bash
# Warum erreicht ein Arbeitsplatz OTA, die KI oder das Netz nicht mehr?
# Läuft **im** Arbeitsplatz und ändert nichts — nur lesen und probieren.
#
# Vom Wirt aus (kopiert sich hinein, Bericht bleibt auf dem Wirt):
#   sudo scripts/platz-diagnose.sh ota-s-<Anfang der Sitzung>   [host:port …]
#   sudo scripts/platz-diagnose.sh <Sitzungs-ID>
# Im Arbeitsplatz (Konsole unter Betrieb), am besten als root:
#   bash platz-diagnose.sh [host:port …]
#
# Geprüft wird der Weg zu allem, was der Arbeitsplatz braucht: Router und DNS
# von OTA, der Proxy, die KI aus den Einstellungen von Continue und opencode,
# und was zusätzlich als host:port angegeben ist. Beim Root-Arbeitsplatz
# dazu das Docker darin — dessen Netze können Adressen überdecken, die der
# Arbeitsplatz selbst braucht (so schon einmal geschehen: 192.168.0.0/20).
set -uo pipefail

# ------------------------------------------------------------------ vom Wirt
if [ $# -gt 0 ] && [ ! -f /etc/ota/umgebung.sh ] && command -v docker >/dev/null && [[ "$1" != *:* ]]; then
  ziel=$1; shift
  c=$(docker ps -a --format '{{.Names}}' | grep -E "^(${ziel}|ota-s-${ziel:0:12})" | head -1)
  [ -n "$c" ] || { echo "Kein Container zu '$ziel' (docker ps -a | grep ota-s-)." >&2; exit 1; }
  [ "$(docker inspect -f '{{.State.Running}}' "$c")" = true ] || { echo "$c läuft nicht." >&2; exit 1; }
  bericht="/tmp/platz-diagnose-$c-$(date +%Y%m%d-%H%M%S).txt"
  {
    # Von aussen: Hängt der Platz an seinem Sitzungsnetz, und der Router darin?
    echo "== Von aussen (Wirt): $c =="
    netz="ota-n-${c#ota-s-}"
    echo "-- Netze des Containers:"
    docker inspect -f '{{range $n, $e := .NetworkSettings.Networks}}  {{$n}} {{$e.IPAddress}} (Gateway {{$e.Gateway}}){{"\n"}}{{end}}' "$c"
    docker inspect -f '{{range $n, $e := .NetworkSettings.Networks}}{{$n}} {{end}}' "$c" | grep -qw "$netz" ||
      echo "  !! $c hängt nicht in seinem Sitzungsnetz $netz"
    if docker network inspect "$netz" >/dev/null 2>&1; then
      echo "-- Im Sitzungsnetz $netz ($(docker network inspect -f '{{range .IPAM.Config}}{{.Subnet}}{{end}}' "$netz")):"
      docker network inspect -f '{{range .Containers}}  {{.Name}} {{.IPv4Address}}{{"\n"}}{{end}}' "$netz"
      docker network inspect -f '{{range .Containers}}{{.Name}} {{end}}' "$netz" | grep -qw ota-firewall ||
        echo "  !! Der Router (ota-firewall) hängt nicht in $netz — der Platz hat keinen Weg nach draussen."
    else
      echo "  !! Das Sitzungsnetz $netz gibt es nicht mehr."
    fi
    echo "-- Router: $(docker inspect -f '{{.Name}} {{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}' ota-firewall 2>&1)"
    # In den Netz-Namensraum des Platzes, mit den Werkzeugen des Wirts.
    pid=$(docker inspect -f '{{.State.Pid}}' "$c")
    if command -v nsenter >/dev/null && [ "${pid:-0}" -gt 0 ]; then
      echo "-- Netz im Platz (nsenter):"
      nsenter -t "$pid" -n ip -br addr 2>&1 | sed 's/^/  /'
      nsenter -t "$pid" -n ip route 2>&1 | sed 's/^/  /'
      gw=$(docker inspect -f "{{(index .NetworkSettings.Networks \"$netz\").Gateway}}" "$c" 2>/dev/null)
      r=$(docker network inspect -f '{{range .Containers}}{{if eq .Name "ota-firewall"}}{{.IPv4Address}}{{end}}{{end}}' "$netz" 2>/dev/null)
      r=${r%/*}
      [ -n "$r" ] && echo "  ping zum Router $r: $(nsenter -t "$pid" -n ping -c 2 -W 2 "$r" 2>&1 | grep -oE '[0-9]+% packet loss' || echo 'kein ping')"
      [ -z "$(nsenter -t "$pid" -n ip route show default 2>/dev/null)" ] && echo "  !! Keine Standardroute im Platz."
    fi
    echo
  } 2>&1 | tee "$bericht"
  if docker cp "$0" "$c:/tmp/.ota-platz-diagnose.sh" >/dev/null; then
    docker exec -u 0 "$c" bash /tmp/.ota-platz-diagnose.sh "$@" 2>&1 | tee -a "$bericht"
    docker exec -u 0 "$c" rm -f /tmp/.ota-platz-diagnose.sh
  else
    echo "(Konnte das Skript nicht in den Container kopieren — nur die Sicht von aussen.)" | tee -a "$bericht"
  fi
  echo; echo "Bericht auf dem Wirt: $bericht"
  exit 0
fi

# ------------------------------------------------------------------ im Arbeitsplatz
HINWEISE=()
hinweis() { HINWEISE+=("$1"); }
kopf() { printf '\n== %s ==\n' "$1"; }
z() { timeout "${2:-20}" bash -c "$1" 2>&1 || echo "  (Fehler oder Zeitlimit: $?)"; }
hat() { command -v "$1" >/dev/null 2>&1; }
ip2n() { local IFS=.; set -- $1; echo $(( ($1 << 24) + ($2 << 16) + ($3 << 8) + $4 )); }
# liegt <IP> in <Netz/Länge>?
im_netz() {
  local ip=$1 netz=${2%/*} len=${2#*/}
  [ "$len" = "$2" ] && len=32
  local m=$(( len == 0 ? 0 : (0xFFFFFFFF << (32 - len)) & 0xFFFFFFFF ))
  [ $(( $(ip2n "$ip") & m )) -eq $(( $(ip2n "$netz") & m )) ]
}
ist_ip() { [[ "$1" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; }
aufloesen() { # Name → erste IPv4
  ist_ip "$1" && { echo "$1"; return; }
  getent ahostsv4 "$1" 2>/dev/null | awk 'NR == 1 {print $1}'
}

echo "Arbeitsplatz-Diagnose $(hostname) — $(date)"
[ "$(id -u)" = 0 ] || echo "(nicht als root — einiges fehlt; besser: sudo bash $0)"

# Die Umgebung, mit der der Arbeitsplatz gestartet wurde (die Konsole hat sie
# nicht unbedingt).
ENV1=$(tr '\0' '\n' < /proc/1/environ 2>/dev/null)
wert() { echo "$ENV1" | sed -n "s/^$1=//p" | head -1; }
ROUTER=$(wert OTA_ROUTER)
OTA_DOCKER=$(wert OTA_DOCKER)
[ -f /etc/ota/umgebung.sh ] && PROXY=$(sed -n "s/^export HTTPS_PROXY=//p" /etc/ota/umgebung.sh | tr -d "'\"" | head -1)
PROXY=${PROXY:-$(wert HTTPS_PROXY)}
OHNE=$( { [ -f /etc/ota/umgebung.sh ] && sed -n "s/^export NO_PROXY=//p" /etc/ota/umgebung.sh; wert NO_PROXY; } | tr -d "'\"" | head -1)

kopf "Arbeitsplatz"
echo "  Root-Arbeitsplatz (Docker darin): $([ "$OTA_DOCKER" = 1 ] && echo ja || echo nein)"
echo "  Router laut OTA: ${ROUTER:-?}   Proxy: ${PROXY:-keiner}"
z "uptime"

# ------------------------------------------------------------------ Netz
kopf "Netz: Schnittstellen und Routen"
if hat ip; then
  z "ip -br addr"
  z "ip route"
  RULES=$(ip rule 2>/dev/null | grep -vcE 'lookup (local|main|default)')
  [ "${RULES:-0}" -gt 0 ] && { echo "  Zusätzliche Routing-Regeln:"; ip rule; hinweis "Es gibt eigene Routing-Regeln (ip rule) — die lenken Verkehr womöglich an OTA vorbei."; }
  DEFDEV=$(ip route show default | awk '{for (i = 1; i < NF; i++) if ($i == "dev") print $(i + 1)}' | head -1)
  DEFVIA=$(ip route show default | awk '{for (i = 1; i < NF; i++) if ($i == "via") print $(i + 1)}' | head -1)
  NDEF=$(ip route show default | wc -l)
  [ "$NDEF" -eq 0 ] && hinweis "Keine Standardroute — der Arbeitsplatz kommt nirgendwo hin. Der Router von OTA setzt sie beim Start; Fortsetzen oder Neustart des Platzes setzt sie neu."
  [ "$NDEF" -gt 1 ] && hinweis "$NDEF Standardrouten — eine davon führt vermutlich an OTA vorbei."
  [ -n "$ROUTER" ] && [ -n "$DEFVIA" ] && [ "$DEFVIA" != "$ROUTER" ] &&
    hinweis "Die Standardroute geht über $DEFVIA, OTAs Router ist aber $ROUTER."
  # Das eigene Sitzungsnetz (Schnittstelle der Standardroute oder die mit dem Router).
  [ -z "$DEFDEV" ] && [ -n "$ROUTER" ] && DEFDEV=$(ip route get "$ROUTER" 2>/dev/null | awk '{for (i = 1; i < NF; i++) if ($i == "dev") print $(i + 1)}' | head -1)
  SITZNETZ=$(ip -o -4 addr show dev "${DEFDEV:-eth0}" 2>/dev/null | awk '{print $4}' | head -1)
  echo "  Sitzungsnetz: ${SITZNETZ:-?} auf ${DEFDEV:-?}"
  MTU=$(cat "/sys/class/net/${DEFDEV:-eth0}/mtu" 2>/dev/null)
  echo "  MTU: ${MTU:-?}"
else
  echo "  (ip fehlt — apt install iproute2)"
  z "cat /proc/net/route"
fi

# ------------------------------------------------------------------ Ziele
# Was der Arbeitsplatz erreichen soll: Router (DNS), Proxy, die KI aus den
# Einstellungen und alles, was als Argument kam.
ZIELE=()
[ -n "$ROUTER" ] && ZIELE+=("dns://$ROUTER:53")
[ -n "$PROXY" ] && ZIELE+=("$PROXY")
for f in /home/*/.continue/config.yaml /root/.continue/config.yaml \
         /home/*/.config/opencode/opencode.json* /home/*/.config/opencode/config.json \
         /root/.config/opencode/opencode.json*; do
  [ -f "$f" ] || continue
  while read -r u; do ZIELE+=("$u"); done < <(grep -hoE 'https?://[^"'"'"' ,}]+' "$f" | sort -u)
done
grep -E ' ota-erweiterungen' /etc/hosts >/dev/null 2>&1 && ZIELE+=("https://ota-erweiterungen/")
for a in "$@"; do ZIELE+=("$a"); done
# Doppelte weg, Reihenfolge behalten.
mapfile -t ZIELE < <(printf '%s\n' "${ZIELE[@]}" | awk 'NF && !seen[$0]++')

kopf "DNS"
z "grep -v '^#' /etc/resolv.conf"
NS=$(awk '/^nameserver/ {print $2; exit}' /etc/resolv.conf 2>/dev/null)
[ -n "$ROUTER" ] && [ -n "$NS" ] && [ "$NS" != "$ROUTER" ] && [ "$NS" != 127.0.0.11 ] &&
  hinweis "Als DNS ist $NS eingetragen, OTAs Router ist $ROUTER. Freigaben nach Namen und interne Namen gehen nur über OTAs DNS."

kopf "Erreichbarkeit"
printf '  %-46s %-16s %-12s %s\n' "Ziel" "Adresse" "über" "Ergebnis"
for ziel in "${ZIELE[@]}"; do
  url=$ziel
  [[ "$url" == *"://"* ]] || url="tcp://$url"
  schema=${url%%://*}; rest=${url#*://}; hostport=${rest%%/*}
  host=${hostport%:*}; port=${hostport##*:}
  [ "$host" = "$hostport" ] && port=$([ "$schema" = https ] && echo 443 || echo 80)
  adr=$(aufloesen "$host")
  if [ -z "$adr" ]; then
    printf '  %-46s %-16s %-12s %s\n' "${ziel:0:46}" "-" "-" "Name nicht auflösbar"
    hinweis "$host lässt sich nicht auflösen — DNS (Router $ROUTER) prüfen."
    continue
  fi
  dev="-"
  hat ip && dev=$(ip route get "$adr" 2>/dev/null | awk '{for (i = 1; i < NF; i++) if ($i == "dev") print $(i + 1)}' | head -1)
  if timeout 5 bash -c "exec 3<>/dev/tcp/$adr/$port" 2>/dev/null; then erg="TCP offen"; else erg="TCP zu/keine Antwort"; fi
  if [[ "$schema" == http* ]] && hat curl && [ "$erg" = "TCP offen" ]; then
    erg="$erg, $(curl -sk -o /dev/null -m 15 --noproxy '*' -w 'HTTP %{http_code} in %{time_total}s' "$url" 2>&1)"
  fi
  printf '  %-46s %-16s %-12s %s\n' "${ziel:0:46}" "$adr" "${dev:-?}" "$erg"
  if [ -n "${DEFDEV:-}" ] && [ -n "$dev" ] && [ "$dev" != "$DEFDEV" ] && [ "$dev" != lo ]; then
    hinweis "$host ($adr) wird über $dev geleitet statt über $DEFDEV — ein Netz im Arbeitsplatz (meist ein Docker-Netz) überdeckt diese Adresse. Siehe unten."
  fi
  [[ "$erg" == "TCP zu"* ]] && hinweis "$host:$port ($adr) antwortet nicht."
done
# Mit Proxy, wenn einer gesetzt ist: so gehen Programme ins Netz, die ihn nutzen.
if [ -n "$PROXY" ] && hat curl; then
  echo "  Über den Proxy $PROXY:"
  for u in https://deb.debian.org/ https://pypi.org/; do
    printf '    %-40s %s\n' "$u" "$(curl -s -o /dev/null -m 15 -x "$PROXY" -w 'HTTP %{http_code} in %{time_total}s' "$u" 2>&1)"
  done
fi
# Die Uhr: Weicht sie stark ab, scheitert jedes TLS.
if [ -n "$ROUTER" ] && hat curl; then
  for ziel in "${ZIELE[@]}"; do
    [[ "$ziel" == https://* ]] || continue
    D=$(curl -skI -m 10 --noproxy '*' "$ziel" 2>/dev/null | sed -n 's/^[Dd]ate: //p' | tr -d '\r')
    if [ -n "$D" ]; then
      ab=$(( $(date +%s) - $(date -d "$D" +%s 2>/dev/null || date +%s) ))
      echo "  Uhr: Abweichung zu ${ziel%%/*//}… ${ab#-} s"
      [ "${ab#-}" -gt 300 ] && hinweis "Die Uhr weicht ${ab#-} s ab — TLS-Verbindungen scheitern daran."
      break
    fi
  done
fi

# ------------------------------------------------------------------ Docker darin
if [ "$OTA_DOCKER" = 1 ] || hat dockerd; then
  kopf "Docker im Arbeitsplatz"
  if timeout 10 docker info >/dev/null 2>&1; then
    z "docker info -f 'Container: {{.Containers}} ({{.ContainersRunning}} laufen), Images: {{.Images}}, Netze-Treiber: {{.Driver}}'"
    echo "-- daemon.json:"
    z "cat /etc/docker/daemon.json"
    [ -f /etc/docker/.ota-netze ] && echo "  (Bereiche von OTA eingetragen: $(cat /etc/docker/.ota-netze))"
    echo "-- Netze und ihre Bereiche:"
    NETZE=$(timeout 30 docker network ls -q | xargs -r timeout 30 docker network inspect -f '{{.Name}} {{range .IPAM.Config}}{{.Subnet}} {{end}}' 2>/dev/null)
    echo "$NETZE" | awk '{printf "  %-40s %s\n", $1, $2" "$3}'
    N=$(echo "$NETZE" | grep -c .)
    echo "  $N Netze"
    # Überdeckt ein Netz eine Adresse, die der Arbeitsplatz braucht?
    PRUEF=()
    [ -n "$ROUTER" ] && PRUEF+=("$ROUTER")
    [ -n "${SITZNETZ:-}" ] && PRUEF+=("${SITZNETZ%/*}")
    for ziel in "${ZIELE[@]}"; do
      h=${ziel#*://}; h=${h%%/*}; h=${h%:*}
      a=$(aufloesen "$h"); [ -n "$a" ] && PRUEF+=("$a")
    done
    while read -r name subs; do
      for s in $subs; do
        [[ "$s" == */* ]] && ist_ip "${s%/*}" || continue
        for a in "${PRUEF[@]}"; do
          im_netz "$a" "$s" &&
            hinweis "Das Docker-Netz '$name' ($s) im Arbeitsplatz überdeckt $a — alles dorthin landet auf dieser Bridge. Abhilfe: das Projekt mit 'docker compose down' und wieder 'up' neu anlegen (dann aus OTAs Bereich), oder das Netz löschen."
        done
        # Überschneidet sich das Netz mit dem eigenen Sitzungsnetz?
        [ -n "${SITZNETZ:-}" ] && im_netz "${s%/*}" "$SITZNETZ" &&
          hinweis "Das Docker-Netz '$name' ($s) liegt im Sitzungsnetz $SITZNETZ."
        case "$s" in 192.168.*|10.*)
          [ -f /etc/docker/.ota-netze ] && hinweis "Das Docker-Netz '$name' hat $s — nicht aus OTAs Bereich. Es ist älter als die Vorgabe oder von Hand angelegt; überdeckt es das LAN, ist das der Fehler." ;;
        esac
      done
    done <<<"$NETZE"
    [ ! -f /etc/docker/.ota-netze ] && grep -q default-address-pools /etc/docker/daemon.json 2>/dev/null &&
      echo "  (default-address-pools in daemon.json sind eigene Einträge — OTA fasst sie nicht an)"
    [ ! -f /etc/docker/.ota-netze ] && ! grep -q default-address-pools /etc/docker/daemon.json 2>/dev/null &&
      hinweis "In /etc/docker/daemon.json fehlen default-address-pools. Ab 15 Netzen nimmt Docker dann 192.168.x und überdeckt das LAN. OTA trägt sie beim nächsten Fortsetzen ein."
    echo "-- Container:"
    z "docker ps --format '  {{.Names}}  {{.Status}}  {{.Networks}}' | head -40"
    echo "-- Container mit eigenem Netz des Wirts (network_mode: host):"
    z "docker ps -q | xargs -r docker inspect -f '{{.Name}} {{.HostConfig.NetworkMode}}' | awk '\$2 == \"host\" {print \"  \" \$1}'"
  else
    echo "  dockerd antwortet nicht."
    z "pgrep -a dockerd || echo '  dockerd läuft nicht'"
    z "tail -20 /var/log/dockerd.log 2>/dev/null || tail -20 /var/log/docker.log 2>/dev/null"
    hinweis "Docker im Arbeitsplatz antwortet nicht — innere Container und deren Netze sind weg; das Protokoll von dockerd steht oben."
  fi
fi

# ------------------------------------------------------------------ Regeln
kopf "Paketfilter im Arbeitsplatz"
if hat iptables && [ "$(id -u)" = 0 ]; then
  for t in filter nat; do
    n=$(timeout 10 iptables -t "$t" -S 2>/dev/null | wc -l)
    echo "  iptables $t: $n Regeln"
  done
  z "iptables -S OUTPUT; iptables -S FORWARD | head -5"
  timeout 10 iptables -S OUTPUT 2>/dev/null | grep -qE '^-P OUTPUT (DROP|REJECT)' &&
    hinweis "Die Kette OUTPUT im Arbeitsplatz verwirft alles, was nicht erlaubt ist — prüfen, wer das gesetzt hat."
  timeout 10 iptables -S OUTPUT 2>/dev/null | grep -qE -- '-j (DROP|REJECT)' &&
    hinweis "In OUTPUT stehen DROP/REJECT-Regeln (siehe oben)."
else
  echo "  (iptables fehlt oder nicht root)"
fi

# ------------------------------------------------------------------ Grenzen
kopf "Grenzen des Containers"
CG=/sys/fs/cgroup
if [ -r $CG/pids.max ]; then
  echo "  Prozesse: $(cat $CG/pids.current 2>/dev/null) von $(cat $CG/pids.max)"
  pm=$(cat $CG/pids.max); pc=$(cat $CG/pids.current 2>/dev/null || echo 0)
  [ "$pm" != max ] && [ "$pc" -ge $(( pm * 9 / 10 )) ] && hinweis "Fast alle erlaubten Prozesse belegt ($pc von $pm) — neue Verbindungen und Programme scheitern."
  # Wie oft ein fork an der Grenze gescheitert ist, seit der Platz läuft.
  PMAX=$(awk '$1 == "max" {print $2}' $CG/pids.events 2>/dev/null)
  echo "  An der Prozessgrenze gescheitert (seit Start): ${PMAX:-?}"
  [ "${PMAX:-0}" -gt 0 ] && hinweis "$PMAX-mal ist ein neuer Prozess an der Grenze von $pm gescheitert (Threads zählen mit). Dann startet nichts mehr, auch keine Verbindung — es sieht aus wie „kein Netz“. Grenze: OTA_ROOT_PIDS_LIMIT bzw. OTA_PIDS_LIMIT in der .env."
  echo "  Die meisten Threads:"
  ps -eo nlwp=,comm= 2>/dev/null | awk '{n[$2] += $1} END {for (k in n) print n[k], k}' | sort -rn | head -8 | sed 's/^/    /'
fi
if [ -r $CG/memory.events ]; then
  echo "  Speicher: $(( $(cat $CG/memory.current 2>/dev/null || echo 0) / 1048576 )) MB von $(cat $CG/memory.max 2>/dev/null)"
  OOM=$(awk '$1 == "oom_kill" {print $2}' $CG/memory.events)
  echo "  Vom Speicherwächter beendet (seit Start): ${OOM:-0}"
  [ "${OOM:-0}" -gt 0 ] && hinweis "$OOM Prozesse wurden wegen Speichermangel beendet (oom_kill) — womöglich auch die, die die Verbindung halten (Selkies, opencode)."
fi
[ -r $CG/cpu.stat ] && awk '$1 ~ /nr_throttled|throttled_usec/ {printf "  %s %s\n", $1, $2}' $CG/cpu.stat
z "df -h / /home /tmp /var/lib/docker 2>/dev/null | awk '!seen[\$0]++'"
for d in / /home /var/lib/docker; do
  p=$(df --output=pcent "$d" 2>/dev/null | tail -1 | tr -dc 0-9)
  [ "${p:-0}" -ge 95 ] && hinweis "$d ist zu $p % voll."
done
z "free -m"

# ------------------------------------------------------------------ Dienste
kopf "Dienste im Arbeitsplatz"
for p in selkies Xvfb opencode dockerd containerd sshd; do
  printf '  %-12s %s\n' "$p" "$(pgrep -x "$p" >/dev/null 2>&1 && echo läuft || (pgrep -f "^[^ ]*$p" >/dev/null 2>&1 && echo läuft || echo '-'))"
done
hat ss && { echo "-- lauscht auf:"; z "ss -ltnp 2>/dev/null | awk 'NR > 1 {print \"  \" \$4, \$6}' | head -25"; }
echo "-- die meisten Prozesse:"
z "ps -eo comm= | sort | uniq -c | sort -rn | head -8"

# ------------------------------------------------------------------ Ergebnis
kopf "Ergebnis"
if [ ${#HINWEISE[@]} -eq 0 ]; then
  echo "  Nichts Eindeutiges gefunden. Die Tabelle „Erreichbarkeit“ zeigt, was geht und was nicht."
else
  printf '%s\n' "${HINWEISE[@]}" | awk '!seen[$0]++ {print "  • " $0}'
fi
