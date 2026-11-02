"""OTA-Erweiterungen (Handbuch Kapitel 39).

Eine Erweiterung ist eine **eigenständige Docker-Anwendung** mit eigenem
Compose-Projekt, die dem Netz `ota_erweiterungen` beitritt. OTA koppelt sie,
schaltet sie für Gruppen ein und gibt jedem berechtigten Arbeitsplatz, was
sie liefert: ein Token, einen MCP-Server für opencode, einen Schnipsel für
den Systemprompt. Ihr Netz, ihre Daten und ihr Lebenszyklus bleiben bei ihr.

Der Vertrag (Schnittstelle 1) — OTA ruft die Erweiterung, nie umgekehrt:

    GET  /ota/v1/manifest              ohne Anmeldung
    POST /ota/v1/koppeln               {kopplungsschluessel, dienstgeheimnis}
    GET  /ota/v1/gesund                alle Aufrufe ab hier: Bearer <Dienstgeheimnis>
    GET|PUT /ota/v1/konfiguration
    POST /ota/v1/testen
    POST /ota/v1/arbeitsplatz          → {token, mcp_pfad, opencode_plugin, opencode_fragen, prompt}
    DELETE /ota/v1/arbeitsplatz/{id}
    GET  /ota/v1/arbeitsplaetze
    POST /ota/v1/nutzer/{id}/sperren | entsperren | loeschen
    GET  /ota/v1/statistik
    GET  /ota/v1/sicherung

Wege, die OTA öffnet (der Agent schreibt die Routen für Traefik):

* Aus den Arbeitsplätzen nur die Pfade aus `pfade_fuer_arbeitsplaetze`,
  unter `http://ota-erweiterungen:8091/<slug>/…`. Der Name zeigt in jedem
  Arbeitsplatz auf Traefik im eigenen Sitzungsnetz — kein Hostport, keine
  Firewallregel. Unverschlüsselt, weil das Netz nur diesen einen
  Arbeitsplatz, seinen Router und Traefik enthält; das Token ist an den
  Arbeitsplatz gebunden und endet mit ihm.
* Aus dem Browser nur `/x/<slug>/ansicht/…`, hinter forwardAuth: OTA prüft
  die Anmeldung und setzt signierte Kopfzeilen (`pruefen`).

**Ein Arbeitsplatz scheitert nie an einer Erweiterung.** Antwortet sie beim
Start nicht innerhalb weniger Sekunden, geht es ohne sie weiter.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
import time
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote, urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from .models import Erweiterung, ErweiterungAuftrag, ErweiterungToken, Session as SessionModel, User

log = logging.getLogger("ota.erweiterungen")

SCHNITTSTELLE = 1
HOST = "ota-erweiterungen"
PORT = 8091
SLUG_OK = re.compile(r"[a-z][a-z0-9]{1,30}")
PFAD_OK = re.compile(r"/[A-Za-z0-9._~/-]{0,200}")
LIVE = ("starting", "running", "paused")
# Plugins, die das Paket ota-opencode mitbringt. Fremden Plugin-Code nimmt
# OTA nicht an: Ein Plugin läuft im opencode-Prozess mit allen Rechten des
# Menschen.
PLUGINS = ("ota-sitzung",)
PROMPT_LAENGE = 4000


class ErweiterungFehler(Exception):
    """Die Meldung geht an den Menschen."""


def _jetzt() -> datetime:
    return datetime.now(timezone.utc)


def _ruf(adresse: str, methode: str, pfad: str, geheimnis: str | None = None,
         zeitlimit: float = 10.0, **kw: Any) -> httpx.Response:
    kopf = kw.pop("headers", {})
    if geheimnis:
        kopf["Authorization"] = f"Bearer {geheimnis}"
    try:
        # Ohne Proxy: Die Erweiterung ist ein Container nebenan.
        with httpx.Client(timeout=zeitlimit, trust_env=False) as c:
            return c.request(methode, adresse.rstrip("/") + pfad, headers=kopf, **kw)
    except httpx.HTTPError as exc:
        raise ErweiterungFehler(f"Die Erweiterung unter {adresse} antwortet nicht: {exc}") from exc


def _antwort(r: httpx.Response, was: str) -> Any:
    if r.status_code >= 400:
        try:
            text = r.json().get("detail") or r.text
        except ValueError:
            text = r.text
        raise ErweiterungFehler(f"{was}: {r.status_code} {str(text)[:300]}")
    try:
        return r.json()
    except ValueError as exc:
        raise ErweiterungFehler(f"{was}: Antwort ist kein JSON") from exc


def aufruf(e: Erweiterung, methode: str, pfad: str, was: str, zeitlimit: float = 10.0, **kw) -> Any:
    return _antwort(_ruf(e.adresse, methode, pfad, e.geheimnis, zeitlimit, **kw), was)


# --------------------------------------------------------------------------
# Koppeln und verwalten
# --------------------------------------------------------------------------

def adresse_pruefen(roh: str) -> str:
    adresse = (roh or "").strip().rstrip("/")
    teile = urlparse(adresse)
    if teile.scheme != "http" or not teile.hostname or teile.path or teile.query:
        raise ErweiterungFehler("Die Adresse sieht so aus: http://<container>:<port>, "
                                "z. B. http://ota-gedaechtnis:8080")
    return adresse


def manifest_pruefen(m: Any) -> dict[str, Any]:
    if not isinstance(m, dict):
        raise ErweiterungFehler("Das Manifest ist kein JSON-Objekt.")
    if m.get("ota_schnittstelle") != SCHNITTSTELLE:
        raise ErweiterungFehler(f"Die Erweiterung spricht Schnittstelle {m.get('ota_schnittstelle')}, "
                                f"OTA Schnittstelle {SCHNITTSTELLE}.")
    slug = str(m.get("slug") or "")
    if not SLUG_OK.fullmatch(slug):
        raise ErweiterungFehler(f"„{slug}“ taugt nicht als Kennung (a–z, 0–9, 2–31 Zeichen).")
    pfade = m.get("pfade_fuer_arbeitsplaetze") or []
    if not isinstance(pfade, list) or not all(isinstance(p, str) and PFAD_OK.fullmatch(p) and ".." not in p
                                              for p in pfade):
        raise ErweiterungFehler("pfade_fuer_arbeitsplaetze: nur Pfade wie /mcp.")
    ansichten = []
    for a in m.get("ansichten") or []:
        pfad = str(a.get("pfad") or "")
        if a.get("ort") not in ("konto", "arbeitsplatz") or not pfad.startswith("/ansicht/"):
            raise ErweiterungFehler("ansichten: Ort konto oder arbeitsplatz, Pfad unter /ansicht/.")
        ansichten.append({"ort": a["ort"], "titel": str(a.get("titel") or m.get("name") or slug)[:80],
                          "pfad": pfad})
    return {**m, "slug": slug, "name": str(m.get("name") or slug)[:255],
            "pfade_fuer_arbeitsplaetze": pfade, "ansichten": ansichten}


def koppeln(db: DbSession, adresse: str, schluessel: str) -> Erweiterung:
    """Manifest holen, Dienstgeheimnis erzeugen und übergeben. Eine bereits
    gekoppelte Erweiterung (gleiche Kennung) wird neu gekoppelt."""
    adresse = adresse_pruefen(adresse)
    m = manifest_pruefen(_antwort(_ruf(adresse, "GET", "/ota/v1/manifest"), "Manifest"))
    geheimnis = secrets.token_urlsafe(40)
    _antwort(_ruf(adresse, "POST", "/ota/v1/koppeln",
                  json={"kopplungsschluessel": schluessel.strip(), "dienstgeheimnis": geheimnis}),
             "Koppeln")
    e = db.get(Erweiterung, m["slug"])
    if e is None:
        e = Erweiterung(slug=m["slug"], an=False, gruppen=[])
        db.add(e)
    e.name, e.adresse, e.manifest, e.geheimnis = m["name"], adresse, m, geheimnis
    e.stand, e.zuletzt_gesund = "gekoppelt", _jetzt()
    db.flush()
    return e


def manifest_auffrischen(e: Erweiterung) -> None:
    """Nach einem Update der Erweiterung: neues Manifest, gleiche Kennung."""
    m = manifest_pruefen(_antwort(_ruf(e.adresse, "GET", "/ota/v1/manifest"), "Manifest"))
    if m["slug"] != e.slug:
        raise ErweiterungFehler(f"Unter {e.adresse} antwortet jetzt „{m['slug']}“, nicht „{e.slug}“.")
    e.manifest, e.name = m, m["name"]


def einstellen(e: Erweiterung, body: dict[str, Any]) -> None:
    if "an" in body:
        e.an = bool(body["an"])
    if "gruppen" in body:
        e.gruppen = [str(g) for g in body["gruppen"] or []]
    if "prompt_an" in body:
        e.prompt_an = bool(body["prompt_an"])


def entfernen(db: DbSession, e: Erweiterung) -> None:
    """Entkoppeln: Tokens widerrufen, Routen weg. Die Daten bleiben in der
    Erweiterung — wer sie loswerden will, entfernt deren Volume."""
    for t in db.scalars(select(ErweiterungToken).where(ErweiterungToken.slug == e.slug)).all():
        try:
            aufruf(e, "DELETE", f"/ota/v1/arbeitsplatz/{t.session_id}", "Widerrufen", zeitlimit=3.0)
        except ErweiterungFehler:
            pass
        db.delete(t)
    for a in db.scalars(select(ErweiterungAuftrag).where(ErweiterungAuftrag.slug == e.slug)).all():
        db.delete(a)
    db.delete(e)


def alle(db: DbSession) -> list[Erweiterung]:
    return list(db.scalars(select(Erweiterung).order_by(Erweiterung.name)).all())


def berechtigt(e: Erweiterung, user: User) -> bool:
    if not e.an or not user.is_active or user.is_locked:
        return False
    if not e.gruppen or user.is_admin:
        return True
    erlaubt = set(e.gruppen)
    return any(str(g.id) in erlaubt for g in user.groups)


def stand(e: Erweiterung) -> dict[str, Any]:
    """Für die Oberfläche. Das Dienstgeheimnis verlässt den Server nie."""
    m = e.manifest or {}
    return {"slug": e.slug, "name": e.name, "adresse": e.adresse, "an": e.an, "gruppen": e.gruppen,
            "prompt_an": e.prompt_an, "stand": e.stand, "version": m.get("version", ""),
            "beschreibung": m.get("beschreibung", ""), "konfiguration_schema": m.get("konfiguration") or {},
            "ansichten": m.get("ansichten") or [], "liefert": m.get("liefert") or [],
            "pfade": m.get("pfade_fuer_arbeitsplaetze") or [],
            "zuletzt_gesund": e.zuletzt_gesund.isoformat() if e.zuletzt_gesund else None}


# --------------------------------------------------------------------------
# Routen für Traefik (schreibt der Agent)
# --------------------------------------------------------------------------

def routen(db: DbSession) -> list[dict[str, Any]]:
    """Was Traefik öffnen soll — nur für eingeschaltete Erweiterungen."""
    return [{"slug": e.slug, "adresse": e.adresse,
             "pfade": list((e.manifest or {}).get("pfade_fuer_arbeitsplaetze") or []),
             "ansichten": bool((e.manifest or {}).get("ansichten"))}
            for e in alle(db) if e.an]


def routen_schieben(db: DbSession) -> None:
    from . import agent_client

    try:
        agent_client.erweiterungen_routen(routen(db))
    except Exception as exc:  # noqa: BLE001 — Routen kommen beim nächsten Takt
        log.warning("Routen der Erweiterungen nicht geschrieben: %s", getattr(exc, "detail", exc))


# --------------------------------------------------------------------------
# Arbeitsplätze
# --------------------------------------------------------------------------

def fuer_sitzung(db: DbSession, sess: SessionModel, user: User, tpl: Any) -> list[dict[str, Any]]:
    """Was der Agent im Arbeitsplatz einrichtet: je berechtigter Erweiterung
    Token, MCP-Eintrag und Prompt. Was nicht antwortet, fehlt eben."""
    raus = []
    for e in alle(db):
        if not berechtigt(e, user):
            continue
        liefert = set((e.manifest or {}).get("liefert") or [])
        try:
            a = aufruf(e, "POST", "/ota/v1/arbeitsplatz", "Arbeitsplatz anmelden", zeitlimit=3.0, json={
                "arbeitsplatz_id": str(sess.id), "arbeitsplatz_name": getattr(tpl, "name", "") or "",
                "nutzer": {"id": str(user.id), "name": user.username,
                           "anzeigename": user.display_name or user.username},
                "gruppen": [str(g.id) for g in user.groups], "vorlage": getattr(tpl, "slug", ""),
                "root": getattr(tpl, "klasse", "") == "root"})
        except ErweiterungFehler as exc:
            log.warning("Erweiterung %s für %s nicht eingerichtet: %s", e.slug, sess.id, exc)
            e.stand = f"Fehler beim Start eines Arbeitsplatzes: {exc}"[:255]
            continue
        token = str(a.get("token") or "")
        if not re.fullmatch(r"[A-Za-z0-9._~+/=-]{16,512}", token):
            log.warning("Erweiterung %s: unbrauchbares Token", e.slug)
            continue
        eintrag: dict[str, Any] = {"slug": e.slug, "token": token, "name": e.name}
        pfad = str(a.get("mcp_pfad") or "")
        if pfad and "opencode.mcp" in liefert and pfad in (e.manifest or {}).get("pfade_fuer_arbeitsplaetze", []):
            eintrag["mcp_url"] = f"http://{HOST}:{PORT}/{e.slug}{pfad}"
            eintrag["fragen"] = [str(w) for w in a.get("opencode_fragen") or []
                                 if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", str(w))]
        if "opencode.plugin" in liefert:
            eintrag["plugins"] = [p for p in a.get("opencode_plugin") or [] if p in PLUGINS]
        if "prompt" in liefert and e.prompt_an:
            eintrag["prompt"] = str(a.get("prompt") or "")[:PROMPT_LAENGE]
        raus.append(eintrag)
        if db.get(ErweiterungToken, (sess.id, e.slug)) is None:
            db.add(ErweiterungToken(session_id=sess.id, slug=e.slug))
    db.flush()
    return raus


def widerrufen(db: DbSession, session_id: uuid.UUID) -> None:
    """Die Tokens eines Arbeitsplatzes widerrufen. Committet nicht; was nicht
    durchkommt, holt der Abgleich nach."""
    for t in db.scalars(select(ErweiterungToken).where(ErweiterungToken.session_id == session_id)).all():
        e = db.get(Erweiterung, t.slug)
        if e is not None:
            try:
                aufruf(e, "DELETE", f"/ota/v1/arbeitsplatz/{session_id}", "Widerrufen", zeitlimit=3.0)
            except ErweiterungFehler as exc:
                log.info("Token von %s bei %s nicht widerrufen: %s", session_id, t.slug, exc)
                continue
        db.delete(t)


def abgleichen(db: DbSession) -> None:
    """Alle 15 Minuten: Tokens beendeter Arbeitsplätze widerrufen — auch die,
    von denen OTA nichts mehr weiss. Committet."""
    laufend = {str(i) for (i,) in db.execute(
        select(SessionModel.id).where(SessionModel.status.in_(LIVE))).all()}
    for t in db.scalars(select(ErweiterungToken)).all():
        if str(t.session_id) not in laufend:
            widerrufen(db, t.session_id)
    for e in alle(db):
        try:
            aktiv = aufruf(e, "GET", "/ota/v1/arbeitsplaetze", "Abgleich").get("arbeitsplaetze") or []
        except ErweiterungFehler:
            continue
        for platz in aktiv:
            if str(platz) not in laufend:
                try:
                    aufruf(e, "DELETE", f"/ota/v1/arbeitsplatz/{platz}", "Widerrufen", zeitlimit=3.0)
                except ErweiterungFehler:
                    pass
    db.commit()


# --------------------------------------------------------------------------
# Menschen
# --------------------------------------------------------------------------

def nutzer_abgleichen(db: DbSession, user: User) -> None:
    """Nach einer Änderung an einem Konto: gesperrt, wer nicht (mehr) darf.
    Die Daten bleiben; wer wieder darf, findet sie vor."""
    for e in alle(db):
        weg = "entsperren" if berechtigt(e, user) else "sperren"
        try:
            aufruf(e, "POST", f"/ota/v1/nutzer/{user.id}/{weg}", weg, zeitlimit=3.0)
        except ErweiterungFehler as exc:
            log.info("Erweiterung %s: %s %s nicht gemeldet: %s", e.slug, weg, user.username, exc)


def alle_nutzer_abgleichen(db: DbSession) -> None:
    for user in db.scalars(select(User)).all():
        nutzer_abgleichen(db, user)


def vor_dem_loeschen(db: DbSession, user: User) -> None:
    """Ein OTA-Konto wird gelöscht: Jede Erweiterung löscht dessen Daten. Wer
    nicht erreichbar ist, bekommt den Auftrag, bis er bestätigt."""
    for e in alle(db):
        db.add(ErweiterungAuftrag(slug=e.slug, art="nutzer_loeschen", nutzer_id=user.id))
    db.flush()
    auftraege_abarbeiten(db, commit=False)


def auftraege_abarbeiten(db: DbSession, commit: bool = True) -> None:
    from . import audit

    for a in db.scalars(select(ErweiterungAuftrag).order_by(ErweiterungAuftrag.am)).all():
        e = db.get(Erweiterung, a.slug)
        if e is None:
            db.delete(a)
            continue
        try:
            erg = aufruf(e, "POST", f"/ota/v1/nutzer/{a.nutzer_id}/loeschen", "Konto löschen", zeitlimit=10.0)
        except ErweiterungFehler as exc:
            a.versuche += 1
            a.fehler = str(exc)[:500]
            continue
        audit.record(db, "erweiterung.nutzer_geloescht", object_type="erweiterung", object_id=e.slug,
                     nutzer_id=str(a.nutzer_id), eintraege=erg.get("eintraege"))
        db.delete(a)
    if commit:
        db.commit()


# --------------------------------------------------------------------------
# Ansichten im Browser (forwardAuth)
# --------------------------------------------------------------------------

def signatur(geheim: str, mensch: str, name: str, arbeitsplaetze: str, zeit: str) -> str:
    """Muss genau so in der Erweiterung geprüft werden."""
    nachricht = f"{mensch}|{name}|{arbeitsplaetze}|{zeit}".encode()
    return hmac.new(geheim.encode(), nachricht, hashlib.sha256).hexdigest()


_PLATZ = re.compile(r"/ansicht/arbeitsplatz/([0-9a-fA-F-]{36})(?:[/?]|$)")


def pruefen(db: DbSession, slug: str, user: User, uri: str) -> dict[str, str]:
    """Für Traefiks forwardAuth: Darf dieser Mensch diese Ansicht sehen?
    Gibt die Kopfzeilen zurück, die Traefik an die Erweiterung weiterreicht."""
    e = db.get(Erweiterung, slug)
    if e is None or not berechtigt(e, user):
        raise PermissionError("Diese Erweiterung ist für dich nicht eingeschaltet.")
    plaetze = [str(i) for (i,) in db.execute(
        select(SessionModel.id).where(SessionModel.user_id == user.id,
                                      SessionModel.status.in_((*LIVE, "angehalten")))
        .order_by(SessionModel.started_at.desc()).limit(50)).all()]
    if (m := _PLATZ.search(urlparse(uri).path)):
        ziel = m.group(1).lower()
        sess = db.get(SessionModel, uuid.UUID(ziel))
        if sess is None or sess.user_id != user.id:
            raise PermissionError("Dieser Arbeitsplatz gehört dir nicht.")
        if ziel not in plaetze:
            plaetze.append(ziel)
    name = quote(user.username, safe="")
    liste = ",".join(plaetze)
    zeit = str(int(time.time()))
    return {"X-OTA-Nutzer": str(user.id), "X-OTA-Name": name, "X-OTA-Arbeitsplaetze": liste,
            "X-OTA-Zeit": zeit, "X-OTA-Signatur": signatur(e.geheimnis, str(user.id), name, liste, zeit)}


def ansichten_fuer(db: DbSession, user: User) -> list[dict[str, Any]]:
    """Was die Oberfläche diesem Menschen anbietet (Mein Konto, ⋯-Menü)."""
    raus = []
    for e in alle(db):
        if not berechtigt(e, user):
            continue
        for a in (e.manifest or {}).get("ansichten") or []:
            raus.append({"slug": e.slug, "name": e.name, "ort": a["ort"], "titel": a["titel"],
                         "url": f"/x/{e.slug}{a['pfad']}"})
    return raus


# --------------------------------------------------------------------------
# Takt (main.py, jede Minute)
# --------------------------------------------------------------------------

_zuletzt = {"gesund": 0.0, "abgleich": 0.0}


def takt(db: DbSession) -> None:
    jetzt = time.monotonic()
    if jetzt - _zuletzt["gesund"] >= 60:
        _zuletzt["gesund"] = jetzt
        for e in alle(db):
            try:
                g = aufruf(e, "GET", "/ota/v1/gesund", "Gesundheit", zeitlimit=5.0)
                e.zuletzt_gesund = _jetzt()
                eb = g.get("einbettung") or {}
                e.stand = ("bereit" if not eb.get("an") or eb.get("erreichbar")
                           else f"bereit, Embeddings nicht erreichbar: {eb.get('meldung', '')}")[:255]
                if (e.manifest or {}).get("version") != g.get("version"):
                    manifest_auffrischen(e)
            except ErweiterungFehler as exc:
                e.stand = str(exc)[:255]
        db.commit()
    if jetzt - _zuletzt["abgleich"] >= 900:
        _zuletzt["abgleich"] = jetzt
        abgleichen(db)
        auftraege_abarbeiten(db)
        alle_nutzer_abgleichen(db)
        db.commit()
        routen_schieben(db)
