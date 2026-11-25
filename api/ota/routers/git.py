"""Einstellungen → Git (git.py, Handbuch Kapitel 27)."""

from __future__ import annotations

import asyncio
import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session as DbSession

from .. import audit, git, git_geheimnisse, keycloak, settings_store
from ..db import SessionLocal, get_db
from ..deps import current_user, require_permission
from ..models import User

router = APIRouter(prefix="/api/admin/git", tags=["git"])
verwalten = require_permission("settings.manage")

NAME_OK = re.compile(r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+")


@router.get("", dependencies=[Depends(verwalten)])
def stand(db: DbSession = Depends(get_db)) -> dict:
    return git.stand(db)


@router.put("", dependencies=[Depends(verwalten)])
def einstellen(body: dict, request: Request, actor: User = Depends(current_user),
               db: DbSession = Depends(get_db)) -> dict:
    """Subdomain, Gruppen und Adresse von OTA speichern. Ist Git an, wird
    sofort nachgezogen (neue Subdomain: Container, Zertifikat, Keycloak)."""
    alt_domain = git.domain(db)
    if "domain" in body:
        name = str(body.get("domain") or "").strip().lower().rstrip(".")
        if name and not NAME_OK.fullmatch(name):
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                f"„{name}“ ist kein gültiger Name, z. B. git.firma.de.")
        settings_store.put(db, settings_store.GIT_DOMAIN, name)
    if "gruppen" in body:
        settings_store.put(db, settings_store.GIT_GRUPPEN,
                           [str(g) for g in body.get("gruppen") or []])
    if "ota_url" in body:
        url = str(body.get("ota_url") or "").strip().rstrip("/")
        if url and not url.startswith("https://"):
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "Die Adresse von OTA beginnt mit https://.")
        settings_store.put(db, settings_store.GIT_OTA_URL, url)
    neu_geschuetzt = False
    if "branchschutz" in body:
        eingabe = body.get("branchschutz") or {}
        regel = git.branchschutz(db)
        if "freigaben" in eingabe:
            try:
                freigaben = int(eingabe["freigaben"])
            except (TypeError, ValueError):
                freigaben = -1
            if not 0 <= freigaben <= 5:
                raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                    "Zwischen 0 und 5 Freigaben, bitte.")
            regel["freigaben"] = freigaben
        if "fuer_admins" in eingabe:
            regel["fuer_admins"] = bool(eingabe["fuer_admins"])
        if "an" in eingabe:
            neu_geschuetzt = bool(eingabe["an"]) and not regel["an"]
            regel["an"] = bool(eingabe["an"])
        settings_store.put(db, settings_store.GIT_BRANCHSCHUTZ, regel)
        audit.record(db, "git.branchschutz_eingestellt", actor=actor, request=request, **regel)
    audit.record(db, "git.eingestellt", actor=actor, request=request,
                 domain=git.domain(db), gruppen=len(git.gruppen_ids(db)))
    db.commit()

    if git.an(db):
        try:
            if git.domain(db) != alt_domain:
                git.einschalten(db)
            else:
                git.zugang_nachziehen(db)
                db.commit()
                git.konten_abgleichen(db)
        except (git.GitFehler, keycloak.KeycloakFehler) as exc:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
        if neu_geschuetzt:
            # Gleich beim Einschalten, nicht erst im nächsten Takt.
            try:
                ergebnis = git.branchschutz_setzen(db)
            except git.GitFehler as exc:
                raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
            return {**git.stand(db), "ergebnis": ergebnis}
    return git.stand(db)


def _einschalten() -> dict:
    with SessionLocal() as db:
        return git.einschalten(db)


@router.post("/an", dependencies=[Depends(verwalten)])
async def einschalten(request: Request, actor: User = Depends(current_user),
                      db: DbSession = Depends(get_db)) -> dict:
    if not git.domain(db):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Erst eine Subdomain eintragen.")
    if not settings_store.get(db, settings_store.GIT_OTA_URL):
        # Wie Browser OTA sehen — aus dieser Anfrage, wenn noch nichts steht.
        herkunft = request.headers.get("origin") or ""
        if herkunft.startswith("https://"):
            settings_store.put(db, settings_store.GIT_OTA_URL, herkunft.rstrip("/"))
            db.commit()
    try:
        ergebnis = await asyncio.to_thread(_einschalten)
    except (git.GitFehler, keycloak.KeycloakFehler) as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    audit.record(db, "git.an", actor=actor, request=request, domain=git.domain(db))
    db.commit()
    return {**git.stand(db), "ergebnis": ergebnis}


@router.post("/aus", dependencies=[Depends(verwalten)])
def ausschalten(request: Request, actor: User = Depends(current_user),
                db: DbSession = Depends(get_db)) -> dict:
    git.ausschalten(db)
    audit.record(db, "git.aus", actor=actor, request=request)
    db.commit()
    return git.stand(db)


@router.post("/abgleich", dependencies=[Depends(verwalten)])
def abgleichen(db: DbSession = Depends(get_db)) -> dict:
    if not git.an(db):
        raise HTTPException(status.HTTP_409_CONFLICT, "OTA-Git ist aus.")
    return git.konten_abgleichen(db)


# --------------------------------------------------------------------------
# Geheimnisse beim Push (git_geheimnisse.py)
# --------------------------------------------------------------------------

def _geheimnisse_stand(db: DbSession) -> dict:
    return {**git_geheimnisse.einstellungen(db), "git_an": git.an(db),
            "frist_tage": git_geheimnisse.FRIST_TAGE}


@router.get("/geheimnisse", dependencies=[Depends(verwalten)])
def geheimnisse_stand(db: DbSession = Depends(get_db)) -> dict:
    return _geheimnisse_stand(db)


@router.put("/geheimnisse", dependencies=[Depends(verwalten)])
async def geheimnisse_einstellen(body: dict, request: Request,
                                 actor: User = Depends(current_user),
                                 db: DbSession = Depends(get_db)) -> dict:
    try:
        e = git_geheimnisse.speichern(db, body)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    audit.record(db, "git.geheimnisse_eingestellt", actor=actor, request=request,
                 object_type="settings", object_id="git_geheimnisse", **e)
    db.commit()
    stand = _geheimnisse_stand(db)
    if git.an(db):
        # Gleich in Forgejo, nicht erst im nächsten Takt.
        try:
            stand["abgleich"] = await asyncio.to_thread(_geheimnisse_abgleichen)
        except HTTPException as exc:
            stand["abgleich"] = {"fehler": str(exc.detail)}
    return stand


def _geheimnisse_abgleichen() -> dict:
    with SessionLocal() as db:
        return git_geheimnisse.abgleichen(db)


@router.get("/geheimnisse/statistik", dependencies=[Depends(verwalten)])
def geheimnisse_statistik(tage: int = Query(30, ge=1, le=365),
                          db: DbSession = Depends(get_db)) -> dict:
    return {**git_geheimnisse.uebersicht(db, tage), **_geheimnisse_stand(db)}


@router.delete("/geheimnisse/statistik", dependencies=[Depends(verwalten)])
def geheimnisse_loeschen(request: Request, actor: User = Depends(current_user),
                         db: DbSession = Depends(get_db)) -> dict:
    weg = git_geheimnisse.alles_loeschen(db)
    audit.record(db, "git.geheimnisse_geloescht", actor=actor, request=request, zeilen=weg)
    db.commit()
    return {"zeilen": weg}
