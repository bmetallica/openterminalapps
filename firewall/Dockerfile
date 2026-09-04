# Der Firewall-Dienst. Er laeuft im Netzwerk-Namensraum des Wirts und braucht
# ausser NET_ADMIN nichts — kein Docker-Socket, keine Datenbank, keine Ablage.
FROM python:3.12-slim AS runtime

# `iptables` in der nft-Fassung, weil Docker auf Debian 13 dieselbe benutzt:
# Zwei Regelwerke, die sich gegenseitig nicht sehen, waeren schlimmer als eins.
RUN apt-get update && apt-get install -y --no-install-recommends \
      iptables ipset dnsmasq ca-certificates \
 && update-alternatives --set iptables /usr/sbin/iptables-nft \
 && update-alternatives --set ip6tables /usr/sbin/ip6tables-nft \
 # dnsmasq wird von diesem Dienst gestartet, nicht von systemd.
 && rm -f /etc/dnsmasq.d/* \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY otafw ./otafw

# **Kein Netzwerkport.** Der Dienst laeuft im Namensraum des Wirts; ein Port
# waere damit auf jeder Adresse des Wirts offen, auch der im Firmennetz. Der
# Agent erreicht ihn statt dessen ueber einen Unix-Socket im gemeinsamen
# Ablageverzeichnis — kein Port, keine Adresse, und die Dateirechte entscheiden.
CMD ["uvicorn", "otafw.main:app", "--uds", "/srv/ota/runtime/firewall.sock"]
