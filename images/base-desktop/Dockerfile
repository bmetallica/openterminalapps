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

# Der Datei-Vorrat der eigenen Paketquelle (Handbuch Kapitel 26): Selkies,
# clipnotify und die pip-Pakete, damit der Bau ohne GitHub und PyPI auskommt.
# Diese Stufe ist leer; `scripts/build-desktop-image.sh` ersetzt sie durch den
# Vorrat (`--build-context ota-dateien=…`), wenn es einen gibt. Ohne ihn lädt
# jeder Schritt wie bisher aus dem Internet.
FROM scratch AS ota-dateien

# Das Paket ota-selkies (scripts/build-selkies-deb.sh). Auch diese Stufe ist
# leer; das Bauskript ersetzt sie (`--build-context ota-pakete=…`).
FROM scratch AS ota-pakete

FROM debian:13

ARG DEBIAN_FRONTEND=noninteractive

LABEL org.opencontainers.image.title="OpenTerminalApps Basisimage (Debian/XFCE/Selkies)" \
      org.opencontainers.image.description="Debian 13 + XFCE + Selkies 2.0 über WebSockets, ohne KasmVNC" \
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
RUN --mount=type=bind,from=ota-dateien,target=/mnt/ota-dateien \
    apt-get update && apt-get install -y --no-install-recommends \
      wmctrl xdotool xsel xclip autocutsel \
      build-essential libx11-dev libxfixes-dev git \
 && if [ -f /mnt/ota-dateien/clipnotify/clipnotify.tar.gz ]; then \
      mkdir -p /tmp/clipnotify \
      && tar -xzf /mnt/ota-dateien/clipnotify/clipnotify.tar.gz -C /tmp/clipnotify --strip-components=1; \
    else \
      git clone --depth 1 https://github.com/cdown/clipnotify /tmp/clipnotify; \
    fi \
 && make -C /tmp/clipnotify \
 && install -m 0755 /tmp/clipnotify/clipnotify /usr/local/bin/clipnotify \
 && rm -rf /tmp/clipnotify \
 && apt-get purge -y build-essential libx11-dev libxfixes-dev git \
 && apt-get autoremove -y \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

# --- Selkies -------------------------------------------------------------
#
# **Über das Paket ota-selkies**, und nur darüber: Selkies 2.0 aus OTAs Fork
# (`third_party/selkies`, OTA-FORK.md) samt Abhängigkeiten unter /opt/selkies,
# dazu `desktop_startup.sh` und `selkies-starten.sh`. Dasselbe Paket hebt alte
# Golden Images an und aktualisiert Root-Arbeitsplätze beim Fortsetzen
# (Kapitel 20) — ein Weg statt zweier, die auseinanderlaufen.
#
# Die Bibliotheken, die pixelflux und pcmflux brauchen (`libgbm`, `libva` …),
# zieht apt als Abhängigkeiten des Pakets herein. **Kein GStreamer mehr**:
# Selkies 2.0 nimmt Bild und Ton mit eigenen Erweiterungen auf.
#
# Bauen mit `scripts/build-desktop-image.sh`; es baut das Paket bei Bedarf
# und reicht es herein. Ohne Paket bricht der Bau hier ab.
RUN --mount=type=bind,from=ota-pakete,target=/mnt/ota-pakete \
    PAKET=$(ls /mnt/ota-pakete/ota-selkies_*_amd64.deb 2>/dev/null | head -1); \
    if [ -z "$PAKET" ]; then \
      echo "Das Paket ota-selkies fehlt. Bauen mit scripts/build-desktop-image.sh —" \
           "das baut es (scripts/build-selkies-deb.sh) und reicht es herein." >&2; exit 1; \
    fi \
 && cp "$PAKET" /tmp/ \
 && apt-get update \
 && apt-get install -y --no-install-recommends "/tmp/$(basename "$PAKET")" \
 && rm -f /tmp/ota-selkies_*.deb \
 && apt-get clean && rm -rf /var/lib/apt/lists/* \
 # Nicht nur "es ist installiert", sondern "es laedt": die beiden Rust-
 # Erweiterungen mit den Bibliotheken des Systems. Ein Fehler hier faellt sonst
 # erst in der ersten Sitzung auf, als schwarzer Bildschirm.
 && /opt/selkies/bin/python -c "import pixelflux, pcmflux, selkies.settings, selkies.websockets_mode, selkies.stream_server; from importlib.metadata import version; print('Selkies', version('selkies'), 'laedt')" \
 && dpkg-query -W ota-selkies
ENV SELKIES_HOME=/opt/selkies

# `cvt` rechnet eine Modeline aus. Selkies 2.0 stellt die Auflösung zuerst
# selbst über RandR um und greift nur im Rückfall zu `xrandr`/`cvt` — und
# **Debian 13 liefert `cvt` nicht** mehr (`x11-xserver-utils` hat es nicht,
# nachgeprüft). Ohne diesen Ersatz bliebe der ferne Bildschirm in diesem Fall
# auf der vollen Grösse des Framebuffers stehen.
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

# Die beiden Startskripte für Selkies bringt das Paket ota-selkies mit; hier
# nur das, was ein abgeleitetes Image überschreibt.
COPY dockerstartup/custom_startup.sh /dockerstartup/custom_startup.sh
RUN chmod +x /dockerstartup/*.sh

# Derselbe Port nach aussen wie beim Selkies-Versuch — für Traefik ist es
# dieselbe Route.
EXPOSE 8080

WORKDIR /home/ota
USER 1000

ENTRYPOINT ["/dockerstartup/desktop_startup.sh"]
