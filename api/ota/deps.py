"""Abhaengigkeiten fuer Authentifizierung und Rechte.

Die Rechtepruefung passiert hier — serverseitig, an jedem Endpunkt.
Das Frontend blendet Menues aus, aber das ist Komfort, nicht Sicherheit.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session as DbSession

from . import keycloak, settings_store
from .config import settings
from .db import get_db
from .models import User
from .security import as_uuid, make_token, read_token


def set_session_cookie(response: Response, user: User, minutes: int) -> None:
    s = settings()
    response.set_cookie(
        s.cookie_name,
        make_token(user, "access", minutes=minutes),
        httponly=True,
        secure=s.cookie_secure,
        samesite="lax",
        max_age=minutes * 60,
        path="/",
    )


log = logging.getLogger("ota.deps")

# Das Refresh-Token der Keycloak-Anmeldung, mit dem Zeitpunkt der letzten
# Auffrischung davor: "<unixzeit>.<token>". Im Browser und nicht in der
# Datenbank — es gehört zu dieser einen Anmeldung auf diesem einen Gerät,
# und so endet es mit ihr. httponly, wie das Sitzungscookie.
KC_WACH_COOKIE = "ota_kcwach"
KC_WACH_PFAD = "/api"
# Wie oft Keycloak hört, dass jemand noch da ist. Weit unter jeder Frist,
# die man einstellen kann (die kleinste ist 30 Minuten).
KC_WACH_SEKUNDEN = 300


def set_kc_wach(response: Response, refresh_token: str, minutes: int) -> None:
    s = settings()
    response.set_cookie(
        KC_WACH_COOKIE, f"{int(time.time())}.{refresh_token}",
        httponly=True, secure=s.cookie_secure, samesite="lax",
        max_age=minutes * 60, path=KC_WACH_PFAD,
    )


def clear_kc_wach(response: Response) -> None:
    """Bei jeder Anmeldung ohne Keycloak: Sonst hielte das Cookie einer
    früheren Anmeldung im selben Browser eine fremde Sitzung wach."""
    response.delete_cookie(KC_WACH_COOKIE, path=KC_WACH_PFAD)


def _keycloak_wach(request: Request, response: Response, db: DbSession) -> None:
    """Hält die Keycloak-Sitzung wach, solange OTAs Sitzung lebt — und
    beendet OTAs Sitzung, wenn Keycloaks weg ist.

    Eine Uhr statt zwei (2026-10-08): Vorher lief Keycloaks SSO-Sitzung nach
    30 Minuten ohne Kontakt ab, OTAs nach acht Stunden ohne Arbeit. Dazwischen
    war man in OTA angemeldet, aber eine fremde Anwendung zeigte die
    Anmeldemaske. Antwortet Keycloak nicht, bleibt alles, wie es ist, und es
    wird beim nächsten Mal wieder versucht.
    """
    roh = request.cookies.get(KC_WACH_COOKIE) or ""
    stempel, _, refresh = roh.partition(".")
    if not refresh or not stempel.isdigit():
        return
    if time.time() - int(stempel) < KC_WACH_SEKUNDEN:
        return
    minutes = settings_store.idle_minutes(db)
    try:
        neu = keycloak.auffrischen(refresh)
    except keycloak.SitzungWeg:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            "Die zentrale Anmeldung ist beendet") from None
    except keycloak.KeycloakFehler as exc:
        log.info("Keycloak-Sitzung nicht aufgefrischt: %s", exc)
        set_kc_wach(response, refresh, minutes)   # nur den Zeitpunkt
        return
    set_kc_wach(response, str(neu.get("refresh_token") or refresh), minutes)


def current_user(
    request: Request,
    response: Response,
    db: DbSession = Depends(get_db),
) -> User:
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

    _keycloak_wach(request, response, db)
    _renew(response, user, db, claims)
    return user


def _renew(response: Response, user: User, db: DbSession, claims: dict) -> None:
    """Schiebt die Anmeldefrist nach vorn — die Sitzung ist rollend.

    Ohne das lief die Anmeldung nach einer festen Zeit ab, egal ob jemand
    gerade arbeitete: Man sass in einer Session und wurde mitten im Tippen auf
    den Anmeldebildschirm geworfen. Gemeint war eine Frist fuer *Untaetigkeit*,
    und genau die ist es jetzt.

    Erneuert wird erst in der zweiten Haelfte der Laufzeit. Bei jedem Request
    ein neues Merkmal auszustellen waere Verschwendung — das Dashboard fragt im
    15-Sekunden-Takt nach.
    """
    minutes = settings_store.idle_minutes(db)
    exp = claims.get("exp")
    iat = claims.get("iat")
    if not isinstance(exp, int) or not isinstance(iat, int):
        return
    now = datetime.now(timezone.utc).timestamp()
    if now < iat + (exp - iat) / 2:
        return
    set_session_cookie(response, user, minutes)


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
