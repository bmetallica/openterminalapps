"""Die Wege zu den Erweiterungen in Traefik (Handbuch Kapitel 39).

Die API sagt, welche Erweiterungen an sind (api/ota/erweiterungen.py:
`routen`); der Agent schreibt daraus Traefiks Datei `erweiterungen.yml` —
er ist der einzige mit Schreibrecht auf dessen Verzeichnis. Zwei Wege je
Erweiterung, sonst keiner:

* **Aus den Arbeitsplätzen** auf dem Eingang `erweiterungen` (:8091, nur in
  den Sitzungsnetzen, nie auf dem Host): `ota-erweiterungen/<slug>/<pfad>`
  für genau die Pfade aus dem Manifest, nur aus dem Sitzungsbereich. Der
  Vertrag `/ota/v1` ist von dort nicht erreichbar.
* **Aus dem Browser** auf OTAs Adresse: `/x/<slug>/ansicht/…` hinter
  forwardAuth — die API prüft die Anmeldung und setzt signierte Kopfzeilen.

JSON ist gültiges YAML; Traefik liest die Datei und merkt Änderungen von
selbst.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from . import netz as netz_ops
from .git_dienst import TRAEFIK_DYNAMIC

log = logging.getLogger("otaagent.erweiterungen")

DATEI = os.path.join(TRAEFIK_DYNAMIC, "erweiterungen.yml")
SLUG_OK = re.compile(r"[a-z][a-z0-9]{1,30}")
PFAD_OK = re.compile(r"/[A-Za-z0-9._~/-]{0,200}")
ADRESSE_OK = re.compile(r"http://[A-Za-z0-9.-]{1,120}(:[0-9]{1,5})?")
KOPFZEILEN = ["X-OTA-Nutzer", "X-OTA-Name", "X-OTA-Arbeitsplaetze", "X-OTA-Zeit", "X-OTA-Signatur"]


def _regel_pfade(slug: str, pfade: list[str]) -> str:
    return " || ".join(f"PathPrefix(`/{slug}{p}`)" for p in pfade)


def schreiben(routen: list[dict[str, Any]]) -> dict[str, Any]:
    routers: dict[str, Any] = {}
    middlewares: dict[str, Any] = {}
    services: dict[str, Any] = {}
    geschrieben = []
    for r in routen:
        slug, adresse = str(r.get("slug") or ""), str(r.get("adresse") or "")
        pfade = [p for p in r.get("pfade") or [] if isinstance(p, str) and PFAD_OK.fullmatch(p) and ".." not in p]
        if not SLUG_OK.fullmatch(slug) or not ADRESSE_OK.fullmatch(adresse):
            log.warning("Erweiterung übergangen: %r %r", slug, adresse)
            continue
        services[f"erw-{slug}"] = {"loadBalancer": {"servers": [{"url": adresse}]}}
        if pfade:
            middlewares[f"erw-{slug}-ab"] = {"stripPrefix": {"prefixes": [f"/{slug}"]}}
            routers[f"erw-{slug}-platz"] = {
                "rule": f"Host(`ota-erweiterungen`) && ClientIP(`{netz_ops.POOL}`) && ({_regel_pfade(slug, pfade)})",
                "entryPoints": ["erweiterungen"], "middlewares": [f"erw-{slug}-ab"],
                "service": f"erw-{slug}"}
        if r.get("ansichten"):
            middlewares[f"erw-{slug}-anmeldung"] = {"forwardAuth": {
                "address": f"http://api:8000/api/erweiterungen/{slug}/pruefen",
                "trustForwardHeader": True, "authResponseHeaders": KOPFZEILEN}}
            middlewares[f"erw-{slug}-ansicht-ab"] = {"stripPrefix": {"prefixes": [f"/x/{slug}"]}}
            routers[f"erw-{slug}-ansicht"] = {
                "rule": f"PathPrefix(`/x/{slug}/ansicht/`)", "entryPoints": ["websecure"], "tls": {},
                "priority": 900, "service": f"erw-{slug}",
                "middlewares": [f"erw-{slug}-anmeldung", f"erw-{slug}-ansicht-ab", "ota-headers@file"]}
        geschrieben.append(slug)
    if not services:
        try:
            os.remove(DATEI)
        except FileNotFoundError:
            pass
        return {"erweiterungen": []}
    inhalt = {"http": {"routers": routers, "middlewares": middlewares, "services": services}}
    text = "# ERZEUGT vom Agent aus den Erweiterungen in OTA (Kapitel 39).\n" + json.dumps(inhalt, indent=2) + "\n"
    with open(DATEI + ".neu", "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(DATEI + ".neu", DATEI)
    log.info("Routen der Erweiterungen: %s", ", ".join(geschrieben))
    return {"erweiterungen": geschrieben}
