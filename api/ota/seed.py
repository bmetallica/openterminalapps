"""Erstbefuellung: Systemgruppen und der erste Administrator.

Aufruf:  python -m ota.seed --admin <name>
"""

from __future__ import annotations

import argparse
import secrets
import sys

from sqlalchemy import select

from .db import Base, SessionLocal, engine
from .models import Group, User
from .security import hash_password

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OTA einrichten")
    parser.add_argument("--admin", help="Benutzername des ersten Administrators")
    parser.add_argument("--password", help="Passwort setzen (sonst wird eines erzeugt)")
    args = parser.parse_args(argv)

    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        groups = ensure_groups(db)

        if args.admin:
            user = db.scalar(select(User).where(User.username == args.admin))
            password = args.password or secrets.token_urlsafe(12)

            if user is None:
                user = User(
                    username=args.admin,
                    display_name=args.admin,
                    password_hash=hash_password(password),
                    must_change_password=not args.password,
                )
                db.add(user)
                created = True
            else:
                user.password_hash = hash_password(password)
                user.must_change_password = not args.password
                user.token_epoch += 1
                created = False

            for slug in ("admins", "users"):
                if groups[slug] not in user.groups:
                    user.groups.append(groups[slug])

            db.commit()
            print()
            print(f"  Administrator {'angelegt' if created else 'aktualisiert'}: {args.admin}")
            if not args.password:
                print(f"  Einmal-Passwort: {password}")
                print("  Muss bei der ersten Anmeldung gewechselt werden.")
            print()
        else:
            db.commit()
            print("Systemgruppen sind vorhanden. Für einen Administrator: --admin <name>")

    return 0


if __name__ == "__main__":
    sys.exit(main())
