"""Skeleton-Profile — Verwaltung über die Oberfläche.

Womit das Zuhause eines Nutzers anfängt: ein Verzeichnisbaum je Workspace, der
beim **ersten** Start hineinkopiert wird. Einzelne Pfade lassen sich als
*durchgesetzt* markieren; die kommen bei **jedem** Start und überschreiben.

Dazu je Anwendung ein eigener Teilbaum (`?app=<kennung>`), der erst kommt,
wenn **diese Anwendung** zum ersten Mal startet. Ein Arbeitsplatz trägt ein
Dutzend Anwendungen, und nicht jeder Mensch startet jede davon; die
Einstellungen von IntelliJ ins Zuhause von jemandem zu legen, der nur das
Terminal benutzt, macht das Zuhause voll und die Fehlersuche schwer.

Wer darf hier hinein: nur, wer Workspaces verwalten darf. Anders als bei der
gemeinsamen Ablage ([shared.py](shared.py)) gibt es keinen Lesezugriff für
alle — was hier liegt, sind Voreinstellungen für fremde Zuhause, und das ist
nichts, was ein Nutzer durchblättern muss.

Ausgeführt wird alles im Agent (`agent/otaagent/skeleton.py`). Die API fasst
das Dateisystem des Hosts nicht an.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session as DbSession

from .. import agent_client, audit
from ..db import get_db
from ..deps import current_user, require_permission
from ..models import Template, User
from ..schemas import SkeletonDirIn

router = APIRouter(prefix="/api/templates", tags=["skeleton"])
manage = require_permission("templates.manage", "images.manage")


def _slug(template_id: uuid.UUID, db: DbSession) -> str:
    tpl = db.get(Template, template_id)
    if not tpl:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace nicht gefunden")
    return tpl.slug


def _app(template_id: uuid.UUID, app: str, db: DbSession) -> str:
    """Prueft, dass es diese Anwendung in diesem Workspace wirklich gibt.

    Ohne diese Pruefung waere `app` ein frei waehlbarer Verzeichnisname unter
    `/srv/ota/skeletons/<workspace>/.apps/`. Der Agent laesst nur harmlose
    Zeichen durch, aber „harmlos" ist nicht dasselbe wie „gehoert hierher":
    Es entstuenden Teilbaeume fuer Anwendungen, die es nicht gibt, und sie
    fielen niemandem auf, weil die Oberflaeche nur die echten zeigt.
    """
    if not app:
        return ""
    tpl = db.get(Template, template_id)
    if not tpl:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace nicht gefunden")
    if not any(a.slug == app for a in tpl.apps):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"\u201e{app}\u201c ist keine Anwendung dieses Workspace.",
        )
    return app


@router.get("/{template_id}/skeleton", dependencies=[Depends(manage)])
def listing(template_id: uuid.UUID, path: str = "", app: str = "",
            db: DbSession = Depends(get_db)) -> dict:
    return agent_client.skeleton_list(_slug(template_id, db), path,
                                      _app(template_id, app, db))


@router.post("/{template_id}/skeleton/upload", dependencies=[Depends(manage)])
async def upload(template_id: uuid.UUID, request: Request, path: str = "",
                 app: str = "",
                 file: UploadFile = File(...),
                 actor: User = Depends(manage),
                 db: DbSession = Depends(get_db)) -> dict:
    slug = _slug(template_id, db)
    app = _app(template_id, app, db)
    data = await file.read()
    result = agent_client.skeleton_upload(slug, path, file.filename or "datei", data, app)
    audit.record(db, "skeleton.uploaded", actor=actor, object_type="template",
                 object_id=slug, request=request, app=app or "-",
                 path=f"{path}/{file.filename}".strip("/"), size_bytes=len(data))
    db.commit()
    return result


@router.post("/{template_id}/skeleton/dir", dependencies=[Depends(manage)])
def make_dir(template_id: uuid.UUID, body: SkeletonDirIn, request: Request,
             actor: User = Depends(manage),
             db: DbSession = Depends(get_db)) -> dict:
    slug = _slug(template_id, db)
    app = _app(template_id, body.app, db)
    result = agent_client.skeleton_mkdir(slug, body.path, body.name, app)
    audit.record(db, "skeleton.dir_created", actor=actor, object_type="template",
                 object_id=slug, request=request, app=app or "-",
                 path=f"{body.path}/{body.name}".strip("/"))
    db.commit()
    return result


@router.delete("/{template_id}/skeleton", dependencies=[Depends(manage)])
def remove(template_id: uuid.UUID, path: str, request: Request, app: str = "",
           actor: User = Depends(manage),
           db: DbSession = Depends(get_db)) -> dict:
    tpl = db.get(Template, template_id)
    if not tpl:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace nicht gefunden")

    app = _app(template_id, app, db)
    result = agent_client.skeleton_remove(tpl.slug, path, app)

    # Was geloescht ist, kann nicht mehr durchgesetzt werden. Den Pfad in der
    # Liste stehen zu lassen, waere eine Einstellung, die nichts mehr tut —
    # und beim naechsten Blick in die Oberflaeche eine Frage.
    #
    # Nur fuer das Skeleton des Workspace: Die Durchsetzungsliste haengt am
    # Workspace, nicht an einer Anwendung. Ein Teilbaum kommt ohnehin genau
    # einmal.
    if not app:
        rest = [p for p in (tpl.skeleton_enforce or [])
                if p != path and not p.startswith(path + "/")]
        if rest != (tpl.skeleton_enforce or []):
            tpl.skeleton_enforce = rest

    audit.record(db, "skeleton.removed", actor=actor, object_type="template",
                 object_id=tpl.slug, request=request, path=path, app=app or "-")
    db.commit()
    return result
