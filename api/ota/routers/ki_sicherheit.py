"""KI-Sicherheit (ki_sicherheit.py, Handbuch Kapitel 41).

Nur für die Verwaltung (`settings.manage`). Die Zahlen enthalten weder
Inhalte noch Personen; eine Auskunft mit Begründung wie bei der KI-Nutzung
braucht es für sie nicht.

**Fallberichte** enthalten Inhalt (Ausschnitte, Quelle), wenn auch ohne
Person. Die Liste zeigt nur Zeit, Typ und Werkzeug; einen Bericht öffnet
`POST /faelle/{id}/einsehen` nur mit Begründung, und jede Einsicht steht im
Prüfprotokoll (`ki.fallbericht_eingesehen`, lange Frist). Löschen ebenso
(`ki.fallbericht_geloescht`).
"""
from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
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
            "frist_tage": ki_sicherheit.FRIST_TAGE,
            "fallbericht_tage_max": ki_sicherheit.FALLBERICHT_TAGE_MAX}


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


# ------------------------------------------------------------ Fallberichte

class EinsichtIn(BaseModel):
    grund: str = Field(min_length=10, max_length=500)


def _fall(db: DbSession, fall_id: str):
    try:
        schluessel = uuid.UUID(fall_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Diesen Fallbericht gibt es nicht.") from exc
    b = ki_sicherheit.bericht(db, schluessel)
    if b is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "Diesen Fallbericht gibt es nicht (mehr). Nach Ablauf der Frist löscht OTA ihn.")
    return b


@router.get("/faelle", dependencies=[Depends(verwalten)])
def faelle(tage: int = Query(30, ge=1, le=365), db: DbSession = Depends(get_db)) -> dict:
    """Die Liste ohne Inhalt — ohne Begründung, ohne Protokoll."""
    e = ki_sicherheit.einstellungen(db)
    return {"an": e["fallberichte"], "frist_tage": e["fallbericht_tage"],
            "faelle": ki_sicherheit.faelle(db, tage)}


@router.post("/faelle/{fall_id}/einsehen", dependencies=[Depends(verwalten)])
def einsehen(fall_id: str, body: EinsichtIn, request: Request, actor: User = Depends(current_user),
             db: DbSession = Depends(get_db)) -> dict:
    """Einen Bericht öffnen: nur mit Begründung, jede Einsicht im Protokoll."""
    grund = " ".join(body.grund.split())
    if len(grund) < 10:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Die Begründung ist zu kurz.")
    b = _fall(db, fall_id)
    b.eingesehen = (b.eingesehen or 0) + 1
    audit.record(db, "ki.fallbericht_eingesehen", actor=actor, request=request,
                 object_type="ki_fallbericht", object_id=str(b.id), grund=grund,
                 fall_zeit=b.zeit.isoformat(), typen=b.typen, werkzeug=b.werkzeug)
    db.commit()
    return ki_sicherheit.bericht_voll(b)


@router.delete("/faelle/{fall_id}", dependencies=[Depends(verwalten)])
def fall_loeschen(fall_id: str, request: Request, actor: User = Depends(current_user),
                  db: DbSession = Depends(get_db)) -> dict:
    b = _fall(db, fall_id)
    audit.record(db, "ki.fallbericht_geloescht", actor=actor, request=request,
                 object_type="ki_fallbericht", object_id=str(b.id), fall_zeit=b.zeit.isoformat(),
                 typen=b.typen)
    db.delete(b)
    db.commit()
    return {"geloescht": 1}


@router.delete("/faelle", dependencies=[Depends(verwalten)])
def faelle_loeschen(request: Request, actor: User = Depends(current_user),
                    db: DbSession = Depends(get_db)) -> dict:
    weg = ki_sicherheit.faelle_loeschen(db)
    audit.record(db, "ki.fallbericht_geloescht", actor=actor, request=request,
                 object_type="ki_fallbericht", object_id="alle", anzahl=weg)
    db.commit()
    return {"geloescht": weg}
