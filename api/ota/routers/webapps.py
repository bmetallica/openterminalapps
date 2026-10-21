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

import logging
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

log = logging.getLogger("ota.webapps")

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
            "Es ist noch kein Ziel freigegeben. Trag unter Einstellungen → "
            "Anwendungen → Erlaubte Ziele ein, wohin Anwendungen ihre Anmeldung "
            "schicken dürfen — solange dort nichts steht, ist nichts erlaubt.",
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
            f"„{herkunft}“ steht nicht auf der Liste erlaubter Ziele "
            "(Einstellungen → Anwendungen). Wer sie ergänzt, entscheidet, wohin "
            "Anmeldedaten fliessen dürfen.",
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

    Dieselbe Regel wie beim Anmelden in Keycloak (`_zugang`): „für alle",
    oder eine gemeinsame Gruppe. **Ohne Gruppe sieht sie niemand** — bis zum
    2026-10-19 hiess das „alle"; der Bestand steht seitdem auf „für alle".
    """
    alle = db.scalars(select(WebApp).order_by(WebApp.sort_order, WebApp.name)).all()
    darf = user.is_admin or "anwendungen.verwalten" in user.permissions
    meine = {g.id for g in user.groups}
    return [
        _out(a) for a in alle
        if darf or (a.is_enabled and (a.fuer_alle or {g.id for g in a.groups} & meine))
    ]


def _nicht_verwaltet(app: WebApp) -> None:
    """Einträge, die OTA selbst führt (OTA-Git), ändert man dort, wo sie
    herkommen — sonst liefen Kachel und Dienst auseinander."""
    if app.verwaltet == "git":
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Diese Anwendung gehört zu OTA-Git. Ändern unter Einstellungen → Git.")


def _zugang(app: WebApp) -> None:
    """Traegt in Keycloak ein, wer sich anmelden darf. Wirft `KeycloakFehler`."""
    keycloak.anwendung_zugang(app.client_id, sorted(g.name for g in app.groups),
                              bool(app.fuer_alle))


def zugang_alle() -> None:
    """Alle Anwendungen nachziehen — beim Start, und wenn sich Gruppen aendern.
    Eine, die scheitert, haelt die anderen nicht auf."""
    from ..db import SessionLocal

    with SessionLocal() as db:
        for app in db.scalars(select(WebApp)).all():
            try:
                _zugang(app)
            except Exception as exc:  # noqa: BLE001
                log.warning("Zugang zu %s nicht eingetragen: %s", app.slug, exc)


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
        fuer_alle=bool(body.fuer_alle),
    )
    app.groups = list(db.scalars(select(Group).where(Group.id.in_(body.group_ids or []))).all())
    try:
        _zugang(app)
    except keycloak.KeycloakFehler as exc:
        # Ohne eingetragenen Zugang waere die Anwendung offen fuer jeden mit
        # einem Konto — genau das, was die Gruppen verhindern sollen.
        keycloak.client_entfernen(client_id)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            f"Der Zugang liess sich in Keycloak nicht eintragen: {exc}") from exc
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
    _nicht_verwaltet(app)

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
    if body.fuer_alle is not None:
        app.fuer_alle = body.fuer_alle
    try:
        _zugang(app)
    except keycloak.KeycloakFehler as exc:
        db.rollback()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            f"Der Zugang liess sich in Keycloak nicht eintragen: {exc}") from exc

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
    _nicht_verwaltet(app)
    try:
        keycloak.anwendung_fluss_entfernen(app.client_id)
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
    _nicht_verwaltet(app)
    try:
        neu = keycloak.client_neues_geheimnis(app.client_id)
    except keycloak.KeycloakFehler as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    audit.record(db, "webapp.secret_rotated", actor=actor, object_type="webapp",
                 object_id=app.slug, request=request)
    db.commit()
    return {"client_secret": neu}
