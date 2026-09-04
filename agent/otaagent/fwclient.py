"""Der Draht zum Firewall-Dienst — ueber einen Unix-Socket.

Kein Port und keine Adresse: Der Firewall-Dienst laeuft im Namensraum des
Wirts, und ein offener Port waere dort auf **jeder** Adresse des Wirts
erreichbar, auch der im Firmennetz. Ein Socket im gemeinsamen
Ablageverzeichnis hat diese Eigenschaft nicht — es entscheiden die
Dateirechte.

Ohne zusaetzliche Abhaengigkeit: `http.client` kann jede Verbindung benutzen,
die man ihm hinlegt.
"""

from __future__ import annotations

import http.client
import json
import logging
import os
import socket

log = logging.getLogger("ota.agent.firewall")

SOCKET = os.environ.get("OTA_FW_SOCKET", "/srv/ota/runtime/firewall.sock")
TOKEN = os.environ.get("OTA_AGENT_TOKEN", "")


class _UnixVerbindung(http.client.HTTPConnection):
    def __init__(self, pfad: str, timeout: float = 20.0) -> None:
        super().__init__("localhost", timeout=timeout)
        self._pfad = pfad

    def connect(self) -> None:  # noqa: D102
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(self.timeout)
        s.connect(self._pfad)
        self.sock = s


def erreichbar() -> bool:
    return os.path.exists(SOCKET)


def _ruf(methode: str, pfad: str, koerper: dict | None = None) -> dict:
    verbindung = _UnixVerbindung(SOCKET)
    try:
        daten = json.dumps(koerper).encode() if koerper is not None else None
        verbindung.request(methode, pfad, body=daten, headers={
            "Content-Type": "application/json",
            "X-Agent-Token": TOKEN,
        })
        antwort = verbindung.getresponse()
        roh = antwort.read()
        if antwort.status >= 400:
            raise RuntimeError(f"Firewall meldet {antwort.status}: {roh[:200]!r}")
        return json.loads(roh) if roh else {}
    finally:
        verbindung.close()


def regelwerk_setzen(zustand: dict) -> dict:
    """Den **Gesamtzustand** schicken, nicht eine einzelne Aenderung.

    Warum: siehe `firewall/otafw/main.py`. Ein verlorener Aufruf faellt bei
    Einzelbefehlen niemandem auf — es geht nichts kaputt, es bleibt nur etwas
    offen. Beim Vollabgleich heilt sich das beim naechsten Mal von selbst.
    """
    return _ruf("PUT", "/regelwerk", zustand)


def zustand() -> dict:
    return _ruf("GET", "/zustand")
