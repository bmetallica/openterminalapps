# OTAs eigenes Basisimage — Debian 13 + XFCE + Selkies, **ohne KasmVNC**.
#
# **Warum ein drittes Basisimage.** `base-xfce` ist Ubuntu + XFCE + KasmVNC,
# `base-selkies` leitet davon ab und legt Selkies daneben. Das war richtig,
# solange Selkies ein Versuch auf einer funktionierenden Grundlage war — und
# ist verkehrt herum, seit es streamt: Im Selkies-Image liegen `Xvnc`,
# `kasmvncserver`, `kasmvncpasswd` und 3,4 MB Weboberfläche, und **nichts
# davon läuft dort**. Dieses Image beginnt deshalb bei `debian:13` und nimmt
# nur mit, was gebraucht wird.
#
# Damit fallen drei Dinge zusammen, die einzeln keinen eigenen Umbau wert
# wären:
#
#   * **Kein KasmVNC** — weder Programm noch Name noch GPL-Pflicht daraus.
#   * **Kein `kasm-user`** — die Kennung 1000 heisst `ota` und wohnt unter
#     `/home/ota`. Wo das Zuhause liegt, liest der Agent aus `HOME` **dieses
#     Images** (`_heimat_aus_env` in `agent/otaagent/main.py`); Fremdimages
#     mit `/home/kasm-user` laufen unverändert weiter.
#   * **Debian 13 statt Ubuntu 24.04** — neueres GStreamer in der
#     Distribution (1.26 gegen 1.24 im Bündel), und der Weg dahin, das
#     vorgebaute Bündel später ganz wegzulassen.
#
# **Kein vorgebautes GStreamer-Bündel mehr.** Der erste Anlauf behielt das
# `ubuntu24.04`-Paket von Selkies bei, damit nur *eine* Variable wechselt.
# Das geht nicht: Das Bündel bringt `gi/overrides` als für **Python 3.12**
# übersetzte Erweiterung mit, und Debian 13 hat 3.13. Selkies endet dann mit
#
#     could not find working GStreamer-Python installation
#     cannot import name '_gi_gst' from 'gi.overrides'
#
# Distribution und GStreamer hängen also über Python zusammen und lassen sich
# nicht einzeln wechseln. Genommen wird deshalb **Debians eigenes GStreamer
# 1.26** — neuer als die 1.24.6 im Bündel, mit `python3-gst-1.0` für die
# richtige Python-Fassung, und ohne die 366 MB unter `/opt/gstreamer`.
#
# **Dies ist ein Testimage.** Es trägt `:test`, und `base-xfce` mit KasmVNC
# bleibt unangetastet — darauf laufen die heutigen Arbeitsplätze.

FROM debian:13

ARG DEBIAN_FRONTEND=noninteractive

LABEL org.opencontainers.image.title="OpenTerminalApps Basisimage (Debian/XFCE/Selkies)" \
      org.opencontainers.image.description="Debian 13 + XFCE + Selkies, H.264 über WebRTC, ohne KasmVNC" \
      org.opencontainers.image.licenses="MPL-2.0 AND GPL-2.0-or-later AND MIT"

# `HOME` ist hier nicht nur Bequemlichkeit, sondern **die Auskunft an den
# Agent**: Er liest den Wert aus dem Image und hängt das Zuhause genau
# dorthin. Steht hier nichts, fällt er auf `/home/kasm-user` zurück.
#
# Die `VNC_*`-Namen bleiben, obwohl hier kein VNC läuft: Sie sind der Vertrag
# mit dem Agent, der sie unverändert durchreicht. Ein zweiter Satz Namen für
# dieselbe Sache wäre eine Fehlerquelle ohne Gewinn — das Startskript nimmt
# aber schon die neuen entgegen, damit die Umbenennung später ohne Bruch geht.
ENV HOME=/home/ota \
    STARTUPDIR=/dockerstartup \
    DISPLAY=:1 \
    VNC_RESOLUTION=1280x720 \
    # **Die Größe des Mauszeigers festnageln.** Ohne `XCURSOR_SIZE` leitet
    # libXcursor sie aus der Bildschirmgrösse ab — `min(Breite, Höhe) / 48`.
    # Gemessen in diesem Image: 1280x720 ergibt 15 Pixel, 3840x2160 ergibt 45.
    #
    # Das ist hier fatal, weil der Rahmen des Xvfb 3840x2160 gross ist und
    # `--enable_resize` den Bildschirm mit dem Browserfenster wachsen lässt:
    # Ein Zeiger, der **danach** zum ersten Mal geladen wird, kommt dreimal so
    # gross heraus wie einer davor. Der Client legt ihn unter seiner Kennung
    # ab und behält ihn — sichtbar als ein Zeiger, der sporadisch riesig wird
    # und es dann bleibt.
    #
    # Auf einem Arbeitsplatz mit vollständiger XFCE-Sitzung setzt `xfsettingsd`
    # die Grösse über XSETTINGS. Auf den Bildschirmen einzelner Anwendungen
    # läuft der nicht — dort ist nur ein Fenstermanager, und niemand sagt es.
    XCURSOR_THEME=Adwaita \
    XCURSOR_SIZE=24 \
    LANG=de_DE.UTF-8 \
    LANGUAGE=de_DE:de \
    LC_ALL=de_DE.UTF-8 \
    SHELL=/bin/bash

# --- Eigene Zertifizierungsstellen ---------------------------------------
#
# Für Firmennetze, deren Proxy TLS aufbricht. Liegt in `ca/` eine `*.crt`,
# wird sie in den Systemspeicher übernommen; ist das Verzeichnis leer — der
# Normalfall —, passiert nichts.
#
# **Vor** dem Grundsystem, weil sonst schon das erste `apt-get update` an
# einem unbekannten Aussteller scheitert. `ca-certificates` kommt dafür
# vorgezogen; der Rest folgt unten.
COPY ca/ /tmp/ota-ca/
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
 && if ls /tmp/ota-ca/*.crt > /dev/null 2>&1; then \
      install -d /usr/local/share/ca-certificates/ota \
      && cp /tmp/ota-ca/*.crt /usr/local/share/ca-certificates/ota/ \
      && update-ca-certificates \
      && echo "Eigene Zertifizierungsstellen übernommen:" \
      && ls -1 /tmp/ota-ca/*.crt; \
    else \
      echo "Keine eigene Zertifizierungsstelle — Normalfall."; \
    fi \
 && rm -rf /tmp/ota-ca \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

# --- Grundsystem ---------------------------------------------------------
#
# Bewusst --no-install-recommends: Die Empfehlungen ziehen an XFCE einen
# Drucker-Stack, einen Indexdienst und einen Mailclient hinterher. Was
# wirklich gebraucht wird, steht hier namentlich.
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl wget gnupg locales tzdata sudo \
      procps psmisc net-tools iproute2 less nano vim-tiny file unzip zip \
      dbus-x11 xauth x11-utils x11-xserver-utils xdg-utils \
      fonts-dejavu-core fonts-liberation fonts-noto-color-emoji \
      mesa-utils libgl1 libegl1 \
 && sed -i 's/^# *\(de_DE.UTF-8\)/\1/;s/^# *\(en_US.UTF-8\)/\1/' /etc/locale.gen \
 && locale-gen \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

# --- XFCE ----------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
      xfce4 xfce4-terminal xfce4-panel xfce4-session xfce4-settings \
      xfwm4 xfdesktop4 thunar mousepad ristretto \
      xfce4-notifyd xfce4-screenshooter \
 && apt-get purge -y xfce4-power-manager xfce4-power-manager-plugins \
      light-locker xscreensaver 2>/dev/null || true \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

# --- Werkzeuge für Fenster und Zwischenablage ----------------------------
#
# `wmctrl` braucht der Agent, um zu erkennen, ob auf einem Display schon eine
# Anwendung läuft, und um sie formatfüllend zu setzen (siehe apps.py).
#
# `clipnotify` fehlt in den Paketquellen und wird deshalb übersetzt. Es
# blockiert, bis sich die Zwischenablage ändert — genau das, was eine Brücke
# sonst im halben Sekundentakt abfragen müsste. Die Übersetzerkette fliegt in
# derselben Schicht wieder raus, sonst läge sie im fertigen Image.
RUN apt-get update && apt-get install -y --no-install-recommends \
      wmctrl xdotool xsel xclip autocutsel \
      build-essential libx11-dev libxfixes-dev git \
 && git clone --depth 1 https://github.com/cdown/clipnotify /tmp/clipnotify \
 && make -C /tmp/clipnotify \
 && install -m 0755 /tmp/clipnotify/clipnotify /usr/local/bin/clipnotify \
 && rm -rf /tmp/clipnotify \
 && apt-get purge -y build-essential libx11-dev libxfixes-dev git \
 && apt-get autoremove -y \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

# --- Was Selkies vom System braucht --------------------------------------
#
# `Xvfb` liefert das Display, das Selkies abgreift; `pulseaudio` den Ton.
#
# **Kein `coturn`.** Vermittelt wird über den Dienst `turn` aus dem Stack, auf
# dem Netz des Hosts. Ein TURN-Server hinter einer Docker-Bridge meldet die
# Adresse des Hosts als Relay und verschickt die Pakete mit der
# Container-Adresse als Absender — der Browser verwirft sie. Siehe
# `deploy/docker-compose.yml` und `scripts/pruef-turn.py`.
RUN apt-get update && apt-get install -y --no-install-recommends \
      xvfb pulseaudio pulseaudio-utils \
      python3-venv python3-pip \
      # `evdev` (über `pynput`) bringt kein fertiges Rad mit und würde sonst
      # übersetzt — mit Übersetzer und Kernel-Kopfdateien im Image. Debian
      # hat es fertig; die Umgebung unten wird mit `--system-site-packages`
      # angelegt und sieht es.
      python3-evdev \
      # Das GStreamer-Bündel bringt nur `gi/overrides` mit, nicht `gi`
      # selbst — das kommt vom System. Ohne es endet Selkies beim Start mit
      # "could not find working GStreamer-Python installation", und der Grund
      # steht nirgends im Klartext.
      python3-gi python3-gi-cairo gir1.2-glib-2.0 \
      libgl1 libegl1 libgbm1 libxcb-shm0 libxdamage1 libxfixes3 libxtst6 \
      # GStreamer aus der Distribution statt aus einem Bündel. `-ugly` bringt
      # `x264enc` (der Kodierer), `-bad` bringt `webrtcbin`, `-x` den
      # Bildschirmabgriff `ximagesrc`, `-pulseaudio` den Ton, `-nice` die
      # ICE-Anbindung. `python3-gst-1.0` ist der Teil, an dem der Versuch mit
      # dem Ubuntu-Bündel gescheitert ist: Er muss zur Python-Fassung der
      # Distribution passen.
      gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
      gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly \
      gstreamer1.0-nice gstreamer1.0-pulseaudio gstreamer1.0-x \
      gstreamer1.0-tools python3-gst-1.0 \
      # Die Introspektionsdaten. Ohne sie startet Selkies mit
      # "Namespace GstWebRTC not available" — die Plugins sind da, aber
      # Python findet die Typbeschreibungen nicht. `GstWebRTC` und `GstSdp`
      # liegen in `-bad`, alles Uebrige in `-base` und im Kern.
      gir1.2-gstreamer-1.0 gir1.2-gst-plugins-base-1.0 \
      gir1.2-gst-plugins-bad-1.0 \
 && apt-get clean && rm -rf /var/lib/apt/lists/* \
 # Laut scheitern, wenn ein Baustein fehlt: Ohne diese beiden Elemente baut
 # Selkies seine Pipeline nicht, und der Fehler faellt sonst erst beim ersten
 # Verbindungsversuch auf — als schwarzes Bild ohne Meldung.
 && gst-inspect-1.0 webrtcbin > /dev/null \
 && gst-inspect-1.0 x264enc > /dev/null \
 # Und die Bruecke nach Python — daran ist der Versuch mit dem Ubuntu-Buendel
 # gescheitert, und zwar zweimal hintereinander mit zwei verschiedenen
 # Meldungen. Hier faellt es beim Bauen auf.
 && python3 -c "import gi; gi.require_version(\"Gst\", \"1.0\"); gi.require_version(\"GstWebRTC\", \"1.0\"); gi.require_version(\"GstSdp\", \"1.0\"); from gi.repository import Gst, GstWebRTC, GstSdp; Gst.init(None); print(\"GStreamer-Python:\", Gst.version_string())"

# --- Selkies -------------------------------------------------------------
#
# Aus dem **getaggten Release** und nicht von `main`. Zwei Anläufe vorher, und
# beide gehören in die Akte:
#
# 1. PyPI führt ein Paket `selkies` in der Fassung 1.6.1 — trotz des Namens
#    ist das die alte GStreamer-Linie, nicht die neue mit WebSocket-Transport.
# 2. Die neue Linie liegt nur auf `main` und verlangt `pixelflux~=2.1.0`, das
#    es nirgends gibt. Ein Testimage, das sich nicht bauen lässt, ist keins.
ARG SELKIES_VERSION=1.6.2
ARG SELKIES_BASE=https://github.com/selkies-project/selkies-gstreamer/releases/download

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
COPY patches/gst-web-pfad.py /tmp/gst-web-pfad.py
RUN python3 /tmp/gst-web-pfad.py /opt/gst-web/app.js && rm -f /tmp/gst-web-pfad.py

# Der Client bringt eine eigene Seitenleiste mit, deren runder Knopf am
# rechten Rand genau unter OTAs Griff liegt. Was darin steht, ist hier fast
# durchweg ueberfluessig (Zwischenablage, Skalierung) oder falsch ("Return to
# launcher" fuehrt aus OTA heraus). Der Kopf der Datei begruendet es; sie
# bricht ab, wenn der Knopf nicht mehr genau einmal vorkommt.
COPY patches/keine-fremde-leiste.py /tmp/keine-fremde-leiste.py
RUN python3 /tmp/keine-fremde-leiste.py /opt/gst-web/index.html \
 && rm -f /tmp/keine-fremde-leiste.py

# Und die Anwendung selbst, in ein eigenes Verzeichnis: Debian verwaltet sein
# Python selbst (PEP 668), und ein `--break-system-packages` wäre genau das,
# was der Name sagt.
#
# **Kein `|| true` am Ende dieser Kette.** Genau das stand hier zuerst und hat
# einen gescheiterten Install in einen grünen Build verwandelt.
ENV SELKIES_HOME=/opt/selkies
RUN python3 -m venv --system-site-packages "$SELKIES_HOME" \
 && "$SELKIES_HOME/bin/pip" install --no-cache-dir --upgrade pip \
 # `setuptools` ist hier kein Beiwerk, sondern Pflicht: Selkies zieht `GPUtil`
 # herein, und das macht `from distutils import spawn`. `distutils` ist mit
 # Python 3.12 aus der Standardbibliothek geflogen (PEP 632) — unter Ubuntus
 # 3.12 fiel das nicht auf, weil dort noch ein Rest lag, unter Debians 3.13
 # bricht Selkies beim Start ab. `setuptools` bringt den Ersatz mit.
 && "$SELKIES_HOME/bin/pip" install --no-cache-dir setuptools \
 && "$SELKIES_HOME/bin/pip" install --no-cache-dir \
      "${SELKIES_BASE}/v${SELKIES_VERSION}/selkies_gstreamer-${SELKIES_VERSION}-py3-none-any.whl" \
 && ln -sf "$SELKIES_HOME/bin/selkies-gstreamer" /usr/local/bin/selkies-gstreamer \
 && test -x "$SELKIES_HOME/bin/selkies-gstreamer" \
 # Nicht nur "die Datei ist da", sondern "sie laesst sich laden". Genau daran
 # ist dieser Bau zweimal gescheitert — einmal an den GStreamer-Bindungen,
 # einmal an `distutils` —, und beide Male stand der Fehler erst im Protokoll
 # der ersten Sitzung, nie im Build.
 #
 # Nicht `--help`: Das verlangt einen laufenden X-Server und ist hier deshalb
 # nicht zu haben. Die drei Module decken die Importe ab, die tatsaechlich
 # brechen koennen.
 && ORT="$(ls -d "$SELKIES_HOME"/lib/python3*/site-packages)/selkies_gstreamer" \
 && PYTHONPATH="$ORT" "$SELKIES_HOME/bin/python" -c \
      "import gpu_monitor, gstwebrtc_app, signalling_web; print('Selkies laedt')"

# Die beiden Eingriffe in Selkies. Der Pfad wird **ermittelt** und nicht
# festgeschrieben: Debian 13 bringt Python 3.13, Ubuntu 24.04 brachte 3.12 —
# ein fester Pfad wäre beim Distributionswechsel still ins Leere gelaufen.
#
#   * Selkies hängt an jede STUN-Liste `stun.l.google.com` an, unabhängig von
#     der Konfiguration. Im Firmennetz ein Ruf nach draussen, den niemand
#     bestellt hat; ohne Internet wartet der Aufbau in einen Zeitablauf.
#   * `iceTransportPolicy` steht fest auf "all". Für Netze mit kleiner
#     Paketgrösse muss es einstellbar sein — Chrome verschickt DTLS mit fest
#     1200 Byte je Paket und passt sich nicht an.
#
# Beide brechen den Build ab, wenn eine neue Selkies-Fassung die Stelle
# verschoben hat. Die Köpfe der Dateien erklären die Messungen.
COPY patches/kein-fremd-stun.py patches/ice-nur-vermittelt.py /tmp/
RUN set -eu; \
    ORT="$(ls -d "$SELKIES_HOME"/lib/python3*/site-packages)"; \
    python3 /tmp/kein-fremd-stun.py "$ORT"; \
    python3 /tmp/ice-nur-vermittelt.py "$ORT"; \
    rm -f /tmp/kein-fremd-stun.py /tmp/ice-nur-vermittelt.py

# `cvt` rechnet eine Modeline aus. Selkies braucht es, um die Auflösung an das
# Browserfenster anzupassen — und **auch Debian 13 liefert es nicht** mehr
# (`x11-xserver-utils` hat es nicht, nachgeprüft). Ohne diesen Ersatz bleibt
# der ferne Bildschirm auf der vollen Grösse des Framebuffers stehen.
COPY bin/cvt /usr/local/bin/cvt
RUN chmod +x /usr/local/bin/cvt \
 && /usr/local/bin/cvt -r 1920 1080 60 | grep -q '138.50  1920 1968 2000 2080'

# --- Der Mensch ----------------------------------------------------------
#
# Kennung 1000, aber **nicht** `kasm-user`: Hier gibt es kein Kasm, und der
# Name hat in einem eigenen Image nichts zu suchen. Die **Zahl** 1000 ist
# dagegen nicht verhandelbar — die vorhandenen Profile auf der Platte gehören
# 1000:1000, und der Agent startet die Sitzung als 1000.
#
# `/home` gehört der Gruppe 1000 und ist für sie beschreibbar, damit das
# Startskript dort den Verweis unter dem OTA-Anmeldenamen anlegen kann. Der
# Pfad selbst bleibt `/home/ota` und wandert nie — genau wie auf dem Host,
# wo unter der Kennung gespeichert und daneben ein lesbarer Verweis gelegt
# wird. Eine Umbenennung in Keycloak verschiebt damit den Verweis, nichts
# sonst; alles, was im Profil einen absoluten Pfad gespeichert hat, bleibt
# gültig.
RUN groupadd -g 1000 ota \
 && useradd -u 1000 -g 1000 -m -d /home/ota -s /bin/bash ota \
 && echo 'ota:ota' | chpasswd \
 && mkdir -p /dockerstartup /var/run/dbus \
 && chown -R 1000:1000 /home/ota \
 && chgrp 1000 /home && chmod 775 /home

COPY dockerstartup/ /dockerstartup/
RUN chmod +x /dockerstartup/*.sh

# Derselbe Port nach aussen wie beim Selkies-Versuch — für Traefik ist es
# dieselbe Route.
EXPOSE 8080

WORKDIR /home/ota
USER 1000

ENTRYPOINT ["/dockerstartup/desktop_startup.sh"]
