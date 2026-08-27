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

DEFAULTS: dict[str, Any] = {
    # Acht Stunden: ein Arbeitstag. Wer morgens kommt, meldet sich einmal an.
    AUTH_IDLE_MINUTES: 480,
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
