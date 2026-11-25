"""KI-Sicherheit (ki_sicherheit.py, Handbuch Kapitel 41).

Nur für die Verwaltung (`settings.manage`). Die Zahlen enthalten weder
Inhalte noch Personen; eine Auskunft mit Begründung wie bei der KI-Nutzung
braucht es deshalb nicht.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session as DbSession

from .. import agent_client, audit, ide_ai, ki_sicherheit
from ..db import get_db
from ..deps import current_user, require_permission
from ..models import User

router = APIRouter(prefix="/api/admin/ki-sicherheit", tags=["ki-sicherheit"])
verwalten = require_permission("settings.manage")


def _stand(db: DbSession) -> dict:
    e = ide_ai.einstellungen(db)
    return {**ki_sicherheit.einstellungen(db), "modelle": ki_sicherheit.modelle(db),
            "durchgang": e["durchgang"], "aktiv": ide_ai.durchgang_aktiv(db, e),
            "frist_tage": ki_sicherheit.FRIST_TAGE}


@router.get("", dependencies=[Depends(verwalten)])
def stand(db: DbSession = Depends(get_db)) -> dict:
    return _stand(db)


@router.put("", dependencies=[Depends(verwalten)])
def einstellen(body: dict, request: Request, actor: User = Depends(current_user),
               db: DbSession = Depends(get_db)) -> dict:
    try:
        e = ki_sicherheit.speichern(db, body)
    except ki_sicherheit.SicherheitFehler as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    audit.record(db, "ki.sicherheit_eingestellt", actor=actor, request=request,
                 object_type="settings", object_id="ki_sicherheit", **e)
    db.commit()
    ide_ai.durchgang_schieben(db)
    return _stand(db)


@router.post("/test", dependencies=[Depends(verwalten)])
async def testen(body: dict, db: DbSession = Depends(get_db)) -> dict:
    modell = str(body.get("modell") or ki_sicherheit.einstellungen(db)["modell"] or "")
    try:
        return await asyncio.to_thread(ki_sicherheit.modell_testen, db, modell)
    except ki_sicherheit.SicherheitFehler as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.get("/statistik", dependencies=[Depends(verwalten)])
async def statistik(tage: int = Query(30, ge=1, le=365), db: DbSession = Depends(get_db)) -> dict:
    try:
        lage = (await asyncio.to_thread(agent_client.ki_status)).get("durchgang") or {}
    except HTTPException:
        lage = {}
    return {**ki_sicherheit.uebersicht(db, tage), "lage": lage.get("sicherheit") or {}}


@router.delete("/statistik", dependencies=[Depends(verwalten)])
def loeschen(request: Request, actor: User = Depends(current_user),
             db: DbSession = Depends(get_db)) -> dict:
    weg = ki_sicherheit.alles_loeschen(db)
    audit.record(db, "ki.sicherheit_geloescht", actor=actor, request=request, zeilen=weg)
    db.commit()
    return {"zeilen": weg}
