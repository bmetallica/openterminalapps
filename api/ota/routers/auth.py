from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from .. import audit
from ..config import settings
from ..db import get_db
from ..deps import current_user, set_session_cookie
from ..models import User
from .. import settings_store, totp
from ..schemas import (
    LocaleIn, LoginIn, MeOut, PasswordChangeIn, PasswordIn,
    TotpActivateIn, TotpCodesOut, TotpDisableIn, TotpSetupOut,
)
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

        # Ein Rueckfallcode statt des Zeitcodes: der Weg fuer ein verlorenes
        # Telefon. Erkannt an der Form, damit nicht jede fehlgeschlagene
        # Anmeldung beide Wege durchprobiert — jeder Versuch waere sonst ein
        # Argon2-Durchlauf je gespeichertem Code.
        if totp.looks_like_recovery(body.totp):
            rest = totp.redeem(user.totp_recovery or [], body.totp)
            if rest is None:
                audit.record(db, "login.totp_failed", actor=user, request=request)
                db.commit()
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Der Code stimmt nicht.")
            user.totp_recovery = rest
            audit.record(db, "login.recovery_used", actor=user, request=request,
                         remaining=len(rest))
        elif not totp.verify(user.totp_secret, body.totp):
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
        totp_enabled=bool(user.totp_secret),
        recovery_left=len(user.totp_recovery or []),
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


# --------------------------------------------------------------------------
# Zweiter Faktor (siehe ota/totp.py)
# --------------------------------------------------------------------------

@router.post("/totp/setup", response_model=TotpSetupOut)
def totp_setup(user: User = Depends(current_user)) -> TotpSetupOut:
    """Erzeugt ein Geheimnis und zeigt es als Code zum Abscannen.

    Gespeichert wird hier noch **nichts**. Erst der naechste Schritt beweist
    mit einem gueltigen Zeitcode, dass die App das Geheimnis wirklich hat —
    sonst schaltete man sich mit einem Tippfehler aus.
    """
    if user.totp_secret:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Der zweite Faktor ist schon eingerichtet. Schalte ihn erst ab.",
        )
    secret = totp.new_secret()
    uri = totp.provisioning_uri(secret, user.username)
    return TotpSetupOut(secret=secret, uri=uri, qr_svg=totp.qr_svg(uri))


@router.post("/totp/activate", response_model=TotpCodesOut)
def totp_activate(body: TotpActivateIn, request: Request,
                  user: User = Depends(current_user),
                  db: DbSession = Depends(get_db)) -> TotpCodesOut:
    """Schaltet den zweiten Faktor ein — nach bestandener Probe."""
    if user.totp_secret:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Der zweite Faktor ist schon eingerichtet.")
    if not totp.verify(body.secret, body.code):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Der Code stimmt nicht. Stimmt die Uhrzeit auf dem Telefon?",
        )

    plain, hashed = totp.new_recovery_codes()
    user.totp_secret = body.secret
    user.totp_recovery = hashed
    audit.record(db, "totp.enabled", actor=user, object_type="user",
                 object_id=user.username, request=request)
    db.commit()
    return TotpCodesOut(codes=plain)


@router.post("/totp/recovery", response_model=TotpCodesOut)
def totp_new_codes(body: PasswordIn, request: Request,
                   user: User = Depends(current_user),
                   db: DbSession = Depends(get_db)) -> TotpCodesOut:
    """Erzeugt neue Rueckfallcodes. Die alten gelten danach nicht mehr."""
    if not user.totp_secret:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Der zweite Faktor ist nicht eingerichtet.")
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Das Passwort stimmt nicht.")

    plain, hashed = totp.new_recovery_codes()
    user.totp_recovery = hashed
    audit.record(db, "totp.recovery_renewed", actor=user, object_type="user",
                 object_id=user.username, request=request)
    db.commit()
    return TotpCodesOut(codes=plain)


@router.delete("/totp")
def totp_disable(body: TotpDisableIn, request: Request,
                 user: User = Depends(current_user),
                 db: DbSession = Depends(get_db)) -> dict[str, str]:
    """Schaltet den zweiten Faktor ab.

    Verlangt Passwort **und** einen gueltigen Code. Wer nur das Passwort hat —
    etwa an einem unbeaufsichtigten Rechner —, soll den zweiten Faktor nicht
    entfernen koennen; sonst waere er keiner.
    """
    if not user.totp_secret:
        return {"status": "war nicht eingerichtet"}
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Das Passwort stimmt nicht.")

    ok = totp.verify(user.totp_secret, body.code)
    if not ok and totp.looks_like_recovery(body.code):
        ok = totp.redeem(user.totp_recovery or [], body.code) is not None
    if not ok:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Der Code stimmt nicht.")

    user.totp_secret = None
    user.totp_recovery = []
    audit.record(db, "totp.disabled", actor=user, object_type="user",
                 object_id=user.username, request=request)
    db.commit()
    return {"status": "abgeschaltet"}


@router.put("/locale")
def set_locale(body: LocaleIn, user: User = Depends(current_user),
               db: DbSession = Depends(get_db)) -> MeOut:
    """Merkt sich die Sprache am Konto.

    Der Umschalter in der Leiste wirkt sofort und liegt im Browser. Hier
    landet er zusaetzlich am Konto, damit er an einem anderen Rechner wieder
    gilt — ohne dass jemand ihn dort erneut sucht.
    """
    if body.locale not in ("de", "en"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Diese Sprache gibt es nicht.")
    user.locale = body.locale
    db.commit()
    return _me(user)
