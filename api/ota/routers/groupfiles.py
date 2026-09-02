"""Gemeinsame Gruppenlaufwerke — dieselben Dateien für ein Team.

Die dritte Ablage neben der [gemeinsamen](shared.py) und der
[eigenen](files.py). Der Unterschied ist wieder nicht die Technik, sondern
wem sie gehört:

* Die **gemeinsame** Ablage ist der Weg der Verwaltung zu allen. Sie liegt in
  den Containern nur lesbar, beschreiben darf sie nur, wer Vorlagen verwaltet.
* Die **eigene** Ablage gehört genau einem Menschen.
* Ein **Gruppenlaufwerk** gehört einer Gruppe. Jedes Mitglied darf lesen und
  schreiben, im Browser wie im Container (`/mnt/gruppen/<name>`, im Zuhause
  als „Gruppen").

**Die Mitgliedschaft entscheidet, und sonst nichts.** Auch ein Administrator
kommt nur an die Laufwerke der Gruppen, in denen er selbst ist. Das ist
Absicht und keine Lücke: Wer Gruppen verwaltet, verwaltet Zugehörigkeiten —
das heisst nicht, dass er in die Dateien schauen soll. Wer wirklich hinein
muss, trägt sich in die Gruppe ein, und das steht im Protokoll.

Der Entzug einer Mitgliedschaft wirkt hier **sofort**: Die nächste Anfrage
wird abgewiesen. Im laufenden Container bleibt das Laufwerk bis zum nächsten
Start eingehängt — dieselbe Regel wie bei den übrigen Rechten
(`auth-roadmap.md`). Ein Bind-Mount lässt sich einem laufenden Container nicht
entziehen, ohne ihn zu beenden, und jemanden mitten in der Arbeit
hinauszuwerfen wäre schlimmer als die Stunde bis zum nächsten Start.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session as DbSession

from .. import agent_client, audit
from ..db import get_db
from ..deps import current_user
from ..models import Group, User
from ..schemas import SharedDirIn

router = APIRouter(prefix="/api/groupfiles", tags=["groupfiles"])


def _meine(me: User, group_id: uuid.UUID) -> Group:
    """Die Gruppe — wenn der Anfragende darin ist. Sonst 404.

    Bewusst 404 und nicht 403: Ein 403 verriete, dass es diese Gruppe gibt.
    Für jemanden, der nicht dazugehört, ist beides dasselbe.
    """
    for g in me.groups:
        if g.id == group_id:
            return g
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Dieses Laufwerk gibt es nicht.")


@router.get("")
def meine_gruppen(me: User = Depends(current_user)) -> list[dict]:
    """Welche Laufwerke dieser Mensch hat. Die Grundlage für die Umschaltung."""
    return [
        {"id": str(g.id), "name": g.name}
        for g in sorted(me.groups, key=lambda g: g.name.lower())
    ]


@router.get("/{group_id}")
def listing(group_id: uuid.UUID, path: str = "",
            me: User = Depends(current_user)) -> dict:
    _meine(me, group_id)
    return agent_client.group_list(str(group_id), path)


@router.get("/{group_id}/file")
def download(group_id: uuid.UUID, path: str,
             me: User = Depends(current_user)) -> Response:
    _meine(me, group_id)
    data, name = agent_client.group_read(str(group_id), path)
    return Response(
        content=data, media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.post("/{group_id}/upload")
async def upload(group_id: uuid.UUID, request: Request, path: str = "",
                 file: UploadFile = File(...),
                 me: User = Depends(current_user),
                 db: DbSession = Depends(get_db)) -> dict:
    gruppe = _meine(me, group_id)
    data = await file.read()
    result = agent_client.group_upload(str(group_id), path,
                                       file.filename or "datei", data)
    # Ausführlicher protokolliert als die eigene Ablage: Hier ändert jemand
    # etwas, das andere sehen. Wer später fragt „wer hat das gelöscht", soll
    # eine Antwort bekommen.
    audit.record(db, "groupfiles.uploaded", actor=me, object_type="group",
                 object_id=str(group_id), request=request, group=gruppe.name,
                 path=f"{path}/{result.get('name')}".strip("/"),
                 size_bytes=len(data))
    db.commit()
    return result


@router.post("/{group_id}/dir")
def make_dir(group_id: uuid.UUID, body: SharedDirIn, request: Request,
             me: User = Depends(current_user),
             db: DbSession = Depends(get_db)) -> dict:
    gruppe = _meine(me, group_id)
    result = agent_client.group_mkdir(str(group_id), body.path, body.name)
    audit.record(db, "groupfiles.dir_created", actor=me, object_type="group",
                 object_id=str(group_id), request=request, group=gruppe.name,
                 path=f"{body.path}/{body.name}".strip("/"))
    db.commit()
    return result


@router.delete("/{group_id}")
def remove(group_id: uuid.UUID, path: str, request: Request,
           me: User = Depends(current_user),
           db: DbSession = Depends(get_db)) -> dict:
    gruppe = _meine(me, group_id)
    result = agent_client.group_remove(str(group_id), path)
    audit.record(db, "groupfiles.deleted", actor=me, object_type="group",
                 object_id=str(group_id), request=request, group=gruppe.name,
                 path=path)
    db.commit()
    return result
