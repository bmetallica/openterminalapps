# Basisimage für Root-Arbeitsplätze: das Desktop-Basisimage plus Docker.
#
# Läuft **nur** unter Sysbox (`runtime=sysbox-runc`), nie unter `runc`. Unter
# Sysbox ist root im Container auf dem Wirt ein unprivilegierter Nutzer, und
# `dockerd` läuft ohne `--privileged` (Handbuch Kapitel 25, ADR-007). Unter
# `runc` bräuchte derselbe `dockerd` `--privileged` — genau das, was dieser
# Weg vermeiden soll. Der Agent startet Vorlagen der Klasse `root` deshalb
# ausschliesslich mit Sysbox und verweigert den Start, wenn es fehlt.
#
# Gebaut von `scripts/build-root-image.sh`, auf `ota/base-desktop:1`.
ARG BASIS=ota/base-desktop:1
FROM ${BASIS}

LABEL org.opencontainers.image.title="OpenTerminalApps Root-Arbeitsplatz (Debian/XFCE/Selkies + Docker)" \
      org.opencontainers.image.description="Basisimage mit root und Docker im Container, nur unter Sysbox" \
      org.opencontainers.image.licenses="MPL-2.0 AND GPL-2.0-or-later AND MIT AND Apache-2.0" \
      ota.klasse="root"

USER root
ARG DEBIAN_FRONTEND=noninteractive

# Docker aus Dockers eigener Paketquelle, nicht `docker.io` aus Debian: Nur
# dort gibt es `docker compose` (v2) und `buildx` als Plugins, und genau die
# sind der Grund für diese Klasse.
RUN install -m 0755 -d /etc/apt/keyrings \
 && curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc \
 && chmod a+r /etc/apt/keyrings/docker.asc \
 && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
      > /etc/apt/sources.list.d/docker.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
      docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin \
      iptables kmod \
 && apt-get clean && rm -rf /var/lib/apt/lists/* \
 # Der Mensch am Arbeitsplatz ist hier root — das ist die Klasse. `sudo`
 # ohne Kennwort, und `docker` ohne `sudo`.
 && usermod -aG docker ota \
 && printf 'ota ALL=(ALL) NOPASSWD:ALL\n' > /etc/sudoers.d/ota-root \
 && chmod 0440 /etc/sudoers.d/ota-root \
 && mkdir -p /etc/ota \
 # Selbstprüfung: Ein Image, dem `compose` fehlt, ist für diese Klasse
 # wertlos — und das soll beim Bauen auffallen, nicht beim ersten Nutzer.
 && docker --version && docker compose version && docker buildx version

COPY dockerstartup/root_startup.sh /dockerstartup/root_startup.sh
RUN chmod 0755 /dockerstartup/root_startup.sh

# **Root bleibt der Startnutzer.** `dockerd` muss als root starten; der
# Desktop läuft danach trotzdem als 1000 (`root_startup.sh`). Der Agent führt
# seine Befehle ohnehin ausdrücklich als 1000 aus.
USER root
ENTRYPOINT ["/dockerstartup/root_startup.sh"]
