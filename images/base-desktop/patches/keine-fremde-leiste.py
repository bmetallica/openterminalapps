#!/usr/bin/env python3
"""Nimmt Selkies' eigenen Aufklapp-Knopf aus der Oberfläche.

**Das Problem.** Der Selkies-Client bringt eine eigene Seitenleiste mit,
aufklappbar über einen runden Knopf am **rechten** Rand
(`<v-btn class="fab-container" … fixed right>`). OTAs Kontrollleiste hat ihren
Griff an derselben Stelle (`.viewer__handle`, `right: 0; top: 50%`) — die
beiden liegen übereinander, und welcher getroffen wird, ist Zufall.

**Warum der von Selkies weicht und nicht der von OTA.** Was in dieser Leiste
steht, ist hier fast durchweg überflüssig oder falsch:

* *Enable clipboard access* — macht OTA selbst, mit einer eigenen Brücke, die
  auch die Systemzwischenablage des Anwenders erreicht.
* *Resize remote to fit window*, *Scale to fit* — steht serverseitig fest
  (`--enable_resize=true`), und zwei Stellen für dieselbe Einstellung sind
  eine Fehlerquelle.
* *Force relay connection* — entscheidet `OTA_TURN_ICE_POLICY` in der `.env`,
  aus gutem Grund für die ganze Anlage und nicht je Sitzung.
* **Return to launcher** — führt aus OTA heraus auf Selkies' eigene
  Startseite. In einer eingebetteten Sitzung ist das schlicht ein Ausgang ins
  Nichts.

Übrig bliebe die Diagnose (Protokoll, CPU-Last, Gamepad). Die ist es nicht
wert, dass zwei Knöpfe übereinanderliegen; wer sie braucht, erreicht die
Leiste weiterhin über die Tastenkombination, die der Client selbst kennt
(`showDrawer` in `app.js`).

**Was hier nicht passiert:** Die Leiste selbst bleibt im Markup. Sie zu
entfernen hiesse, in Vuetifys Aufbau einzugreifen; der Knopf ist ein Element,
und mehr braucht es nicht.
"""

import pathlib
import re
import sys

# Der Knopf, wie ihn Selkies 1.6.2 setzt. Bewusst als Muster und nicht als
# fester Text: Zwischen den Attributen darf sich die Reihenfolge ändern, ohne
# dass dieser Patch stillschweigend danebengreift.
KNOPF = re.compile(
    r'<v-btn\s+class="fab-container"[^>]*>\s*</v-btn>',
    re.IGNORECASE | re.DOTALL,
)

ERSATZ = ("<!-- OTA: Selkies' eigener Leistenknopf entfernt — er lag genau "
          "unter OTAs Griff. Siehe patches/keine-fremde-leiste.py. -->")


def main() -> int:
    datei = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "/opt/gst-web/index.html")
    text = datei.read_text(encoding="utf-8")

    if "keine-fremde-leiste" in text:
        print("Leistenknopf ist schon entfernt")
        return 0

    neu, anzahl = KNOPF.subn(ERSATZ, text)
    if anzahl != 1:
        # Laut scheitern statt still nichts zu tun: Findet sich der Knopf
        # nicht mehr oder plötzlich mehrfach, liegen die beiden Griffe wieder
        # übereinander — und das fiele erst dem Anwender auf.
        print(f"Erwartet wurde genau ein Leistenknopf, gefunden: {anzahl}. "
              "Selkies-Fassung geaendert? Die Oberflaeche muss neu geprueft "
              "werden.", file=sys.stderr)
        return 1

    datei.write_text(neu, encoding="utf-8")
    print("Selkies' Leistenknopf entfernt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
