"""Die Firewall aus Sicht der Verwaltung.

Drei Dinge: **globale Freigaben** (was für alle gilt), **Portfreigaben** über
den Wirt (die „+ NAT"-Funktion) und die **Netzübersicht** — welcher Mensch
gerade unter welcher Adresse arbeitet, mit welchem Profil und wie viel dabei
durch die Leitung geht.

Durchgesetzt wird nichts hier. Das tut der Router (`firewall/`); diese Datei
sagt ihm, was gelten soll, und prüft, dass es etwas Sinnvolles ist.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from .. import agent_client, audit, settings_store
from ..config import settings
from ..db import get_db
from ..deps import require_permission
from ..models import NetForward, Session as SessionModel, Template, User
from ..schemas import NetzRegel
from .netprofiles import _ports_pruefen, _ziel_pruefen

router = APIRouter(prefix="/api/firewall", tags=["firewall"])

manage = require_permission("settings.manage")

# Derselbe Bereich, den der Router beim Start veroeffentlicht. Steht in der
# `.env`; groesser machen heisst, den Router neu zu starten — und der ist der
# Weg **aller** Arbeitsplaetze nach draussen.
def _bereich() -> tuple[int, int]:
    import os

    return (int(os.environ.get("OTA_NAT_MIN", "30000")),
            int(os.environ.get("OTA_NAT_MAX", "30019")))


class ForwardIn(BaseModel):
    user_id: uuid.UUID
    template_id: uuid.UUID
    innen: int
    protokoll: str = "tcp"
    notiz: str = ""
    # Wie viele Tage. 0 heisst unbefristet — erlaubt, aber eine Entscheidung.
    tage: int = 30


class ForwardOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    template_id: uuid.UUID
    user: str
    template: str
    aussen: int
    innen: int
    protokoll: str
    notiz: str
    expires_at: datetime | None
    abgelaufen: bool
    # Greift die Freigabe gerade? Sie besteht auch ohne laufenden Arbeitsplatz
    # — dann wartet sie auf den nächsten Start. Genau deshalb muss sie in der
    # Liste bleiben, auch wenn niemand arbeitet.
    aktiv: bool = False


def _aus(f: NetForward, aktiv: bool = False) -> ForwardOut:
    return ForwardOut(
        id=f.id, user_id=f.user_id, template_id=f.template_id,
        user=f.user.username if f.user else "?",
        template=f.template.friendly_name if f.template else "?",
        aussen=f.aussen, innen=f.innen, protokoll=f.protokoll,
        notiz=f.notiz, expires_at=f.expires_at, abgelaufen=f.abgelaufen,
        aktiv=aktiv,
    )


def _laufende(db: DbSession) -> set[tuple[uuid.UUID, uuid.UUID]]:
    return {(s.user_id, s.template_id) for s in db.scalars(
        select(SessionModel).where(
            SessionModel.status.in_(("running", "starting")))).all()}


# --------------------------------------------------------------------------
# Der Grundregelsatz
# --------------------------------------------------------------------------

class Grundregel(BaseModel):
    ziel: str
    ports: str
    protokoll: str
    # Woher der Wert kommt — meist ein Eintrag in der `.env`. Steht dabei,
    # weil die Liste sonst wie etwas aussieht, das man hier ändern könnte.
    herkunft: str
    grund: str


@router.get("/grundregeln", dependencies=[Depends(manage)])
def grundregeln() -> list[Grundregel]:
    """Was **jede** Sitzung erreichen darf, unabhängig vom Profil.

    Abgeleitet und nicht eingetragen: Die Werte kommen aus der Umgebung
    (`deploy/.env`) und aus dem Aufbau selbst. Deshalb ist die Liste hier zu
    sehen, aber nicht zu ändern — geändert wird sie dort, wo sie herkommt.

    Sichtbar sein muss sie trotzdem. Ohne sie steht in der Oberfläche eine
    Firewall, von der niemand weiss, was sie ohnehin durchlässt — und die
    erste Frage bei jedem Problem wäre, ob TURN überhaupt erlaubt ist.
    """
    try:
        return [Grundregel(**r) for r in agent_client.firewall_grundregeln().get("regeln", [])]
    except Exception:  # noqa: BLE001 — lieber leer als eine kaputte Seite
        return []


# --------------------------------------------------------------------------
# Globale Freigaben
# --------------------------------------------------------------------------

@router.get("/global", dependencies=[Depends(manage)])
def global_lesen(db: DbSession = Depends(get_db)) -> list[NetzRegel]:
    return [NetzRegel(**r) for r in settings_store.get(db, settings_store.FIREWALL_GLOBAL) or []]


@router.put("/global", dependencies=[Depends(manage)])
def global_setzen(body: list[NetzRegel], request: Request,
                  db: DbSession = Depends(get_db),
                  actor: User = Depends(manage)) -> list[NetzRegel]:
    for regel in body:
        _ziel_pruefen(regel.ziel)
        _ports_pruefen(regel.ports)
        if not regel.notiz.strip():
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Die Freigabe für {regel.ziel} braucht eine kurze Notiz — "
                "sie gilt für **alle** Arbeitsplätze.")
    settings_store.put(db, settings_store.FIREWALL_GLOBAL,
                       [r.model_dump() for r in body])
    audit.record(db, "firewall.global_updated", actor=actor, object_type="firewall",
                 object_id="global", request=request, regeln=len(body))
    db.commit()
    _schieben(db)
    return body


# --------------------------------------------------------------------------
# Portfreigaben über den Wirt
# --------------------------------------------------------------------------

@router.get("/forwards", dependencies=[Depends(manage)])
def forwards(db: DbSession = Depends(get_db)) -> list[ForwardOut]:
    """**Alle** Freigaben — auch die zu Arbeitsplätzen, die gerade nicht laufen.

    Das ist der Punkt: Eine Freigabe gilt für einen Menschen an einem
    Arbeitsplatz, nicht für eine Sitzung. Sie überlebt den Feierabend und
    greift beim nächsten Start wieder. Eine Liste, die nur laufende Sitzungen
    zeigte, liesse sie verschwinden — und niemand könnte sie mehr entfernen.
    """
    laufend = _laufende(db)
    return [_aus(f, (f.user_id, f.template_id) in laufend)
            for f in db.scalars(select(NetForward).order_by(NetForward.aussen)).all()]


@router.post("/forwards", dependencies=[Depends(manage)],
             status_code=status.HTTP_201_CREATED)
def forward_anlegen(body: ForwardIn, request: Request,
                    db: DbSession = Depends(get_db),
                    actor: User = Depends(manage)) -> ForwardOut:
    if not 1 <= body.innen <= 65535:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Port ausserhalb von 1–65535.")
    if body.protokoll not in ("tcp", "udp"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "tcp oder udp.")
    if not body.notiz.strip():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Wofür ist die Freigabe? Ohne Notiz traut sich später niemand, "
            "sie wieder zu entfernen.")
    if not db.get(User, body.user_id) or not db.get(Template, body.template_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nutzer oder Arbeitsplatz nicht gefunden")

    unten, oben = _bereich()
    belegt = {f.aussen for f in db.scalars(select(NetForward)).all()}
    frei = next((p for p in range(unten, oben + 1) if p not in belegt), None)
    if frei is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Alle Ports zwischen {unten} und {oben} sind vergeben. Erst eine "
            "alte Freigabe entfernen — oder den Bereich in der .env vergrössern "
            "(dazu muss der Router neu starten, und das trennt kurz alle "
            "Arbeitsplätze vom Netz).")

    eintrag = NetForward(
        user_id=body.user_id, template_id=body.template_id,
        aussen=frei, innen=body.innen, protokoll=body.protokoll,
        notiz=body.notiz.strip(), created_by=actor.id,
        expires_at=(datetime.now(timezone.utc) + timedelta(days=body.tage))
        if body.tage > 0 else None,
    )
    db.add(eintrag)
    audit.record(db, "firewall.forward_created", actor=actor, object_type="forward",
                 object_id=str(frei), request=request,
                 innen=body.innen, tage=body.tage, notiz=body.notiz.strip())
    db.commit()
    _schieben(db)
    return _aus(eintrag, (eintrag.user_id, eintrag.template_id) in _laufende(db))


@router.delete("/forwards/{forward_id}", dependencies=[Depends(manage)])
def forward_entfernen(forward_id: uuid.UUID, request: Request,
                      db: DbSession = Depends(get_db),
                      actor: User = Depends(manage)) -> dict[str, str]:
    eintrag = db.get(NetForward, forward_id)
    if not eintrag:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Freigabe nicht gefunden")
    port = eintrag.aussen
    db.delete(eintrag)
    audit.record(db, "firewall.forward_deleted", actor=actor, object_type="forward",
                 object_id=str(port), request=request)
    db.commit()
    _schieben(db)
    return {"status": f"Port {port} freigegeben"}


# --------------------------------------------------------------------------
# Netzübersicht
# --------------------------------------------------------------------------

class UebersichtZeile(BaseModel):
    session_id: uuid.UUID
    # Die Kennungen gehen mit: Die Oberflaeche braucht sie fuer eine
    # Portfreigabe, und ein zweiter Aufruf dafuer waere ein zweiter Aufruf.
    user_id: uuid.UUID
    template_id: uuid.UUID
    user: str
    template: str
    subnetz: str
    adresse: str
    stufe: str
    profil: str
    bytes: int = 0
    verworfen: int = 0
    forwards: list[ForwardOut] = []


@router.get("/uebersicht", dependencies=[Depends(manage)])
def uebersicht(db: DbSession = Depends(get_db)) -> list[UebersichtZeile]:
    """Wer arbeitet gerade unter welcher Adresse — die „IP → Container"-Liste.

    Sie kommt aus den laufenden Sitzungen und nicht aus einer gepflegten
    Datei; damit ist sie immer richtig.
    """
    vom_agent = agent_client.firewall_uebersicht()
    netze = {n["session_id"]: n for n in vom_agent.get("netze", [])}
    zaehler = vom_agent.get("zaehler", {})

    raus = []
    for sess in db.scalars(select(SessionModel).where(
            SessionModel.status.in_(("running", "starting", "paused")))).all():
        netz = netze.get(str(sess.id), {})
        profil = sess.template.net_profile if sess.template else None
        werte = zaehler.get(netz.get("subnetz", ""), {})
        raus.append(UebersichtZeile(
            session_id=sess.id,
            user_id=sess.user_id,
            template_id=sess.template_id,
            user=sess.user.username if sess.user else "?",
            template=sess.template.friendly_name if sess.template else "?",
            subnetz=netz.get("subnetz", ""),
            adresse=netz.get("adresse", ""),
            stufe=profil.stufe if profil else "internet",
            profil=profil.name if profil else "(Vorgabe)",
            bytes=werte.get("bytes", 0),
            verworfen=werte.get("verworfen", 0),
            forwards=[_aus(f, True) for f in db.scalars(select(NetForward).where(
                NetForward.user_id == sess.user_id,
                NetForward.template_id == sess.template_id)).all()],
        ))
    return raus


# --------------------------------------------------------------------------
# Der Weg zum Router
# --------------------------------------------------------------------------

def _schieben(db: DbSession) -> None:
    """Globale Freigaben und Portfreigaben an den Agent geben.

    Abgelaufene bleiben liegen — sie werden hier **nicht** mitgeschickt, und
    damit verschwindet ihre Regel beim nächsten Abgleich. Der Eintrag bleibt
    sichtbar, damit jemand sieht, dass es sie gab.
    """
    jetzt = datetime.now(timezone.utc)
    laufend = {(s.user_id, s.template_id): s.id for s in db.scalars(
        select(SessionModel).where(SessionModel.status.in_(("running", "starting")))).all()}

    weiter = []
    for f in db.scalars(select(NetForward)).all():
        if f.expires_at is not None and f.expires_at <= jetzt:
            continue
        sitzung = laufend.get((f.user_id, f.template_id))
        if not sitzung:
            # Kein laufender Arbeitsplatz — nichts weiterzuleiten. Die
            # Freigabe bleibt bestehen und greift beim nächsten Start.
            continue
        weiter.append({"session_id": str(sitzung), "aussen": f.aussen,
                       "innen": f.innen, "protokoll": f.protokoll})

    try:
        agent_client.firewall_global({
            "freigaben": settings_store.get(db, settings_store.FIREWALL_GLOBAL) or [],
            "weiterleitungen": weiter,
        })
    except Exception:  # noqa: BLE001 — die Firewall darf keine Anfrage kippen
        import logging

        logging.getLogger("ota.firewall").warning(
            "Firewall-Zustand nicht übertragbar — der Router behält den alten "
            "Stand, bis der nächste Abgleich läuft.")


def schieben(db: DbSession) -> None:
    """Von aussen aufrufbar: nach jedem Sessionstart und -ende."""
    _schieben(db)
