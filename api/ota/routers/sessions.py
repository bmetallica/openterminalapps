from __future__ import annotations

import base64
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from .. import agent_client, audit
from ..config import settings
from ..db import get_db
from ..deps import current_user
from ..models import AppStream, Session as SessionModel, Template, TemplateApp, User
from ..schemas import SessionOut, SessionStartIn, StreamOut
from ..security import (
    effective_resources, owns_session, profile_path, user_can_see_template,
    vnc_secret,
)

router = APIRouter(prefix="/api/sessions", tags=["sessions"])
log = logging.getLogger("ota.sessions")

LIVE = ("starting", "running", "paused")

# Wie viele Anwendungen ein Arbeitsplatz gleichzeitig offen haben darf.
# Jede belegt ein eigenes Display und einen eigenen Websocket-Port.
MAX_APP_DISPLAYS = 6


def _stream_out(s: SessionModel, st: AppStream) -> StreamOut:
    data = StreamOut.model_validate(st)
    if st.display_num <= 1:
        # Display 1 ist der Hauptbildschirm des Containers und hat bereits
        # eine eigene Route.
        data.url = f"/s/{s.id}/?path=s/{s.id}/websockify"
    else:
        data.url = f"/s/{s.id}/a/{st.display_num}/?path=s/{s.id}/a/{st.display_num}/websockify"
    return data


def _out(s: SessionModel) -> SessionOut:
    return SessionOut(
        id=s.id,
        template_id=s.template_id,
        template_name=s.template.friendly_name,
        template_icon=s.template.icon,
        template_mode=s.template.mode,
        username=s.user.username,
        status=s.status,
        cores=s.cores,
        memory_bytes=s.memory_bytes,
        started_at=s.started_at,
        last_seen_at=s.last_seen_at,
        error=s.error,
        # Der KasmVNC-Client haengt seinen Websocket-Pfad an die Wurzel der
        # Seite, nicht an den aktuellen Pfad. Ohne diesen Parameter versucht er
        # wss://host/websockify — das landet bei der Weboberflaeche, die mit
        # 200 statt mit einem Upgrade antwortet, und es fliesst kein Bild.
        url=f"/s/{s.id}/?path=s/{s.id}/websockify",
        streams=[_stream_out(s, x) for x in s.streams],
    )


def _traefik_labels(sess_id: uuid.UUID, user_id: uuid.UUID, vnc_user: str,
                    secret: str) -> dict[str, str]:
    """Routing-Regeln fuer diese eine Session.

    Der Authorization-Header wird von Traefik gesetzt, nicht vom Browser.
    Das KasmVNC-Passwort verlaesst den Server damit nie.
    """
    sid = str(sess_id)
    name = f"s-{sess_id.hex}"
    basic = base64.b64encode(f"{vnc_user}:{secret}".encode()).decode()

    labels = {
        "traefik.enable": "true",
        "traefik.docker.network": "ota_public",

        f"traefik.http.routers.{name}.rule": f"PathPrefix(`/s/{sid}`)",
        f"traefik.http.routers.{name}.entrypoints": "websecure",
        f"traefik.http.routers.{name}.tls": "true",
        # Hoeher als die Web-App, die auf "/" liegt.
        f"traefik.http.routers.{name}.priority": "100",
        # Pflicht, sobald der Container mehr als einen Dienst definiert.
        # Ohne diese Zeile verweigert Traefik die Zuordnung und verwirft
        # ALLE Router dieses Containers — auch diesen hier.
        f"traefik.http.routers.{name}.service": name,
        f"traefik.http.routers.{name}.middlewares":
            f"ota-authz@file,{name}-strip@docker,{name}-basic@docker",

        f"traefik.http.middlewares.{name}-strip.stripprefix.prefixes": f"/s/{sid}",
        f"traefik.http.middlewares.{name}-basic.headers."
        f"customrequestheaders.Authorization": f"Basic {basic}",

        f"traefik.http.services.{name}.loadbalancer.server.port": "6901",
        f"traefik.http.services.{name}.loadbalancer.server.scheme": "https",
        f"traefik.http.services.{name}.loadbalancer.serverstransport": "ota-insecure@file",

        "ota.session_id": sid,
        "ota.user_id": str(user_id),
    }

    # Routen für die App-Displays gleich mitgeben. Labels lassen sich an einem
    # laufenden Container nicht mehr ändern, deshalb werden sie hier auf Vorrat
    # angelegt — sie kosten nichts, solange kein Display dahinter läuft.
    for display in range(2, 2 + MAX_APP_DISPLAYS):
        an = f"{name}-a{display}"
        labels.update({
            f"traefik.http.routers.{an}.rule": f"PathPrefix(`/s/{sid}/a/{display}`)",
            f"traefik.http.routers.{an}.entrypoints": "websecure",
            f"traefik.http.routers.{an}.tls": "true",
            # Höher als die Session-Wurzel, sonst gewinnt deren PathPrefix.
            f"traefik.http.routers.{an}.priority": "200",
            f"traefik.http.routers.{an}.service": an,
            f"traefik.http.routers.{an}.middlewares":
                f"ota-authz@file,{an}-strip@docker,{name}-basic@docker",
            f"traefik.http.middlewares.{an}-strip.stripprefix.prefixes": f"/s/{sid}/a/{display}",
            f"traefik.http.services.{an}.loadbalancer.server.port": str(6900 + display),
            f"traefik.http.services.{an}.loadbalancer.server.scheme": "https",
            f"traefik.http.services.{an}.loadbalancer.serverstransport": "ota-insecure@file",
        })

    return labels


@router.get("")
def list_sessions(
    all_users: bool = False,
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> list[SessionOut]:
    query = select(SessionModel).where(SessionModel.status.in_(LIVE))
    if not (all_users and (user.is_admin or "sessions.view_all" in user.permissions)):
        # Einschraenkung in der Abfrage, nicht im Frontend.
        query = query.where(SessionModel.user_id == user.id)
    sessions = db.scalars(query.order_by(SessionModel.started_at.desc())).all()
    return [_out(s) for s in sessions]


@router.post("", status_code=status.HTTP_201_CREATED)
def start_session(
    body: SessionStartIn,
    request: Request,
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> SessionOut:
    tpl = db.get(Template, body.template_id)
    if not tpl or not user_can_see_template(tpl, user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace nicht gefunden")
    if not tpl.is_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Dieser Workspace ist derzeit abgeschaltet.")

    # Laeuft schon eine? Dann diese zurueckgeben statt eine zweite zu starten.
    existing = db.scalar(select(SessionModel).where(
        SessionModel.user_id == user.id,
        SessionModel.template_id == tpl.id,
        SessionModel.status.in_(LIVE),
    ))
    if existing:
        return _out(existing)

    running = db.scalars(select(SessionModel).where(
        SessionModel.user_id == user.id, SessionModel.status.in_(LIVE)
    )).all()
    if len(running) >= settings().session_limit_per_user:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Du hast bereits {len(running)} Sessions offen. "
            "Beende eine davon, bevor du eine neue startest.",
        )

    cores, memory, _, _ = effective_resources(tpl, user)

    # Kapazitaets-Preflight: lieber eine verstaendliche Ablehnung als ein OOM-Kill.
    host = agent_client.host_info()
    if memory > host["memory_available"]:
        need = memory / 1024**3
        have = host["memory_available"] / 1024**3
        raise HTTPException(
            status.HTTP_507_INSUFFICIENT_STORAGE,
            f"Zu wenig freier Arbeitsspeicher: {have:.1f} GB frei, "
            f"{need:.1f} GB nötig. Beende eine andere Session oder wende dich "
            "an deinen Administrator.",
        )

    sess = SessionModel(
        user_id=user.id, template_id=tpl.id, cores=cores, memory_bytes=memory,
        vnc_secret=vnc_secret(), status="starting",
    )
    db.add(sess)
    db.flush()

    env = {str(k): str(v) for k, v in (tpl.env or {}).items()}
    env.setdefault("VNC_RESOLUTION", f"{tpl.x_res}x{tpl.y_res}")

    try:
        result = agent_client.start_container({
            "session_id": str(sess.id),
            "image": tpl.image_ref,
            "cores": cores,
            "memory_bytes": memory,
            "env": env,
            "profile_path": profile_path(user, tpl),
            "vnc_user": sess.vnc_user,
            "vnc_secret": sess.vnc_secret,
            "mode": tpl.mode,
            "labels": _traefik_labels(sess.id, user.id, sess.vnc_user, sess.vnc_secret),
        })
    except HTTPException:
        sess.status = "failed"
        sess.error = "Der Container konnte nicht gestartet werden."
        db.commit()
        raise

    sess.container_id = result["container_id"]
    sess.status = "running"
    audit.record(db, "session.started", actor=user, object_type="session",
                 object_id=str(sess.id), request=request,
                 template=tpl.slug, cores=cores, memory_bytes=memory)
    db.commit()
    return _out(sess)


def _load(session_id: uuid.UUID, user: User, db: DbSession) -> SessionModel:
    sess = db.get(SessionModel, session_id)
    if not sess or not owns_session(sess, user):
        # Bewusst 404 statt 403: fremde Session-IDs sollen nicht bestaetigt werden.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session nicht gefunden")
    return sess


@router.post("/{session_id}/heartbeat")
def heartbeat(
    session_id: uuid.UUID,
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> dict[str, str]:
    sess = _load(session_id, user, db)
    sess.last_seen_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": sess.status}


@router.post("/{session_id}/{action}")
def act(
    session_id: uuid.UUID,
    action: str,
    request: Request,
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> SessionOut:
    if action not in {"pause", "unpause", "stop"}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unbekannte Aktion")
    sess = _load(session_id, user, db)
    if not sess.container_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Für diese Session gibt es keinen Container.")

    # Ein pausierter Container wird fortgesetzt, ein gestoppter neu angefahren.
    # "unpause" auf einen gestoppten Container laeuft in einen Docker-Fehler.
    docker_action = action
    if action == "unpause" and sess.status == "stopped":
        docker_action = "start"

    agent_client.container_action(sess.container_id, docker_action)
    sess.status = {"pause": "paused", "unpause": "running", "stop": "stopped"}[action]
    if action == "unpause":
        sess.ended_at = None
        sess.end_reason = None
        sess.last_seen_at = datetime.now(timezone.utc)
    if action == "stop":
        sess.ended_at = datetime.now(timezone.utc)
        sess.end_reason = "user"
    audit.record(db, f"session.{action}", actor=user, object_type="session",
                 object_id=str(sess.id), request=request)
    db.commit()
    return _out(sess)


@router.delete("/{session_id}")
def delete_session(
    session_id: uuid.UUID,
    request: Request,
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> dict[str, str]:
    sess = _load(session_id, user, db)
    if sess.container_id:
        agent_client.remove_container(sess.container_id)
    sess.status = "stopped"
    sess.ended_at = datetime.now(timezone.utc)
    sess.end_reason = "user"
    audit.record(db, "session.deleted", actor=user, object_type="session",
                 object_id=str(sess.id), request=request)
    db.commit()
    # Das persistente Profil bleibt erhalten — geloescht wird nur der Container.
    return {"status": "Session beendet. Dein Profil bleibt erhalten."}


# --------------------------------------------------------------------------
# Arbeitsplatz: Anwendungen im laufenden Container (plan.md §9.2)
# --------------------------------------------------------------------------

def _ensure_clipboard_bridge(sess: SessionModel) -> None:
    """Sorgt dafuer, dass die Zwischenablage ueber alle Displays gleich ist.

    Ohne sie hat jede Anwendung im Arbeitsplatz ihre eigene X-Zwischenablage;
    Kopieren zwischen zwei Apps im selben Container funktioniert dann nicht
    (plan.md §10.4). Sie folgt den Rechten des Workspace: ist das Kopieren
    dort abgeschaltet, laeuft sie bewusst nicht.

    Ein Fehlschlag darf den App-Start nicht verhindern — der Weg ueber die
    Browser-Zwischenablage funktioniert weiterhin.
    """
    if not sess.container_id:
        return
    rights = sess.template.rights or {}
    wanted = bool(rights.get("clipboardUp", True) or rights.get("clipboardDown", True))
    try:
        agent_client.clipboard_bridge(sess.container_id, wanted)
    except HTTPException as exc:
        log.warning("Zwischenablage-Brücke: %s", exc.detail)


@router.post("/{session_id}/apps/{slug}")
def start_app(
    session_id: uuid.UUID,
    slug: str,
    request: Request,
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> SessionOut:
    """Startet eine Anwendung auf einem eigenen Display im selben Container."""
    sess = _load(session_id, user, db)
    if sess.status != "running" or not sess.container_id:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Der Arbeitsplatz läuft gerade nicht.")
    if sess.template.mode != "workspace":
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Dieser Workspace kennt nur eine Anwendung.")

    app = next((a for a in sess.template.apps if a.slug == slug), None)
    if app is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Diese Anwendung ist nicht hinterlegt.")
    if app.blocked_reason:
        raise HTTPException(status.HTTP_409_CONFLICT, app.blocked_reason)
    if not app.is_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"{app.name} ist für diesen Workspace abgeschaltet.")

    # Vor dem fruehen Ruecksprung: Auch wenn die Anwendung schon laeuft, muss
    # die Bruecke stehen — etwa nach einem Neustart der Dienste.
    _ensure_clipboard_bridge(sess)

    existing = next((s for s in sess.streams if s.app_slug == slug), None)
    if existing and existing.status == "running":
        existing.last_seen_at = datetime.now(timezone.utc)
        db.commit()
        return _out(sess)

    rights = sess.template.rights or {}

    if app.fixed_display is not None:
        # Einzelinstanz-Anwendung, die das Image bereits selbst gestartet hat.
        # Sie wird nur eingeblendet, nicht ein zweites Mal gestartet — ein
        # zweiter Aufruf wuerde sich lediglich bei der laufenden Instanz
        # melden und sich beenden, ohne ein Fenster zu oeffnen.
        display = app.fixed_display
        result = {"port": 6900 + display}
    else:
        # Displaynummer aus der Reihenfolge im Katalog ableiten: stabil ueber
        # Neustarts hinweg, und die Traefik-Route dafuer existiert bereits.
        order = [a.slug for a in sess.template.apps if a.fixed_display is None]
        display = order.index(slug) + 2
        if display >= 2 + MAX_APP_DISPLAYS:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Es sind höchstens {MAX_APP_DISPLAYS} Anwendungen gleichzeitig möglich.",
            )

        result = agent_client.start_app(sess.container_id, {
            "slug": slug,
            "command": f"{app.exec_cmd} {app.exec_args}".strip(),
            "display": display,
            "geometry": f"{sess.template.x_res}x{sess.template.y_res}",
            "title": app.name,
            "send_primary": bool(rights.get("clipboardPrimary")),
        })

    if existing:
        existing.status = "running"
        existing.display_num = display
        existing.port = result["port"]
        existing.last_seen_at = datetime.now(timezone.utc)
    else:
        db.add(AppStream(
            session_id=sess.id, app_slug=slug, display_num=display,
            port=result["port"], status="running",
        ))

    audit.record(db, "app.started", actor=user, object_type="session",
                 object_id=str(sess.id), request=request, app=slug, display=display)
    db.commit()
    db.refresh(sess)
    return _out(sess)


@router.delete("/{session_id}/apps/{slug}")
def stop_app(
    session_id: uuid.UUID,
    slug: str,
    request: Request,
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> SessionOut:
    sess = _load(session_id, user, db)
    stream = next((s for s in sess.streams if s.app_slug == slug), None)
    if stream is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Diese Anwendung läuft nicht.")

    # Den Hauptbildschirm des Containers niemals abbauen — dort haengt die
    # Anwendung, die das Image selbst gestartet hat.
    if sess.container_id and stream.display_num > 1:
        agent_client.stop_app(sess.container_id, stream.display_num)
    db.delete(stream)
    audit.record(db, "app.stopped", actor=user, object_type="session",
                 object_id=str(sess.id), request=request, app=slug)
    db.commit()
    db.refresh(sess)
    return _out(sess)
