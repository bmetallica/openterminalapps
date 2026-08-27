from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from . import agent_client
from .db import Base, SessionLocal, engine
from .models import Session as SessionModel
from .routers import admin, auth, internal, sessions, templates

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

        known: set[str] = set()
        for sess in live:
            if sess.container_id:
                known.add(sess.container_id)

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


async def _reaper() -> None:
    while True:
        await asyncio.sleep(REAP_INTERVAL)
        try:
            await asyncio.to_thread(_reap_once)
        except Exception as exc:  # noqa: BLE001
            log.warning("Reaper-Durchlauf fehlgeschlagen: %s", exc)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Fuer den ersten Start. Spaetere Schemaaenderungen laufen ueber Alembic.
    Base.metadata.create_all(bind=engine)
    log.info("Schema bereit")

    task = asyncio.create_task(_reaper())
    try:
        yield
    finally:
        task.cancel()
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
app.include_router(sessions.router)
app.include_router(admin.router)
app.include_router(internal.router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception) -> JSONResponse:
    log.exception("Unbehandelter Fehler bei %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Unerwarteter Fehler. Der Vorgang wurde abgebrochen."},
    )
