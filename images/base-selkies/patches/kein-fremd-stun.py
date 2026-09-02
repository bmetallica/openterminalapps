#!/usr/bin/env python3
"""Nimmt Googles STUN-Server aus dem, was Selkies dem Browser mitgibt.

**Was Selkies tut.** Zu jeder STUN-Liste hängt es `stun.l.google.com` an —
unabhängig davon, was konfiguriert ist:

    if stun_host != "stun.l.google.com" or (str(stun_port) != "19302"):
        stun_list.append("stun:stun.l.google.com:19302")

Als Rückfallebene im offenen Netz ist das vernünftig gedacht. Für OTA ist es
falsch, aus zwei Gründen:

* **Es ruft nach draussen.** Jede Sitzung fragt einen Server von Google, wie
  der Browser des Anwenders von aussen aussieht. Das hat in einer Anlage, die
  im Firmennetz steht, niemand bestellt — und in einem Netz ohne Internet
  wartet der Verbindungsaufbau erst einmal in einen Zeitablauf hinein.
* **Es hilft hier nichts.** Browser und Session-Container liegen im selben
  Netz. Was der Browser draussen für eine Adresse hat, ist für den Medienweg
  ohne Belang; vermittelt wird über OTAs eigenen TURN-Server, und der spricht
  auch STUN.

Betroffen sind drei Sorten Stellen: der Anhang oben, die Vorgabe für
`--stun_host`, und die Beispielkonfiguration, die ohne TURN gilt. Danach steht
in der Konfiguration nur noch, was in `deploy/.env` konfiguriert ist.

Wer die Rückfallebene doch will, nimmt den Aufruf aus dem Dockerfile.
"""

import pathlib
import sys

ZIEL = (
    "selkies_gstreamer/signalling_web.py",
    "selkies_gstreamer/__main__.py",
)

ANHANG_ALT = (
    '    if stun_host != "stun.l.google.com" or (str(stun_port) != "19302"):\n'
    '        stun_list.append("stun:stun.l.google.com:19302")\n'
)
ANHANG_NEU = "    # Kein fremder STUN-Server. Siehe patches/kein-fremd-stun.py.\n"

# Ein leerer STUN-Host soll heissen "keiner" und nicht "einer namens nichts".
# Ohne diese Zeile landet `stun::19302` in der Liste, sobald die Vorgabe
# weiter unten leer ist.
LEER_ALT = ("    if stun_host is not None and stun_port is not None and "
            "(stun_host != turn_host or str(stun_port) != str(turn_port)):")
LEER_NEU = ("    if stun_host and stun_port and "
            "(stun_host != turn_host or str(stun_port) != str(turn_port)):")

GEMEINSAM = ((ANHANG_ALT, ANHANG_NEU), (LEER_ALT, LEER_NEU))

# Die Beispielkonfiguration, die gilt, solange kein TURN eingerichtet ist.
# Ohne TURN kommt in diesem Netz ohnehin keine Verbindung zustande; ein Ruf
# nach Kalifornien macht sie nicht wahrscheinlicher.
VORGABE_ALT = ('      "urls": [\n'
               '        "stun:stun.l.google.com:19302"\n'
               '      ]\n')
VORGABE_NEU = '      "urls": []\n'

# Und je Datei die Vorgabe, die gilt, wenn niemand etwas angibt.
EINZELN = {
    "selkies_gstreamer/signalling_web.py": (
        ("parser.add_argument('--stun_host', default=\"stun.l.google.com\", type=str,",
         "parser.add_argument('--stun_host', default=\"\", type=str,"),
    ),
    "selkies_gstreamer/__main__.py": (
        ("'SELKIES_STUN_HOST', 'stun.l.google.com'),",
         "'SELKIES_STUN_HOST', ''),"),
        (VORGABE_ALT, VORGABE_NEU),
        # Der Hilfetext stuende sonst da und behauptete eine Vorgabe, die es
        # nicht mehr gibt.
        ('defaults to "stun.l.google.com"',
         "no default here, see patches/kein-fremd-stun.py"),
    ),
}


def main() -> int:
    wurzel = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".")

    for name in ZIEL:
        datei = wurzel / name
        text = datei.read_text(encoding="utf-8")

        for alt, neu in GEMEINSAM + EINZELN.get(name, ()):
            if alt not in text:
                if neu.strip() and neu.strip() in text:
                    continue
                # Laut scheitern statt still nichts zu tun: Eine neue
                # Selkies-Fassung kann die Stelle geaendert haben, und dann
                # ruft die Anlage wieder nach draussen, ohne dass es jemandem
                # auffaellt.
                print(f"Die erwartete Stelle steht nicht in {name}:\n"
                      f"  {alt.strip()[:90]}\n"
                      "Selkies-Fassung geaendert? Der Ruf nach aussen muss "
                      "neu geprueft werden.", file=sys.stderr)
                return 1
            text = text.replace(alt, neu)

        datei.write_text(text, encoding="utf-8")

    uebrig = [n for n in ZIEL
              if "stun.l.google.com" in (wurzel / n).read_text(encoding="utf-8")]
    if uebrig:
        print("stun.l.google.com steht noch in: " + ", ".join(uebrig),
              file=sys.stderr)
        return 1

    print("kein fremder STUN mehr in: " + ", ".join(ZIEL))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
