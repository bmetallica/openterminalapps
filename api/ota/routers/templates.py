from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from .. import agent_client, audit
from ..db import get_db
from ..deps import current_user, require_permission
from ..models import (
    Group, Session as SessionModel, Template, TemplateApp, TemplateOverride, User,
)
from ..schemas import (
    AllocationOut, AppIn, OverrideIn, OverrideOut, TemplateIn, TemplateOut,
)
from ..security import effective_resources, user_can_see_app, user_can_see_template

router = APIRouter(prefix="/api/templates", tags=["templates"])
manage = require_permission("templates.manage")


def _slugify(value: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return s or "workspace"


def _out(tpl: Template, user: User | None = None) -> TemplateOut:
    data = TemplateOut.model_validate(tpl)
    data.group_ids = [g.id for g in tpl.groups]
    if user is not None:
        # Was der Nutzer nicht sehen darf, taucht hier gar nicht erst auf.
        # Der Start prueft es noch einmal — diese Liste ist Anzeige, nicht
        # Absicherung.
        data.apps = [
            a for a, orig in zip(data.apps, tpl.apps)
            if user_can_see_app(orig, user)
        ]
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

    # Ein Workspace mit laufenden Sessions wird nicht weggezogen. Die Container
    # blieben sonst als Waisen zurueck, und ihre Nutzer saehen mitten in der
    # Arbeit eine Fehlerseite statt einer Erklaerung.
    live = db.scalars(select(SessionModel).where(
        SessionModel.template_id == tpl.id,
        SessionModel.status.in_(("starting", "running", "paused")),
    )).all()
    if live:
        who = ", ".join(sorted({s.user.username for s in live}))
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Hier läuft noch etwas: {who}. Beende die Sessions unter "
            "Betrieb, dann lässt sich der Workspace löschen.",
        )

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

@router.get("/{template_id}/packages", dependencies=[Depends(manage)])
def check_packages(
    template_id: uuid.UUID,
    names: str = "",
    db: DbSession = Depends(get_db),
) -> list[dict]:
    """Kennt das Image dieser Vorlage diese Pakete?

    Gefragt wird, bevor gebaut wird. Ein Build dauert Minuten, und an einem
    Debian-Namen auf einem Ubuntu-Image (`firefox-esr`) scheitert er erst am
    Ende — mit einer Meldung, die in hundert Zeilen Protokoll steht.
    """
    tpl = db.get(Template, template_id)
    if not tpl:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace nicht gefunden")
    wanted = [n.strip() for n in names.split(",") if n.strip()]
    if not wanted:
        return []
    return agent_client.image_packages(tpl.image_ref, wanted)


@router.get("/{template_id}/apps/discover", dependencies=[Depends(manage)])
def discover_apps(
    template_id: uuid.UUID,
    db: DbSession = Depends(get_db),
) -> list[dict]:
    """Welche Anwendungen im Image dieser Vorlage installiert sind.

    Der Weg vom „Firefox einbauen" zum „Firefox im Dashboard" fuehrt sonst
    ueber drei Fragen, die niemand beantworten will: Wie heisst die
    Binaerdatei, wo liegt sie, und wie soll das Ding in der Oberflaeche
    heissen. Das steht alles in den .desktop-Dateien des Images.

    Zurueck kommt die Vereinigung aus Gefundenem und bereits Eingetragenem.
    `in_catalog` sagt, was schon im Arbeitsplatz angeboten wird; `missing`
    markiert Eintraege, die im Katalog stehen, aber im Image nicht mehr
    vorkommen — etwa nach einem Basiswechsel.
    """
    tpl = db.get(Template, template_id)
    if not tpl:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace nicht gefunden")

    found = agent_client.image_applications(tpl.image_ref)

    # Zuordnung ueber zwei Wege, weil beide vorkommen: Der Katalog kann eine
    # eigene Kennung tragen (`vscode`), waehrend die .desktop-Datei einen
    # anderen Namen hat (`visual-studio-code`). Was zaehlt, ist das Programm —
    # also auch der Name der Binaerdatei.
    known = {a.slug: a for a in tpl.apps}
    by_binary = {a.exec_cmd.rsplit("/", 1)[-1]: a for a in tpl.apps}

    out: list[dict] = []
    matched: set[str] = set()
    seen: set[str] = set()
    for entry in found:
        current = known.get(entry["slug"]) or by_binary.get(str(entry["binary"]))
        if current is not None:
            matched.add(current.slug)
            # Die Kennung des Katalogs behalten: An ihr haengt die
            # Displaynummer und damit die Traefik-Route.
            entry = {**entry, "slug": current.slug}
        # Zwei .desktop-Dateien koennen auf dasselbe Programm zeigen (Thunar
        # bringt eine fuer die Anwendung und eine fuer den Ordner-Handler mit).
        # Nach der Zuordnung faellt das zusammen — hier einmal reicht.
        if entry["slug"] in seen:
            continue
        seen.add(str(entry["slug"]))
        out.append({
            **entry,
            "in_catalog": current is not None,
            "is_enabled": current.is_enabled if current else False,
            "fixed_display": current.fixed_display if current else None,
            # Eine schon gesetzte Sichtbarkeit ueberlebt das Durchsehen. Sonst
            # waere jede Einschraenkung nach dem naechsten Build wieder weg.
            "group_ids": (current.group_ids or []) if current else [],
            "missing": False,
            # Name und Zeichen aus dem Katalog haben Vorrang: Wer sie
            # angepasst hat, will das nicht bei jedem Durchsehen verlieren.
            "name": current.name if current else entry["name"],
            "icon": current.icon if current else entry["icon"],
        })

    for slug, app in known.items():
        if slug in matched:
            continue
        out.append({
            "slug": slug, "name": app.name, "icon": app.icon,
            "exec_cmd": app.exec_cmd, "exec_args": app.exec_args,
            "categories": [], "needs_terminal": False,
            "binary": app.exec_cmd.rsplit("/", 1)[-1],
            "in_catalog": True, "is_enabled": app.is_enabled,
            "fixed_display": app.fixed_display, "missing": True,
            "group_ids": app.group_ids or [],
        })

    return sorted(out, key=lambda a: (a["missing"], str(a["name"]).lower()))


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

    known_groups = set(db.scalars(select(Group.id)).all())

    tpl.apps.clear()
    db.flush()
    for order, entry in enumerate(body):
        fields = entry.model_dump()
        # JSONB nimmt keine UUID-Objekte. Und Gruppen, die es nicht gibt,
        # sollen gar nicht erst gespeichert werden — sonst steht in der
        # Oberfläche gleich wieder eine Auswahl, die niemand getroffen hat.
        fields["group_ids"] = [str(g) for g in fields.get("group_ids") or [] if g in known_groups]
        tpl.apps.append(TemplateApp(sort_order=order, **fields))

    audit.record(db, "template.apps_set", actor=actor, object_type="template",
                 object_id=tpl.slug, request=request, count=len(body))
    db.commit()
    db.refresh(tpl)
    return _out(tpl)
