"""IDE-AI: ein KI-Assistent in VS Code, VSCodium und PyCharm, verbunden mit
dem eigenen KI-Server (Handbuch Kapitel 28).

Dahinter steckt [Continue](https://continue.dev) (Apache-2.0). OTA

* bringt es als Paket aus der eigenen Paketquelle in jeden Arbeitsplatz, in
  dem es einen passenden Editor gibt (`ota-ide-ai-vscode`,
  `ota-ide-ai-jetbrains`, gebaut von scripts/build-ide-ai-deb.sh), und hebt
  es bei jedem Start und Fortsetzen auf die neueste Fassung;
* schreibt die Konfiguration ins Zuhause (`~/.continue/config.yaml`):
  Server, Modelle, Kontextfenster, Antwortlänge und was sonst hier
  eingestellt ist. Wer OTAs erste Zeile löscht, übernimmt die Datei selbst;
* gibt den KI-Server in der Firewall frei, solange IDE-AI an ist.

Der Server spricht die OpenAI-Schnittstelle (`/v1/chat/completions`) — das
können vLLM, llama.cpp (auch hinter llama-swap), Ollama und LiteLLM.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any
from urllib.parse import urlparse

import httpx
import yaml
from sqlalchemy.orm import Session as DbSession

from . import settings_store
from .models import User

log = logging.getLogger("ota.ide_ai")

# Die erste Zeile jeder Datei, die OTA schreibt. Der Agent prüft genau diese
# Zeile (agent/otaagent/ide_ai.py): Fehlt sie, gehört die Datei dem Menschen.
MARKE = "# Verwaltet von OTA (IDE-AI)."

VORGABEN: dict[str, Any] = {
    "an": False,
    # Mit /v1, so wie die OpenAI-Schnittstelle des Servers beginnt.
    "url": "",
    "api_key": "",
    # Leer: alle. Sonst nur Mitglieder dieser Gruppen (Kennungen) und Admins.
    "gruppen": [],
    # Die angebotenen Modelle, das Standardmodell zuerst. Je Modell
    # Kontextfenster und Antwortlänge, weil beides am Modell hängt.
    "modelle": [],
    "standard": "",
    # Ein Modell für die Vervollständigung beim Tippen, oder leer = aus.
    "autocomplete": "",
    # None: was der Server vorgibt.
    "temperatur": None,
    # Werkzeuge (Dateien lesen und ändern, Befehle): der Agent-Modus von
    # Continue. Braucht einen Server, der Werkzeugaufrufe beherrscht.
    "werkzeuge": True,
    "zeitlimit": 600,
    # Hinweise an das Modell bei jeder Anfrage, eine Zeile je Regel.
    "regeln": "",
    # Den Firmenproxy für den KI-Server umgehen. Er steht fast immer im
    # eigenen Netz, und ein Proxy davor scheitert dann am Rückweg.
    "ohne_proxy": True,
}
KONTEXT_VORGABE = 8192
ANTWORT_VORGABE = 2048
MODELL_OK = re.compile(r"[\w.:/@+-]{1,200}")


class IdeAiFehler(Exception):
    """Etwas taugt nicht. Die Meldung geht an den Menschen."""


def einstellungen(db: DbSession) -> dict[str, Any]:
    gespeichert = settings_store.get(db, settings_store.IDE_AI) or {}
    return {**VORGABEN, **{k: v for k, v in gespeichert.items() if k in VORGABEN}}


def url_pruefen(roh: str) -> str:
    """Die Adresse der Schnittstelle — mit /v1, wenn kein Pfad dasteht."""
    url = (roh or "").strip().rstrip("/")
    if not url:
        return ""
    teile = urlparse(url)
    if teile.scheme not in ("http", "https") or not teile.hostname:
        raise IdeAiFehler("Die Adresse beginnt mit http:// oder https://, z. B. http://192.168.1.2:3000/v1.")
    try:
        teile.port
    except ValueError as exc:
        raise IdeAiFehler("Der Port in der Adresse ist ungültig.") from exc
    if teile.query or teile.fragment or teile.username:
        raise IdeAiFehler("Die Adresse darf weder Parameter noch Zugangsdaten enthalten.")
    if not teile.path:
        url += "/v1"
    return url


def _zahl(wert: Any, unten: int, oben: int, fehler: str) -> int:
    """Eine ganze Zahl in den Grenzen — sonst die Meldung `fehler`."""
    try:
        n = int(wert)
    except (TypeError, ValueError) as exc:
        raise IdeAiFehler(fehler) from exc
    if not unten <= n <= oben:
        raise IdeAiFehler(fehler)
    return n


def speichern(db: DbSession, body: dict[str, Any]) -> dict[str, Any]:
    """Prüfen und speichern, was kommt. Was fehlt, bleibt, wie es war."""
    neu = einstellungen(db)
    if "url" in body:
        neu["url"] = url_pruefen(str(body["url"] or ""))
    if "api_key" in body and body["api_key"] is not None:
        # Leer heißt: keinen Schlüssel. Die Oberfläche schickt das Feld nur,
        # wenn jemand es geändert hat — gelesen wird es nie.
        neu["api_key"] = str(body["api_key"]).strip()
    if "gruppen" in body:
        neu["gruppen"] = [str(g) for g in body["gruppen"] or []]
    if "modelle" in body:
        modelle = []
        for m in body["modelle"] or []:
            mid = str(m.get("id") or "").strip()
            if not MODELL_OK.fullmatch(mid):
                raise IdeAiFehler(f"„{mid}“ ist kein gültiger Modellname.")
            if any(x["id"] == mid for x in modelle):
                continue
            kontext = _zahl(m.get("kontext") or KONTEXT_VORGABE, 512, 2_000_000,
                            f"{mid}: Das Kontextfenster liegt zwischen 512 und 2000000 Tokens.")
            antwort = _zahl(m.get("max_tokens") or ANTWORT_VORGABE, 16, 1_000_000,
                            f"{mid}: Die Antwortlänge liegt zwischen 16 und 1000000 Tokens.")
            if antwort >= kontext:
                raise IdeAiFehler(f"{mid}: Die Antwortlänge muss kleiner sein als das Kontextfenster.")
            modelle.append({"id": mid, "titel": str(m.get("titel") or "").strip()[:80],
                            "kontext": kontext, "max_tokens": antwort})
        neu["modelle"] = modelle
    for feld in ("standard", "autocomplete"):
        if feld in body:
            neu[feld] = str(body[feld] or "").strip()
    if "temperatur" in body:
        t = body["temperatur"]
        if t in (None, ""):
            neu["temperatur"] = None
        else:
            try:
                t = float(t)
            except (TypeError, ValueError) as exc:
                raise IdeAiFehler("Temperatur: eine Zahl zwischen 0 und 2.") from exc
            if not 0 <= t <= 2:
                raise IdeAiFehler("Temperatur: eine Zahl zwischen 0 und 2.")
            neu["temperatur"] = t
    for feld in ("werkzeuge", "ohne_proxy"):
        if feld in body:
            neu[feld] = bool(body[feld])
    if "zeitlimit" in body:
        neu["zeitlimit"] = _zahl(body["zeitlimit"], 10, 3600,
                                 "Das Zeitlimit liegt zwischen 10 und 3600 Sekunden.")
    if "regeln" in body:
        neu["regeln"] = str(body["regeln"] or "")[:4000]
    if "an" in body:
        neu["an"] = bool(body["an"])

    ids = [m["id"] for m in neu["modelle"]]
    if neu["standard"] not in ids:
        neu["standard"] = ids[0] if ids else ""
    if neu["autocomplete"] and neu["autocomplete"] not in ids:
        neu["autocomplete"] = ""
    if neu["an"] and not neu["url"]:
        raise IdeAiFehler("Erst die Adresse des KI-Servers eintragen.")
    if neu["an"] and not ids:
        raise IdeAiFehler("Erst mindestens ein Modell auswählen.")
    settings_store.put(db, settings_store.IDE_AI, neu)
    return neu


# --------------------------------------------------------------------------
# Der KI-Server
# --------------------------------------------------------------------------

def _kopf(schluessel: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {schluessel}"} if schluessel else {}


def _client() -> httpx.Client:
    # Ohne Proxy aus der Umgebung: Der KI-Server steht im eigenen Netz, und
    # ein Firmenproxy davor beantwortet die Frage nach 192.168.x nicht.
    return httpx.Client(timeout=httpx.Timeout(15.0, read=180.0), trust_env=False)


def modelle_abrufen(url: str, schluessel: str) -> list[dict[str, Any]]:
    """Was der Server anbietet — mit Kontextfenster, wenn er es verrät.

    vLLM nennt es (`max_model_len`), llama.cpp in `meta.n_ctx_train` die
    Obergrenze des Modells — nicht, womit der Server gestartet wurde. Fehlt
    es, bleibt das Feld leer, und die Oberfläche nimmt die Vorgabe.
    """
    url = url_pruefen(url)
    if not url:
        raise IdeAiFehler("Erst die Adresse des KI-Servers eintragen.")
    try:
        with _client() as c:
            r = c.get(f"{url}/models", headers=_kopf(schluessel))
    except httpx.HTTPError as exc:
        raise IdeAiFehler(f"Der KI-Server antwortet nicht: {exc}") from exc
    if r.status_code in (401, 403):
        raise IdeAiFehler("Der KI-Server lehnt ab — stimmt der API-Schlüssel?")
    if r.status_code != 200:
        raise IdeAiFehler(f"Der KI-Server meldet {r.status_code} auf {url}/models — stimmt die Adresse (mit /v1)?")
    try:
        daten = r.json().get("data") or []
    except (ValueError, AttributeError) as exc:
        raise IdeAiFehler("Die Antwort ist keine Modellliste — stimmt die Adresse (mit /v1)?") from exc
    raus = []
    for m in daten:
        mid = str(m.get("id") or "")
        if not mid:
            continue
        kontext = m.get("max_model_len") or (m.get("meta") or {}).get("n_ctx_train")
        raus.append({"id": mid, "titel": str(m.get("name") or "")[:80],
                     "beschreibung": str(m.get("description") or "")[:200],
                     "kontext": int(kontext) if isinstance(kontext, int) else None})
    return raus


def testen(db: DbSession, modell: str) -> dict[str, Any]:
    """Eine kurze Frage an das Modell, so wie Continue sie stellt."""
    e = einstellungen(db)
    if not e["url"]:
        raise IdeAiFehler("Erst die Adresse des KI-Servers eintragen.")
    m = next((x for x in e["modelle"] if x["id"] == modell), None)
    if m is None:
        raise IdeAiFehler("Dieses Modell ist nicht ausgewählt.")
    frage = {"model": modell, "stream": False, "max_tokens": min(m["max_tokens"], 1024),
             "messages": [{"role": "user", "content": "Antworte nur mit dem Wort: OK"}]}
    beginn = time.monotonic()
    try:
        with _client() as c:
            r = c.post(f"{e['url']}/chat/completions", json=frage, headers=_kopf(e["api_key"]))
    except httpx.HTTPError as exc:
        raise IdeAiFehler(f"Der KI-Server antwortet nicht: {exc}") from exc
    dauer = int((time.monotonic() - beginn) * 1000)
    if r.status_code != 200:
        raise IdeAiFehler(f"Der KI-Server meldet {r.status_code}: {r.text[:300]}")
    try:
        wahl = (r.json().get("choices") or [{}])[0]
    except ValueError as exc:
        raise IdeAiFehler("Die Antwort des KI-Servers ist kein JSON.") from exc
    nachricht = wahl.get("message") or {}
    return {"ok": True, "ms": dauer, "antwort": str(nachricht.get("content") or "")[:300],
            "denkt": bool(nachricht.get("reasoning_content")),
            "abbruch": wahl.get("finish_reason") or ""}


# --------------------------------------------------------------------------
# Was in den Arbeitsplatz kommt
# --------------------------------------------------------------------------

def berechtigt(db: DbSession, user: User, e: dict[str, Any] | None = None) -> bool:
    e = e or einstellungen(db)
    if not e["an"] or not user.is_active or user.is_locked:
        return False
    if not e["gruppen"] or user.is_admin:
        return True
    erlaubt = set(e["gruppen"])
    return any(str(g.id) in erlaubt for g in user.groups)


def konfiguration(e: dict[str, Any]) -> str:
    """Continues config.yaml (Schema v1), mit OTAs Marke in der ersten Zeile."""
    host = urlparse(e["url"]).hostname or ""
    modelle = sorted(e["modelle"], key=lambda m: m["id"] != e["standard"])
    eintraege = []
    for m in modelle:
        rollen = ["chat", "edit", "apply", "summarize"]
        if m["id"] == e["autocomplete"]:
            rollen.append("autocomplete")
        optionen: dict[str, Any] = {"contextLength": m["kontext"], "maxTokens": m["max_tokens"]}
        if e["temperatur"] is not None:
            optionen["temperature"] = e["temperatur"]
        anfrage: dict[str, Any] = {"timeout": e["zeitlimit"]}
        if e["ohne_proxy"] and host:
            anfrage["noProxy"] = [host]
        eintrag: dict[str, Any] = {
            "name": m["titel"] or m["id"], "provider": "openai", "model": m["id"],
            "apiBase": e["url"], "roles": rollen,
            "defaultCompletionOptions": optionen, "requestOptions": anfrage,
        }
        if e["api_key"]:
            eintrag["apiKey"] = e["api_key"]
        if e["werkzeuge"]:
            eintrag["capabilities"] = ["tool_use"]
        eintraege.append(eintrag)
    inhalt: dict[str, Any] = {"name": "OTA IDE-AI", "version": "1.0.0", "schema": "v1",
                              "models": eintraege}
    regeln = [z.strip() for z in (e["regeln"] or "").splitlines() if z.strip()]
    if regeln:
        inhalt["rules"] = regeln
    return (f"{MARKE} Änderungen hier überschreibt OTA beim nächsten Start.\n"
            "# Wer die Datei selbst pflegen will, löscht diese erste Zeile.\n"
            + yaml.safe_dump(inhalt, sort_keys=False, allow_unicode=True))


def fassungen(db: DbSession) -> dict[str, str]:
    """Die neuesten Fassungen der Pakete in der eigenen Paketquelle."""
    from . import paketquellen

    return dict((paketquellen.fuer_container(db) or {}).get("ide_ai") or {})


def fuer_sitzung(db: DbSession, user: User) -> dict[str, Any]:
    """Was der Agent im Arbeitsplatz einrichtet — oder {} (dann räumt er weg)."""
    e = einstellungen(db)
    if not berechtigt(db, user, e) or not e["url"] or not e["modelle"]:
        return {}
    return {"fassungen": fassungen(db), "config": konfiguration(e)}


def freigabe(db: DbSession) -> dict[str, str] | None:
    """Die Zeile für die Firewall: der KI-Server, für alle Arbeitsplätze."""
    e = einstellungen(db)
    if not e["an"] or not e["url"]:
        return None
    teile = urlparse(e["url"])
    port = teile.port or (443 if teile.scheme == "https" else 80)
    return {"ziel": teile.hostname or "", "ports": str(port), "protokoll": "tcp",
            "notiz": "IDE-AI: der KI-Server (Einstellungen → IDE-AI)"}


def stand(db: DbSession) -> dict[str, Any]:
    """Für die Einstellungen. Der API-Schlüssel verlässt den Server nie."""
    e = einstellungen(db)
    try:
        f = fassungen(db)
    except Exception:  # noqa: BLE001 — Paketquelle nicht erreichbar
        f = {}
    return {**{k: v for k, v in e.items() if k != "api_key"},
            "api_key_gesetzt": bool(e["api_key"]), "fassungen": f}
