"""Netzprofile — was eine Sitzung im Netz darf.

Drei Stufen und eine Freigabeliste. Durchgesetzt wird nichts hier, sondern im
Netfilter des Wirts (`firewall/`); diese Datei verwaltet nur, **was** gelten
soll, und prueft, dass es sich um etwas Sinnvolles handelt.

**Geprueft wird auf dem Server.** Eine Pruefung, die nur im Formular
stattfindet, ist keine — und aus einer krummen Freigabe wird sonst eine Regel,
die entweder gar nicht greift oder mehr aufmacht als gemeint.
"""

from __future__ import annotations

import ipaddress
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from .. import audit
from ..db import get_db
from ..deps import require_permission
from ..models import NetProfile, Template, User
from ..schemas import NetProfileIn, NetProfileOut

router = APIRouter(prefix="/api/netprofiles", tags=["netprofiles"])

# Die Profile, die jede Anlage mitbringt.
#
# **Warum ueberhaupt welche.** Eine leere Liste ist keine Vorgabe, sondern eine
# Aufgabe: Wer die Anlage aufsetzt, muesste sich erst ueberlegen, welche
# Profile es geben soll — und in der Zwischenzeit laeuft alles auf der
# eingebauten Vorgabe, ohne dass irgendwo steht, welche das ist. Zwei fertige
# Profile machen sichtbar, was gilt, und geben etwas zum Danebenstellen.
#
# **Warum keines mit der Stufe „aus".** Die hebt jede Einschraenkung auf und
# verlangt eine Begruendung. Ein mitgeliefertes waere eine, die niemand
# geschrieben hat — und ein Profil, das man nur noch zuweisen muss, wird
# zugewiesen. Wer es braucht, legt es an; das ist der Punkt.
MITGELIEFERT = [
    {
        "name": "Standard",
        "description": "Internet ja, Firmennetz nein, Nachbarsitzung nein. "
                       "Das ist die Vorgabe — ein Arbeitsplatz ohne Profil "
                       "verhält sich genauso.",
        "stufe": "internet",
        "regeln": [],
    },
    {
        "name": "Abgeschottet",
        "description": "Nur was OTA selbst braucht: Bild, Zwischenablage, "
                       "Namensauflösung. Kein Internet, kein Firmennetz. "
                       "Für Arbeitsplätze, die nur mit lokalen Daten umgehen.",
        "stufe": "abgeschottet",
        "regeln": [],
    },
]


def ensure_builtins(db: DbSession) -> int:
    """Die mitgelieferten Profile anlegen, falls sie fehlen.

    **Nur anlegen, nie überschreiben.** Wer „Standard" umbaut, hat es
    absichtlich getan; ein Start, der das jede Nacht zurückdreht, wäre eine
    Zumutung. Dieselbe Regel wie bei den mitgelieferten Rezepten.
    """
    neu = 0
    for spec in MITGELIEFERT:
        if db.scalar(select(NetProfile).where(NetProfile.name == spec["name"])):
            continue
        db.add(NetProfile(**spec))
        neu += 1
    if neu:
        db.commit()
    return neu

manage = require_permission("settings.manage")

# Dieselben drei Woerter wie im Regelwerk des Routers (`firewall/otafw/nft.py`).
# **"aus" heisst nicht "ohne Firewall"**: Der Weg fuehrt weiter durch den
# Router, er filtert nur nicht mehr. Der Zaehler laeuft weiter.
STUFEN = ("abgeschottet", "internet", "aus")
NAME = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$")
PORTS = re.compile(r"^(\*|(\d{1,5}(-\d{1,5})?)(,\d{1,5}(-\d{1,5})?)*)$")


def _ziel_pruefen(ziel: str) -> None:
    """IP, CIDR oder Name — und sonst nichts."""
    ziel = (ziel or "").strip()
    if not ziel:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ein Ziel fehlt.")
    try:
        ipaddress.ip_network(ziel, strict=False)
        return
    except ValueError:
        pass
    if not NAME.match(ziel):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"„{ziel}“ ist weder eine Adresse noch ein Name. Erwartet wird "
            "etwas wie 192.168.66.10, 10.20.0.0/16 oder git.firma.de.")


def _ports_pruefen(ports: str) -> None:
    ports = (ports or "*").strip()
    if not PORTS.match(ports):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"„{ports}“ ist keine Portangabe. Erwartet wird 443, 80,443, "
            "8080-8090 oder *.")
    for teil in ports.split(","):
        if teil == "*":
            continue
        grenzen = [int(g) for g in teil.split("-")]
        if any(not 1 <= g <= 65535 for g in grenzen):
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                f"Port ausserhalb von 1–65535: {teil}")
        if len(grenzen) == 2 and grenzen[0] > grenzen[1]:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                f"Der Bereich {teil} laeuft rueckwaerts.")


def _pruefen(body: NetProfileIn) -> None:
    if body.stufe not in STUFEN:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"Unbekannte Stufe. Erlaubt: {', '.join(STUFEN)}.")
    if body.stufe == "aus" and not body.begruendung.strip():
        # Dieselbe Behandlung wie andere Ausnahmen in diesem Projekt: Wer sie
        # waehlt, soll sie spaeter begruenden koennen.
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Die Stufe „aus“ hebt jede Einschränkung auf. Bitte kurz "
            "begründen, warum dieser Arbeitsplatz sie braucht.")
    if not body.name.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ein Name fehlt.")
    for regel in body.regeln:
        _ziel_pruefen(regel.ziel)
        _ports_pruefen(regel.ports)
        if regel.protokoll not in ("tcp", "udp", "beide"):
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                f"Unbekanntes Protokoll: {regel.protokoll}")
        if not regel.notiz.strip():
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Die Freigabe für {regel.ziel} braucht eine kurze Notiz — "
                "wofür sie da ist. Ohne die traut sich später niemand, sie "
                "wieder zu entfernen.")


def _aus(profil: NetProfile, benutzt: int = 0) -> NetProfileOut:
    daten = NetProfileOut.model_validate(profil)
    daten.in_benutzung = benutzt
    return daten


def _benutzung(db: DbSession) -> dict[uuid.UUID, int]:
    zeilen = db.execute(
        select(Template.net_profile_id, func.count())
        .where(Template.net_profile_id.is_not(None))
        .group_by(Template.net_profile_id)
    ).all()
    return {kennung: anzahl for kennung, anzahl in zeilen}


@router.get("", dependencies=[Depends(manage)])
def liste(db: DbSession = Depends(get_db)) -> list[NetProfileOut]:
    benutzung = _benutzung(db)
    return [_aus(p, benutzung.get(p.id, 0))
            for p in db.scalars(select(NetProfile).order_by(NetProfile.name)).all()]


@router.post("", dependencies=[Depends(manage)], status_code=status.HTTP_201_CREATED)
def anlegen(body: NetProfileIn, request: Request,
            db: DbSession = Depends(get_db),
            actor: User = Depends(manage)) -> NetProfileOut:
    _pruefen(body)
    if db.scalar(select(NetProfile).where(NetProfile.name == body.name.strip())):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Ein Profil mit diesem Namen gibt es schon.")
    profil = NetProfile(
        name=body.name.strip(),
        description=body.description,
        stufe=body.stufe,
        regeln=[r.model_dump() for r in body.regeln],
        begruendung=body.begruendung,
    )
    db.add(profil)
    audit.record(db, "netprofile.created", actor=actor, object_type="netprofile",
                 object_id=profil.name, request=request,
                 stufe=body.stufe, regeln=len(body.regeln))
    db.commit()
    return _aus(profil)


@router.put("/{profil_id}", dependencies=[Depends(manage)])
def aendern(profil_id: uuid.UUID, body: NetProfileIn, request: Request,
            db: DbSession = Depends(get_db),
            actor: User = Depends(manage)) -> NetProfileOut:
    profil = db.get(NetProfile, profil_id)
    if not profil:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Profil nicht gefunden")
    _pruefen(body)
    vorher = profil.stufe
    profil.name = body.name.strip()
    profil.description = body.description
    profil.stufe = body.stufe
    profil.regeln = [r.model_dump() for r in body.regeln]
    profil.begruendung = body.begruendung

    # Eine Lockerung wird eigens vermerkt. Wer im Protokoll sucht, warum ein
    # Arbeitsplatz ploetzlich ins Firmennetz kam, findet genau diese Zeile.
    aktion = "netprofile.updated"
    if vorher != body.stufe and body.stufe == "aus":
        aktion = "netprofile.opened"
    audit.record(db, aktion, actor=actor, object_type="netprofile",
                 object_id=profil.name, request=request,
                 vorher=vorher, nachher=body.stufe, regeln=len(body.regeln))
    db.commit()
    return _aus(profil, _benutzung(db).get(profil.id, 0))


@router.delete("/{profil_id}", dependencies=[Depends(manage)])
def loeschen(profil_id: uuid.UUID, request: Request,
             db: DbSession = Depends(get_db),
             actor: User = Depends(manage)) -> dict[str, str]:
    profil = db.get(NetProfile, profil_id)
    if not profil:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Profil nicht gefunden")
    benutzt = _benutzung(db).get(profil.id, 0)
    if benutzt:
        # Nicht stillschweigend auf die Vorgabe zurueckfallen lassen: Das
        # waere eine Lockerung, die niemand bemerkt.
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Dieses Profil gilt noch für {benutzt} Arbeitsplatz/Arbeitsplätze. "
            "Erst dort umstellen, dann löschen.")
    name = profil.name
    db.delete(profil)
    audit.record(db, "netprofile.deleted", actor=actor, object_type="netprofile",
                 object_id=name, request=request)
    db.commit()
    return {"status": f"{name} gelöscht"}
