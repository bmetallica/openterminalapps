"""Datenschutz (datenschutz.py, Handbuch Kapitel 42).

Recht `datenschutz.pruefen` (oder `admin`). Was hier gelesen wird, steht nur
dann im Prüfprotokoll, wenn es um eine bestimmte Person geht oder Daten die
Anlage verlassen:

* `user.auskunft` — Auskunft nach Art. 15 erstellt, mit Begründung;
* `datenschutz.protokoll_exportiert` — das Prüfprotokoll als CSV, mit Filtern;
* `datenschutz.protokoll_person` — das Protokoll nach einer Person gefiltert,
  einmal je zehn Minuten und Person.
"""
from __future__ import annotations

import re
import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DbSession

from .. import audit, datenschutz
from ..db import get_db
from ..deps import current_user, require_permission
from ..models import User

router = APIRouter(prefix="/api/datenschutz", tags=["datenschutz"])
pruefen = require_permission(datenschutz.RECHT)

_person_gesehen: dict[tuple[str, str], float] = {}


class AuskunftIn(BaseModel):
    grund: str = Field(min_length=10, max_length=500)


def _aktionen(art: str | None) -> tuple[str, ...] | None:
    if not art:
        return None
    if art == "zugriffe":
        return datenschutz.ALLE_ZUGRIFFE
    if art in datenschutz.ZUGRIFFE:
        return datenschutz.ZUGRIFFE[art]
    if re.fullmatch(r"[a-z_]+\.[a-z_]+", art):
        return (art,)
    raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unbekannte Art von Vorgängen.")


def _betroffen(db: DbSession, person: str | None) -> User | None:
    if not person:
        return None
    try:
        u = db.get(User, uuid.UUID(person))
    except ValueError:
        u = None
    if u is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dieses Konto gibt es nicht.")
    return u


def _person_vermerken(db: DbSession, actor: User, u: User, request: Request) -> None:
    """Wer im Protokoll gezielt nach einer Person sucht, sieht deren Vorgänge.
    Das gehört selbst ins Protokoll — einmal je zehn Minuten, nicht je Seite."""
    schl = (str(actor.id), str(u.id))
    jetzt = time.monotonic()
    if jetzt - _person_gesehen.get(schl, -1e9) < 600:
        return
    _person_gesehen[schl] = jetzt
    audit.record(db, "datenschutz.protokoll_person", actor=actor, request=request,
                 object_type="user", object_id=str(u.id), name=u.username)
    db.commit()


@router.get("/lage", dependencies=[Depends(pruefen)])
def lage(db: DbSession = Depends(get_db)) -> dict:
    return datenschutz.lage(db)


@router.get("/rechte", dependencies=[Depends(pruefen)])
def rechte(db: DbSession = Depends(get_db)) -> dict:
    return datenschutz.rechte(db)


@router.get("/protokoll", dependencies=[Depends(pruefen)])
def protokoll(request: Request, von: str | None = None, bis: str | None = None,
              art: str | None = Query(None, max_length=64), wer: str | None = Query(None, max_length=128),
              person: str | None = None, seite: int = Query(1, ge=1, le=100_000),
              actor: User = Depends(current_user), db: DbSession = Depends(get_db)) -> dict:
    u = _betroffen(db, person)
    if u is not None:
        _person_vermerken(db, actor, u, request)
    return datenschutz.protokoll(db, von=datenschutz.tag(von), bis=datenschutz.tag(bis, ende=True),
                                 aktionen=_aktionen(art), wer=wer, betroffen=u, seite=seite)


@router.get("/protokoll.csv", dependencies=[Depends(pruefen)])
def protokoll_csv(request: Request, von: str | None = None, bis: str | None = None,
                  art: str | None = Query(None, max_length=64), wer: str | None = Query(None, max_length=128),
                  person: str | None = None, actor: User = Depends(current_user),
                  db: DbSession = Depends(get_db)) -> Response:
    u = _betroffen(db, person)
    inhalt, n = datenschutz.protokoll_csv(db, von=datenschutz.tag(von),
                                          bis=datenschutz.tag(bis, ende=True),
                                          aktionen=_aktionen(art), wer=wer, betroffen=u)
    audit.record(db, "datenschutz.protokoll_exportiert", actor=actor, request=request,
                 object_type="user" if u else None, object_id=str(u.id) if u else None,
                 von=von, bis=bis, art=art, wer=wer, person=u.username if u else None, zeilen=n)
    db.commit()
    datei = f"pruefprotokoll-{datetime.now(timezone.utc):%Y%m%d-%H%M}.csv"
    return Response(content=inhalt, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{datei}"',
                             "Cache-Control": "no-store"})


@router.get("/personen", dependencies=[Depends(pruefen)])
def personen(q: str = Query(..., min_length=2, max_length=128), db: DbSession = Depends(get_db)) -> list[dict]:
    return datenschutz.personen(db, q)


def auskunft_erstellen(db: DbSession, user_id: uuid.UUID, grund: str, actor: User,
                       request: Request) -> Response:
    """Auskunft nach Art. 15 als ZIP — für diese Seite und für Personen →
    Konto (routers/admin.py). Die Begründung ist Pflicht und steht im Protokoll."""
    from .. import auskunft as auskunft_mod

    grund = " ".join(grund.split())
    if len(grund) < 10:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Bitte eine Begründung angeben, z. B. das Aktenzeichen des Antrags.")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nutzer nicht gefunden")
    inhalt, zaehler = auskunft_mod.erstellen(db, user, actor)
    audit.record(db, "user.auskunft", actor=actor, object_type="user", object_id=str(user.id),
                 request=request, name=user.username, grund=grund, dateien=zaehler)
    db.commit()
    datei = f"auskunft-{re.sub(r'[^A-Za-z0-9._-]', '_', user.username)}-{datetime.now(timezone.utc):%Y%m%d-%H%M}.zip"
    return Response(content=inhalt, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{datei}"',
                             "Cache-Control": "no-store"})


@router.post("/auskunft/{user_id}", dependencies=[Depends(pruefen)])
def auskunft(user_id: uuid.UUID, body: AuskunftIn, request: Request,
             actor: User = Depends(current_user), db: DbSession = Depends(get_db)) -> Response:
    return auskunft_erstellen(db, user_id, body.grund, actor, request)
