"""ota-fw — der Router aller Arbeitsplätze.

Vier Aufgaben, mehr nicht: **routen**, **NAT**, **DNS**, **Portfreigaben**. Er
hat in jedem Sitzungsnetz eine Schnittstelle und einen Uplink nach draussen;
die Sitzungsnetze sind `internal`, es gibt also keinen Weg an ihm vorbei.

**Er bekommt seinen Zustand als Gesamtbild**, nicht als Einzelbefehle: „So
sieht die Welt aus." Ein verlorener Aufruf heilt sich damit beim naechsten Mal
von selbst. Bei Einzelbefehlen bliebe sonst etwas offen, ohne dass etwas
kaputtgeht — und niemand merkte es.

Erreichbar ueber einen Unix-Socket im gemeinsamen Ablageverzeichnis: kein
Port, keine Adresse, es entscheiden die Dateirechte.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel

from . import netns, nft, resolver

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("otafw")

TOKEN = os.environ.get("OTA_AGENT_TOKEN", "")
POOL = os.environ.get("OTA_SESSION_POOL", "10.99.0.0/16")
ZUSTAND_DATEI = Path(os.environ.get("OTA_FW_STATE", "/var/lib/ota-firewall/zustand.json"))
ABGLEICH = int(os.environ.get("OTA_FW_RESYNC", "30"))

app = FastAPI(title="OTA Firewall", version="2")

_zustand: dict[str, Any] = {"pool": POOL, "sitzungen": []}
_sperre = threading.Lock()

# Der zuletzt gesetzte Satz — als Fingerabdruck.
#
# **Warum das mehr ist als Sparsamkeit:** `nft -f` setzt beim Setzen alle
# Zaehler zurueck. Wer den Satz alle dreissig Sekunden neu schreibt, weil die
# Abgleichschleife laeuft, hat nie eine Zahl groesser als eine halbe Minute —
# und damit kein Messen (Etappe 8). Deshalb wird nur gesetzt, was sich
# geaendert hat.
_letzter_satz = ""

# Und was trotzdem verlorenginge, wird vorher gerettet: Summen ueber alle
# bisherigen Saetze, je Sitzungsnetz.
_summen: dict[str, dict[str, int]] = {}


def require_token(x_agent_token: str = Header(default="")) -> None:
    if not TOKEN or not secrets.compare_digest(x_agent_token, TOKEN):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Agent-Token ungültig")


class Freigabe(BaseModel):
    ziel: str
    ports: str = "*"
    protokoll: str = "beide"


class Sitzung(BaseModel):
    subnetz: str
    # Wohin die Standardroute des Arbeitsplatzes zeigen soll — die Adresse
    # dieses Routers in genau diesem Netz.
    gateway: str = ""
    # Dockers Pfad zum Netzwerk-Namensraum des Arbeitsplatzes.
    sandbox: str = ""
    stufe: str = "internet"
    freigaben: list[Freigabe] = []
    namen: list[str] = []


class Weiterleitung(BaseModel):
    """Eine Portfreigabe ueber den Wirt — die „+ NAT"-Funktion."""

    aussen: int
    innen: int
    ziel: str
    protokoll: str = "tcp"


class Regelwerk(BaseModel):
    sitzungen: list[Sitzung] = []
    # Was fuer alle gilt, an einer Stelle gepflegt.
    global_: list[Freigabe] = []
    grundfreigaben: list[tuple[str, str, str]] = []
    weiterleitungen: list[Weiterleitung] = []


def _speichern() -> None:
    try:
        ZUSTAND_DATEI.parent.mkdir(parents=True, exist_ok=True)
        ZUSTAND_DATEI.write_text(json.dumps(_zustand), encoding="utf-8")
    except OSError as exc:
        log.warning("Zustand nicht speicherbar: %s", exc)


def _laden() -> None:
    global _zustand
    try:
        _zustand = json.loads(ZUSTAND_DATEI.read_text(encoding="utf-8"))
        _zustand.setdefault("pool", POOL)
        log.info("Zustand von der Platte: %d Sitzungen", len(_zustand.get("sitzungen", [])))
    except (OSError, ValueError):
        log.info("Kein gespeicherter Zustand — es gilt die Grundsperre")


def _summen_retten() -> None:
    """Zaehlerstaende sichern, bevor ein neuer Satz sie zuruecksetzt."""
    for netz, werte in nft.zaehler().items():
        eintrag = _summen.setdefault(netz, {"bytes": 0, "pakete": 0,
                                            "verworfen": 0, "verworfen_bytes": 0})
        for schluessel, wert in werte.items():
            eintrag[schluessel] = eintrag.get(schluessel, 0) + wert


def _durchsetzen() -> dict:
    """Regelwerk, Resolver und Routen in Einklang mit `_zustand` bringen."""
    global _letzter_satz
    with _sperre:
        _zustand["uplink"] = nft.uplink_finden()
        satz = nft.regelwerk(_zustand)
        if satz == _letzter_satz and nft.tabelle_da():
            ergebnis = {"regelwerk": "unveraendert"}
        else:
            _summen_retten()
            ergebnis = nft.anwenden(_zustand)
            _letzter_satz = satz
        ergebnis.update(resolver.anwenden(_zustand))

        # Die Routen zuletzt: Erst wenn das Regelwerk steht, soll ein
        # Arbeitsplatz ueberhaupt einen Weg haben.
        gesetzt, fehlend = 0, []
        for s in _zustand.get("sitzungen", []):
            if not s.get("sandbox") or not s.get("gateway"):
                continue
            try:
                if not netns.stimmt(s["sandbox"], s["gateway"]):
                    netns.route_setzen(s["sandbox"], s["gateway"])
                gesetzt += 1
            except netns.RouteFehler as exc:
                # Laut, nicht still: Ein Arbeitsplatz ohne Route hat kein Netz,
                # und das soll man sehen, statt es zu suchen.
                log.error("KEINE ROUTE fuer %s: %s", s["subnetz"], exc)
                fehlend.append(s["subnetz"])
        ergebnis["routen"] = gesetzt
        if fehlend:
            ergebnis["ohne_route"] = fehlend
        return ergebnis


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.put("/regelwerk", dependencies=[Depends(require_token)])
def regelwerk(body: Regelwerk) -> dict:
    global _zustand
    daten = body.model_dump()
    daten["global"] = daten.pop("global_", [])
    _zustand = {"pool": POOL, **daten}
    _speichern()
    ergebnis = _durchsetzen()
    log.info("Regelwerk gesetzt: %d Sitzungen, %d Weiterleitungen, %s",
             len(body.sitzungen), len(body.weiterleitungen), ergebnis)
    return {"status": "ok", **ergebnis}


@app.get("/zustand", dependencies=[Depends(require_token)])
def zustand() -> dict:
    return {
        "pool": POOL,
        "uplink": _zustand.get("uplink", ""),
        "sitzungen": len(_zustand.get("sitzungen", [])),
        "weiterleitungen": len(_zustand.get("weiterleitungen", [])),
        "resolver_laeuft": resolver.laeuft(),
        "namensraeume": netns.erreichbar(),
        "routen": {s["subnetz"]: netns.route_lesen(s.get("sandbox", ""))
                   for s in _zustand.get("sitzungen", [])},
    }


@app.get("/zaehler", dependencies=[Depends(require_token)])
def zaehler() -> dict:
    """Durchsatz und verworfene Pakete je Sitzung.

    Je Sitzung eine eigene Kette — deshalb ist das hier kostenlos zu haben.
    Die Zahlen stehen je **Netz**, nicht je Person; wer dahintersteht, loest
    erst die Oberflaeche auf.

    Zurueck kommen die Staende **seit dem Start des Dienstes**: die laufenden
    Zaehler plus das, was vor dem letzten Setzen des Regelwerks gerettet wurde.
    """
    jetzt = nft.zaehler()
    raus: dict[str, dict[str, int]] = {}
    for netz in set(jetzt) | set(_summen):
        a, b = jetzt.get(netz, {}), _summen.get(netz, {})
        raus[netz] = {k: a.get(k, 0) + b.get(k, 0)
                      for k in ("bytes", "pakete", "verworfen", "verworfen_bytes")}
    return {"sitzungen": raus}


def _abgleichschleife() -> None:
    while True:
        time.sleep(ABGLEICH)
        try:
            _durchsetzen()
        except Exception as exc:  # noqa: BLE001 — die Schleife darf nie sterben
            log.error("Abgleich fehlgeschlagen: %s", exc)


@app.on_event("startup")
def start() -> None:
    _laden()
    if not netns.erreichbar():
        log.error("%s fehlt — ohne die Namensraeume kann kein Arbeitsplatz "
                  "eine Route bekommen.", netns.WURZEL)
    try:
        log.info("Regelwerk beim Start: %s", _durchsetzen())
    except Exception as exc:  # noqa: BLE001
        log.error("Regelwerk beim Start nicht setzbar: %s", exc)
    threading.Thread(target=_abgleichschleife, daemon=True).start()
