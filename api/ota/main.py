from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from . import agent_client, migrate, recipes, schema_sync
from .db import Base, SessionLocal, engine
from .models import ImageBuild, Session as SessionModel
from .routers import (
    admin, auth, backups, builds, help as help_router, internal, monitoring,
    pwa, recipes as recipes_router, registries as registries_router,
    sessions, shared as shared_router, templates,
)

log = logging.getLogger("ota")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

REAP_INTERVAL = 60


def _reap_once() -> None:
    """Beendet Sessions ohne Lebenszeichen und raeumt verwaiste Container ab."""
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        live = db.scalars(select(SessionModel).where(
            SessionModel.status.in_(("running", "paused", "starting"))
        )).all()

        # Vorlagen, an denen gerade gebaut oder eingefroren wird. Deren
        # Sessions bleiben in Ruhe: `docker commit` haengt unbegrenzt, wenn der
        # Container mittendrin pausiert wird — ohne Fehler, ohne Meldung. Ein
        # Aufraeumer, der eine laufende Aufnahme abwuergt, ist schlimmer als
        # eine Session, die zehn Minuten laenger steht.
        beschaeftigt = {
            tid for (tid,) in db.execute(
                select(ImageBuild.template_id).where(
                    ImageBuild.status.in_(("queued", "building"))
                )
            ).all()
        }

        known: set[str] = set()
        for sess in live:
            if sess.container_id:
                known.add(sess.container_id)

            if sess.template_id in beschaeftigt:
                continue

            idle_minutes = sess.template.idle_minutes if sess.template else 60
            if idle_minutes >= 100_000:
                continue
            if now - sess.last_seen_at < timedelta(minutes=idle_minutes):
                continue

            action = sess.template.idle_action if sess.template else "stop"
            try:
                if action == "delete" and sess.container_id:
                    agent_client.remove_container(sess.container_id)
                    sess.status = "stopped"
                elif action == "pause" and sess.container_id:
                    agent_client.container_action(sess.container_id, "pause")
                    sess.status = "paused"
                elif sess.container_id:
                    agent_client.container_action(sess.container_id, "stop")
                    sess.status = "stopped"
            except Exception as exc:  # noqa: BLE001 — der Reaper darf nie sterben
                log.warning("Aufräumen von %s fehlgeschlagen: %s", sess.id, exc)
                continue

            if sess.status == "stopped":
                sess.ended_at = now
            sess.end_reason = "idle"
            log.info("Session %s wegen Leerlauf: %s", sess.id, action)

        # Aufraeumen. Zwei Faelle:
        #  - Waisen: tragen eine OTA-Kennzeichnung, sind der DB aber unbekannt.
        #  - Leichen: Container zu Sessions, die fehlgeschlagen oder laengst
        #    beendet sind. Ein gestoppter Container einer noch gueltigen
        #    Session bleibt bewusst liegen, damit sie schnell wieder anlaeuft.
        keep_stopped = {
            s.container_id for s in db.scalars(select(SessionModel).where(
                SessionModel.status == "stopped",
                SessionModel.end_reason == "idle",
            )).all() if s.container_id
        }
        try:
            for orphan in agent_client.orphans():
                cid = orphan["container_id"]
                if cid in known or cid in keep_stopped:
                    continue
                log.info("Container ohne gültige Session entfernt: %s (%s)",
                         cid[:12], orphan["status"])
                agent_client.remove_container(cid)
        except Exception as exc:  # noqa: BLE001
            log.debug("Aufräumen nicht möglich: %s", exc)

        db.commit()


def _backup_due() -> bool:
    """Steht ein geplanter Sicherungslauf an?

    Es genuegt, minuetlich zu pruefen: Der Lauf gilt als erledigt, sobald
    ``last_run_at`` am selben Tag nach der geplanten Zeit liegt. Damit holt
    der Zeitplan einen Lauf auch nach, wenn der Dienst zur geplanten Minute
    gerade neu gestartet wurde.
    """
    from .models import BackupPolicy

    now = datetime.now()
    with SessionLocal() as db:
        policy = db.scalar(select(BackupPolicy))
        if policy is None or not policy.is_enabled:
            return False
        if policy.weekdays and now.weekday() not in policy.weekdays:
            return False

        planned = now.replace(hour=policy.hour, minute=policy.minute,
                              second=0, microsecond=0)
        if now < planned:
            return False
        if policy.last_run_at is not None:
            last = policy.last_run_at
            if last.tzinfo is not None:
                last = last.astimezone().replace(tzinfo=None)
            if last >= planned:
                return False
        return True


async def _scheduler() -> None:
    from .routers.backups import run_scheduled

    while True:
        await asyncio.sleep(60)
        try:
            if await asyncio.to_thread(_backup_due):
                log.info("Geplante Sicherung startet")
                counts = await asyncio.to_thread(run_scheduled)
                log.info("Geplante Sicherung fertig: %s", counts)
        except Exception as exc:  # noqa: BLE001 — der Zeitplaner darf nie sterben
            log.warning("Geplante Sicherung fehlgeschlagen: %s", exc)


async def _reaper() -> None:
    while True:
        await asyncio.sleep(REAP_INTERVAL)
        try:
            await asyncio.to_thread(_reap_once)
        except Exception as exc:  # noqa: BLE001
            log.warning("Reaper-Durchlauf fehlgeschlagen: %s", exc)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Drei Schritte, und jeder deckt ab, was der vorige nicht kann:
    #
    #   1. Migrationen (migrate.py) — der eigentliche Weg. Baut eine leere
    #      Datenbank auf und uebernimmt eine bestehende per Stempel.
    #   2. create_all — legt Tabellen an, die noch keine Migration hat.
    #   3. schema_sync — ergaenzt fehlende Spalten. create_all tut das nicht,
    #      und genau daran ist am 2026-08-27 eine laufende Anlage gescheitert:
    #      neue Spalte im Modell, "Schema bereit" im Protokoll, und danach
    #      scheiterte jede Abfrage auf die Tabelle.
    #
    # Schritt 2 und 3 sind das Netz fuers Weiterbauen, nicht der Ersatz fuer
    # eine Migration. Was sie ergaenzen, steht im Protokoll und gehoert
    # nachgetragen.
    migrate.run(engine)
    Base.metadata.create_all(bind=engine)
    added = schema_sync.sync(engine)
    if added:
        log.info("Schema ergänzt: %s", ", ".join(added))
    log.info("Schema bereit")

    # Die mitgelieferten Rezepte gehoeren in dieselbe Tabelle wie selbst
    # gebaute. Sonst gaebe es zwei Quellen fuer dasselbe.
    with SessionLocal() as db:
        try:
            recipes.ensure_builtins(db)
        except Exception as exc:  # noqa: BLE001 — der Start darf daran nicht scheitern
            log.warning("Mitgelieferte Rezepte nicht angelegt: %s", exc)

    tasks = [asyncio.create_task(_reaper()), asyncio.create_task(_scheduler())]
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task


app = FastAPI(
    title="OpenTerminalApps API",
    version="0.1.0",
    lifespan=lifespan,
    # Kein oeffentliches Schema — die API ist kein Produkt fuer Dritte.
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.include_router(auth.router)
app.include_router(templates.router)
app.include_router(builds.router)
app.include_router(backups.router)
app.include_router(sessions.router)
app.include_router(admin.router)
app.include_router(help_router.router)
app.include_router(pwa.router)
app.include_router(recipes_router.router)
app.include_router(shared_router.router)
app.include_router(registries_router.router)
app.include_router(internal.router)
app.include_router(monitoring.router)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception) -> JSONResponse:
    log.exception("Unbehandelter Fehler bei %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Unerwarteter Fehler. Der Vorgang wurde abgebrochen."},
    )
