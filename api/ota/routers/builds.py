"""Golden Images: bauen, aktivieren, zurueckrollen (plan.md §8)."""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from .. import agent_client, audit
from ..db import SessionLocal, get_db
from ..deps import current_user, require_permission
from ..models import ImageBuild, Template, User
from ..schemas import BuildIn, BuildOut

router = APIRouter(prefix="/api/templates", tags=["builds"])
manage = require_permission("images.manage", "templates.manage")

# Wie viele Versionen je Vorlage aufgehoben werden (plan.md §8.2).
KEEP_VERSIONS = 3


def _out(b: ImageBuild) -> BuildOut:
    return BuildOut.model_validate(b)


async def _watch(build_db_id: uuid.UUID, agent_build_id: str) -> None:
    """Verfolgt den Build im Agent und schreibt Log und Ergebnis in die DB.

    Laeuft als Hintergrundaufgabe, damit der Aufruf sofort zurueckkehrt —
    ein Build dauert Minuten.
    """
    while True:
        await asyncio.sleep(2)
        try:
            state = await asyncio.to_thread(agent_client.build_status, agent_build_id)
        except Exception:  # noqa: BLE001
            continue

        with SessionLocal() as db:
            build = db.get(ImageBuild, build_db_id)
            if build is None:
                return
            build.log = state.get("log", "")
            build.status = state.get("status", "building")
            if state["status"] in ("ok", "failed"):
                build.image_ref = state.get("image_ref")
                build.size_bytes = state.get("size_bytes") or 0
                build.digest = state.get("digest")
                build.finished_at = datetime.now(timezone.utc)
                db.commit()

                if state["status"] == "ok" and build.image_ref:
                    await _verify_survives(build_db_id, build.image_ref)
                return
            db.commit()


# Wie lange nach dem Build nachgeprueft wird, ob das Image noch da ist.
# Kasms Agent raeumt im Modus "Aggressive" etwa alle 30 Sekunden auf.
_VERIFY_AFTER = 45


async def _verify_survives(build_db_id: uuid.UUID, image_ref: str) -> None:
    """Prueft, ob das frisch gebaute Image noch im Image-Store liegt.

    Klingt ueberfluessig, ist es aber nicht: Laeuft auf demselben Docker-Host
    ein zweites System, das Images aufraeumt — Kasm tut das im Modus
    "Aggressive" alle 30 Sekunden mit allem, was es nicht kennt —, ist ein
    erfolgreich gebautes Image Sekunden spaeter wieder weg. Der Build meldet
    dann Erfolg, und der erste Sessionstart scheitert mit "Image liegt nicht
    auf diesem Host". Diese Nachpruefung macht aus dem Raetsel eine Aussage.
    """
    await asyncio.sleep(_VERIFY_AFTER)
    try:
        result = await asyncio.to_thread(agent_client.image_exists, image_ref)
    except Exception:  # noqa: BLE001
        return
    if result.get("exists"):
        return

    with SessionLocal() as db:
        build = db.get(ImageBuild, build_db_id)
        if build is None or build.status != "ok":
            return
        build.status = "failed"
        build.log += (
            "\n"
            + "=" * 62
            + "\nDas Image wurde erfolgreich gebaut und ist danach wieder aus dem\n"
            "Image-Store verschwunden.\n\n"
            "Ursache ist fast immer ein zweites System auf demselben Docker-Host,\n"
            "das Images aufräumt. Kasm Workspaces tut das im Modus \"Aggressive\"\n"
            "etwa alle 30 Sekunden mit jedem Image, das es nicht kennt — auch mit\n"
            "unseren Golden Images.\n\n"
            "Nachsehen lässt sich das so:\n"
            "  docker logs kasm_agent --since 5m | grep -i prune\n\n"
            "Abhilfe, eine von beiden:\n"
            "  - In Kasm unter Infrastructure → Servers die Aufräum-Einstellung\n"
            "    von \"Aggressive\" auf eine mildere Stufe setzen.\n"
            "  - Golden Images erst bauen, nachdem Kasm abgelöst ist.\n"
            + "=" * 62 + "\n"
        )
        db.commit()


@router.get("/{template_id}/builds", dependencies=[Depends(manage)])
def list_builds(template_id: uuid.UUID, db: DbSession = Depends(get_db)) -> list[BuildOut]:
    tpl = db.get(Template, template_id)
    if not tpl:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace nicht gefunden")
    return [_out(b) for b in tpl.builds]


@router.post("/{template_id}/builds", dependencies=[Depends(manage)],
             status_code=status.HTTP_202_ACCEPTED)
async def start_build(
    template_id: uuid.UUID,
    body: BuildIn,
    request: Request,
    actor: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> BuildOut:
    tpl = db.get(Template, template_id)
    if not tpl:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace nicht gefunden")

    running = db.scalar(select(ImageBuild).where(
        ImageBuild.status.in_(("queued", "building"))
    ))
    if running:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Es läuft bereits ein Build. Sie laufen bewusst nacheinander, damit "
            "der Host die Sessions weiter bedienen kann.",
        )

    version = max((b.version for b in tpl.builds), default=0) + 1
    base = body.base_image or tpl.image_ref
    tag = f"ota/{tpl.slug}:v{version}"

    build = ImageBuild(
        template_id=tpl.id, version=version, base_image=base,
        apt_packages=body.apt_packages, vscode_extensions=body.vscode_extensions,
        setup_script=body.setup_script, comment=body.comment,
        status="queued", built_by=actor.username,
    )
    db.add(build)
    db.flush()

    from ..config import settings

    # Fremde Container, die waehrend des Builds stoeren. Der Agent startet sie
    # in jedem Fall wieder — auch wenn der Build scheitert.
    pause = [
        name.strip() for name in settings().build_pause_containers.split(",")
        if name.strip()
    ] if body.pause_foreign_cleanup else []

    result = agent_client.start_build({
        "tag": tag,
        "base_image": base,
        "apt_packages": body.apt_packages,
        "vscode_extensions": body.vscode_extensions,
        "setup_script": body.setup_script,
        # Arbeitsplatz-Images duerfen keine Anwendung von selbst starten.
        "mode": tpl.mode,
        "pause_containers": pause,
    })

    build.log = f"Build gestartet als {tag}\n\n"
    audit.record(db, "build.started", actor=actor, object_type="template",
                 object_id=tpl.slug, request=request, version=version, tag=tag)
    db.commit()

    task = asyncio.create_task(_watch(build.id, result["build_id"]))
    # Referenz halten, damit die Aufgabe nicht vorzeitig eingesammelt wird.
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)

    return _out(build)


_tasks: set[asyncio.Task] = set()


@router.get("/{template_id}/builds/{build_id}", dependencies=[Depends(manage)])
def build_detail(
    template_id: uuid.UUID, build_id: uuid.UUID, db: DbSession = Depends(get_db)
) -> BuildOut:
    build = db.get(ImageBuild, build_id)
    if not build or build.template_id != template_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Build nicht gefunden")
    return _out(build)


@router.get("/{template_id}/builds/{build_id}/stream", dependencies=[Depends(manage)])
async def build_stream(template_id: uuid.UUID, build_id: uuid.UUID) -> StreamingResponse:
    """Das Build-Protokoll als Ereignisstrom.

    Was sich damit aendert und was nicht: Der Server fragt den Agent weiterhin
    im Zwei-Sekunden-Takt ab — anders kommt man an den Fortschritt von
    `docker build` nicht heran. Was wegfaellt, ist die Abfrage des *Browsers*.
    Er bekommt nur noch das, was dazugekommen ist, und zwar sobald es da ist,
    statt alle 2,5 Sekunden das ganze Protokoll neu zu holen. Bei einem Build,
    dessen Protokoll auf mehrere hundert Kilobyte anwaechst, ist das der
    Unterschied zwischen einem ruhigen Fenster und einem, das ruckelt.

    Drei Ereignisarten: `log` mit dem Zuwachs, `status` bei jedem Wechsel,
    `end` zum Schluss. Danach schliesst der Server; der Browser soll nicht
    wieder verbinden.
    """
    async def events():
        seen = 0
        last_status = ""
        # Eine Obergrenze, damit ein haengender Build nicht dauerhaft eine
        # Verbindung bindet. Der Client faellt danach auf die Abfrage zurueck.
        deadline = asyncio.get_event_loop().time() + 3600

        while asyncio.get_event_loop().time() < deadline:
            with SessionLocal() as db:
                build = db.get(ImageBuild, build_id)
                if build is None or build.template_id != template_id:
                    yield "event: end\ndata: {\"status\": \"weg\"}\n\n"
                    return
                log, current = build.log or "", build.status

            if current != last_status:
                last_status = current
                yield f"event: status\ndata: {json.dumps({'status': current})}\n\n"

            if len(log) > seen:
                # Nur der Zuwachs. Ihn als JSON zu verpacken erspart die Frage,
                # was mit Zeilenumbruechen im Protokoll passiert — im
                # SSE-Format ist der Umbruch das Trennzeichen.
                chunk = log[seen:]
                seen = len(log)
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"

            if current not in ("queued", "building"):
                yield f"event: end\ndata: {json.dumps({'status': current})}\n\n"
                return

            await asyncio.sleep(1)

        yield "event: end\ndata: {\"status\": \"abgelaufen\"}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Fuer den Fall, dass irgendwann ein nginx davorsteht: Ohne diesen
            # Kopf puffert es den Strom und die Ereignisse kommen im Block.
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{template_id}/builds/{build_id}/activate", dependencies=[Depends(manage)])
def activate(
    template_id: uuid.UUID,
    build_id: uuid.UUID,
    request: Request,
    actor: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> BuildOut:
    """Setzt eine Version aktiv. Laufende Sessions bleiben unberuehrt."""
    tpl = db.get(Template, template_id)
    build = db.get(ImageBuild, build_id)
    if not tpl or not build or build.template_id != template_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Build nicht gefunden")
    if build.status != "ok" or not build.image_ref:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Nur ein erfolgreich gebautes Image kann aktiv werden.")

    for other in tpl.builds:
        other.is_current = False
    build.is_current = True
    tpl.image_ref = build.image_ref

    audit.record(db, "build.activated", actor=actor, object_type="template",
                 object_id=tpl.slug, request=request,
                 version=build.version, image=build.image_ref)
    db.commit()
    return _out(build)


@router.delete("/{template_id}/builds/{build_id}", dependencies=[Depends(manage)])
def delete_build(
    template_id: uuid.UUID,
    build_id: uuid.UUID,
    request: Request,
    actor: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> dict[str, str]:
    build = db.get(ImageBuild, build_id)
    if not build or build.template_id != template_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Build nicht gefunden")
    if build.is_current:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Die aktive Version kann nicht gelöscht werden. Erst eine andere aktivieren.",
        )

    version = build.version
    if build.image_ref:
        with contextlib.suppress(HTTPException):
            agent_client.remove_image(build.image_ref)
    db.delete(build)
    audit.record(db, "build.deleted", actor=actor, object_type="template",
                 object_id=str(template_id), request=request, version=version)
    db.commit()
    return {"status": f"Version v{version} entfernt"}
