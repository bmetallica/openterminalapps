"""Endpunkte, die nur Traefik aufruft — nie der Browser direkt."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session as DbSession

from ..config import settings
from ..db import get_db
from ..models import Session as SessionModel, User
from ..security import as_uuid, may_attach_to_session, read_token

router = APIRouter(prefix="/api/internal", tags=["internal"])

_SESSION_PATH = re.compile(r"^/s/([0-9a-fA-F-]{36})(/|$)")


@router.get("/authz")
def authz(request: Request, db: DbSession = Depends(get_db)) -> Response:
    """forwardAuth fuer Traefik.

    Wird vor JEDEM Request auf /s/<id>/... aufgerufen, auch vor dem
    WebSocket-Handshake. Prueft, ob der Cookie zu einem Nutzer gehoert, dem
    diese Session gehoert. Fremde Sessions ergeben 403 — auch fuer jemanden
    mit `sessions.view_all`, siehe `may_attach_to_session`.
    """
    uri = request.headers.get("x-forwarded-uri", "")
    match = _SESSION_PATH.match(uri)
    if not match:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Kein gültiger Session-Pfad")

    session_id = as_uuid(match.group(1))
    if session_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Ungültige Session")

    token = request.cookies.get(settings().cookie_name)
    claims = read_token(token) if token else None
    if not claims or claims.get("typ") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nicht angemeldet")

    user = db.get(User, as_uuid(claims.get("sub", "")))
    if not user or not user.is_active or user.is_locked:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Konto nicht verfügbar")
    if claims.get("epoch") != user.token_epoch:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sitzung wurde beendet")

    sess = db.get(SessionModel, session_id)
    # Bewusst nicht `owns_session`: Das Recht, alle Sessions zu *sehen*, ist
    # nicht das Recht, an einem fremden Bildschirm zu sitzen.
    if not sess or not may_attach_to_session(sess, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Diese Session gehört dir nicht")

    return Response(status_code=status.HTTP_200_OK)


@router.api_route("/session-unavailable", methods=["GET", "POST", "HEAD"])
def session_unavailable() -> Response:
    """Antwort, wenn ein Session-Pfad zu keiner laufenden Session gehoert.

    Erreichbar nur ueber den Schutzwall in der Traefik-Konfiguration, und
    auch dort erst nach bestandener Anmeldung. Ohne diesen Endpunkt fiele
    ein solcher Pfad auf die Weboberflaeche durch und antwortete mit 200.
    """
    return Response(
        status_code=status.HTTP_410_GONE,
        media_type="text/html; charset=utf-8",
        content=(
            "<!doctype html><meta charset='utf-8'>"
            "<title>Sitzung nicht verfügbar</title>"
            "<style>body{font-family:system-ui,sans-serif;background:#0B1315;"
            "color:#E6EDEC;display:grid;place-items:center;height:100vh;margin:0}"
            "div{max-width:26rem;text-align:center;line-height:1.6}"
            "a{color:#EADFCB}</style>"
            "<div><h1>Diese Sitzung läuft nicht mehr</h1>"
            "<p>Sie wurde beendet oder ist abgelaufen. Deine Dateien sind "
            "davon nicht betroffen.</p>"
            "<p><a href='/'>Zurück zum Dashboard</a></p></div>"
        ),
    )
