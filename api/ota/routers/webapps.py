"""Fremde Web-Anwendungen im Katalog (auth-roadmap.md, Etappe D).

OTA betreibt sie nicht. Es kennt sie, entscheidet, wer sie sieht, und hat in
Keycloak den OIDC-Client dafür angelegt. Was jemand *innerhalb* der Anwendung
darf, entscheidet die Anwendung; OTA baut ihr Rechtemodell nicht nach.

**Warum das ein eigenes Recht hat.** Eine Anwendung anzulegen heisst, in
Keycloak einen Client zu erzeugen — und darin steht eine Zeile, die alles
entscheidet:

    Redirect-URI    https://ai.firma.de/oauth/oidc/callback

Dorthin schickt Keycloak nach der Anmeldung den Autorisierungs-Code. Wer die
URI bestimmt, bestimmt, wohin die Identität der Nutzer fliesst. Im Protokoll
sieht das aus wie „hat eine Anwendung hinzugefügt"; es ist aber kategorisch
etwas anderes als ein freigegebenes Image. Das eine bleibt auf dem Rechner,
das andere leitet Identitäten nach draussen.

Deshalb zwei Schlösser (§5d), und sie sichern gegen Verschiedenes:

* das Recht ``anwendungen.verwalten`` gegen den, der es nicht haben soll,
* die Liste erlaubter Herkünfte gegen den Tippfehler dessen, der es hat.

Der zweite Fall ist der wahrscheinlichere.
"""

from __future__ import annotations

import re
import uuid
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from .. import audit, keycloak, settings_store
from ..db import get_db
from ..deps import current_user, require_permission
from ..models import Group, User, WebApp
from ..schemas import WebAppIn, WebAppOut

router = APIRouter(prefix="/api/webapps", tags=["webapps"])
manage = require_permission("anwendungen.verwalten")

SLUG = re.compile(r"[^a-z0-9]+")


def _slug(name: str) -> str:
    return SLUG.sub("-", name.strip().lower()).strip("-")[:64] or "anwendung"


def _erlaubt(db: DbSession, ziel: str) -> None:
    """Darf ein Token dorthin? Geprüft **hier**, nicht im Formular.

    Eine Prüfung, die nur im Browser stattfindet, ist keine.
    """
    erlaubt = settings_store.allowed_origins(db)
    if not erlaubt:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Es ist noch kein Ziel freigegeben. Trag unter Einstellungen ein, "
            "wohin Anwendungen ihre Anmeldung schicken dürfen — solange dort "
            "nichts steht, ist nichts erlaubt.",
        )

    teil = urlparse(ziel)
    if teil.scheme not in ("http", "https") or not teil.netloc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Das ist keine vollständige Adresse.")
    # Kein Platzhalter im Pfad. Keycloak erlaubt `*` in Redirect-URIs; OTA
    # reicht das nicht durch — ein `*` machte aus einem erlaubten Ziel eine
    # ganze Familie von Zielen.
    if "*" in ziel:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Platzhalter sind in der Adresse nicht erlaubt.")

    herkunft = f"{teil.scheme}://{teil.netloc}"
    if herkunft not in erlaubt:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"„{herkunft}“ steht nicht auf der Liste erlaubter Ziele. "
            "Wer sie ergänzt, entscheidet, wohin Anmeldedaten fliessen dürfen.",
        )


def _out(app: WebApp, geheimnis: str | None = None) -> WebAppOut:
    daten = WebAppOut.model_validate(app)
    daten.group_ids = [g.id for g in app.groups]
    daten.client_secret = geheimnis
    return daten


@router.get("")
def liste(user: User = Depends(current_user),
          db: DbSession = Depends(get_db)) -> list[WebAppOut]:
    """Was dieser Mensch sehen darf.

    Ohne Gruppenzuweisung ist eine Anwendung für alle sichtbar — dieselbe
    Regel wie bei den Arbeitsplätzen.
    """
    alle = db.scalars(select(WebApp).order_by(WebApp.sort_order, WebApp.name)).all()
    darf = user.is_admin or "anwendungen.verwalten" in user.permissions
    meine = {g.id for g in user.groups}
    return [
        _out(a) for a in alle
        if darf or (a.is_enabled and (not a.groups or {g.id for g in a.groups} & meine))
    ]


@router.post("", dependencies=[Depends(manage)], status_code=status.HTTP_201_CREATED)
def anlegen(body: WebAppIn, request: Request,
            actor: User = Depends(current_user),
            db: DbSession = Depends(get_db)) -> WebAppOut:
    """Anwendung anlegen und den Client in Keycloak dazu.

    Das Geheimnis kommt **einmal** zurück, hier in der Antwort. Danach steht
    es nur noch in Keycloak.
    """
    _erlaubt(db, body.redirect_uri)

    slug = _slug(body.slug or body.name)
    if db.scalar(select(WebApp).where(WebApp.slug == slug)):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"„{slug}“ gibt es schon.")

    client_id = f"ota-app-{slug}"
    try:
        geheimnis = keycloak.client_anlegen(client_id, body.name, body.redirect_uri)
    except keycloak.KeycloakFehler as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    app = WebApp(
        slug=slug, name=body.name, description=body.description, icon=body.icon,
        url=body.url, redirect_uri=body.redirect_uri, client_id=client_id,
        is_enabled=body.is_enabled, sort_order=body.sort_order,
    )
    app.groups = list(db.scalars(select(Group).where(Group.id.in_(body.group_ids or []))).all())
    db.add(app)
    audit.record(db, "webapp.created", actor=actor, object_type="webapp",
                 object_id=slug, request=request, redirect=body.redirect_uri)
    db.commit()
    db.refresh(app)
    return _out(app, geheimnis)


@router.put("/{app_id}", dependencies=[Depends(manage)])
def aendern(app_id: uuid.UUID, body: WebAppIn, request: Request,
            actor: User = Depends(current_user),
            db: DbSession = Depends(get_db)) -> WebAppOut:
    app = db.get(WebApp, app_id)
    if not app:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Anwendung nicht gefunden")

    if body.redirect_uri != app.redirect_uri:
        # Die heikelste Änderung überhaupt: Sie verlegt, wohin Token fliessen.
        _erlaubt(db, body.redirect_uri)
        try:
            keycloak.client_entfernen(app.client_id)
            keycloak.client_anlegen(app.client_id, body.name, body.redirect_uri)
        except keycloak.KeycloakFehler as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
        audit.record(db, "webapp.redirect_changed", actor=actor, object_type="webapp",
                     object_id=app.slug, request=request,
                     alt=app.redirect_uri, neu=body.redirect_uri)

    app.name, app.description, app.icon = body.name, body.description, body.icon
    app.url, app.redirect_uri = body.url, body.redirect_uri
    app.is_enabled, app.sort_order = body.is_enabled, body.sort_order
    if body.group_ids is not None:
        app.groups = list(db.scalars(select(Group).where(Group.id.in_(body.group_ids))).all())

    audit.record(db, "webapp.updated", actor=actor, object_type="webapp",
                 object_id=app.slug, request=request)
    db.commit()
    db.refresh(app)
    return _out(app)


@router.delete("/{app_id}", dependencies=[Depends(manage)])
def entfernen(app_id: uuid.UUID, request: Request,
              actor: User = Depends(current_user),
              db: DbSession = Depends(get_db)) -> dict:
    app = db.get(WebApp, app_id)
    if not app:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Anwendung nicht gefunden")
    try:
        keycloak.client_entfernen(app.client_id)
    except keycloak.KeycloakFehler:
        # Der Client in Keycloak ist womöglich schon weg. Das ist kein Grund,
        # die Kachel stehenzulassen.
        pass
    slug = app.slug
    db.delete(app)
    audit.record(db, "webapp.deleted", actor=actor, object_type="webapp",
                 object_id=slug, request=request)
    db.commit()
    return {"status": "entfernt"}


@router.post("/{app_id}/geheimnis", dependencies=[Depends(manage)])
def neues_geheimnis(app_id: uuid.UUID, request: Request,
                    actor: User = Depends(current_user),
                    db: DbSession = Depends(get_db)) -> dict:
    """Ein neues Client-Geheimnis. Das alte gilt danach nicht mehr."""
    app = db.get(WebApp, app_id)
    if not app:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Anwendung nicht gefunden")
    try:
        neu = keycloak.client_neues_geheimnis(app.client_id)
    except keycloak.KeycloakFehler as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    audit.record(db, "webapp.secret_rotated", actor=actor, object_type="webapp",
                 object_id=app.slug, request=request)
    db.commit()
    return {"client_secret": neu}
