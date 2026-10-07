#!/usr/bin/env bash
# Startet Selkies 2.0 für das Display in $DISPLAY auf dem Port $1 — im
# Vordergrund (`exec`). Wer es aufruft, kümmert sich um Hintergrund, Protokoll
# und Prozesskennung:
#
#   desktop_startup.sh   der Hauptbildschirm (:1, Port 8080)
#   agent/otaagent/apps.py   je Anwendung ein eigener Bildschirm (:N, 8080+N)
#
# **Ein Skript für beide**, damit Haupt- und Anwendungsbildschirm nie
# auseinanderlaufen. Dass es diese Datei gibt, ist zugleich die Auskunft an den
# Agent: Ein Image ohne sie trägt noch Selkies 1.6.2 (ein Golden Image auf dem
# alten Basisimage), und der Agent startet dort den alten Weg.
#
# Alles wird über `SELKIES_*`-Einstellungen gesetzt, nicht über Eingriffe in
# den Code (third_party/selkies/OTA-FORK.md). Was ein Arbeitsplatz von aussen
# vorgibt (`SELKIES_FRAMERATE`, `SELKIES_ENCODER`), gewinnt.
set -eu

PORT=${1:?Aufruf: selkies-starten.sh PORT}

# --- Anmeldung -----------------------------------------------------------
# Traefik setzt den Basic-Auth-Header vor jede Route dieser Sitzung; das
# Passwort verlässt den Server nie. Ohne Passwort startet Selkies nicht —
# genau so soll es sein.
export SELKIES_ENABLE_BASIC_AUTH=true
export SELKIES_BASIC_AUTH_USER="${OTA_SESSION_USER:-${VNC_USER:-ota}}"
export SELKIES_BASIC_AUTH_PASSWORD="${OTA_SESSION_PW:-${VNC_PW:?Kein Sitzungspasswort}}"

# --- Transport -----------------------------------------------------------
# **WebSockets, fest.** Bild, Ton, Eingaben und Zwischenablage laufen über den
# einen Port durch Traefik — wie die Oberfläche selbst. Kein UDP, kein TURN,
# keine Frage nach der Paketgrösse eines VPN. WebRTC bliebe als Umschalter in
# der Oberfläche; abgeschaltet, weil es ohne TURN hier nicht trägt.
export SELKIES_MODE=websockets
export SELKIES_ENABLE_DUAL_MODE=false
# TLS beendet Traefik.
export SELKIES_ENABLE_HTTPS=false

# --- Was der Arbeitsplatz NICHT kann -------------------------------------
# Jeder dieser Wege wäre ein neuer Weg für Daten aus dem Arbeitsplatz hinaus
# oder hinein, an OTAs Ablagen, Rechten und Protokoll vorbei. Selkies 1.6.2
# hatte keinen davon; mit 2.0 kamen sie, und zwar eingeschaltet.
export SELKIES_FILE_TRANSFERS=none
export SELKIES_PRINTING_ENABLED=false
export SELKIES_ENABLE_SHARING=false
export SELKIES_ENABLE_COLLAB=false
export SELKIES_ENABLE_SHARED=false
export SELKIES_ENABLE_PLAYER2=false
export SELKIES_ENABLE_PLAYER3=false
export SELKIES_ENABLE_PLAYER4=false
export SELKIES_COMMAND_ENABLED=false
export SELKIES_MICROPHONE_ENABLED=false
export SELKIES_WEBCAM_ENABLED=false
export SELKIES_GAMEPAD_ENABLED=false
# Ein Bildschirm je Seite — mehrere Anwendungen sind bei OTA mehrere
# Bildschirme, nicht ein erweiterter Schreibtisch.
export SELKIES_SECOND_SCREEN=false

# --- Oberfläche ----------------------------------------------------------
# Die Seitenleiste von Selkies läge genau unter OTAs Griff am rechten Rand,
# und was darin steht, regelt OTA selbst. Bei 1.6.2 musste dafür ein Patch
# ins HTML; jetzt ist es eine Einstellung.
export SELKIES_UI_SHOW_SIDEBAR=false
export SELKIES_UI_SHOW_CORE_BUTTONS=false
export SELKIES_UI_SHOW_LOGO=false

# --- Bild ----------------------------------------------------------------
# H.264 in Software (x264), solange keine GPU da ist; pixelflux nimmt eine,
# wenn es eine findet. 30 Bilder je Sekunde wie bisher.
export SELKIES_ENCODER="${SELKIES_ENCODER:-h264enc}"
export SELKIES_FRAMERATE="${SELKIES_FRAMERATE:-30}"

# Die Zwischenablage in beide Richtungen, wie bisher.
export SELKIES_ENABLE_CLIPBOARD="${SELKIES_ENABLE_CLIPBOARD:-true}"

# Port und Adresse auf der Kommandozeile und nicht in der Umgebung: Der Agent
# erkennt den Hauptbildschirm an `--port=8080` in der Prozessliste.
exec selkies --addr=0.0.0.0 --port="$PORT"
