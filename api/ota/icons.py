"""Anwendungssymbole aus den Images auf ein brauchbares Mass bringen.

Der Agent liest das Symbol einer Anwendung aus ihrer `.desktop`-Datei und
gibt es als Datenadresse zurück (`agent/otaagent/discover.py`). Was ein Paket
dort mitbringt, ist völlig uneinheitlich: 554 Bytes bei Vim, 42 KB bei GIMP,
**428 KB bei VSCodium**. Ungeprüft weitergereicht läge das so in der Datenbank
und in jeder Antwort des Katalogs — bei sechzehn Anwendungen wäre das ein
halbes Megabyte, das jedes Dashboard mitlädt.

Deshalb wird hier verkleinert: höchstens 128 Pixel Kantenlänge, als PNG. Das
reicht für jede Stelle, an der OTA ein Symbol zeigt (Kachel, Umschalter,
Liste), und macht die Grösse vorhersagbar.

**Warum in der API und nicht im Agent.** Hier wird ein Bild aus einem fremden
Paket dekodiert — Angriffsfläche, wenn auch eine kleine. Der Agent ist der
einzige Dienst mit dem Docker-Socket; fremde Daten gehören dorthin, wo ohnehin
fremde Daten verarbeitet werden (`docs/adr/002-nur-der-agent-fasst-docker-an.md`).

**SVG wird durchgereicht, nicht gerechnet.** Es ist Text, meist wenige
Kilobyte, und beliebig skalierbar — verkleinern würde nichts gewinnen. Es geht
allerdings nur durch, wenn es klein genug ist und keine externen Verweise
enthält; ein SVG, das beim Anzeigen etwas nachlädt, hat im Katalog nichts zu
suchen.
"""

from __future__ import annotations

import base64
import binascii
import io
import logging
import re

log = logging.getLogger("ota.icons")

# Kantenlänge, auf die verkleinert wird. 128 statt 64: Auf einem Bildschirm
# mit doppelter Pixeldichte ist eine 64er-Grafik in einer 64er-Kachel bereits
# unscharf.
MAX_KANTE = 128

# Obergrenze für das, was am Ende gespeichert wird. Ein 128×128-PNG liegt bei
# 5 bis 20 KB; was danach noch grösser ist, ist kein Symbol.
MAX_BYTES = 96 * 1024

DATENADRESSE = re.compile(r"^data:(image/[a-z+]+);base64,([A-Za-z0-9+/=\s]+)$")

# Was ein SVG nicht enthalten darf, wenn es unverändert durchgehen soll.
# Ein Verweis nach draussen macht aus einem Symbol einen Aufruf an einen
# fremden Server — beim Öffnen des Dashboards, für jeden Betrachter.
SVG_VERBOTEN = re.compile(
    rb"<script|\son\w+\s*=|xlink:href\s*=\s*[\"']\s*(?!#)|"
    rb"href\s*=\s*[\"']\s*https?:|url\s*\(\s*[\"']?\s*https?:|<foreignObject",
    re.IGNORECASE,
)


def verkleinern(datenadresse: str) -> str:
    """Nimmt eine Datenadresse und gibt eine kleinere zurück — oder nichts.

    Ein leerer Rückgabewert heisst: unbrauchbar. Die Oberfläche zeigt dann das
    Zeichen, das ohnehin an jeder Anwendung steht. Ein Symbol ist nie ein
    Grund, einen Katalog abzulehnen.
    """
    if not datenadresse:
        return ""

    treffer = DATENADRESSE.match(datenadresse.strip())
    if not treffer:
        return ""
    typ, roh = treffer.group(1), treffer.group(2)

    try:
        daten = base64.b64decode(roh, validate=False)
    except (binascii.Error, ValueError):
        return ""
    if not daten:
        return ""

    if typ == "image/svg+xml":
        if len(daten) > MAX_BYTES or SVG_VERBOTEN.search(daten):
            return ""
        return f"data:image/svg+xml;base64,{base64.b64encode(daten).decode()}"

    try:
        from PIL import Image
    except ImportError:          # pragma: no cover — Pillow steht in den Anforderungen
        log.warning("Pillow fehlt; Symbole werden nicht verkleinert")
        return datenadresse if len(daten) <= MAX_BYTES else ""

    try:
        with Image.open(io.BytesIO(daten)) as bild:
            # Erst laden, dann rechnen: `Image.open` liest nur den Kopf, und
            # ein beschädigtes Bild fällt sonst mitten im Verkleinern auf.
            bild.load()
            bild = bild.convert("RGBA")
            if max(bild.size) > MAX_KANTE:
                bild.thumbnail((MAX_KANTE, MAX_KANTE), Image.LANCZOS)
            puffer = io.BytesIO()
            bild.save(puffer, format="PNG", optimize=True)
    except Exception as exc:      # noqa: BLE001 — jedes kaputte Bild, nicht nur die erwarteten
        log.info("Symbol nicht verwertbar: %s", exc)
        return ""

    klein = puffer.getvalue()
    if len(klein) > MAX_BYTES:
        return ""
    return f"data:image/png;base64,{base64.b64encode(klein).decode()}"
