"""Gruppen aus dem Verzeichnis: wer in welcher OTA-Gruppe ist, und warum.

Eine OTA-Gruppe kann an Gruppen des Verzeichnisses gekoppelt sein
(`group_directory_links`). Ihre Mitglieder sind dann alle, die **von Hand**
aufgenommen wurden, und alle, die das Verzeichnis nennt — beides zugleich,
und jede Mitgliedschaft weiss, woher sie kommt (`GroupMember.von_hand`,
`GroupMember.aus_verzeichnis`). Der Abgleich fasst nur die eine Haelfte an,
die Verwaltung nur die andere (Betreiber, 2026-10-19).

**OTA rechnet die Gruppen selbst aus.** Bis zum 2026-10-19 uebernahm OTA bei
jeder Anmeldung die Gruppen aus dem Token. Das ging, solange OTA der einzige
war, der sie in Keycloak setzte. Mit einem Verzeichnis daneben waere das
Token nicht mehr eindeutig — deshalb gilt jetzt: OTA-Datenbank plus
Verzeichnis ergibt die Gruppen, und OTA traegt das Ergebnis nach Keycloak
(`/ota/<gruppe>`), damit fremde Anwendungen es im Token sehen.

Wann eine Aenderung im Verzeichnis wirkt:

* bei der **naechsten Anmeldung** in OTA — Keycloak liest das Verzeichnis
  dafuer live (`keycloak.verzeichnisgruppen_von`);
* beim **Abgleich**, im eingestellten Takt oder auf Knopfdruck — auch fuer
  alle, die sich gerade nicht anmelden.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import select, text
from sqlalchemy.orm import Session as DbSession

from . import audit, keycloak, settings_store
from .models import Group, GroupDirectoryLink, GroupMember, User

log = logging.getLogger("ota.verzeichnis")

# Ein fester Schluessel fuer pg_try_advisory_lock: Zwei Abgleiche zugleich
# (Takt und Knopf, oder zwei API-Prozesse) schrieben sonst dieselben Zeilen.
_SPERRE = 0x07A_9E2_D1


# --- Mitgliedschaften ------------------------------------------------------

def _zeilen(db: DbSession, user: User) -> dict[uuid.UUID, GroupMember]:
    return {m.group_id: m for m in db.scalars(
        select(GroupMember).where(GroupMember.user_id == user.id)).all()}


def _fertig(db: DbSession, user: User) -> None:
    """Nach dem Schreiben einzelner Zeilen: `user.groups` neu laden."""
    db.flush()
    db.expire(user, ["groups"])


def hand_setzen(db: DbSession, user: User, gruppen: list[Group]) -> None:
    """Die von Hand vergebenen Gruppen eines Kontos. Was das Verzeichnis
    vergibt, bleibt davon unberuehrt."""
    soll = {g.id for g in gruppen}
    zeilen = _zeilen(db, user)
    for gid, z in zeilen.items():
        if gid in soll:
            z.von_hand = True
        elif z.aus_verzeichnis:
            z.von_hand = False
        else:
            db.delete(z)
    for gid in soll - zeilen.keys():
        db.add(GroupMember(group_id=gid, user_id=user.id, von_hand=True,
                           aus_verzeichnis=False))
    _fertig(db, user)


def verzeichnis_setzen(db: DbSession, user: User,
                       soll: set[uuid.UUID]) -> tuple[set[uuid.UUID], set[uuid.UUID]]:
    """Die Gruppen, die das Verzeichnis einem Konto gibt. Rueckgabe: welche
    Gruppen dazukamen und welche wegfielen — gemessen an der Mitgliedschaft
    insgesamt, nicht nur an ihrer Verzeichnis-Haelfte."""
    zeilen = _zeilen(db, user)
    dazu: set[uuid.UUID] = set()
    weg: set[uuid.UUID] = set()
    geschrieben = False
    for gid, z in zeilen.items():
        if gid in soll:
            if not z.aus_verzeichnis:
                z.aus_verzeichnis = geschrieben = True
        elif z.aus_verzeichnis:
            geschrieben = True
            if z.von_hand:
                z.aus_verzeichnis = False
            else:
                db.delete(z)
                weg.add(gid)
    for gid in soll - zeilen.keys():
        db.add(GroupMember(group_id=gid, user_id=user.id, von_hand=False,
                           aus_verzeichnis=True))
        dazu.add(gid)
    if dazu or geschrieben:
        _fertig(db, user)
    return dazu, weg


def herkunft(db: DbSession, user: User) -> dict[str, dict[str, bool]]:
    """Fuer die Oberflaeche: je Gruppe, ob von Hand und/oder aus dem Verzeichnis."""
    return {str(gid): {"von_hand": z.von_hand, "aus_verzeichnis": z.aus_verzeichnis}
            for gid, z in _zeilen(db, user).items()}


def kopplungen(db: DbSession) -> dict[str, set[uuid.UUID]]:
    """Verzeichnisgruppe -> die OTA-Gruppen, die sie fuettert."""
    raus: dict[str, set[uuid.UUID]] = {}
    for link in db.scalars(select(GroupDirectoryLink)).all():
        raus.setdefault(link.ldap_gruppe, set()).add(link.group_id)
    return raus


def kopplung_setzen(db: DbSession, gruppe: Group, ldap_gruppen: list[str]) -> None:
    soll = {n.strip() for n in ldap_gruppen if n.strip()}
    ist = {l.ldap_gruppe: l for l in db.scalars(select(GroupDirectoryLink).where(
        GroupDirectoryLink.group_id == gruppe.id)).all()}
    for name, link in ist.items():
        if name not in soll:
            db.delete(link)
    for name in soll - ist.keys():
        db.add(GroupDirectoryLink(group_id=gruppe.id, ldap_gruppe=name))
    db.flush()


def gekoppelt_an(db: DbSession, gruppe: Group) -> list[str]:
    return sorted(db.scalars(select(GroupDirectoryLink.ldap_gruppe).where(
        GroupDirectoryLink.group_id == gruppe.id)).all())


def nach_keycloak(user: User) -> None:
    """Traegt ein Konto nach Keycloak nach: Profil, OTA-Gruppen, zweite Stufe.

    Ohne das lief die Verwaltung auseinander: Eine E-Mail, hier eingetragen,
    stand nur hier — und eine fremde Anwendung, die sie im Token erwartet,
    bekam sie nie zu sehen. Genau daran scheiterte die erste Anbindung von
    Open WebUI: `OAuth callback failed, email is missing`, obwohl in OTA eine
    Adresse stand. Dasselbe gilt fuer die Gruppen: Open WebUI liest sie aus
    dem Token, und dort stehen sie nur, wenn OTA sie nach Keycloak traegt.

    Betrifft **nur** Konten mit `auth_provider == "keycloak"`. Schlaegt es
    fehl, bleibt die Aenderung in OTA trotzdem: Ein Keycloak, das gerade
    schweigt, darf die Verwaltung nicht anhalten. Der naechste Speichervorgang
    oder Abgleich holt es nach; sichtbar bleibt es im Protokoll.
    """
    if user.auth_provider != "keycloak" or not user.external_id:
        return
    try:
        konto = keycloak.konto_lesen(user.external_id)
        keycloak.konto_profil(user.external_id, anzeigename=user.display_name,
                              email=user.email,
                              aktiv=bool(user.is_active) and not user.is_locked,
                              verzeichnis=keycloak.aus_verzeichnis(konto))
        keycloak.gruppen_setzen(user.external_id, sorted(g.name for g in user.groups))
        keycloak.rolle_setzen(
            user.external_id, "zweiter-faktor",
            any(getattr(g, "require_totp", False) for g in user.groups))
    except (keycloak.KeycloakFehler, httpx.HTTPError) as exc:
        log.warning("Konto %s nicht nach Keycloak nachgetragen: %s", user.username, exc)


# --- Bei der Anmeldung -----------------------------------------------------

def bei_anmeldung(db: DbSession, user: User) -> None:
    """Die Verzeichnis-Haelfte der Gruppen eines Kontos, frisch gelesen.

    Scheitert das Lesen, bleibt der letzte bekannte Stand: Ein Verzeichnis,
    das gerade nicht antwortet, soll niemanden aussperren — und niemandem
    etwas geben, das er nicht hatte.
    """
    links = kopplungen(db)
    if not links or user.auth_provider != "keycloak" or not user.external_id:
        dazu, weg = verzeichnis_setzen(db, user, set())
    else:
        try:
            namen = keycloak.verzeichnisgruppen_von(user.external_id)
        except (keycloak.KeycloakFehler, httpx.HTTPError) as exc:
            log.warning("Verzeichnisgruppen von %s nicht gelesen: %s", user.username, exc)
            return
        soll: set[uuid.UUID] = set()
        for name in namen:
            soll |= links.get(name, set())
        dazu, weg = verzeichnis_setzen(db, user, soll)
    if dazu or weg:
        log.info("Gruppen von %s aus dem Verzeichnis: +%d -%d", user.username,
                 len(dazu), len(weg))
        nach_keycloak(user)


# --- Abgleich --------------------------------------------------------------

def _jetzt() -> datetime:
    return datetime.now(timezone.utc)


def faellig(db: DbSession) -> bool:
    """Ist ein Abgleich im eingestellten Takt dran?"""
    minuten = int(settings_store.get(db, settings_store.VERZEICHNIS_INTERVALL) or 0)
    if minuten <= 0:
        return False
    letzter = settings_store.get(db, settings_store.VERZEICHNIS_LETZTER) or {}
    try:
        zeit = datetime.fromisoformat(letzter["zeit"])
    except (KeyError, TypeError, ValueError):
        return True
    return (_jetzt() - zeit).total_seconds() >= minuten * 60


def abgleichen(db: DbSession, *, actor: User | None = None,
               request: Any = None, anlass: str = "takt") -> dict[str, Any]:
    """Ein ganzer Lauf. Rueckgabe — und gespeichert als letzter Stand:

    `{"zeit", "ok", "anlass", "konten", "geaendert", "gruppen": {name: [+, -]},
      "deaktiviert": [namen], "fehler"}`
    """
    # Die Sperre haengt an **einer** Verbindung. Ueber die Sitzung `db` ginge
    # das schief: Nach jedem Commit gibt sie ihre Verbindung an den Pool
    # zurueck, das Freigeben liefe auf einer anderen — und die Sperre bliebe
    # fuer immer stehen. Genau so am 2026-10-19 gemessen.
    sperre = db.get_bind().connect()
    if not sperre.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _SPERRE}).scalar():
        sperre.close()
        return {"ok": False, "fehler": "Es läuft gerade schon ein Abgleich."}
    ergebnis: dict[str, Any] = {
        "zeit": _jetzt().isoformat(), "ok": True, "anlass": anlass, "konten": 0,
        "geaendert": 0, "gruppen": {}, "deaktiviert": [], "fehler": None,
    }
    try:
        _lauf(db, ergebnis)
        db.commit()
    except (keycloak.KeycloakFehler, httpx.HTTPError) as exc:
        db.rollback()
        ergebnis.update(ok=False, fehler=str(exc) or exc.__class__.__name__)
        log.warning("Verzeichnisabgleich gescheitert: %s", ergebnis["fehler"])
    finally:
        sperre.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _SPERRE})
        sperre.close()
    settings_store.put(db, settings_store.VERZEICHNIS_LETZTER, ergebnis)
    audit.record(db, "verzeichnis.abgleich", actor=actor, request=request,
                 anlass=anlass, ok=ergebnis["ok"], geaendert=ergebnis["geaendert"],
                 gruppen=ergebnis["gruppen"], deaktiviert=ergebnis["deaktiviert"],
                 fehler=ergebnis["fehler"])
    db.commit()
    # Gruppen können sich geändert haben — und damit, wer in OTA-Git darf.
    from . import git
    git.nach_aenderung(db)
    return ergebnis


# Ein Abgleich, der mehr als diesen Anteil der Verzeichniskonten deaktivieren
# wuerde, haelt an. Ein falsch eingestellter Filter oder ein halb
# erreichbares Verzeichnis sieht genau so aus — und haette sonst die halbe
# Belegschaft ausgesperrt.
_HOECHSTENS_DEAKTIVIEREN = 0.5


def _lauf(db: DbSession, ergebnis: dict[str, Any]) -> None:
    if keycloak.verzeichnis_lesen() is None:
        raise keycloak.KeycloakFehler("Es ist kein Verzeichnis angebunden.")
    # 1. Konten und Gruppen aus dem Verzeichnis in Keycloak. Voll, weil nur
    #    der volle Lauf bemerkt, dass ein Konto im Verzeichnis fehlt.
    keycloak.verzeichnis_abgleichen(voll=True)
    keycloak.verzeichnisgruppen_abgleichen()

    # 2. Wer laut Verzeichnis in welcher OTA-Gruppe ist.
    links = kopplungen(db)
    soll: dict[str, set[uuid.UUID]] = {}
    for name, gruppen in links.items():
        for m in keycloak.verzeichnisgruppe_mitglieder(name):
            soll.setdefault(m["sub"], set()).update(gruppen)

    namen = {g.id: g.name for g in db.scalars(select(Group)).all()}
    notfall = settings_store.breakglass(db)
    konten = db.scalars(select(User).where(
        User.auth_provider == "keycloak", User.external_id.is_not(None))).all()
    ergebnis["konten"] = len(konten)

    # 3. Wer im Verzeichnis fehlt. Erst zaehlen, dann entscheiden.
    weg_aus_verzeichnis: list[User] = []
    aus_dem_verzeichnis = 0
    for u in konten:
        if not u.is_active or u.username == notfall:
            continue
        konto = keycloak.konto_lesen(u.external_id)
        if konto is not None and keycloak.aus_verzeichnis(konto):
            aus_dem_verzeichnis += 1
            if not konto.get("enabled", True):
                weg_aus_verzeichnis.append(u)
        elif konto is None and u.groups and any(
                z.aus_verzeichnis for z in _zeilen(db, u).values()):
            # Ein Konto, das Keycloak nicht mehr kennt und das seine Gruppen
            # (auch) aus dem Verzeichnis hatte: im Verzeichnis entfernt.
            aus_dem_verzeichnis += 1
            weg_aus_verzeichnis.append(u)
    if weg_aus_verzeichnis and \
            len(weg_aus_verzeichnis) > _HOECHSTENS_DEAKTIVIEREN * max(aus_dem_verzeichnis, 1):
        raise keycloak.KeycloakFehler(
            f"Der Abgleich würde {len(weg_aus_verzeichnis)} von {aus_dem_verzeichnis} "
            "Verzeichniskonten deaktivieren und hält deshalb an. Stimmen Anbindung und "
            "Filter? Erreichbar ist das Verzeichnis?")

    # 4. Die Gruppen nachziehen, Abwesende deaktivieren — nie loeschen.
    for u in konten:
        dazu, weg = verzeichnis_setzen(db, u, soll.get(u.external_id, set()))
        if u in weg_aus_verzeichnis:
            u.is_active = False
            ergebnis["deaktiviert"].append(u.username)
            audit.record(db, "user.deaktiviert", object_type="user", object_id=u.username,
                         grund="Im Verzeichnis entfernt oder gesperrt (Abgleich)")
        if dazu or weg or u in weg_aus_verzeichnis:
            ergebnis["geaendert"] += 1
            for gid in dazu:
                ergebnis["gruppen"].setdefault(namen.get(gid, str(gid)), [0, 0])[0] += 1
            for gid in weg:
                ergebnis["gruppen"].setdefault(namen.get(gid, str(gid)), [0, 0])[1] += 1
            nach_keycloak(u)


def vorschau(db: DbSession, gruppe: Group, ldap_gruppen: list[str]) -> dict[str, Any]:
    """Was eine Kopplung aendern wuerde, bevor sie gespeichert ist.

    Kommen kann nur dazu, nie weg — von Hand Aufgenommene bleiben. Weg faellt
    nur, wer bisher **allein** ueber eine Kopplung drin war, die jetzt fehlt.
    """
    mitglieder: dict[str, str] = {}
    for name in ldap_gruppen:
        for m in keycloak.verzeichnisgruppe_mitglieder(name):
            mitglieder[m["sub"]] = m["username"]
    zeilen = {z.user_id: z for z in db.scalars(select(GroupMember).where(
        GroupMember.group_id == gruppe.id)).all()}
    in_ota = {u.external_id: u for u in db.scalars(select(User).where(
        User.auth_provider == "keycloak", User.external_id.in_(list(mitglieder)))).all()}
    dazu = sorted(mitglieder[s] for s, u in in_ota.items() if u.id not in zeilen)
    spaeter = sorted(n for s, n in mitglieder.items() if s not in in_ota)
    weg = sorted(u.username for u in db.scalars(select(User).where(User.id.in_(
        [uid for uid, z in zeilen.items() if z.aus_verzeichnis and not z.von_hand]))).all()
        if u.external_id not in mitglieder)
    return {"im_verzeichnis": len(mitglieder), "dazu": dazu, "weg": weg,
            "noch_nie_angemeldet": spaeter}
