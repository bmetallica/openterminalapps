# OTAs eigenes Basisimage: Ubuntu + XFCE + KasmVNC aus dem offiziellen Release.
#
# **Warum überhaupt ein eigenes.** Bisher leitet jeder Arbeitsplatz von einem
# Kasm-Anwendungsimage ab (`kasmweb/vs-code` und Verwandte). Das brachte drei
# Dinge mit, die dort stören: eine Anwendung, die von selbst startet und im
# Drei-Sekunden-Takt neu gestartet wird (siehe `WORKSPACE_STARTUP` im Agent),
# 6 GB Ballast für eine Anwendung, die der Arbeitsplatz gar nicht braucht, und
# das Label `com.kasmweb.image`, wegen dessen Kasms eigener Aufräumer das
# fertige Image Sekunden nach dem Bau wieder löscht.
#
# Und es fehlten drei Kleinigkeiten, an denen die Zwischenablage hängt:
# `clipnotify` (eine ereignisgesteuerte Brücke statt der Abfrage im halben
# Sekundentakt), `xsel` und `autocutsel`.
#
# **Dies ist ein Testimage.** Es trägt `:test`, keine Vorlage zeigt darauf, und
# `ota/arbeitsplatz` bleibt unberührt. Erst wenn ein Arbeitsplatz darauf
# nachweislich so läuft wie bisher, wird daraus ein `:1`.
#
# KasmVNC ist bewusst auf **1.4.0** festgenagelt und nicht auf 1.5.0. Das
# heutige Image bringt 1.4.1 mit — die gibt es öffentlich nicht, Kasm baut sie
# nur für die eigenen Images. 1.4.0 ist derselbe Stand der Weboberfläche, und
# genau darauf kommt es an: Die OTA-Oberfläche spricht mit ihr (Reconnect,
# `set_idle_timeout` per postMessage, `idle_disconnect` als Auswahlfeld mit
# genau vier Werten — ein Wert ausserhalb fällt stumm auf den ersten zurück).
# Ein Sprung auf 1.5.0 ist ein eigener, eigens zu prüfender Schritt.
#
# **Warum überhaupt KasmVNC und nichts Eigenes.** Selbst gebaut hiesse hier
# schlechter: x11vnc ist einfädig und seit Jahren ungepflegt, TigerVNC ist der
# Stamm, von dem KasmVNC abzweigt — wir würden genau die Teile weglassen, die
# ihn ausmachen (mehrfädige WebP-Kodierung, DLP_ClipDelay, KasmPasswordFile).
# Wirklich besser wäre nur ein Wechsel des Verfahrens: WebRTC statt RFB. Das
# ist ein eigener Meilenstein mit eigener Abnahme (roadmap.md) und nicht
# nebenbei im Basisimage zu erledigen.

FROM ubuntu:24.04

ARG KASMVNC_VERSION=1.4.0
ARG DEBIAN_FRONTEND=noninteractive

# Kein Kasm-Label. Siehe render_dockerfile im Agent: Kasms Aufräumer löscht im
# Modus "Aggressive" alle 30 Sekunden Images mit com.kasmweb.image=true, die
# nicht in seiner Datenbank stehen. Ein Image ohne das Label sieht er nicht an.
LABEL org.opencontainers.image.title="OpenTerminalApps Basisimage (XFCE)" \
      org.opencontainers.image.description="Ubuntu 24.04 + XFCE + KasmVNC, ohne Anwendung" \
      org.opencontainers.image.licenses="GPL-2.0-or-later AND MIT" \
      com.kasmweb.image=""

ENV HOME=/home/kasm-user \
    STARTUPDIR=/dockerstartup \
    DISPLAY=:1 \
    VNC_PORT=5901 \
    VNC_WEB_PORT=6901 \
    VNC_COL_DEPTH=24 \
    VNC_RESOLUTION=1280x720 \
    LANG=de_DE.UTF-8 \
    LANGUAGE=de_DE:de \
    LC_ALL=de_DE.UTF-8 \
    SHELL=/bin/bash

# --- Grundsystem ---------------------------------------------------------
#
# Bewusst --no-install-recommends: Ubuntus Empfehlungen ziehen an XFCE einen
# Drucker-Stack, einen Indexdienst und einen Mailclient hinterher. Was wirklich
# gebraucht wird, steht hier namentlich.
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
# `clipnotify` fehlt in Ubuntus Paketquellen und wird deshalb übersetzt. Es
# blockiert, bis sich die Zwischenablage ändert — genau das, was die heutige
# Brücke im halben Sekundentakt abfragen muss.
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

# --- KasmVNC -------------------------------------------------------------
#
# Aus dem offiziellen Release, nicht aus einem fremden Image. Die Prüfsumme
# wird bewusst nicht festgeschrieben: GitHub liefert das Paket über HTTPS, und
# eine Prüfsumme im Dockerfile, die bei jedem Versionswechsel von Hand
# nachgezogen werden muss, ist erfahrungsgemäß nach dem zweiten Mal falsch.
# Wer strenger sein will, spiegelt das Paket und setzt KASMVNC_URL.
ARG KASMVNC_URL=https://github.com/kasmtech/KasmVNC/releases/download/v${KASMVNC_VERSION}/kasmvncserver_noble_${KASMVNC_VERSION}_amd64.deb
RUN apt-get update \
 && curl -fsSL -o /tmp/kasmvnc.deb "$KASMVNC_URL" \
 && apt-get install -y --no-install-recommends /tmp/kasmvnc.deb \
 && rm -f /tmp/kasmvnc.deb \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

# --- Der Mensch ----------------------------------------------------------
#
# Kennung 1000 heisst `kasm-user` und liegt unter /home/kasm-user. Beides ist
# nicht frei wählbar: Der Agent hängt das Zuhause genau dorthin, startet
# Anwendungen mit HOME=/home/kasm-user und die Sitzung als 1000 — und die
# vorhandenen Ablagen auf der Platte gehören 1000:1000.
# Ubuntu 24.04 bringt selbst schon ein Konto `ubuntu` mit der Kennung 1000
# mit. Es muss weg, sonst ist die 1000 belegt — und die 1000 ist hier nicht
# verhandelbar, siehe oben.
RUN userdel -r ubuntu 2>/dev/null || true \
 && groupdel ubuntu 2>/dev/null || true \
 && groupadd -g 1000 kasm-user \
 && useradd -u 1000 -g 1000 -m -d /home/kasm-user -s /bin/bash kasm-user \
 && echo 'kasm-user:kasm-user' | chpasswd \
 && mkdir -p /dockerstartup /var/run/dbus \
 && chown -R 1000:1000 /home/kasm-user

COPY dockerstartup/ /dockerstartup/
RUN chmod +x /dockerstartup/*.sh

EXPOSE 6901
WORKDIR /home/kasm-user
USER 1000

ENTRYPOINT ["/dockerstartup/vnc_startup.sh"]
