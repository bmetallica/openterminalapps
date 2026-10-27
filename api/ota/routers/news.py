"""News: Meldungen der Verwaltung an alle (Handbuch Kapitel 11).

Lesen darf jeder Angemeldete, schreiben, wer `settings.manage` hat. Der Text
ist Markdown und wird im Browser mit demselben Renderer gezeigt wie das
Handbuch — der gibt kein rohes HTML durch, ein Beitrag kann also nichts
ausführen.

Ungelesen ist, was nach dem letzten Besuch der News-Seite veröffentlicht
wurde. Wer die Seite nie geöffnet hat, sieht nur die Beiträge der letzten
30 Tage als neu — sonst begrüsste ein neues Konto ein Zähler über alles,
was je geschrieben wurde.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from .. import audit
from ..db import get_db
from ..deps import current_user, require_permission
from ..models import NewsBeitrag, NewsGelesen, User

router = APIRouter(prefix="/api/news", tags=["news"])

schreiben = require_permission("settings.manage")

NEU_OHNE_BESUCH = timedelta(days=30)


class NewsIn(BaseModel):
    titel: str = Field(min_length=1, max_length=200)
    text: str = Field("", max_length=100_000)
    angeheftet: bool = False
    entwurf: bool = False


def _darf_schreiben(user: User) -> bool:
    return user.is_admin or "settings.manage" in user.permissions


def _out(b: NewsBeitrag) -> dict:
    return {
        "id": str(b.id), "titel": b.titel, "text": b.text,
        "angeheftet": b.angeheftet, "entwurf": b.entwurf, "autor": b.autor,
        "erstellt_am": b.erstellt_am.isoformat(),
        "geaendert_am": b.geaendert_am.isoformat(),
        "veroeffentlicht_am": b.veroeffentlicht_am.isoformat() if b.veroeffentlicht_am else None,
    }


def _gelesen_bis(db: DbSession, user: User) -> datetime:
    zeile = db.get(NewsGelesen, user.id)
    return zeile.am if zeile else datetime.now(timezone.utc) - NEU_OHNE_BESUCH


@router.get("")
def liste(user: User = Depends(current_user), db: DbSession = Depends(get_db)) -> dict:
    """Alle Beiträge, angeheftete zuerst, dann die neuesten. Entwürfe nur für
    die, die schreiben dürfen."""
    abfrage = select(NewsBeitrag)
    if not _darf_schreiben(user):
        abfrage = abfrage.where(NewsBeitrag.entwurf.is_(False))
    beitraege = db.scalars(abfrage.order_by(
        NewsBeitrag.angeheftet.desc(),
        func.coalesce(NewsBeitrag.veroeffentlicht_am, NewsBeitrag.erstellt_am).desc(),
    )).all()
    return {
        "beitraege": [_out(b) for b in beitraege],
        "gelesen_bis": _gelesen_bis(db, user).isoformat(),
        "darf_schreiben": _darf_schreiben(user),
    }


@router.get("/ungelesen")
def ungelesen(user: User = Depends(current_user), db: DbSession = Depends(get_db)) -> dict:
    """Für den Punkt in der Seitenleiste."""
    anzahl = db.scalar(select(func.count()).select_from(NewsBeitrag).where(
        NewsBeitrag.entwurf.is_(False),
        NewsBeitrag.veroeffentlicht_am > _gelesen_bis(db, user),
    )) or 0
    return {"anzahl": anzahl}


@router.post("/gelesen")
def gelesen(user: User = Depends(current_user), db: DbSession = Depends(get_db)) -> dict:
    """Die News-Seite wurde geöffnet: alles bis jetzt ist gelesen."""
    zeile = db.get(NewsGelesen, user.id)
    jetzt = datetime.now(timezone.utc)
    if zeile:
        zeile.am = jetzt
    else:
        db.add(NewsGelesen(user_id=user.id, am=jetzt))
    db.commit()
    return {"anzahl": 0}


def _setzen(b: NewsBeitrag, body: NewsIn) -> None:
    b.titel, b.text = body.titel.strip(), body.text
    b.angeheftet, b.entwurf = body.angeheftet, body.entwurf
    b.geaendert_am = datetime.now(timezone.utc)
    if not body.entwurf and b.veroeffentlicht_am is None:
        b.veroeffentlicht_am = b.geaendert_am


@router.post("", status_code=status.HTTP_201_CREATED)
def anlegen(body: NewsIn, request: Request, user: User = Depends(schreiben),
            db: DbSession = Depends(get_db)) -> dict:
    b = NewsBeitrag(id=uuid.uuid4(), autor=user.display_name or user.username,
                    erstellt_am=datetime.now(timezone.utc))
    _setzen(b, body)
    db.add(b)
    audit.record(db, "news.created", actor=user, object_type="news", object_id=str(b.id),
                 request=request, entwurf=body.entwurf)
    db.commit()
    return _out(b)


def _laden(db: DbSession, news_id: uuid.UUID) -> NewsBeitrag:
    b = db.get(NewsBeitrag, news_id)
    if not b:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Beitrag nicht gefunden")
    return b


@router.put("/{news_id}")
def aendern(news_id: uuid.UUID, body: NewsIn, request: Request,
            user: User = Depends(schreiben), db: DbSession = Depends(get_db)) -> dict:
    b = _laden(db, news_id)
    _setzen(b, body)
    audit.record(db, "news.updated", actor=user, object_type="news", object_id=str(b.id),
                 request=request, entwurf=body.entwurf)
    db.commit()
    return _out(b)


@router.delete("/{news_id}")
def loeschen(news_id: uuid.UUID, request: Request,
             user: User = Depends(schreiben), db: DbSession = Depends(get_db)) -> dict:
    b = _laden(db, news_id)
    db.delete(b)
    audit.record(db, "news.deleted", actor=user, object_type="news", object_id=str(news_id),
                 request=request)
    db.commit()
    return {"status": "geloescht"}
