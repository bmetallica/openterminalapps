"""Paketquellen (Handbuch Kapitel 26) — was die API dem Agent mitgibt.

Die API kennt die Einstellung (Modus, Bau-Snapshot), der Steuerdienst `repo`
kennt die veroeffentlichten Staende und den Schluessel, und die CA liegt bei
den Zertifikaten. Zusammengesetzt wird das hier, einmal je Start eines
Arbeitsplatzes oder Baus.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import logging

import httpx
from fastapi import HTTPException, status
from sqlalchemy.orm import Session as DbSession

from . import settings_store
from .config import settings

log = logging.getLogger("ota.paketquellen")

REPO_URL = os.environ.get("OTA_REPO_URL", "http://repo:8200").rstrip("/")
CA_DATEI = Path("/app/certs/ota-ca.crt")
MODI = ("aus", "zuerst", "nur")

_zwischen: dict[str, Any] = {"zeit": 0.0, "daten": None}


def spiegel_aktiv() -> bool:
    """Ist der Spiegel von Debian und Docker eingeschaltet?

    Das eigene Repository laeuft immer — ueber es kommt ota-selkies in die
    Arbeitsplaetze. Der Spiegel ist ein Zusatz (`OTA_REPO_SPIEGEL=1`).
    `OTA_REPO=1` war bis zum 2026-10-08 der Schalter fuer beides und wird
    in deploy/docker-compose.yml weiter als Spiegel gelesen.
    """
    return os.environ.get("OTA_REPO_SPIEGEL", "0").strip() == "1"


def aufruf(methode: str, pfad: str, **kw: Any) -> Any:
    zeit = kw.pop("timeout", 60.0)
    try:
        # `trust_env=False`: Der Repo-Dienst ist ein Dienst des Stacks. Mit
        # einem Firmenproxy in der Umgebung ging der Aufruf sonst an den
        # Proxy — `repo` steht in keiner gewachsenen NO_PROXY-Liste.
        with httpx.Client(timeout=zeit, trust_env=False) as client:
            antwort = client.request(methode, f"{REPO_URL}{pfad}",
                                     headers={"X-Agent-Token": settings().agent_token}, **kw)
    except httpx.HTTPError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            f"Der Dienst der Paketquellen antwortet nicht: {exc}") from exc
    if antwort.status_code >= 400:
        try:
            meldung = antwort.json().get("detail", antwort.text)
        except ValueError:
            meldung = antwort.text
        raise HTTPException(antwort.status_code, meldung)
    try:
        return antwort.json()
    except ValueError:
        return antwort.text


def fuer_container(db: DbSession) -> dict[str, Any]:
    """Was der Agent in einen Container eintraegt — leer, wenn nichts.

    Eine Minute zwischengespeichert: Die API fragt das bei jedem Start, und
    die veroeffentlichten Staende aendern sich nur mit einem Abgleich. Ist der
    Dienst nicht erreichbar, startet der Arbeitsplatz trotzdem — mit den
    Quellen seines Images.
    """
    # **Die eigene Quelle wird immer eingetragen** — ueber sie kommt
    # ota-selkies, und ueber sie heben sich Root-Arbeitsplaetze an. Die
    # Betriebsart betrifft nur den Spiegel (Betreiber, 2026-10-08): "aus"
    # heisst "den Spiegel nicht benutzen", nicht "nichts eintragen". Bis dahin
    # trug "aus" auch die eigene Quelle aus, und ein Root-Arbeitsplatz hob
    # sich nie an.
    modus = settings_store.get(db, settings_store.REPO_MODUS) or "zuerst"
    # "Nur eigene" ohne Spiegel hiesse: gar keine Debian-Pakete mehr. Die
    # Oberflaeche bietet es dann nicht an; steht es von frueher noch so da,
    # gilt "zuerst".
    if modus == "nur" and not spiegel_aktiv():
        modus = "zuerst"
    if time.monotonic() - _zwischen["zeit"] > 60 or _zwischen["daten"] is None:
        try:
            _zwischen["daten"] = aufruf("GET", "/quellen", timeout=10.0)
            _zwischen["zeit"] = time.monotonic()
        except HTTPException as exc:
            # Laut, nicht still: Ein leeres Ergebnis heisst fuer den Agent
            # "nichts eintragen, nichts anheben" — und im Arbeitsplatz sah man
            # nur, dass die Quelle fehlte (gemeldet 2026-10-08).
            log.warning("Paketquelle nicht erreichbar, Container bekommen nichts "
                        "eingetragen: %s", exc.detail)
            return {}
    try:
        ca = CA_DATEI.read_text(encoding="utf-8")
    except OSError:
        ca = ""
    daten = _zwischen["daten"] or {}
    quellen = daten.get("quellen", [])
    if modus == "aus" or not spiegel_aktiv():
        # Nur die eigene Quelle: keine Debian-Pakete von hier, nichts
        # abschalten. Der Agent kennt dafuer die Betriebsart "eigen".
        quellen = [q for q in quellen if q["prefix"].split("/")[-1] == "ota"]
        modus = "eigen"
    return {"modus": modus, "quellen": quellen,
            "schluessel": daten.get("schluessel", ""), "ca": ca,
            # Die Fassung, auf die der Agent einen Root-Arbeitsplatz hebt.
            "selkies": daten.get("selkies", "")}


def zwischenspeicher_leeren() -> None:
    _zwischen.update({"zeit": 0.0, "daten": None})
