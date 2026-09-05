"""Das Handbuch aus `docs/wiki/` im Programm selbst.

Warum es hier liegt und nicht als statische Dateien beim Webserver: Die
Kapitel richten sich an unterschiedliche Leser. Wer kein Administrator ist,
soll die Betriebs- und Verwaltungskapitel gar nicht erst zu sehen bekommen —
und das ist eine Rechtefrage, also gehoert sie hinter die Anmeldung.

Der Ordner wird per Compose eingehaengt, nicht ins Abbild kopiert. So laesst
sich das Handbuch nachbessern, ohne das Abbild neu zu bauen — dieselbe
Ueberlegung wie bei der nginx-Konfiguration.
"""

from __future__ import annotations

import io
import os
import re
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response, status

from ..deps import current_user
from ..models import User
from ..schemas import HelpChapter, HelpPage

router = APIRouter(prefix="/api/help", tags=["help"])

WIKI_DIR = Path(os.environ.get("OTA_WIKI_DIR", "/app/wiki"))

# Dateiname -> Rubrik. Die Reihenfolge im Handbuch ist die Nummer im Namen,
# die Rubrik entscheidet, wer das Kapitel sieht.
SECTIONS: dict[str, tuple[str, bool]] = {
    # Praefix: (Rubrik, nur fuer Administratoren)
    "01": ("Grundlagen", False),
    "02": ("Grundlagen", True),
    "03": ("Für Anwender", False),
    "04": ("Für Anwender", False),
    "05": ("Für Administratoren", True),
    "06": ("Für Administratoren", True),
    "07": ("Für Administratoren", True),
    "08": ("Für Administratoren", True),
    "09": ("Für Administratoren", True),
    "10": ("Betrieb", True),
    "11": ("Betrieb", True),
    "12": ("Betrieb", True),
    "13": ("Betrieb", False),
    "14": ("Betrieb", True),
    "15": ("Betrieb", True),
    "16": ("Für Administratoren", True),
    "17": ("Für Administratoren", True),
    # Die Kapitel 18 bis 23 sind nach der ersten Fassung dieser Tabelle
    # dazugekommen und landeten bis dahin unter „Weiteres" — sichtbar nur fuer
    # Administratoren, aber in der falschen Rubrik.
    "18": ("Für Administratoren", True),
    "19": ("Für Administratoren", True),
    "20": ("Für Administratoren", True),
    "21": ("Für Administratoren", True),
    "22": ("Für Administratoren", True),
    "23": ("Für Administratoren", True),
}

SLUG_OK = re.compile(r"^[0-9a-z-]+$")


def _title_of(path: Path) -> str:
    """Die erste Ueberschrift der Datei, ohne die Raute."""
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("# "):
                    return line[2:].strip()
    except OSError:
        pass
    return path.stem


def _chapters(user: User) -> list[HelpChapter]:
    if not WIKI_DIR.is_dir():
        return []
    out: list[HelpChapter] = []
    for path in sorted(WIKI_DIR.glob("*.md")):
        if path.name == "README.md":
            continue
        section, admin_only = SECTIONS.get(path.name[:2], ("Weiteres", True))
        if admin_only and not user.is_admin:
            continue
        out.append(HelpChapter(
            slug=path.stem,
            title=_title_of(path),
            section=section,
        ))
    return out


@router.get("", response_model=list[HelpChapter])
def list_chapters(user: User = Depends(current_user)) -> list[HelpChapter]:
    return _chapters(user)


@router.get("/{slug}", response_model=HelpPage)
def read_chapter(slug: str, user: User = Depends(current_user)) -> HelpPage:
    # Der Name kommt aus der Adresse. Ohne diese Pruefung liesse sich mit
    # "../../etc/passwd" alles lesen, was der Prozess lesen darf.
    if not SLUG_OK.match(slug):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kapitel nicht gefunden")

    allowed = {c.slug for c in _chapters(user)}
    if slug not in allowed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kapitel nicht gefunden")

    path = WIKI_DIR / f"{slug}.md"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kapitel nicht gefunden") from None

    return HelpPage(slug=slug, title=_title_of(path), markdown=text)


# --------------------------------------------------------------------------
# Bilder im Handbuch
# --------------------------------------------------------------------------

BILD_OK = re.compile(r"^[0-9a-z-]+\.svg$")


@router.get("/bild/{datei}")
def read_bild(datei: str, user: User = Depends(current_user)) -> Response:
    """Ein Bild aus `docs/wiki/bilder/`.

    Nur SVG, nur aus diesem einen Ordner, und der Name muss aus Kleinbuchstaben,
    Ziffern und Bindestrichen bestehen. Der Name kommt aus der Adresse — ohne
    diese Pruefung liesse sich mit `../../etc/passwd` alles lesen, was der
    Prozess lesen darf. Dieselbe Ueberlegung wie bei den Kapiteln oben.

    **Ohne Rechtefilter**, anders als die Kapitel: Ein Bild ist ohne den Text
    darum herum nichts, und wer den Text nicht sehen darf, bekommt ihn auch
    nicht. Eine zweite Rechteliste, die mit der ersten auseinanderlaeuft, waere
    die groessere Gefahr.
    """
    if not BILD_OK.match(datei):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bild nicht gefunden")

    pfad = WIKI_DIR / "bilder" / datei
    try:
        inhalt = pfad.read_bytes()
    except OSError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bild nicht gefunden") from None

    return Response(
        content=inhalt,
        media_type="image/svg+xml",
        # Die Bilder aendern sich nur mit einer neuen Fassung des Handbuchs.
        headers={"Cache-Control": "public, max-age=3600"},
    )


# --------------------------------------------------------------------------
# Firefox-Erweiterung
# --------------------------------------------------------------------------

EXT_DIR = Path(os.environ.get("OTA_EXTENSION_DIR", "/app/extension"))
EXT_NAME = "ota-zwischenablage-firefox.zip"


@router.get("/extension/firefox")
def firefox_extension(user: User = Depends(current_user)) -> Response:
    """Die Erweiterung als Paket zum Herunterladen.

    Erzeugt statt abgelegt: Das Paket ist ein paar Kilobyte gross, und eine
    Datei, die beim Bauen entsteht, laeuft irgendwann gegenueber dem Quelltext
    daneben. So ist immer drin, was im Ordner liegt.

    Signiert ist es nicht — dafuer braeuchte es Mozilla. Wie es trotzdem
    dauerhaft installiert wird, steht in Kapitel 4 des Handbuchs.
    """
    src = EXT_DIR / "firefox"
    if not src.is_dir():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Die Erweiterung liegt nicht bereit.")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(src.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(src).as_posix())

    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{EXT_NAME}"'},
    )
