"""ota-firewall — schreibt Regeln, transportiert keine Pakete.

Der Dienst laeuft im Netzwerk-Namensraum des Wirts und hat `NET_ADMIN`. Mehr
braucht er nicht: Er legt zwei eigene iptables-Ketten an, fuellt sie aus dem
gewuenschten Zustand, den der Agent schickt, und haelt sie dort.

**Warum ein eigener Dienst und nicht der Agent.** `NET_ADMIN` im
Wirtsnamensraum ist eine Rechteklasse fuer sich, und der Agent ist schon heute
der Dienst mit der groessten Angriffsflaeche (`security.md`, H3). Zwei kleine
Dienste mit je einer Aufgabe sind leichter zu verstehen als einer mit beiden.

**Warum er kein Router ist.** Steht in `firewall.md`, Korrektur 1: Docker
richtet fuer jedes Bridge-Netz eigenes NAT ein, der Weg nach draussen ginge an
einem Router-Container vorbei. Ihn zum Gateway zu machen braeuchte `NET_ADMIN`
**im Sitzungscontainer** — genau die Faehigkeit, die dort weggenommen wird.
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

from . import anwenden as netfilter
from . import resolver

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("otafw")

TOKEN = os.environ.get("OTA_AGENT_TOKEN", "")
POOL = os.environ.get("OTA_SESSION_POOL", "10.99.0.0/16")
ZUSTAND_DATEI = Path(os.environ.get("OTA_FW_STATE", "/var/lib/ota-firewall/zustand.json"))
ABGLEICH_SEKUNDEN = int(os.environ.get("OTA_FW_RESYNC", "30"))

app = FastAPI(title="OTA Firewall", version="1")

# Der zuletzt gewuenschte Zustand. Er liegt auch auf Platte, damit ein Neustart
# des Dienstes selbst nichts vergisst — sonst stuenden nach einem Update
# Sitzungen ohne Regeln da, und die Grundsperre haette sie stumm abgeschnitten.
_zustand: dict[str, Any] = {"pool": POOL, "sitzungen": []}
_sperre = threading.Lock()


def require_token(x_agent_token: str = Header(default="")) -> None:
    if not TOKEN or not secrets.compare_digest(x_agent_token, TOKEN):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Agent-Token ungültig")


class Freigabe(BaseModel):
    ziel: str
    ports: str = "*"
    protokoll: str = "beide"


class Sitzung(BaseModel):
    subnetz: str
    stufe: str = "internet"
    freigaben: list[Freigabe] = []
    namen: list[str] = []


class Regelwerk(BaseModel):
    """Der gewuenschte Gesamtzustand — nicht eine einzelne Aenderung."""

    sitzungen: list[Sitzung] = []
    # Traefik haengt in jedem Sitzungsnetz und hat dort je eine Adresse.
    traefik_ips: list[str] = []
    turn: dict = {}
    # Was jede Sitzung erreichen darf, damit OTA selbst funktioniert:
    # (ziel, ports, protokoll)
    grundfreigaben: list[tuple[str, str, str]] = []
    # Auf welchem Port der eigene Resolver antwortet. Ohne dieses Feld
    # verwarf Pydantic die Angabe stillschweigend, und die Sitzungen hatten
    # keine Namensaufloesung — ohne dass irgendwo etwas dazu stand.
    dns_port: int = 53


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
        log.info("Zustand von der Platte gelesen: %d Sitzungen",
                 len(_zustand.get("sitzungen", [])))
    except (OSError, ValueError):
        log.info("Kein gespeicherter Zustand — es gilt die Grundsperre")


def _durchsetzen() -> dict:
    """Regelwerk und Resolver in Einklang mit `_zustand` bringen."""
    with _sperre:
        # Namen ohne `ipset` gehen als aufgeloeste Adressen in die Freigaben.
        # Schlechter, aber sichtbar: `zustand` meldet es.
        arbeit = json.loads(json.dumps(_zustand))
        if resolver.ipset_verfuegbar():
            for s in arbeit.get("sitzungen", []):
                if s.get("namen"):
                    s["mengenname"] = resolver.mengenname(s["subnetz"])
        else:
            for s in arbeit.get("sitzungen", []):
                for adresse in resolver.aufloesen(s.get("namen", [])):
                    s.setdefault("freigaben", []).append(
                        {"ziel": adresse, "ports": "*", "protokoll": "beide"})

        res = resolver.anwenden(arbeit)
        fw = netfilter.anwenden(arbeit)
        return {**fw, **res}


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.put("/regelwerk", dependencies=[Depends(require_token)])
def regelwerk(body: Regelwerk) -> dict:
    global _zustand
    _zustand = {"pool": POOL, **body.model_dump()}
    _speichern()
    ergebnis = _durchsetzen()
    log.info("Regelwerk gesetzt: %d Sitzungen, %d Regeln",
             len(body.sitzungen), ergebnis.get("regeln", 0))
    return {"status": "ok", **ergebnis}


@app.get("/zustand", dependencies=[Depends(require_token)])
def zustand() -> dict:
    return {
        "pool": POOL,
        "sitzungen": len(_zustand.get("sitzungen", [])),
        "eingehaengt": netfilter.eingehaengt(),
        "ketten": netfilter.zustand_lesen(),
        "resolver_laeuft": resolver.laeuft(),
        "ipset": resolver.ipset_verfuegbar(),
    }


def _abgleichschleife() -> None:
    """Nachziehen, was Docker weggeraeumt hat.

    Beim Neustart des Docker-Dienstes baut Docker seine Ketten neu auf. Die
    eigenen Ketten bleiben stehen, **der Verweis darauf verschwindet** — und
    dann steht ein vollstaendiges Regelwerk da, das nie aufgerufen wird. Genau
    das prueft diese Schleife, und genau das vergisst man beim Bauen.
    """
    while True:
        time.sleep(ABGLEICH_SEKUNDEN)
        try:
            haengt = netfilter.eingehaengt()
            if not all(haengt.values()):
                log.warning("Ketten waren ausgehaengt (%s) — wird nachgezogen", haengt)
                _durchsetzen()
        except Exception as exc:  # noqa: BLE001 — die Schleife darf nie sterben
            log.error("Abgleich fehlgeschlagen: %s", exc)


@app.on_event("startup")
def start() -> None:
    _laden()
    try:
        ergebnis = _durchsetzen()
        log.info("Grundsperre steht (%s)", ergebnis)
    except Exception as exc:  # noqa: BLE001
        log.error("Regelwerk beim Start nicht setzbar: %s", exc)
    threading.Thread(target=_abgleichschleife, daemon=True).start()
