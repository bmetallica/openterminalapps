"""Auskunft nach Art. 15 DSGVO auf Knopfdruck (Handbuch Kapitel 08).

Personen → ⋯ → **Auskunft erstellen** ergibt ein ZIP mit allem, was OTA über
ein Konto gespeichert hat — so, wie es in dsgvo.md Abschnitt 2 aufgezählt
ist. Bis zum 2026-11-25 hieß es dort „von Hand: Datenbankabfrage plus
Zuhause“.

**Was hinein kommt:** Stammdaten, Gruppen und Rechte, die Anmeldemittel aus
Keycloak (Art und Datum, nie das Geheimnis), Protokolleinträge über das Konto
und von ihm, das Terminal-Protokoll von Administratoren in seinen
Arbeitsplätzen, Sitzungen, KI-Nutzung, Softwarefunde, Sicherungen, feste
Netzadressen und Portfreigaben, das Konto in OTA-Git samt Repositories, und
die **Liste** der Dateien in Zuhause und Ablage.

**Was nicht:** der Inhalt der Dateien (den hat die Person selbst, im
Arbeitsplatz), Passwort-Hash, TOTP-Startwert, Zugangsdaten der Sitzungen. Das
Gedächtnis von opencode exportiert jeder selbst. Open WebUI ist eine eigene
Verarbeitung (dsgvo.md Abschnitt 12).

**Vor dem Herausgeben lesen:** Protokolleinträge nennen auch die Namen der
Administratoren, die etwas mit dem Konto getan haben, und das
Terminal-Protokoll enthält, was sie getippt haben. Ob das herausgeht, ist
eine Abwägung nach Art. 15 Abs. 4 — `liesmich.txt` im ZIP sagt das auch.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import uuid
import zipfile
from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import or_, select
from sqlalchemy.orm import Session as DbSession

from . import agent_client, git, keycloak
from .models import (
    AuditLog, Backup, EigenerName, GitKonto, KiAnfrage, KiStunde, NetForward, NetLease,
    NewsGelesen, OnceScriptRun, Session as SessionModel, SoftwareFund, Template,
    TerminalEintrag, User,
)

log = logging.getLogger("ota.auskunft")

# Was nie in eine Auskunft gehört: Geheimnisse, mit denen man sich anmelden
# oder in eine Sitzung schalten könnte.
OHNE = {"password_hash", "totp_secret", "totp_recovery", "token_epoch", "vnc_secret",
        "vnc_user", "failed_from"}


def _wert(v: Any) -> Any:
    if isinstance(v, datetime):
        return v.astimezone(timezone.utc).isoformat()
    if isinstance(v, uuid.UUID):
        return str(v)
    return v


def _zeile(obj: Any, ohne: Iterable[str] = ()) -> dict[str, Any]:
    weg = OHNE | set(ohne)
    return {c.key: _wert(getattr(obj, c.key)) for c in sa_inspect(obj).mapper.column_attrs
            if c.key not in weg}


def _csv(zeilen: list[dict[str, Any]], spalten: list[str] | None = None) -> bytes:
    """CSV mit Semikolon und BOM: So öffnet Excel es ohne Rückfrage richtig."""
    puffer = io.StringIO()
    spalten = spalten or (list(zeilen[0]) if zeilen else ["(leer)"])
    w = csv.DictWriter(puffer, fieldnames=spalten, delimiter=";", extrasaction="ignore")
    w.writeheader()
    for z in zeilen:
        w.writerow({k: (json.dumps(v, ensure_ascii=False, default=str)
                        if isinstance(v, (dict, list)) else _wert(v)) for k, v in z.items()})
    return ("﻿" + puffer.getvalue()).encode("utf-8")


def _json(daten: Any) -> bytes:
    return json.dumps(daten, ensure_ascii=False, indent=2, default=_wert).encode("utf-8")


LIESMICH = """Auskunft nach Art. 15 DSGVO — {anlage}
=====================================================

Konto:        {name} ({kennung})
Erstellt am:  {zeit} (UTC)
Erstellt von: {von}

Diese Sammlung enthält, was OpenTerminalApps (OTA) über dieses Konto
gespeichert hat. Grundlage ist die Übersicht der Verarbeitung (dsgvo.md,
Abschnitt 2).

Dateien
-------
konto.json          Stammdaten, Gruppen, Rechte, eigene Kachelnamen, Gelesen-Stand
                    der News, feste Netzadressen, Portfreigaben, Einmal-Skripte,
                    Anmeldemittel in der zentralen Anmeldung (nur Art und Datum).
protokoll.csv       Einträge im Protokoll, die dieses Konto ausgelöst hat oder
                    die es betreffen. Frist: Anmeldungen und Sitzungen {frist_kurz} Tage,
                    alles andere {frist_lang} Tage.
terminal.csv        Was Administratoren per Webterminal in den Arbeitsplätzen
                    dieses Kontos eingegeben haben (nur Eingaben, keine Ausgaben).
sitzungen.csv       Arbeitsplätze: Vorlage, Beginn, Ende, Grund.
ki_anfragen.csv     KI-Nutzung, je Anfrage (nur Metadaten, nie Inhalte).
ki_stunden.csv      KI-Nutzung, Summen je Stunde.
software.csv        Programme, die in laufenden Arbeitsplätzen gefunden wurden.
sicherungen.csv     Sicherungen von Zuhause und Arbeitsplätzen dieses Kontos.
git.json            Das Konto in OTA-Git und seine Repositories (nur Namen).
dateien.csv         Die LISTE der Dateien in Zuhause und eigener Ablage: Pfad,
                    Größe, Änderungszeit. Den Inhalt hat die Person selbst.

Nicht enthalten
---------------
- Passwort, Passwort-Hash, Startwerte des zweiten Faktors und Zugangsdaten
  der Arbeitsplätze. Sie dienen der Anmeldung und würden sie gefährden.
- Der Inhalt der Dateien im Zuhause und in den Ablagen.
- Das Gedächtnis von opencode (Erweiterung): Es lässt sich dort selbst
  exportieren (JSON, Markdown).
- Open WebUI: eine eigene Verarbeitung mit eigener Datenbank.
- Kopien in Sicherungen: Sie enthalten dieselben Daten wie oben, Stand des
  Sicherungstages; sicherungen.csv listet sie.
{hinweise}
Vor dem Herausgeben (für die Verwaltung)
----------------------------------------
protokoll.csv nennt auch die Administratoren, die etwas mit diesem Konto
getan haben, und terminal.csv enthält, was sie getippt haben. Ob das so
herausgeht, ist eine Abwägung nach Art. 15 Abs. 4 DSGVO (Rechte Dritter).
Im Zweifel mit dem Datenschutz abstimmen.
"""


def erstellen(db: DbSession, user: User, von: User) -> tuple[bytes, dict[str, int]]:
    """Das ZIP und je Datei die Zahl der Einträge (für das Protokoll)."""
    from .config import settings

    kennung = str(user.id)
    hinweise: list[str] = []
    zaehler: dict[str, int] = {}

    # --- Stammdaten
    konto = _zeile(user)
    konto["zweiter_faktor_lokal"] = bool(user.totp_secret)
    konto["gruppen"] = sorted(g.name for g in user.groups)
    konto["rechte"] = sorted(user.permissions)
    vorlagen = {t.id: t.friendly_name or t.slug for t in db.scalars(select(Template)).all()}
    konto["eigene_kachelnamen"] = [
        {"vorlage": vorlagen.get(e.template_id, str(e.template_id)), "name": e.name}
        for e in db.scalars(select(EigenerName).where(EigenerName.user_id == user.id)).all()]
    gelesen = db.get(NewsGelesen, user.id)
    konto["news_gelesen_bis"] = _wert(gelesen.am) if gelesen else None
    konto["feste_netzadressen"] = [
        {"vorlage": vorlagen.get(n.template_id, str(n.template_id)), "netz": f"10.99.{n.idx}.0/24",
         "seit": _wert(n.created_at)}
        for n in db.scalars(select(NetLease).where(NetLease.user_id == user.id)).all()]
    konto["portfreigaben"] = [
        {**_zeile(f, ohne=("user_id",)), "vorlage": vorlagen.get(f.template_id, "")}
        for f in db.scalars(select(NetForward).where(NetForward.user_id == user.id)).all()]
    konto["einmal_skripte"] = [
        _zeile(r, ohne=("user_id",))
        for r in db.scalars(select(OnceScriptRun).where(OnceScriptRun.user_id == user.id)).all()]
    if user.auth_provider == "keycloak" and user.external_id:
        try:
            kc = keycloak.konto_lesen(user.external_id) or {}
            resp = keycloak.ruf("GET", f"/users/{user.external_id}/credentials")
            mittel = resp.json() if resp.status_code == 200 else []
            konto["zentrale_anmeldung"] = {
                "aktiv": kc.get("enabled"),
                "aus_verzeichnis": keycloak.aus_verzeichnis(kc),
                "angelegt": (datetime.fromtimestamp(kc["createdTimestamp"] / 1000, timezone.utc)
                             .isoformat() if kc.get("createdTimestamp") else None),
                "anmeldemittel": [{"art": m.get("type"), "bezeichnung": m.get("userLabel"),
                                   "angelegt": (datetime.fromtimestamp(m["createdDate"] / 1000,
                                                                       timezone.utc).isoformat()
                                                if m.get("createdDate") else None)}
                                  for m in mittel],
            }
        except Exception as exc:  # noqa: BLE001 — Keycloak ist ein Teil, kein Tor
            log.warning("Auskunft %s: Keycloak nicht gelesen: %s", user.username, exc)
            hinweise.append("- Die zentrale Anmeldung (Keycloak) war nicht erreichbar; "
                            "Anmeldemittel fehlen.")

    # --- Protokoll
    protokoll = db.scalars(select(AuditLog).where(or_(
        AuditLog.actor_user_id == user.id,
        AuditLog.object_id.in_([kennung, user.username]),
        AuditLog.actor_name == user.username,
    )).order_by(AuditLog.ts)).all()
    protokoll_zeilen = [{"zeit": a.ts, "aktion": a.action, "von": a.actor_name,
                         "objekt_art": a.object_type, "objekt": a.object_id, "adresse": a.ip,
                         "einzelheiten": a.detail} for a in protokoll]

    terminal = db.scalars(select(TerminalEintrag).where(or_(
        TerminalEintrag.nutzer_name == user.username,
        TerminalEintrag.admin_name == user.username)).order_by(TerminalEintrag.ts)).all()

    # --- Sitzungen, KI, Software, Sicherungen
    sitzungen = db.scalars(select(SessionModel).where(SessionModel.user_id == user.id)
                           .order_by(SessionModel.started_at)).all()
    sitzungs_ids = [s.id for s in sitzungen]
    sitzung_zeilen = [{"vorlage": vorlagen.get(s.template_id, str(s.template_id)),
                       **_zeile(s, ohne=("user_id", "template_id", "container_id"))}
                      for s in sitzungen]
    ki_anfragen = db.scalars(select(KiAnfrage).where(KiAnfrage.user_id == user.id)
                             .order_by(KiAnfrage.ts)).all()
    ki_stunden = db.scalars(select(KiStunde).where(KiStunde.user_id == user.id)
                            .order_by(KiStunde.stunde)).all()
    software = db.scalars(select(SoftwareFund).where(SoftwareFund.session_id.in_(sitzungs_ids))
                          ).all() if sitzungs_ids else []
    sicherungen = db.scalars(select(Backup).where(or_(
        Backup.user_id == user.id, Backup.username == user.username))
        .order_by(Backup.started_at)).all()

    # --- OTA-Git
    git_daten: dict[str, Any] = {"an": git.an(db)}
    eintrag = db.get(GitKonto, user.id)
    if eintrag is not None:
        git_daten.update({"konto": eintrag.forgejo_name, "gesperrt": eintrag.gesperrt})
        if git.an(db):
            try:
                repos = git._pruefen(git._ruf("GET", f"/users/{eintrag.forgejo_name}/repos",
                                              params={"limit": 200}),
                                     "Repositories lesen").json() or []
                git_daten["repositories"] = [
                    {"name": r.get("full_name"), "privat": r.get("private"),
                     "angelegt": r.get("created_at"), "geaendert": r.get("updated_at")}
                    for r in repos]
            except git.GitFehler as exc:
                hinweise.append(f"- OTA-Git war nicht erreichbar ({exc}); Repositories fehlen.")

    # --- Dateien (Agent)
    try:
        liste = agent_client.konto_verzeichnis(kennung)
    except Exception as exc:  # noqa: BLE001
        log.warning("Auskunft %s: Dateiliste nicht gelesen: %s", user.username, exc)
        liste = {"eintraege": [], "gekuerzt": False}
        hinweise.append("- Die Dateiliste ließ sich nicht lesen (Agent nicht erreichbar).")
    if liste.get("gekuerzt"):
        hinweise.append("- Die Dateiliste ist nach 200.000 Einträgen gekürzt.")
    dateien = [{**d, "geaendert": datetime.fromtimestamp(d["geaendert"], timezone.utc)}
               for d in liste.get("eintraege") or []]

    s = settings()
    jetzt = datetime.now(timezone.utc)
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as z:
        def rein(name: str, inhalt: bytes, anzahl: int) -> None:
            z.writestr(name, inhalt)
            zaehler[name] = anzahl

        rein("konto.json", _json(konto), 1)
        rein("protokoll.csv", _csv(protokoll_zeilen, ["zeit", "aktion", "von", "objekt_art",
                                                      "objekt", "adresse", "einzelheiten"]),
             len(protokoll_zeilen))
        rein("terminal.csv", _csv([_zeile(t, ohne=("id",)) for t in terminal],
                                  ["ts", "admin_name", "nutzer_name", "vorlage", "art", "text",
                                   "session_id", "verbindung"]), len(terminal))
        rein("sitzungen.csv", _csv(sitzung_zeilen), len(sitzung_zeilen))
        rein("ki_anfragen.csv", _csv([_zeile(k, ohne=("id", "herkunft")) for k in ki_anfragen]),
             len(ki_anfragen))
        rein("ki_stunden.csv", _csv([_zeile(k) for k in ki_stunden]), len(ki_stunden))
        rein("software.csv", _csv([_zeile(f) for f in software]), len(software))
        rein("sicherungen.csv", _csv([_zeile(b, ohne=("log",)) for b in sicherungen]),
             len(sicherungen))
        rein("git.json", _json(git_daten), len(git_daten.get("repositories") or []))
        rein("dateien.csv", _csv(dateien, ["bereich", "pfad", "groesse", "geaendert", "verweis"]),
             len(dateien))
        z.writestr("liesmich.txt", LIESMICH.format(
            anlage="OpenTerminalApps", name=user.display_name or user.username, kennung=kennung,
            zeit=jetzt.strftime("%Y-%m-%d %H:%M"), von=von.username,
            frist_kurz=s.protokoll_verhalten_tage, frist_lang=s.protokoll_verwaltung_tage,
            hinweise=("\nHinweise zu dieser Auskunft\n---------------------------\n"
                      + "\n".join(hinweise) + "\n") if hinweise else ""))
    return puffer.getvalue(), zaehler
