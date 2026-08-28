"""Erstbefuellung: Systemgruppen, der erste Administrator und der Notzugang.

Aufruf:  python -m ota.seed --admin <name>

Seit der Umstellung auf Keycloak (auth-roadmap.md) legt dieser Lauf **zwei**
Konten an, und das ist kein Zufall, sondern genau die Architektur, die dort
beschlossen wurde:

  <name>    der Alltagszugang. Liegt in Keycloak, meldet sich ueber die
            zentrale Anmeldung an — wie spaeter jeder andere auch.
  notfall   der Ausweg. Ein lokales Konto, das ohne Keycloak funktioniert,
            unter einer eigenen Adresse erreichbar und im Protokoll sichtbar.

Ohne den zweiten waere die Anlage nach einer kaputten Keycloak-Konfiguration
nicht mehr zu betreten. Ohne den ersten muesste jeder Alltagsschritt ueber den
Notausgang laufen — und dann ist er keiner mehr.

Ist Keycloak nicht erreichbar, entsteht nur das lokale Konto. Der Lauf sagt
das deutlich; nachholen laesst es sich mit einem zweiten Aufruf.
"""

from __future__ import annotations

import argparse
import secrets
import sys

from sqlalchemy import select

from . import keycloak, settings_store
from .db import Base, SessionLocal, engine
from .models import Group, User
from .security import hash_password

# Der Name des Notzugangs steht fest. Er soll genau einer sein, und einer,
# den man in jeder Anlage an derselben Stelle sucht.
NOTFALL = "notfall"

SYSTEM_GROUPS = [
    {
        "name": "admins", "slug": "admins", "priority": 1, "is_system": True,
        "description": "Vollzugriff auf Verwaltung, Images und alle Sessions.",
        "permissions": ["admin"],
    },
    {
        "name": "users", "slug": "users", "priority": 1000, "is_system": True,
        "description": "Sieht ausschliesslich das eigene Dashboard.",
        "permissions": [],
    },
]


def ensure_groups(db) -> dict[str, Group]:
    out: dict[str, Group] = {}
    for spec in SYSTEM_GROUPS:
        group = db.scalar(select(Group).where(Group.slug == spec["slug"]))
        if group is None:
            group = Group(**spec)
            db.add(group)
            print(f"Gruppe angelegt: {spec['slug']}")
        else:
            # Rechte der Systemgruppen wieder geradeziehen, falls verstellt.
            group.permissions = spec["permissions"]
            group.is_system = True
        out[spec["slug"]] = group
    db.flush()
    return out


def _passwort(laenge: int = 14) -> str:
    """Lesbar am Telefon: keine Zeichen, die sich verwechseln lassen."""
    import string

    alphabet = "".join(c for c in string.ascii_letters + string.digits
                       if c not in "0O1lI")
    return "".join(secrets.choice(alphabet) for _ in range(laenge))


def _in_keycloak(db, groups, name: str, email: str | None, passwort: str) -> bool:
    """Der Alltagszugang. Gibt zurueck, ob er in Keycloak entstanden ist."""
    adresse = email or f"{name}@ota.invalid"
    user = db.scalar(select(User).where(User.username == name))

    sub = None
    try:
        vorhanden = keycloak.konto_finden(name)
        if vorhanden is None:
            sub = keycloak.konto_anlegen(name, email=adresse, anzeigename=name,
                                         passwort=passwort)
        else:
            sub = str(vorhanden["id"])
            print(f"  In Keycloak gibt es {name} schon — nur verknuepft.")
        keycloak.gruppen_setzen(sub, ["admins", "users"])
    except Exception as exc:  # noqa: BLE001
        print(f"  Keycloak nicht erreichbar ({type(exc).__name__}).")
        sub = None

    if user is None:
        user = User(username=name, display_name=name, email=adresse)
        db.add(user)

    if sub:
        user.auth_provider = "keycloak"
        user.external_id = sub
        # Kein lokaler Hash. Er waere ein zweiter Weg an Keycloak vorbei.
        user.password_hash = None
        user.must_change_password = False
    else:
        user.auth_provider = "local"
        user.password_hash = hash_password(passwort)
        user.must_change_password = True
    user.is_active = True
    user.token_epoch = (user.token_epoch or 0) + 1

    for slug in ("admins", "users"):
        if groups[slug] not in user.groups:
            user.groups.append(groups[slug])
    db.flush()
    return bool(sub)


def _notzugang(db, groups) -> str | None:
    """Das eine lokale Konto, das bleibt. Gibt sein Passwort zurueck — einmal.

    Existiert es schon, wird es **nicht** angefasst: Ein zweiter Aufruf von
    `make admin` soll nicht stillschweigend das Passwort des Notausgangs
    aendern, das jemand notiert hat.
    """
    vorhanden = db.scalar(select(User).where(User.username == NOTFALL))
    if vorhanden is not None:
        settings_store.put(db, settings_store.BREAKGLASS, NOTFALL)
        return None

    passwort = _passwort(18)
    konto = User(
        username=NOTFALL,
        display_name="Notzugang",
        email=f"{NOTFALL}@ota.invalid",
        password_hash=hash_password(passwort),
        auth_provider="local",
        # Ausdruecklich **kein** erzwungener Wechsel: Wer diesen Zugang
        # braucht, steht vor einer Anlage, die gerade nicht funktioniert.
        # Eine zusaetzliche Huerde ist dann das Letzte, was hilft.
        must_change_password=False,
        is_active=True,
    )
    db.add(konto)
    for slug in ("admins", "users"):
        konto.groups.append(groups[slug])
    db.flush()
    settings_store.put(db, settings_store.BREAKGLASS, NOTFALL)
    return passwort


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OTA einrichten")
    parser.add_argument("--admin", help="Benutzername des ersten Administrators")
    parser.add_argument("--password", help="Passwort setzen (sonst wird eines erzeugt)")
    parser.add_argument("--email", help="E-Mail des Kontos (Pflichtfeld in der Oberflaeche)")
    args = parser.parse_args(argv)

    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        groups = ensure_groups(db)

        if args.admin:
            passwort = args.password or _passwort()
            zentral = _in_keycloak(db, groups, args.admin, args.email, passwort)
            notfall_pw = _notzugang(db, groups)
            db.commit()

            print()
            if zentral:
                print(f"  Administrator in Keycloak angelegt: {args.admin}")
                print(f"  Einmal-Passwort: {passwort}")
                print("  Anmeldung ueber die Startseite; Keycloak verlangt sofort ein eigenes.")
            else:
                print(f"  Administrator lokal angelegt: {args.admin}")
                print(f"  Einmal-Passwort: {passwort}")
                print("  Keycloak war nicht erreichbar — Anmeldung unter /login.")
                print("  Sobald es laeuft:  make identity  und diesen Aufruf wiederholen.")

            if notfall_pw:
                print()
                print(f"  Notzugang angelegt: {NOTFALL}  (lokal, unter /notfall)")
                print(f"  Passwort: {notfall_pw}")
                print("  Er ist der Weg herein, wenn Keycloak einmal nicht antwortet.")
                print("  Bitte notieren — er wird nicht noch einmal gezeigt.")
            print()

        else:
            db.commit()
            print("Systemgruppen sind vorhanden. Für einen Administrator: --admin <name>")

    return 0


if __name__ == "__main__":
    sys.exit(main())
