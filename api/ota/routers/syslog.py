"""Einstellungen → Protokoll an Syslog (syslog.py, Handbuch Kapitel 11)."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session as DbSession

from .. import audit, syslog
from ..db import get_db
from ..deps import current_user, require_permission
from ..models import User

router = APIRouter(prefix="/api/admin/syslog", tags=["syslog"])
verwalten = require_permission("settings.manage")


def _stand(db: DbSession) -> dict:
    return {**syslog.einstellungen(db), "lage": syslog.lage(),
            "rueckstand": syslog.rueckstand(db),
            "facilities": list(syslog.FACILITIES)}


@router.get("", dependencies=[Depends(verwalten)])
def stand(db: DbSession = Depends(get_db)) -> dict:
    return _stand(db)


@router.put("", dependencies=[Depends(verwalten)])
def einstellen(body: dict, request: Request, actor: User = Depends(current_user),
               db: DbSession = Depends(get_db)) -> dict:
    try:
        e = syslog.speichern(db, body)
    except syslog.SyslogFehler as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    # Das CA-Zertifikat nicht ins Protokoll, nur ob es eines gibt.
    audit.record(db, "syslog.eingestellt", actor=actor, request=request,
                 object_type="settings", object_id="syslog",
                 **{**e, "ca": bool(e["ca"])})
    db.commit()
    return _stand(db)


@router.post("/test", dependencies=[Depends(verwalten)])
async def testen(body: dict, db: DbSession = Depends(get_db)) -> dict:
    try:
        return await asyncio.to_thread(syslog.testen, db, body)
    except syslog.SyslogFehler as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
