"""Softwaremonitoring: welche Anwendung in welchem Arbeitsplatz steckt.

Das Ziel ist, Wildwuchs zu bemerken, nicht ihn zu verhindern. Einmal je
Stunde liest der Agent die Anwendungen jedes laufenden Arbeitsplatzes
(agent/otaagent/software.py). Was nicht auf der Whitelist steht, sehen
Administratoren auf ihrem Dashboard. Nach Rücksprache mit dem Nutzer nimmt
die Verwaltung die Anwendung entweder in die Whitelist auf, oder der Nutzer
deinstalliert sie. Dann fehlt sie bei der nächsten Erfassung, und die Meldung
verschwindet von selbst.

**Die Whitelist kennt keine Versionen und keine Herkunft**, nur Namen: das
Debian-Paket `gimp` und der Starteintrag `gimp.desktop` sind dieselbe
Anwendung. Auch was das Image mitbringt, muss darauf stehen (Betreiber,
2026-10-21). Damit das nicht beim ersten Mal hundert Meldungen ergibt, lässt
sie sich aus dem aktuellen Stand befüllen.

**Gespeichert wird je Sitzung der aktuelle Stand.** Ein angehaltener
Root-Arbeitsplatz wird nicht gelesen und behält seinen letzten Stand; eine
beendete Sitzung verliert ihn, weil es ihren Container nicht mehr gibt.
"""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DbSession

from . import agent_client, settings_store
from .models import Session as SessionModel, SoftwareFreigabe, SoftwareFund

log = logging.getLogger("ota.software")

# Eine Erfassung zur Zeit: Der Knopf und der Takt sollen sich nicht doppeln.
_sperre = threading.Lock()

INTERVALL_SEKUNDEN = 3600


class LaeuftSchon(Exception):
    pass


def freigegeben(db: DbSession) -> set[str]:
    return set(db.scalars(select(SoftwareFreigabe.name)).all())


def erfassen(db: DbSession, anlass: str = "takt") -> dict:
    """Liest alle laufenden Arbeitsplätze und schreibt den Stand. Committet."""
    if not _sperre.acquire(blocking=False):
        raise LaeuftSchon("Es läuft gerade schon eine Erfassung.")
    try:
        return _lauf(db, anlass)
    finally:
        _sperre.release()


def _lauf(db: DbSession, anlass: str) -> dict:
    jetzt = datetime.now(timezone.utc)
    try:
        antwort = agent_client.software()
    except Exception as exc:  # noqa: BLE001 — der Stand bleibt, wie er war
        ergebnis = {"zeit": jetzt.isoformat(), "ok": False, "anlass": anlass,
                    "fehler": str(getattr(exc, "detail", exc))[:200]}
        settings_store.put(db, settings_store.SOFTWARE_LETZTE, ergebnis)
        db.commit()
        return ergebnis

    gelesen = 0
    fehler: list[str] = []
    for eintrag in antwort:
        try:
            sid = uuid.UUID(str(eintrag.get("session_id", "")))
        except ValueError:
            continue
        sess = db.get(SessionModel, sid)
        if sess is None:
            continue
        if "fehler" in eintrag:
            fehler.append(f"{sess.user.username if sess.user else '?'}: {eintrag['fehler']}")
            continue
        gelesen += 1
        neu = {a["name"]: a for a in eintrag.get("anwendungen") or [] if a.get("name")}
        alt = {f.name: f for f in db.scalars(
            select(SoftwareFund).where(SoftwareFund.session_id == sid)).all()}
        for name, fund in alt.items():
            if name not in neu:
                db.delete(fund)  # deinstalliert — die Meldung erledigt sich
        for name, a in neu.items():
            fund = alt.get(name)
            if fund is None:
                db.add(SoftwareFund(session_id=sid, name=name[:200],
                                    quelle=str(a.get("quelle", ""))[:16],
                                    titel=str(a.get("titel", ""))[:200],
                                    erstmals=jetzt, zuletzt=jetzt))
            else:
                fund.zuletzt = jetzt
                fund.quelle = str(a.get("quelle", fund.quelle))[:16]
                if a.get("titel"):
                    fund.titel = str(a["titel"])[:200]

    # Beendete Sitzungen: Ihr Container ist weg, ihr Stand gilt nicht mehr.
    beendet = select(SessionModel.id).where(SessionModel.status == "stopped")
    db.execute(delete(SoftwareFund).where(SoftwareFund.session_id.in_(beendet)))

    ergebnis = {"zeit": jetzt.isoformat(), "ok": True, "anlass": anlass,
                "container": gelesen, "fehler": fehler[:20]}
    settings_store.put(db, settings_store.SOFTWARE_LETZTE, ergebnis)
    db.commit()
    log.info("Software erfasst: %d Arbeitsplätze, %d Fehler", gelesen, len(fehler))
    return ergebnis


def _ort(sess: SessionModel) -> dict:
    return {
        "session_id": str(sess.id),
        "user": sess.user.username if sess.user else "?",
        "vorlage": sess.template.friendly_name if sess.template else "?",
        "klasse": getattr(sess.template, "klasse", "") if sess.template else "",
        "status": sess.status,
    }


def uebersicht(db: DbSession) -> list[dict]:
    """Je Arbeitsplatz die Anwendungen, mit Markierung, was nicht freigegeben ist."""
    frei = freigegeben(db)
    je: dict = {}
    for fund in db.scalars(select(SoftwareFund).order_by(SoftwareFund.name)).all():
        je.setdefault(fund.session_id, []).append(fund)
    aus = []
    for sid, funde in je.items():
        sess = db.get(SessionModel, sid)
        if sess is None or sess.status == "stopped":
            continue  # beendet; die nächste Erfassung räumt die Zeilen
        aus.append({
            **_ort(sess),
            "zuletzt": max(f.zuletzt for f in funde).isoformat(),
            "anwendungen": [{"name": f.name, "titel": f.titel, "quelle": f.quelle,
                             "frei": f.name in frei, "erstmals": f.erstmals.isoformat()}
                            for f in funde],
        })
    aus.sort(key=lambda e: (e["user"], e["vorlage"]))
    return aus


def meldungen(db: DbSession) -> list[dict]:
    """Was nicht auf der Whitelist steht — je Anwendung, mit allen Fundorten."""
    frei = freigegeben(db)
    je: dict[str, dict] = {}
    for fund in db.scalars(select(SoftwareFund)).all():
        if fund.name in frei:
            continue
        sess = db.get(SessionModel, fund.session_id)
        if sess is None or sess.status == "stopped":
            continue
        m = je.setdefault(fund.name, {"name": fund.name, "titel": fund.titel,
                                      "quelle": fund.quelle, "erstmals": fund.erstmals,
                                      "orte": []})
        m["titel"] = m["titel"] or fund.titel
        m["erstmals"] = min(m["erstmals"], fund.erstmals)
        m["orte"].append({**_ort(sess), "erstmals": fund.erstmals.isoformat()})
    aus = sorted(je.values(), key=lambda m: m["erstmals"], reverse=True)
    for m in aus:
        m["erstmals"] = m["erstmals"].isoformat()
    return aus


def freigeben(db: DbSession, namen: list[str], von: str) -> list[str]:
    """Nimmt Namen in die Whitelist auf. Gibt die neu aufgenommenen zurück."""
    schon = freigegeben(db)
    bekannt = {f.name: f for f in db.scalars(select(SoftwareFund)).all()}
    neu = []
    for roh in namen:
        name = str(roh or "").strip().lower()[:200]
        if not name or name in schon:
            continue
        fund = bekannt.get(name)
        db.add(SoftwareFreigabe(name=name, titel=fund.titel if fund else "",
                                quelle=fund.quelle if fund else "", von=von))
        schon.add(name)
        neu.append(name)
    return neu


def erstbefuellen(db: DbSession, von: str) -> list[str]:
    """Alles, was gerade irgendwo installiert ist, in die Whitelist."""
    namen = sorted(set(db.scalars(select(SoftwareFund.name)).all()))
    return freigeben(db, namen, von)
