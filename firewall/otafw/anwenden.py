"""Regeln in den Netfilter des Wirts schreiben — und dort halten.

Der Dienst besitzt zwei eigene Ketten und baut sie bei jedem Abgleich neu auf.
Fremde Regeln fasst er nicht an; er haengt sich nur ganz vorn in `DOCKER-USER`
und `INPUT` ein.

**`-w` bei jedem Aufruf.** Docker schreibt selbst iptables-Regeln, und zwei
Schreiber ohne Sperre erzeugen `Another app is currently holding the xtables
lock`. Mit `-w` wartet unser Aufruf, statt zu scheitern.
"""

from __future__ import annotations

import logging
import subprocess

from .regeln import KETTE_FWD, KETTE_IN, forward_regeln, input_regeln

log = logging.getLogger("otafw")

IPT = ["iptables", "-w", "5"]


class FirewallFehler(RuntimeError):
    pass


def _lauf(args: list[str], *, dulden: bool = False) -> str:
    fertig = subprocess.run(IPT + args, capture_output=True, text=True, timeout=30)
    if fertig.returncode != 0 and not dulden:
        raise FirewallFehler(f"iptables {' '.join(args)}: {fertig.stderr.strip()}")
    return fertig.stdout


def _kette_anlegen(name: str) -> None:
    _lauf(["-N", name], dulden=True)   # existiert schon? dann gut.


def _einhaengen(elternkette: str, name: str) -> None:
    """Ganz vorn einhaengen — und nur, wenn es noch nicht drinsteht.

    Ganz vorn, weil auf diesem Wirt fremde Regeln vor `DOCKER-USER` stehen und
    Verkehr durchlassen (siehe firewall.md). Wer hinten anhaengt, wird nie
    gefragt.
    """
    vorhanden = subprocess.run(IPT + ["-C", elternkette, "-j", name],
                               capture_output=True, text=True)
    if vorhanden.returncode != 0:
        _lauf(["-I", elternkette, "1", "-j", name])


def anwenden(zustand: dict) -> dict:
    """Den gewuenschten Zustand herstellen. Idempotent."""
    _kette_anlegen(KETTE_FWD)
    _kette_anlegen(KETTE_IN)
    _einhaengen("DOCKER-USER", KETTE_FWD)
    _einhaengen("INPUT", KETTE_IN)

    gesetzt = 0
    for kette, regeln in ((KETTE_FWD, forward_regeln(zustand)),
                          (KETTE_IN, input_regeln(zustand))):
        # Leeren und neu fuellen. Zwischen beiden Schritten liegt ein Moment
        # ohne Regeln — aber die Kette ist dann leer, und eine leere Kette
        # faellt auf die Politik der Elternkette zurueck. Bei `FORWARD` ist
        # das auf diesem Wirt `DROP`; bei `INPUT` nicht, deshalb wird die
        # Grundsperre der INPUT-Kette **zuerst** gesetzt.
        _lauf(["-F", kette])
        if kette == KETTE_IN:
            _lauf(["-A", kette, "-s", zustand["pool"], "-j", "DROP"])
        for regel in regeln:
            _lauf(["-A", kette] + regel)
            gesetzt += 1
        if kette == KETTE_IN:
            # Die vorgezogene Grundsperre wieder heraus — sie steht jetzt als
            # letzte Regel ordentlich in der Reihe.
            _lauf(["-D", kette, "-s", zustand["pool"], "-j", "DROP"], dulden=True)

    return {"regeln": gesetzt}


def zustand_lesen() -> dict:
    """Was gerade wirklich in den Ketten steht — fuer die Abgleichschleife."""
    raus = {}
    for kette in (KETTE_FWD, KETTE_IN):
        try:
            raus[kette] = [z for z in _lauf(["-S", kette]).splitlines()
                           if not z.startswith("-N ")]
        except FirewallFehler:
            raus[kette] = []
    return raus


def eingehaengt() -> dict[str, bool]:
    """Haengen unsere Ketten noch in den Elternketten?

    Genau das geht bei einem Neustart von Docker verloren: Die Ketten selbst
    bleiben stehen, der Verweis darauf verschwindet — und dann steht ein
    vollstaendiges Regelwerk da, das nie aufgerufen wird.
    """
    raus = {}
    for eltern, kette in (("DOCKER-USER", KETTE_FWD), ("INPUT", KETTE_IN)):
        fertig = subprocess.run(IPT + ["-C", eltern, "-j", kette],
                                capture_output=True, text=True)
        raus[kette] = fertig.returncode == 0
    return raus
