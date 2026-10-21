"""Ein Domänenkonto einem bestehenden OTA-Konto zuordnen (2026-10-21).

Der Fall aus dem Betrieb: Jemand hatte ein OTA-Konto — lokal oder in
Keycloak von OTA angelegt — und arbeitet mit dessen Containern. Dann kommt
das Verzeichnis (AD/LDAP), er meldet sich mit seinem Domänenkonto an, und
OTA legt ihm dafür ein **neues, leeres** Konto an (`kcidentity.anmelden`,
erkannt am Keycloak-`sub`). Seine Arbeitsplätze hängen aber am alten.

Die Verwaltung ordnet deshalb das Domänenkonto dem alten Konto zu. Danach
gibt es nur noch das alte — mit seinen Sitzungen, Zuhausen, Ablagen und
Kontingenten, denn die hängen alle an `user.id` und nicht am Namen
(`security.profile_path`). Es meldet sich ab dann über die Domäne an und
heisst wie dort.

Drei Entscheidungen:

* **Das lokale Passwort geht weg.** Es bliebe sonst ein zweiter Weg hinein,
  an Keycloak und an einer Sperre im Verzeichnis vorbei — dieselbe Regel wie
  bei der Übernahme (`uebernahme.py`).
* **Das bei der ersten Domänenanmeldung entstandene Konto verschwindet.** Es
  ist ein Nebenprodukt, kein Konto, das jemand wollte. Läuft darin gerade
  etwas, wird nichts angefasst: Die Verwaltung soll erst nachsehen.
* **In Keycloak wird nichts gelöscht.** Ein Konto, das OTA dort früher für
  den Menschen angelegt hatte, wird nur deaktiviert. Das Domänenkonto selbst
  gehört dem Verzeichnis und bleibt, wie es ist.
"""

from __future__ import annotations

import logging

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from . import agent_client, keycloak, settings_store, verzeichnis
from .models import Session as SessionModel, User

log = logging.getLogger("ota.verknuepfen")

LIVE = ("starting", "running", "paused")
KEYCLOAK = "keycloak"


def root_plaetze_entfernen(db: DbSession, user: User) -> None:
    """Die Root-Arbeitsplätze eines Kontos samt Docker-Daten.

    Die Zeilen verschwinden mit dem Konto; blieben die Container stehen,
    räumte sie der Aufräumer zwar weg, ihre Docker-Volumes aber nie.
    """
    for sess in db.scalars(select(SessionModel).where(
            SessionModel.user_id == user.id)).all():
        if sess.container_id and sess.template and sess.template.klasse == "root":
            try:
                agent_client.remove_container(sess.container_id, daten=True)
            except HTTPException as exc:
                log.warning("Root-Arbeitsplatz %s nicht entfernt: %s", sess.id, exc.detail)


def _fehler(code: int, text: str) -> HTTPException:
    return HTTPException(code, text)


def _bericht(db: DbSession, user: User) -> dict:
    """Was ein Konto in OTA hat — für die Entscheidung der Verwaltung."""
    sitzungen = db.scalars(select(SessionModel).where(
        SessionModel.user_id == user.id, SessionModel.status != "stopped")).all()
    return {
        "id": str(user.id),
        "username": user.username,
        "angelegt": user.created_at.isoformat() if getattr(user, "created_at", None) else None,
        "letzte_anmeldung": user.last_login_at.isoformat() if user.last_login_at else None,
        "sitzungen": len(sitzungen),
        "laufend": sum(1 for s in sitzungen if s.status in LIVE),
        "is_admin": bool(user.is_admin),
    }


def _pruefe_ziel(db: DbSession, ziel: User, actor: User) -> None:
    if ziel.id == actor.id:
        raise _fehler(status.HTTP_409_CONFLICT,
                      "Das eigene Konto lässt sich hier nicht verknüpfen — "
                      "du würdest dich dabei selbst abmelden.")
    if ziel.username == settings_store.breakglass(db):
        raise _fehler(status.HTTP_409_CONFLICT,
                      "Das Notfallkonto bleibt lokal. Es ist der Weg hinein, "
                      "wenn die zentrale Anmeldung nicht geht.")
    if ziel.auth_provider == KEYCLOAK and ziel.external_id:
        try:
            jetzt = keycloak.konto_lesen(ziel.external_id)
        except (keycloak.KeycloakFehler, httpx.HTTPError):
            jetzt = None
        if keycloak.aus_verzeichnis(jetzt):
            raise _fehler(status.HTTP_409_CONFLICT,
                          f"„{ziel.username}“ meldet sich schon über das Verzeichnis an.")


def kandidaten(db: DbSession, ziel: User, suche: str) -> list[dict]:
    """Domänenkonten, die zur Suche passen — mit dem, was in OTA schon dazu steht."""
    suche = (suche or "").strip()
    if len(suche) < 2:
        return []
    try:
        resp = keycloak.ruf("GET", "/users", params={"search": suche, "max": 25,
                                                     "briefRepresentation": "false"})
    except httpx.HTTPError as exc:
        raise _fehler(status.HTTP_503_SERVICE_UNAVAILABLE,
                      "Keycloak antwortet nicht.") from exc
    if resp.status_code != 200:
        raise _fehler(status.HTTP_502_BAD_GATEWAY, "Keycloak liefert keine Konten.")

    aus = []
    for k in resp.json():
        if not keycloak.aus_verzeichnis(k):
            continue
        name = " ".join(x for x in (k.get("firstName"), k.get("lastName")) if x) or None
        vorhanden = db.scalar(select(User).where(User.external_id == str(k["id"])))
        aus.append({
            "sub": str(k["id"]),
            "username": str(k.get("username", "")).lower(),
            "name": name,
            "email": k.get("email"),
            "aktiv": bool(k.get("enabled", True)),
            # Das Konto, das OTA bei der ersten Domänenanmeldung angelegt hat.
            "ota_konto": _bericht(db, vorhanden) if vorhanden is not None
            and vorhanden.id != ziel.id else None,
            "ist_ziel": vorhanden is not None and vorhanden.id == ziel.id,
        })
    return aus


def verknuepfen(db: DbSession, ziel: User, sub: str, actor: User) -> dict:
    """Ordnet das Domänenkonto `sub` dem Konto `ziel` zu. Committet nicht."""
    _pruefe_ziel(db, ziel, actor)

    try:
        konto = keycloak.konto_lesen(sub)
    except (keycloak.KeycloakFehler, httpx.HTTPError) as exc:
        raise _fehler(status.HTTP_503_SERVICE_UNAVAILABLE,
                      f"Keycloak antwortet nicht: {exc}") from exc
    if konto is None:
        raise _fehler(status.HTTP_404_NOT_FOUND, "Dieses Domänenkonto gibt es nicht.")
    if not keycloak.aus_verzeichnis(konto):
        raise _fehler(status.HTTP_400_BAD_REQUEST,
                      "Das ist kein Konto aus dem Verzeichnis.")
    neuer_name = str(konto.get("username", "")).strip().lower()
    if not neuer_name:
        raise _fehler(status.HTTP_400_BAD_REQUEST, "Das Domänenkonto hat keinen Namen.")

    # 1. Das Nebenprodukt der ersten Domänenanmeldung.
    doppel = db.scalar(select(User).where(User.external_id == sub, User.id != ziel.id))
    entfernt = None
    if doppel is not None:
        bericht = _bericht(db, doppel)
        if bericht["laufend"]:
            raise _fehler(
                status.HTTP_409_CONFLICT,
                f"Das Konto „{doppel.username}“, das bei der Domänenanmeldung "
                f"entstanden ist, hat {bericht['laufend']} laufende Sitzung(en). "
                "Erst beenden — es wird beim Verknüpfen entfernt.")
        if doppel.is_admin and not any(
                u.is_admin for u in db.scalars(select(User).where(
                    User.is_active.is_(True), User.id != doppel.id)).all()):
            raise _fehler(status.HTTP_409_CONFLICT,
                          f"„{doppel.username}“ ist der letzte Administrator.")
        root_plaetze_entfernen(db, doppel)
        entfernt = bericht
        db.delete(doppel)
        db.flush()
        log.info("Konto %s aus der Domänenanmeldung entfernt; %s übernimmt",
                 bericht["username"], ziel.username)

    # 2. Ein Name, den schon ein drittes Konto trägt, das nichts damit zu tun hat.
    dritter = db.scalar(select(User).where(User.username == neuer_name, User.id != ziel.id))
    if dritter is not None:
        raise _fehler(status.HTTP_409_CONFLICT,
                      f"Den Namen „{neuer_name}“ trägt hier schon ein anderes Konto.")

    # 3. Das alte Keycloak-Konto, das OTA einmal angelegt hatte: nur deaktivieren.
    altes_kc = None
    if ziel.auth_provider == KEYCLOAK and ziel.external_id and ziel.external_id != sub:
        altes_kc = ziel.external_id
        try:
            keycloak.konto_sperren(altes_kc, True)
        except (keycloak.KeycloakFehler, httpx.HTTPError) as exc:
            log.warning("Altes Keycloak-Konto %s nicht deaktiviert: %s", altes_kc[:8], exc)

    alter_name = ziel.username
    ziel.username = neuer_name
    ziel.auth_provider = KEYCLOAK
    ziel.external_id = sub
    ziel.email = konto.get("email") or ziel.email
    name = " ".join(x for x in (konto.get("firstName"), konto.get("lastName")) if x)
    ziel.display_name = name or ziel.display_name
    # Kein zweiter Weg hinein (siehe oben), und angemeldete Sitzungen des
    # alten Kontos sind ab jetzt ungültig.
    ziel.password_hash = None
    ziel.must_change_password = False
    ziel.totp_secret = None
    ziel.totp_recovery = []
    ziel.token_epoch = (ziel.token_epoch or 0) + 1
    db.flush()

    # Gruppen aus dem Verzeichnis gleich jetzt, und die von OTA nach Keycloak.
    try:
        verzeichnis.bei_anmeldung(db, ziel)
    except Exception as exc:  # noqa: BLE001 — die nächste Anmeldung holt es nach
        log.warning("Verzeichnisgruppen für %s nicht gelesen: %s", neuer_name, exc)
    verzeichnis.nach_keycloak(ziel)

    return {
        "username": neuer_name,
        "vorher": alter_name,
        "entfernt": entfernt,
        "altes_keycloak_konto_deaktiviert": bool(altes_kc),
    }
