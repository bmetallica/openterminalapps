"""Passwoerter, Token und die Aufloesung der Ressourcen."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from .config import settings
from .models import Session as SessionModel, Template, User

_hasher = PasswordHasher()

# Bekannt schwache Passwoerter. Bewusst kurz gehalten — die eigentliche
# Pruefung gegen kompromittierte Listen kommt spaeter dazu.
_WEAK = {
    "passwort1234", "password1234", "administrator", "qwertzuiopü",
    "123456789012", "willkommen12", "changeme1234",
}


def hash_password(pw: str) -> str:
    return _hasher.hash(pw)


def verify_password(pw: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        return _hasher.verify(stored, pw)
    except (VerifyMismatchError, InvalidHashError):
        return False


def password_problem(pw: str) -> str | None:
    """Gibt den Grund zurueck, warum ein Passwort abgelehnt wird — oder None."""
    if len(pw) < 12:
        return "Das Passwort muss mindestens 12 Zeichen haben."
    if pw.lower() in _WEAK:
        return "Dieses Passwort ist zu verbreitet. Bitte ein anderes wählen."
    if pw.strip() != pw:
        return "Das Passwort darf nicht mit einem Leerzeichen beginnen oder enden."
    return None


def make_token(user: User, kind: str = "access", minutes: int | None = None) -> str:
    """Baut ein Zugangsmerkmal.

    `minutes` uebersteuert die Frist aus der Konfiguration. Gebraucht wird das
    fuer die rollende Anmeldung: Wie lange jemand angemeldet bleibt, steht in
    der Datenbank und ist im Verwaltungsbereich einstellbar — nicht in einer
    Umgebungsvariablen, die einen Neustart braechte.
    """
    s = settings()
    now = datetime.now(timezone.utc)
    if minutes is not None:
        lifetime = timedelta(minutes=minutes)
    else:
        lifetime = (
            timedelta(minutes=s.access_token_minutes)
            if kind == "access"
            else timedelta(days=s.refresh_token_days)
        )
    payload = {
        "sub": str(user.id),
        "typ": kind,
        "epoch": user.token_epoch,
        "iat": int(now.timestamp()),
        "exp": int((now + lifetime).timestamp()),
        "jti": secrets.token_urlsafe(12),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def read_token(token: str) -> dict | None:
    s = settings()
    try:
        return jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
    except jwt.PyJWTError:
        return None


def vnc_secret(user: User, profile: str) -> str:
    """Das KasmVNC-Passwort dieser Session. Sieht der Browser nie.

    Frueher war das ein Zufallswert je Session. Das war falsch, und der Fehler
    war heimtueckisch:

    Alle Sessions eines Nutzers teilen sich dasselbe `/home/kasm-user` — das
    ist der Sinn des persistenten Profils. Der Startvorgang der Kasm-Images
    schreibt aber bei *jedem* Containerstart `~/.kasmpasswd` aus `VNC_PW` neu.
    Startete jemand eine zweite Session, ueberschrieb sie damit das Passwort
    der ersten. Die lief weiter, ihr Bild lief weiter — aber jede neue Anfrage
    an ihren Stream bekam 401, ohne dass sich an der laufenden Session
    irgendetwas geaendert haette. Gemessen am 2026-08-27: Arbeitsplatz um
    10:29 gestartet, VS Code um 11:12 dazu, danach antworteten alle Displays
    des Arbeitsplatzes mit 401.

    Deshalb haengt das Passwort jetzt am Profil und nicht an der Session: Wer
    sich dasselbe Zuhause teilt, teilt sich auch den Zugang. Das schwaecht
    nichts ab — es ist dieselbe Person, und die Datei liegt ohnehin in genau
    diesem Zuhause.

    Abgeleitet statt gespeichert, damit es keine weitere Spalte braucht, die
    mit der Wirklichkeit auseinanderlaufen kann. Ohne Profil (fluechtige
    Sessions) hat jeder Container sein eigenes Zuhause — dann darf und soll
    das Passwort je Container verschieden sein.
    """
    if not profile:
        return secrets.token_urlsafe(24)[:32]
    material = f"vnc:{user.id}:{profile}".encode()
    digest = hmac.new(settings().jwt_secret.encode(), material, hashlib.sha256).digest()
    # urlsafe-Base64 ohne Polster: KasmVNC nimmt das Passwort als Zeichenkette,
    # und ein "=" am Ende hat in Basic-Auth schon oft genug Aerger gemacht.
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")[:32]


# --------------------------------------------------------------------------
# Ressourcen-Aufloesung
# --------------------------------------------------------------------------

def effective_resources(tpl: Template, user: User) -> tuple[float, int, str, str]:
    """Ermittelt die geltenden Ressourcen fuer ein Paar (Nutzer, Template).

    Reihenfolge nach plan.md §5 — das Spezifischste gewinnt:
      1. Vorgabe der Vorlage
      2. Abweichung je Gruppe, in Reihenfolge der Gruppen-Prioritaet
      3. Abweichung je Nutzer

    Rueckgabe: (cores, memory_bytes, herkunft_cores, herkunft_memory)
    """
    cores, memory = tpl.cores, tpl.memory_bytes
    from_cores = from_mem = "Vorlage"

    by_group = {
        o.target_id: o for o in tpl.overrides if o.scope == "group"
    }
    # Niedrige priority-Zahl gewinnt, deshalb absteigend anwenden.
    for group in sorted(user.groups, key=lambda g: g.priority, reverse=True):
        o = by_group.get(group.id)
        if not o:
            continue
        if o.cores is not None:
            cores, from_cores = o.cores, "Gruppe"
        if o.memory_bytes is not None:
            memory, from_mem = o.memory_bytes, "Gruppe"

    for o in tpl.overrides:
        if o.scope == "user" and o.target_id == user.id:
            if o.cores is not None:
                cores, from_cores = o.cores, "Nutzer"
            if o.memory_bytes is not None:
                memory, from_mem = o.memory_bytes, "Nutzer"

    return cores, memory, from_cores, from_mem


def user_can_see_template(tpl: Template, user: User) -> bool:
    if user.is_admin:
        return True
    if not tpl.is_enabled:
        return False
    user_groups = {g.id for g in user.groups}
    return any(g.id in user_groups for g in tpl.groups)


def user_can_see_app(app, user: User) -> bool:
    """Darf dieser Nutzer diese Anwendung im Arbeitsplatz sehen und starten?

    Voraussetzung ist immer, dass er den Arbeitsplatz selbst sehen darf; das
    entscheidet `user_can_see_template`. Hier geht es nur um die Anwendung
    darin — etwa eine Lizenz, die nur ein Teil der Belegschaft hat.

    **Eine Anwendung ohne Gruppen ist fuer alle da.** Andersherum waere jeder
    bestehende Katalog mit dem Einfuehren dieser Regel unsichtbar geworden.
    """
    if user.is_admin:
        return True
    if not app.is_enabled:
        return False
    wanted = app.group_ids or []
    if not wanted:
        return True
    mine = {str(g.id) for g in user.groups}
    return any(str(g) in mine for g in wanted)


def owns_session(sess: SessionModel, user: User) -> bool:
    return sess.user_id == user.id or "sessions.view_all" in user.permissions or user.is_admin


def profile_path(user: User, tpl: Template) -> str:
    """Wohin das persistente Home dieses Nutzers gemountet wird."""
    root = settings().profiles_root.rstrip("/")
    if tpl.persistence_scope == "template":
        return f"{root}/{user.username}/{tpl.slug}"
    if tpl.persistence_scope == "none":
        return ""
    return f"{root}/{user.username}/user"


def as_uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None
