"""Die KI-Nutzung: Abholen, Verdichten, Aufräumen, Abfragen (Handbuch Kapitel 28).

Der Durchgang (ota-ki) zählt jede Anfrage und legt sie in Spool-Dateien ab.
Von hier aus

* holt die API sie jede Minute über den Agent ab, schreibt sie in
  `ki_anfragen` und zählt sie in `ki_stunden` dazu — in **einem** Zug je
  Datei, und erst danach wird die Datei gelöscht;
* räumt sie einmal am Tag ab, was älter ist als die eingestellten Fristen;
* beantwortet sie die Fragen der Oberfläche: wer wie viel, wann, womit.

Wer zur Absenderadresse gehört, löst sich hier auf: Der Durchgang kennt nur
die Sitzung, die API kennt Mensch und Arbeitsplatz dazu.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session as DbSession

from . import agent_client, ide_ai
from .models import KiAnfrage, KiStunde, Session as SessionModel, Template, User

log = logging.getLogger("ota.ki")

NULL = uuid.UUID(int=0)
# Ein externer Dienst steht in der Statistik wie ein Arbeitsplatz: mit einer
# festen Kennung aus seinem Kürzel, damit seine Stundensummen beisammen bleiben.
EXTERN_NS = uuid.UUID("6f0b3c5e-2d7a-4e7b-9a51-0c1d2e3f4a5b")


def extern_kennung(kuerzel: str) -> uuid.UUID:
    return uuid.uuid5(EXTERN_NS, "ki-extern:" + kuerzel)


def _personen(db: DbSession, zeilen: list[dict[str, Any]]) -> dict[str, tuple[uuid.UUID, str]]:
    """E-Mail, Benutzername oder (eindeutiger) Anzeigename → Mensch, für
    Anfragen externer Dienste. Alles klein."""
    gesucht = {str(z.get(k) or "").strip().lower() for z in zeilen
               for k in ("person_email", "person_name")} - {""}
    if not gesucht:
        return {}
    raus: dict[str, tuple[uuid.UUID, str]] = {}
    anzeige: dict[str, list[tuple[uuid.UUID, str]]] = {}
    for u in db.scalars(select(User).where(
            func.lower(User.email).in_(gesucht) | func.lower(User.username).in_(gesucht)
            | func.lower(User.display_name).in_(gesucht))).all():
        if u.email and u.email.lower() in gesucht:
            raus[u.email.lower()] = (u.id, u.username)
        if u.username.lower() in gesucht:
            raus.setdefault(u.username.lower(), (u.id, u.username))
        if u.display_name and u.display_name.lower() in gesucht:
            anzeige.setdefault(u.display_name.lower(), []).append((u.id, u.username))
    for name, treffer in anzeige.items():
        if len(treffer) == 1:
            raus.setdefault(name, treffer[0])
    return raus


def _uuid(roh: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(roh))
    except (ValueError, TypeError):
        return None


def _zeit(roh: Any) -> datetime | None:
    try:
        z = datetime.fromisoformat(str(roh))
    except ValueError:
        return None
    return z if z.tzinfo else z.replace(tzinfo=timezone.utc)


# ------------------------------------------------------------------ Abholen

def abholen(db: DbSession) -> int:
    """Alle abgeschlossenen Spool-Dateien übernehmen. Gibt die Zahl der neuen
    Zeilen zurück."""
    neu_gesamt = 0
    for _ in range(10):  # höchstens zehn Runden je Aufruf
        antwort = agent_client.ki_spool()
        dateien = antwort.get("dateien") or []
        for datei in dateien:
            neu_gesamt += _datei_uebernehmen(db, datei["name"], datei.get("zeilen") or [])
            agent_client.ki_spool_loeschen(datei["name"])
        if not antwort.get("mehr"):
            break
    return neu_gesamt


def _datei_uebernehmen(db: DbSession, name: str, zeilen: list[dict[str, Any]]) -> int:
    sitzungen = {_uuid(z.get("session_id")) for z in zeilen} - {None}
    wer: dict[uuid.UUID, tuple[uuid.UUID, str, uuid.UUID, str]] = {}
    if sitzungen:
        for s, u, t in db.execute(
                select(SessionModel.id, User, Template)
                .join(User, User.id == SessionModel.user_id)
                .join(Template, Template.id == SessionModel.template_id)
                .where(SessionModel.id.in_(sitzungen))).all():
            wer[s] = (u.id, u.username, t.id, t.friendly_name)
    personen = _personen(db, [z for z in zeilen if z.get("extern")])

    werte = []
    for i, z in enumerate(zeilen):
        ts = _zeit(z.get("zeit"))
        if ts is None:
            continue
        sid = _uuid(z.get("session_id"))
        uid, uname, tid, tname = wer.get(sid, (None, "", None, "")) if sid else (None, "", None, "")
        if z.get("extern"):
            # Ein externer Dienst: der Mensch aus seinen Kopfzeilen, der
            # Dienst an der Stelle des Arbeitsplatzes.
            sid = None
            mensch = (personen.get(str(z.get("person_email") or "").strip().lower())
                      or personen.get(str(z.get("person_name") or "").strip().lower()))
            uid, uname = mensch if mensch else (None, "")
            tid = extern_kennung(str(z["extern"]))
            tname = str(z.get("extern_name") or z["extern"])[:200]
        werte.append({
            "herkunft": f"{name}:{i}"[:120], "ts": ts, "user_id": uid, "user_name": uname,
            "session_id": sid, "template_id": tid, "arbeitsplatz": tname,
            "quelle": (f"extern:{z['extern']}" if z.get("extern") else str(z.get("quelle") or ""))[:64], "server": str(z.get("server") or "")[:32],
            "modell": str(z.get("modell") or (z.get("sni") or ""))[:200],
            "werkzeug": str(z.get("werkzeug") or ("tls" if z.get("weg") == "tls" else ""))[:16],
            "weg": str(z.get("weg") or "")[:12], "pfad": str(z.get("pfad") or "")[:120],
            "status": int(z.get("status") or 0), "dauer_ms": int(z.get("dauer_ms") or 0),
            "erstes_ms": z.get("erstes_ms") if isinstance(z.get("erstes_ms"), int) else None,
            "ein": z.get("ein") if isinstance(z.get("ein"), int) else None,
            "aus": z.get("aus") if isinstance(z.get("aus"), int) else None,
            "bytes": (int(z.get("bytes_hin") or 0) + int(z.get("bytes_her") or 0))
            if z.get("weg") == "tls" else None,
        })
    if not werte:
        return 0

    # Nur, was wirklich neu ist, kommt in die Stundensummen — eine zweimal
    # abgeholte Datei zählt sonst doppelt.
    eingefuegt = db.execute(
        insert(KiAnfrage).values(werte).on_conflict_do_nothing(index_elements=["herkunft"])
        .returning(KiAnfrage.herkunft)).scalars().all()
    neu = set(eingefuegt)

    summen: dict[tuple, dict[str, Any]] = {}
    for w in werte:
        if w["herkunft"] not in neu:
            continue
        stunde = w["ts"].replace(minute=0, second=0, microsecond=0)
        schl = (stunde, w["user_id"] or NULL, w["template_id"] or NULL, w["server"], w["modell"])
        s = summen.setdefault(schl, {"user_name": w["user_name"], "arbeitsplatz": w["arbeitsplatz"],
                                     "anfragen": 0, "fehler": 0, "verbindungen": 0, "ein": 0,
                                     "aus": 0, "dauer_ms": 0, "bytes": 0})
        if w["weg"] == "tls":
            s["verbindungen"] += 1
            s["bytes"] += w["bytes"] or 0
        else:
            s["anfragen"] += 1
            s["fehler"] += 1 if (w["status"] == 0 or w["status"] >= 400) else 0
            s["ein"] += w["ein"] or 0
            s["aus"] += w["aus"] or 0
        s["dauer_ms"] += w["dauer_ms"]
    for (stunde, uid, tid, server, modell), s in summen.items():
        stmt = insert(KiStunde).values(stunde=stunde, user_id=uid, template_id=tid,
                                       server=server, modell=modell, **s)
        stmt = stmt.on_conflict_do_update(
            index_elements=["stunde", "user_id", "template_id", "server", "modell"],
            set_={k: getattr(KiStunde, k) + stmt.excluded[k]
                  for k in ("anfragen", "fehler", "verbindungen", "ein", "aus", "dauer_ms", "bytes")}
            | {"user_name": stmt.excluded.user_name, "arbeitsplatz": stmt.excluded.arbeitsplatz})
        db.execute(stmt)
    db.commit()
    return len(neu)


# ---------------------------------------------------------------- Aufräumen

def aufraeumen(db: DbSession) -> dict[str, int]:
    e = ide_ai.einstellungen(db)
    jetzt = datetime.now(timezone.utc)
    roh = db.execute(delete(KiAnfrage).where(
        KiAnfrage.ts < jetzt - timedelta(days=int(e["frist_roh"])))).rowcount or 0
    stunden = 0
    if int(e["frist_stunden"]) > 0:
        stunden = db.execute(delete(KiStunde).where(
            KiStunde.stunde < jetzt - timedelta(days=int(e["frist_stunden"])))).rowcount or 0
    db.commit()
    return {"anfragen": roh, "stunden": stunden}


def alles_loeschen(db: DbSession) -> dict[str, int]:
    roh = db.execute(delete(KiAnfrage)).rowcount or 0
    stunden = db.execute(delete(KiStunde)).rowcount or 0
    db.commit()
    return {"anfragen": roh, "stunden": stunden}


# ---------------------------------------------------------------- Abfragen

def _raster(von: datetime, bis: datetime, frist_roh: int) -> tuple[str, int]:
    """(Quelle, Schritt in Sekunden): Für kurze Zeiträume die Einzelanfragen
    in fünf Minuten, sonst die Stunden- oder Tagessummen."""
    spanne = (bis - von).total_seconds()
    roh_ab = datetime.now(timezone.utc) - timedelta(days=frist_roh)
    if spanne <= 2 * 86400 and von >= roh_ab:
        return "roh", 300
    if spanne <= 14 * 86400:
        return "stunde", 3600
    return "stunde", 86400


def _verlauf(db: DbSession, von: datetime, bis: datetime, tz: str, frist_roh: int,
             user_id: uuid.UUID | None, je_platz: bool) -> dict[str, Any]:
    quelle, schritt = _raster(von, bis, frist_roh)
    params: dict[str, Any] = {"von": von, "bis": bis, "tz": tz}
    if quelle == "roh":
        eimer = "date_bin(interval '5 minutes', ts, timestamptz '2000-01-01')"
        tabelle, zeit, anfragen = "ki_anfragen", "ts", "count(*) FILTER (WHERE weg <> 'tls')"
        tokens = "coalesce(sum(coalesce(ein,0) + coalesce(aus,0)), 0)"
    else:
        eimer = ("stunde" if schritt == 3600
                 else "(date_trunc('day', stunde AT TIME ZONE :tz) AT TIME ZONE :tz)")
        tabelle, zeit, anfragen = "ki_stunden", "stunde", "sum(anfragen)"
        tokens = "sum(ein + aus)"
    wo = f"{zeit} >= :von AND {zeit} < :bis"
    if user_id is not None:
        wo += " AND coalesce(user_id, '00000000-0000-0000-0000-000000000000'::uuid) = :uid"
        params["uid"] = user_id
    platz = ("coalesce(template_id, '00000000-0000-0000-0000-000000000000'::uuid)"
             if je_platz else "NULL::uuid")
    zeilen = db.execute(text(
        f"SELECT {eimer} AS e, {platz} AS p, {anfragen} AS a, {tokens} AS t "
        f"FROM {tabelle} WHERE {wo} GROUP BY 1, 2 ORDER BY 1"), params).all()
    reihen: dict[str, list[list[Any]]] = {}
    for e, p, a, t in zeilen:
        reihen.setdefault(str(p) if p else "", []).append([e.isoformat(), int(a or 0), int(t or 0)])
    return {"schritt": schritt, "quelle": quelle, "reihen": reihen}


def _zeitraum(von: datetime | None, bis: datetime | None) -> tuple[datetime, datetime]:
    bis = bis or datetime.now(timezone.utc)
    von = von or bis - timedelta(hours=24)
    if von >= bis:
        von = bis - timedelta(hours=1)
    return von, bis


def uebersicht(db: DbSession, von: datetime | None, bis: datetime | None, tz: str) -> dict[str, Any]:
    e = ide_ai.einstellungen(db)
    von, bis = _zeitraum(von, bis)
    # Stundensummen ab der vollen Stunde, in der `von` liegt.
    ab = von.replace(minute=0, second=0, microsecond=0)
    zeilen = db.execute(
        select(KiStunde.user_id, func.max(KiStunde.user_name),
               func.sum(KiStunde.anfragen), func.sum(KiStunde.fehler),
               func.sum(KiStunde.verbindungen), func.sum(KiStunde.ein), func.sum(KiStunde.aus),
               func.sum(KiStunde.dauer_ms), func.count(func.distinct(KiStunde.template_id)),
               func.max(KiStunde.stunde))
        .where(KiStunde.stunde >= ab, KiStunde.stunde < bis)
        .group_by(KiStunde.user_id)).all()
    # Genauer als die Stunde: die letzte Anfrage, solange es sie einzeln gibt.
    zuletzt = dict(db.execute(
        select(KiAnfrage.user_id, func.max(KiAnfrage.ts))
        .where(KiAnfrage.ts >= von, KiAnfrage.ts < bis).group_by(KiAnfrage.user_id)).all())
    modelle: dict[Any, list[str]] = {}
    for uid, modell, n in db.execute(
            select(KiStunde.user_id, KiStunde.modell, func.sum(KiStunde.anfragen))
            .where(KiStunde.stunde >= ab, KiStunde.stunde < bis, KiStunde.anfragen > 0)
            .group_by(KiStunde.user_id, KiStunde.modell)
            .order_by(func.sum(KiStunde.anfragen).desc())).all():
        modelle.setdefault(uid, []).append(modell)
    namen = {u.id: (u.username, u.display_name or "") for u in db.scalars(
        select(User).where(User.id.in_([z[0] for z in zeilen if z[0] != NULL]))).all()}
    nutzer = []
    for uid, uname, a, f, v, ein, aus, dauer, plaetze, letzte in zeilen:
        bekannt = uid != NULL
        nutzer.append({
            "user_id": str(uid) if bekannt else "", "name": namen.get(uid, (uname, ""))[0] or uname,
            "anzeigename": namen.get(uid, ("", ""))[1], "bekannt": bekannt,
            "anfragen": int(a or 0), "fehler": int(f or 0), "verbindungen": int(v or 0),
            "ein": int(ein or 0), "aus": int(aus or 0),
            "dauer_mittel_ms": int((dauer or 0) / a) if a else 0,
            "arbeitsplaetze": int(plaetze or 0), "modell": (modelle.get(uid) or [""])[0],
            "zuletzt": (zuletzt.get(uid if bekannt else None) or letzte).isoformat(),
        })
    nutzer.sort(key=lambda n: -n["anfragen"])
    verlauf = _verlauf(db, von, bis, tz, int(e["frist_roh"]), None, False)
    je_nutzer = _funken(db, ab, bis)
    for n in nutzer:
        n["funken"] = je_nutzer.get(n["user_id"] or str(NULL), [])
    return {"von": von.isoformat(), "bis": bis.isoformat(), "nutzer": nutzer, "verlauf": verlauf,
            "summe": {k: sum(n[k] for n in nutzer)
                      for k in ("anfragen", "fehler", "verbindungen", "ein", "aus")}}


def _funken(db: DbSession, von: datetime, bis: datetime) -> dict[str, list[int]]:
    """Eine kleine Verlaufslinie je Mensch: der Zeitraum in 24 Abschnitten."""
    breite = max(3600.0, (bis - von).total_seconds() / 24)
    zeilen = db.execute(text(
        "SELECT user_id, floor(extract(epoch FROM stunde - :von) / :breite)::int AS i, "
        "sum(anfragen) FROM ki_stunden WHERE stunde >= :von AND stunde < :bis "
        "GROUP BY 1, 2"), {"von": von, "bis": bis, "breite": breite}).all()
    raus: dict[str, list[int]] = {}
    for uid, i, a in zeilen:
        reihe = raus.setdefault(str(uid), [0] * 24)
        if 0 <= i < 24:
            reihe[i] += int(a or 0)
    return raus


def nutzer(db: DbSession, user_id: uuid.UUID | None, von: datetime | None, bis: datetime | None,
           tz: str) -> dict[str, Any]:
    """Ein Mensch: seine Arbeitsplätze, ihr Verlauf, Modelle und Werkzeuge."""
    e = ide_ai.einstellungen(db)
    von, bis = _zeitraum(von, bis)
    ab = von.replace(minute=0, second=0, microsecond=0)
    uid = user_id or NULL
    plaetze = []
    for tid, name, a, f, v, ein, aus, dauer, letzte in db.execute(
            select(KiStunde.template_id, func.max(KiStunde.arbeitsplatz), func.sum(KiStunde.anfragen),
                   func.sum(KiStunde.fehler), func.sum(KiStunde.verbindungen), func.sum(KiStunde.ein),
                   func.sum(KiStunde.aus), func.sum(KiStunde.dauer_ms), func.max(KiStunde.stunde))
            .where(KiStunde.user_id == uid, KiStunde.stunde >= ab, KiStunde.stunde < bis)
            .group_by(KiStunde.template_id)).all():
        plaetze.append({"template_id": str(tid), "name": name or "", "anfragen": int(a or 0),
                        "fehler": int(f or 0), "verbindungen": int(v or 0), "ein": int(ein or 0),
                        "aus": int(aus or 0), "dauer_mittel_ms": int((dauer or 0) / a) if a else 0,
                        "zuletzt": letzte.isoformat()})
    plaetze.sort(key=lambda p: -p["anfragen"])
    modelle = [{"server": s, "modell": m, "anfragen": int(a or 0), "ein": int(ein or 0),
                "aus": int(aus or 0)}
               for s, m, a, ein, aus in db.execute(
                   select(KiStunde.server, KiStunde.modell, func.sum(KiStunde.anfragen),
                          func.sum(KiStunde.ein), func.sum(KiStunde.aus))
                   .where(KiStunde.user_id == uid, KiStunde.stunde >= ab, KiStunde.stunde < bis)
                   .group_by(KiStunde.server, KiStunde.modell)
                   .order_by(func.sum(KiStunde.anfragen).desc())).all()]
    # Werkzeuge gibt es nur einzeln — so weit die Einzelanfragen zurückreichen.
    werkzeuge = [{"werkzeug": w, "anfragen": int(n)} for w, n in db.execute(
        select(KiAnfrage.werkzeug, func.count())
        .where(KiAnfrage.user_id == user_id if user_id else KiAnfrage.user_id.is_(None),
               KiAnfrage.ts >= von, KiAnfrage.ts < bis)
        .group_by(KiAnfrage.werkzeug).order_by(func.count().desc())).all()]
    u = db.get(User, user_id) if user_id else None
    return {"von": von.isoformat(), "bis": bis.isoformat(),
            "nutzer": {"user_id": str(user_id) if user_id else "",
                       "name": u.username if u else "", "anzeigename": (u.display_name or "") if u else ""},
            "arbeitsplaetze": plaetze, "modelle": modelle, "werkzeuge": werkzeuge,
            "verlauf": _verlauf(db, von, bis, tz, int(e["frist_roh"]), uid, True),
            "frist_roh": int(e["frist_roh"])}


# ------------------------------------------------- Die Übersicht ohne Namen

# Unter so vielen Menschen (oder Arbeitsplätzen) im Zeitraum gibt es keine
# Aufteilung: Bei zweien weiss jeder, wer „Person 1“ ist.
MINDESTENS = 3


def _anteile(zeilen: list[tuple[Any, Any, Any]]) -> list[dict[str, int]]:
    """Nur die Grössen, ohne Kennung — die Reihenfolge ist die der Grösse,
    und die Namen vergibt erst die Oberfläche nach dem Rang."""
    raus = [{"anfragen": int(a or 0), "tokens": int(t or 0)} for _, a, t in zeilen]
    return sorted(raus, key=lambda r: (-r["anfragen"], -r["tokens"]))


def anonym(db: DbSession, von: datetime | None, bis: datetime | None, tz: str) -> dict[str, Any]:
    """Was die Seite ohne Auskunft zeigt: Summen, Verlauf und Anteile — kein
    Name, keine Kennung eines Menschen oder seines Arbeitsplatzes."""
    e = ide_ai.einstellungen(db)
    von, bis = _zeitraum(von, bis)
    ab = von.replace(minute=0, second=0, microsecond=0)
    im = (KiStunde.stunde >= ab, KiStunde.stunde < bis)
    tokens = func.sum(KiStunde.ein + KiStunde.aus)
    bekannt = KiStunde.user_id != NULL

    summe = db.execute(select(
        func.coalesce(func.sum(KiStunde.anfragen), 0), func.coalesce(func.sum(KiStunde.fehler), 0),
        func.coalesce(func.sum(KiStunde.verbindungen), 0), func.coalesce(func.sum(KiStunde.ein), 0),
        func.coalesce(func.sum(KiStunde.aus), 0), func.coalesce(func.sum(KiStunde.dauer_ms), 0),
    ).where(*im)).one()

    personen = db.execute(select(KiStunde.user_id, func.sum(KiStunde.anfragen), tokens)
                          .where(*im, bekannt).group_by(KiStunde.user_id)).all()
    plaetze = db.execute(select(KiStunde.user_id, func.sum(KiStunde.anfragen), tokens)
                         .where(*im, bekannt)
                         .group_by(KiStunde.user_id, KiStunde.template_id)).all()
    ohne = db.execute(select(func.coalesce(func.sum(KiStunde.anfragen), 0),
                             func.coalesce(tokens, 0)).where(*im, ~bekannt)).one()

    def benannt(spalte_name, spalte_gruppe) -> list[dict[str, Any]]:
        return sorted(({"name": n or "", "anfragen": int(a or 0), "tokens": int(t or 0)}
                       for n, a, t in db.execute(
                           select(spalte_name, func.sum(KiStunde.anfragen), tokens)
                           .where(*im).group_by(spalte_gruppe)).all()),
                      key=lambda r: (-r["anfragen"], -r["tokens"]))

    # Vorlagen und Modelle sind keine Menschen: Sie stehen mit Namen da.
    vorlagen = sorted(({"name": n or "", "anfragen": int(a or 0), "tokens": int(t or 0)}
                       for _, n, a, t in db.execute(
                           select(KiStunde.template_id, func.max(KiStunde.arbeitsplatz),
                                  func.sum(KiStunde.anfragen), tokens)
                           .where(*im).group_by(KiStunde.template_id)).all()),
                      key=lambda r: (-r["anfragen"], -r["tokens"]))
    modelle = benannt(KiStunde.modell, KiStunde.modell)
    server = benannt(KiStunde.server, KiStunde.server)

    tageszeit = [{"anfragen": 0, "tokens": 0} for _ in range(24)]
    for h, a, t in db.execute(text(
            "SELECT extract(hour FROM stunde AT TIME ZONE :tz)::int, sum(anfragen), sum(ein + aus) "
            "FROM ki_stunden WHERE stunde >= :von AND stunde < :bis GROUP BY 1"),
            {"tz": tz, "von": ab, "bis": bis}).all():
        if 0 <= h < 24:
            tageszeit[h] = {"anfragen": int(a or 0), "tokens": int(t or 0)}

    a = int(summe[0])
    return {
        "von": von.isoformat(), "bis": bis.isoformat(), "mindestens": MINDESTENS,
        "summe": {"anfragen": a, "fehler": int(summe[1]), "verbindungen": int(summe[2]),
                  "ein": int(summe[3]), "aus": int(summe[4]),
                  "dauer_mittel_ms": int(summe[5] / a) if a else 0,
                  "personen": len(personen), "arbeitsplaetze": len(plaetze)},
        "verlauf": _verlauf(db, von, bis, tz, int(e["frist_roh"]), None, False),
        "personen": _anteile(personen) if len(personen) >= MINDESTENS else [],
        "arbeitsplaetze": _anteile(plaetze) if len(plaetze) >= MINDESTENS else [],
        "nicht_zuzuordnen": {"anfragen": int(ohne[0]), "tokens": int(ohne[1])},
        "vorlagen": vorlagen, "modelle": modelle, "server": server, "tageszeit": tageszeit,
    }
