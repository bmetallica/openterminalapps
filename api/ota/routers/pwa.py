"""Anwendungen als Verknuepfung auf dem Desktop.

Ein Progressive Web App-Manifest sagt dem Browser, was passieren soll, wenn
jemand die Seite „installiert": eigenes Fenster ohne Adressleiste, eigener
Name, eigenes Symbol. Damit bekommt jede Anwendung im Arbeitsplatz eine
Verknuepfung, die sich anfuehlt wie ein lokales Programm.

Das Manifest wird erzeugt und nicht abgelegt: Es haengt an Vorlage und
Anwendung, und beides ist zur Bauzeit nicht bekannt.

**Ohne Anmeldung erreichbar**, und zwar mit Absicht. Der Browser holt Manifest
und Symbol beim Installieren teils ohne Zugangsdaten; eine geschuetzte Datei
liesse die Installation kommentarlos scheitern. Preisgegeben wird dabei nur,
wie eine Anwendung heisst — und der Startpunkt fuehrt auf die Anmeldung, wenn
niemand angemeldet ist.
"""

from __future__ import annotations

import html
import json
import re

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..db import get_db
from ..models import Template, TemplateApp

router = APIRouter(prefix="/api/pwa", tags=["pwa"])

SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

# Die Farben der Oberflaeche. Sie stehen hier ein zweites Mal, weil das
# Manifest sie braucht, bevor irgendein Stylesheet geladen ist — der Browser
# malt damit die Startflaeche, waehrend die Anwendung noch kommt.
GROUND = "#0B1315"
BONE = "#EADFCB"


def _lookup(db: DbSession, template: str, app: str | None) -> tuple[str, str]:
    """Name und Symbol fuer die Verknuepfung."""
    if not SLUG.match(template):
        return "OpenTerminalApps", "▣"

    tpl = db.scalar(select(Template).where(Template.slug == template))
    if tpl is None:
        return "OpenTerminalApps", "▣"

    if app and SLUG.match(app):
        entry = db.scalar(
            select(TemplateApp).where(
                TemplateApp.template_id == tpl.id, TemplateApp.slug == app
            )
        )
        if entry is not None:
            return entry.name, entry.icon or "▢"

    return tpl.friendly_name, tpl.icon or "▣"


@router.get("/manifest.webmanifest")
def manifest(
    template: str = Query(...),
    app: str | None = Query(default=None),
    db: DbSession = Depends(get_db),
) -> Response:
    name, _icon = _lookup(db, template, app)
    start = f"/launch/{template}" + (f"/{app}" if app else "")
    icon = f"/api/pwa/icon.svg?template={template}" + (f"&app={app}" if app else "")

    body = {
        "name": f"{name} · OTA",
        "short_name": name[:12],
        "start_url": start,
        "scope": "/",
        # "standalone": eigenes Fenster ohne Adressleiste. Genau das macht den
        # Unterschied zwischen "Lesezeichen" und "sieht aus wie ein Programm".
        "display": "standalone",
        "background_color": GROUND,
        "theme_color": GROUND,
        "orientation": "any",
        "icons": [
            {"src": icon, "sizes": "any", "type": "image/svg+xml", "purpose": "any"},
            {"src": icon, "sizes": "any", "type": "image/svg+xml", "purpose": "maskable"},
        ],
    }
    return Response(
        content=json.dumps(body, ensure_ascii=False),
        media_type="application/manifest+json",
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/icon.svg")
def icon(
    template: str = Query(...),
    app: str | None = Query(default=None),
    db: DbSession = Depends(get_db),
) -> Response:
    _name, glyph = _lookup(db, template, app)
    # Maskierung, weil das Zeichen aus der Datenbank kommt und hier in ein
    # Dokument geschrieben wird, das der Browser aufmacht.
    safe = html.escape(glyph, quote=True)
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">'
        f'<rect width="512" height="512" rx="96" fill="{GROUND}"/>'
        f'<text x="256" y="256" font-size="248" fill="{BONE}" text-anchor="middle"'
        ' dominant-baseline="central"'
        ' font-family="Archivo, Segoe UI Symbol, Noto Sans Symbols 2, sans-serif">'
        f'{safe}</text></svg>'
    )
    return Response(content=svg, media_type="image/svg+xml",
                    headers={"Cache-Control": "public, max-age=3600"})
