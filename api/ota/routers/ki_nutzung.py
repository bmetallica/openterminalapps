"""Betrieb → KI-Nutzung (ki_statistik.py, Handbuch Kapitel 28).

Nur für die Verwaltung (`settings.manage`), und auch dort in zwei Stufen:

* **Ohne Namen** (`GET ""`): Summen, Verlauf, Anteile. Menschen und ihre
  Arbeitsplätze erscheinen nur als Grössen, ohne Kennung.
* **Mit Namen** (`/personen`, `/nutzer/{id}`): nur mit einer *Auskunft*. Die
  gibt es gegen eine Begründung, die im Prüfprotokoll landet
  (`ki.auskunft`), und sie gilt eine halbe Stunde für dieses eine Konto.
  Jeder Blick auf einen einzelnen Menschen steht dazu im Protokoll —
  einmal je zehn Minuten und Mensch, mit dem Vorgang der Auskunft.

Die Auskunft ist ein signiertes Merkmal (Kopfzeile `X-OTA-Auskunft`), kein
Zustand im Prozess: Sie überlebt keinen Neustart des Browsers, wohl aber
einen der API, und mehrere API-Prozesse kennen sie alle.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DbSession

from .. import agent_client, audit, ide_ai, ki_statistik
from ..config import settings as konfig
from ..db import get_db
from ..deps import current_user, require_permission
from ..models import User

router = APIRouter(prefix="/api/admin/ki-nutzung", tags=["ki-nutzung"])
verwalten = require_permission("settings.manage")

_angesehen: dict[tuple[str, str], float] = {}

AUSKUNFT_DAUER = 30 * 60


def _signatur(roh: bytes) -> str:
    schluessel = ("ki-auskunft:" + konfig().jwt_secret).encode()
    return base64.urlsafe_b64encode(hmac.new(schluessel, roh, hashlib.sha256).digest()).decode().rstrip("=")


def _merkmal(actor: User, vorgang: str, bis: int) -> str:
    roh = json.dumps({"u": str(actor.id), "v": vorgang, "b": bis}, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(roh).decode().rstrip("=") + "." + _signatur(roh)


def auskunft(actor: User = Depends(current_user),
             x_ota_auskunft: str | None = Header(None)) -> str:
    """Der Vorgang der gültigen Auskunft dieses Kontos — sonst 403."""
    fehlt = HTTPException(status.HTTP_403_FORBIDDEN,
                          "Personenbezogene Zahlen nur mit einer Auskunft — bitte mit Begründung anfordern.")
    if not x_ota_auskunft or "." not in x_ota_auskunft:
        raise fehlt
    teil, sig = x_ota_auskunft.rsplit(".", 1)
    try:
        roh = base64.urlsafe_b64decode(teil + "=" * (-len(teil) % 4))
        daten = json.loads(roh)
    except (ValueError, json.JSONDecodeError) as exc:
        raise fehlt from exc
    if not hmac.compare_digest(sig, _signatur(roh)):
        raise fehlt
    if daten.get("u") != str(actor.id):
        raise fehlt
    if int(daten.get("b") or 0) < time.time():
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Die Auskunft ist abgelaufen — bitte mit Begründung neu anfordern.")
    return str(daten.get("v") or "")


class AuskunftIn(BaseModel):
    grund: str = Field(min_length=10, max_length=500)


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


def _rahmen(db: DbSession) -> dict:
    e = ide_ai.einstellungen(db)
    return {"statistik": e["statistik"], "durchgang": e["durchgang"],
            "frist_roh": e["frist_roh"], "frist_stunden": e["frist_stunden"]}


@router.get("", dependencies=[Depends(verwalten)])
def uebersicht(von: str | None = Query(None), bis: str | None = Query(None),
               tz: str | None = Query(None), db: DbSession = Depends(get_db)) -> dict:
    """Ohne Namen — das, was die Seite ohne Auskunft zeigt."""
    return {**ki_statistik.anonym(db, _zeit(von), _zeit(bis), _tz(tz)), **_rahmen(db)}


@router.post("/auskunft", dependencies=[Depends(verwalten)])
def auskunft_anfordern(body: AuskunftIn, request: Request, actor: User = Depends(current_user),
                       db: DbSession = Depends(get_db)) -> dict:
    grund = " ".join(body.grund.split())
    if len(grund) < 10:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Die Begründung ist zu kurz.")
    vorgang = uuid.uuid4().hex[:12]
    bis = int(time.time()) + AUSKUNFT_DAUER
    audit.record(db, "ki.auskunft", actor=actor, request=request, object_type="ki_auskunft",
                 object_id=vorgang, grund=grund,
                 gueltig_bis=datetime.fromtimestamp(bis, timezone.utc).isoformat())
    db.commit()
    return {"merkmal": _merkmal(actor, vorgang, bis), "vorgang": vorgang,
            "bis": datetime.fromtimestamp(bis, timezone.utc).isoformat(), "grund": grund}


@router.get("/personen", dependencies=[Depends(verwalten)])
def personen(von: str | None = Query(None), bis: str | None = Query(None),
             tz: str | None = Query(None), vorgang: str = Depends(auskunft),
             db: DbSession = Depends(get_db)) -> dict:
    """Die Übersicht mit Namen — nur mit Auskunft."""
    return {**ki_statistik.uebersicht(db, _zeit(von), _zeit(bis), _tz(tz)), **_rahmen(db),
            "vorgang": vorgang}


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
           vorgang: str = Depends(auskunft),
           actor: User = Depends(current_user), db: DbSession = Depends(get_db)) -> dict:
    """`unbekannt` für Anfragen, die keiner Sitzung zuzuordnen waren. Nur
    mit Auskunft."""
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
                     object_type="user", object_id=user_id, vorgang=vorgang)
        db.commit()
    return ki_statistik.nutzer(db, uid, _zeit(von), _zeit(bis), _tz(tz))


@router.delete("", dependencies=[Depends(verwalten)])
def alles_loeschen(request: Request, actor: User = Depends(current_user),
                   db: DbSession = Depends(get_db)) -> dict:
    weg = ki_statistik.alles_loeschen(db)
    audit.record(db, "ki.nutzung_geloescht", actor=actor, request=request, **weg)
    db.commit()
    return weg


# ------------------------------------------------ Die eigenen Zahlen (Art. 15)

eigen = APIRouter(prefix="/api/ki-nutzung", tags=["ki-nutzung"])


@eigen.get("/meine")
def meine(von: str | None = Query(None), bis: str | None = Query(None),
          tz: str | None = Query(None), user: User = Depends(current_user),
          db: DbSession = Depends(get_db)) -> dict:
    """Jeder sieht seine eigenen Zahlen — ohne Begründung und ohne Eintrag
    im Prüfprotokoll: Es sind seine Daten, nicht die eines anderen."""
    return {**ki_statistik.nutzer(db, user.id, _zeit(von), _zeit(bis), _tz(tz)), **_rahmen(db)}
