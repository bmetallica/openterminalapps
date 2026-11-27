"""Datenschutz: der Hinweis in der Seitenleiste (Handbuch Kapitel 28).

Sobald die KI-Nutzungsstatistik läuft, steht für **alle** ein Punkt
„DSGVO“ in der Seitenleiste: was OTA über Arbeitsplätze und KI-Nutzung
erfasst, wie lange, und wer es sehen darf. Die Verwaltung sieht ihn immer,
damit sie den Text vorher anpassen kann.

Der Text ist Markdown wie bei den News. Leer heisst: der mitgelieferte
(in der Oberfläche, deutsch und englisch). Platzhalter wie `{frist_roh}`
setzt die Oberfläche ein — ein Text, der die Fristen nennt, bleibt so
richtig, wenn jemand sie ändert.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DbSession

from .. import audit, ide_ai, settings_store
from ..db import get_db
from ..deps import current_user, require_permission
from ..models import User

router = APIRouter(prefix="/api/dsgvo", tags=["dsgvo"])

# Den Text verantwortet inhaltlich der/die Datenschutzbeauftragte (Kapitel 42).
schreiben = require_permission("settings.manage", "datenschutz.pruefen")


class HinweisIn(BaseModel):
    text: str = Field("", max_length=100_000)


def _darf_schreiben(user: User) -> bool:
    return user.is_admin or bool({"settings.manage", "datenschutz.pruefen"} & user.permissions)


@router.get("")
def hinweis(user: User = Depends(current_user), db: DbSession = Depends(get_db)) -> dict:
    e = ide_ai.einstellungen(db)
    gespeichert = settings_store.get(db, settings_store.DSGVO) or {}
    darf = _darf_schreiben(user)
    return {
        "aktiv": bool(e["statistik"]),
        "sichtbar": bool(e["statistik"]) or darf,
        "darf_schreiben": darf,
        "text": gespeichert.get("text") or "",
        "geaendert_am": gespeichert.get("am"),
        "werte": {"frist_roh": e["frist_roh"], "frist_stunden": e["frist_stunden"],
                  "statistik": bool(e["statistik"]), "durchgang": bool(e["durchgang"])},
    }


@router.put("")
def setzen(body: HinweisIn, request: Request, user: User = Depends(schreiben),
           db: DbSession = Depends(get_db)) -> dict:
    text = body.text.strip()
    settings_store.put(db, settings_store.DSGVO, {
        "text": text, "am": datetime.now(timezone.utc).isoformat(),
        "von": user.display_name or user.username})
    audit.record(db, "dsgvo.hinweis_geaendert", actor=user, request=request,
                 eigener_text=bool(text))
    db.commit()
    return hinweis(user, db)
