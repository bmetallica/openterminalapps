from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from .. import agent_client, audit
import os
import re
from ..db import get_db
from ..deps import current_user, require_permission
from ..models import (
    PERMISSIONS, AuditLog, Group, GroupMember, Session as SessionModel,
    Template, User,
)
from ..schemas import (
    GroupIn, GroupOut, HostOut, ImagePullIn, SessionAdminOut, SettingsIn,
    UserIn, UserOut,
)
from ..security import hash_password, password_problem
from .. import settings_store

router = APIRouter(prefix="/api/admin", tags=["admin"])

manage_users = require_permission("users.manage")
manage_groups = require_permission("groups.manage")


@router.get("/host")
def host(_: User = Depends(require_permission("admin", "settings.manage"))) -> HostOut:
    return HostOut(**agent_client.host_info())


manage_images = require_permission("images.manage", "templates.manage")

# Eine Image-Adresse, wie Docker sie versteht: optionale Registry mit Port,
# Pfad, Tag oder Digest. Bewusst streng — was hier durchkommt, wandert in
# einen Aufruf an die Docker-API.
IMAGE_REF = re.compile(
    r"^(?:[a-z0-9.-]+(?::\d{1,5})?/)?"      # Registry, optional
    r"[a-z0-9]+(?:[._-][a-z0-9]+)*"          # erster Pfadteil
    r"(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)*"    # weitere Pfadteile
    r"(?::[\w][\w.-]{0,127})?"               # Tag
    r"(?:@sha256:[a-f0-9]{64})?$"            # oder Digest
)

# Woher ein Image stammt, ist am Namen ablesbar und fuer die Oberflaeche
# wichtiger als der Name selbst: Ein Kasm-Image gehoert dem anderen System auf
# diesem Host und wird von OTA nicht angefasst.
# Die eigene Registry traegt dieselben Images wie der Store — nur mit ihrer
# Adresse davor. Ohne diese Zeile stuenden die eigenen Golden Images nach dem
# Ablegen dort unter "Uebrige".
OTA_REGISTRY = os.environ.get("OTA_REGISTRY", "127.0.0.1:5000").strip()


def _origin(ref: str) -> str:
    if ref.startswith("ota/"):
        return "ota"
    if OTA_REGISTRY and ref.startswith(f"{OTA_REGISTRY}/ota/"):
        return "ota"
    if "kasmweb/" in ref or ref.startswith("kasmregistry"):
        return "kasm"
    return "fremd"


@router.get("/images")
def images(db: DbSession = Depends(get_db),
           _: User = Depends(manage_images)) -> list[dict]:
    """Die auf dem Host vorhandenen Images.

    Mit zwei Angaben, die die blosse Liste nicht hat: woher das Image stammt,
    und welcher Workspace es gerade benutzt. Ohne die zweite ist "loeschen"
    ein Ratespiel.
    """
    used: dict[str, list[str]] = {}
    for tpl in db.scalars(select(Template)).all():
        used.setdefault(tpl.image_ref, []).append(tpl.friendly_name)

    out = []
    for entry in agent_client.list_images():
        ref = entry["ref"]
        out.append({**entry, "origin": _origin(ref), "used_by": used.get(ref, [])})
    return out


@router.post("/images/pull", dependencies=[Depends(manage_images)])
def pull_image(body: ImagePullIn, request: Request,
               actor: User = Depends(manage_images),
               db: DbSession = Depends(get_db)) -> dict:
    """Holt ein Image aus seiner Registry auf diesen Host.

    Damit ist die Auswahlliste kein geschlossener Kreis mehr: Bisher liess
    sich nur waehlen, was zufaellig schon dalag.
    """
    ref = body.ref.strip()
    if not IMAGE_REF.match(ref):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Das sieht nicht nach einer Image-Adresse aus. Beispiel: "
            "kasmweb/gimp:1.18.0-rolling-weekly",
        )
    job = agent_client.pull_image(ref)
    audit.record(db, "image.pull", actor=actor, object_type="image",
                 object_id=ref, request=request)
    db.commit()
    return job


@router.get("/images/pull/{job_id}", dependencies=[Depends(manage_images)])
def pull_status(job_id: str) -> dict:
    return agent_client.pull_status(job_id)


@router.delete("/images", dependencies=[Depends(manage_images)])
def remove_image(ref: str, request: Request,
                 actor: User = Depends(manage_images),
                 db: DbSession = Depends(get_db)) -> dict:
    """Entfernt ein Image vom Host.

    Nicht, solange ein Workspace es benutzt: Der liesse sich danach nicht mehr
    starten, und die Meldung dazu kaeme erst beim naechsten Klick eines
    Nutzers.
    """
    in_use = db.scalars(select(Template).where(Template.image_ref == ref)).all()
    if in_use:
        names = ", ".join(t.friendly_name for t in in_use)
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Dieses Image ist in Benutzung: {names}. Stelle die Workspaces "
            "erst auf ein anderes Image um.",
        )
    if _origin(ref) == "kasm":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Das ist ein Image von Kasm. OTA fasst fremde Images nicht an — "
            "gelöscht wird es dort, wo es hergekommen ist.",
        )
    result = agent_client.remove_image(ref)
    audit.record(db, "image.removed", actor=actor, object_type="image",
                 object_id=ref, request=request)
    db.commit()
    return result


# --------------------------------------------------------------------------
# Nutzer
# --------------------------------------------------------------------------

def _user_out(u: User) -> UserOut:
    data = UserOut.model_validate(u)
    data.group_ids = [g.id for g in u.groups]
    return data


@router.get("/users", dependencies=[Depends(manage_users)])
def list_users(db: DbSession = Depends(get_db)) -> list[UserOut]:
    return [_user_out(u) for u in db.scalars(select(User).order_by(User.username)).all()]


@router.post("/users", dependencies=[Depends(manage_users)],
             status_code=status.HTTP_201_CREATED)
def create_user(
    body: UserIn,
    request: Request,
    actor: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> UserOut:
    if db.scalar(select(User).where(User.username == body.username)):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Der Benutzername {body.username} ist schon vergeben.")
    if body.password:
        problem = password_problem(body.password)
        if problem:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, problem)

    user = User(
        username=body.username,
        display_name=body.display_name,
        email=body.email,
        is_active=body.is_active,
        password_hash=hash_password(body.password) if body.password else None,
        must_change_password=bool(body.password),
    )
    user.groups = list(db.scalars(select(Group).where(Group.id.in_(body.group_ids))).all())
    db.add(user)
    audit.record(db, "user.created", actor=actor, object_type="user",
                 object_id=body.username, request=request)
    db.commit()
    return _user_out(user)


@router.put("/users/{user_id}", dependencies=[Depends(manage_users)])
def update_user(
    user_id: uuid.UUID,
    body: UserIn,
    request: Request,
    actor: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> UserOut:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nutzer nicht gefunden")

    new_groups = list(db.scalars(select(Group).where(Group.id.in_(body.group_ids))).all())

    # Der letzte aktive lokale Administrator darf sich seine Rechte nicht nehmen.
    if user.is_admin and not any("admin" in (g.permissions or []) for g in new_groups):
        if _admin_count(db) <= 1:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Das ist der letzte Administrator. Ohne ihn kommt niemand mehr "
                "in die Verwaltung. Lege zuerst einen zweiten an.",
            )

    user.display_name = body.display_name
    user.email = body.email
    user.is_active = body.is_active
    user.groups = new_groups
    if body.password:
        problem = password_problem(body.password)
        if problem:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, problem)
        user.password_hash = hash_password(body.password)
        user.must_change_password = True
        user.token_epoch += 1

    audit.record(db, "user.updated", actor=actor, object_type="user",
                 object_id=user.username, request=request)
    db.commit()
    return _user_out(user)


def _admin_count(db: DbSession) -> int:
    total = 0
    for u in db.scalars(select(User).where(User.is_active.is_(True))).all():
        if u.is_admin:
            total += 1
    return total


@router.delete("/users/{user_id}", dependencies=[Depends(manage_users)])
def delete_user(
    user_id: uuid.UUID,
    request: Request,
    actor: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> dict[str, str]:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nutzer nicht gefunden")
    if user.id == actor.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Du kannst dich nicht selbst löschen.")
    if user.is_admin and _admin_count(db) <= 1:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Das ist der letzte Administrator und kann nicht gelöscht werden.")

    name = user.username
    db.delete(user)
    audit.record(db, "user.deleted", actor=actor, object_type="user",
                 object_id=name, request=request)
    db.commit()
    return {"status": f"{name} gelöscht. Das Profil auf der Platte bleibt bestehen."}


# --------------------------------------------------------------------------
# Gruppen
# --------------------------------------------------------------------------

@router.get("/groups", dependencies=[Depends(manage_groups)])
def list_groups(db: DbSession = Depends(get_db)) -> list[GroupOut]:
    counts = dict(db.execute(
        select(GroupMember.group_id, func.count()).group_by(GroupMember.group_id)
    ).all())
    out = []
    for g in db.scalars(select(Group).order_by(Group.priority, Group.name)).all():
        data = GroupOut.model_validate(g)
        data.member_count = counts.get(g.id, 0)
        out.append(data)
    return out


PROTECTED_SLUGS = {"admins", "users"}


@router.post("/groups", dependencies=[Depends(manage_groups)],
             status_code=status.HTTP_201_CREATED)
def create_group(
    body: GroupIn,
    request: Request,
    actor: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> GroupOut:
    slug = re.sub(r"[^a-z0-9]+", "-", body.name.lower()).strip("-") or "gruppe"
    if db.scalar(select(Group).where(Group.slug == slug)):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Eine Gruppe mit der Kennung {slug} gibt es schon.")

    unknown = set(body.permissions) - set(PERMISSIONS)
    if unknown:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"Unbekannte Rechte: {', '.join(sorted(unknown))}")

    group = Group(slug=slug, **body.model_dump())
    db.add(group)
    audit.record(db, "group.created", actor=actor, object_type="group",
                 object_id=slug, request=request)
    db.commit()
    data = GroupOut.model_validate(group)
    data.member_count = 0
    return data


@router.put("/groups/{group_id}", dependencies=[Depends(manage_groups)])
def update_group(
    group_id: uuid.UUID,
    body: GroupIn,
    request: Request,
    actor: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> GroupOut:
    group = db.get(Group, group_id)
    if not group:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Gruppe nicht gefunden")

    unknown = set(body.permissions) - set(PERMISSIONS)
    if unknown:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"Unbekannte Rechte: {', '.join(sorted(unknown))}")

    # Den Systemgruppen darf ihre Rolle nicht genommen werden — sonst steht
    # niemand mehr in der Verwaltung.
    if group.slug in PROTECTED_SLUGS:
        if group.slug == "admins" and "admin" not in body.permissions:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Der Gruppe admins kann das Verwaltungsrecht nicht entzogen werden. "
                "Ohne sie käme niemand mehr in die Verwaltung.",
            )
        group.description = body.description
        group.permissions = body.permissions
    else:
        group.name = body.name
        group.description = body.description
        group.priority = body.priority
        group.permissions = body.permissions

    audit.record(db, "group.updated", actor=actor, object_type="group",
                 object_id=group.slug, request=request)
    db.commit()
    data = GroupOut.model_validate(group)
    data.member_count = len(group.members)
    return data


@router.delete("/groups/{group_id}", dependencies=[Depends(manage_groups)])
def delete_group(
    group_id: uuid.UUID,
    request: Request,
    actor: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> dict[str, str]:
    group = db.get(Group, group_id)
    if not group:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Gruppe nicht gefunden")
    if group.is_system or group.slug in PROTECTED_SLUGS:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"{group.name} ist eine Systemgruppe und bleibt bestehen.")

    members = len(group.members)
    name = group.name
    db.delete(group)
    audit.record(db, "group.deleted", actor=actor, object_type="group",
                 object_id=group.slug, request=request, members=members)
    db.commit()
    return {"status": f"{name} gelöscht. {members} Mitgliedschaft(en) sind entfallen."}


@router.get("/permissions", dependencies=[Depends(manage_groups)])
def list_permissions() -> list[dict[str, str]]:
    """Die vergebbaren Rechte, mit Klartext fuer die Oberflaeche."""
    texts = {
        "admin": "Vollzugriff auf alles",
        "templates.manage": "Workspaces anlegen und ändern",
        "images.manage": "Golden Images bauen und aktivieren",
        "users.manage": "Nutzer anlegen und ändern",
        "groups.manage": "Gruppen anlegen und ändern",
        "sessions.view_all": "Alle Sessions sehen und beenden",
        "settings.manage": "Globale Einstellungen ändern",
        "audit.view": "Audit-Log einsehen",
        "registries.manage": "Registries einbinden",
    }
    return [{"key": k, "text": texts.get(k, k)} for k in PERMISSIONS]


# --------------------------------------------------------------------------
# Alle Sessions
# --------------------------------------------------------------------------

@router.get("/sessions", dependencies=[Depends(require_permission("sessions.view_all"))])
def all_sessions(db: DbSession = Depends(get_db)) -> list[SessionAdminOut]:
    rows = db.scalars(select(SessionModel).where(
        SessionModel.status.in_(("starting", "running", "paused"))
    ).order_by(SessionModel.started_at.desc())).all()
    return [SessionAdminOut(
        id=s.id, username=s.user.username,
        template_name=s.template.friendly_name, template_icon=s.template.icon,
        status=s.status, cores=s.cores, memory_bytes=s.memory_bytes,
        started_at=s.started_at, last_seen_at=s.last_seen_at,
        app_count=len(s.streams),
    ) for s in rows]


# --------------------------------------------------------------------------
# Audit
# --------------------------------------------------------------------------

@router.get("/audit", dependencies=[Depends(require_permission("audit.view"))])
def audit_log(limit: int = 100, db: DbSession = Depends(get_db)) -> list[dict]:
    rows = db.scalars(
        select(AuditLog).order_by(AuditLog.ts.desc()).limit(min(limit, 500))
    ).all()
    return [{
        "ts": r.ts.isoformat(),
        "actor": r.actor_name,
        "action": r.action,
        "object_type": r.object_type,
        "object_id": r.object_id,
        "ip": r.ip,
        "detail": r.detail,
    } for r in rows]


# --------------------------------------------------------------------------
# Globale Einstellungen
# --------------------------------------------------------------------------

manage_settings = require_permission("settings.manage")


@router.get("/settings", dependencies=[Depends(manage_settings)])
def read_settings(db: DbSession = Depends(get_db)) -> dict:
    """Was im laufenden Betrieb umstellbar ist — mit den erlaubten Stufen.

    Die Stufen kommen bewusst vom Server: Die Oberflaeche soll keine Auswahl
    anbieten, die der Server anschliessend zurechtbiegt.
    """
    return {
        "auth_idle_minutes": settings_store.idle_minutes(db),
        "auth_idle_steps": list(settings_store.IDLE_STEPS),
    }


@router.put("/settings", dependencies=[Depends(manage_settings)])
def write_settings(
    body: SettingsIn,
    request: Request,
    db: DbSession = Depends(get_db),
    actor: User = Depends(manage_settings),
) -> dict:
    if body.auth_idle_minutes is not None:
        if body.auth_idle_minutes not in settings_store.IDLE_STEPS:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Diese Anmeldefrist ist nicht vorgesehen.",
            )
        settings_store.put(db, settings_store.AUTH_IDLE_MINUTES, body.auth_idle_minutes)

    audit.record(db, "settings.updated", actor=actor, object_type="settings",
                 object_id="global", request=request)
    db.commit()
    return read_settings(db)
