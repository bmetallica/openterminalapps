#!/usr/bin/env python3
"""Bietet dem Browser den TURN-Server über **beide** Wege an: UDP und TCP.

Selkies liefert genau einen TURN-Eintrag aus, mit dem Transport aus
`--turn_protocol`. Fällt dieser eine Weg aus, ist die Sitzung tot — obwohl
derselbe Server über den anderen erreichbar wäre. Dieser Eingriff macht aus
dem einen Eintrag zwei: denselben Server einmal über UDP, einmal über TCP.

**Was das leistet — und was ausdrücklich nicht.**

Der eingestellte Transport steht **zuerst** und bleibt der bevorzugte. Der
zweite ist eine Rückfallebene für den Fall, dass der erste *vollständig*
blockiert ist — etwa UDP in einem Netz, das nur TCP durchlässt.

Was es **nicht** leistet: automatisch den tragfähigen Weg finden, wenn einer
nur *teilweise* funktioniert. Der wichtigste Fall dafür ist eine kleine MTU.
Gemessen am 2026-09-03 unter nachgestellten Tunnelbedingungen (MTU 1000,
grosse UDP-Pakete verworfen), mit `udp` als Vorgabe und beiden Wegen im
Angebot:

    Gewaehlte Kandidatenpaare:
      host/:44991 -> relay/192.168.66.224:49185  empfangen=0B gesendet=14630B
    KEIN BILD.

Der Grund liegt in ICE selbst: Es prüft Wege mit **kleinen** Paketen. Der
UDP-Weg wirkt damit tragfähig und gewinnt wegen der höheren Priorität — dass
er beim 1200 Byte grossen DTLS-Handschlag bricht, erfährt ICE nie. Eine
MTU-Begrenzung ist für ICE unsichtbar.

**Für solche Netze bleibt die Einstellung nötig**: `OTA_TURN_PROTOCOL=tcp`
zusammen mit `OTA_TURN_ICE_POLICY=relay`. Dass beide Wege angeboten werden,
schadet dabei nicht — derselbe Versuch mit dieser Einstellung liefert 1250
Bilder, weil der bevorzugte Transport zuerst steht.

Kurz: Dieser Eingriff macht den Weg robuster gegen ein **blockiertes**
Protokoll, nicht gegen ein **verstümmeltes**. Das ist weniger, als der Titel
verspricht, und es ist gemessen.
"""

import pathlib
import sys

DATEI = "selkies_gstreamer/signalling_web.py"

ALT = '''    rtc_config["iceServers"].append({
        "urls": [
            "{}:{}:{}?transport={}".format('turns' if turn_tls else 'turn', turn_host, turn_port, protocol)
        ],
        "username": username,
        "credential": password
    })'''

NEU = '''    # OTA: derselbe Server über beide Wege. Siehe patches/beide-turn-wege.py.
    #
    # Zuerst der eingestellte Transport, dann der andere — ICE probiert beide
    # und nimmt den, der trägt. Damit braucht niemand mehr eine Anlage auf TCP
    # festzunageln, nur weil ein Anwender hinter einem engen Tunnel sitzt.
    _schema = 'turns' if turn_tls else 'turn'
    _erst = (protocol or "udp").lower()
    _dann = "tcp" if _erst == "udp" else "udp"
    rtc_config["iceServers"].append({
        "urls": [
            "{}:{}:{}?transport={}".format(_schema, turn_host, turn_port, _erst),
            "{}:{}:{}?transport={}".format(_schema, turn_host, turn_port, _dann),
        ],
        "username": username,
        "credential": password
    })'''


def main() -> int:
    wurzel = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    datei = wurzel / DATEI
    text = datei.read_text(encoding="utf-8")

    if "beide-turn-wege" in text:
        print("beide TURN-Wege stehen schon drin")
        return 0
    if ALT not in text:
        # Laut scheitern statt still nichts zu tun: Sonst bekaeme der Browser
        # wieder nur einen Weg, und es faellt erst dem Anwender auf, der
        # hinter einem Tunnel sitzt.
        print(f"Die erwartete Stelle steht nicht in {DATEI} — Selkies-Fassung "
              "geaendert? Der TURN-Eintrag muss neu geprueft werden.",
              file=sys.stderr)
        return 1

    datei.write_text(text.replace(ALT, NEU, 1), encoding="utf-8")
    print("TURN wird über UDP und TCP angeboten")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
