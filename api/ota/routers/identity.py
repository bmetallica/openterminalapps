"""Die Verzeichnis-Anbindung verwalten (plan.md §9.4).

Ein Bildschirm, ein Prüf-Knopf, ein Schalter. Der Schalter steht auf **aus**,
bis jemand die Prüfung bestanden gesehen hat — das ist die einzige
Einstellung in OTA, bei der ein Fehler Menschen aussperrt, und sie soll
deshalb nicht blind einzuschalten sein.

Das Kennwort des Dienstkontos geht nur **hinein**. Es kommt nie zurück; die
Oberfläche zeigt statt dessen, ob eines hinterlegt ist.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session as DbSession

from .. import audit, directory, identity
from ..db import get_db
from ..deps import current_user, require_permission
from ..models import Group, IdentityConfig, User
from ..schemas import IdentityIn, IdentityOut, IdentityTestIn

router = APIRouter(prefix="/api/admin/identity", tags=["identity"])
manage = require_permission("users.manage", "settings.manage")


def _out(cfg: IdentityConfig | None) -> IdentityOut:
    if cfg is None:
        return IdentityOut()
    data = IdentityOut.model_validate(cfg)
    # Das Kennwort selbst verlaesst den Server nie — nur die Auskunft,
    # ob eines hinterlegt ist.
    data.has_bind_password = bool(cfg.bind_password)
    return data


def _load(db: DbSession) -> IdentityConfig:
    cfg = identity.config(db)
    if cfg is None:
        cfg = IdentityConfig()
        db.add(cfg)
        db.flush()
    return cfg


@router.get("", dependencies=[Depends(manage)])
def read(db: DbSession = Depends(get_db)) -> IdentityOut:
    return _out(identity.config(db))


@router.put("", dependencies=[Depends(manage)])
def write(body: IdentityIn, request: Request,
          actor: User = Depends(manage),
          db: DbSession = Depends(get_db)) -> IdentityOut:
    cfg = _load(db)

    for feld, wert in body.model_dump(exclude={"bind_password", "group_map"}).items():
        if wert is not None:
            setattr(cfg, feld, wert)

    # Leer heisst „nicht geaendert", nicht „loeschen". Sonst raeumte jedes
    # Speichern eines anderen Feldes das Kennwort mit weg — und die naechste
    # Anmeldung scheiterte an etwas, das niemand angefasst hat.
    if body.bind_password:
        cfg.bind_password = body.bind_password

    if body.group_map is not None:
        bekannt = {str(g.id) for g in db.query(Group).all()}
        unbekannt = [v for v in body.group_map.values() if str(v) not in bekannt]
        if unbekannt:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Die Zuordnung zeigt auf Gruppen, die es in OTA nicht gibt.",
            )
        cfg.group_map = {str(k): str(v) for k, v in body.group_map.items()}

    audit.record(db, "identity.updated", actor=actor, object_type="identity",
                 object_id=cfg.server_uri or "—", request=request,
                 enabled=cfg.is_enabled)
    db.commit()
    db.refresh(cfg)
    return _out(cfg)


@router.post("/test", dependencies=[Depends(manage)])
def test(body: IdentityTestIn, db: DbSession = Depends(get_db)) -> dict:
    """Verbindung, Suche und — auf Wunsch — ein einzelner Name.

    Geprüft wird gegen die **gespeicherte** Einstellung. Eine Prüfung gegen
    das, was gerade im Formular steht, wäre bequemer und würde die Frage
    nicht beantworten, um die es geht: ob die Anmeldung nachher funktioniert.
    """
    cfg = identity.config(db)
    if cfg is None or not cfg.server_uri:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Es ist noch keine Verzeichnis-Adresse gespeichert.")
    try:
        ergebnis = directory.check(cfg, body.probe_login or "")
    except directory.DirectoryError as exc:
        cfg.last_error = str(exc)[:500]
        db.commit()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    cfg.last_error = None
    db.commit()
    return ergebnis


@router.post("/sync", dependencies=[Depends(manage)])
def sync(request: Request, actor: User = Depends(manage),
         db: DbSession = Depends(get_db)) -> dict:
    """Abgleich von Hand anstossen."""
    ergebnis = identity.sync_all(db)
    audit.record(db, "identity.synced", actor=actor, object_type="identity",
                 object_id="—", request=request, **ergebnis)
    db.commit()
    return ergebnis
