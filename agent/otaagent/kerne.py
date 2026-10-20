"""Speicherabbilder abgestürzter Programme aus den Zuhausen räumen.

**Warum es sie überhaupt gibt.** `dockerd` läuft mit `LimitCORE=infinity`,
jeder Container erbt das, und der Wirt schreibt mit `core_pattern = core` das
Abbild ins aktuelle Verzeichnis — fast immer das Zuhause. Gemessen am
2026-10-20: 24 Abbilder von Firefox-Unterprozessen in einem Zuhause, die beim
Anhalten jeder Sitzung sterben; auf einer Anlage ein einzelnes von 4,3 GB.
Niemand hat sie angelegt, niemand sieht sie, und sie zählen auf die
Platzgrenze — bis der Nutzer seinen Arbeitsplatz nicht mehr starten darf.

Neue Container bekommen deshalb `ulimit core=0` (siehe `create_container`).
Das hier räumt, was vorher entstand und was ein Root-Arbeitsplatz sich selbst
wieder einschaltet.

**Gelöscht wird nur, was nachweislich ein Abbild ist:** Name `core` oder
`core.<Zahl>`, eine gewöhnliche Datei (kein Verweis) und im Kopf eine
ELF-Datei vom Typ `ET_CORE`. Eine Datei des Nutzers, die zufällig `core`
heisst, bleibt liegen.
"""
from __future__ import annotations

import logging
import os
import re
import stat
import time

log = logging.getLogger("otaagent.kerne")

NAME = re.compile(r"core(\.\d+)?")
# Ein Abbild, das gerade geschrieben wird, nicht unter den Füßen wegziehen.
MINDESTALTER = 300.0
ET_CORE = 4


def ist_abbild(pfad: str) -> bool:
    """Ein ELF-Speicherabbild? Gelesen wird nur der Kopf, ohne Verweisen zu folgen."""
    try:
        fd = os.open(pfad, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        return False
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return False
        kopf = os.read(fd, 18)
    except OSError:
        return False
    finally:
        os.close(fd)
    if len(kopf) < 18 or kopf[:4] != b"\x7fELF":
        return False
    reihenfolge = "little" if kopf[5] == 1 else "big"
    return int.from_bytes(kopf[16:18], reihenfolge) == ET_CORE


def raeumen(wurzel: str, jetzt: float | None = None) -> dict[str, int]:
    """Alle Abbilder unter `wurzel` löschen. Gibt Anzahl und Bytes zurück."""
    jetzt = time.time() if jetzt is None else jetzt
    anzahl = belegt = 0
    if not os.path.isdir(wurzel):
        return {"dateien": 0, "bytes": 0}
    for ordner, _, dateien in os.walk(wurzel, followlinks=False):
        for name in dateien:
            if not NAME.fullmatch(name):
                continue
            pfad = os.path.join(ordner, name)
            try:
                st = os.lstat(pfad)
            except OSError:
                continue
            if not stat.S_ISREG(st.st_mode) or jetzt - st.st_mtime < MINDESTALTER:
                continue
            if not ist_abbild(pfad):
                continue
            try:
                os.unlink(pfad)
            except OSError as exc:
                log.warning("Abbild %s nicht löschbar: %s", pfad, exc)
                continue
            anzahl += 1
            belegt += st.st_blocks * 512
    if anzahl:
        log.info("%d Speicherabbilder (%.1f MB) unter %s entfernt",
                 anzahl, belegt / 1024 ** 2, wurzel)
    return {"dateien": anzahl, "bytes": belegt}
