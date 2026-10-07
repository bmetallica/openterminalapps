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

import httpx
from fastapi import HTTPException, status
from sqlalchemy.orm import Session as DbSession

from . import settings_store
from .config import settings

REPO_URL = os.environ.get("OTA_REPO_URL", "http://repo:8200").rstrip("/")
CA_DATEI = Path("/app/certs/ota-ca.crt")
MODI = ("aus", "zuerst", "nur")

_zwischen: dict[str, Any] = {"zeit": 0.0, "daten": None}


def aktiv() -> bool:
    """Ist das Modul eingeschaltet (OTA_REPO=1 in deploy/.env)?"""
    return os.environ.get("OTA_REPO", "0").strip() == "1"


def aufruf(methode: str, pfad: str, **kw: Any) -> Any:
    if not aktiv():
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "Paketquellen sind nicht eingeschaltet (OTA_REPO=1, Kapitel 26).")
    zeit = kw.pop("timeout", 60.0)
    try:
        with httpx.Client(timeout=zeit) as client:
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
    if not aktiv():
        return {}
    modus = settings_store.get(db, settings_store.REPO_MODUS) or "zuerst"
    if modus == "aus":
        return {"modus": "aus"}
    if time.monotonic() - _zwischen["zeit"] > 60 or _zwischen["daten"] is None:
        try:
            _zwischen["daten"] = aufruf("GET", "/quellen", timeout=10.0)
            _zwischen["zeit"] = time.monotonic()
        except HTTPException:
            return {}
    try:
        ca = CA_DATEI.read_text(encoding="utf-8")
    except OSError:
        ca = ""
    daten = _zwischen["daten"] or {}
    return {"modus": modus, "quellen": daten.get("quellen", []),
            "schluessel": daten.get("schluessel", ""), "ca": ca}


def zwischenspeicher_leeren() -> None:
    _zwischen.update({"zeit": 0.0, "daten": None})
