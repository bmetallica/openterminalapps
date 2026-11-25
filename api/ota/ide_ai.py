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

import hashlib
import logging
import os
import re
import secrets
import time
from datetime import datetime, timezone
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
    # Name und Kürzel des Servers oben. Das Kürzel unterscheidet Modelle
    # gleichen Namens auf mehreren Servern und steht in der Statistik.
    "name": "KI-Server",
    "kuerzel": "ki",
    # Weitere KI-Server: [{name, kuerzel, url, api_key, modelle}]. Wirken nur
    # mit dem Durchgang — er führt alle unter einem Namen zusammen.
    "weitere": [],
    # Der KI-Durchgang (ota-ki): Continue und opencode sprechen ki.ota an,
    # die Firewall fängt Verbindungen an die Server ab.
    "durchgang": False,
    # Nutzungsstatistik je Person und Arbeitsplatz. Braucht den Durchgang.
    "statistik": False,
    # Aufbewahrung in Tagen: jede Anfrage einzeln, und Stundensummen (0 = immer).
    "frist_roh": 30,
    "frist_stunden": 365,
    # Externe Dienste (Open WebUI …) am zweiten Eingang des Durchgangs:
    # [{kuerzel, name, hash, kopf, am}]. Vom Schlüssel steht hier nur der
    # SHA-256; ihn selbst sieht die Verwaltung genau einmal, beim Anlegen.
    # `kopf`: den Kopfzeilen glauben, die sagen, wer fragt.
    "extern": [],
}
KONTEXT_VORGABE = 8192
ANTWORT_VORGABE = 2048
MODELL_OK = re.compile(r"[\w.:/@+-]{1,200}")
KUERZEL_OK = re.compile(r"[a-z0-9][a-z0-9-]{0,15}")
# Wie Continue und opencode den Durchgang ansprechen. Der Name löst der
# Resolver der Firewall in jedem Sitzungsnetz zur Adresse des Routers auf.
KI_NAME = "ki.ota"
KI_PORT = 8790
KI_URL = f"http://{KI_NAME}:{KI_PORT}/v1"


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
        neu["modelle"] = _modelle_pruefen(body["modelle"])
    if "name" in body:
        neu["name"] = str(body["name"] or "").strip()[:60] or "KI-Server"
    if "kuerzel" in body:
        neu["kuerzel"] = _kuerzel_pruefen(body["kuerzel"])
    if "weitere" in body:
        neu["weitere"] = _weitere_pruefen(body["weitere"], neu["weitere"])
    for feld in ("durchgang", "statistik"):
        if feld in body:
            neu[feld] = bool(body[feld])
    if "frist_roh" in body:
        neu["frist_roh"] = _zahl(body["frist_roh"], 1, 3650,
                                 "Die Aufbewahrung der einzelnen Anfragen liegt zwischen 1 und 3650 Tagen.")
    if "frist_stunden" in body:
        neu["frist_stunden"] = _zahl(body["frist_stunden"], 0, 36500,
                                     "Die Aufbewahrung der Stundensummen: 0 (immer) bis 36500 Tage.")
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
    # Mit Durchgang darf auch ein Modell eines weiteren Servers Standard sein.
    alle = [m["id"] for m in modelle_aussen(neu)] if neu["durchgang"] else ids
    if neu["standard"] not in alle:
        neu["standard"] = ids[0] if ids else ""
    if neu["autocomplete"] and neu["autocomplete"] not in alle:
        neu["autocomplete"] = ""
    if neu["an"] and not neu["url"]:
        raise IdeAiFehler("Erst die Adresse des KI-Servers eintragen.")
    if neu["an"] and not ids:
        raise IdeAiFehler("Erst mindestens ein Modell auswählen.")
    kuerzel = [neu["kuerzel"]] + [w["kuerzel"] for w in neu["weitere"]]
    if len(set(kuerzel)) != len(kuerzel):
        raise IdeAiFehler("Jeder KI-Server braucht ein eigenes Kürzel.")
    if neu["statistik"] and not neu["durchgang"]:
        raise IdeAiFehler("Die Nutzungsstatistik braucht den KI-Durchgang.")
    settings_store.put(db, settings_store.IDE_AI, neu)
    return neu


def _modelle_pruefen(roh: Any) -> list[dict[str, Any]]:
    modelle: list[dict[str, Any]] = []
    for m in roh or []:
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
    return modelle


def _kuerzel_pruefen(roh: Any) -> str:
    k = str(roh or "").strip().lower()
    if not KUERZEL_OK.fullmatch(k):
        raise IdeAiFehler(f"„{k}“ taugt nicht als Kürzel: Kleinbuchstaben, Ziffern und "
                          "Bindestrich, höchstens 16 Zeichen.")
    return k


def _weitere_pruefen(roh: Any, alt: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Die weiteren Server. Ein Schlüssel, der nicht mitkommt (None), bleibt —
    die Oberfläche bekommt ihn nie zu sehen und kann ihn nicht zurückschicken."""
    vorher = {w["kuerzel"]: w for w in alt}
    raus = []
    for w in roh or []:
        kuerzel = _kuerzel_pruefen(w.get("kuerzel"))
        url = url_pruefen(str(w.get("url") or ""))
        if not url:
            raise IdeAiFehler(f"{kuerzel}: Die Adresse des Servers fehlt.")
        schluessel = w.get("api_key")
        if schluessel is None:
            schluessel = (vorher.get(str(w.get("kuerzel_vorher") or kuerzel)) or {}).get("api_key", "")
        raus.append({"name": str(w.get("name") or "").strip()[:60] or kuerzel,
                     "kuerzel": kuerzel, "url": url, "api_key": str(schluessel or "").strip(),
                     "modelle": _modelle_pruefen(w.get("modelle")),
                     # Wer ihn zusätzlich bekommt. Leer: alle.
                     "gruppen": [str(g) for g in w.get("gruppen") or []]})
    return raus


def server_fuer(e: dict[str, Any], user: User | None) -> set[str]:
    """Die Kürzel der Server, die dieser Mensch bekommt.

    Der Server oben gilt für alle, die IDE-AI oder opencode haben. Ein
    weiterer Server ohne Gruppe auch; mit Gruppen nur deren Mitglieder — und
    Administratoren immer. `None`: alle (Verwaltung, Vorschau ohne Mensch).
    """
    alle = {s["kuerzel"] for s in server_liste(e)}
    if user is None or user.is_admin:
        return alle
    meine = {str(g.id) for g in user.groups}
    return {e["kuerzel"]} | {w["kuerzel"] for w in e["weitere"]
                             if w["kuerzel"] in alle and (not w.get("gruppen") or meine & set(w["gruppen"]))}


def server_liste(e: dict[str, Any]) -> list[dict[str, Any]]:
    """Alle KI-Server: der oben eingetragene zuerst, dann die weiteren.
    Ohne Durchgang zählt nur der erste — die Werkzeuge kennen dann nur ihn."""
    erster = {"name": e["name"], "kuerzel": e["kuerzel"], "url": e["url"],
              "api_key": e["api_key"], "modelle": e["modelle"]}
    return [erster] + (list(e["weitere"]) if e["durchgang"] else [])


def modelle_aussen(e: dict[str, Any]) -> list[dict[str, Any]]:
    """Ein Modellverzeichnis über alle Server, wie die Werkzeuge es sehen.

    Die Modelle des ersten Servers behalten ihren Namen; ein Modell eines
    weiteren Servers, dessen Name schon vergeben ist, heißt `kürzel/name`.
    So bleiben Standardmodell und Einstellungen von vorher gültig.
    """
    raus: list[dict[str, Any]] = []
    belegt: set[str] = set()
    for s in server_liste(e):
        if not s["url"]:
            continue
        for m in s["modelle"]:
            aussen = m["id"] if m["id"] not in belegt else f"{s['kuerzel']}/{m['id']}"
            belegt.add(aussen)
            titel = m["titel"] or m["id"]
            if aussen != m["id"]:
                titel = f"{titel} ({s['name']})"
            raus.append({**m, "id": aussen, "echt": m["id"], "titel": titel,
                         "server": s["kuerzel"]})
    return raus


def durchgang_aktiv(db: DbSession, e: dict[str, Any] | None = None) -> bool:
    from . import opencode

    e = e or einstellungen(db)
    return bool(e["durchgang"] and e["url"] and (e["an"] or opencode.an(db)))


def sicht(e: dict[str, Any], db: DbSession | None = None, user: User | None = None) -> dict[str, Any]:
    """Die Einstellungen so, wie die Werkzeuge sie brauchen: mit Durchgang
    zeigt alles auf ki.ota, ohne Schlüssel, mit den Modellen aller Server,
    die dieser Mensch bekommt."""
    if not e["durchgang"] or not e["url"]:
        return e
    if db is not None and not durchgang_aktiv(db, e):
        return e
    meine = server_fuer(e, user)
    modelle = [m for m in modelle_aussen(e) if m["server"] in meine]
    ids = {m["id"] for m in modelle}
    standard = e["standard"] if e["standard"] in ids else (e["modelle"][0]["id"] if e["modelle"] else "")
    return {**e, "url": KI_URL, "api_key": "", "modelle": modelle,
            "standard": standard, "autocomplete": e["autocomplete"] if e["autocomplete"] in ids else "",
            "ohne_proxy": True, "ueber_durchgang": True}


def _sitzungen_fuer(db: DbSession, w: dict[str, Any]) -> list[str]:
    """Die laufenden Sitzungen, deren Mensch diesen weiteren Server bekommt."""
    from .models import Session as SessionModel

    raus = []
    for sess in db.query(SessionModel).filter(
            SessionModel.status.in_(("starting", "running", "paused"))).all():
        u = sess.user
        if u is None:
            continue
        if u.is_admin or {str(g.id) for g in u.groups} & set(w["gruppen"]):
            raus.append(str(sess.id))
    return raus


def durchgang_konfig(db: DbSession) -> dict[str, Any]:
    """Was ota-ki braucht (über den Agent nach ki/konfig.json)."""
    e = einstellungen(db)
    aktiv = durchgang_aktiv(db, e)
    nach_server: dict[str, list[dict[str, str]]] = {}
    for m in modelle_aussen(e):
        nach_server.setdefault(m["server"], []).append({"aussen": m["id"], "echt": m["echt"]})
    return {
        "aktiv": aktiv,
        "statistik": bool(aktiv and e["statistik"]),
        "zeitlimit": e["zeitlimit"],
        "ohne_proxy": e["ohne_proxy"],
        "server": [{"name": s["name"], "kuerzel": s["kuerzel"], "url": s["url"],
                    "api_key": s["api_key"], "modelle": nach_server.get(s["kuerzel"], []),
                    # Ein weiterer Server mit Gruppen: nur diese Sitzungen.
                    # Der Durchgang kennt Sitzungen, keine Menschen — ausser
                    # bei externen Diensten, die sagen, wer fragt.
                    **({"alle": False, "sitzungen": _sitzungen_fuer(db, s),
                        "personen": _personen_fuer(db, s) if e["extern"] else []}
                       if s.get("gruppen") else {"alle": True})}
                   for s in server_liste(e) if s["url"]] if aktiv else [],
        "extern": [{k: d[k] for k in ("kuerzel", "name", "hash", "kopf")}
                   for d in e["extern"]] if aktiv else [],
        # KI-Sicherheit (ki_sicherheit.py, Prüfung in ki/otaki/wache.py)
        "sicherheit": _sicherheit(db) if aktiv else {},
    }


def _sicherheit(db: DbSession) -> dict[str, Any]:
    from . import ki_sicherheit

    return ki_sicherheit.konfig(db)


def _personen_fuer(db: DbSession, w: dict[str, Any]) -> list[str]:
    """E-Mail und Benutzername (klein) aller, die diesen weiteren Server
    bekommen — für Anfragen externer Dienste, die nur sagen, wer fragt."""
    from .models import User as UserModel

    raus: set[str] = set()
    for u in db.query(UserModel).filter(UserModel.is_active.is_(True)).all():
        if u.is_admin or {str(g.id) for g in u.groups} & set(w["gruppen"]):
            raus.add(u.username.lower())
            if u.email:
                raus.add(u.email.strip().lower())
    return sorted(raus)


# --------------------------------------------------------------------------
# Externe Dienste
# --------------------------------------------------------------------------

def extern_port() -> str:
    return os.environ.get("OTA_KI_EXTERN_PORT", "").strip()


def extern_anlegen(db: DbSession, name: str, kopf: bool = True) -> tuple[dict[str, Any], str]:
    """Einen externen Dienst eintragen. Gibt den Eintrag und den Schlüssel
    zurück — der steht danach nirgends mehr im Klartext."""
    e = einstellungen(db)
    if not e["durchgang"]:
        raise IdeAiFehler("Externe Dienste brauchen den KI-Durchgang.")
    name = " ".join(str(name or "").split())[:60]
    if not name:
        raise IdeAiFehler("Bitte einen Namen angeben, z. B. Open WebUI.")
    basis = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:12].strip("-") or "dienst"
    belegt = {d["kuerzel"] for d in e["extern"]}
    kuerzel, n = basis, 2
    while kuerzel in belegt:
        kuerzel, n = f"{basis[:10]}{n}", n + 1
    schluessel = "otaki_" + secrets.token_urlsafe(32)
    eintrag = {"kuerzel": kuerzel, "name": name, "kopf": bool(kopf),
               "hash": hashlib.sha256(schluessel.encode()).hexdigest(),
               "am": datetime.now(timezone.utc).isoformat()}
    settings_store.put(db, settings_store.IDE_AI, {**e, "extern": [*e["extern"], eintrag]})
    return eintrag, schluessel


def extern_loeschen(db: DbSession, kuerzel: str) -> bool:
    e = einstellungen(db)
    rest = [d for d in e["extern"] if d["kuerzel"] != kuerzel]
    if len(rest) == len(e["extern"]):
        return False
    settings_store.put(db, settings_store.IDE_AI, {**e, "extern": rest})
    return True


def ki_ziele(db: DbSession) -> list[dict[str, Any]]:
    """Für die Firewall: wessen Verkehr der Durchgang abfängt."""
    e = einstellungen(db)
    if not durchgang_aktiv(db, e):
        return []
    raus = []
    for s in server_liste(e):
        teile = urlparse(s["url"])
        if teile.hostname:
            raus.append({"ziel": teile.hostname,
                         "port": teile.port or (443 if teile.scheme == "https" else 80)})
    return raus


def durchgang_schieben(db: DbSession) -> None:
    """Die Konfiguration an ota-ki geben. Scheitert das, bleibt die alte —
    beim nächsten Speichern oder Abholen kommt die neue."""
    from . import agent_client

    try:
        agent_client.ki_konfig(durchgang_konfig(db))
    except Exception as exc:  # noqa: BLE001 — darf keine Anfrage kippen
        log.warning("Konfiguration des KI-Durchgangs nicht übertragbar: %s", exc)


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


def testen(db: DbSession, modell: str, kuerzel: str = "") -> dict[str, Any]:
    """Eine kurze Frage an das Modell, so wie Continue sie stellt."""
    e = einstellungen(db)
    if not e["url"]:
        raise IdeAiFehler("Erst die Adresse des KI-Servers eintragen.")
    # Ein Modell eines weiteren Servers: dorthin, mit dessen Schlüssel.
    server = next((s for s in [{"url": e["url"], "api_key": e["api_key"], "modelle": e["modelle"],
                                "kuerzel": e["kuerzel"]}] + e["weitere"]
                   if (not kuerzel or s["kuerzel"] == kuerzel)
                   and any(x["id"] == modell for x in s["modelle"])), None)
    if server is None:
        raise IdeAiFehler("Dieses Modell ist nicht ausgewählt.")
    m = next(x for x in server["modelle"] if x["id"] == modell)
    e = {**e, "url": server["url"], "api_key": server["api_key"]}
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


def aktiv_fuer(db: DbSession, user: User, e: dict[str, Any] | None = None) -> bool:
    """Kommt IDE-AI in die Arbeitsplätze dieses Menschen?"""
    e = e or einstellungen(db)
    return berechtigt(db, user, e) and bool(e["url"]) and bool(e["modelle"])


def fuer_sitzung(db: DbSession, user: User) -> dict[str, Any]:
    """Was der Agent im Arbeitsplatz einrichtet — oder {} (dann räumt er weg)."""
    e = einstellungen(db)
    if not aktiv_fuer(db, user, e):
        return {}
    return {"fassungen": fassungen(db), "config": konfiguration(sicht(e, db, user))}


def freigaben(db: DbSession) -> list[dict[str, str]]:
    """Die Zeilen für die Firewall: die KI-Server, für alle Arbeitsplätze —
    solange IDE-AI oder opencode (Kapitel 38) an ist. Auch mit Durchgang:
    Liegt er, geht der Verkehr wieder direkt, und dafür muss der Weg offen sein."""
    from . import opencode

    e = einstellungen(db)
    if not (e["an"] or opencode.an(db)) or not e["url"]:
        return []
    raus = []
    for s in server_liste(e):
        if s.get("gruppen"):
            # Nur für bestimmte Gruppen: kein Weg an allen vorbei. Erreichbar
            # ist er dann nur über den Durchgang, der die Gruppe prüft — liegt
            # der, bleibt dieser Server zu, statt für alle offen zu sein.
            continue
        teile = urlparse(s["url"])
        port = teile.port or (443 if teile.scheme == "https" else 80)
        raus.append({"ziel": teile.hostname or "", "ports": str(port), "protokoll": "tcp",
                     "notiz": f"IDE-AI/opencode: KI-Server {s['name']} (Einstellungen → IDE-AI)"})
    return raus


def stand(db: DbSession) -> dict[str, Any]:
    """Für die Einstellungen. Der API-Schlüssel verlässt den Server nie."""
    e = einstellungen(db)
    try:
        f = fassungen(db)
    except Exception:  # noqa: BLE001 — Paketquelle nicht erreichbar
        f = {}
    weitere = [{**{k: v for k, v in w.items() if k != "api_key"}, "api_key_gesetzt": bool(w["api_key"])}
               for w in e["weitere"]]
    extern = [{k: v for k, v in d.items() if k != "hash"} for d in e["extern"]]
    return {**{k: v for k, v in e.items() if k not in ("api_key", "weitere", "extern")},
            "weitere": weitere, "extern": extern, "extern_port": extern_port(), "api_key_gesetzt": bool(e["api_key"]), "fassungen": f,
            "ki_url": KI_URL, "durchgang_aktiv": durchgang_aktiv(db, e),
            "modelle_alle": [{"id": m["id"], "titel": m["titel"], "server": m["server"]}
                             for m in modelle_aussen(e)]}
