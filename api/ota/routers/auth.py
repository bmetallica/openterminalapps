from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pyotp
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from .. import audit
from ..config import settings
from ..db import get_db
from ..deps import current_user, set_session_cookie
from ..models import User
from .. import settings_store
from ..schemas import LoginIn, MeOut, PasswordChangeIn
from ..security import hash_password, password_problem, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

LOCK_AFTER = 8
LOCK_MINUTES = 15




@router.post("/login")
def login(
    body: LoginIn,
    request: Request,
    response: Response,
    db: DbSession = Depends(get_db),
) -> MeOut:
    user = db.scalar(select(User).where(User.username == body.username))

    # Immer dieselbe Meldung, egal ob Nutzer oder Passwort falsch war —
    # sonst laesst sich herausfinden, welche Konten existieren.
    invalid = HTTPException(status.HTTP_401_UNAUTHORIZED, "Benutzername oder Passwort ist falsch.")

    if user is None:
        raise invalid

    now = datetime.now(timezone.utc)
    if user.locked_until and user.locked_until > now:
        rest = int((user.locked_until - now).total_seconds() // 60) + 1
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Zu viele Fehlversuche. Bitte in {rest} Minuten erneut versuchen.",
        )

    if not user.is_active or user.is_locked:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Dieses Konto ist deaktiviert.")

    if not verify_password(body.password, user.password_hash):
        user.failed_logins += 1
        if user.failed_logins >= LOCK_AFTER:
            user.locked_until = now + timedelta(minutes=LOCK_MINUTES)
            user.failed_logins = 0
        audit.record(db, "login.failed", actor=user, request=request)
        db.commit()
        raise invalid

    if user.totp_secret:
        if not body.totp:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bitte den Code aus deiner App eingeben.")
        if not pyotp.TOTP(user.totp_secret).verify(body.totp, valid_window=1):
            audit.record(db, "login.totp_failed", actor=user, request=request)
            db.commit()
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Der Code stimmt nicht.")

    user.failed_logins = 0
    user.locked_until = None
    user.last_login_at = now
    audit.record(db, "login.ok", actor=user, request=request)
    db.commit()

    set_session_cookie(response, user, settings_store.idle_minutes(db))
    return _me(user)


@router.post("/logout")
def logout(response: Response) -> dict[str, str]:
    response.delete_cookie(settings().cookie_name, path="/")
    return {"status": "abgemeldet"}


def _me(user: User) -> MeOut:
    return MeOut(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        is_admin=user.is_admin,
        permissions=sorted(user.permissions),
        groups=sorted(g.slug for g in user.groups),
        locale=user.locale,
        must_change_password=user.must_change_password,
    )


@router.get("/me")
def me(user: User = Depends(current_user)) -> MeOut:
    return _me(user)


@router.post("/password")
def change_password(
    body: PasswordChangeIn,
    request: Request,
    response: Response,
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> dict[str, str]:
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Das aktuelle Passwort stimmt nicht.")

    problem = password_problem(body.new_password)
    if problem:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, problem)

    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    # Alle anderen Sitzungen dieses Nutzers ungueltig machen.
    user.token_epoch += 1
    audit.record(db, "password.changed", actor=user, request=request)
    db.commit()

    # Die eigene Sitzung bleibt bestehen, sonst wirft der Wechsel den Nutzer raus.
    set_session_cookie(response, user, settings_store.idle_minutes(db))
    return {"status": "Passwort geändert"}
