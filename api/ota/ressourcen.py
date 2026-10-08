"""CPU und RAM vorhandener Container nachziehen.

Bis zum 2026-10-08 galten geaenderte Ressourcen eines Workspaces erst fuer
Container, die danach **entstanden**. Laufende, pausierte und angehaltene
behielten ihre alten Grenzen — bei einem Root-Arbeitsplatz, der wochenlang
derselbe Container bleibt, hiess das: nie. Docker kann die Grenzen eines
vorhandenen Containers aendern (`docker update`); der Agent tut das, und hier
wird entschieden, wo.

Gerechnet wird je Nutzer mit `effective_resources` — dieselbe Rechnung wie
beim Start, also mit den Abweichungen je Gruppe und Nutzer.
"""
from __future__ import annotations

import logging

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from . import agent_client
from .models import Session as SessionModel
from .models import Template
from .security import effective_resources

log = logging.getLogger("ota.ressourcen")

# Zustaende, in denen es einen Container gibt. "angehalten" ist ein
# Root-Arbeitsplatz, der steht und beim naechsten Start fortgesetzt wird.
MIT_CONTAINER = ("starting", "running", "paused", "angehalten")


def angleichen(sess: SessionModel) -> str:
    """Bringt einen Container auf die geltenden Werte.

    Rueckgabe: `gleich`, `gesetzt`, `spaeter` (weniger RAM, als er gerade
    belegt — gilt ab dem naechsten Fortsetzen) oder `fehler`.
    """
    if not sess.container_id:
        return "gleich"
    cores, memory, _, _ = effective_resources(sess.template, sess.user)
    if sess.cores == cores and sess.memory_bytes == memory:
        return "gleich"
    try:
        antwort = agent_client.ressourcen(sess.container_id, cores, memory)
    except HTTPException as exc:
        log.warning("Ressourcen fuer %s nicht gesetzt: %s", sess.id, exc.detail)
        return "fehler"
    if antwort.get("status") != "gesetzt":
        # Die CPU hat der Agent gesetzt, der RAM wartet. Gespeichert wird nur
        # die CPU; der Unterschied beim RAM bleibt stehen, damit das naechste
        # Fortsetzen ihn nachholt.
        sess.cores = cores
        return "spaeter"
    sess.cores, sess.memory_bytes = cores, memory
    return "gesetzt"


def nachziehen(db: DbSession, tpl: Template) -> str:
    """Alle Container eines Workspaces angleichen. Rueckgabe: ein Satz fuer
    die Verwaltung, leer, wenn es nichts zu tun gab."""
    sitzungen = db.scalars(select(SessionModel).where(
        SessionModel.template_id == tpl.id,
        SessionModel.container_id.is_not(None),
        SessionModel.status.in_(MIT_CONTAINER),
    )).all()
    zaehler = {"gesetzt": 0, "spaeter": 0, "fehler": 0, "gleich": 0}
    for sess in sitzungen:
        zaehler[angleichen(sess)] += 1
    db.commit()

    def anzahl(n: int) -> str:
        return "ein vorhandener Container" if n == 1 else f"{n} vorhandene Container"

    teile = []
    if zaehler["gesetzt"]:
        teile.append(f"{anzahl(zaehler['gesetzt'])} sofort angepasst")
    if zaehler["spaeter"]:
        n = zaehler["spaeter"]
        teile.append(f"{anzahl(n)} {'belegt' if n == 1 else 'belegen'} gerade mehr RAM als "
                     "die neue Grenze: CPU sofort, RAM ab dem nächsten Start")
    if zaehler["fehler"]:
        teile.append(f"{anzahl(zaehler['fehler'])} nicht änderbar (siehe Protokoll der API)")
    return "; ".join(teile)
