from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session as DbSession

from .models import AuditLog, User


def absender(request: Request | None) -> str | None:
    """Von welcher Adresse die Anfrage kam.

    **Wem wir dabei glauben:** Den Kopf `X-Forwarded-For` setzt Traefik selbst;
    einen mitgeschickten uebernimmt es nur von Absendern, die in
    `OTA_TRUSTED_PROXIES` stehen. Ohne diese Kette waere der Wert frei waehlbar
    — und eine Bremse, die sich am Absender orientiert, waere wirkungslos: Wer
    den Kopf selbst setzt, ist bei jedem Versuch jemand anderes.

    Diese Funktion steht hier und nicht zweimal im Quelltext, weil das Protokoll
    und die Anmeldebremse dieselbe Adresse meinen muessen. Sonst steht im
    Protokoll ein anderer Absender als der, den die Bremse gezaehlt hat.
    """
    if request is None:
        return None
    return request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (
        request.client.host if request.client else None
    )


def record(
    db: DbSession,
    action: str,
    *,
    actor: User | None = None,
    object_type: str | None = None,
    object_id: str | None = None,
    request: Request | None = None,
    **detail,
) -> None:
    """Schreibt einen Audit-Eintrag. Inhalte werden nie erfasst, nur Vorgaenge."""
    ip = absender(request)
    db.add(AuditLog(
        actor_user_id=actor.id if actor else None,
        actor_name=actor.username if actor else None,
        action=action,
        object_type=object_type,
        object_id=str(object_id) if object_id else None,
        ip=ip,
        detail=detail,
    ))
