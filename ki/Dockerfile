# Der KI-Durchgang (Handbuch Kapitel 28). Läuft im Netzwerk-Namensraum der
# Firewall (network_mode: service:firewall) und sieht damit jede Verbindung
# aus einem Arbeitsplatz mit ihrer echten Absenderadresse. Er braucht keine
# Fähigkeit, keinen Docker-Socket und keine Datenbank — nur das Verzeichnis
# ki/ in der Ablage und den Zustand der Firewall (lesend).
FROM python:3.13-slim

ARG OTA_PAKETSTAND=
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get upgrade -y \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt
COPY otaki ./otaki
RUN useradd -r -u 10001 -m otaki
USER otaki

CMD ["python", "-m", "otaki"]
