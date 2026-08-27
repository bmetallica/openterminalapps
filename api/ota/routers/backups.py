"""Sicherung und Wiederherstellung (plan.md §11.2)."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from .. import agent_client, audit
from ..db import SessionLocal, get_db
from ..deps import current_user, require_permission
from ..models import (
    Backup, BackupPolicy, Session as SessionModel, Template, User,
)
from ..schemas import (
    BackupOut, BackupPolicyIn, BackupPolicyOut, BackupRunIn, BackupStorageOut,
)

router = APIRouter(prefix="/api/backups", tags=["backups"])
log = logging.getLogger("ota.backups")
manage = require_permission("settings.manage", "users.manage")

LIVE = ("starting", "running", "paused")


def _out(b: Backup) -> BackupOut:
    return BackupOut.model_validate(b)


def get_policy(db: DbSession) -> BackupPolicy:
    policy = db.scalar(select(BackupPolicy))
    if policy is None:
        policy = BackupPolicy()
        db.add(policy)
        db.commit()
    return policy


# --------------------------------------------------------------------------
# Ausfuehrung
# --------------------------------------------------------------------------

def run_profile_backup(db: DbSession, user: User, trigger: str,
                       actor: str | None) -> Backup | None:
    """Sichert das Home eines Nutzers.

    Laeuft auch, waehrend die Session offen ist. Das ist bewusst so: Wer nur
    bei geschlossener Session sichert, sichert in der Praxis nie. Ein Editor,
    der gerade schreibt, kann eine Datei im Archiv halbfertig hinterlassen —
    fuer Quelltext und Einstellungen ist das vertretbar, fuer Datenbanken
    waere es das nicht. Deshalb steht in der Oberflaeche der Hinweis, dass
    eine Sicherung bei geschlossener Session sauberer ist.
    """
    backup = Backup(kind="profile", user_id=user.id, username=user.username,
                    trigger=trigger, actor=actor, status="running")
    db.add(backup)
    db.commit()

    try:
        result = agent_client.backup_profile(user.username)
        backup.path = result["path"]
        backup.size_bytes = result["size_bytes"]
        backup.file_count = result["file_count"]
        backup.log = result["log"]
        backup.status = "ok"
    except HTTPException as exc:
        # Wer noch nie eine Session hatte, hat kein Profil. Das ist kein
        # Fehler, sondern der Normalfall bei frisch angelegten Konten — und
        # soll die Liste nicht mit roten Einträgen zustellen. Ob ein Profil
        # existiert, weiss nur der Agent: Die API hat das Dateisystem der
        # Profile bewusst nicht gemountet.
        if exc.status_code == 404:
            db.delete(backup)
            db.commit()
            return None
        backup.status = "failed"
        backup.error = str(exc.detail)
    finally:
        if backup in db:
            backup.finished_at = datetime.now(timezone.utc)
            db.commit()
    return backup


def run_container_backup(db: DbSession, sess: SessionModel, trigger: str,
                         actor: str | None) -> Backup:
    backup = Backup(kind="container", user_id=sess.user_id,
                    username=sess.user.username,
                    template_slug=sess.template.slug,
                    trigger=trigger, actor=actor, status="running")
    db.add(backup)
    db.commit()

    try:
        result = agent_client.backup_container(
            sess.container_id, sess.user.username, sess.template.slug,
        )
        backup.path = result.get("path")
        backup.size_bytes = result.get("size_bytes", 0)
        backup.file_count = result.get("file_count", 0)
        backup.log = result.get("log", "")
        backup.status = "ok"
    except HTTPException as exc:
        backup.status = "failed"
        backup.error = str(exc.detail)
    finally:
        backup.finished_at = datetime.now(timezone.utc)
        db.commit()
    return backup


def run_database_backup(db: DbSession, trigger: str, actor: str | None) -> Backup:
    """Sichert die Datenbank ueber pg_dump im Datenbank-Container."""
    from ..config import settings

    backup = Backup(kind="database", trigger=trigger, actor=actor, status="running")
    db.add(backup)
    db.commit()

    s = settings()
    try:
        result = agent_client.backup_database(s.db_container, s.db_user, s.db_name)
        backup.path = result["path"]
        backup.size_bytes = result["size_bytes"]
        backup.file_count = result["file_count"]
        backup.log = result["log"]
        backup.status = "ok"
    except HTTPException as exc:
        backup.status = "failed"
        backup.error = str(exc.detail)
    finally:
        backup.finished_at = datetime.now(timezone.utc)
        db.commit()
    return backup


STALE_AFTER = timedelta(hours=2)


def close_stale(db: DbSession) -> int:
    """Beendet Sicherungen, die auf ``running`` haengengeblieben sind.

    Passiert, wenn der Dienst mitten in einem Lauf neu startet — oder nach
    einer Wiederherstellung der Datenbank, die den Stand auf einen Zeitpunkt
    zurueckdreht, an dem der Lauf noch offen war. Ohne dieses Aufraeumen
    stuende dort fuer immer "läuft", und niemand wuesste, ob noch etwas
    passiert.
    """
    cutoff = datetime.now(timezone.utc) - STALE_AFTER
    stale = db.scalars(select(Backup).where(
        Backup.status == "running", Backup.started_at < cutoff,
    )).all()
    for backup in stale:
        backup.status = "failed"
        backup.error = ("Der Lauf wurde nicht abgeschlossen — vermutlich hat der "
                        "Dienst zwischendurch neu gestartet.")
        backup.finished_at = datetime.now(timezone.utc)
    if stale:
        db.commit()
    return len(stale)


def apply_retention(db: DbSession, policy: BackupPolicy) -> int:
    """Raeumt alte Sicherungen ab.

    Behalten werden die letzten ``keep_daily`` je Nutzer und Art, dazu
    ``keep_weekly`` aeltere im Wochenabstand. Fehlgeschlagene Laeufe fliegen
    nach 30 Tagen raus — sie belegen nichts, verstellen aber die Sicht.
    """
    # Haengengebliebene Laeufe zuerst abschliessen — sonst zaehlen sie als
    # gueltig und verdraengen eine echte Sicherung aus der Aufbewahrung.
    close_stale(db)

    removed = 0
    now = datetime.now(timezone.utc)

    groups: dict[tuple[str, str | None], list[Backup]] = {}
    for b in db.scalars(select(Backup).where(Backup.status == "ok")
                        .order_by(Backup.started_at.desc())).all():
        # Datenbanksicherungen haben keinen Nutzer und bilden eine eigene Reihe.
        groups.setdefault((b.kind, b.username), []).append(b)

    for items in groups.values():
        keep: set[uuid.UUID] = {b.id for b in items[:policy.keep_daily]}

        # Aus den aelteren je Kalenderwoche die neueste behalten.
        seen_weeks: set[tuple[int, int]] = set()
        for b in items[policy.keep_daily:]:
            week = b.started_at.isocalendar()[:2]
            if week in seen_weeks:
                continue
            seen_weeks.add(week)
            if len(seen_weeks) <= policy.keep_weekly:
                keep.add(b.id)

        for b in items:
            if b.id in keep:
                continue
            if b.path:
                try:
                    agent_client.delete_backup_file(b.path)
                except HTTPException:
                    pass
            db.delete(b)
            removed += 1

    cutoff = now - timedelta(days=30)
    for b in db.scalars(select(Backup).where(
            Backup.status == "failed", Backup.started_at < cutoff)).all():
        db.delete(b)
        removed += 1

    db.commit()
    return removed


def run_scheduled(trigger: str = "schedule", actor: str | None = None) -> dict[str, int]:
    """Ein vollstaendiger Sicherungslauf ueber alle Nutzer."""
    counts = {"profiles": 0, "containers": 0, "database": 0,
              "skipped": 0, "failed": 0, "removed": 0}
    with SessionLocal() as db:
        policy = get_policy(db)
        close_stale(db)

        if policy.include_profiles:
            for user in db.scalars(select(User).where(User.is_active.is_(True))).all():
                backup = run_profile_backup(db, user, trigger, actor)
                if backup is None:
                    counts["skipped"] += 1
                elif backup.status == "ok":
                    counts["profiles"] += 1
                else:
                    counts["failed"] += 1

        if policy.include_containers:
            for sess in db.scalars(select(SessionModel).where(
                    SessionModel.status.in_(LIVE))).all():
                if not sess.container_id:
                    continue
                backup = run_container_backup(db, sess, trigger, actor)
                if backup.status == "ok":
                    counts["containers"] += 1
                else:
                    counts["failed"] += 1

        if policy.include_database:
            backup = run_database_backup(db, trigger, actor)
            if backup.status == "ok":
                counts["database"] = 1
            else:
                counts["failed"] += 1

        counts["removed"] = apply_retention(db, policy)

        policy.last_run_at = datetime.now(timezone.utc)
        policy.last_result = (
            f"{counts['profiles']} Profile, {counts['containers']} Container, "
            f"{counts['database']} Datenbank, {counts['skipped']} ohne Profil, "
            f"{counts['failed']} Fehler, {counts['removed']} aufgeräumt"
        )
        db.commit()
    return counts


# --------------------------------------------------------------------------
# Endpunkte
# --------------------------------------------------------------------------

@router.get("", dependencies=[Depends(manage)])
def list_backups(limit: int = 200, db: DbSession = Depends(get_db)) -> list[BackupOut]:
    # Beim Hinsehen aufräumen: Ein Lauf, der beim Neustart des Dienstes
    # abgebrochen ist, stünde sonst für immer auf "läuft". Der Aufwand ist
    # eine Abfrage, und die Liste stimmt damit immer, wenn jemand sie öffnet.
    close_stale(db)

    rows = db.scalars(select(Backup).order_by(Backup.started_at.desc())
                      .limit(min(limit, 1000))).all()
    return [_out(b) for b in rows]


@router.get("/storage", dependencies=[Depends(manage)])
def storage() -> BackupStorageOut:
    """Zustand des Sicherungsverzeichnisses.

    Zeigt unter anderem, ob es auf einem eigenen Dateisystem liegt — das ist
    die Frage, die zaehlt, wenn spaeter ein NFS-Mount dahinter soll.
    """
    return BackupStorageOut(**agent_client.backup_root())


@router.get("/policy", dependencies=[Depends(manage)])
def read_policy(db: DbSession = Depends(get_db)) -> BackupPolicyOut:
    return BackupPolicyOut.model_validate(get_policy(db))


@router.put("/policy", dependencies=[Depends(manage)])
def write_policy(
    body: BackupPolicyIn,
    request: Request,
    actor: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> BackupPolicyOut:
    policy = get_policy(db)
    for key, value in body.model_dump().items():
        setattr(policy, key, value)
    audit.record(db, "backup.policy_changed", actor=actor, request=request,
                 enabled=body.is_enabled, hour=body.hour, minute=body.minute)
    db.commit()
    return BackupPolicyOut.model_validate(policy)


@router.post("/run", dependencies=[Depends(manage)],
             status_code=status.HTTP_202_ACCEPTED)
async def run_now(
    body: BackupRunIn,
    request: Request,
    actor: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> dict[str, str]:
    """Startet eine Sicherung von Hand.

    Ohne ``username`` werden alle aktiven Nutzer gesichert.
    """
    if body.username:
        user = db.scalar(select(User).where(User.username == body.username))
        if not user:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Nutzer nicht gefunden")

        audit.record(db, "backup.started", actor=actor, object_type="user",
                     object_id=user.username, request=request, kind="manual")
        db.commit()

        await asyncio.to_thread(_backup_one, user.id, actor.username,
                                body.include_container)
        return {"status": f"Sicherung für {user.username} abgeschlossen"}

    if body.database_only:
        audit.record(db, "backup.started", actor=actor, request=request, kind="datenbank")
        db.commit()
        result = await asyncio.to_thread(_backup_database_once, actor.username)
        return {"status": result}

    audit.record(db, "backup.started", actor=actor, request=request, kind="alle")
    db.commit()
    task = asyncio.create_task(asyncio.to_thread(run_scheduled, "manual", actor.username))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return {"status": "Sicherung aller Nutzer läuft. Der Fortschritt erscheint in der Liste."}


_tasks: set[asyncio.Task] = set()


def _backup_database_once(actor: str) -> str:
    with SessionLocal() as db:
        backup = run_database_backup(db, "manual", actor)
        if backup.status == "ok":
            return (f"Datenbank gesichert — {backup.size_bytes / 1024:.0f} KB "
                    f"komprimiert.")
        return f"Datenbanksicherung fehlgeschlagen: {backup.error}"


def _backup_one(user_id: uuid.UUID, actor: str, include_container: bool) -> None:
    with SessionLocal() as db:
        user = db.get(User, user_id)
        if user is None:
            return
        if run_profile_backup(db, user, "manual", actor) is None:
            log.info("%s hat noch kein Profil — übersprungen", user.username)
        if include_container:
            for sess in db.scalars(select(SessionModel).where(
                    SessionModel.user_id == user_id,
                    SessionModel.status.in_(LIVE))).all():
                if sess.container_id:
                    run_container_backup(db, sess, "manual", actor)


@router.post("/{backup_id}/restore", dependencies=[Depends(manage)])
def restore(
    backup_id: uuid.UUID,
    request: Request,
    actor: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> dict[str, str]:
    """Spielt eine Sicherung zurueck.

    Zwei Schutzmassnahmen, beide nicht verhandelbar:

    1. Solange eine Session des Nutzers laeuft, wird abgelehnt. Ein Profil
       unter einem laufenden Editor auszutauschen fuehrt zu Datenverlust auf
       beiden Seiten.
    2. Der bisherige Stand wird nicht geloescht, sondern beiseitegelegt. Eine
       Wiederherstellung, die im Fehlerfall nichts uebriglaesst, ist keine.
    """
    backup = db.get(Backup, backup_id)
    if not backup or backup.status != "ok" or not backup.path:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "Diese Sicherung gibt es nicht oder sie ist unbrauchbar.")

    if backup.username:
        running = db.scalars(select(SessionModel).join(User).where(
            User.username == backup.username,
            SessionModel.status.in_(LIVE),
        )).all()
        if running:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"{backup.username} hat noch {len(running)} laufende Session(s). "
                "Beende sie zuerst — ein Profil unter einem laufenden Editor "
                "auszutauschen führt auf beiden Seiten zu Datenverlust.",
            )

    if backup.kind == "profile":
        result = agent_client.restore_profile(backup.username, backup.path)
        detail = result.get("previous_kept_at")
        audit.record(db, "backup.restored", actor=actor, object_type="user",
                     object_id=backup.username, request=request,
                     archive=backup.path)
        db.commit()
        return {
            "status": f"Profil von {backup.username} wiederhergestellt."
                      + (f" Der bisherige Stand liegt unter {detail}." if detail else ""),
        }

    if backup.kind == "container":
        # Anders als beim Profil braucht diese Wiederherstellung einen
        # LAUFENDEN Container — die Dateien werden hineingelegt. Die Pruefung
        # oben greift hier deshalb nicht: Sie steht vor diesem Zweig und
        # betrifft nur Profile.
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Container-Sicherungen werden über den laufenden Arbeitsplatz "
            "zurückgespielt. Nutze dafür /restore-into-session.",
        )

    if backup.kind == "database":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Die Datenbank lässt sich nicht aus der laufenden Anwendung heraus "
            "zurückspielen — sie trägt die Anmeldung, mit der du gerade hier bist. "
            "Der Weg dafür ist `scripts/restore-db.sh`, das die Dienste vorher "
            "anhält. Siehe Handbuch, Kapitel 14.",
        )

    raise HTTPException(status.HTTP_400_BAD_REQUEST,
                        f"Für die Art {backup.kind} gibt es keine Wiederherstellung.")


@router.post("/{backup_id}/restore-into-session", dependencies=[Depends(manage)])
def restore_into_session(
    backup_id: uuid.UUID,
    request: Request,
    actor: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> dict[str, str]:
    """Spielt eine Container-Sicherung in den laufenden Arbeitsplatz zurueck.

    Anders als beim Profil braucht das einen **laufenden** Container: Die
    Dateien werden hineingelegt. Sie liegen ausserhalb des Home und werden
    von bereits gestarteten Anwendungen nicht mehr gelesen — deshalb der
    Hinweis, die Apps danach neu zu oeffnen.
    """
    backup = db.get(Backup, backup_id)
    if not backup or backup.kind != "container" or backup.status != "ok" or not backup.path:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "Diese Container-Sicherung gibt es nicht oder sie ist leer.")

    sess = db.scalar(select(SessionModel).join(User).join(Template).where(
        User.username == backup.username,
        Template.slug == backup.template_slug,
        SessionModel.status.in_(LIVE),
    ))
    if sess is None or not sess.container_id:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Für {backup.username} läuft gerade kein Arbeitsplatz "
            f"'{backup.template_slug}'. Starte ihn zuerst — die Dateien werden "
            "in den laufenden Container gelegt.",
        )

    agent_client.restore_container(sess.container_id, backup.path)
    audit.record(db, "backup.restored_container", actor=actor, object_type="session",
                 object_id=str(sess.id), request=request, archive=backup.path)
    db.commit()
    return {
        "status": f"{backup.file_count} Dateien in den Arbeitsplatz von "
                  f"{backup.username} zurückgespielt. Bereits geöffnete Anwendungen "
                  "lesen sie nicht mehr — schliesse und öffne sie neu.",
    }


@router.delete("/{backup_id}", dependencies=[Depends(manage)])
def delete_backup(
    backup_id: uuid.UUID,
    request: Request,
    actor: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> dict[str, str]:
    backup = db.get(Backup, backup_id)
    if not backup:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sicherung nicht gefunden")
    if backup.path:
        try:
            agent_client.delete_backup_file(backup.path)
        except HTTPException:
            pass
    db.delete(backup)
    audit.record(db, "backup.deleted", actor=actor, request=request,
                 archive=backup.path)
    db.commit()
    return {"status": "Sicherung entfernt"}
