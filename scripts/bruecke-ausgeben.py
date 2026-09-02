#!/usr/bin/env python3
"""Gibt das Brueckenskript aus, das der Agent in den Container legt.

Damit prueft `build-base-image.sh` genau das Skript, das im Betrieb laeuft,
und nicht eine Nachbildung davon — die waere nach der ersten Aenderung an
`clipboard.py` still veraltet und wuerde trotzdem gruen melden.

    scripts/bruecke-ausgeben.py bridge [intervall]
    scripts/bruecke-ausgeben.py stop
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "agent"))

from otaagent import clipboard  # noqa: E402

was = sys.argv[1] if len(sys.argv) > 1 else "bridge"
if was == "stop":
    sys.stdout.write(clipboard.STOP)
else:
    intervall = sys.argv[2] if len(sys.argv) > 2 else "0.5"
    sys.stdout.write(clipboard.BRIDGE.replace("@INTERVAL@", intervall))
