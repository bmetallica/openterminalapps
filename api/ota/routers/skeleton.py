"""Skeleton-Profile — Verwaltung über die Oberfläche.

Womit das Zuhause eines Nutzers anfängt: ein Verzeichnisbaum je Workspace, der
beim **ersten** Start hineinkopiert wird. Einzelne Pfade lassen sich als
*durchgesetzt* markieren; die kommen bei **jedem** Start und überschreiben.

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


@router.get("/{template_id}/skeleton", dependencies=[Depends(manage)])
def listing(template_id: uuid.UUID, path: str = "",
            db: DbSession = Depends(get_db)) -> dict:
    return agent_client.skeleton_list(_slug(template_id, db), path)


@router.post("/{template_id}/skeleton/upload", dependencies=[Depends(manage)])
async def upload(template_id: uuid.UUID, request: Request, path: str = "",
                 file: UploadFile = File(...),
                 actor: User = Depends(manage),
                 db: DbSession = Depends(get_db)) -> dict:
    slug = _slug(template_id, db)
    data = await file.read()
    result = agent_client.skeleton_upload(slug, path, file.filename or "datei", data)
    audit.record(db, "skeleton.uploaded", actor=actor, object_type="template",
                 object_id=slug, request=request,
                 path=f"{path}/{file.filename}".strip("/"), size_bytes=len(data))
    db.commit()
    return result


@router.post("/{template_id}/skeleton/dir", dependencies=[Depends(manage)])
def make_dir(template_id: uuid.UUID, body: SkeletonDirIn, request: Request,
             actor: User = Depends(manage),
             db: DbSession = Depends(get_db)) -> dict:
    slug = _slug(template_id, db)
    result = agent_client.skeleton_mkdir(slug, body.path, body.name)
    audit.record(db, "skeleton.dir_created", actor=actor, object_type="template",
                 object_id=slug, request=request,
                 path=f"{body.path}/{body.name}".strip("/"))
    db.commit()
    return result


@router.delete("/{template_id}/skeleton", dependencies=[Depends(manage)])
def remove(template_id: uuid.UUID, path: str, request: Request,
           actor: User = Depends(manage),
           db: DbSession = Depends(get_db)) -> dict:
    tpl = db.get(Template, template_id)
    if not tpl:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace nicht gefunden")

    result = agent_client.skeleton_remove(tpl.slug, path)

    # Was geloescht ist, kann nicht mehr durchgesetzt werden. Den Pfad in der
    # Liste stehen zu lassen, waere eine Einstellung, die nichts mehr tut —
    # und beim naechsten Blick in die Oberflaeche eine Frage.
    rest = [p for p in (tpl.skeleton_enforce or []) if p != path and not p.startswith(path + "/")]
    if rest != (tpl.skeleton_enforce or []):
        tpl.skeleton_enforce = rest

    audit.record(db, "skeleton.removed", actor=actor, object_type="template",
                 object_id=tpl.slug, request=request, path=path)
    db.commit()
    return result
