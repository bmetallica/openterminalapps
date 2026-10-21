"""Softwaremonitoring in der Verwaltung (software.py, Handbuch Kapitel 11).

Sehen darf, wer alle Sitzungen sehen darf. Die Whitelist ändert, wer die
Einstellungen ändert — sie ist eine Regel für alle, keine Beobachtung.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from .. import audit, settings_store, software
from ..db import SessionLocal, get_db
from ..deps import current_user, require_permission
from ..models import SoftwareFreigabe, User

router = APIRouter(prefix="/api/admin/software", tags=["software"])
sehen = require_permission("sessions.view_all")
aendern = require_permission("settings.manage")


@router.get("", dependencies=[Depends(sehen)])
def stand(db: DbSession = Depends(get_db)) -> dict:
    return {
        "letzte": settings_store.get(db, settings_store.SOFTWARE_LETZTE),
        "intervall_minuten": software.INTERVALL_SEKUNDEN // 60,
        "arbeitsplaetze": software.uebersicht(db),
        "meldungen": software.meldungen(db),
        "whitelist": [{"name": f.name, "titel": f.titel, "quelle": f.quelle,
                       "von": f.von, "am": f.am.isoformat()}
                      for f in db.scalars(select(SoftwareFreigabe)
                                          .order_by(SoftwareFreigabe.name)).all()],
    }


@router.get("/meldungen", dependencies=[Depends(sehen)])
def meldungen(db: DbSession = Depends(get_db)) -> list[dict]:
    """Kurz, fürs Dashboard."""
    return software.meldungen(db)


def _erfassen(anlass: str) -> dict:
    with SessionLocal() as db:
        return software.erfassen(db, anlass)


@router.post("/erfassen", dependencies=[Depends(sehen)])
async def erfassen(request: Request, actor: User = Depends(current_user)) -> dict:
    try:
        return await asyncio.to_thread(_erfassen, f"von Hand ({actor.username})")
    except software.LaeuftSchon as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.post("/whitelist", dependencies=[Depends(aendern)])
def aufnehmen(body: dict, request: Request, actor: User = Depends(current_user),
              db: DbSession = Depends(get_db)) -> dict:
    namen = body.get("namen") or []
    if not isinstance(namen, list) or not namen:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Welche Anwendungen?")
    neu = software.freigeben(db, [str(n) for n in namen], actor.username)
    if neu:
        audit.record(db, "software.freigegeben", actor=actor, request=request,
                     namen=neu[:50], anzahl=len(neu))
    db.commit()
    return {"neu": neu}


@router.post("/whitelist/erstbefuellen", dependencies=[Depends(aendern)])
def erstbefuellen(request: Request, actor: User = Depends(current_user),
                  db: DbSession = Depends(get_db)) -> dict:
    neu = software.erstbefuellen(db, actor.username)
    audit.record(db, "software.whitelist_befuellt", actor=actor, request=request,
                 anzahl=len(neu))
    db.commit()
    return {"neu": neu}


@router.delete("/whitelist/{name}", dependencies=[Depends(aendern)])
def entfernen(name: str, request: Request, actor: User = Depends(current_user),
              db: DbSession = Depends(get_db)) -> dict:
    eintrag = db.get(SoftwareFreigabe, name.strip().lower())
    if eintrag is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Steht nicht auf der Whitelist.")
    db.delete(eintrag)
    audit.record(db, "software.entzogen", actor=actor, request=request, name=eintrag.name)
    db.commit()
    return {"entfernt": eintrag.name}
