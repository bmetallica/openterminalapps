"""Verwaltung → Paketquellen (Handbuch Kapitel 26).

Nur Administratoren (Betreiber, 2026-10-07): Ein hochgeladenes Paket laeuft
bei der Installation als root in jedem Arbeitsplatz. Jeder Vorgang steht im
Audit-Log; beim Upload mit Name, Version und Pruefsumme.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DbSession

from .. import audit, paketquellen, settings_store
from ..db import get_db
from ..deps import current_user, require_permission
from ..models import User

router = APIRouter(prefix="/api/paketquellen", tags=["paketquellen"])
nur_admin = require_permission("admin")


def _alter_tage(status_: dict) -> float | None:
    letzter = status_.get("letzter_abgleich") or {}
    zeit = letzter.get("zeit")
    if not zeit:
        return None
    try:
        dann = datetime.fromisoformat(zeit)
    except ValueError:
        return None
    return round((datetime.now(timezone.utc) - dann).total_seconds() / 86400, 1)


@router.get("/kurz", dependencies=[Depends(require_permission("admin", "sessions.view_all"))])
def kurz(db: DbSession = Depends(get_db)) -> dict:
    """Für das Dashboard der Verwaltung: erreichbar? wie alt ist der Spiegel?"""
    spiegel = paketquellen.spiegel_aktiv()
    try:
        # `/kurz` statt `/status`: Das Dashboard fragt alle 15 Sekunden, und
        # `/status` misst den ganzen Bestand und wartet auf aptlys Sperre —
        # mit kurzer Wartezeit hiess das dauerhaft „antwortet nicht", mit
        # langer belegten haengende Abfragen Arbeiter der API.
        st = paketquellen.aufruf("GET", "/kurz", timeout=5.0)
    except HTTPException:
        return {"aktiv": True, "spiegel": spiegel, "erreichbar": False}
    return {"aktiv": True, "spiegel": spiegel, "erreichbar": True,
            "alter_tage": _alter_tage(st) if spiegel else None,
            "gelb": settings_store.get(db, settings_store.REPO_ALTER_GELB),
            "rot": settings_store.get(db, settings_store.REPO_ALTER_ROT)}


@router.get("", dependencies=[Depends(nur_admin)])
def uebersicht(db: DbSession = Depends(get_db)) -> dict:
    einstellungen = {
        "modus": settings_store.get(db, settings_store.REPO_MODUS),
        "bau_snapshot": settings_store.get(db, settings_store.REPO_BAU_SNAPSHOT) or "",
        "alter_gelb": settings_store.get(db, settings_store.REPO_ALTER_GELB),
        "alter_rot": settings_store.get(db, settings_store.REPO_ALTER_ROT),
    }
    spiegel = paketquellen.spiegel_aktiv()
    try:
        st = paketquellen.aufruf("GET", "/status", timeout=120.0)
    except HTTPException as exc:
        return {"aktiv": True, "spiegel": spiegel, "erreichbar": False,
                "fehler": str(exc.detail), "einstellungen": einstellungen}
    return {"aktiv": True, "spiegel": spiegel, "erreichbar": True, "status": st,
            "alter_tage": _alter_tage(st) if spiegel else None,
            "einstellungen": einstellungen}


class EinstellungenIn(BaseModel):
    modus: str = Field(pattern="^(aus|zuerst|nur)$")
    bau_snapshot: str = ""
    alter_gelb: int = Field(7, ge=1, le=365)
    alter_rot: int = Field(30, ge=1, le=3650)


@router.put("/einstellungen", dependencies=[Depends(nur_admin)])
def einstellungen(body: EinstellungenIn, request: Request,
                  actor: User = Depends(current_user),
                  db: DbSession = Depends(get_db)) -> dict:
    if body.modus == "nur" and not paketquellen.spiegel_aktiv():
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "„Nur Spiegel“ braucht den Spiegel — sonst gäbe es in den "
                            "Arbeitsplätzen keine Debian-Pakete mehr (OTA_REPO_SPIEGEL=1).")
    alt = settings_store.get(db, settings_store.REPO_MODUS)
    settings_store.put(db, settings_store.REPO_MODUS, body.modus)
    settings_store.put(db, settings_store.REPO_BAU_SNAPSHOT, body.bau_snapshot)
    settings_store.put(db, settings_store.REPO_ALTER_GELB, body.alter_gelb)
    settings_store.put(db, settings_store.REPO_ALTER_ROT, body.alter_rot)
    audit.record(db, "repo.einstellungen", actor=actor, request=request,
                 modus=body.modus, vorher=alt, bau_snapshot=body.bau_snapshot)
    db.commit()
    paketquellen.zwischenspeicher_leeren()
    return {"status": "gespeichert — gilt beim nächsten Start eines Arbeitsplatzes"}


@router.post("/abgleich", dependencies=[Depends(nur_admin)])
def abgleich(request: Request, actor: User = Depends(current_user),
             db: DbSession = Depends(get_db)) -> dict:
    ergebnis = paketquellen.aufruf("POST", "/abgleich")
    audit.record(db, "repo.abgleich", actor=actor, request=request)
    db.commit()
    paketquellen.zwischenspeicher_leeren()
    return ergebnis


@router.get("/auftrag", dependencies=[Depends(nur_admin)])
def auftrag() -> dict:
    return paketquellen.aufruf("GET", "/auftrag")


@router.get("/pakete", dependencies=[Depends(nur_admin)])
def pakete() -> list:
    return paketquellen.aufruf("GET", "/pakete")


@router.post("/pakete", dependencies=[Depends(nur_admin)])
async def hochladen(request: Request, datei: UploadFile = File(...),
                    actor: User = Depends(current_user),
                    db: DbSession = Depends(get_db)) -> dict:
    inhalt = await datei.read()
    ergebnis = paketquellen.aufruf(
        "POST", "/pakete", timeout=600.0,
        files={"datei": (datei.filename or "paket.deb", inhalt, "application/vnd.debian.binary-package")},
        data={"von": actor.username})
    audit.record(db, "repo.paket_hochgeladen", actor=actor, request=request,
                 object_type="paket", object_id=f"{ergebnis.get('name')} {ergebnis.get('version')}",
                 sha256=ergebnis.get("sha256"), arch=ergebnis.get("arch"))
    db.commit()
    return ergebnis


@router.delete("/pakete/{schluessel}", dependencies=[Depends(nur_admin)])
def paket_loeschen(schluessel: str, request: Request, actor: User = Depends(current_user),
                   db: DbSession = Depends(get_db)) -> dict:
    ergebnis = paketquellen.aufruf("DELETE", f"/pakete/{schluessel}")
    audit.record(db, "repo.paket_geloescht", actor=actor, request=request,
                 object_type="paket", object_id=schluessel)
    db.commit()
    return ergebnis


class SnapshotIn(BaseModel):
    name: str
    notiz: str = ""


@router.post("/snapshots", dependencies=[Depends(nur_admin)])
def snapshot_anlegen(body: SnapshotIn, request: Request, actor: User = Depends(current_user),
                     db: DbSession = Depends(get_db)) -> dict:
    ergebnis = paketquellen.aufruf("POST", "/snapshots", timeout=600.0,
                                   json={"name": body.name, "notiz": body.notiz,
                                         "von": actor.username})
    audit.record(db, "repo.snapshot_angelegt", actor=actor, request=request,
                 object_type="snapshot", object_id=body.name)
    db.commit()
    paketquellen.zwischenspeicher_leeren()
    return ergebnis


@router.delete("/snapshots/{name}", dependencies=[Depends(nur_admin)])
def snapshot_loeschen(name: str, request: Request, actor: User = Depends(current_user),
                      db: DbSession = Depends(get_db)) -> dict:
    if (settings_store.get(db, settings_store.REPO_BAU_SNAPSHOT) or "") == name:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Gegen diesen Stand wird gebaut. Erst unter „Bauen gegen“ "
                            "einen anderen wählen, dann löschen.")
    ergebnis = paketquellen.aufruf("DELETE", f"/snapshots/{name}", timeout=600.0)
    audit.record(db, "repo.snapshot_geloescht", actor=actor, request=request,
                 object_type="snapshot", object_id=name)
    db.commit()
    paketquellen.zwischenspeicher_leeren()
    return ergebnis


@router.post("/snapshots/{name}/zurueckdrehen", dependencies=[Depends(nur_admin)])
def zurueckdrehen(name: str, request: Request, actor: User = Depends(current_user),
                  db: DbSession = Depends(get_db)) -> dict:
    ergebnis = paketquellen.aufruf("POST", f"/snapshots/{name}/zurueckdrehen", timeout=600.0)
    audit.record(db, "repo.zurueckgedreht", actor=actor, request=request,
                 object_type="snapshot", object_id=name)
    db.commit()
    paketquellen.zwischenspeicher_leeren()
    return ergebnis


@router.post("/dateien", dependencies=[Depends(nur_admin)])
def dateien(request: Request, actor: User = Depends(current_user),
            db: DbSession = Depends(get_db)) -> dict:
    ergebnis = paketquellen.aufruf("POST", "/dateien")
    audit.record(db, "repo.dateien_geholt", actor=actor, request=request)
    db.commit()
    return ergebnis
