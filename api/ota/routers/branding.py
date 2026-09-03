"""Das Gesicht der Anlage — Name, Farbe, Zeichen.

**Wozu.** OTA steht in einem Unternehmen und heisst dort selten
„OpenTerminalApps". Wer die Anlage aufmacht, soll sein eigenes Zeichen sehen;
das kostet nichts und entscheidet, ob sich etwas nach „unser Werkzeug" anfuehlt
oder nach fremder Software.

**Warum in der Datenbank und nicht als Datei.** Ein Bild auf der Platte
braeuchte ein weiteres Verzeichnis, einen weiteren Einhaengepunkt und einen
weiteren Eintrag in der Sicherung — und faellt genau dann auf, wenn nach einer
Wiederherstellung das Zeichen fehlt. In der Datenbank ist es ohne Zutun
mitgesichert und mitzurueckgespielt. Ein Zeichen ist ein paar Kilobyte; das
traegt eine JSONB-Spalte ohne Federlesens.

**Ohne Anmeldung lesbar**, und zwar mit Absicht: Die Anmeldemaske selbst
braucht Name, Farbe und Zeichen, bevor irgendjemand angemeldet ist. Preis-
gegeben wird damit, wie die Anlage heisst — und das steht ohnehin auf dem
Bildschirm, den jeder Besucher sieht.
"""

from __future__ import annotations

import base64
import hashlib
import re

from fastapi import (
    APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status,
)
from sqlalchemy.orm import Session as DbSession

from .. import audit, settings_store
from ..db import get_db
from ..deps import require_permission
from ..models import User
from ..schemas import BrandingIn, BrandingOut

router = APIRouter(prefix="/api/branding", tags=["branding"])

manage = require_permission("settings.manage")

FARBE = re.compile(r"^#[0-9A-Fa-f]{6}$")

# Was als Zeichen durchgeht. SVG ist dabei, weil ein Firmenlogo fast immer als
# SVG vorliegt und alles andere beim Skalieren ausfranst.
TYPEN = frozenset({"image/svg+xml", "image/png", "image/webp", "image/jpeg"})

# 512 KB. Ein Logo, das groesser ist, ist kein Logo, sondern ein Foto — und
# es wuerde bei jedem Aufruf der Anmeldemaske mitgeladen.
MAX = 512 * 1024

# Was in einem SVG nichts zu suchen hat. Ein Zeichen besteht aus Formen; alles
# hier drin ist Verhalten, und Verhalten laeuft auf der Herkunft der Anlage.
#
# Geprueft wird, nicht entfernt: Ein Filter, der Gefaehrliches herausschneidet,
# ist ein Wettlauf gegen jede neue Schreibweise. Eine Ablehnung mit klarer
# Begruendung ist ehrlicher — und wer sein Firmenlogo als Bild braucht,
# bekommt es auch ohne Skript exportiert.
SVG_VERBOTEN = (
    (b"<script", "ein <script>-Element"),
    (b"<foreignobject", "ein <foreignObject>-Element"),
    (b"javascript:", "einen javascript:-Verweis"),
    (b"<!entity", "eine Entity-Deklaration"),
    (b"<iframe", "ein <iframe>-Element"),
)


def _svg_pruefen(roh: bytes) -> None:
    """Ein Zeichen darf Formen enthalten und sonst nichts."""
    klein = roh.lower()
    for muster, was in SVG_VERBOTEN:
        if muster in klein:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Dieses SVG enthält {was}. Ein Zeichen soll nur zeichnen — "
                "bitte ohne Skript exportieren oder ein PNG nehmen.")
    # Ereignisbehandler heissen alle `on…` und stehen als Attribut da. Der
    # Vergleich laeuft ueber die Schreibweise mit Gleichheitszeichen, damit
    # `font-family="Monaco"` nicht als Treffer durchgeht.
    for behandler in (b"onload=", b"onclick=", b"onerror=", b"onmouseover=",
                      b"onbegin=", b"onend=", b"onrepeat=", b"onfocusin="):
        if behandler in klein.replace(b" =", b"="):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Dieses SVG enthält einen Ereignisbehandler "
                f"({behandler.decode().rstrip('=')}). Ein Zeichen soll nur "
                "zeichnen — bitte ohne exportieren oder ein PNG nehmen.")


def _daten(db: DbSession) -> dict:
    return {
        "name": settings_store.get(db, settings_store.BRAND_NAME),
        "accent": settings_store.get(db, settings_store.BRAND_ACCENT),
        "logo": settings_store.get(db, settings_store.BRAND_LOGO),
    }


def _aus(db: DbSession) -> BrandingOut:
    d = _daten(db)
    logo = d["logo"] or {}
    return BrandingOut(
        name=d["name"],
        accent=d["accent"],
        # Die Kennung im Pfad ist der Fingerabdruck des Bildes. Ohne ihn zeigte
        # jeder Browser nach einem Wechsel noch tagelang das alte Zeichen — das
        # Bild darf lange zwischengespeichert werden, sein Name aendert sich.
        logo_url=f"/api/branding/logo?v={logo['etag']}" if logo else None,
        has_logo=bool(logo),
    )


@router.get("")
def read(db: DbSession = Depends(get_db)) -> BrandingOut:
    return _aus(db)


@router.get("/logo")
def logo(db: DbSession = Depends(get_db)) -> Response:
    gespeichert = settings_store.get(db, settings_store.BRAND_LOGO)
    if not gespeichert:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kein eigenes Zeichen hinterlegt.")
    roh = base64.b64decode(gespeichert["b64"])
    return Response(
        roh,
        media_type=gespeichert["mime"],
        headers={
            # Ein Jahr, denn der Pfad traegt den Fingerabdruck; ein neues Bild
            # ist eine neue Adresse.
            "Cache-Control": "public, max-age=31536000, immutable",
            "ETag": f'"{gespeichert["etag"]}"',
            "X-Content-Type-Options": "nosniff",
            # Ein SVG ist ein Dokument und darf Skript enthalten. Wer es direkt
            # aufruft, bekaeme es auf der Herkunft der Anlage ausgefuehrt.
            #
            # Hier stand deshalb erst eine eigene, strenge Content-Security-
            # Policy an dieser Antwort. **Sie kommt nie an**: Traefik setzt den
            # Kopf fuer alle Antworten und ueberschreibt ihn (nachgemessen am
            # 2026-09-03, `deploy/traefik/dynamic/middlewares.yml`). Ein
            # Schutz, den man nicht nachprueft, ist keiner.
            #
            # Die Pruefung sitzt deshalb beim Hochladen (`_svg_pruefen`), wo
            # sie niemand ueberschreiben kann, und dazu diese Zeile: Wer die
            # Adresse direkt aufruft, laedt die Datei herunter statt sie
            # auszufuehren. Als `<img src=…>` eingebunden — der einzige Weg,
            # auf dem OTA das Zeichen benutzt — stoert sie nicht.
            "Content-Disposition": 'attachment; filename="zeichen"',
        },
    )


@router.put("", dependencies=[Depends(manage)])
def write(body: BrandingIn, request: Request,
          db: DbSession = Depends(get_db),
          actor: User = Depends(manage)) -> BrandingOut:
    if body.name is not None:
        name = body.name.strip()
        if not 1 <= len(name) <= 48:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "Ein Name zwischen 1 und 48 Zeichen, bitte.")
        settings_store.put(db, settings_store.BRAND_NAME, name)

    if body.accent is not None:
        if not FARBE.match(body.accent):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"„{body.accent}“ ist keine Farbe. Erwartet wird #RRGGBB.")
        settings_store.put(db, settings_store.BRAND_ACCENT, body.accent.upper())

    audit.record(db, "branding.updated", actor=actor, object_type="branding",
                 object_id="global", request=request,
                 name=body.name, accent=body.accent)
    db.commit()
    return _aus(db)


@router.post("/logo", dependencies=[Depends(manage)])
async def upload(request: Request,
                 datei: UploadFile = File(...),
                 db: DbSession = Depends(get_db),
                 actor: User = Depends(manage)) -> BrandingOut:
    roh = await datei.read()
    if not roh:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Die Datei ist leer.")
    if len(roh) > MAX:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"Das Zeichen darf höchstens {MAX // 1024} KB gross sein — "
            f"diese Datei hat {len(roh) // 1024} KB.")

    mime = (datei.content_type or "").split(";")[0].strip().lower()
    # Dem gemeldeten Typ nicht blind glauben: Er kommt vom Browser. Bei den
    # Bildformaten entscheidet die Signatur, bei SVG der Anfang des Textes.
    if roh[:8] == b"\x89PNG\r\n\x1a\n":
        mime = "image/png"
    elif roh[:3] == b"\xff\xd8\xff":
        mime = "image/jpeg"
    elif roh[:4] == b"RIFF" and roh[8:12] == b"WEBP":
        mime = "image/webp"
    elif b"<svg" in roh[:1024].lower():
        mime = "image/svg+xml"
    if mime not in TYPEN:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "Als Zeichen gehen SVG, PNG, WebP und JPEG.")
    if mime == "image/svg+xml":
        _svg_pruefen(roh)

    settings_store.put(db, settings_store.BRAND_LOGO, {
        "mime": mime,
        "b64": base64.b64encode(roh).decode(),
        "etag": hashlib.sha256(roh).hexdigest()[:16],
    })
    audit.record(db, "branding.logo_set", actor=actor, object_type="branding",
                 object_id="logo", request=request, mime=mime, bytes=len(roh))
    db.commit()
    return _aus(db)


@router.delete("/logo", dependencies=[Depends(manage)])
def logo_weg(request: Request, db: DbSession = Depends(get_db),
             actor: User = Depends(manage)) -> BrandingOut:
    settings_store.put(db, settings_store.BRAND_LOGO, None)
    audit.record(db, "branding.logo_cleared", actor=actor, object_type="branding",
                 object_id="logo", request=request)
    db.commit()
    return _aus(db)
