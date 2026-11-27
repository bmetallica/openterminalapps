"""Datenschutz: die Sicht für den/die Datenschutzbeauftragte(n) (Handbuch Kapitel 42).

Recht `datenschutz.pruefen`, Systemgruppe **datenschutz**. Wer sie hat, sieht
den Menüpunkt **Datenschutz** mit:

* **Lagebild:** welche Verarbeitungen eingeschaltet sind, mit Fristen, und
  Hinweise, wo etwas offen ist.
* **Berechtigungen:** wer welche weitreichenden Rechte hat, über welche Gruppe.
* **Zugriffe:** die Einträge im Prüfprotokoll, bei denen jemand auf Daten
  anderer zugegriffen oder Datenschutz-Einstellungen geändert hat.
* **Prüfprotokoll:** vollständig, mit Filtern, seitenweise, als CSV.
* **Auskunft nach Art. 15** für ein Konto, nur mit Begründung.
* **Datenschutzhinweis**, den die Gruppe auch ändern darf.

Nur lesend, bis auf Auskunft und Datenschutzhinweis. Keine Einstellungen,
keine Konten, kein Aufschalten, kein Terminal. Die Inhalte der Fallberichte
der KI-Sicherheit und die personenbezogene KI-Nutzung gehören bewusst nicht
dazu: Für die Kontrolle reicht es zu sehen, *wer* sie geöffnet hat und warum.

Die Texte für Menschen stehen in der Oberfläche (Datenschutz.tsx); hier
liefert die API nur Werte und Schlüssel.
"""
from __future__ import annotations

import csv
import io
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session as DbSession

from . import erweiterungen, git_geheimnisse, ide_ai, ki_sicherheit, settings_store, syslog
from .config import settings as konfig
from .models import AuditLog, BackupPolicy, Group, User

RECHT = "datenschutz.pruefen"
GRUPPE = {
    "name": "datenschutz", "slug": "datenschutz", "priority": 900, "is_system": True,
    "description": "Datenschutzbeauftragte: Lagebild, Prüfprotokoll, Auskunft nach Art. 15, "
                   "Datenschutzhinweis. Nur lesend, keine Verwaltung.",
    "permissions": [RECHT],
}

# Rechte, die Zugriff auf Daten anderer oder auf die ganze Anlage geben. Die
# übrigen (Images bauen, Registries …) sind für den Datenschutz Nebensache.
WEITREICHEND = ("admin", "arbeitsplatz.terminal", "sessions.view_all", "users.manage",
                "groups.manage", "settings.manage", "audit.view", RECHT,
                "anwendungen.verwalten", "arbeitsplatz.root")

# Vorgänge, die der/die DSB im Blick haben muss, nach Art. Die Namen für
# Menschen stehen in der Oberfläche (Monitor.tsx, VORGAENGE).
ZUGRIFFE: dict[str, tuple[str, ...]] = {
    # Jemand hat auf Daten oder Bildschirm eines anderen zugegriffen.
    "einsicht": ("session.attached", "terminal.geoeffnet", "terminal.protokoll_exportiert",
                 "ki.auskunft", "ki.nutzung_angesehen", "ki.fallbericht_eingesehen",
                 "user.auskunft", "datenschutz.protokoll_exportiert",
                 "datenschutz.protokoll_person"),
    # Konten gesperrt, gelöscht, ihre Daten entfernt.
    "konten": ("user.deaktiviert", "user.deleted", "user.daten_geloescht", "user.daten_entfernt",
               "user.daten_nicht_entfernt", "user.totp_reset", "erweiterung.nutzer_geloescht"),
    # Wer welche Rechte bekommt.
    "rechte": ("group.created", "group.updated", "group.deleted", "verzeichnis.gruppen_gesetzt",
               "verzeichnis.gruppen_entfernt", "notfallkonto.gesetzt", "notfallkonto.entfernt"),
    # Was erfasst und wie lange aufbewahrt wird.
    "einstellungen": ("ki.statistik_an", "ki.statistik_aus", "ide_ai.eingestellt", "ki.nutzung_geloescht",
                      "ki.extern_angelegt", "ki.extern_geloescht", "ki.sicherheit_eingestellt",
                      "ki.sicherheit_geloescht", "ki.fallbericht_geloescht",
                      "git.geheimnisse_eingestellt", "git.geheimnisse_geloescht", "syslog.eingestellt",
                      "settings.konto_daten", "dsgvo.hinweis_geaendert", "erweiterung.eingestellt",
                      "backup.policy_changed", "backup.restored", "protokoll.aufgeraeumt"),
}
ALLE_ZUGRIFFE = tuple(a for liste in ZUGRIFFE.values() for a in liste)

SEITE = 100
EXPORT_MAX = 50_000


def gruppe_sicherstellen(db: DbSession) -> None:
    """Die Systemgruppe beim Start anlegen, ihre Rechte geradeziehen."""
    g = db.scalar(select(Group).where(Group.slug == GRUPPE["slug"]))
    if g is None:
        db.add(Group(**GRUPPE))
    else:
        g.permissions = list(GRUPPE["permissions"])
        g.is_system = True
    db.commit()


# ------------------------------------------------------------------ Lagebild

def lage(db: DbSession) -> dict[str, Any]:
    s = konfig()
    ki = ide_ai.einstellungen(db)
    sicher = ki_sicherheit.einstellungen(db)
    git = git_geheimnisse.einstellungen(db)
    sys = syslog.einstellungen(db)
    konto = settings_store.konto_daten(db)
    hinweis = settings_store.get(db, settings_store.DSGVO) or {}
    gruppen = {str(g.id): g.name for g in db.scalars(select(Group)).all()}
    policy = db.scalar(select(BackupPolicy).limit(1))

    punkte: list[dict[str, Any]] = [
        {"id": "protokoll", "an": True,
         "werte": {"verhalten_tage": s.protokoll_verhalten_tage,
                   "verwaltung_tage": s.protokoll_verwaltung_tage}},
        {"id": "syslog", "an": bool(sys.get("an") and sys.get("host")),
         "werte": {"ziel": sys.get("host") or ""}},
        {"id": "ki_statistik", "an": bool(ki["statistik"] and ki["durchgang"]),
         "werte": {"frist_roh": ki["frist_roh"], "frist_stunden": ki["frist_stunden"]}},
        {"id": "ki_extern", "an": bool(ki.get("extern")),
         "werte": {"dienste": [str(d.get("name") or d.get("kuerzel")) for d in ki.get("extern") or []]}},
        {"id": "ki_sicherheit", "an": bool(sicher["an"]),
         "werte": {"betriebsart": sicher["betriebsart"], "modell": bool(sicher["modell_an"])}},
        {"id": "fallberichte", "an": bool(sicher["an"] and sicher["fallberichte"]),
         "werte": {"frist_tage": sicher["fallbericht_tage"]}},
        {"id": "git_geheimnisse", "an": bool(git["an"]), "werte": {"betriebsart": git["betriebsart"]}},
        {"id": "konto_daten", "an": bool(konto["an"]), "werte": {"tage": konto["tage"]}},
        {"id": "sicherungen", "an": bool(policy and policy.is_enabled),
         "werte": {"taeglich": policy.keep_daily if policy else 0,
                   "woechentlich": policy.keep_weekly if policy else 0}},
        {"id": "hinweis", "an": bool(hinweis.get("text")),
         "werte": {"am": hinweis.get("am"), "von": hinweis.get("von") or ""}},
    ]
    for e in erweiterungen.alle(db):
        punkte.append({"id": "erweiterung", "an": bool(e.an),
                       "werte": {"name": e.name,
                                 "gruppen": sorted(gruppen.get(str(g), "?") for g in e.gruppen or [])}})

    # Hinweise: wo etwas offen ist. Schlüssel; der Text steht in der Oberfläche.
    hinweise: list[str] = []
    if not hinweis.get("text"):
        hinweise.append("hinweis_standard")
    if not (sys.get("an") and sys.get("host")):
        hinweise.append("syslog_aus")
    if not konto["an"]:
        hinweise.append("konto_daten_behalten")
    if sicher["an"] and sicher["fallberichte"]:
        hinweise.append("fallberichte_an")
    if ki["statistik"] and ki["durchgang"]:
        hinweise.append("ki_statistik_an")
    if ki.get("extern"):
        hinweise.append("ki_extern")
    if s.protokoll_verhalten_tage <= 0 or s.protokoll_verwaltung_tage <= 0:
        hinweise.append("protokoll_unbegrenzt")
    return {"punkte": punkte, "hinweise": hinweise}


# -------------------------------------------------------------- Berechtigungen

def rechte(db: DbSession) -> dict[str, Any]:
    gruppen = []
    for g in db.scalars(select(Group).order_by(Group.priority, Group.name)).all():
        weit = [p for p in (g.permissions or []) if p in WEITREICHEND]
        if not weit:
            continue
        gruppen.append({
            "name": g.name, "beschreibung": g.description or "", "system": g.is_system,
            "rechte": weit,
            "mitglieder": sorted(({"name": u.display_name or u.username, "konto": u.username,
                                   "aktiv": bool(u.is_active and not u.is_locked)}
                                  for u in g.members), key=lambda m: m["name"].lower()),
        })
    # Je Recht: wer es hat, egal über welche Gruppe.
    je_recht: dict[str, set[str]] = {r: set() for r in WEITREICHEND}
    for g in gruppen:
        for r in g["rechte"]:
            je_recht[r].update(m["konto"] for m in g["mitglieder"] if m["aktiv"])
    return {"gruppen": gruppen,
            "je_recht": [{"recht": r, "anzahl": len(k)} for r, k in je_recht.items()]}


# ---------------------------------------------------------------- Protokoll

def _filter(stmt, von: datetime | None, bis: datetime | None, aktionen: tuple[str, ...] | None,
            wer: str | None, betroffen: User | None):
    if von:
        stmt = stmt.where(AuditLog.ts >= von)
    if bis:
        stmt = stmt.where(AuditLog.ts < bis)
    if aktionen:
        stmt = stmt.where(AuditLog.action.in_(aktionen))
    if wer:
        stmt = stmt.where(AuditLog.actor_name.ilike(f"%{wer.strip()}%"))
    if betroffen is not None:
        # Betroffen ist, wer gehandelt hat, und wessen Konto der Vorgang galt.
        stmt = stmt.where(or_(AuditLog.actor_user_id == betroffen.id,
                              AuditLog.object_id == str(betroffen.id),
                              (AuditLog.object_type == "user") & (AuditLog.object_id == betroffen.username),
                              AuditLog.detail["name"].astext == betroffen.username,
                              AuditLog.detail["username"].astext == betroffen.username,
                              AuditLog.detail["eigner"].astext == betroffen.username,
                              AuditLog.detail["nutzer"].astext == betroffen.username,
                              AuditLog.detail["nutzer_id"].astext == str(betroffen.id)))
    return stmt


def _zeile(r: AuditLog, namen: dict[str, str]) -> dict[str, Any]:
    return {"ts": r.ts.isoformat(), "wer": r.actor_name, "aktion": r.action,
            "objekt_art": r.object_type, "objekt": r.object_id, "ip": r.ip, "detail": r.detail or {},
            "konto": _konto(r, namen)}


def _uuid_oder_none(roh: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(roh))
    except (ValueError, TypeError):
        return None


def _namen(db: DbSession, zeilen: list[AuditLog]) -> dict[str, str]:
    """Kontonamen zu den Kennungen in diesen Einträgen: Für Menschen ist
    „Konto: anna“ lesbar, eine UUID nicht."""
    ids = set()
    for r in zeilen:
        d = r.detail or {}
        for roh in ((r.object_id if r.object_type == "user" else None), d.get("nutzer_id")):
            u = _uuid_oder_none(roh)
            if u:
                ids.add(u)
    if not ids:
        return {}
    return {str(i): n for i, n in db.execute(select(User.id, User.username).where(User.id.in_(ids))).all()}


def _konto(r: AuditLog, namen: dict[str, str]) -> str | None:
    """Wessen Konto ein Vorgang betraf — soweit es sich sagen lässt."""
    d = r.detail or {}
    for k in ("name", "username", "eigner", "nutzer", "person"):
        if isinstance(d.get(k), str) and d[k]:
            return d[k]
    if d.get("nutzer_id"):
        return namen.get(str(d["nutzer_id"]))
    if r.object_type == "user" and r.object_id:
        return namen.get(r.object_id) or (None if _uuid_oder_none(r.object_id) else r.object_id)
    return None


def protokoll(db: DbSession, *, von=None, bis=None, aktionen=None, wer=None, betroffen=None,
              seite: int = 1) -> dict[str, Any]:
    gesamt = db.scalar(_filter(select(func.count()).select_from(AuditLog), von, bis, aktionen, wer,
                               betroffen)) or 0
    zeilen = db.scalars(_filter(select(AuditLog), von, bis, aktionen, wer, betroffen)
                        .order_by(AuditLog.ts.desc())
                        .offset((max(seite, 1) - 1) * SEITE).limit(SEITE)).all()
    namen = _namen(db, list(zeilen))
    return {"gesamt": gesamt, "seite": max(seite, 1), "je_seite": SEITE,
            "eintraege": [_zeile(r, namen) for r in zeilen]}


def protokoll_csv(db: DbSession, *, von=None, bis=None, aktionen=None, wer=None,
                  betroffen=None) -> tuple[bytes, int]:
    zeilen = db.scalars(_filter(select(AuditLog), von, bis, aktionen, wer, betroffen)
                        .order_by(AuditLog.ts.desc()).limit(EXPORT_MAX)).all()
    puffer = io.StringIO()
    w = csv.writer(puffer, delimiter=";")
    w.writerow(["zeit_utc", "wer", "vorgang", "betroffenes_konto", "objekt_art", "objekt", "ip", "details"])
    namen = _namen(db, list(zeilen))
    for r in zeilen:
        w.writerow([r.ts.isoformat(), r.actor_name or "", r.action, _konto(r, namen) or "",
                    r.object_type or "", r.object_id or "", r.ip or "",
                    json.dumps(r.detail or {}, ensure_ascii=False)])
    # BOM: Excel erkennt sonst die Umlaute nicht.
    return ("﻿" + puffer.getvalue()).encode("utf-8"), len(zeilen)


def personen(db: DbSession, suche: str) -> list[dict[str, Any]]:
    q = f"%{suche.strip()}%"
    treffer = db.scalars(select(User).where(or_(User.username.ilike(q), User.display_name.ilike(q),
                                                User.email.ilike(q)))
                         .order_by(User.username).limit(20)).all()
    return [{"id": str(u.id), "konto": u.username, "name": u.display_name or u.username,
             "email": u.email or "", "aktiv": bool(u.is_active and not u.is_locked)} for u in treffer]


def tag(roh: str | None, ende: bool = False) -> datetime | None:
    """„2026-11-27“ als Beginn des Tages in UTC; mit `ende` der Beginn des Folgetags."""
    if not roh:
        return None
    try:
        d = datetime.fromisoformat(roh[:10]).replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return d + timedelta(days=1) if ende else d
