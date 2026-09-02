# OTAs zweite Streaming-Maschine: Selkies statt KasmVNC.
#
# **Testimage.** Es trägt `:test`, keine bestehende Vorlage zeigt darauf, und
# `ota/base-xfce` bleibt unberührt. Der bisherige Weg läuft vollständig weiter.
#
# **Warum überhaupt eine zweite.** KasmVNC spricht RFB — ein Protokoll, das
# rechteckige Bildausschnitte überträgt. Für Text und ruhige Oberflächen ist
# das gut; für alles, was sich bewegt (ein Video, ein Scroll durch eine lange
# Datei, eine Zeichenfläche), ist es die falsche Form. Selkies kodiert
# statt dessen einen H.264-Strom.
#
# **Und warum das hier ohne TURN-Server geht.** Der naheliegende Gedanke war
# „WebRTC statt RFB", und daran hing die unangenehme Folge: WebRTC braucht
# einen Medienweg per UDP, und Session-Container liegen in einem internen
# Docker-Netz ohne veröffentlichte Ports. Das hätte einen TURN-Server im Stack
# bedeutet.
#
# Selkies streamt aber **standardmässig über eine gewöhnliche
# WebSocket-Verbindung** und benutzt WebRTC nur auf Wunsch (`--mode=webrtc`).
# Damit ist der Weg derselbe wie bei KasmVNC: ein Port im Container, Traefik
# davor, Basic-Auth im Header. Kein neues Bauteil im Stack.
#
# Gebaut auf `ota/base-xfce:test` und nicht daneben: Der Vertrag mit dem Agent
# (Kennung 1000, `/home/kasm-user`, XFCE, die Werkzeuge für Zwischenablage und
# Fenster) gilt unverändert. KasmVNC bleibt im Image liegen — dadurch lässt
# sich derselbe Arbeitsplatz mit beiden Maschinen starten und vergleichen.

ARG OTA_BASE=ota/base-xfce:test
FROM ${OTA_BASE}

ARG DEBIAN_FRONTEND=noninteractive

LABEL org.opencontainers.image.title="OpenTerminalApps Basisimage (Selkies)" \
      org.opencontainers.image.description="Ubuntu 24.04 + XFCE + Selkies, H.264 über WebSocket" \
      org.opencontainers.image.licenses="MPL-2.0 AND GPL-2.0-or-later AND MIT" \
      com.kasmweb.image=""

USER root

# --- Was Selkies vom System braucht --------------------------------------
#
# `Xvfb` liefert das Display, das Selkies abgreift. Es könnte auch das `Xvnc`
# aus dem Basisimage sein — aber ein X-Server, der nebenbei RFB spricht, ist
# für diesen Weg Ballast, und die beiden Maschinen sollen sich nicht ins
# Gehege kommen.
#
# `pulseaudio` für den Ton. `xdotool`, `xclip` und die übrigen Werkzeuge
# bringt das Basisimage schon mit.
# **Kein `coturn`.** WebRTC braucht einen Medienweg per UDP, und der geht
# nicht durch Traefik — vermittelt wird über einen TURN-Server. Der stand
# zuerst hier drin, ein eigener je Sitzung, und das kann nicht funktionieren:
# Hinter einer Docker-Bridge meldet TURN die Adresse des Hosts als Relay und
# verschickt die Pakete mit der Container-Adresse als Absender; der Browser
# verwirft sie. Er läuft deshalb als Dienst `turn` im Stack, auf dem Netz des
# Hosts. Siehe `deploy/docker-compose.yml` und `scripts/pruef-turn.py`.
RUN apt-get update && apt-get install -y --no-install-recommends \
      xvfb x11-xserver-utils \
      pulseaudio pulseaudio-utils \
      python3-venv python3-pip \
      # `evdev` (ueber `pynput`) bringt kein fertiges Rad mit und wuerde sonst
      # uebersetzt — mit Uebersetzer und Kernel-Kopfdateien im Image. Ubuntu
      # hat es fertig; die Umgebung unten wird mit `--system-site-packages`
      # angelegt und sieht es.
      python3-evdev \
      # Das GStreamer-Buendel bringt nur `gi/overrides` mit, nicht `gi`
      # selbst — das kommt vom System. Ohne es endet Selkies beim Start mit
      # "could not find working GStreamer-Python installation", und der Grund
      # steht nirgends im Klartext.
      python3-gi python3-gi-cairo gir1.2-glib-2.0 \
      libgl1 libegl1 libgbm1 libxcb-shm0 libxdamage1 libxfixes3 libxtst6 \
      libgudev-1.0-0 libpangocairo-1.0-0 libsoup-3.0-0 libjson-glib-1.0-0 \
      libwoff1 libvpx9 libopus0 libsrtp2-1 libnice10 \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

# --- Selkies ------------------------------------------------------------
#
# Aus dem **getaggten Release** und nicht von `main`. Zwei Anläufe vorher, und
# beide gehören in die Akte:
#
# 1. PyPI führt ein Paket `selkies` in der Fassung 1.6.1 — trotz des Namens
#    ist das die alte GStreamer-Linie (`selkies_gstreamer`), nicht die neue
#    mit WebSocket-Transport.
# 2. Die neue Linie liegt nur auf `main` und verlangt `pixelflux~=2.1.0` und
#    `pcmflux~=2.1.0`. Auf PyPI gibt es davon 2.0.0, sonst nirgends etwas.
#    Ein Testimage, das sich nicht bauen lässt, ist kein Testimage.
#
# Also v1.6.2: getaggt, mit vorgebauten Binärdateien für Ubuntu 24.04, und
# reproduzierbar. Der Preis steht im Startskript — diese Fassung spricht
# **nur** WebRTC und braucht deshalb einen TURN-Server.
ARG SELKIES_VERSION=1.6.2
ARG SELKIES_BASE=https://github.com/selkies-project/selkies-gstreamer/releases/download

# Der GStreamer-Unterbau. Er liegt getrennt unter /opt/gstreamer und wird beim
# Start über `gst-env` in die Umgebung geholt — das System-GStreamer bleibt
# unangetastet.
RUN curl -fsSL -o /tmp/gst.tgz \
      "${SELKIES_BASE}/v${SELKIES_VERSION}/gstreamer-selkies_gpl_v${SELKIES_VERSION}_ubuntu24.04_amd64.tar.gz" \
 && mkdir -p /opt/gstreamer \
 && tar -xzf /tmp/gst.tgz -C /opt/gstreamer --strip-components=1 \
 && rm -f /tmp/gst.tgz \
 && test -f /opt/gstreamer/gst-env

# Die Weboberfläche. Sie wird von Selkies selbst ausgeliefert (`--web_root`).
RUN curl -fsSL -o /tmp/web.tgz \
      "${SELKIES_BASE}/v${SELKIES_VERSION}/selkies-gstreamer-web_v${SELKIES_VERSION}.tar.gz" \
 && mkdir -p /opt/gst-web \
 && tar -xzf /tmp/web.tgz -C /opt/gst-web --strip-components=1 \
 && rm -f /tmp/web.tgz \
 && test -f /opt/gst-web/index.html

# Der Client hängt seine Signalisierungsadresse an die Wurzel des Hosts und
# nimmt dafür nur das erste Segment des Pfades. Eine OTA-Session liegt unter
# `/s/<kennung>/` — zwei Segmente. Ohne diese Korrektur landet er bei
# `wss://host/s/signalling/`, also bei OTAs Weboberfläche: Die Seite baut sich
# vollständig auf, das Bild bleibt schwarz, und nirgends steht, warum.
# Der Kopf der Datei erklärt es ausführlich.
COPY patches/gst-web-pfad.py /tmp/gst-web-pfad.py
RUN python3 /tmp/gst-web-pfad.py /opt/gst-web/app.js && rm -f /tmp/gst-web-pfad.py

# Und die Anwendung selbst, in ein eigenes Verzeichnis: Ubuntu 24.04 verwaltet
# sein Python selbst (PEP 668), und ein `--break-system-packages` wäre genau
# das, was der Name sagt.
#
# **Kein `|| true` am Ende dieser Kette.** Genau das stand hier zuerst und hat
# einen gescheiterten Install in einen grünen Build verwandelt: Das Image war
# fertig, `selkies` fehlte, und aufgefallen ist es erst beim Starten mit
# „command not found".
ENV SELKIES_HOME=/opt/selkies
RUN python3 -m venv --system-site-packages "$SELKIES_HOME" \
 && "$SELKIES_HOME/bin/pip" install --no-cache-dir --upgrade pip \
 && "$SELKIES_HOME/bin/pip" install --no-cache-dir \
      "${SELKIES_BASE}/v${SELKIES_VERSION}/selkies_gstreamer-${SELKIES_VERSION}-py3-none-any.whl" \
 && ln -sf "$SELKIES_HOME/bin/selkies-gstreamer" /usr/local/bin/selkies-gstreamer \
 && test -x "$SELKIES_HOME/bin/selkies-gstreamer"

# Selkies hängt an jede STUN-Liste `stun.l.google.com` an — unabhängig davon,
# was konfiguriert ist. Im Firmennetz ist das ein Ruf nach draussen, den
# niemand bestellt hat, und ohne Internet wartet der Verbindungsaufbau erst
# in einen Zeitablauf hinein. Der Kopf der Datei erklärt es; sie bricht ab,
# wenn eine neue Selkies-Fassung die Stelle verschoben hat.
COPY patches/kein-fremd-stun.py /tmp/kein-fremd-stun.py
RUN python3 /tmp/kein-fremd-stun.py \
      "$SELKIES_HOME/lib/python3.12/site-packages" \
 && rm -f /tmp/kein-fremd-stun.py

# Chrome verschickt seinen DTLS-Handschlag mit fest 1200 Byte je Paket und
# passt sich einer kleineren Pfadgroesse nicht an. Wo weniger durchpasst —
# ein VPN-Tunnel mit MTU 1000 — kommt der Handschlag nie zustande. Dagegen
# hilft, den Browser ueber TURN zu zwingen; dafuer muss die Einstellung
# ueberhaupt einstellbar sein. Der Kopf der Datei erklaert die Messung.
COPY patches/ice-nur-vermittelt.py /tmp/ice-nur-vermittelt.py
RUN python3 /tmp/ice-nur-vermittelt.py \
      "$SELKIES_HOME/lib/python3.12/site-packages" \
 && rm -f /tmp/ice-nur-vermittelt.py

# `cvt` rechnet eine Modeline aus. Selkies braucht es, um die Auflösung an
# das Browserfenster anzupassen — und in Ubuntu 24.04 liefert es **kein**
# Paket mehr (mit `apt-file` nachgeprüft). Ohne diesen Ersatz bleibt der ferne
# Bildschirm auf der vollen Grösse des Framebuffers stehen. Der Kopf der Datei
# erklärt die Rechnung; sie ist am Referenzwert für 1920x1080 geprüft.
COPY bin/cvt /usr/local/bin/cvt
RUN chmod +x /usr/local/bin/cvt \
 && /usr/local/bin/cvt -r 1920 1080 60 | grep -q '138.50  1920 1968 2000 2080'

COPY dockerstartup/selkies_startup.sh /dockerstartup/selkies_startup.sh
RUN chmod +x /dockerstartup/selkies_startup.sh

# Derselbe Port nach aussen wie bei KasmVNC — für Traefik ist es dieselbe
# Route, nur ein anderes Ziel.
EXPOSE 8080

WORKDIR /home/kasm-user
USER 1000

ENTRYPOINT ["/dockerstartup/selkies_startup.sh"]
