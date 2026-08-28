"""Einstellungen, die zur Laufzeit aenderbar sein muessen.

Abgrenzung zu `config.py`: Dort steht, was beim Start aus der Umgebung kommt
und einen Neustart braucht — Datenbankadresse, Geheimnisse, Pfade. Hier steht,
was ein Administrator im laufenden Betrieb ueber die Oberflaeche dreht.

Die Werte liegen in der Tabelle `settings` als JSON. Ein winziger Zwischen-
speicher haelt sie im Prozess, damit nicht jede einzelne Anfrage die Datenbank
fragt — die Anmeldefrist wird bei *jedem* Request gebraucht.
"""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy.orm import Session as DbSession

from .models import Setting

# Wie lange jemand angemeldet bleibt, ohne etwas zu tun. Die Sitzung ist
# rollend: Jede Anfrage schiebt die Frist nach vorn. Wer arbeitet, wird nie
# herausgeworfen; wer den Rechner verlaesst, irgendwann schon.
AUTH_IDLE_MINUTES = "auth.idle_minutes"

# Die Stufen, die die Oberflaeche anbietet. Kein freies Zahlenfeld: Zwischen
# 30 Minuten und zwei Tagen gibt es keine Zahl, deren genauer Wert jemandem
# etwas bedeutet — die Groessenordnung ist die Entscheidung.
IDLE_STEPS = (30, 60, 120, 240, 480, 720, 1440, 2880)

# Wie viel Platz das Zuhause eines Nutzers belegen darf, in Gigabyte.
# 0 heisst: keine Grenze.
PROFILE_QUOTA_GB = "storage.profile_quota_gb"

# Wie viel freier Plattenplatz mindestens bleiben muss, damit noch eine
# Session startet. Ein volles Dateisystem ist kein Fehler, den ein Nutzer
# versteht — es ist ein Container, der beim Schreiben stehenbleibt.
DISK_FLOOR_GB = "storage.disk_floor_gb"

# Wohin eine externe Anwendung ihre Token bekommen darf.
#
# **Leer heisst: nichts ist erlaubt** — nicht: alles. Eine Schranke, die im
# Auslieferungszustand offen steht, wird nie geschlossen (auth-roadmap.md
# §5d). Eingetragen werden vollstaendige Herkuenfte mit Schema, damit ein
# `http://` sichtbar eine Entscheidung ist und kein Versehen.
APP_ORIGINS = "apps.allowed_origins"

DEFAULTS: dict[str, Any] = {
    # Acht Stunden: ein Arbeitstag. Wer morgens kommt, meldet sich einmal an.
    AUTH_IDLE_MINUTES: 480,
    PROFILE_QUOTA_GB: 20,
    DISK_FLOOR_GB: 5,
}

_cache: dict[str, tuple[float, Any]] = {}
_TTL = 5.0


def get(db: DbSession, key: str) -> Any:
    hit = _cache.get(key)
    now = time.monotonic()
    if hit and now - hit[0] < _TTL:
        return hit[1]

    row = db.get(Setting, key)
    value = row.value.get("v") if row and isinstance(row.value, dict) else None
    if value is None:
        value = DEFAULTS.get(key)
    _cache[key] = (now, value)
    return value


def put(db: DbSession, key: str, value: Any) -> None:
    row = db.get(Setting, key)
    if row is None:
        row = Setting(key=key, value={"v": value})
        db.add(row)
    else:
        row.value = {"v": value}
    _cache.pop(key, None)


def idle_minutes(db: DbSession) -> int:
    """Die Anmeldefrist, auf eine der angebotenen Stufen gerundet.

    Gerundet wird auch beim Lesen, nicht nur beim Schreiben: Ein Wert, der
    ueber die Datenbank von Hand hineingeraten ist, soll die Anmeldung nicht
    auf fuenf Sekunden setzen koennen.
    """
    raw = get(db, AUTH_IDLE_MINUTES)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULTS[AUTH_IDLE_MINUTES]
    return min(IDLE_STEPS, key=lambda step: abs(step - value))


def profile_quota_bytes(db: DbSession) -> int:
    """Die Grenze je Zuhause in Bytes. 0 heisst: keine."""
    try:
        gb = max(0, int(get(db, PROFILE_QUOTA_GB)))
    except (TypeError, ValueError):
        gb = DEFAULTS[PROFILE_QUOTA_GB]
    return gb * 1024 ** 3


def disk_floor_bytes(db: DbSession) -> int:
    """Was auf der Platte frei bleiben muss. 0 heisst: keine Untergrenze."""
    try:
        gb = max(0, int(get(db, DISK_FLOOR_GB)))
    except (TypeError, ValueError):
        gb = DEFAULTS[DISK_FLOOR_GB]
    return gb * 1024 ** 3


def allowed_origins(db: DbSession) -> list[str]:
    """Die erlaubten Ziele fuer externe Anwendungen. Leer heisst: keine."""
    wert = get(db, APP_ORIGINS)
    if isinstance(wert, list):
        return [str(x).strip().rstrip("/") for x in wert if str(x).strip()]
    return []
