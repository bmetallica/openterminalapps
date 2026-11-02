"""opencode im Arbeitsplatz (Handbuch Kapitel 38).

Die API sagt, **was** gelten soll (api/ota/opencode.py): die Fassung des
Pakets ota-opencode, die verwaltete Konfiguration, den Prompt-Zusatz, den
Schlüssel des KI-Servers und die Tokens der Erweiterungen. Der Agent setzt
es um, bei jedem Start und jedem Fortsetzen:

1. **Dateien** — sofort, vor allem anderen:
   `/etc/opencode/opencode.jsonc` (opencodes verwaltete Konfiguration, mit
   OTAs Marke in der ersten Zeile), `/etc/opencode/ota-anweisungen.md`,
   `/etc/opencode/ota-ki-schluessel`, `/etc/ota/erweiterungen/<slug>/token`
   und in `/etc/hosts` der Name `ota-erweiterungen` → Traefik im eigenen
   Sitzungsnetz. Eine verwaltete Konfiguration ohne OTAs Marke gehört dem
   Image; dann schreibt OTA keine und meldet es.
2. **Paket** — im Hintergrund, nur wenn die Fassung abweicht, aus der
   eigenen Paketquelle (wie IDE-AI: ohne Weg ins Netz).
3. **Übernehmen**, was jemand selbst installiert hat (Installationsskript,
   npm, Bun): Die Datei wird zu `*.vor-ota` und an ihrer Stelle steht ein
   kleines Skript, das /usr/bin/opencode startet — sonst liefe eine andere
   Fassung, für die OTAs Plugin nicht geprüft ist. Gelöscht wird nichts.

Hat der Mensch in `~/.config/opencode/` selbst ein Standardmodell gesetzt,
lässt OTA `model`/`small_model` weg: Die verwaltete Konfiguration hat
Vorrang und überschriebe sonst seine Wahl.

Leere Angaben heißen: opencode ist aus oder nicht für diesen Menschen. Dann
verschwinden OTAs Dateien; Paket und übernommene Verweise bleiben.
"""
from __future__ import annotations

import io
import json
import logging
import re
import tarfile
import threading
import urllib.error
from typing import Any, Callable

from . import ide_ai

log = logging.getLogger("otaagent.opencode")

MARKE = "// Verwaltet von OTA (opencode)."
PAKET = "ota-opencode"
SLUG_OK = re.compile(r"[a-z][a-z0-9]{1,30}")

_laufend: set[str] = set()
_sperre = threading.Lock()

# $1 Zuhause, $2 Adresse von Traefik im Sitzungsnetz (oder leer), $3 "an"/"aus".
# Auf stdin ein tar mit den Dateien (nur bei "an").
_DATEIEN = r"""
H="$1"; IP="$2"; WAS="$3"; M='// Verwaltet von OTA (opencode).'
D=/etc/opencode
ours() { [ -f "$1" ] && head -1 "$1" | grep -qF "$M"; }
if [ -w /etc/hosts ]; then
  grep -v ' # ota-erweiterungen$' /etc/hosts > /tmp/.ota-hosts || true
  [ "$WAS" = an ] && [ -n "$IP" ] && echo "$IP ota-erweiterungen # ota-erweiterungen" >> /tmp/.ota-hosts
  cat /tmp/.ota-hosts > /etc/hosts; rm -f /tmp/.ota-hosts
fi
if [ "$WAS" != an ]; then
  ours "$D/opencode.jsonc" && rm -f "$D/opencode.jsonc" && echo "konfig-weg"
  rm -f "$D/ota-anweisungen.md" "$D/ota-ki-schluessel"
  rm -rf /etc/ota/erweiterungen "$D/ota-mcp"
  rmdir "$D" 2>/dev/null || true
  exit 0
fi
T=$(mktemp -d)
tar -x -C "$T" || { rm -rf "$T"; echo "tar-fehler"; exit 1; }
mkdir -p "$D" /etc/ota; chmod 755 "$D"
fremd=""
for f in "$D/opencode.json" "$D/opencode.jsonc"; do
  [ -f "$f" ] && ! ours "$f" && fremd="$f"
done
if [ -n "$fremd" ]; then
  echo "konfig-fremd: $fremd"
else
  install -m 0644 "$T/opencode.jsonc" "$D/opencode.jsonc.ota" && mv "$D/opencode.jsonc.ota" "$D/opencode.jsonc"
  echo "konfig-gesetzt"
fi
install -m 0644 "$T/ota-anweisungen.md" "$D/ota-anweisungen.md"
if [ -s "$T/ota-ki-schluessel" ]; then install -m 0644 "$T/ota-ki-schluessel" "$D/ota-ki-schluessel"
else rm -f "$D/ota-ki-schluessel"; fi
# Die Schlüssel der weiteren MCP-Server (Kapitel 38).
rm -rf "$D/ota-mcp"
if [ -d "$T/ota-mcp" ]; then
  cp -r "$T/ota-mcp" "$D/ota-mcp"; chmod 755 "$D/ota-mcp"; chmod 644 "$D/ota-mcp"/*
fi
rm -rf /etc/ota/erweiterungen.neu
if [ -d "$T/erweiterungen" ]; then
  cp -r "$T/erweiterungen" /etc/ota/erweiterungen.neu
  find /etc/ota/erweiterungen.neu -type d -exec chmod 755 {} +
  find /etc/ota/erweiterungen.neu -type f -exec chmod 644 {} +
fi
rm -rf /etc/ota/erweiterungen
[ -d /etc/ota/erweiterungen.neu ] && mv /etc/ota/erweiterungen.neu /etc/ota/erweiterungen
rm -rf "$T"
exit 0
"""

# $1 Zuhause. Selbst installiertes opencode auf OTAs Fassung umlenken.
#
# **Ein kleines Skript, kein Symlink.** Ein Symlink auf /usr/bin/opencode
# hiesse: Wer opencode später neu installiert (das Installationsskript
# schreibt mit curl -o an diese Stelle), überschriebe durch den Verweis
# hindurch OTAs Paketdatei — gemessen im Root-Arbeitsplatz, wo das als root
# geht. Das Skript wird dabei nur selbst ersetzt, und beim nächsten Start
# übernimmt OTA wieder.
_UEBERNEHMEN = r"""
H="$1"; Z=/usr/bin/opencode; M='# ota-opencode: Verweis auf OTAs Fassung'
[ -x "$Z" ] || exit 0
B=$(stat -c %u:%g "$H" 2>/dev/null || echo 0:0)
for b in "$H/.opencode/bin/opencode" "$H/.local/bin/opencode" "$H/.bun/bin/opencode" \
         "$H/.npm-global/bin/opencode" /usr/local/bin/opencode /root/.opencode/bin/opencode; do
  [ -e "$b" ] || [ -L "$b" ] || continue
  [ -f "$b" ] && [ ! -L "$b" ] && sed -n 2p "$b" 2>/dev/null | grep -qF "$M" && continue
  mv -f "$b" "$b.vor-ota" || continue
  printf '#!/bin/sh\n%s (Handbuch Kapitel 38). Das Original: %s.vor-ota\nexec %s "$@"\n' "$M" "$b" "$Z" > "$b"
  chmod 755 "$b"
  echo "uebernommen: $b"
  case "$b" in "$H"/*) chown -h "$B" "$b" "$b.vor-ota" 2>/dev/null ;; esac
done
exit 0
"""

# Was es im Container gibt: dpkg? welche Fassung?
_ERKUNDEN = r"""
command -v dpkg >/dev/null 2>&1 || { echo "kein-dpkg"; exit 0; }
echo "fassung $(dpkg-query -W -f='${Version}' ota-opencode 2>/dev/null)"
"""

# Die eigene Konfiguration des Menschen, um zu sehen, ob er ein Modell setzt.
_EIGENE = r"""
for f in "$1/.config/opencode/opencode.json" "$1/.config/opencode/opencode.jsonc" "$1/.config/opencode/config.json"; do
  [ -f "$f" ] && { echo "=== $f"; head -c 200000 "$f"; echo; }
done
exit 0
"""


def _ohne_kommentare(text: str) -> str:
    """JSONC → JSON: Kommentare und Kommas vor schliessenden Klammern weg,
    ohne in Zeichenketten hineinzuschneiden."""
    raus, i, n, in_str = [], 0, len(text), False
    while i < n:
        c = text[i]
        if in_str:
            raus.append(c)
            if c == "\\" and i + 1 < n:
                raus.append(text[i + 1])
                i += 1
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
            raus.append(c)
        elif text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
            continue
        elif text.startswith("/*", i):
            ende = text.find("*/", i + 2)
            i = n if ende < 0 else ende + 2
            continue
        else:
            raus.append(c)
        i += 1
    return re.sub(r",(\s*[}\]])", r"\1", "".join(raus))


def _setzt_modell(ausgabe: str) -> bool:
    for teil in ausgabe.split("=== ")[1:]:
        _, _, inhalt = teil.partition("\n")
        try:
            d = json.loads(_ohne_kommentare(inhalt))
        except ValueError:
            continue
        if isinstance(d, dict) and d.get("model"):
            return True
    return False


def _konfig_anpassen(konfig: str, eigenes_modell: bool) -> str:
    if not eigenes_modell:
        return konfig
    kopf = [z for z in konfig.splitlines() if z.startswith("//")]
    try:
        d = json.loads(_ohne_kommentare(konfig))
    except ValueError:
        return konfig
    d.pop("model", None)
    d.pop("small_model", None)
    return "\n".join(kopf + ["// Standardmodell: wie in ~/.config/opencode eingestellt."]) + "\n" + \
        json.dumps(d, ensure_ascii=False, indent=2) + "\n"


def _tar(dateien: dict[str, str]) -> bytes:
    puffer = io.BytesIO()
    with tarfile.open(fileobj=puffer, mode="w") as tar:
        for name, inhalt in dateien.items():
            daten = inhalt.encode("utf-8")
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(daten), 0o644
            tar.addfile(info, io.BytesIO(daten))
    return puffer.getvalue()


def _mit_eingabe(container, cmd: list[str], eingabe: bytes) -> tuple[int, str]:
    """Wie run_as_root, aber mit Daten auf stdin: Tokens und Schlüssel
    gehören nicht in die Befehlszeile (die steht in `ps`)."""
    api = container.client.api
    res = api.exec_create(container.id, cmd, user="0", stdin=True)
    sock = api.exec_start(res["Id"], socket=True)
    roh = getattr(sock, "_sock", sock)
    try:
        roh.sendall(eingabe)
        roh.shutdown(1)
        aus = b""
        while (stueck := roh.recv(65536)):
            aus += stueck
    finally:
        roh.close()
    return int(api.exec_inspect(res["Id"]).get("ExitCode") or 0), _entmischen(aus)


def _entmischen(roh: bytes) -> str:
    """Ohne TTY setzt Docker vor jeden Block einen Kopf aus 8 Bytes: Strom,
    drei Nullen, Länge (big endian)."""
    raus, i = bytearray(), 0
    while i + 8 <= len(roh) and roh[i] in (0, 1, 2) and roh[i + 1:i + 4] == b"\0\0\0":
        laenge = int.from_bytes(roh[i + 4:i + 8], "big")
        raus += roh[i + 8:i + 8 + laenge]
        i += 8 + laenge
    if i < len(roh):
        raus += roh[i:]
    return raus.decode("utf-8", "replace")


def _paket(container, soll: str, run_as_root: Callable, erzwingen: bool = False) -> bool:
    """True, wenn ota-opencode neu installiert oder angehoben wurde."""
    if not soll or not ide_ai.FASSUNG_OK.fullmatch(soll):
        return False
    _, out = run_as_root(container, ["sh", "-c", _ERKUNDEN])
    if "kein-dpkg" in out:
        log.info("opencode in %s: kein dpkg — nichts installiert", container.name)
        return False
    ist = (out.split("fassung", 1)[1].strip().split() or [""])[0] if "fassung" in out else ""
    if ist == soll and not erzwingen:
        return False
    if ist and not erzwingen:
        c, _ = run_as_root(container, ["dpkg", "--compare-versions", ist, "gt", soll])
        if c == 0:
            return False
    try:
        datei = ide_ai._hinein(container, ide_ai._datei(PAKET, soll))
    except (urllib.error.URLError, OSError) as exc:
        log.warning("opencode in %s: %s %s nicht geholt: %s", container.name, PAKET, soll, exc)
        return False
    c, aus = ide_ai.dpkg_installieren(container, datei, run_as_root)
    if c != 0:
        log.warning("opencode in %s: %s nicht installiert: %s", container.name, PAKET, aus.strip()[-300:])
        return False
    log.info("opencode in %s: %s %s -> %s", container.name, PAKET, ist or "neu", soll)
    return True


def _uebernehmen(container, heim: str, run_as_root: Callable) -> list[str]:
    _, out = run_as_root(container, ["sh", "-c", _UEBERNEHMEN, "sh", heim])
    pfade = [z.split(": ", 1)[1] for z in out.splitlines() if z.startswith("uebernommen: ")]
    for p in pfade:
        log.info("opencode in %s: eigene Installation übernommen (%s, Original: %s.vor-ota)",
                 container.name, p, p)
    return pfade


def _dateien(container, angaben: dict[str, Any], heim: str, traefik_ip: str,
             run_as_root: Callable) -> str:
    konfig = str(angaben.get("config") or "")
    if not konfig:
        _, out = run_as_root(container, ["sh", "-c", _DATEIEN, "sh", heim, "", "aus"])
        return out
    _, eigene = run_as_root(container, ["sh", "-c", _EIGENE, "sh", heim])
    dateien = {"opencode.jsonc": _konfig_anpassen(konfig, _setzt_modell(eigene)),
               "ota-anweisungen.md": str(angaben.get("anweisungen") or ""),
               "ota-ki-schluessel": str(angaben.get("ki_schluessel") or "")}
    for name, schluessel in (angaben.get("mcp_schluessel") or {}).items():
        if re.fullmatch(r"[a-z][a-z0-9_-]{1,30}", str(name)) and schluessel:
            dateien[f"ota-mcp/{name}"] = str(schluessel)
    for e in angaben.get("erweiterungen") or []:
        slug, token = str(e.get("slug") or ""), str(e.get("token") or "")
        if SLUG_OK.fullmatch(slug) and token:
            dateien[f"erweiterungen/{slug}/token"] = token
    _, out = _mit_eingabe(container, ["sh", "-c", _DATEIEN, "sh", heim, traefik_ip, "an"], _tar(dateien))
    return out


def im_container(container, angaben: dict[str, Any], heim: str, traefik_ip: str,
                 run_as_root: Callable) -> None:
    """Dateien sofort, Paket und Übernahme im Hintergrund. Scheitert etwas,
    startet der Arbeitsplatz trotzdem — dann eben ohne opencode von OTA."""
    try:
        out = _dateien(container, angaben, heim, traefik_ip, run_as_root)
        if "konfig-fremd" in out:
            log.warning("opencode in %s: %s gehört dem Image — OTA schreibt keine verwaltete "
                        "Konfiguration", container.name, out.split("konfig-fremd: ", 1)[1].split()[0])
        elif "konfig-gesetzt" in out:
            log.info("opencode in %s: Konfiguration gesetzt (%d Erweiterungen)", container.name,
                     len(angaben.get("erweiterungen") or []))
    except Exception as exc:  # noqa: BLE001 — darf keinen Start kippen
        log.warning("opencode in %s nicht eingerichtet: %s", container.name, exc)
        return
    if not angaben.get("config"):
        return

    def hintergrund() -> None:
        try:
            _paket(container, str(angaben.get("fassung") or ""), run_as_root)
            _uebernehmen(container, heim, run_as_root)
        except Exception as exc:  # noqa: BLE001 — Container kann inzwischen weg sein
            log.warning("opencode in %s: Paket nicht eingerichtet: %s", container.name, exc)
        finally:
            with _sperre:
                _laufend.discard(container.id)

    with _sperre:
        if container.id in _laufend:
            return
        _laufend.add(container.id)
    threading.Thread(target=hintergrund, name=f"opencode-{container.name}", daemon=True).start()
