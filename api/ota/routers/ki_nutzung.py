"""Verwaltung → KI-Nutzung (ki_statistik.py, Handbuch Kapitel 28).

Nur für die Verwaltung (`settings.manage`). Wer die Zahlen eines einzelnen
Menschen ansieht, steht im Prüfprotokoll — einmal je zehn Minuten und
Mensch, nicht bei jedem Verschieben des Graphen.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session as DbSession

from .. import agent_client, audit, ide_ai, ki_statistik
from ..db import get_db
from ..deps import current_user, require_permission
from ..models import User

router = APIRouter(prefix="/api/admin/ki-nutzung", tags=["ki-nutzung"])
verwalten = require_permission("settings.manage")

_angesehen: dict[tuple[str, str], float] = {}


def _zeit(roh: str | None) -> datetime | None:
    if not roh:
        return None
    try:
        z = datetime.fromisoformat(roh.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ungültige Zeitangabe.") from exc
    return z if z.tzinfo else z.replace(tzinfo=timezone.utc)


def _tz(roh: str | None) -> str:
    try:
        ZoneInfo(roh or "UTC")
        return roh or "UTC"
    except (ZoneInfoNotFoundError, ValueError):
        return "UTC"


@router.get("", dependencies=[Depends(verwalten)])
def uebersicht(von: str | None = Query(None), bis: str | None = Query(None),
               tz: str | None = Query(None), db: DbSession = Depends(get_db)) -> dict:
    e = ide_ai.einstellungen(db)
    return {**ki_statistik.uebersicht(db, _zeit(von), _zeit(bis), _tz(tz)),
            "statistik": e["statistik"], "durchgang": e["durchgang"],
            "frist_roh": e["frist_roh"], "frist_stunden": e["frist_stunden"]}


@router.get("/status", dependencies=[Depends(verwalten)])
async def zustand(db: DbSession = Depends(get_db)) -> dict:
    e = ide_ai.einstellungen(db)
    try:
        lage = await asyncio.to_thread(agent_client.ki_status)
    except HTTPException as exc:
        lage = {"fehler": exc.detail}
    return {"durchgang": e["durchgang"], "statistik": e["statistik"],
            "aktiv": ide_ai.durchgang_aktiv(db, e), "fehler": lage.get("fehler"),
            # Was ota-ki über sich meldet, und ob die Firewall umleitet.
            "lage": lage.get("durchgang") or {}, "firewall": lage.get("firewall") or {}}


@router.get("/nutzer/{user_id}", dependencies=[Depends(verwalten)])
def nutzer(user_id: str, request: Request, von: str | None = Query(None),
           bis: str | None = Query(None), tz: str | None = Query(None),
           actor: User = Depends(current_user), db: DbSession = Depends(get_db)) -> dict:
    """`unbekannt` für Anfragen, die keiner Sitzung zuzuordnen waren."""
    uid = None
    if user_id != "unbekannt":
        try:
            uid = uuid.UUID(user_id)
        except ValueError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Unbekannt.") from exc
    schl = (str(actor.id), user_id)
    if time.monotonic() - _angesehen.get(schl, -1e9) > 600:
        _angesehen[schl] = time.monotonic()
        audit.record(db, "ki.nutzung_angesehen", actor=actor, request=request,
                     object_type="user", object_id=user_id)
        db.commit()
    return ki_statistik.nutzer(db, uid, _zeit(von), _zeit(bis), _tz(tz))


@router.delete("", dependencies=[Depends(verwalten)])
def alles_loeschen(request: Request, actor: User = Depends(current_user),
                   db: DbSession = Depends(get_db)) -> dict:
    weg = ki_statistik.alles_loeschen(db)
    audit.record(db, "ki.nutzung_geloescht", actor=actor, request=request, **weg)
    db.commit()
    return weg
