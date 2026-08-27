from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from .. import audit
from ..db import get_db
from ..deps import current_user, require_permission
from ..models import Group, Template, TemplateApp, TemplateOverride, User
from ..schemas import (
    AllocationOut, AppIn, OverrideIn, OverrideOut, TemplateIn, TemplateOut,
)
from ..security import effective_resources, user_can_see_template

router = APIRouter(prefix="/api/templates", tags=["templates"])
manage = require_permission("templates.manage")


def _slugify(value: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return s or "workspace"


def _out(tpl: Template, user: User | None = None) -> TemplateOut:
    data = TemplateOut.model_validate(tpl)
    data.group_ids = [g.id for g in tpl.groups]
    if user is not None:
        cores, mem, _, _ = effective_resources(tpl, user)
        data.effective_cores = cores
        data.effective_memory_bytes = mem
    return data


@router.get("")
def list_templates(
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> list[TemplateOut]:
    """Admins sehen alles, alle anderen ausschliesslich Zugewiesenes.

    Die Einschraenkung passiert hier in der Abfrage, nicht im Frontend.
    """
    templates = db.scalars(select(Template).order_by(Template.friendly_name)).all()
    return [_out(t, user) for t in templates if user_can_see_template(t, user)]


@router.post("", dependencies=[Depends(manage)], status_code=status.HTTP_201_CREATED)
def create_template(
    body: TemplateIn,
    request: Request,
    actor: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> TemplateOut:
    slug = _slugify(body.friendly_name)
    if db.scalar(select(Template).where(Template.slug == slug)):
        slug = f"{slug}-{uuid.uuid4().hex[:6]}"

    tpl = Template(slug=slug, **body.model_dump(exclude={"group_ids"}))
    tpl.groups = list(db.scalars(select(Group).where(Group.id.in_(body.group_ids))).all())
    db.add(tpl)
    audit.record(db, "template.created", actor=actor, object_type="template",
                 object_id=slug, request=request, name=body.friendly_name)
    db.commit()
    return _out(tpl)


@router.get("/{template_id}")
def get_template(
    template_id: uuid.UUID,
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> TemplateOut:
    tpl = db.get(Template, template_id)
    if not tpl or not user_can_see_template(tpl, user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace nicht gefunden")
    return _out(tpl, user)


@router.put("/{template_id}", dependencies=[Depends(manage)])
def update_template(
    template_id: uuid.UUID,
    body: TemplateIn,
    request: Request,
    actor: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> TemplateOut:
    tpl = db.get(Template, template_id)
    if not tpl:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace nicht gefunden")

    for key, value in body.model_dump(exclude={"group_ids"}).items():
        setattr(tpl, key, value)
    tpl.groups = list(db.scalars(select(Group).where(Group.id.in_(body.group_ids))).all())

    audit.record(db, "template.updated", actor=actor, object_type="template",
                 object_id=tpl.slug, request=request)
    db.commit()
    return _out(tpl)


@router.delete("/{template_id}", dependencies=[Depends(manage)])
def delete_template(
    template_id: uuid.UUID,
    request: Request,
    actor: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> dict[str, str]:
    tpl = db.get(Template, template_id)
    if not tpl:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace nicht gefunden")
    name = tpl.friendly_name
    db.delete(tpl)
    audit.record(db, "template.deleted", actor=actor, object_type="template",
                 object_id=tpl.slug, request=request, name=name)
    db.commit()
    return {"status": f"{name} gelöscht"}


# --------------------------------------------------------------------------
# Zuteilung je Nutzer (plan.md §5)
# --------------------------------------------------------------------------

@router.get("/{template_id}/allocations", dependencies=[Depends(manage)])
def allocations(
    template_id: uuid.UUID,
    db: DbSession = Depends(get_db),
) -> list[AllocationOut]:
    """Was fuer jeden erreichbaren Nutzer tatsaechlich gilt.

    Auch Nutzer ohne eigene Abweichung erscheinen — sonst muesste man raten,
    wen die Vorlage betrifft.
    """
    tpl = db.get(Template, template_id)
    if not tpl:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace nicht gefunden")

    group_ids = {g.id for g in tpl.groups}
    own = {o.target_id for o in tpl.overrides if o.scope == "user"}

    out: list[AllocationOut] = []
    for user in db.scalars(select(User).order_by(User.username)).all():
        if not group_ids & {g.id for g in user.groups}:
            continue
        cores, mem, cf, mf = effective_resources(tpl, user)
        out.append(AllocationOut(
            user_id=user.id, username=user.username,
            cores=cores, memory_bytes=mem,
            cores_from=cf, memory_from=mf,
            has_own_override=user.id in own,
        ))
    return out


@router.get("/{template_id}/overrides", dependencies=[Depends(manage)])
def list_overrides(
    template_id: uuid.UUID, db: DbSession = Depends(get_db)
) -> list[OverrideOut]:
    tpl = db.get(Template, template_id)
    if not tpl:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace nicht gefunden")
    return [OverrideOut.model_validate(o) for o in tpl.overrides]


@router.put("/{template_id}/overrides", dependencies=[Depends(manage)])
def set_override(
    template_id: uuid.UUID,
    body: OverrideIn,
    request: Request,
    actor: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> dict[str, str]:
    """Setzt oder entfernt eine Abweichung.

    Sind beide Werte None, wird die Abweichung geloescht — dann erbt der
    Nutzer wieder.
    """
    tpl = db.get(Template, template_id)
    if not tpl:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace nicht gefunden")
    if body.scope not in {"user", "group"}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "scope muss 'user' oder 'group' sein")

    existing = db.scalar(select(TemplateOverride).where(
        TemplateOverride.template_id == template_id,
        TemplateOverride.scope == body.scope,
        TemplateOverride.target_id == body.target_id,
    ))

    if body.cores is None and body.memory_bytes is None:
        if existing:
            db.delete(existing)
        audit.record(db, "override.cleared", actor=actor, object_type="template",
                     object_id=tpl.slug, request=request,
                     scope=body.scope, target=str(body.target_id))
        db.commit()
        return {"status": "Abweichung entfernt"}

    if existing:
        existing.cores = body.cores
        existing.memory_bytes = body.memory_bytes
    else:
        db.add(TemplateOverride(template_id=template_id, **body.model_dump()))

    audit.record(db, "override.set", actor=actor, object_type="template",
                 object_id=tpl.slug, request=request,
                 scope=body.scope, target=str(body.target_id),
                 cores=body.cores, memory_bytes=body.memory_bytes)
    db.commit()
    return {"status": "Abweichung gespeichert"}


# --------------------------------------------------------------------------
# App-Katalog des Arbeitsplatzes (plan.md §9.5)
# --------------------------------------------------------------------------

@router.put("/{template_id}/apps", dependencies=[Depends(manage)])
def set_apps(
    template_id: uuid.UUID,
    body: list[AppIn],
    request: Request,
    actor: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> TemplateOut:
    """Ersetzt den App-Katalog einer Vorlage.

    Die Reihenfolge ist bedeutsam: Aus ihr leitet sich die Displaynummer ab,
    und die Traefik-Routen dafuer werden beim Containerstart auf Vorrat
    angelegt. Wer die Reihenfolge aendert, aendert die Displayzuordnung —
    laufende Sessions muessen dafuer neu gestartet werden.
    """
    tpl = db.get(Template, template_id)
    if not tpl:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace nicht gefunden")
    if tpl.mode != "workspace":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Ein App-Katalog ergibt nur beim Arbeitsplatz Sinn. "
            "Stelle die Betriebsart um, wenn du mehrere Anwendungen willst.",
        )

    seen: set[str] = set()
    for entry in body:
        if entry.slug in seen:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                f"Die Kennung {entry.slug} kommt doppelt vor.")
        seen.add(entry.slug)

    tpl.apps.clear()
    db.flush()
    for order, entry in enumerate(body):
        tpl.apps.append(TemplateApp(sort_order=order, **entry.model_dump()))

    audit.record(db, "template.apps_set", actor=actor, object_type="template",
                 object_id=tpl.slug, request=request, count=len(body))
    db.commit()
    db.refresh(tpl)
    return _out(tpl)
