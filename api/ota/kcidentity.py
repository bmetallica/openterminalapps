"""Aus einem Keycloak-Token ein OTA-Konto machen — und nur so viel wie nötig.

Die Schwesterdatei zu [`identity.py`](identity.py), mit denselben Regeln und
demselben Misstrauen. Der Unterschied ist der Schlüssel:

* Das Verzeichnis kannte OTA über den DN, und der Anmeldename war der
  Schlüssel. Das ging so lange gut, bis jemand heiratet.
* Keycloak liefert `sub` — eine Kennung, die sich nie ändert. **Sie ist der
  Schlüssel.** Der Anmeldename ist nur noch eine Beschriftung, die sich
  ändern darf, ohne dass jemand sein Zuhause verliert.

Drei Regeln, und alle drei sind Absicht:

1. **Ein lokales Konto wird nie übernommen.** Meldet sich jemand über
   Keycloak an und es gibt hier ein gleichnamiges lokales Konto, wird
   abgelehnt statt zugeordnet. Genau derselbe Angriff wie beim Verzeichnis:
   Wer in Keycloak ein Konto anlegen darf, legte sonst eines mit dem Namen
   des ersten Administrators an.
2. **Der Name folgt dem `sub`, nicht umgekehrt.** Ändert sich der Anmeldename
   in Keycloak, wird er hier nachgezogen — dasselbe Konto bleibt dasselbe.
3. **Gruppen kommen bei jeder Anmeldung mit**, und zwar nur die, die es in
   OTA wirklich gibt. Eine Gruppe in Keycloak ist eine Beschriftung; welche
   Rechte daran hängen, entscheidet OTA (auth-roadmap.md §4).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from .models import Group, User

log = logging.getLogger("ota.kcidentity")

KEYCLOAK = "keycloak"


class Abgelehnt(Exception):
    """Der Anmeldeversuch ist gültig, aber OTA nimmt ihn nicht an.

    Die Meldung ist für den Menschen vor dem Bildschirm gedacht und sagt, was
    zu tun ist — nicht, was intern schiefging.
    """


def gruppen_dazu(db: DbSession, namen: list[str]) -> list[Group]:
    """Die OTA-Gruppen zu diesen Namen. Unbekannte werden übergangen.

    Bewusst **kein** Anlegen fehlender Gruppen: Eine Gruppe in OTA trägt
    Rechte. Sie aus einem Namen entstehen zu lassen, den irgendwer in
    Keycloak vergeben hat, hiesse, die Rechtevergabe dorthin auszulagern.
    """
    if not namen:
        return []
    gefunden = db.scalars(select(Group).where(Group.name.in_(namen))).all()
    unbekannt = sorted(set(namen) - {g.name for g in gefunden})
    if unbekannt:
        log.debug("Gruppen ohne Entsprechung in OTA: %s", ", ".join(unbekannt))
    return list(gefunden)


def finde(db: DbSession, sub: str) -> User | None:
    """Das Konto zu dieser Keycloak-Kennung."""
    if not sub:
        return None
    return db.scalar(select(User).where(
        User.auth_provider == KEYCLOAK, User.external_id == sub))


def anmelden(db: DbSession, angaben: dict) -> User:
    """Das Konto zu diesen geprüften Angaben — anlegen oder auffrischen.

    Der Aufrufer hat das Token bereits geprüft (`keycloak.pruefe_token`).
    Hier geht es nur noch darum, wem es in OTA entspricht.
    """
    sub = angaben.get("sub") or ""
    name = (angaben.get("username") or "").strip().lower()
    if not sub or not name:
        raise Abgelehnt("Das Token nennt weder Kennung noch Anmeldenamen.")

    user = finde(db, sub)

    if user is None:
        # Zweiter Blick: Gibt es den Namen schon, aber mit anderer Herkunft?
        fremd = db.scalar(select(User).where(User.username == name))
        if fremd is not None:
            log.warning(
                "Keycloak-Konto %r (%s) trifft auf ein bestehendes %s-Konto. "
                "Es wird nicht übernommen.", name, sub[:8], fremd.auth_provider)
            raise Abgelehnt(
                f"Es gibt hier bereits ein Konto „{name}“, das nicht über "
                "Keycloak angelegt wurde. Ein bestehendes Konto wird nicht "
                "übernommen — die Verwaltung muss es zuerst übertragen."
            )

        user = User(
            username=name,
            display_name=angaben.get("display_name") or None,
            email=angaben.get("email") or None,
            # Kein Passwort. Ein Keycloak-Konto hat hier keines, und ein
            # zufälliges hinzuschreiben wäre eines, das niemand kennt und das
            # trotzdem geprüft würde, wenn jemand `auth_provider` umstellt.
            password_hash=None,
            auth_provider=KEYCLOAK,
            external_id=sub,
            is_active=True,
            must_change_password=False,
        )
        db.add(user)
        db.flush()
        log.info("Konto %s aus Keycloak angelegt (%s)", name, sub[:8])

    else:
        if user.username != name:
            log.info("Konto %s heisst jetzt %s (%s)", user.username, name, sub[:8])
            user.username = name
        user.display_name = angaben.get("display_name") or user.display_name
        user.email = angaben.get("email") or user.email

    if not user.is_active:
        raise Abgelehnt("Dieses Konto ist in OTA deaktiviert.")
    if user.is_locked:
        raise Abgelehnt("Dieses Konto ist gesperrt.")

    # Gruppen bei jeder Anmeldung. Ein Entzug wirkt damit beim nächsten Mal —
    # so entschieden, weil eine Gruppenänderung im Verzeichnis in aller Regel
    # organisatorisch ist und niemandem mitten im Satz den Editor wegnehmen
    # soll (auth-roadmap.md §5c). Sofort wirkt die Sperre, nicht dies hier.
    user.groups = gruppen_dazu(db, angaben.get("groups") or [])
    user.last_login_at = datetime.now(timezone.utc)
    user.failed_logins = 0
    db.flush()
    return user
