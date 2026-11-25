"""OTA-Git: Geheimnisse beim Push erkennen (Handbuch Kapitel 27).

Ein Pre-Receive-Hook in Forgejo prüft die neuen Commits eines Pushes auf
private Schlüssel, Tokens, Passwörter im Code und Dateien wie `.env`
(agent/otaagent/git_geheimnisse.sh). Der Agent hängt ihn in jedes
Repository ein und holt die Zähler ab (git_dienst.geheimnisse); hier stehen
die Einstellungen, die Übernahme in die Datenbank und die Auswertung.

**Datensparsam wie die KI-Sicherheit:** In die Datenbank kommen nur Zahlen je
Stunde: wie viele Pushes, was mit ihnen geschah, wie viele Treffer je Art.
Kein Geheimnis, kein Dateiname, kein Repository, keine Person. Den Fundort
sieht nur, wer pusht — in der Ausgabe von git.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session as DbSession

from . import agent_client, settings_store
from .models import GitGeheimnis

log = logging.getLogger("ota.git_geheimnisse")

FRIST_TAGE = 365
BETRIEBSARTEN = ("beobachten", "warnen", "sperren")
PUSH_AKTIONEN = ("geprueft", "gezaehlt", "gewarnt", "gesperrt", "uebergangen", "gekuerzt")
FALL_AKTIONEN = ("gezaehlt", "gewarnt", "gesperrt", "uebergangen")
TYPEN = ("privater-schluessel", "cloud-schluessel", "git-token", "ki-schluessel", "chat-token",
         "jwt", "passwort-im-code", "zugang-in-adresse", "env-datei", "schluesseldatei")


def einstellungen(db: DbSession) -> dict[str, Any]:
    roh = settings_store.get(db, settings_store.GIT_GEHEIMNISSE)
    roh = roh if isinstance(roh, dict) else {}
    art = roh.get("betriebsart")
    return {"an": bool(roh.get("an")),
            "betriebsart": art if art in BETRIEBSARTEN else "warnen",
            "uebergehen": bool(roh.get("uebergehen", True))}


def speichern(db: DbSession, eingabe: dict[str, Any]) -> dict[str, Any]:
    e = einstellungen(db)
    if "an" in eingabe:
        e["an"] = bool(eingabe["an"])
    if "uebergehen" in eingabe:
        e["uebergehen"] = bool(eingabe["uebergehen"])
    if "betriebsart" in eingabe:
        if eingabe["betriebsart"] not in BETRIEBSARTEN:
            raise ValueError("Betriebsart: beobachten, warnen oder sperren.")
        e["betriebsart"] = eingabe["betriebsart"]
    settings_store.put(db, settings_store.GIT_GEHEIMNISSE, e)
    return e


def _stunde(zeit: Any) -> datetime:
    try:
        t = datetime.fromtimestamp(int(zeit), timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        t = datetime.now(timezone.utc)
    return t.replace(minute=0, second=0, microsecond=0)


def _zaehlen(db: DbSession, stunde: datetime, art: str, typ: str, n: int) -> None:
    stmt = insert(GitGeheimnis).values(stunde=stunde, art=art, typ=typ, anzahl=n)
    db.execute(stmt.on_conflict_do_update(
        index_elements=["stunde", "art", "typ"],
        set_={"anzahl": GitGeheimnis.anzahl + stmt.excluded.anzahl}))


def uebernehmen(db: DbSession, zeilen: list[dict[str, Any]]) -> int:
    """Zeilen aus dem Spool in die Stundensummen. Committet nicht.

    Nur bekannte Namen: Was das Skript schreibt, kommt aus einem Container,
    in dem jeder Push Code ausführen lässt — es wird nicht geglaubt.
    """
    n = 0
    for z in zeilen:
        if not isinstance(z, dict):
            continue
        stunde = _stunde(z.get("zeit"))
        aktion = z.get("aktion")
        if aktion not in PUSH_AKTIONEN or aktion == "gekuerzt":
            continue
        _zaehlen(db, stunde, "push", "geprueft", 1)
        if aktion != "geprueft":
            _zaehlen(db, stunde, "push", aktion, 1)
        if z.get("gekuerzt"):
            _zaehlen(db, stunde, "push", "gekuerzt", 1)
        typen = z.get("typen") if isinstance(z.get("typen"), dict) else {}
        for typ, anzahl in typen.items():
            if typ in TYPEN and isinstance(anzahl, int) and 0 < anzahl < 100_000:
                _zaehlen(db, stunde, "treffer", typ, anzahl)
        n += 1
    return n


def abgleichen(db: DbSession) -> dict[str, Any]:
    """Jede Minute (main._scheduler): Hook und Einstellung in Forgejo
    nachziehen, Zähler abholen. Committet."""
    e = einstellungen(db)
    erg = agent_client.git_geheimnisse(e["an"], e["betriebsart"], e["uebergehen"])
    neu = uebernehmen(db, erg.get("zeilen") or [])
    db.commit()
    return {"pushes": neu, "verweise": erg.get("verweise", 0), "repos": erg.get("repos", 0),
            "laeuft": bool(erg.get("laeuft"))}


def aufraeumen(db: DbSession) -> int:
    grenze = datetime.now(timezone.utc) - timedelta(days=FRIST_TAGE)
    weg = db.execute(delete(GitGeheimnis).where(GitGeheimnis.stunde < grenze)).rowcount or 0
    db.commit()
    return weg


def alles_loeschen(db: DbSession) -> int:
    weg = db.execute(delete(GitGeheimnis)).rowcount or 0
    db.commit()
    return weg


def uebersicht(db: DbSession, tage: int) -> dict[str, Any]:
    tage = min(max(int(tage), 1), FRIST_TAGE)
    ab = datetime.now(timezone.utc) - timedelta(days=tage)
    zeilen = db.execute(select(GitGeheimnis.stunde, GitGeheimnis.art, GitGeheimnis.typ,
                               GitGeheimnis.anzahl).where(GitGeheimnis.stunde >= ab)).all()
    pushes: dict[str, int] = {}
    treffer: dict[str, int] = {}
    nach_tag: dict[str, dict[str, int]] = {}
    for stunde, art, typ, n in zeilen:
        tag = stunde.astimezone(timezone.utc).date().isoformat()
        t = nach_tag.setdefault(tag, {"geprueft": 0, "faelle": 0, "gesperrt": 0})
        if art == "push":
            pushes[typ] = pushes.get(typ, 0) + n
            if typ == "geprueft":
                t["geprueft"] += n
            elif typ in FALL_AKTIONEN:
                t["faelle"] += n
                if typ == "gesperrt":
                    t["gesperrt"] += n
        elif art == "treffer":
            treffer[typ] = treffer.get(typ, 0) + n
    erster = db.execute(select(func.min(GitGeheimnis.stunde))).scalar()
    return {
        "tage": tage,
        "seit": erster.isoformat() if erster else None,
        "geprueft": pushes.get("geprueft", 0),
        "faelle": sum(pushes.get(a, 0) for a in FALL_AKTIONEN),
        "nach_aktion": {a: pushes.get(a, 0) for a in FALL_AKTIONEN},
        "gekuerzt": pushes.get("gekuerzt", 0),
        "treffer": sorted(({"typ": k, "anzahl": v} for k, v in treffer.items()),
                          key=lambda x: -x["anzahl"]),
        "summe_treffer": sum(treffer.values()),
        "verlauf": [{"tag": k, **v} for k, v in sorted(nach_tag.items())],
    }
