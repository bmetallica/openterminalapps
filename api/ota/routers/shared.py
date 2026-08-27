"""Die gemeinsame Ablage — Verwaltung über die Oberfläche.

Die Aufteilung ist der Punkt dieser Datei:

* **Lesen** darf jeder Angemeldete. Er sieht die Ablage ohnehin in seinem
  Container unter ``/mnt/ota`` (und als „Gemeinsam" in seinem Home); sie im
  Browser zu verbergen wäre eine Kulisse, keine Sicherheit.
* **Schreiben** darf nur, wer Dateien verwalten darf. In den Containern liegt
  die Ablage schreibgeschützt — der Weg hinein führt ausschliesslich hier
  entlang.

Ausgeführt wird alles im Agent (`agent/otaagent/shared.py`). Die API fasst das
Dateisystem des Hosts nicht an; sie entscheidet, wer was darf.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session as DbSession

from .. import agent_client, audit
from ..db import get_db
from ..deps import current_user, require_permission
from ..models import User
from ..schemas import SharedDirIn

router = APIRouter(prefix="/api/shared", tags=["shared"])

# Wer Images verwalten darf, darf auch verteilen, was in sie hineingehört.
manage = require_permission("images.manage", "templates.manage")


@router.get("")
def listing(path: str = "", _: User = Depends(current_user)) -> dict:
    return agent_client.shared_list(path)


@router.get("/file")
def download(path: str, _: User = Depends(current_user)) -> Response:
    data, name = agent_client.shared_read(path)
    return Response(
        content=data, media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.post("/upload", dependencies=[Depends(manage)])
async def upload(request: Request, path: str = "",
                 file: UploadFile = File(...),
                 actor: User = Depends(manage),
                 db: DbSession = Depends(get_db)) -> dict:
    data = await file.read()
    result = agent_client.shared_upload(path, file.filename or "datei", data)
    audit.record(db, "shared.uploaded", actor=actor, object_type="shared",
                 object_id=f"{path}/{result.get('name')}".strip("/"),
                 request=request, size_bytes=len(data))
    db.commit()
    return result


@router.post("/dir", dependencies=[Depends(manage)])
def make_dir(body: SharedDirIn, request: Request,
             actor: User = Depends(manage),
             db: DbSession = Depends(get_db)) -> dict:
    result = agent_client.shared_mkdir(body.path, body.name)
    audit.record(db, "shared.dir_created", actor=actor, object_type="shared",
                 object_id=f"{body.path}/{body.name}".strip("/"), request=request)
    db.commit()
    return result


@router.delete("", dependencies=[Depends(manage)])
def remove(path: str, request: Request,
           actor: User = Depends(manage),
           db: DbSession = Depends(get_db)) -> dict:
    result = agent_client.shared_remove(path)
    audit.record(db, "shared.deleted", actor=actor, object_type="shared",
                 object_id=path, request=request)
    db.commit()
    return result
