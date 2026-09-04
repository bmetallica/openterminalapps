"""Die Standardroute in den Namensraum eines Arbeitsplatzes setzen.

**Warum das sein muss.** Docker laesst einen Container nicht Gateway sein. In
einem `internal`-Netz legt es ueberhaupt keine Standardroute an (gemessen) —
der Arbeitsplatz kommt also nirgendwohin, bis ihm jemand den Weg zeigt. Setzen
darf er sie nicht selbst: Mit `cap_drop: ALL` antwortet der Kernel
`RTNETLINK answers: Operation not permitted`, und das ist richtig so. Wer
Routen setzen darf, darf sie auch wieder wegnehmen.

**Also von aussen.** Dieser Dienst betritt den Namensraum
(`nsenter --net=<SandboxKey>`) und setzt die Route dort. Der Arbeitsplatz
braucht dafuer keine einzige Faehigkeit und merkt nichts davon.

**Der Preis** steht in `firewall.md`: Dieser Container braucht `SYS_ADMIN` und
den Pfad `/var/run/docker/netns`. Das ist eine Rechteklasse fuer sich — sie
sitzt dafuer an genau einer Stelle und ist dort sichtbar.

**Und die Bedingung:** Scheitert das, hat der Arbeitsplatz kein Netz. Dann
soll es **laut** scheitern und nicht still — ein Arbeitsplatz ohne Route ist
besser als einer, von dem niemand weiss, dass er keine hat.
"""

from __future__ import annotations

import logging
import os
import subprocess

log = logging.getLogger("otafw.netns")

# Docker legt die Namensraeume hier ab. Der `SandboxKey` eines Containers zeigt
# genau hierhin; der Agent reicht ihn durch.
WURZEL = "/var/run/docker/netns"


class RouteFehler(RuntimeError):
    pass


def _nsenter(pfad: str, *befehl: str) -> subprocess.CompletedProcess:
    return subprocess.run(["nsenter", f"--net={pfad}", *befehl],
                          capture_output=True, text=True, timeout=20)


def erreichbar() -> bool:
    return os.path.isdir(WURZEL)


def route_setzen(sandbox: str, gateway: str) -> None:
    """Standardroute im fremden Namensraum auf den Router zeigen lassen."""
    if not sandbox:
        raise RouteFehler("Kein Namensraum angegeben")
    if not os.path.exists(sandbox):
        raise RouteFehler(
            f"Namensraum {sandbox} gibt es nicht. Aendert Docker seine Ablage, "
            f"steht sie woanders — dann findet dieser Dienst sie nicht mehr, "
            f"und der Arbeitsplatz hat kein Netz.")
    fertig = _nsenter(sandbox, "ip", "route", "replace", "default", "via", gateway)
    if fertig.returncode != 0:
        raise RouteFehler(f"Route nicht setzbar: {fertig.stderr.strip()}")
    log.info("Standardroute in %s auf %s gesetzt", os.path.basename(sandbox), gateway)


def route_lesen(sandbox: str) -> str:
    """Was gerade drinsteht — fuer den Abgleich und die Fehlersuche."""
    if not sandbox or not os.path.exists(sandbox):
        return ""
    fertig = _nsenter(sandbox, "ip", "route", "show", "default")
    return fertig.stdout.strip() if fertig.returncode == 0 else ""


def stimmt(sandbox: str, gateway: str) -> bool:
    return f"via {gateway}" in route_lesen(sandbox)
