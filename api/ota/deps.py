"""Abhaengigkeiten fuer Authentifizierung und Rechte.

Die Rechtepruefung passiert hier — serverseitig, an jedem Endpunkt.
Das Frontend blendet Menues aus, aber das ist Komfort, nicht Sicherheit.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session as DbSession

from .config import settings
from .db import get_db
from .models import User
from .security import as_uuid, read_token


def current_user(request: Request, db: DbSession = Depends(get_db)) -> User:
    token = request.cookies.get(settings().cookie_name)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nicht angemeldet")

    claims = read_token(token)
    if not claims or claims.get("typ") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sitzung abgelaufen")

    uid = as_uuid(claims.get("sub", ""))
    user = db.get(User, uid) if uid else None
    if not user or not user.is_active or user.is_locked:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Konto nicht verfügbar")

    # Erlaubt das serverseitige Ungueltigmachen aller Sitzungen eines Nutzers.
    if claims.get("epoch") != user.token_epoch:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sitzung wurde beendet")

    return user


def require_permission(*keys: str):
    """Erzeugt eine Abhaengigkeit, die eines der genannten Rechte verlangt."""

    def check(user: User = Depends(current_user)) -> User:
        if user.is_admin or set(keys) & user.permissions:
            return user
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Für diese Aktion fehlen dir die Rechte.",
        )

    return check


require_admin = require_permission("admin")
