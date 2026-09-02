#!/usr/bin/env bash
# Der Platzhalter des Basisimages: Es startet nichts von selbst.
#
# Ein abgeleitetes Einzelanwendungs-Image überschreibt diese Datei mit dem
# Aufruf seiner Anwendung. Ein Arbeitsplatz lässt sie, wie sie ist — OTA hängt
# dort ohnehin ein eigenes Skript darüber und startet Anwendungen auf Zuruf.
#
# Das Skript darf sich nicht beenden: vnc_startup.sh startet es sonst alle
# drei Sekunden neu.
while true; do sleep 3600; done
