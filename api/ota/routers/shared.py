"""Die gemeinsame Ablage — der Weg der Administration zu den Nutzern.

**Diese Ablage gehört der Verwaltung.** Wer sie im Browser sieht, sieht sie
ganz: lesen, hochladen, Ordner anlegen, löschen. Wer sie nicht verwalten darf,
hat hier nichts zu suchen und bekommt seine [eigene](files.py).

Das war einmal anders — bis zum 2026-08-28 durfte jeder Angemeldete den
Inhalt lesen, mit dem Argument, er sehe ihn ohnehin in seinem Container. Das
Argument stimmt weiterhin, taugt aber nicht als Bauplan für die Oberfläche:
Zwei Ablagen nebeneinander, von denen eine nur zum Zusehen da ist, erklären
sich nicht. Der lesende Zugriff im Container über ``/mnt/ota`` bleibt davon
unberührt — dafür ist sie da.

Ausgeführt wird alles im Agent (`agent/otaagent/shared.py`). Die API fasst das
Dateisystem des Hosts nicht an; sie entscheidet, wer was darf.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session as DbSession

from .. import agent_client, audit
from ..db import get_db
from ..deps import require_permission
from ..models import User
from ..schemas import SharedDirIn

router = APIRouter(prefix="/api/shared", tags=["shared"])

# Wer Images verwalten darf, darf auch verteilen, was in sie hineingehört.
manage = require_permission("images.manage", "templates.manage")


@router.get("", dependencies=[Depends(manage)])
def listing(path: str = "") -> dict:
    return agent_client.shared_list(path)


@router.get("/file", dependencies=[Depends(manage)])
def download(path: str) -> Response:
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
