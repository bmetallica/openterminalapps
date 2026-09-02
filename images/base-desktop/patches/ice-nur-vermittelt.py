#!/usr/bin/env python3
"""Macht `iceTransportPolicy` einstellbar, damit auch Wege mit kleiner MTU tragen.

Selkies schreibt `"iceTransportPolicy": "all"` fest in die Konfiguration, die
der Browser bekommt. Damit darf der Browser jeden Weg nehmen, den er findet —
und er nimmt den mit der höchsten Priorität, nicht den, der trägt.

**Warum das ein Problem ist.** Chrome verschickt seinen DTLS-Handschlag mit
fest **1200 Byte** je Paket und passt sich einer kleineren Pfadgrösse *nicht*
an. Wo weniger durchpasst — ein WireGuard-Tunnel mit MTU 1000 zum Beispiel —
kommt das grosse Paket nie an, während die kleinen durchgehen. Gemessen an
zwei Sitzungen desselben Aufbaus:

    funktionierender Weg:  1200, 263, 1200, 263, …
    Weg über den Tunnel:   263, 263, 263, …  (24 mal, nichts sonst)

OpenSSL wartet auf den fehlenden Teil des Handschlags und antwortet deshalb
gar nicht. Im Container steht kein Fehler, im Browser steht „Waiting for
stream", und der Browser wiederholt sein Paket bis in alle Ewigkeit.

**Was `relay` daran ändert.** Der Browser verwirft dann seine eigenen
Kandidaten und schickt alles über den TURN-Server. Zusammen mit
`OTA_TURN_PROTOCOL=tcp` liegt die Strecke Browser–TURN in einem TCP-Strom,
und TCP handelt seine Segmentgrösse mit dem Pfad selbst aus. Die Frage nach
der Paketgrösse stellt sich damit nicht mehr.

Es kostet etwas: Jedes Byte läuft über den TURN-Server, auch für Anwender im
selben Netz, die direkt könnten. Deshalb bleibt `all` die Vorgabe.
"""

import pathlib
import sys

ZIEL = (
    "selkies_gstreamer/signalling_web.py",
    "selkies_gstreamer/__main__.py",
)

ALT = '''    rtc_config["iceTransportPolicy"] = "all"'''
NEU = '''    # OTA: einstellbar statt fest. Siehe patches/ice-nur-vermittelt.py.
    rtc_config["iceTransportPolicy"] = os.environ.get(
        "SELKIES_ICE_TRANSPORT_POLICY", "all")'''


def main() -> int:
    wurzel = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    for name in ZIEL:
        datei = wurzel / name
        text = datei.read_text(encoding="utf-8")
        if "SELKIES_ICE_TRANSPORT_POLICY" in text:
            continue
        if ALT not in text:
            # Laut scheitern statt still nichts zu tun: Eine neue
            # Selkies-Fassung kann die Zeile geaendert haben, und dann steht
            # die Einstellung wirkungslos in der .env.
            print(f"Die erwartete Stelle steht nicht in {name} — "
                  "Selkies-Fassung geaendert?", file=sys.stderr)
            return 1
        text = text.replace(ALT, NEU)
        # `os` ist in signalling_web.py nicht zwingend importiert.
        if "\nimport os\n" not in text and "\nimport os," not in text:
            text = text.replace("\nimport json\n", "\nimport json\nimport os\n", 1)
        datei.write_text(text, encoding="utf-8")

    fehlt = [n for n in ZIEL
             if "SELKIES_ICE_TRANSPORT_POLICY" not in (wurzel / n).read_text(encoding="utf-8")]
    if fehlt:
        print("nicht gesetzt in: " + ", ".join(fehlt), file=sys.stderr)
        return 1
    print("iceTransportPolicy ist einstellbar")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
