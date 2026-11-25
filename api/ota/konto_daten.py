"""Was mit den Daten eines gelöschten Kontos geschieht.

Die Verwaltung wählt unter Einstellungen → Löschen von Konten:

* **behalten** (Vorgabe): Zuhause, Ablage und Sicherungen bleiben, wie bisher.
  Löschen ist dann Handarbeit nach dem Löschkonzept (dsgvo.md, 4.2).
* **löschen nach N Tagen**: Zuhause und Ablage wandern beim Löschen in den
  Papierkorb des Agents (agent/otaagent/konto_daten.py). Der tägliche Lauf
  löscht sie nach der Frist endgültig, und mit ihnen die Sicherungen des
  Kontos. 0 Tage heißt: sofort.

**Warum die Sicherungen mitgehen:** Die Aufbewahrung (`apply_retention`)
behält die letzten `keep_daily` Sicherungen je Name. Für ein gelöschtes Konto
entstehen keine neuen mehr, also verdrängt auch nichts die alten. Ohne diesen
Schritt lebte das Zuhause in seinen Sicherungen unbegrenzt weiter.

Nicht hier: das Konto in Keycloak (wird gesperrt, nie gelöscht), in OTA-Git
(gesperrt) und in Open WebUI (eigene Anwendung, die OTA nicht anfasst).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from . import agent_client, audit, settings_store
from .models import Backup

log = logging.getLogger("ota.konto_daten")


def sicherungen_entfernen(db: DbSession, name: str) -> int:
    """Die Sicherungen eines **gelöschten** Kontos: Zuhause und Container.

    Nur Zeilen ohne Konto (`user_id` ist beim Löschen auf NULL gefallen). Ein
    neues Konto mit demselben Namen behält seine. Eine Datei, die sich nicht
    löschen lässt, behält ihre Zeile; der nächste Lauf versucht es wieder.
    """
    if not name:
        return 0
    weg = 0
    for b in db.scalars(select(Backup).where(
            Backup.user_id.is_(None), Backup.username == name,
            Backup.kind != "database")).all():
        if b.path:
            try:
                agent_client.delete_backup_file(b.path)
            except HTTPException as exc:
                if exc.status_code != 404:
                    log.warning("Sicherung %s nicht gelöscht: %s", b.path, exc.detail)
                    continue
        db.delete(b)
        weg += 1
    return weg


def nach_dem_loeschen(db: DbSession, kennung: str, name: str, actor) -> str:
    """Nach dem Löschen des Kontos aufrufen, nach dem Commit. Gibt den Satz
    für die Rückmeldung an die Verwaltung zurück.

    Nach dem Commit, nicht davor: Geht hier etwas schief, ist das Konto
    trotzdem weg, und die Daten liegen wie bisher auf der Platte. Davor
    stünde ein Konto, dessen Zuhause schon im Papierkorb liegt.
    """
    regel = settings_store.konto_daten(db)
    if not regel["an"]:
        return " Zuhause und Ablage auf der Platte bleiben bestehen."
    sofort = regel["tage"] == 0
    try:
        ergebnis = agent_client.konto_daten_entfernen(kennung, name, sofort)
    except HTTPException as exc:
        log.warning("Daten von %s nicht entfernt: %s", name, exc.detail)
        audit.record(db, "user.daten_nicht_entfernt", actor=actor, object_type="user",
                     object_id=name, kennung=kennung, grund=str(exc.detail)[:300])
        db.commit()
        return (" Achtung: Zuhause und Ablage ließen sich nicht entfernen "
                f"({exc.detail}). Sie liegen weiter auf der Platte.")
    sicherungen = sicherungen_entfernen(db, name) if sofort else 0
    audit.record(db, "user.daten_entfernt", actor=actor, object_type="user",
                 object_id=name, kennung=kennung, frist_tage=regel["tage"],
                 bereiche=ergebnis.get("bereiche", []), sicherungen=sicherungen)
    db.commit()
    if sofort:
        return " Zuhause, Ablage und Sicherungen werden jetzt gelöscht."
    am = (datetime.now() + timedelta(days=regel["tage"])).strftime("%d.%m.%Y")
    return (" Zuhause und Ablage liegen im Papierkorb und werden samt Sicherungen "
            f"am {am} endgültig gelöscht.")


def papierkorb_leeren(db: DbSession) -> dict:
    """Der tägliche Lauf. Die Frist gilt, wie sie heute eingestellt ist, auch
    für Konten, die gelöscht wurden, als die Regel noch anders lautete; und
    auch dann, wenn sie inzwischen auf „behalten“ steht: Was einmal im
    Papierkorb liegt, ist zum Löschen bestimmt."""
    tage = settings_store.konto_daten(db)["tage"]
    ergebnis = agent_client.konten_papierkorb_leeren(tage)
    for e in ergebnis.get("entfernt", []):
        n = sicherungen_entfernen(db, e.get("name") or "")
        audit.record(db, "user.daten_geloescht", object_type="user",
                     object_id=e.get("name") or e["kennung"], kennung=e["kennung"],
                     sicherungen=n)
    db.commit()
    return ergebnis
