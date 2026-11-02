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


def konfiguration(e: dict[str, Any], ki: dict[str, Any], angaben: list[dict[str, Any]]) -> str:
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
    return {
        "fassung": fassung(db),
        "config": konfiguration(e, ki, angaben),
        "anweisungen": anweisungen(db, e, user, vorlage, angaben),
        "ki_schluessel": ki["api_key"] or "",
        "erweiterungen": [{"slug": a["slug"], "token": a["token"]} for a in angaben],
    }


def vorschau(db: DbSession, user: User, entwurf: dict[str, Any] | None = None) -> dict[str, Any]:
    """Für die Einstellungen: so sähe es für diesen Menschen aus — auf Wunsch
    mit einem noch nicht gespeicherten Entwurf. Ohne Tokens; die
    Erweiterungen werden nicht gefragt."""
    e = {**einstellungen(db), **{k: v for k, v in (entwurf or {}).items() if k in VORGABEN}}
    _zusatz(str(e["zusatz"] or ""))
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
    return {"berechtigt": berechtigt(db, user, e), "config": konfiguration(e, ki, angaben),
            "anweisungen": anw, "tokens_geschaetzt": len(anw) // 4}


def stand(db: DbSession) -> dict[str, Any]:
    e = einstellungen(db)
    ki = ide_ai.einstellungen(db)
    try:
        f = fassung(db)
    except Exception:  # noqa: BLE001 — Paketquelle nicht erreichbar
        f = ""
    return {**e, "fassung": f, "ki_url": ki["url"],
            "modelle": [{"id": m["id"], "titel": m["titel"]} for m in ki["modelle"]],
            "ki_standard": ki["standard"], "prompt_warnung_tokens": PROMPT_WARNUNG_TOKENS,
            "gruppen_namen": {str(g.id): g.name for g in db.query(Group).all()}}
