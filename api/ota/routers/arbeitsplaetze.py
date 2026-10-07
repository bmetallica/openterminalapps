"""Betrieb → Arbeitsplätze: alle Arbeitsplätze, Webterminal, Protokoll.

Die Schaltzentrale für Administratoren (Handbuch Kapitel 25, Uoktober.md §10):

* **Liste** aller Arbeitsplätze, laufend und angehalten, mit Nutzer, Klasse,
  Zustand, zuletzt aktiv und — für Root-Arbeitsplätze — dem belegten Platz.
* **Starten / Anhalten** von Root-Arbeitsplätzen, **Löschen** von allen.
* **Webterminal**: eine root-Shell im Browser, in jedem laufenden Arbeitsplatz.
  Jede Eingabezeile wird protokolliert (`TerminalEintrag`), je Arbeitsplatz,
  und lässt sich als Datei exportieren.

**Wer was darf.** Sehen, Starten, Anhalten, Löschen und das Protokoll
exportieren: `sessions.view_all` (jeder Administrator). Das Terminal selbst
braucht `arbeitsplatz.terminal` — es ist mächtiger als das Aufschalten auf den
Bildschirm, weil es jede Datei im Zuhause eines Nutzers lesen kann.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import re
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import (
    APIRouter, Depends, HTTPException, Request, Response, WebSocket, status,
)
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from .. import agent_client, audit
from ..config import settings
from ..db import SessionLocal, get_db
from ..deps import current_user, require_permission
from ..models import Session as SessionModel, TerminalEintrag, User
from ..security import darf_terminal, read_token
from .sessions import (
    ANGEHALTEN, LIVE, platz_anhalten, platz_fortsetzen,
)

router = APIRouter(prefix="/api/admin/arbeitsplaetze", tags=["arbeitsplaetze"])
log = logging.getLogger("ota.arbeitsplaetze")

sehen = require_permission("sessions.view_all")


def _load(db: DbSession, session_id: uuid.UUID) -> SessionModel:
    sess = db.get(SessionModel, session_id)
    if not sess or sess.status not in LIVE + (ANGEHALTEN,):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Arbeitsplatz nicht gefunden")
    return sess


@router.get("", dependencies=[Depends(sehen)])
def liste(db: DbSession = Depends(get_db)) -> list[dict]:
    """Alle Arbeitsplätze, die es gerade gibt — laufend oder angehalten."""
    rows = db.scalars(select(SessionModel).where(
        SessionModel.status.in_(LIVE + (ANGEHALTEN,))
    ).order_by(SessionModel.last_seen_at.desc())).all()
    return [{
        "id": str(s.id),
        "username": s.user.username,
        "display_name": s.user.display_name or "",
        "template_name": s.template.friendly_name,
        "template_icon": s.template.icon,
        "template_slug": s.template.slug,
        "klasse": s.template.klasse,
        "platz_grenze_gb": s.template.platz_grenze_gb,
        "status": s.status,
        "hat_container": bool(s.container_id),
        "started_at": s.started_at.isoformat(),
        "last_seen_at": s.last_seen_at.isoformat(),
        "ended_at": s.ended_at.isoformat() if s.ended_at else None,
        "end_reason": s.end_reason,
        "cores": s.cores,
        "memory_bytes": s.memory_bytes,
        "app_count": sum(1 for x in s.streams if x.status == "running"),
    } for s in rows]


@router.get("/{session_id}/platz", dependencies=[Depends(sehen)])
def platz(session_id: uuid.UUID, db: DbSession = Depends(get_db)) -> dict:
    """Was ein Root-Arbeitsplatz belegt. Eigener Aufruf, weil die Messung
    dauert — die Liste soll nicht auf sie warten."""
    sess = _load(db, session_id)
    if sess.template.klasse != "root" or not sess.container_id:
        return {"gesamt": None}
    return agent_client.platz(sess.container_id)


@router.post("/{session_id}/starten", dependencies=[Depends(sehen)])
def starten(session_id: uuid.UUID, request: Request,
            actor: User = Depends(current_user),
            db: DbSession = Depends(get_db)) -> dict:
    """Einen angehaltenen Root-Arbeitsplatz starten — ohne dass der Nutzer
    dafür eine Sitzung öffnet. Er läuft, bis der Nutzer sich verbindet oder
    jemand ihn wieder anhält. Die Platzgrenze gilt hier nicht: Wer verwaltet,
    soll einen übervollen Platz starten können, um darin aufzuräumen."""
    sess = _load(db, session_id)
    if sess.template.klasse != "root" or sess.status != ANGEHALTEN:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Nur angehaltene Root-Arbeitsplätze lassen sich hier starten.")
    if not sess.container_id:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Dieser Arbeitsplatz wurde neu aufgesetzt und hat noch keinen Container. "
            "Er entsteht beim nächsten Start durch den Nutzer — erst dann sind "
            "Zuhause, Ablagen und Rechte des Nutzers bekannt.",
        )
    platz_fortsetzen(db, sess, request, actor, platzgrenze=False)
    return {"status": sess.status}


@router.post("/{session_id}/anhalten", dependencies=[Depends(sehen)])
def anhalten(session_id: uuid.UUID, request: Request,
             actor: User = Depends(current_user),
             db: DbSession = Depends(get_db)) -> dict:
    sess = _load(db, session_id)
    if sess.template.klasse != "root" or sess.status not in LIVE:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Nur laufende Root-Arbeitsplätze lassen sich anhalten.")
    platz_anhalten(db, sess, request, actor, "verwaltung")
    return {"status": sess.status}


@router.delete("/{session_id}", dependencies=[Depends(sehen)])
def loeschen(session_id: uuid.UUID, request: Request,
             actor: User = Depends(current_user),
             db: DbSession = Depends(get_db)) -> dict:
    """Arbeitsplatz löschen. Bei Root-Arbeitsplätzen samt Docker-Daten — das
    Zuhause bleibt immer. Das Terminal-Protokoll bleibt ebenfalls."""
    sess = _load(db, session_id)
    ist_root = sess.template.klasse == "root"
    if sess.container_id:
        agent_client.remove_container(sess.container_id, daten=ist_root)
    sess.container_id = None
    sess.status = "stopped"
    sess.ended_at = datetime.now(timezone.utc)
    sess.end_reason = "verwaltung_geloescht"
    for st in sess.streams:
        st.status = "stopped"
    audit.record(db, "platz.geloescht" if ist_root else "session.deleted",
                 actor=actor, object_type="session", object_id=str(sess.id),
                 request=request, nutzer=sess.user.username,
                 template=sess.template.slug)
    db.commit()
    from .firewall import schieben
    schieben(db)
    return {"status": "gelöscht"}


# --------------------------------------------------------------------------
# Terminal-Protokoll
# --------------------------------------------------------------------------

@router.get("/{session_id}/terminal-protokoll", dependencies=[Depends(sehen)])
def protokoll(session_id: uuid.UUID, request: Request, format: str = "txt",
              actor: User = Depends(current_user),
              db: DbSession = Depends(get_db)) -> Response:
    """Das Terminal-Protokoll eines Arbeitsplatzes als Datei.

    Gelesen wird nur. Es gibt keinen Weg, Einträge zu ändern oder zu löschen
    (siehe `TerminalEintrag`).
    """
    rows = db.scalars(select(TerminalEintrag).where(
        TerminalEintrag.session_id == session_id
    ).order_by(TerminalEintrag.id)).all()
    audit.record(db, "terminal.protokoll_exportiert", actor=actor,
                 object_type="session", object_id=str(session_id),
                 request=request, eintraege=len(rows), format=format)
    db.commit()
    stempel = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    if format == "csv":
        puffer = io.StringIO()
        w = csv.writer(puffer, delimiter=";")
        w.writerow(["zeit_utc", "verbindung", "administrator", "nutzer",
                    "vorlage", "art", "text"])
        for r in rows:
            w.writerow([r.ts.isoformat(), r.verbindung, r.admin_name, r.nutzer_name,
                        r.vorlage, r.art, r.text])
        inhalt, typ, endung = puffer.getvalue(), "text/csv; charset=utf-8", "csv"
    else:
        zeilen = [f"# Terminal-Protokoll, Arbeitsplatz {session_id}",
                  f"# exportiert {datetime.now(timezone.utc).isoformat()} von {actor.username}",
                  "# Nur Eingaben, keine Ausgaben. Zeiten in UTC.", ""]
        for r in rows:
            zeit = r.ts.strftime("%Y-%m-%d %H:%M:%S")
            if r.art == "auf":
                zeilen.append(f"{zeit}  [{r.verbindung}] {r.admin_name} öffnet das "
                              f"Terminal ({r.nutzer_name}, {r.vorlage}) {r.text}")
            elif r.art == "zu":
                zeilen.append(f"{zeit}  [{r.verbindung}] {r.admin_name} schliesst das Terminal")
            else:
                zeilen.append(f"{zeit}  [{r.verbindung}] {r.admin_name} $ {r.text}")
        inhalt, typ, endung = "\n".join(zeilen) + "\n", "text/plain; charset=utf-8", "txt"
    return Response(content=inhalt, media_type=typ, headers={
        "Content-Disposition":
            f'attachment; filename="terminal-{str(session_id)[:8]}-{stempel}.{endung}"',
    })


# --------------------------------------------------------------------------
# Webterminal
# --------------------------------------------------------------------------

# Steuerfolgen, die ein Terminal schickt, aber kein Mensch tippt: Pfeiltasten,
# Pos1/Ende, Fokusmeldungen. Im Protokoll sind sie Rauschen.
_ESC = re.compile(r"\x1b(?:\[[0-9;?]*[ -/]*[@-~]|O.|[@-Z\\-_])")


def _zeilen(puffer: list[str], daten: str) -> list[str]:
    """Aus dem, was der Browser schickt, die fertigen Eingabezeilen.

    Annäherung, kein Mitschnitt des Bildschirms: Rücktaste wird angewandt,
    Strg+C und Strg+D stehen als `^C`/`^D` da, Pfeiltasten fallen weg. Was die
    Shell daraus macht (Vervollständigung mit Tab, Verlauf mit Pfeil hoch),
    steht nicht im Protokoll — dafür müsste die Ausgabe mit, und die bleibt
    bewusst draussen.
    """
    fertig: list[str] = []
    for zeichen in _ESC.sub("", daten):
        if zeichen in "\r\n":
            fertig.append("".join(puffer))
            puffer.clear()
        elif zeichen in "\x7f\b":
            if puffer:
                puffer.pop()
        elif zeichen == "\x03":
            fertig.append("".join(puffer) + "^C")
            puffer.clear()
        elif zeichen == "\x04":
            fertig.append("".join(puffer) + "^D")
            puffer.clear()
        elif zeichen == "\t" or zeichen >= " ":
            puffer.append(zeichen)
    return fertig


def _eintrag(session_id: uuid.UUID, verbindung: str, info: dict, art: str,
             text: str = "") -> None:
    with SessionLocal() as db:
        db.add(TerminalEintrag(
            session_id=session_id, verbindung=verbindung,
            admin_name=info["admin"], nutzer_name=info["nutzer"],
            vorlage=info["vorlage"], art=art, text=text[:4000],
        ))
        db.commit()


def _ws_nutzer(ws: WebSocket, db: DbSession) -> User | None:
    """Wer am anderen Ende sitzt — dieselben Prüfungen wie `current_user`."""
    claims = read_token(ws.cookies.get(settings().cookie_name, "") or "")
    if not claims or claims.get("typ") != "access":
        return None
    try:
        user = db.get(User, uuid.UUID(str(claims.get("sub", ""))))
    except ValueError:
        return None
    if not user or not user.is_active or user.is_locked:
        return None
    if claims.get("epoch") != user.token_epoch:
        return None
    return user


@router.websocket("/{session_id}/terminal")
async def terminal(ws: WebSocket, session_id: uuid.UUID) -> None:
    """Root-Shell im Arbeitsplatz. Browser ⇄ API ⇄ Agent ⇄ `docker exec`.

    Die API steht in der Mitte, weil nur sie weiss, **wer** tippt: Hier wird
    jede Eingabezeile mit Namen protokolliert, bevor sie weitergeht.
    """
    absender = (ws.headers.get("x-forwarded-for", "").split(",")[0].strip()
                or (ws.client.host if ws.client else ""))
    with SessionLocal() as db:
        user = _ws_nutzer(ws, db)
        if user is None or not darf_terminal(user):
            await ws.close(code=4403)
            return
        sess = db.get(SessionModel, session_id)
        if not sess or sess.status not in ("running", "starting") or not sess.container_id:
            await ws.close(code=4409)
            return
        info = {"admin": user.username, "nutzer": sess.user.username,
                "vorlage": sess.template.slug, "cid": sess.container_id}
        audit.record(db, "terminal.geoeffnet", actor=user, object_type="session",
                     object_id=str(session_id), nutzer=info["nutzer"],
                     template=info["vorlage"], ip=absender)
        db.commit()

    await ws.accept()
    verbindung = secrets.token_hex(4)
    await asyncio.to_thread(_eintrag, session_id, verbindung, info, "auf",
                            f"von {absender}" if absender else "")
    puffer: list[str] = []
    url, kopf = agent_client.terminal_url(info["cid"])
    try:
        from websockets.asyncio.client import connect

        async with connect(url, additional_headers=kopf, max_size=None) as agent:
            async def zum_browser() -> None:
                async for nachricht in agent:
                    if isinstance(nachricht, bytes):
                        await ws.send_bytes(nachricht)
                    else:
                        await ws.send_text(nachricht)

            ausgabe = asyncio.create_task(zum_browser())
            try:
                while not ausgabe.done():
                    empfang = asyncio.create_task(ws.receive())
                    fertig, _ = await asyncio.wait({empfang, ausgabe},
                                                   return_when=asyncio.FIRST_COMPLETED)
                    if empfang not in fertig:
                        empfang.cancel()
                        break
                    nachricht = empfang.result()
                    if nachricht.get("type") == "websocket.disconnect":
                        break
                    text = nachricht.get("text")
                    if text is None:
                        continue
                    try:
                        obj = json.loads(text)
                    except ValueError:
                        continue
                    if "i" in obj:
                        daten = str(obj["i"])
                        await agent.send(daten.encode("utf-8"))
                        for zeile in _zeilen(puffer, daten):
                            await asyncio.to_thread(_eintrag, session_id, verbindung,
                                                    info, "eingabe", zeile)
                    elif "r" in obj:
                        await agent.send(json.dumps({"r": obj["r"]}))
            finally:
                ausgabe.cancel()
    except Exception as exc:  # noqa: BLE001 — Agent weg, Container weg
        log.warning("Terminal %s beendet: %s", session_id, exc)
        try:
            await ws.send_text(f"\r\n[Verbindung zum Arbeitsplatz verloren: {exc}]\r\n")
        except Exception:  # noqa: BLE001
            pass
    finally:
        if puffer:
            await asyncio.to_thread(_eintrag, session_id, verbindung, info,
                                    "eingabe", "".join(puffer) + "  (ohne Enter)")
        await asyncio.to_thread(_eintrag, session_id, verbindung, info, "zu")
        with SessionLocal() as db:
            audit.record(db, "terminal.geschlossen", actor=None, object_type="session",
                         object_id=str(session_id), admin=info["admin"],
                         nutzer=info["nutzer"])
            db.commit()
        try:
            await ws.close()
        except Exception:  # noqa: BLE001
            pass
