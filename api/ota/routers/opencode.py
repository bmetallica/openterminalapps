"""Einstellungen → KI-Werkzeuge → opencode (opencode.py, Handbuch Kapitel 38)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session as DbSession

from .. import audit, opencode
from ..db import get_db
from ..deps import current_user, require_permission
from ..models import User
from .firewall import schieben

router = APIRouter(prefix="/api/admin/opencode", tags=["opencode"])
verwalten = require_permission("settings.manage")


@router.get("", dependencies=[Depends(verwalten)])
def stand(db: DbSession = Depends(get_db)) -> dict:
    return opencode.stand(db)


@router.put("", dependencies=[Depends(verwalten)])
def einstellen(body: dict, request: Request, actor: User = Depends(current_user),
               db: DbSession = Depends(get_db)) -> dict:
    """Wirkt beim nächsten Start oder Fortsetzen eines Arbeitsplatzes. Der
    Prompt-Zusatz kommt mit altem und neuem Text ins Audit-Log: Er steuert,
    was die Modelle tun."""
    vorher = opencode.einstellungen(db)
    try:
        neu = opencode.speichern(db, body)
    except opencode.OpencodeFehler as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    geaendert = {k: {"vorher": vorher[k], "nachher": neu[k]}
                 for k in ("prompt", "prompt_gruppen", "zusatz") if vorher[k] != neu[k]}
    if vorher["mcp"] != neu["mcp"]:
        # Ohne die Schlüssel — nur, dass sich einer geändert hat.
        ohne = lambda liste: [{k: v for k, v in m.items() if k != "schluessel"} for m in liste]  # noqa: E731
        alt = {m["name"]: m.get("schluessel") for m in vorher["mcp"]}
        geaendert["mcp"] = {"vorher": ohne(vorher["mcp"]), "nachher": ohne(neu["mcp"]),
                            "schluessel_geaendert": sorted(m["name"] for m in neu["mcp"]
                                                           if alt.get(m["name"]) != m.get("schluessel"))}
    audit.record(db, "opencode.eingestellt", actor=actor, request=request,
                 an=neu["an"], gruppen=neu["gruppen"], **geaendert)
    db.commit()
    if vorher["an"] != neu["an"] or opencode.freigaben_von(vorher) != opencode.freigaben_von(neu):
        # Die Firewall gibt den KI-Server frei, solange IDE-AI oder opencode an ist.
        schieben(db)
    return opencode.stand(db)


@router.post("/vorschau", dependencies=[Depends(verwalten)])
def vorschau(body: dict, actor: User = Depends(current_user), db: DbSession = Depends(get_db)) -> dict:
    """So sähe es für diesen Menschen aus (ohne die Einstellungen zu speichern:
    der Entwurf kommt mit)."""
    try:
        uid = uuid.UUID(str(body.get("user_id") or actor.id))
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unbekannter Nutzer") from exc
    user = db.get(User, uid)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unbekannter Nutzer")
    entwurf = body.get("entwurf") if isinstance(body.get("entwurf"), dict) else None
    try:
        return opencode.vorschau(db, user, entwurf)
    except opencode.OpencodeFehler as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
