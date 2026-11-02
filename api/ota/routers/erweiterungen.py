"""Einstellungen → Erweiterungen, und die Ansichten der Erweiterungen in OTA
(erweiterungen.py, Handbuch Kapitel 39)."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session as DbSession

from .. import audit, erweiterungen
from ..db import SessionLocal, get_db
from ..deps import current_user, require_permission
from ..models import Erweiterung, User

router = APIRouter(tags=["erweiterungen"])
verwalten = require_permission("settings.manage")


def _laden(db: DbSession, slug: str) -> Erweiterung:
    e = db.get(Erweiterung, slug)
    if e is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Diese Erweiterung ist nicht gekoppelt.")
    return e


def _fehler(exc: erweiterungen.ErweiterungFehler) -> HTTPException:
    return HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))


def _nutzer_abgleichen() -> None:
    with SessionLocal() as db:
        erweiterungen.alle_nutzer_abgleichen(db)


@router.get("/api/admin/erweiterungen", dependencies=[Depends(verwalten)])
def liste(db: DbSession = Depends(get_db)) -> list[dict[str, Any]]:
    return [erweiterungen.stand(e) for e in erweiterungen.alle(db)]


@router.post("/api/admin/erweiterungen", dependencies=[Depends(verwalten)])
async def koppeln(body: dict, request: Request, actor: User = Depends(current_user),
                  db: DbSession = Depends(get_db)) -> dict[str, Any]:
    try:
        e = await asyncio.to_thread(erweiterungen.koppeln, db, str(body.get("adresse") or ""),
                                    str(body.get("schluessel") or ""))
    except erweiterungen.ErweiterungFehler as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    audit.record(db, "erweiterung.gekoppelt", actor=actor, request=request, object_type="erweiterung",
                 object_id=e.slug, adresse=e.adresse, version=(e.manifest or {}).get("version"))
    db.commit()
    if e.an:
        erweiterungen.routen_schieben(db)
    return erweiterungen.stand(e)


@router.put("/api/admin/erweiterungen/{slug}", dependencies=[Depends(verwalten)])
def einstellen(slug: str, body: dict, request: Request, tasks: BackgroundTasks,
               actor: User = Depends(current_user), db: DbSession = Depends(get_db)) -> dict[str, Any]:
    e = _laden(db, slug)
    erweiterungen.einstellen(e, body)
    audit.record(db, "erweiterung.eingestellt", actor=actor, request=request, object_type="erweiterung",
                 object_id=slug, an=e.an, gruppen=e.gruppen, prompt_an=e.prompt_an)
    db.commit()
    erweiterungen.routen_schieben(db)
    # Wer nicht mehr darf, wird gesperrt; wer wieder darf, entsperrt.
    tasks.add_task(_nutzer_abgleichen)
    return erweiterungen.stand(e)


@router.delete("/api/admin/erweiterungen/{slug}", dependencies=[Depends(verwalten)])
def entfernen(slug: str, request: Request, actor: User = Depends(current_user),
              db: DbSession = Depends(get_db)) -> dict[str, str]:
    e = _laden(db, slug)
    erweiterungen.entfernen(db, e)
    audit.record(db, "erweiterung.entkoppelt", actor=actor, request=request, object_type="erweiterung",
                 object_id=slug)
    db.commit()
    erweiterungen.routen_schieben(db)
    return {"status": "entkoppelt"}


@router.get("/api/admin/erweiterungen/{slug}/konfiguration", dependencies=[Depends(verwalten)])
async def konfiguration(slug: str, db: DbSession = Depends(get_db)) -> dict[str, Any]:
    e = _laden(db, slug)
    try:
        return await asyncio.to_thread(erweiterungen.aufruf, e, "GET", "/ota/v1/konfiguration", "Konfiguration")
    except erweiterungen.ErweiterungFehler as exc:
        raise _fehler(exc) from exc


@router.put("/api/admin/erweiterungen/{slug}/konfiguration", dependencies=[Depends(verwalten)])
async def konfigurieren(slug: str, body: dict, request: Request, actor: User = Depends(current_user),
                        db: DbSession = Depends(get_db)) -> dict[str, Any]:
    e = _laden(db, slug)
    schema = ((e.manifest or {}).get("konfiguration") or {}).get("properties") or {}
    werte = {k: v for k, v in body.items() if k in schema}
    try:
        erg = await asyncio.to_thread(erweiterungen.aufruf, e, "PUT", "/ota/v1/konfiguration",
                                      "Konfiguration", json=werte)
    except erweiterungen.ErweiterungFehler as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    # Ins Audit nur, was geändert wurde — Geheimnisse nur als „geändert“.
    audit.record(db, "erweiterung.konfiguriert", actor=actor, request=request, object_type="erweiterung",
                 object_id=slug, felder={k: ("(geändert)" if schema[k].get("x-geheim") else v)
                                         for k, v in werte.items()})
    db.commit()
    return erg


@router.post("/api/admin/erweiterungen/{slug}/testen", dependencies=[Depends(verwalten)])
async def testen(slug: str, db: DbSession = Depends(get_db)) -> dict[str, Any]:
    e = _laden(db, slug)
    try:
        return await asyncio.to_thread(erweiterungen.aufruf, e, "POST", "/ota/v1/testen", "Testen",
                                       zeitlimit=30.0)
    except erweiterungen.ErweiterungFehler as exc:
        raise _fehler(exc) from exc


@router.get("/api/admin/erweiterungen/{slug}/statistik", dependencies=[Depends(verwalten)])
async def statistik(slug: str, db: DbSession = Depends(get_db)) -> dict[str, Any]:
    e = _laden(db, slug)
    try:
        return await asyncio.to_thread(erweiterungen.aufruf, e, "GET", "/ota/v1/statistik", "Statistik")
    except erweiterungen.ErweiterungFehler as exc:
        raise _fehler(exc) from exc


# --- für alle Angemeldeten ------------------------------------------------

@router.get("/api/erweiterungen/ansichten")
def ansichten(user: User = Depends(current_user), db: DbSession = Depends(get_db)) -> list[dict[str, Any]]:
    """Die Ansichten, die dieser Mensch in OTA sieht (Mein Konto, ⋯-Menü)."""
    return erweiterungen.ansichten_fuer(db, user)


@router.get("/api/erweiterungen/{slug}/pruefen")
def pruefen(slug: str, request: Request, user: User = Depends(current_user),
            db: DbSession = Depends(get_db)) -> Response:
    """Traefiks forwardAuth vor /x/<slug>/ansicht/: 200 mit den signierten
    Kopfzeilen, die Traefik an die Erweiterung weiterreicht — oder 403."""
    uri = request.headers.get("x-forwarded-uri", "")
    try:
        kopf = erweiterungen.pruefen(db, slug, user, uri)
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    return Response(status_code=200, headers=kopf)
