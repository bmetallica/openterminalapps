# Der Router aller Arbeitsplaetze. Er haengt in `ota_uplink` und bekommt zur
# Laufzeit je Sitzung ein weiteres Netz dazu; er braucht ausser NET_ADMIN,
# NET_RAW und SYS_ADMIN nichts — kein Docker-Socket, keine Datenbank, keine
# Ablage ausser dem Socket zum Agent.
FROM python:3.13-slim AS runtime

# Sicherheitsupdates der Basis. `OTA_PAKETSTAND` wechselt jede Woche
# (Makefile) und baut diese Schicht damit spaetestens woechentlich neu —
# sonst hielte der Build-Cache sie auf dem Stand vom ersten Bau.
ARG OTA_PAKETSTAND=
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get upgrade -y \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

# `iptables` in der nft-Fassung, weil Docker auf Debian 13 dieselbe benutzt:
# Zwei Regelwerke, die sich gegenseitig nicht sehen, waeren schlimmer als eins.
RUN apt-get update && apt-get install -y --no-install-recommends \
      iptables nftables ipset dnsmasq ca-certificates \
      # `iproute2` fuer die Routen — auch die, die dieser Dienst in den
      # Namensraum eines Arbeitsplatzes setzt. `util-linux` bringt `nsenter`
      # mit, das ihn dorthin bringt.
      iproute2 util-linux iputils-ping \
 && update-alternatives --set iptables /usr/sbin/iptables-nft \
 && update-alternatives --set ip6tables /usr/sbin/ip6tables-nft \
 # dnsmasq wird von diesem Dienst gestartet, nicht von systemd.
 && rm -f /etc/dnsmasq.d/* \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt
COPY otafw ./otafw

# **Kein Netzwerkport.** Dieser Dienst steuert die Firewall aller Arbeitsplaetze
# — und haengt selbst in **jedem** Sitzungsnetz. Ein Port waere damit aus jedem
# Arbeitsplatz erreichbar, und wer ihn erreicht, schreibt das Regelwerk. Der
# Agent erreicht ihn statt dessen ueber einen Unix-Socket im gemeinsamen
# Ablageverzeichnis — kein Port, keine Adresse, und die Dateirechte entscheiden.
CMD ["uvicorn", "otafw.main:app", "--uds", "/srv/ota/runtime/firewall.sock"]
