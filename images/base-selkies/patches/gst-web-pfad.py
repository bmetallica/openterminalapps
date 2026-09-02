#!/usr/bin/env python3
"""Der Selkies-Client baut seine Signalisierungsadresse aus dem falschen Teil
des Pfades. Diese Datei setzt das gerade.

**Was er tut.** In `app.js` steht:

    appName: window.location.pathname.endsWith("/")
             && (window.location.pathname.split("/")[1]) || "webrtc",
    ...
    new URL(protocol + window.location.host + "/" + app.appName + "/signalling/")

Er nimmt also das **erste** Segment des Pfades und hängt es an die Wurzel des
Hosts. Für eine Anlage, die unter `/webrtc/` liegt, stimmt das.

**Warum das bei OTA nicht stimmt.** Eine Session liegt unter
`/s/<kennung>/` — zwei Segmente. Das erste ist `s`, und der Client landet
damit bei `wss://host/s/signalling/`. Dort steht keine Session, sondern OTAs
Weboberfläche: Die Seite baut sich vollständig auf, das Bild bleibt aber
schwarz, und in keinem Protokoll steht, warum.

Genau derselbe Fehler wie seinerzeit bei KasmVNC, das seinen Websocket-Pfad
ebenfalls an die Wurzel hängte. Dort liess er sich über einen Parameter in der
Adresse geradeziehen (`?path=`); hier gibt es den nicht, also wird die eine
Zeile ersetzt.

**Was danach gilt.** `appName` ist der ganze Pfad ohne führende und folgende
Schrägstriche — für `/s/<kennung>/` also `s/<kennung>`, und die Adresse wird
`wss://host/s/<kennung>/signalling/`. Traefik schneidet das Präfix ab, und
Selkies sieht `/signalling/`, wie es das erwartet. Für einen Aufruf direkt
unter `/` bleibt es bei `webrtc` — wie vorher.
"""

import pathlib
import sys

# Zwei Stellen, derselbe Fehler: Beide zeigen auf die Wurzel des Hosts statt
# auf den Pfad, unter dem die Seite wirklich liegt.
ERSETZUNGEN = (
    (
        'appName: window.location.pathname.endsWith("/") '
        '&& (window.location.pathname.split("/")[1]) || "webrtc",',
        'appName: (window.location.pathname.replace(/^\\/+|\\/+$/g, "")) '
        '|| "webrtc",',
        "Signalisierungspfad",
    ),
    (
        # Die Adresse der ICE-Server. Sie wird **vor** der Signalisierung
        # geholt, und wenn sie fehlschlaegt, versucht der Client nicht einmal
        # eine WebSocket-Verbindung: Die Seite steht da, der Status bleibt auf
        # "connecting", und in der Konsole steht ein einzelnes 401 — von OTAs
        # eigener Schnittstelle, bei der die Anfrage gelandet ist.
        'fetch("/turn")',
        'fetch("turn")',
        "Adresse der ICE-Server",
    ),
)


def main() -> int:
    datei = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "/opt/gst-web/app.js")
    text = datei.read_text(encoding="utf-8")
    getan = []

    for alt, neu, was in ERSETZUNGEN:
        if neu in text and alt not in text:
            getan.append(f"{was}: schon gesetzt")
            continue
        if alt not in text:
            # Laut scheitern und nicht stillschweigend nichts tun: Eine neue
            # Selkies-Fassung kann die Zeile geaendert haben, und dann ist
            # diese Datei falsch — das soll beim Bauen auffallen, nicht beim
            # Benutzen.
            print(f"Die erwartete Stelle fuer {was} steht nicht in app.js — "
                  "Selkies-Fassung geaendert? Beide Pfade muessen neu "
                  "geprueft werden.", file=sys.stderr)
            return 1
        text = text.replace(alt, neu, 1)
        getan.append(f"{was}: korrigiert")

    datei.write_text(text, encoding="utf-8")
    print("; ".join(getan))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
