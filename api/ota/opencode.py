"""opencode in den Arbeitsplätzen, zentral verwaltet (Handbuch Kapitel 38).

OTA

* bringt opencode als Paket aus der eigenen Paketquelle (`ota-opencode`,
  gebaut von scripts/build-opencode-deb.sh) und hebt es bei jedem Start und
  Fortsetzen auf die festgelegte Fassung — opencodes eigene
  Selbstaktualisierung ist aus;
* schreibt opencodes **verwaltete Konfiguration** nach
  `/etc/opencode/opencode.jsonc`. opencode liest sie mit höchstem Vorrang;
  was der Mensch in `~/.config/opencode` einstellt, kommt dazu, kann die
  verwalteten Schlüssel aber nicht überschreiben;
* verbindet opencode mit dem KI-Server aus den KI-Werkzeugen (dieselbe
  Adresse und dieselben Modelle wie IDE-AI);
* setzt einen Zusatz zum Systemprompt zusammen — global, je Gruppe und was
  Erweiterungen liefern (`/etc/opencode/ota-anweisungen.md`);
* hängt die MCP-Server der Erweiterungen ein (erweiterungen.py) samt dem
  Plugin ota-sitzung, das ihnen die Sitzung mitteilt.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session as DbSession

from . import erweiterungen, ide_ai, settings_store
from .models import Group, User

log = logging.getLogger("ota.opencode")

# Die erste Zeile der verwalteten Konfiguration. Der Agent prüft genau diese
# Zeile (agent/otaagent/opencode.py): Fehlt sie, gehört die Datei jemand
# anderem — etwa dem Image — und OTA fasst sie nicht an.
MARKE = "// Verwaltet von OTA (opencode)."
PLUGIN_ORDNER = "/usr/share/ota-opencode/plugins"
ANWEISUNGEN = "/etc/opencode/ota-anweisungen.md"
SCHLUESSEL = "/etc/opencode/ota-ki-schluessel"
TOKENS = "/etc/ota/erweiterungen"
# Die Schlüssel der weiteren MCP-Server, eine Datei je Server.
MCP_SCHLUESSEL = "/etc/opencode/ota-mcp"
MCP_NAME_OK = re.compile(r"[a-z][a-z0-9_-]{1,30}")
KOPF_OK = re.compile(r"[A-Za-z0-9-]{1,64}")
VARIABLE_OK = re.compile(r"[A-Z_][A-Z0-9_]{0,63}")
ANBIETER = "ota"

VORGABEN: dict[str, Any] = {
    "an": False,
    # Leer: alle. Sonst nur Mitglieder dieser Gruppen (Kennungen) und Admins.
    "gruppen": [],
    # Leer: das Standardmodell aus den KI-Werkzeugen.
    "standard": "",
    # Für Titel und Zusammenfassungen; leer: wie das Standardmodell.
    "klein": "",
    # Der Zusatz zum Systemprompt für alle, und je Gruppe (Kennung → Text).
    "prompt": "",
    "prompt_gruppen": {},
    # JSON, das in die verwaltete Konfiguration eingemischt wird — für alles,
    # was die Oberfläche nicht kennt (reasoning, chat_template_kwargs, eigene
    # Modelle für Compaction und Titel). Gewinnt gegen das Erzeugte.
    "zusatz": "",
    # Weitere MCP-Server, die opencode bekommt (Liste, siehe _mcp_pruefen).
    # Die Schlüssel stehen hier, gehen aber nie zurück an den Browser.
    "mcp": [],
}
PROMPT_LAENGE = 8000
# Ab hier warnt die Oberfläche: Der Zusatz geht bei jeder Anfrage mit.
PROMPT_WARNUNG_TOKENS = 2000


class OpencodeFehler(Exception):
    """Die Meldung geht an den Menschen."""


def einstellungen(db: DbSession) -> dict[str, Any]:
    gespeichert = settings_store.get(db, settings_store.OPENCODE) or {}
    return {**VORGABEN, **{k: v for k, v in gespeichert.items() if k in VORGABEN}}


def an(db: DbSession) -> bool:
    return bool(einstellungen(db)["an"])


def _zusatz(roh: str) -> dict[str, Any]:
    roh = (roh or "").strip()
    if not roh:
        return {}
    try:
        wert = json.loads(roh)
    except ValueError as exc:
        raise OpencodeFehler(f"Zusätzliche Konfiguration: kein gültiges JSON ({exc}).") from exc
    if not isinstance(wert, dict):
        raise OpencodeFehler("Zusätzliche Konfiguration: ein JSON-Objekt { … }.")
    for verboten in ("mcp", "plugin", "plugins", "instructions"):
        if verboten in wert:
            raise OpencodeFehler(f"Zusätzliche Konfiguration: „{verboten}“ setzt OTA selbst "
                                 "(Erweiterungen, Prompt-Zusatz).")
    return wert


def _mcp_pruefen(roh: Any, alt: list[dict[str, Any]], belegt: set[str]) -> list[dict[str, Any]]:
    """Die weiteren MCP-Server aus dem Formular. Ein Schlüssel, der nicht
    mitkommt (None), bleibt wie er war; leer heisst: kein Schlüssel."""
    if not isinstance(roh, list):
        raise OpencodeFehler("mcp: eine Liste von Servern.")
    vorher = {m["name"]: m for m in alt}
    raus: list[dict[str, Any]] = []
    for m in roh:
        if not isinstance(m, dict):
            raise OpencodeFehler("mcp: eine Liste von Servern.")
        name = str(m.get("name") or "").strip().lower()
        if not MCP_NAME_OK.fullmatch(name):
            raise OpencodeFehler(f"„{name}“ taugt nicht als Name eines MCP-Servers (a–z, 0–9, - und _).")
        if name in belegt or any(x["name"] == name for x in raus):
            raise OpencodeFehler(f"Der Name „{name}“ ist schon vergeben.")
        typ = "lokal" if m.get("typ") == "lokal" else "entfernt"
        eintrag: dict[str, Any] = {"name": name, "typ": typ, "an": bool(m.get("an", True)),
                                   "gruppen": [str(g) for g in m.get("gruppen") or []]}
        if typ == "entfernt":
            url = str(m.get("url") or "").strip()
            teile = urlparse(url)
            if teile.scheme not in ("http", "https") or not teile.hostname:
                raise OpencodeFehler(f"{name}: Die Adresse beginnt mit http:// oder https://.")
            kopf = str(m.get("kopf") or "Authorization").strip()
            if not KOPF_OK.fullmatch(kopf):
                raise OpencodeFehler(f"{name}: „{kopf}“ ist kein gültiger Name einer Kopfzeile.")
            eintrag.update(url=url, kopf=kopf, praefix=str(m.get("praefix", "Bearer ") or "")[:40],
                           freigeben=bool(m.get("freigeben", True)))
        else:
            befehl = m.get("befehl")
            if isinstance(befehl, str):
                befehl = befehl.split()
            if not isinstance(befehl, list) or not befehl or not all(isinstance(b, str) and b for b in befehl):
                raise OpencodeFehler(f"{name}: Der Befehl fehlt, z. B. npx -y @modelcontextprotocol/server-github.")
            variable = str(m.get("variable") or "").strip()
            if variable and not VARIABLE_OK.fullmatch(variable):
                raise OpencodeFehler(f"{name}: „{variable}“ ist kein gültiger Name einer Umgebungsvariable.")
            eintrag.update(befehl=[b[:500] for b in befehl[:40]], variable=variable)
        schluessel = m.get("schluessel")
        eintrag["schluessel"] = (vorher.get(name, {}).get("schluessel", "") if schluessel is None
                                 else str(schluessel).strip()[:4000])
        raus.append(eintrag)
    return raus


def mcp_fuer(e: dict[str, Any], user: User) -> list[dict[str, Any]]:
    """Die weiteren MCP-Server, die dieser Mensch bekommt."""
    meine = {str(g.id) for g in user.groups}
    return [m for m in e["mcp"] if m.get("an")
            and (not m.get("gruppen") or user.is_admin or meine & set(m["gruppen"]))]


def freigaben(db: DbSession) -> list[dict[str, str]]:
    """Für die Firewall: die entfernten MCP-Server, solange opencode an ist."""
    return freigaben_von(einstellungen(db))


def freigaben_von(e: dict[str, Any]) -> list[dict[str, str]]:
    if not e["an"]:
        return []
    raus = []
    for m in e["mcp"]:
        if m.get("an") and m.get("typ") == "entfernt" and m.get("freigeben"):
            teile = urlparse(m["url"])
            raus.append({"ziel": teile.hostname or "",
                         "ports": str(teile.port or (443 if teile.scheme == "https" else 80)),
                         "protokoll": "tcp", "notiz": f"opencode: MCP-Server {m['name']} (Einstellungen → opencode)"})
    return raus


def speichern(db: DbSession, body: dict[str, Any]) -> dict[str, Any]:
    neu = einstellungen(db)
    if "gruppen" in body:
        neu["gruppen"] = [str(g) for g in body["gruppen"] or []]
    for feld in ("standard", "klein"):
        if feld in body:
            neu[feld] = str(body[feld] or "").strip()
    if "prompt" in body:
        neu["prompt"] = str(body["prompt"] or "")[:PROMPT_LAENGE]
    if "prompt_gruppen" in body:
        roh = body["prompt_gruppen"] or {}
        if not isinstance(roh, dict):
            raise OpencodeFehler("prompt_gruppen: Gruppe → Text.")
        neu["prompt_gruppen"] = {str(k): str(v)[:PROMPT_LAENGE] for k, v in roh.items() if str(v).strip()}
    if "zusatz" in body:
        _zusatz(str(body["zusatz"] or ""))
        neu["zusatz"] = str(body["zusatz"] or "")
    if "mcp" in body:
        belegt = {x.slug for x in erweiterungen.alle(db)}
        neu["mcp"] = _mcp_pruefen(body["mcp"], neu["mcp"], belegt)
    if "an" in body:
        neu["an"] = bool(body["an"])
    ki = ide_ai.einstellungen(db)
    ids = [m["id"] for m in ki["modelle"]]
    for feld in ("standard", "klein"):
        if neu[feld] and neu[feld] not in ids:
            neu[feld] = ""
    if neu["an"] and (not ki["url"] or not ids):
        raise OpencodeFehler("Erst unter KI-Werkzeuge (IDE-AI) den KI-Server und mindestens ein "
                             "Modell eintragen — opencode nutzt dieselben.")
    settings_store.put(db, settings_store.OPENCODE, neu)
    return neu


def berechtigt(db: DbSession, user: User, e: dict[str, Any] | None = None) -> bool:
    e = e or einstellungen(db)
    if not e["an"] or not user.is_active or user.is_locked:
        return False
    if not e["gruppen"] or user.is_admin:
        return True
    erlaubt = set(e["gruppen"])
    return any(str(g.id) in erlaubt for g in user.groups)


def _mischen(basis: dict[str, Any], oben: dict[str, Any]) -> dict[str, Any]:
    raus = dict(basis)
    for k, v in oben.items():
        raus[k] = _mischen(raus[k], v) if isinstance(v, dict) and isinstance(raus.get(k), dict) else v
    return raus


def konfiguration(e: dict[str, Any], ki: dict[str, Any], angaben: list[dict[str, Any]],
                  weitere: list[dict[str, Any]] | None = None) -> str:
    """Die verwaltete Konfiguration (JSONC), mit OTAs Marke in der ersten Zeile."""
    modelle: dict[str, Any] = {}
    for m in ki["modelle"]:
        eintrag: dict[str, Any] = {"name": m["titel"] or m["id"], "tool_call": bool(ki["werkzeuge"]),
                                   "limit": {"context": m["kontext"], "output": m["max_tokens"]}}
        if ki["temperatur"] is not None:
            eintrag["options"] = {"temperature": ki["temperatur"]}
        modelle[m["id"]] = eintrag
    standard = e["standard"] or ki["standard"] or (ki["modelle"][0]["id"] if ki["modelle"] else "")
    inhalt: dict[str, Any] = {
        "$schema": "https://opencode.ai/config.json",
        # Die Fassung legt OTA fest (Paket ota-opencode).
        "autoupdate": False,
        "share": "disabled",
        "provider": {ANBIETER: {
            "npm": "@ai-sdk/openai-compatible", "name": "KI-Server (OTA)",
            "options": {"baseURL": ki["url"],
                        "apiKey": f"{{file:{SCHLUESSEL}}}" if ki["api_key"] else "ota",
                        "timeout": int(ki["zeitlimit"]) * 1000},
            "models": modelle}},
        "model": f"{ANBIETER}/{standard}",
        "small_model": f"{ANBIETER}/{e['klein'] or standard}",
        "instructions": [ANWEISUNGEN],
    }
    mcp: dict[str, Any] = {}
    fragen: dict[str, str] = {}
    sitzung_server: list[str] = []
    for a in angaben:
        if a.get("mcp_url"):
            mcp[a["slug"]] = {"type": "remote", "url": a["mcp_url"], "enabled": True,
                              "headers": {"Authorization": f"Bearer {{file:{TOKENS}/{a['slug']}/token}}"},
                              # Kein OAuth-Versuch, keine Code Mode: Die Werkzeuge
                              # direkt, damit auch lokale Modelle sie finden.
                              "oauth": False, "codemode": False, "timeout": 15000}
            for w in a.get("fragen") or []:
                fragen[f"{a['slug']}_{w}"] = "ask"
        if "ota-sitzung" in (a.get("plugins") or []):
            sitzung_server.append(a["slug"])
    for m in weitere or []:
        datei = f"{{file:{MCP_SCHLUESSEL}/{m['name']}}}"
        if m["typ"] == "entfernt":
            eintrag: dict[str, Any] = {"type": "remote", "url": m["url"], "enabled": True, "codemode": False}
            if m.get("schluessel"):
                eintrag["headers"] = {m["kopf"]: f"{m['praefix']}{datei}"}
                eintrag["oauth"] = False
        else:
            eintrag = {"type": "local", "command": list(m["befehl"]), "enabled": True, "codemode": False}
            if m.get("schluessel") and m.get("variable"):
                eintrag["environment"] = {m["variable"]: datei}
        mcp[m["name"]] = eintrag
    if mcp:
        inhalt["mcp"] = mcp
    if sitzung_server:
        inhalt["plugin"] = [[f"{PLUGIN_ORDNER}/ota-sitzung", {"server": sitzung_server}]]
    if fragen:
        inhalt["permission"] = fragen
    inhalt = _mischen(inhalt, _zusatz(e["zusatz"]))
    return (f"{MARKE} Änderungen hier überschreibt OTA beim nächsten Start.\n"
            "// Eigene Einstellungen gehören nach ~/.config/opencode/opencode.json.\n"
            + json.dumps(inhalt, ensure_ascii=False, indent=2) + "\n")


def _platzhalter(text: str, user: User, vorlage: str) -> str:
    werte = {"anzeigename": user.display_name or user.username, "nutzer": user.username,
             "vorlage": vorlage, "datum": date.today().isoformat()}
    return re.sub(r"\{(anzeigename|nutzer|vorlage|datum)\}", lambda m: werte[m.group(1)], text)


def anweisungen(db: DbSession, e: dict[str, Any], user: User, vorlage: str,
                angaben: list[dict[str, Any]]) -> str:
    teile = ["<!-- Verwaltet von OTA. Änderungen hier gehen beim nächsten Start verloren. -->"]
    if e["prompt"].strip():
        teile.append("## Vorgaben\n\n" + _platzhalter(e["prompt"].strip(), user, vorlage))
    meine = {str(g.id): g.name for g in user.groups}
    for gid, name in sorted(((gid, meine[gid]) for gid in e["prompt_gruppen"] if gid in meine),
                            key=lambda x: x[1].lower()):
        teile.append(f"## Gruppe {name}\n\n" + _platzhalter(e["prompt_gruppen"][gid].strip(), user, vorlage))
    for a in angaben:
        if a.get("prompt"):
            teile.append(f"## Erweiterung: {a.get('name') or a['slug']}\n\n{a['prompt'].strip()}")
    return "\n\n".join(teile) + "\n"


def fassung(db: DbSession) -> str:
    from . import paketquellen

    return str((paketquellen.fuer_container(db) or {}).get("opencode") or "")


def aktiv_fuer(db: DbSession, user: User, e: dict[str, Any] | None = None) -> bool:
    e = e or einstellungen(db)
    ki = ide_ai.einstellungen(db)
    return berechtigt(db, user, e) and bool(ki["url"]) and bool(ki["modelle"])


def fuer_sitzung(db: DbSession, sess: Any, user: User, tpl: Any) -> dict[str, Any]:
    """Was der Agent im Arbeitsplatz einrichtet — oder {} (dann räumt er weg)."""
    e = einstellungen(db)
    if not aktiv_fuer(db, user, e):
        return {}
    ki = ide_ai.einstellungen(db)
    angaben = erweiterungen.fuer_sitzung(db, sess, user, tpl)
    vorlage = getattr(tpl, "name", "") or ""
    weitere = mcp_fuer(e, user)
    return {
        "fassung": fassung(db),
        "config": konfiguration(e, ki, angaben, weitere),
        # Je MCP-Server mit Schlüssel eine Datei; opencode liest sie mit {file:…}.
        "mcp_schluessel": {m["name"]: m["schluessel"] for m in weitere if m.get("schluessel")},
        "anweisungen": anweisungen(db, e, user, vorlage, angaben),
        "ki_schluessel": ki["api_key"] or "",
        "erweiterungen": [{"slug": a["slug"], "token": a["token"]} for a in angaben],
    }


def vorschau(db: DbSession, user: User, entwurf: dict[str, Any] | None = None) -> dict[str, Any]:
    """Für die Einstellungen: so sähe es für diesen Menschen aus — auf Wunsch
    mit einem noch nicht gespeicherten Entwurf. Ohne Tokens; die
    Erweiterungen werden nicht gefragt."""
    gespeichert = einstellungen(db)
    e = {**gespeichert, **{k: v for k, v in (entwurf or {}).items() if k in VORGABEN}}
    _zusatz(str(e["zusatz"] or ""))
    if entwurf and "mcp" in entwurf:
        e["mcp"] = _mcp_pruefen(entwurf["mcp"], gespeichert["mcp"], {x.slug for x in erweiterungen.alle(db)})
    ki = ide_ai.einstellungen(db)
    angaben = []
    for x in erweiterungen.alle(db):
        if not erweiterungen.berechtigt(x, user):
            continue
        liefert = set((x.manifest or {}).get("liefert") or [])
        pfad = ((x.manifest or {}).get("pfade_fuer_arbeitsplaetze") or [""])[0]
        angaben.append({"slug": x.slug, "name": x.name,
                        "mcp_url": f"http://{erweiterungen.HOST}:{erweiterungen.PORT}/{x.slug}{pfad}"
                        if "opencode.mcp" in liefert and pfad else "",
                        "plugins": ["ota-sitzung"] if "opencode.plugin" in liefert else [],
                        "prompt": "(Schnipsel der Erweiterung, kommt beim Start)"
                        if "prompt" in liefert and x.prompt_an else ""})
    anw = anweisungen(db, e, user, "<Vorlage>", angaben)
    return {"berechtigt": berechtigt(db, user, e), "config": konfiguration(e, ki, angaben, mcp_fuer(e, user)),
            "anweisungen": anw, "tokens_geschaetzt": len(anw) // 4}


def stand(db: DbSession) -> dict[str, Any]:
    e = einstellungen(db)
    ki = ide_ai.einstellungen(db)
    try:
        f = fassung(db)
    except Exception:  # noqa: BLE001 — Paketquelle nicht erreichbar
        f = ""
    # Die Schlüssel der MCP-Server verlassen den Server nie.
    mcp = [{**{k: v for k, v in m.items() if k != "schluessel"}, "schluessel_gesetzt": bool(m.get("schluessel"))}
           for m in e["mcp"]]
    return {**e, "mcp": mcp, "fassung": f, "ki_url": ki["url"],
            "modelle": [{"id": m["id"], "titel": m["titel"]} for m in ki["modelle"]],
            "ki_standard": ki["standard"], "prompt_warnung_tokens": PROMPT_WARNUNG_TOKENS,
            "gruppen_namen": {str(g.id): g.name for g in db.query(Group).all()}}
