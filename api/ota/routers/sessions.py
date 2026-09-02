from __future__ import annotations

import base64
import json
import logging
import os
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from .. import agent_client, audit, settings_store
from ..config import settings
from ..db import get_db
from ..deps import current_user
from ..models import (
    AppStream, OnceScriptRun, Session as SessionModel, Template, TemplateApp, User,
)
from ..schemas import SessionOut, SessionStartIn, StreamOut
from ..security import (
    effective_resources, needs_totp, owns_session, profile_path,
    user_can_see_app, user_can_see_template, vnc_secret,
)

router = APIRouter(prefix="/api/sessions", tags=["sessions"])
log = logging.getLogger("ota.sessions")

LIVE = ("starting", "running", "paused")

# Wie viele Anwendungen ein Arbeitsplatz gleichzeitig offen haben darf.
# Jede belegt ein eigenes Display und einen eigenen Websocket-Port.
MAX_APP_DISPLAYS = 6

# Der KasmVNC-Client stellt sich anders ein, sobald er in einem iframe laeuft
# (ui.js: `window.self !== window.top`). Er schaltet dann drei Dinge ab, die
# fuer OTA nicht verhandelbar sind:
#
#   clipboard_up / clipboard_down   `rfb.clipboardDown` bleibt false, und
#       `clipboardReceive()` verwirft alles, was der Server schickt. Der Weg
#       aus der Session heraus ist tot, ohne dass irgendwo ein Fehler steht.
#   resize                          faellt von "remote" auf "off". Der ferne
#       Bildschirm behaelt dann seine Startgroesse und sitzt mit schwarzem
#       Rand mitten im Fenster. Genau das hat sich beim Arbeiten falsch
#       angefuehlt: eine Anwendung, die nicht mitwaechst.
#
# Alle drei lassen sich per URL ueberschreiben, denn `initSetting()` liest
# zuerst die Adresse und erst danach den gespeicherten Vorgabewert.
# `clipboard_seamless` bleibt bewusst aus: den Abgleich mit der System-
# zwischenablage macht die Bruecke im Elternfenster, das dafuer auch die
# Rechte hat.
#
# `idle_disconnect` ist der vierte — und der teuerste. KasmVNC trennt von
# sich aus nach 20 Minuten **ohne Eingabe**:
#
#     const s = (Date.now() - rfb.lastActiveAt) / 1000
#     let l = 1200
#     if (Number.isFinite(parseFloat(rfb.idleDisconnect)))
#         l = parseFloat(rfb.idleDisconnect) * 60
#     if (s > l) window.location.replace("disconnect…")
#
# Gezaehlt werden nur Maus und Tastatur. Wer einem langen Build zusieht, ohne
# das Fenster anzufassen, fliegt heraus — und weil `reconnect` im Client aus
# ist, bleibt das Bild danach einfach weg. Fuer den Benutzer sah das aus, als
# haette OTA die Session beendet, lange vor der eingestellten Grenze.
#
# Ueber die Laufzeit einer Session entscheidet OTA, nicht der Client: Solange
# ein Fenster offen ist, kommt alle 30 Sekunden ein Herzschlag, und erst wenn
# der ausbleibt, greift `idle_minutes` der Vorlage (api/ota/main.py).
#
# Ueber die Adresse laesst sich die Uhr nur bis 60 Minuten stellen: Das Feld
# ist im Client ein `<select>` mit genau vier Werten (10, 20, 30, 60). Ein
# Wert, den es dort nicht gibt, wird nicht etwa uebernommen, sondern faellt
# auf den **ersten** Eintrag zurueck — aus einem gut gemeinten `525600` wurden
# gemessene 10 Minuten, also die Halbierung dessen, was ohne den Parameter da
# gestanden haette. Eine `0` waere noch schlimmer: `parseFloat("0")` ist
# endlich, die Grenze damit null Sekunden, die Verbindung faellt sofort.
#
# 60 Minuten sind deshalb nur die Untergrenze. Ganz aus macht sie der Viewer,
# sobald das Bild steht — er schickt dem Client eine Nachricht, die an dem
# `<select>` vorbeigeht (siehe web/src/screens/SessionViewer.tsx).
STREAM_ARGS = (
    "&clipboard_up=1&clipboard_down=1&clipboard_seamless=0"
    "&resize=remote&idle_disconnect=60"
)


# Wohin die API schaut, um zu erfahren, ob eine Route schon steht.
TRAEFIK_API = os.environ.get("OTA_TRAEFIK_API", "http://traefik:8081")
ROUTE_TIMEOUT = 25.0


def _wait_for_route(sess_id: uuid.UUID, timeout: float = ROUTE_TIMEOUT) -> bool:
    """Wartet, bis Traefik die Route dieser Session kennt.

    Warum das noetig ist: Der Docker-Provider bemerkt einen neuen Container
    erst beim naechsten Durchlauf. In der Luecke dazwischen passt kein
    Session-Router, und der Schutzwall aus `session-guard.yml` antwortet mit
    "Diese Sitzung läuft nicht mehr" — fuer den Anwender sieht das aus, als
    waere die Session sofort wieder gestorben. Genau das ist passiert.

    Die API meldet die Session deshalb erst als `running`, wenn sie auch
    erreichbar ist. Scheitert das Warten, wird der Start trotzdem nicht
    abgebrochen: Der Container laeuft ja. Die Session bleibt dann auf
    `starting`, und das Dashboard versucht es weiter.
    """
    name = f"s-{sess_id.hex}@docker"
    deadline = time.monotonic() + timeout
    url = f"{TRAEFIK_API}/api/http/routers/{name}"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as res:
                if res.status == 200:
                    data = json.load(res)
                    if data.get("status") == "enabled":
                        return True
        except (urllib.error.URLError, OSError, ValueError):
            pass
        time.sleep(0.5)
    return False


def _stream_out(s: SessionModel, st: AppStream) -> StreamOut:
    data = StreamOut.model_validate(st)
    if st.display_num <= 1:
        # Display 1 ist der Hauptbildschirm des Containers und hat bereits
        # eine eigene Route.
        data.url = f"/s/{s.id}/?path=s/{s.id}/websockify{STREAM_ARGS}"
    else:
        data.url = (f"/s/{s.id}/a/{st.display_num}/"
                    f"?path=s/{s.id}/a/{st.display_num}/websockify{STREAM_ARGS}")
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
        url=f"/s/{s.id}/?path=s/{s.id}/websockify{STREAM_ARGS}",
        streams=[_stream_out(s, x) for x in s.streams],
    )


def _offene_einmal_skripte(db: DbSession, tpl, user) -> list[dict[str, str]]:
    """Welche Einmal-Skripte dieser Nutzer noch nicht hatte.

    Gebucht wird je Nutzer und Skript, nicht je Session: Wer drei
    Arbeitsplätze derselben Vorlage nacheinander startet, bekommt es einmal.
    Ein neues Skript ist ein neuer Eintrag und läuft wieder für alle — genau
    dafür gibt es sie.
    """
    if not tpl.once_scripts:
        return []

    erledigt = set(db.scalars(
        select(OnceScriptRun.script_id).where(OnceScriptRun.user_id == user.id)
    ).all())
    return [
        {"id": str(x.id), "name": x.name, "body": x.body}
        for x in tpl.once_scripts
        if x.is_enabled and x.body.strip() and x.id not in erledigt
    ]


def _buche_einmal_skripte(db: DbSession, user, ergebnisse: list[dict]) -> None:
    """Hält fest, was gelaufen ist — auch das, was schiefging.

    Ein gescheitertes Skript wird trotzdem gebucht. Sonst liefe ein kaputtes
    bei **jedem** Start jedes Nutzers erneut, und aus einem Fehler würde eine
    Dauerbelastung. Sichtbar bleibt er: Die Verwaltung sieht Rückgabewert und
    Ausgabe und kann ausdrücklich „nochmal" sagen.

    Nicht gebucht wird, was gar nicht zustande kam — der Agent berichtet dann
    kein Ergebnis, und der nächste Start versucht es wieder.
    """
    for eintrag in ergebnisse:
        try:
            script_id = uuid.UUID(str(eintrag.get("id")))
        except (ValueError, TypeError):
            continue
        db.add(OnceScriptRun(
            script_id=script_id, user_id=user.id,
            exit_code=int(eintrag.get("exit_code") or 0),
            output=str(eintrag.get("output") or "")[:8000],
        ))
    if ergebnisse:
        try:
            db.commit()
        except IntegrityError:
            # Zwei Starts gleichzeitig — die Eindeutigkeit hat entschieden.
            # Das Skript ist dann trotzdem gelaufen, und mehr als einmal
            # gebucht muss es nicht sein.
            db.rollback()


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
    if needs_totp(user):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Für deine Gruppe ist der zweite Faktor Pflicht. Richte ihn unter "
            "„Mein Konto“ ein — danach lassen sich Arbeitsplätze wieder starten.",
        )

    tpl = db.get(Template, body.template_id)
    if not tpl or not user_can_see_template(tpl, user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace nicht gefunden")
    if not tpl.is_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Dieser Workspace ist derzeit abgeschaltet.")

    # Laeuft schon eine? Dann diese zurueckgeben statt eine zweite zu starten.
    #
    # Aber nur, wenn sie auch wirklich laeuft. Eine Session, deren Container
    # nicht mehr da ist, steht sonst fuer immer im Weg: Sie zaehlt als „live",
    # wird hier zurueckgegeben, und der naechste Startversuch bekommt wieder
    # dieselbe Leiche. Gemessen am 2026-08-28 — ein Arbeitsplatz liess sich
    # stundenlang nicht mehr starten, und die Oberflaeche sagte nur
    # „starting".
    existing = db.scalar(select(SessionModel).where(
        SessionModel.user_id == user.id,
        SessionModel.template_id == tpl.id,
        SessionModel.status.in_(LIVE),
    ))
    if existing is not None and not _really_alive(existing):
        log.info("Session %s zeigt ins Leere — wird geschlossen und neu gestartet",
                 existing.id)
        existing.status = "stopped"
        existing.ended_at = datetime.now(timezone.utc)
        existing.end_reason = "container_weg"
        db.commit()
        existing = None
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

    # Kapazitaets-Preflight: lieber eine verstaendliche Ablehnung als ein
    # OOM-Kill oder ein Container, der beim Schreiben stehenbleibt. Drei
    # Fragen, in dieser Reihenfolge — die billigste zuerst.
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

    floor = settings_store.disk_floor_bytes(db)
    if floor and host.get("disk_free", 0) < floor:
        raise HTTPException(
            status.HTTP_507_INSUFFICIENT_STORAGE,
            f"Auf dem Host sind nur noch {host['disk_free'] / 1024**3:.1f} GB "
            f"frei; ab {floor / 1024**3:.0f} GB startet nichts mehr. Ein volles "
            "Dateisystem bringt laufende Arbeitsplätze zum Stehen — das hier "
            "ist die Bremse davor. Bitte den Administrator informieren.",
        )

    # Und das eigene Zuhause. Gemessen wird im Agent und dort gepuffert; ein
    # Profil waechst nicht zwischen zwei Starts um Gigabytes.
    quota = settings_store.profile_quota_bytes(db)
    if quota and tpl.persistence_scope != "none":
        try:
            used = int(agent_client.profile_usage(str(user.id)).get("bytes", 0))
        except Exception:  # noqa: BLE001 — eine Messung darf keinen Start verhindern
            used = 0
        if used >= quota:
            raise HTTPException(
                status.HTTP_507_INSUFFICIENT_STORAGE,
                f"Dein Zuhause belegt {used / 1024**3:.1f} GB und damit die "
                f"gesamten {quota / 1024**3:.0f} GB, die dir zustehen. Räume "
                "auf — Downloads, Caches, alte Container-Abbilder — oder bitte "
                "deinen Administrator um mehr Platz.",
            )

    # Das Profil bestimmt das VNC-Passwort mit — siehe `vnc_secret()`.
    profile = profile_path(user, tpl)

    # Zwei laufende Container auf einem Zuhause vertragen sich nicht.
    #
    # Das ist keine Vorsicht, sondern die Lehre aus zwei gemessenen Schaeden
    # am 2026-08-27. Beide entstanden dadurch, dass zwei Container desselben
    # Nutzers dasselbe `/home/kasm-user` beschrieben:
    #
    #   1. Der Startvorgang der Kasm-Images schreibt `~/.kasmpasswd` neu. Der
    #      zweite Container entwertete damit die Zugangsdaten des ersten —
    #      dessen Streams antworteten ab da mit 401 (siehe security.vnc_secret).
    #   2. VS Code ist einzelinstanzig und legt seinen Steuerkanal als Socket
    #      im Profil ab. Der zweite Container fand ihn, reichte den Aufruf an
    #      die Instanz im *ersten* Container weiter und beendete sich — worauf
    #      die Aufsicht des Images ihn alle drei Sekunden erneut startete.
    #      Ergebnis: ein leeres Fenster nach dem anderen im fremden Container.
    #
    # Beides liesse sich einzeln abfangen. Die gemeinsame Ursache nicht: Ein
    # Zuhause ist fuer einen Rechner gedacht, nicht fuer zwei. Wer beides
    # gleichzeitig braucht, gibt der zweiten Vorlage ein eigenes Profil
    # (Persistenz "Pro Workspace").
    if profile:
        clash = next((s for s in running
                      if profile_path(user, s.template) == profile), None)
        if clash is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"„{clash.template.friendly_name}“ läuft schon und benutzt "
                "dasselbe Zuhause. Zwei Arbeitsplätze auf einem Profil geraten "
                "sich in die Quere. Beende den anderen — oder gib diesem "
                "Workspace unter Persistenz ein eigenes Profil.",
            )

    sess = SessionModel(
        user_id=user.id, template_id=tpl.id, cores=cores, memory_bytes=memory,
        vnc_secret=vnc_secret(user, profile), status="starting",
    )
    db.add(sess)
    # **Committen, nicht nur flushen** — bevor der Container entsteht.
    #
    # Ein `flush` schreibt die Zeile nur innerhalb dieser Transaktion. Fuer
    # jede andere Verbindung gibt es die Session bis zum `commit` nicht — und
    # der kam frueher erst am Ende, nach dem vollstaendigen Start des
    # Containers samt Skeleton, Einmal-Skripten und Startskript. Das dauert
    # unter Last ueber eine Minute.
    #
    # In genau diesem Fenster laeuft der Aufraeumer (`main._reap_once`,
    # minuetlich). Er sieht einen Container mit OTA-Kennzeichnung, findet in
    # der Datenbank keine Session dazu — und entfernt ihn. Mitten im Start.
    #
    # Das Ergebnis sah jedes Mal anders aus und nie nach der Ursache: ein
    # Startskript, das mit 137 endet (SIGKILL), ein Einmal-Skript ohne
    # Ausgabe, „KasmVNC war nach 40s noch nicht bereit", drei 409er
    # hinterher. Aufgefallen ist es als sprunghaft fehlschlagende Pruefungen
    # auf einem gut ausgelasteten Rechner — je laenger der Start dauert,
    # desto wahrscheinlicher der Treffer.
    db.commit()

    env = {str(k): str(v) for k, v in (tpl.env or {}).items()}
    env.setdefault("VNC_RESOLUTION", f"{tpl.x_res}x{tpl.y_res}")

    try:
        result = agent_client.start_container({
            "session_id": str(sess.id),
            "image": tpl.image_ref,
            "cores": cores,
            "memory_bytes": memory,
            "env": env,
            "profile_path": profile,
            "vnc_user": sess.vnc_user,
            "vnc_secret": sess.vnc_secret,
            "mode": tpl.mode,
            # Administratoren duerfen in ihrem Container root werden, sonst
            # koennten sie dort nichts nachinstallieren. Die Entscheidung faellt
            # hier und nicht im Agent: Der Agent kennt keine Rollen.
            "elevated": user.is_admin,
            # Die eigene Ablage des Nutzers, beschreibbar unter
            # /mnt/austausch. Die Vorlage kann sie abschalten — fuer
            # Arbeitsplaetze, aus denen bewusst nichts herausgetragen werden
            # soll. Leer heisst: nicht einhaengen.
            # Die Kennung, nicht der Name — aus demselben Grund wie beim
            # Profil (siehe security.profile_path).
            "shelf_user": str(user.id) if tpl.user_shelf else "",
            # Nur fuer den Verweis im Dateisystem, damit dort jemand etwas
            # findet. Ueber den Pfad entscheidet er nicht.
            "shelf_name": user.username,
            # Die Laufwerke der Gruppen, in denen dieser Mensch **jetzt** ist.
            # Wer waehrend der Session hinausfaellt, behaelt sie bis zum
            # naechsten Start: Einem laufenden Container einen Bind-Mount zu
            # entziehen ginge nur, indem man ihn beendet — und jemanden mitten
            # in der Arbeit hinauszuwerfen waere schlimmer als die Stunde bis
            # zum naechsten Start (auth-roadmap.md). Im Browser wirkt der
            # Entzug sofort.
            "group_shelves": ([{"id": str(g.id), "name": g.name}
                               for g in user.groups] if tpl.group_shelf else []),
            # Einmal-Skripte, die dieser Nutzer noch nicht hatte. Welche das
            # sind, weiss nur die API — der Agent fuehrt aus und berichtet.
            "once_scripts": _offene_einmal_skripte(db, tpl, user),
            # Womit ein Zuhause anfaengt. Beim ersten Start der ganze Baum,
            # danach nur die durchgesetzten Pfade.
            "template_slug": tpl.slug,
            "skeleton_enforce": list(tpl.skeleton_enforce or []),
            # Laeuft nach dem Start als Nutzer im Container.
            "start_script": tpl.start_script or "",
            "labels": _traefik_labels(sess.id, user.id, sess.vnc_user, sess.vnc_secret),
        })
    except HTTPException:
        sess.status = "failed"
        sess.error = "Der Container konnte nicht gestartet werden."
        db.commit()
        raise

    _buche_einmal_skripte(db, user, result.get("once") or [])

    sess.container_id = result["container_id"]
    # Erst wenn die Route steht, ist die Session fuer den Browser da.
    sess.status = "running" if _wait_for_route(sess.id) else "starting"
    audit.record(db, "session.started", actor=user, object_type="session",
                 object_id=str(sess.id), request=request,
                 template=tpl.slug, cores=cores, memory_bytes=memory)
    db.commit()
    return _out(sess)


def _display_lebt(sess: SessionModel, stream) -> bool:
    """Gibt es das X-Display dieses Streams im Container ueberhaupt noch?

    Ein Display kann sterben, ohne dass jemand OTA davon erzaehlt: Die
    Anwendung stuerzt ab, jemand beendet `Xvnc` von Hand, der Speicher geht
    aus. Danach steht in der Datenbank „running", und der Browser zeigt einen
    abgerissenen Stream.

    Bei Zweifeln ja: Antwortet der Agent nicht, ist die Aussage „das Display
    ist weg" nicht gedeckt.
    """
    if not sess.container_id:
        return False
    try:
        return stream.display_num in agent_client.list_displays(sess.container_id)
    except HTTPException:
        return True


def _really_alive(sess: SessionModel) -> bool:
    """Gibt es den Container dieser Session ueberhaupt noch?

    Die Datenbank weiss nur, was ihr zuletzt gesagt wurde. Ein Container kann
    verschwinden, ohne dass jemand OTA davon erzaehlt — ein Neustart des
    Docker-Dienstes, ein fremder Aufraeumer, ein `docker rm` von Hand. Danach
    steht in der Datenbank „laeuft", und in Wirklichkeit laeuft nichts.
    """
    if not sess.container_id:
        return False
    try:
        zustand = agent_client.container_status(sess.container_id).get("status", "")
    except HTTPException:
        # Der Agent antwortet nicht. Dann ist die Aussage „der Container ist
        # weg" nicht gedeckt — im Zweifel die Session stehen lassen.
        return True
    return zustand not in ("gone", "exited", "dead", "removing")


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
    # Die Liste im Dashboard ist schon gefiltert. Das hier ist die Stelle, die
    # zaehlt: Ein Aufruf dieser Adresse mit fremdem Kuerzel darf nicht starten,
    # nur weil der Arbeitsplatz demselben Nutzer gehoert.
    if not user_can_see_app(app, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            f"{app.name} ist für dich nicht freigegeben.")

    # Vor dem fruehen Ruecksprung: Auch wenn die Anwendung schon laeuft, muss
    # die Bruecke stehen — etwa nach einem Neustart der Dienste.
    _ensure_clipboard_bridge(sess)

    existing = next((s for s in sess.streams if s.app_slug == slug), None)
    if existing and existing.status == "running" and _display_lebt(sess, existing):
        existing.last_seen_at = datetime.now(timezone.utc)
        db.commit()
        return _out(sess)
    if existing and existing.status == "running":
        # Der Eintrag sagt „laeuft", das Display gibt es nicht mehr. Ohne
        # diese Pruefung kehrte der Start hier zurueck, ohne etwas zu tun —
        # und die Anwendung waere fuer immer tot: Der Tab zeigt einen
        # abgerissenen Stream, und der Startknopf im Dashboard bewirkt
        # nichts. Gemessen am 2026-08-28.
        log.info("Display :%s von %s ist weg — wird neu aufgemacht",
                 existing.display_num, slug)
        existing.status = "stopped"

    rights = sess.template.rights or {}

    if app.fixed_display is not None:
        # Einzelinstanz-Anwendungen gehoeren auf ein festes Display.
        #
        # `fixed_display` heisst "diese Anwendung muss auf genau diesem
        # Bildschirm laufen" — nicht "sie laeuft dort bereits". Der
        # Unterschied hat Zeit gekostet: Frueher legte die API hier nur den
        # Datensatz an und rief den Agent gar nicht, weil das Basisimage die
        # Anwendung ohnehin startete. Das stimmte nur, solange dessen
        # Startskript sie im Drei-Sekunden-Takt neu startete — und genau das
        # produzierte hundertfach leere Fenster. Seit der Arbeitsplatz das
        # nicht mehr tut (siehe `WORKSPACE_STARTUP` im Agent), muss die
        # Anwendung hier wirklich gestartet werden.
        display = app.fixed_display
    else:
        # Das erste freie Display nehmen — nicht die Position im Katalog.
        #
        # Frueher stand hier `order.index(slug) + 2`. Damit war die
        # Displaynummer an die Stelle im Katalog gebunden, und die Grenze von
        # sechs galt nicht fuer gleichzeitig offene Anwendungen, sondern fuer
        # die Groesse des Katalogs. Gemessen am 2026-08-27: Bei zehn
        # eingetragenen Anwendungen liessen sich die letzten vier nie starten —
        # mit der Meldung „höchstens 6 gleichzeitig", obwohl keine einzige
        # lief. Und alphabetisch traf es ausgerechnet VS Code und VSCodium.
        #
        # Die Traefik-Routen fuer 2 bis 7 legt der Containerstart auf Vorrat
        # an; welche Anwendung darauf liegt, darf sich von Start zu Start
        # unterscheiden. Die Adresse kommt ohnehin aus der API.
        taken = {
            s.display_num for s in sess.streams
            if s.status == "running" and s.app_slug != slug
        }
        display = next(
            (n for n in range(2, 2 + MAX_APP_DISPLAYS) if n not in taken), None
        )
        if display is None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Es sind höchstens {MAX_APP_DISPLAYS} Anwendungen gleichzeitig "
                "offen. Schliesse eine, dann geht die nächste auf.",
            )

    # Auf einem bereits offenen Display legt der Agent kein zweites an; das
    # Startskript erkennt das und ueberspringt es.
    result = agent_client.start_app(sess.container_id, {
        "slug": slug,
        "command": f"{app.exec_cmd} {app.exec_args}".strip(),
        # Damit der Agent den Skeleton-Teilbaum dieser Anwendung findet. Er
        # kommt beim **ersten** Start dieser Anwendung in dieses Zuhause, und
        # zwar bevor sie laeuft — sonst legt sie ihre Voreinstellungen an, und
        # der Teilbaum ueberschriebe hinterher, was der Mensch schon sieht.
        "template_slug": sess.template.slug,
        "display": display,
        # Die Aufloesung der Anwendung, sonst die des Arbeitsplatzes. Der
        # Strom passt sich anschliessend ohnehin dem Browserfenster an
        # (`resize=remote`) — das hier ist der Anfangswert, und der
        # entscheidet, wie eine Anwendung ihre Oberflaeche zuerst aufbaut.
        "geometry": (f"{app.x_res or sess.template.x_res}"
                     f"x{app.y_res or sess.template.y_res}"),
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
