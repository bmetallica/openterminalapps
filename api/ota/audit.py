from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session as DbSession

from .models import AuditLog, User


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
    ip = None
    if request is not None:
        ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (
            request.client.host if request.client else None
        )
    db.add(AuditLog(
        actor_user_id=actor.id if actor else None,
        actor_name=actor.username if actor else None,
        action=action,
        object_type=object_type,
        object_id=str(object_id) if object_id else None,
        ip=ip,
        detail=detail,
    ))
