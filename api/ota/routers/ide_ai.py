"""Einstellungen → IDE-AI (ide_ai.py, Handbuch Kapitel 28)."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session as DbSession

from .. import audit, ide_ai
from ..db import get_db
from ..deps import current_user, require_permission
from ..models import User
from .firewall import schieben

router = APIRouter(prefix="/api/admin/ide-ai", tags=["ide-ai"])
verwalten = require_permission("settings.manage")


@router.get("", dependencies=[Depends(verwalten)])
def stand(db: DbSession = Depends(get_db)) -> dict:
    return ide_ai.stand(db)


@router.put("", dependencies=[Depends(verwalten)])
def einstellen(body: dict, request: Request, actor: User = Depends(current_user),
               db: DbSession = Depends(get_db)) -> dict:
    """Speichern. Wirkt beim nächsten Start oder Fortsetzen eines Arbeitsplatzes;
    die Freigabe in der Firewall sofort."""
    vorher = ide_ai.einstellungen(db)
    try:
        neu = ide_ai.speichern(db, body)
    except ide_ai.IdeAiFehler as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    audit.record(db, "ide_ai.eingestellt", actor=actor, request=request,
                 an=neu["an"], url=neu["url"], modelle=[m["id"] for m in neu["modelle"]],
                 schluessel_geaendert="api_key" in body and body["api_key"] is not None)
    db.commit()
    if (vorher["an"], vorher["url"]) != (neu["an"], neu["url"]):
        schieben(db)
    return ide_ai.stand(db)


@router.post("/modelle", dependencies=[Depends(verwalten)])
async def modelle(body: dict, db: DbSession = Depends(get_db)) -> list[dict]:
    """Die Modelle des Servers. Ohne Schlüssel im Aufruf gilt der gespeicherte."""
    schluessel = body.get("api_key")
    if schluessel is None:
        schluessel = ide_ai.einstellungen(db)["api_key"]
    try:
        return await asyncio.to_thread(ide_ai.modelle_abrufen, str(body.get("url") or ""),
                                       str(schluessel or ""))
    except ide_ai.IdeAiFehler as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc


@router.post("/testen", dependencies=[Depends(verwalten)])
async def testen(body: dict, db: DbSession = Depends(get_db)) -> dict:
    try:
        return await asyncio.to_thread(ide_ai.testen, db, str(body.get("modell") or ""))
    except ide_ai.IdeAiFehler as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
