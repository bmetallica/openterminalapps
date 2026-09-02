"""Die eigene Ablage — Dateien in den eigenen Container und wieder heraus.

Der Unterschied zur [gemeinsamen Ablage](shared.py) ist nicht die Technik,
sondern wem sie gehört:

* Die gemeinsame Ablage ist der Weg der Verwaltung zu allen. Sie liegt in den
  Containern **nur lesbar**, und beschreiben darf sie nur, wer Vorlagen
  verwaltet.
* Diese hier gehört genau einem Menschen. Sie liegt in seinem Container
  **beschreibbar** unter ``/mnt/austausch`` (und als „Austausch" in seinem
  Home). Was er dort hineinlegt, sieht er im Browser; was er im Browser
  hochlädt, liegt eine Sekunde später im Container.

**Wessen Ablage es ist, kommt nie aus der Anfrage.** Es kommt aus dem Cookie —
und zwar als Kennung, nicht als Name: Ein Anmeldename kann sich aendern (siehe
`security.profile_path`), eine Kennung nicht. Es gibt hier
keinen Pfad, über den jemand eine fremde Ablage benennen könnte — auch nicht
als Administrator. Das ist Absicht und keine Lücke: Wer fremde Dateien
braucht, hat mit Sicherung und Wiederherstellung einen Weg, der im Protokoll
steht. Ein stiller Blick ins Zuhause eines Kollegen soll keiner sein.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session as DbSession

from .. import agent_client, audit
from ..db import get_db
from ..deps import current_user
from ..models import User
from ..schemas import SharedDirIn

router = APIRouter(prefix="/api/files", tags=["files"])


@router.get("")
def listing(path: str = "", me: User = Depends(current_user)) -> dict:
    return agent_client.user_list(str(me.id), path)


@router.get("/file")
def download(path: str, me: User = Depends(current_user)) -> Response:
    data, name = agent_client.user_read(str(me.id), path)
    return Response(
        content=data, media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.post("/upload")
async def upload(request: Request, path: str = "",
                 file: UploadFile = File(...),
                 me: User = Depends(current_user),
                 db: DbSession = Depends(get_db)) -> dict:
    data = await file.read()
    result = agent_client.user_upload(str(me.id), path, file.filename or "datei", data)
    # Protokolliert, aber knapp: Wer in seine eigene Ablage schreibt, tut
    # nichts Bemerkenswertes. Es steht trotzdem da, weil hier Daten den
    # Container verlassen und wieder hineingehen — und genau das ist der
    # Vorgang, den eine Revision sehen will.
    audit.record(db, "files.uploaded", actor=me, object_type="files",
                 object_id=f"{path}/{result.get('name')}".strip("/"),
                 request=request, size_bytes=len(data))
    db.commit()
    return result


@router.post("/dir")
def make_dir(body: SharedDirIn, me: User = Depends(current_user)) -> dict:
    return agent_client.user_mkdir(str(me.id), body.path, body.name)


@router.delete("")
def remove(path: str, request: Request,
           me: User = Depends(current_user),
           db: DbSession = Depends(get_db)) -> dict:
    result = agent_client.user_remove(str(me.id), path)
    audit.record(db, "files.deleted", actor=me, object_type="files",
                 object_id=path, request=request)
    db.commit()
    return result
