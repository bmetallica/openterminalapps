"""OTA-Git: eine Forgejo-Instanz, die zu OTA gehört (Handbuch Kapitel 27).

Im Menü ein- und ausschaltbar (Einstellungen → Git). Ist es an,

* läuft der Container `ota-git` (angelegt vom Agent, git_dienst.py) unter
  einer eigenen Subdomain, mit Zertifikat der OTA-CA, hinter Traefik;
* meldet man sich über Keycloak an — dieselben Zugangsdaten wie in OTA —,
  und Keycloak lässt nur die berechtigten Gruppen herein, dazu alle
  Administratoren (derselbe Weg wie bei jeder Anwendung im Katalog);
* legt OTA die Konten selbst an, sperrt sie, wenn jemand die Berechtigung
  verliert, und benennt sie nach. Wer in OTA Admin ist, ist es auch dort;
* bekommt jeder berechtigte Arbeitsplatz Git vorkonfiguriert: ein Token je
  Arbeitsplatz, widerrufen, wenn er endet.

Gelöscht wird in Forgejo nichts — kein Konto, kein Repository. Ausschalten
hält nur an.
"""

from __future__ import annotations

import datetime as dt
import logging
import secrets
import uuid
from pathlib import Path
from typing import Any

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session as DbSession

from . import agent_client, keycloak, settings_store
from .config import settings
from .db import engine
from .models import (
    GitKonto, GitToken, Group, Session as SessionModel, Template, User, WebApp,
)

log = logging.getLogger("ota.git")

CLIENT_ID = "ota-git"
QUELLE = "ota"           # Name der Anmeldequelle in Forgejo
SLUG = "ota-git"
API = "http://ota-git:3000/api/v1"
ADMIN = "ota-admin"
DB_NAME = DB_USER = "forgejo"
LIVE = ("starting", "running", "paused")
# Was ein Arbeitsplatz mit seinem Token darf: Repositories lesen und
# schreiben, sich selbst sehen. Keine Verwaltung, keine Organisationen.
TOKEN_RECHTE = ["write:repository", "read:user"]


class GitFehler(RuntimeError):
    pass


# --------------------------------------------------------------------------
# Zustand
# --------------------------------------------------------------------------

def an(db: DbSession) -> bool:
    return bool(settings_store.get(db, settings_store.GIT_AN))


def domain(db: DbSession) -> str:
    return str(settings_store.get(db, settings_store.GIT_DOMAIN) or "")


def gruppen_ids(db: DbSession) -> list[str]:
    """Die berechtigten Gruppen — nur die, die es noch gibt."""
    gemerkt = [str(g) for g in settings_store.get(db, settings_store.GIT_GRUPPEN) or []]
    da = {str(i) for i in db.scalars(select(Group.id)).all()}
    return [g for g in gemerkt if g in da]


def _admin_pw() -> str:
    import os
    return os.environ.get("OTA_GIT_ADMIN_PW", "")


def berechtigt(db: DbSession, user: User) -> bool:
    """Darf dieser Mensch in OTA-Git? Administratoren immer."""
    if not user.is_active or user.is_locked:
        return False
    if user.is_admin:
        return True
    erlaubt = set(gruppen_ids(db))
    return any(str(g.id) in erlaubt for g in user.groups)


def zugangsgruppen(db: DbSession) -> list[Group]:
    """Die berechtigten Gruppen und alle, die Administratoren machen."""
    erlaubt = set(gruppen_ids(db))
    return [g for g in db.scalars(select(Group)).all()
            if str(g.id) in erlaubt or "admin" in (g.permissions or [])]


# --------------------------------------------------------------------------
# Forgejo
# --------------------------------------------------------------------------

def _ruf(method: str, pfad: str, sudo: str | None = None, **kw: Any) -> httpx.Response:
    kopf = {"Sudo": sudo} if sudo else {}
    try:
        return httpx.request(method, f"{API}{pfad}", auth=(ADMIN, _admin_pw()),
                             headers=kopf, timeout=20.0, **kw)
    except httpx.HTTPError as exc:
        raise GitFehler(f"Forgejo antwortet nicht: {exc}") from exc


def _pruefen(resp: httpx.Response, was: str) -> httpx.Response:
    if resp.status_code >= 400:
        try:
            grund = resp.json().get("message") or resp.text
        except ValueError:
            grund = resp.text
        raise GitFehler(f"{was}: {resp.status_code} {str(grund)[:200]}")
    return resp


# --------------------------------------------------------------------------
# Einschalten und ausschalten
# --------------------------------------------------------------------------

def _datenbank_sorgen() -> None:
    """Eigene Datenbank und eigene Rolle für Forgejo — angelegt, wenn sie
    fehlen; das Passwort wird bei jedem Einschalten aus der .env gesetzt."""
    import os
    pw = os.environ.get("OTA_GIT_DB_PW", "")
    if not pw:
        raise GitFehler("OTA_GIT_DB_PW fehlt in deploy/.env. „sudo make update“ ergänzt es.")
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        if not conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :n"),
                            {"n": DB_USER}).scalar():
            conn.execute(text(f'CREATE ROLE "{DB_USER}" LOGIN'))
        # Das Passwort ist alphanumerisch (setup-env.sh) — trotzdem quotiert.
        conn.execute(text(f"ALTER ROLE \"{DB_USER}\" PASSWORD '{pw.replace(chr(39), '')}'"))
        if not conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :n"),
                            {"n": DB_NAME}).scalar():
            conn.execute(text(f'CREATE DATABASE "{DB_NAME}" OWNER "{DB_USER}" '
                              "ENCODING 'UTF8' TEMPLATE template0"))


def _ca() -> str:
    return (Path(settings().certs_dir) / "ota-ca.crt").read_text()


def _umgebung(name: str) -> dict[str, str]:
    """Forgejos Einstellungen, als FORGEJO__abschnitt__SCHLUESSEL."""
    werte = {
        "database": {"DB_TYPE": "postgres", "HOST": "ota-db:5432", "NAME": DB_NAME,
                     "USER": DB_USER, "SSL_MODE": "disable"},
        "server": {"DOMAIN": name, "ROOT_URL": f"https://{name}/", "HTTP_PORT": "3000",
                   "SSH_DOMAIN": name, "SSH_PORT": "2222", "SSH_LISTEN_PORT": "22",
                   "LANDING_PAGE": "login", "OFFLINE_MODE": "true"},
        "security": {"INSTALL_LOCK": "true", "REVERSE_PROXY_TRUST_LOCAL_NETWORK": "false"},
        # Konten entstehen nur über Keycloak — oder durch OTA selbst.
        "service": {"DISABLE_REGISTRATION": "false", "ALLOW_ONLY_EXTERNAL_REGISTRATION": "true",
                    "SHOW_REGISTRATION_BUTTON": "false", "REQUIRE_SIGNIN_VIEW": "true",
                    "ENABLE_NOTIFY_MAIL": "false", "DEFAULT_KEEP_EMAIL_PRIVATE": "false"},
        "oauth2_client": {"ENABLE_AUTO_REGISTRATION": "true", "ACCOUNT_LINKING": "auto",
                          "USERNAME": "nickname", "UPDATE_AVATAR": "false",
                          "OPENID_CONNECT_SCOPES": "profile email"},
        "openid": {"ENABLE_OPENID_SIGNIN": "false", "ENABLE_OPENID_SIGNUP": "false"},
        "mailer": {"ENABLED": "false"},
        "repository": {"DEFAULT_PRIVATE": "private"},
        "log": {"LEVEL": "Info"},
    }
    return {f"FORGEJO__{abschnitt}__{k}": v
            for abschnitt, paare in werte.items() for k, v in paare.items()}


def _kachel_url(name: str) -> str:
    """Die Kachel startet gleich die Anmeldung über Keycloak. Mit der
    Sitzung aus OTA ist man ohne Zwischenschritt drin; die Anmeldeseite von
    Forgejo sähe man nur über die nackte Adresse."""
    return f"https://{name}/user/oauth2/{QUELLE}"


def _katalog(db: DbSession, name: str) -> tuple[WebApp, str | None]:
    """Die Kachel im Anwendungskatalog — und der Client in Keycloak dazu.

    Gibt das Geheimnis zurück, wenn es neu ist (Forgejo braucht es). Bei
    jedem Einschalten neu: Es steht nirgends in OTA, und ein neues kostet
    nichts, weil OTA es Forgejo gleich mitgibt.
    """
    rueck = f"https://{name}/user/oauth2/{QUELLE}/callback"
    app = db.scalar(select(WebApp).where(WebApp.verwaltet == "git"))
    if app is None:
        app = WebApp(slug=SLUG, name="Git", description="Repositories, Forgejo",
                     icon="⎇", url=_kachel_url(name), redirect_uri=rueck,
                     client_id=CLIENT_ID, verwaltet="git", fuer_alle=False, sort_order=0)
        db.add(app)
    app.url, app.redirect_uri, app.is_enabled = _kachel_url(name), rueck, True
    app.groups = zugangsgruppen(db)
    try:
        keycloak.client_entfernen(CLIENT_ID)
    except keycloak.KeycloakFehler:
        pass
    geheimnis = keycloak.client_anlegen(CLIENT_ID, "OTA-Git", rueck)
    keycloak.anwendung_zugang(CLIENT_ID, sorted(g.name for g in app.groups), False)
    return app, geheimnis


def _ota_url(db: DbSession) -> str:
    url = str(settings_store.get(db, settings_store.GIT_OTA_URL) or "").rstrip("/")
    if not url.startswith("https://"):
        raise GitFehler("Die Adresse von OTA fehlt (so, wie Browser sie sehen, mit https://).")
    return url


def einschalten(db: DbSession) -> dict:
    """Alles, damit OTA-Git läuft — wiederholbar. Committet."""
    name = domain(db)
    if not name:
        raise GitFehler("Erst eine Subdomain eintragen.")
    _datenbank_sorgen()
    app, geheimnis = _katalog(db, name)
    db.flush()
    # Das Zertifikat der Subdomain stellt der Agent aus: Den Schlüssel der
    # CA darf die API nicht lesen.
    agent_client.git_an({"domain": name, "umgebung": _umgebung(name)})
    erg = agent_client.git_einrichten({
        "name": QUELLE, "key": CLIENT_ID, "secret": geheimnis or "",
        "discovery": f"{_ota_url(db)}/auth/realms/{keycloak._realm()}/.well-known/openid-configuration",
    })
    settings_store.put(db, settings_store.GIT_AN, True)
    settings_store.put(db, "git.quelle", int(erg["quelle"]))
    db.commit()
    stand = konten_abgleichen(db)
    return {"an": True, "konten": stand}


def ausschalten(db: DbSession) -> None:
    """Anhalten: Container stoppen, Kachel und Keycloak-Client weg. Daten bleiben."""
    try:
        agent_client.git_aus()
    except HTTPException as exc:
        log.warning("OTA-Git nicht angehalten: %s", exc.detail)
    app = db.scalar(select(WebApp).where(WebApp.verwaltet == "git"))
    if app is not None:
        db.delete(app)
    try:
        keycloak.anwendung_fluss_entfernen(CLIENT_ID)
        keycloak.client_entfernen(CLIENT_ID)
    except keycloak.KeycloakFehler as exc:
        log.warning("Keycloak-Client von OTA-Git nicht entfernt: %s", exc)
    settings_store.put(db, settings_store.GIT_AN, False)
    db.query(GitToken).delete()
    db.commit()


def zugang_nachziehen(db: DbSession) -> None:
    """Gruppen geändert: Kachel und Keycloak nachziehen. Committet nicht."""
    app = db.scalar(select(WebApp).where(WebApp.verwaltet == "git"))
    if app is None:
        return
    app.url = _kachel_url(domain(db))
    app.groups = zugangsgruppen(db)
    keycloak.anwendung_zugang(CLIENT_ID, sorted(g.name for g in app.groups), False)


# --------------------------------------------------------------------------
# Konten
# --------------------------------------------------------------------------

def _quelle(db: DbSession) -> int:
    return int(settings_store.get(db, "git.quelle") or 0)


def konto_sorgen(db: DbSession, user: User) -> str:
    """Bringt das Forgejo-Konto dieses Menschen auf den Stand von OTA.

    Gibt zurück, was geschah: angelegt, gesperrt, entsperrt, umbenannt, ok.
    Wer nicht berechtigt ist und noch kein Konto hat, bekommt keines.
    """
    eintrag = db.get(GitKonto, user.id)
    darf = berechtigt(db, user)
    if eintrag is None and not darf:
        return "nicht berechtigt"

    ergebnis = "ok"
    if eintrag is None:
        resp = _ruf("POST", "/admin/users", json={
            "username": user.username, "email": user.email or f"{user.username}@ota.invalid",
            "full_name": user.display_name or "", "login_name": user.username,
            "source_id": _quelle(db), "must_change_password": False,
            "password": secrets.token_urlsafe(24), "send_notify": False,
        })
        if resp.status_code == 422 and "already exists" in resp.text:
            # Schon da — etwa über die erste Anmeldung in Forgejo selbst.
            pass
        else:
            _pruefen(resp, f"Konto {user.username} anlegen")
            ergebnis = "angelegt"
        eintrag = GitKonto(user_id=user.id, forgejo_name=user.username, gesperrt=False)
        db.add(eintrag)

    if eintrag.forgejo_name != user.username:
        _umbenennen(eintrag.forgejo_name, user.username)
        eintrag.forgejo_name = user.username
        ergebnis = "umbenannt"

    aenderung: dict[str, Any] = {
        "login_name": user.username, "source_id": _quelle(db),
        "full_name": user.display_name or "",
        "admin": bool(user.is_admin) and darf,
        "prohibit_login": not darf,
    }
    if user.email:
        aenderung["email"] = user.email
    _pruefen(_ruf("PATCH", f"/admin/users/{user.username}", json=aenderung),
             f"Konto {user.username} ändern")
    if eintrag.gesperrt != (not darf):
        ergebnis = "gesperrt" if not darf else "entsperrt"
        eintrag.gesperrt = not darf
    db.flush()
    return ergebnis


def _umbenennen(alt: str, neu: str) -> None:
    """Forgejo-Konto umbenennen. Trägt schon ein anderes den neuen Namen —
    etwa das Konto, das bei der ersten Domänenanmeldung entstand (siehe
    verknuepfen.py) —, wird jenes gesperrt und beiseite benannt, nie gelöscht."""
    resp = _ruf("POST", f"/admin/users/{alt}/rename", json={"new_username": neu})
    if resp.status_code == 422:
        beiseite = f"{neu}.alt-{dt.date.today():%Y%m%d}"
        log.info("OTA-Git: %s ist belegt — das vorhandene Konto heisst jetzt %s", neu, beiseite)
        _pruefen(_ruf("PATCH", f"/admin/users/{neu}",
                      json={"login_name": neu, "source_id": 0, "prohibit_login": True}),
                 f"Konto {neu} sperren")
        _pruefen(_ruf("POST", f"/admin/users/{neu}/rename", json={"new_username": beiseite}),
                 f"Konto {neu} beiseite benennen")
        resp = _ruf("POST", f"/admin/users/{alt}/rename", json={"new_username": neu})
    _pruefen(resp, f"Konto {alt} umbenennen")


def konten_abgleichen(db: DbSession) -> dict:
    """Alle Konten. Committet. Einer, der scheitert, hält die anderen nicht auf."""
    if not an(db):
        return {}
    zaehler: dict[str, int] = {}
    fehler: list[str] = []
    for user in db.scalars(select(User)).all():
        try:
            was = konto_sorgen(db, user)
        except GitFehler as exc:
            fehler.append(f"{user.username}: {exc}")
            continue
        zaehler[was] = zaehler.get(was, 0) + 1
    db.commit()
    if fehler:
        log.warning("OTA-Git: %d Konten nicht abgeglichen: %s", len(fehler), fehler[:3])
    return {**zaehler, "fehler": fehler[:20]}


def bei_anmeldung(db: DbSession, user: User) -> None:
    """Bei jeder Anmeldung über Keycloak. Scheitert es, meldet man sich
    trotzdem an — Git ist ein Zusatz, kein Tor."""
    if not an(db):
        return
    try:
        konto_sorgen(db, user)
    except GitFehler as exc:
        log.warning("OTA-Git: Konto %s nicht abgeglichen: %s", user.username, exc)


# --------------------------------------------------------------------------
# Arbeitsplätze
# --------------------------------------------------------------------------

def fuer_sitzung(db: DbSession, sess: SessionModel, user: User, tpl: Template) -> dict:
    """Was der Agent im Arbeitsplatz einrichtet — oder {} (dann räumt er weg)."""
    if not an(db) or not getattr(tpl, "git_vorkonfig", True) or not berechtigt(db, user):
        return {}
    try:
        konto_sorgen(db, user)
        widerrufen(db, sess.id)
        name = f"ota-{str(sess.id)[:8]}-{secrets.token_hex(3)}"
        t = _pruefen(_ruf("POST", f"/users/{user.username}/tokens", sudo=user.username,
                          json={"name": name, "scopes": TOKEN_RECHTE}),
                     "Token ausstellen").json()
        db.add(GitToken(session_id=sess.id, forgejo_name=user.username, token_id=int(t["id"])))
        db.flush()
    except GitFehler as exc:
        log.warning("OTA-Git im Arbeitsplatz %s nicht vorkonfiguriert: %s", sess.id, exc)
        return {}
    return {"domain": domain(db), "token": t["sha1"], "nutzer": user.username,
            "name": user.display_name or user.username, "email": user.email or "",
            "ca": _ca()}


def widerrufen(db: DbSession, session_id: uuid.UUID) -> None:
    """Das Token eines Arbeitsplatzes widerrufen. Committet nicht."""
    eintrag = db.get(GitToken, session_id)
    if eintrag is None:
        return
    try:
        resp = _ruf("DELETE", f"/users/{eintrag.forgejo_name}/tokens/{eintrag.token_id}",
                    sudo=eintrag.forgejo_name)
        if resp.status_code not in (204, 404):
            log.warning("Token von %s nicht widerrufen: %s", session_id, resp.status_code)
            return
    except GitFehler as exc:
        log.warning("Token von %s nicht widerrufen: %s", session_id, exc)
        return
    db.delete(eintrag)


def tokens_aufraeumen(db: DbSession) -> int:
    """Tokens von Arbeitsplätzen, die nicht mehr laufen. Committet."""
    weg = 0
    for eintrag in db.scalars(select(GitToken)).all():
        sess = db.get(SessionModel, eintrag.session_id)
        if sess is None or sess.status not in LIVE:
            widerrufen(db, eintrag.session_id)
            weg += 1
    db.commit()
    return weg


def stand(db: DbSession) -> dict:
    """Für die Einstellungen."""
    try:
        dienst = agent_client.git_status()
    except HTTPException:
        dienst = {"container": "unbekannt"}
    import socket
    name = domain(db)
    try:
        aufgeloest = socket.gethostbyname(name) if name else ""
    except OSError:
        aufgeloest = ""
    return {
        "an": an(db), "domain": name, "gruppen": gruppen_ids(db),
        "ota_url": str(settings_store.get(db, settings_store.GIT_OTA_URL) or ""),
        "dienst": dienst, "dns": aufgeloest,
        "konten": db.query(GitKonto).count(),
        "gesperrt": db.query(GitKonto).filter(GitKonto.gesperrt.is_(True)).count(),
        "tokens": db.query(GitToken).count(),
    }


def nach_aenderung(db: DbSession, user: User | None = None) -> None:
    """Nach Änderungen in der Verwaltung: ein Konto, oder Gruppen und alle.
    Scheitert es, bleibt die Änderung in OTA — der Takt holt es nach."""
    if not an(db):
        return
    try:
        if user is not None:
            # Die Gruppen frisch lesen: Die Verwaltung hat sie eben geändert,
            # und die geladene Beziehung kennt den alten Stand.
            db.refresh(user)
            konto_sorgen(db, user)
            db.commit()
        else:
            zugang_nachziehen(db)
            db.commit()
            konten_abgleichen(db)
    except Exception as exc:  # noqa: BLE001
        log.warning("OTA-Git nicht nachgezogen: %s", exc)


def vor_dem_loeschen(db: DbSession, user: User) -> None:
    """Ein OTA-Konto wird gelöscht: Forgejo-Konto sperren (nie löschen —
    seine Repositories gehören womöglich noch jemandem) und Tokens widerrufen."""
    eintrag = db.get(GitKonto, user.id)
    if eintrag is None or not an(db):
        return
    try:
        for t in db.scalars(select(GitToken).where(GitToken.forgejo_name == eintrag.forgejo_name)).all():
            widerrufen(db, t.session_id)
        _pruefen(_ruf("PATCH", f"/admin/users/{eintrag.forgejo_name}", json={
            "login_name": eintrag.forgejo_name, "source_id": _quelle(db),
            "prohibit_login": True, "admin": False}), f"Konto {eintrag.forgejo_name} sperren")
    except GitFehler as exc:
        log.warning("OTA-Git: Konto %s nicht gesperrt: %s", eintrag.forgejo_name, exc)
