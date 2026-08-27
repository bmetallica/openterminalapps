"""Zweiter Faktor: Einrichtung, Rückfallcodes, Prüfung.

Die *Prüfung* beim Anmelden gab es von Anfang an — nur einrichten liess sich
nichts. Wer ein Geheimnis von Hand in die Datenbank schrieb, hatte einen
zweiten Faktor; alle anderen nicht.

Zwei Entscheidungen prägen diese Datei:

**Rückfallcodes sind Pflicht, nicht Zubehör.** Wer sein Telefon verliert, käme
sonst nicht mehr herein — und die Antwort darauf darf nicht „ein Administrator
schaltet den zweiten Faktor ab" sein. Genau das wäre die Hintertür, die er
verhindern soll. Deshalb entstehen die Codes bei der Einrichtung, werden
**einmal** gezeigt und danach nur noch gehasht aufbewahrt, wie Passwörter.

**Ein Code gilt genau einmal.** Er wird beim Einlösen aus der Liste entfernt,
nicht als „benutzt" markiert — was weg ist, kann nicht wiederverwendet werden.
"""

from __future__ import annotations

import io
import secrets

import pyotp
import qrcode
from qrcode.image.svg import SvgPathImage

from .security import hash_password, verify_password

# Der Name, unter dem der Eintrag in der Authenticator-App erscheint.
ISSUER = "OpenTerminalApps"

# Zehn Codes, je zehn Zeichen aus einem Alphabet ohne Verwechslungspaare:
# kein 0/O, kein 1/l/I. Sie werden abgeschrieben, oft von Papier.
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_COUNT = 10
CODE_LEN = 10


def new_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, username: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=username, issuer_name=ISSUER)


def qr_svg(uri: str) -> str:
    """Der Einrichtungscode als SVG.

    Als SVG und nicht als PNG: Es bleibt bei jeder Grösse scharf, geht ohne
    Bildbibliothek (kein Pillow) und laesst sich als Text durch die API
    reichen.
    """
    image = qrcode.make(uri, image_factory=SvgPathImage, box_size=10, border=2)
    buffer = io.BytesIO()
    image.save(buffer)
    return buffer.getvalue().decode("utf-8")


def verify(secret: str, code: str) -> bool:
    """Prueft einen Zeitcode.

    `valid_window=1` laesst den vorherigen und den naechsten Zeitschritt zu —
    eine Uhr, die eine halbe Minute nachgeht, ist der haeufigste Grund fuer
    einen abgelehnten richtigen Code.
    """
    if not secret or not code:
        return False
    return pyotp.TOTP(secret).verify(code.strip().replace(" ", ""), valid_window=1)


def new_recovery_codes() -> tuple[list[str], list[str]]:
    """Erzeugt Rueckfallcodes. Gibt (Klartext, gehasht) zurueck.

    Der Klartext wird genau einmal gezeigt und danach vergessen.
    """
    plain = [
        "-".join(
            "".join(secrets.choice(ALPHABET) for _ in range(5))
            for _ in range(CODE_LEN // 5)
        )
        for _ in range(CODE_COUNT)
    ]
    return plain, [hash_password(code) for code in plain]


def redeem(stored: list[str], code: str) -> list[str] | None:
    """Loest einen Rueckfallcode ein.

    Zurueck kommt die verbleibende Liste — oder None, wenn der Code nicht
    passt. Der eingeloeste wird entfernt, nicht markiert: Was weg ist, laesst
    sich nicht wiederverwenden.
    """
    candidate = (code or "").strip().upper().replace(" ", "")
    if not candidate:
        return None
    for index, hashed in enumerate(stored or []):
        if verify_password(candidate, hashed):
            return [h for i, h in enumerate(stored) if i != index]
    return None


def looks_like_recovery(code: str) -> bool:
    """Unterscheidet einen Rueckfallcode von einem Zeitcode.

    Zeitcodes sind sechs Ziffern; Rueckfallcodes enthalten Buchstaben und
    Bindestriche. Ohne diese Unterscheidung muesste jede fehlgeschlagene
    Anmeldung beide Wege durchprobieren — und jeder Versuch waere ein
    Argon2-Durchlauf je gespeichertem Code.
    """
    cleaned = (code or "").strip().replace(" ", "")
    return bool(cleaned) and not (cleaned.isdigit() and len(cleaned) <= 8)


__all__ = [
    "ALPHABET", "ISSUER",
    "new_secret", "provisioning_uri", "qr_svg", "verify",
    "new_recovery_codes", "redeem", "looks_like_recovery",
]
