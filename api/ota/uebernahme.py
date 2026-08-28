"""Bestandskonten nach Keycloak übernehmen (auth-roadmap.md, Etappe E).

Der Beschluss aus §5.1: Konten werden übernommen, Passwörter **einmalig neu**
vergeben. Ein Import der vorhandenen Argon2id-Hashes wäre der bequemere Weg
und der schlechtere — er hängt an übereinstimmenden Parametern und scheitert
im Zweifel **still**: Es fällt erst auf, wenn sich jemand nicht anmelden kann.

Drei Eigenschaften, und alle drei sind Absicht:

* **Wiederholbar.** Ein Lauf, der beim zweiten Aufruf Konten doppelt anlegt,
  wäre unbrauchbar. Abgeglichen wird über den Anmeldenamen; angelegt wird nur,
  was fehlt.
* **Ohne Notfallkonto läuft gar nichts.** Wer alle Konten auf einen Dienst
  umstellt, der ausfallen kann, muss vorher einen Weg zurück haben. Solange
  keines bestimmt und geprüft ist, verweigert dieser Lauf die Arbeit (§5.2).
* **Das Notfallkonto wird nie übernommen.** Es ist der Ausweg; ein Ausweg, der
  durch dieselbe Tür führt wie der Weg hinein, ist keiner.
"""

from __future__ import annotations

import logging
import secrets
import string

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from . import keycloak, settings_store
from .models import User

log = logging.getLogger("ota.uebernahme")

# Lesbar am Telefon: keine Zeichen, die sich verwechseln lassen.
ALPHABET = "".join(c for c in string.ascii_letters + string.digits
                   if c not in "0O1lI")


class NichtBereit(Exception):
    """Die Voraussetzungen stimmen nicht. Der Text sagt, welche."""


def einmalpasswort(laenge: int = 14) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(laenge))


def _pruefe_bereit(db: DbSession) -> User:
    """Gibt das Notfallkonto zurück — oder erklärt, warum nichts läuft."""
    name = settings_store.breakglass(db)
    if not name:
        raise NichtBereit(
            "Es ist kein Notfallkonto bestimmt. Solange keines besteht, wird "
            "hier nichts übernommen: Wer alle Konten auf einen Dienst "
            "umstellt, der ausfallen kann, braucht vorher einen Weg zurück."
        )

    konto = db.scalar(select(User).where(User.username == name))
    if konto is None:
        raise NichtBereit(f"Das Notfallkonto „{name}“ gibt es nicht.")
    if konto.auth_provider != "local" or not konto.password_hash:
        raise NichtBereit(
            f"Das Notfallkonto „{name}“ hat kein lokales Passwort. Genau das "
            "ist aber sein Zweck — es soll ohne Keycloak funktionieren."
        )
    if not konto.is_admin:
        raise NichtBereit(f"Das Notfallkonto „{name}“ ist kein Administrator.")
    if not konto.is_active or konto.is_locked:
        raise NichtBereit(f"Das Notfallkonto „{name}“ ist nicht benutzbar.")

    if not keycloak.erreichbar():
        raise NichtBereit(
            "Keycloak antwortet gerade nicht. Konten dorthin zu übernehmen, "
            "während es schweigt, wäre der schlechteste Zeitpunkt."
        )
    return konto


def offen(db: DbSession) -> list[User]:
    """Welche Konten noch zu übernehmen sind."""
    notfall = settings_store.breakglass(db)
    alle = db.scalars(select(User).order_by(User.username)).all()
    return [u for u in alle
            if u.auth_provider == "local" and u.username != notfall]


def lauf(db: DbSession, *, probe: bool = True) -> dict:
    """Übernimmt die Bestandskonten. `probe=True` ändert nichts.

    Zurück kommt je Konto ein Einmal-Passwort. Es wird **einmal** gezeigt und
    nirgends gespeichert — beim ersten Anmelden vergibt der Mensch sein
    eigenes (erforderliche Aktion in Keycloak).
    """
    notfall = _pruefe_bereit(db)
    zu_tun = offen(db)

    ergebnis: dict = {
        "probe": probe,
        "notfallkonto": notfall.username,
        "offen": len(zu_tun),
        "uebernommen": [],
        "uebersprungen": [],
        "gescheitert": [],
    }

    for user in zu_tun:
        gruppen = sorted(g.name for g in user.groups)
        zweiter_faktor = any(getattr(g, "require_totp", False) for g in user.groups)

        if probe:
            ergebnis["uebernommen"].append({
                "username": user.username, "gruppen": gruppen,
                "zweiter_faktor": zweiter_faktor, "passwort": None,
            })
            continue

        try:
            vorhanden = keycloak.konto_finden(user.username)
            if vorhanden is not None:
                # Es gibt den Namen dort schon — etwa aus einem früheren Lauf
                # oder aus dem Verzeichnis. Dann wird verknüpft und nicht
                # überschrieben: Ein bestehendes Konto anzufassen ist genau
                # das, was hier niemand tun soll.
                sub = str(vorhanden["id"])
                passwort = None
                ergebnis["uebersprungen"].append({
                    "username": user.username,
                    "grund": "In Keycloak gibt es diesen Namen schon — nur verknüpft.",
                })
            else:
                passwort = einmalpasswort()
                sub = keycloak.konto_anlegen(
                    user.username, email=user.email,
                    anzeigename=user.display_name, passwort=passwort,
                )
                ergebnis["uebernommen"].append({
                    "username": user.username, "gruppen": gruppen,
                    "zweiter_faktor": zweiter_faktor, "passwort": passwort,
                })

            keycloak.gruppen_setzen(sub, gruppen)
            if zweiter_faktor:
                keycloak.rolle_setzen(sub, "zweiter-faktor", True)

            user.auth_provider = "keycloak"
            user.external_id = sub
            # Der lokale Hash geht weg. Ihn stehenzulassen hiesse, einen
            # zweiten Weg offenzuhalten — an Keycloak und der zweiten Stufe
            # vorbei.
            user.password_hash = None
            user.must_change_password = False
            user.totp_secret = None
            user.totp_recovery = []
            db.flush()
            log.info("Konto %s nach Keycloak übernommen (%s)", user.username, sub[:8])

        except (keycloak.KeycloakFehler, Exception) as exc:  # noqa: BLE001
            ergebnis["gescheitert"].append({
                "username": user.username, "grund": str(exc)[:200],
            })
            log.warning("Konto %s nicht übernommen: %s", user.username, exc)

    if not probe:
        db.commit()
    return ergebnis
