from __future__ import annotations

import logging

import secrets
from datetime import datetime, timedelta, timezone

import jwt

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from .. import agent_client, audit, directory, identity, kcidentity, keycloak
from ..config import settings
from ..db import get_db
from ..deps import current_user, set_session_cookie
from ..models import User
from .. import settings_store, totp
from ..schemas import (
    LocaleIn, LoginIn, MeOut, OidcTokenIn, PasswordChangeIn, PasswordIn,
    TotpActivateIn, TotpCodesOut, TotpDisableIn, TotpSetupOut,
)
from ..security import hash_password, needs_totp, password_problem, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])
log = logging.getLogger("ota.auth")

LOCK_AFTER = 8
LOCK_MINUTES = 15

# Ein gueltiger Argon2-Hash ohne zugehoeriges Passwort. Er dient nur dazu,
# einen Anmeldeversuch fuer ein Konto, das es nicht gibt, genauso lange
# dauern zu lassen wie einen fuer eines, das es gibt.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(32))




def _from_directory(db: DbSession, cfg, body: LoginIn, request: Request) -> User | None:
    """Erster Anmeldeversuch eines Menschen, den OTA noch nicht kennt.

    Erst pruefen lassen, dann anlegen. Andersherum entstuende bei jedem
    Tippfehler im Benutzernamen ein Konto.
    """
    try:
        person = directory.authenticate(cfg, body.username, body.password)
    except directory.DirectoryError as exc:
        log.warning("Verzeichnis-Anmeldung fehlgeschlagen: %s", exc)
        return None
    if person is None:
        return None

    user = identity.adopt(db, cfg, person)
    if user is None:
        # Der Name gehoert einem lokalen Konto. Das Verzeichnis bekommt ihn
        # nicht — und der Vorgang gehoert ins Protokoll, denn er sieht von
        # aussen aus wie ein falsches Passwort.
        audit.record(db, "login.directory_name_taken", actor=None,
                     request=request, username=body.username)
        db.commit()
        return None

    audit.record(db, "user.created_from_directory", actor=user,
                 object_type="user", object_id=user.username, request=request,
                 dn=person.dn, groups=len(user.groups))
    db.commit()
    return user


def _check_directory(db: DbSession, cfg, user: User, body: LoginIn,
                     request: Request, now: datetime) -> bool:
    """Prueft das Passwort eines Verzeichniskontos und frischt es auf."""
    if cfg is None:
        log.warning("Konto %s gehoert zum Verzeichnis, aber die Anbindung ist "
                    "abgeschaltet.", user.username)
        return False
    try:
        person = directory.authenticate(cfg, user.username, body.password)
    except directory.DirectoryError as exc:
        log.warning("Verzeichnis nicht erreichbar: %s", exc)
        audit.record(db, "login.directory_unreachable", actor=user, request=request)
        db.commit()
        return False

    if person is None:
        user.failed_logins += 1
        if user.failed_logins >= LOCK_AFTER:
            user.locked_until = now + timedelta(minutes=LOCK_MINUTES)
            user.failed_logins = 0
        audit.record(db, "login.failed", actor=user, request=request)
        db.commit()
        return False

    # Bei jeder Anmeldung auf den Stand des Verzeichnisses bringen. Das ist
    # der Grund, warum der naechtliche Abgleich keine Voraussetzung ist:
    # Wessen Gruppen sich aendern, merkt es beim naechsten Anmelden.
    identity.refresh(db, cfg, user, person)
    return True


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

    # Wo dieses Passwort geprueft wird, entscheidet das Konto — nicht die
    # Anfrage und nicht das Verzeichnis. Ein lokales Konto wird lokal
    # geprueft, auch wenn im Verzeichnis ein gleichnamiger Eintrag steht.
    # Ohne diese Regel koennte jeder, der dort einen Eintrag anlegen darf,
    # das Konto des ersten Administrators uebernehmen (identity.py).
    dir_cfg = identity.active(db)
    weg = identity.where_to_check(user, dir_cfg)

    if user is None:
        if weg == identity.LDAP and dir_cfg is not None:
            user = _from_directory(db, dir_cfg, body, request)
            if user is None:
                verify_password(body.password, _DUMMY_HASH)
                raise invalid
        else:
            # Die Meldung ist gleich, die Dauer muss es auch sein: Ohne diesen
            # Leerlauf antwortet ein unbekannter Name in Mikrosekunden und ein
            # bekannter erst nach einem Argon2-Durchlauf. Damit liesse sich die
            # Nutzerliste abfragen, ohne je hereinzukommen.
            verify_password(body.password, _DUMMY_HASH)
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

    if weg == identity.LDAP and user.auth_provider == identity.LDAP:
        # Das Verzeichnis entscheidet, nicht wir. Faellt es aus, kommt dieses
        # Konto nicht herein — und das ist richtig so: Ein Ausweichen auf
        # einen lokalen Hash waere ein zweiter Weg an der Stelle, an der es
        # genau einen geben soll.
        if not _check_directory(db, dir_cfg, user, body, request, now):
            raise invalid
    elif not verify_password(body.password, user.password_hash):
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

        # Fehlversuche beim zweiten Faktor zaehlen genauso wie beim Passwort.
        # Ohne das war der zweite Faktor bei bekanntem Passwort beliebig oft
        # ratbar: sechs Ziffern, drei davon zu jedem Zeitpunkt gueltig
        # (`valid_window=1`) — mit genug Versuchen eine Frage von Minuten,
        # nicht von Jahren. Dieselbe Luecke galt fuer die Rueckfallcodes.
        def _totp_failed(kind: str):
            user.failed_logins += 1
            if user.failed_logins >= LOCK_AFTER:
                user.locked_until = now + timedelta(minutes=LOCK_MINUTES)
                user.failed_logins = 0
            audit.record(db, kind, actor=user, request=request)
            db.commit()
            return HTTPException(status.HTTP_401_UNAUTHORIZED, "Der Code stimmt nicht.")

        # Ein Rueckfallcode statt des Zeitcodes: der Weg fuer ein verlorenes
        # Telefon. Erkannt an der Form, damit nicht jede fehlgeschlagene
        # Anmeldung beide Wege durchprobiert — jeder Versuch waere sonst ein
        # Argon2-Durchlauf je gespeichertem Code.
        if totp.looks_like_recovery(body.totp):
            rest = totp.redeem(user.totp_recovery or [], body.totp)
            if rest is None:
                raise _totp_failed("login.recovery_failed")
            user.totp_recovery = rest
            audit.record(db, "login.recovery_used", actor=user, request=request,
                         remaining=len(rest))
        elif not totp.verify(user.totp_secret, body.totp):
            raise _totp_failed("login.totp_failed")

    user.failed_logins = 0
    user.locked_until = None
    user.last_login_at = now
    audit.record(db, "login.ok", actor=user, request=request)
    db.commit()

    set_session_cookie(response, user, settings_store.idle_minutes(db))
    return _me(user)


@router.get("/storage")
def my_storage(
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> dict:
    """Wie voll das eigene Zuhause ist.

    Bewusst ein eigener Aufruf und nicht Teil von `/me`: `/me` laeuft bei
    jedem Seitenaufbau, und eine Messung ueber ein gewachsenes Profil dauert
    beim ersten Mal. Das Dashboard holt das hier nach, wenn es steht.

    Der Wert kommt aus dem Puffer des Agents (zehn Minuten). Wer gerade
    aufgeraeumt hat, sieht das Ergebnis also nicht sofort — dafuer wartet
    niemand beim Anmelden.
    """
    quota = settings_store.profile_quota_bytes(db)
    try:
        used = int(agent_client.profile_usage(user.username).get("bytes", 0))
    except Exception:  # noqa: BLE001 — eine Anzeige darf nichts umwerfen
        return {"bytes": 0, "quota_bytes": quota, "percent": None, "level": "unbekannt"}

    percent = round(used / quota * 100, 1) if quota else None
    # Drei Stufen statt einer Zahl, weil die Zahl allein niemandem sagt, ob
    # sie ein Problem ist. Warnung ab 80 %, wie in plan.md §11.3 vorgesehen.
    if percent is None:
        level = "ohne Grenze"
    elif percent >= 100:
        level = "voll"
    elif percent >= 80:
        level = "knapp"
    else:
        level = "in Ordnung"
    return {"bytes": used, "quota_bytes": quota, "percent": percent, "level": level}


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
        must_setup_totp=needs_totp(user),
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


# --------------------------------------------------------------------------
# Anmeldung über Keycloak (auth-roadmap.md, Etappe B)
#
# Zwei Wege herein, und beide enden an derselben Stelle: einem OTA-Cookie.
#
#   /oidc/token   Ein bereits vorhandenes Keycloak-Token wird als Beweis
#                 vorgelegt. Das ist der Weg für alles ohne Browser — die
#                 Prüfreihen, später ein Kommandozeilenwerkzeug.
#   /oidc/start   Der Weg im Browser: hin zu Keycloak, mit Code zurück.
#                 (folgt)
#
# **Warum überhaupt ein eigenes Cookie und nicht das Keycloak-Token?** Vor
# jedem Session-Pfad steht Traefiks forwardAuth, auch vor dem
# WebSocket-Upgrade. Ein Upgrade lässt sich nicht nach Keycloak umleiten, und
# ein Stream, der alle paar Minuten einen Anmeldefluss durchliefe, wäre
# keiner. Keycloak steht an der Haustür; dahinter gilt OTAs Cookie (§3).
# --------------------------------------------------------------------------


@router.post("/oidc/token")
def oidc_token(
    body: OidcTokenIn,
    request: Request,
    response: Response,
    db: DbSession = Depends(get_db),
) -> MeOut:
    """Ein Keycloak-Token gegen eine OTA-Sitzung.

    Geprüft wird vollständig und gegen den öffentlichen Schlüssel des Realms
    (`keycloak.pruefe_token`) — Signatur, Aussteller, Laufzeit und vor allem,
    für **welche** Anwendung das Token ausgestellt wurde. Ohne den letzten
    Punkt gälte hier ein Token, das für eine andere Anwendung in diesem Realm
    bestimmt war.
    """
    # Das ID-Token, nicht das Zugriffstoken: Es ist die Aussage über eine
    # Person, und nur dort steht die Kennung (siehe keycloak.pruefe_token).
    rohtoken = body.id_token.strip()
    if not rohtoken:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Kein ID-Token übergeben (Feld `id_token`).")

    try:
        daten = keycloak.pruefe_token(rohtoken)
    except keycloak.KeycloakFehler as exc:
        audit.record(db, "login.oidc_rejected", request=request, grund=str(exc)[:200])
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc

    try:
        user = kcidentity.anmelden(db, keycloak.angaben(daten))
    except kcidentity.Abgelehnt as exc:
        audit.record(db, "login.oidc_refused", request=request, grund=str(exc)[:200])
        db.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc

    audit.record(db, "login.oidc_ok", actor=user, request=request)
    db.commit()

    set_session_cookie(response, user, settings_store.idle_minutes(db))
    return _me(user)


# --- Der Anmeldeweg im Browser ------------------------------------------
#
# Zwei Aufrufe, und dazwischen war der Mensch bei Keycloak:
#
#   /oidc/start     merkt sich, wohin es danach gehen soll, und schickt hin
#   /oidc/callback  nimmt den Code entgegen und macht daraus eine Sitzung
#
# Was zwischen beiden gemerkt werden muss — Zustand, Prüfer, Ziel — liegt in
# einem kurzlebigen, signierten Cookie und nicht im Serverspeicher. Der Grund
# ist nicht Bequemlichkeit: Ein Serverspeicher überlebt keinen Neustart der
# API, und ein Neustart mitten in einer Anmeldung ist kein Ausnahmefall,
# sondern der Normalfall bei jedem Update.

OIDC_COOKIE = "ota_oidc"
# Reichlich Zeit für die Anmeldung, aber nicht unbegrenzt: Der Zustand ist der
# Schutz gegen untergeschobene Anmeldungen und soll nicht ewig gelten.
OIDC_MINUTEN = 15


def _oeffentliche_basis(request: Request) -> str:
    """Unter welcher Adresse **der Browser** diese Anlage sieht.

    Hinter Traefik steht sie in den Weiterleitungskopfzeilen. Ohne sie
    schickten wir den Browser an eine Adresse, die nur die API kennt
    (`http://keycloak:8080`) — und er käme nirgends an.
    """
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
    return f"{proto}://{host}"


def _sicheres_ziel(next_: str | None) -> str:
    """Wohin es nach der Anmeldung geht — nur innerhalb dieser Anlage.

    Ein offener Weiterleitungsparameter ist eine der ältesten Lücken
    überhaupt: `?next=https://woanders.example` macht aus der eigenen
    Anmeldeseite eine Startrampe für fremde. Deshalb ausschliesslich Pfade,
    und auch die nicht in der Form `//fremd.example`, die ein Browser als
    Adresse mit Herkunft liest.
    """
    ziel = (next_ or "/").strip()
    if not ziel.startswith("/") or ziel.startswith("//"):
        return "/"
    return ziel


@router.get("/oidc/start")
def oidc_start(request: Request, next: str = "/") -> Response:
    """Schickt den Browser zur Anmeldung bei Keycloak."""
    import base64
    import hashlib

    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    state = secrets.token_urlsafe(24)
    ziel = _sicheres_ziel(next)

    basis = _oeffentliche_basis(request)
    redirect_uri = f"{basis}/api/auth/oidc/callback"

    merkzettel = jwt.encode(
        {"state": state, "verifier": verifier, "ziel": ziel, "redirect": redirect_uri,
         "exp": datetime.now(timezone.utc) + timedelta(minutes=OIDC_MINUTEN)},
        settings().jwt_secret, algorithm=settings().jwt_algorithm,
    )

    antwort = RedirectResponse(
        keycloak.authorize_url(redirect_uri, state, challenge, f"{basis}/auth"),
        status_code=status.HTTP_303_SEE_OTHER,
    )
    antwort.set_cookie(
        OIDC_COOKIE, merkzettel, max_age=OIDC_MINUTEN * 60,
        httponly=True, secure=settings().cookie_secure,
        # Lax und nicht Strict: Der Rückweg von Keycloak ist eine Navigation
        # von einer anderen Seite. Bei Strict schickte der Browser das Cookie
        # dabei nicht mit, und jede Anmeldung scheiterte am fehlenden Zustand.
        samesite="lax", path="/api/auth",
    )
    return antwort


@router.get("/oidc/callback")
def oidc_callback(
    request: Request,
    response: Response,
    db: DbSession = Depends(get_db),
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> Response:
    """Nimmt den Code entgegen und macht daraus eine OTA-Sitzung."""

    def zurueck_mit(grund: str) -> Response:
        # Fehler landen auf der Anmeldeseite und nicht in einem JSON-Fetzen:
        # Hier steht ein Mensch vor dem Bildschirm, kein Programm.
        from urllib.parse import quote
        r = RedirectResponse(f"/login?fehler={quote(grund)}",
                             status_code=status.HTTP_303_SEE_OTHER)
        r.delete_cookie(OIDC_COOKIE, path="/api/auth")
        return r

    if error:
        return zurueck_mit(f"Keycloak hat abgelehnt: {error}")

    merkzettel = request.cookies.get(OIDC_COOKIE)
    if not merkzettel or not code or not state:
        return zurueck_mit("Die Anmeldung ist unterwegs verlorengegangen. Bitte noch einmal.")

    try:
        notiz = jwt.decode(merkzettel, settings().jwt_secret,
                           algorithms=[settings().jwt_algorithm])
    except jwt.PyJWTError:
        return zurueck_mit("Die Anmeldung hat zu lange gedauert. Bitte noch einmal.")

    if not secrets.compare_digest(str(notiz.get("state", "")), state):
        audit.record(db, "login.oidc_state_mismatch", request=request)
        db.commit()
        return zurueck_mit("Die Anmeldung passte nicht zusammen. Bitte noch einmal.")

    try:
        token_antwort = keycloak.tausche_code(
            code, str(notiz["redirect"]), str(notiz["verifier"]))
        daten = keycloak.pruefe_token(str(token_antwort.get("id_token") or ""))
        user = kcidentity.anmelden(db, keycloak.angaben(daten))
    except keycloak.KeycloakFehler as exc:
        audit.record(db, "login.oidc_rejected", request=request, grund=str(exc)[:200])
        db.commit()
        return zurueck_mit(str(exc))
    except kcidentity.Abgelehnt as exc:
        audit.record(db, "login.oidc_refused", request=request, grund=str(exc)[:200])
        db.commit()
        return zurueck_mit(str(exc))

    audit.record(db, "login.oidc_ok", actor=user, request=request)
    db.commit()

    fertig = RedirectResponse(_sicheres_ziel(str(notiz.get("ziel"))),
                              status_code=status.HTTP_303_SEE_OTHER)
    fertig.delete_cookie(OIDC_COOKIE, path="/api/auth")
    set_session_cookie(fertig, user, settings_store.idle_minutes(db))
    return fertig


@router.post("/oidc/backchannel")
async def oidc_backchannel(request: Request, db: DbSession = Depends(get_db)) -> Response:
    """Keycloak meldet: Dieser Mensch hat sich abgemeldet.

    Der Rückkanal ist die Antwort auf die Frage aus §5e, wie zwei Uhren
    zusammenpassen: **Innerhalb von OTA gilt OTAs Uhr**, aber ein ausdrücklicher
    Widerruf wirkt sofort. Erhöht wird `token_epoch` — dieselbe Mechanik, mit
    der ein Administrator jemanden hinauswirft. Damit ist die nächste Prüfung
    in `forwardAuth` die letzte, die das alte Cookie sieht: auch mitten im
    Stream, auch vor dem nächsten WebSocket-Handshake.

    Ohne Anmeldung erreichbar, und das ist richtig so: Der Beweis steckt in
    der Signatur des Tokens, nicht in einem Cookie. Keycloak ruft hier ohne
    Sitzung an.
    """
    formular = await request.form()
    rohtoken = str(formular.get("logout_token") or "")
    if not rohtoken:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Kein Abmeldetoken.")

    try:
        daten = keycloak.pruefe_abmeldetoken(rohtoken)
    except keycloak.KeycloakFehler as exc:
        # Bewusst 400 und nicht 401: Hier meldet sich niemand an, hier wird
        # etwas Ungültiges vorgelegt.
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    sub = str(daten.get("sub") or "")
    user = kcidentity.finde(db, sub) if sub else None
    if user is None:
        # Kein Konto dazu — dann gibt es hier auch nichts zu beenden. Kein
        # Fehler: Keycloak kennt Menschen, die OTA nie gesehen hat.
        return Response(status_code=status.HTTP_200_OK)

    user.token_epoch = (user.token_epoch or 0) + 1
    audit.record(db, "logout.backchannel", actor=user, request=request)
    db.commit()
    log.info("Abmeldung über den Rückkanal: %s", user.username)
    return Response(status_code=status.HTTP_200_OK)
