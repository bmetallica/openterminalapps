"""Konten aus dem Verzeichnis: anlegen, abgleichen, schützen.

Diese Datei entscheidet, **wo** ein Passwort geprüft wird und **was** ein
Verzeichnis an bestehenden Konten ändern darf. Beides ist eng gefasst, und
die engen Stellen sind Absicht:

* `where_to_check()` — ein lokales Konto wird lokal geprüft. Immer. Auch
  wenn im Verzeichnis ein Eintrag mit demselben Namen steht.
* `adopt()` legt nur **neue** Konten an. Ein bestehendes lokales Konto wird
  nie übernommen, nie umgehängt, nie überschrieben.
* Der Abgleich fasst ausschliesslich Konten mit `auth_provider == "ldap"` an.

Der Angriff, gegen den das steht, ist unspektakulär und deshalb leicht zu
übersehen: Wer im Verzeichnis einen Eintrag anlegen darf, legt einen mit dem
Namen des ersten Administrators an und meldet sich mit seinem eigenen
Passwort als dieser an. Ohne die erste Regel funktioniert das.
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from . import directory
from .models import Group, IdentityConfig, User
from .security import hash_password

log = logging.getLogger("ota.identity")

LOCAL = "local"
LDAP = "ldap"
# Seit der Umstellung (auth-roadmap.md, Etappe B) gibt es eine dritte
# Herkunft. Sie hat hier kein Passwort — geprueft wird bei Keycloak.
KEYCLOAK = "keycloak"


def config(db: DbSession) -> IdentityConfig | None:
    """Die eine Verzeichnis-Anbindung, oder nichts."""
    return db.scalar(select(IdentityConfig).limit(1))


def active(db: DbSession) -> IdentityConfig | None:
    """Sie, wenn sie eingeschaltet und brauchbar ausgefüllt ist."""
    cfg = config(db)
    if cfg and cfg.is_enabled and cfg.server_uri and cfg.base_dn:
        return cfg
    return None


def where_to_check(user: User | None, cfg: IdentityConfig | None) -> str:
    """Wo das Passwort dieses Anmeldeversuchs geprüft wird.

    Rückgabe: ``"local"``, ``"ldap"`` oder ``"none"`` (gar nicht möglich).

    **Ein bestehendes Konto entscheidet selbst**, über `auth_provider`. Nur
    für einen Namen, zu dem es gar kein Konto gibt, kommt das Verzeichnis in
    Frage — und auch dann nur, wenn es eingeschaltet ist.
    """
    if user is not None and user.auth_provider == KEYCLOAK:
        # Ein Konto, das ueber die zentrale Anmeldung kommt, hat hier gar kein
        # Passwort mehr. Es lokal zu pruefen waere nicht nur zwecklos, sondern
        # gefaehrlich: Ein `password_hash`, der versehentlich wieder gesetzt
        # wuerde, oeffnete einen zweiten Weg an Keycloak vorbei — samt der
        # zweiten Stufe, die dort haengt.
        return "none"

    if user is not None:
        # Der Kern der Sache. `auth_provider` ist die einzige Instanz, die
        # hierüber entscheidet, und sie ändert sich nie von selbst.
        return LDAP if user.auth_provider == LDAP else LOCAL
    if cfg is not None and cfg.jit_create:
        return LDAP
    return "none"


def mapped_groups(db: DbSession, cfg: IdentityConfig,
                  directory_groups: list[str]) -> list[Group]:
    """Die OTA-Gruppen zu den Gruppen aus dem Verzeichnis.

    Was nicht abgebildet ist, wird stillschweigend übergangen. Ein Verzeichnis
    hat Dutzende Gruppen, die OTA nichts angehen; daraus jedes Mal eine
    Meldung zu machen hiesse, die Meldungen unlesbar zu machen.
    """
    if not cfg.group_map:
        return []
    gewollt = {
        str(gid) for name, gid in cfg.group_map.items()
        if name in directory_groups
    }
    if not gewollt:
        return []
    return list(db.scalars(
        select(Group).where(Group.id.in_([g for g in gewollt]))
    ).all())


def adopt(db: DbSession, cfg: IdentityConfig,
          person: directory.Person) -> User | None:
    """Legt ein Konto für einen Verzeichniseintrag an — oder lehnt ab.

    Gibt ``None`` zurück, wenn es den Namen schon **lokal** gibt. Das ist der
    Schutz aus dem Kopf dieser Datei: Ein Verzeichniseintrag übernimmt kein
    bestehendes Konto, auch nicht ein deaktiviertes.
    """
    vorhanden = db.scalar(select(User).where(User.username == person.login))
    if vorhanden is not None:
        if vorhanden.auth_provider != LDAP:
            log.warning(
                "Verzeichniseintrag %r trägt denselben Namen wie ein lokales "
                "Konto. Das lokale Konto bleibt unangetastet.", person.login,
            )
            return None
        return vorhanden

    user = User(
        username=person.login,
        display_name=person.display_name or None,
        email=person.email or None,
        # Kein Passwort. Ein Verzeichniskonto hat hier keines, und ein
        # zufälliges hinzuschreiben wäre ein Passwort, das niemand kennt und
        # das trotzdem geprüft würde, wenn jemand `auth_provider` umstellt.
        password_hash=None,
        auth_provider=LDAP,
        external_id=person.dn,
        is_active=True,
        must_change_password=False,
    )
    user.groups = mapped_groups(db, cfg, person.groups)
    db.add(user)
    db.flush()
    log.info("Konto %s aus dem Verzeichnis angelegt (%d Gruppe(n))",
             person.login, len(user.groups))
    return user


def refresh(db: DbSession, cfg: IdentityConfig, user: User,
            person: directory.Person) -> None:
    """Bringt ein Verzeichniskonto auf den Stand des Verzeichnisses.

    Fasst **nur** Konten mit `auth_provider == "ldap"` an. Ein lokales Konto
    hier zu verändern wäre derselbe Fehler wie es zu übernehmen, nur später.
    """
    if user.auth_provider != LDAP:
        return

    user.external_id = person.dn
    if person.display_name:
        user.display_name = person.display_name
    if person.email:
        user.email = person.email

    neu = mapped_groups(db, cfg, person.groups)
    # Systemgruppen, die jemand von Hand vergeben hat, bleiben. Der Abgleich
    # bildet das Verzeichnis ab; er soll keine Entscheidung überschreiben,
    # die es dort gar nicht abzubilden gibt.
    behalten = [g for g in user.groups if g.is_system]
    user.groups = list({g.id: g for g in (neu + behalten)}.values())


def sync_all(db: DbSession) -> dict:
    """Gleicht alle Verzeichniskonten ab. Für den nächtlichen Lauf.

    **Löscht nichts.** Ein Konto, das im Verzeichnis verschwunden ist, wird
    deaktiviert und behält seine Daten — sein Zuhause, seine Sicherungen,
    seine Spur im Protokoll. Löschen ist eine Entscheidung, die ein Mensch
    trifft (Handbuch, Kapitel 8, „Offboarding").
    """
    cfg = active(db)
    if cfg is None or not cfg.sync_enabled:
        return {"status": "abgeschaltet", "geprueft": 0}

    konten = db.scalars(select(User).where(User.auth_provider == LDAP)).all()
    geprueft = geaendert = verschwunden = fehler = 0

    for user in konten:
        geprueft += 1
        try:
            person = directory.find_person(cfg, user.username)
        except directory.DirectoryError as exc:
            fehler += 1
            log.warning("Abgleich für %s fehlgeschlagen: %s", user.username, exc)
            continue

        if person is None:
            if user.is_active:
                user.is_active = False
                user.token_epoch = (user.token_epoch or 0) + 1
                verschwunden += 1
                log.info("%s steht nicht mehr im Verzeichnis — deaktiviert, "
                         "nicht gelöscht", user.username)
            continue

        vorher = sorted(g.id for g in user.groups)
        if not user.is_active:
            user.is_active = True
        refresh(db, cfg, user, person)
        if sorted(g.id for g in user.groups) != vorher:
            geaendert += 1

    cfg.last_sync_at = datetime.now(timezone.utc)
    cfg.last_error = None if not fehler else f"{fehler} Konten nicht abgleichbar"
    db.commit()
    return {
        "status": "fertig", "geprueft": geprueft, "geaendert": geaendert,
        "deaktiviert": verschwunden, "fehler": fehler,
    }
