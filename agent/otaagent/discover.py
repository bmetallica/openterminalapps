"""Findet heraus, welche Anwendungen in einem Image installiert sind.

Der Sinn: Nach dem Einbauen von Firefox oder GIMP soll niemand nachschlagen
muessen, wie der Startbefehl heisst, wo die Binaerdatei liegt und wie das
Programm in der Oberflaeche heissen soll. Das steht alles schon im Image —
in den `.desktop`-Dateien, die jedes Linux-Paket mitbringt, damit ein
Startmenue es anzeigen kann. OTA liest genau die.

Gelesen wird in einem kurzlebigen Container aus dem Image selbst. Der
Alternativweg, die Image-Schichten von aussen auszupacken, waere schneller,
aber er muesste Overlay-Schichten, Whiteouts und Symlinks nachbauen — fuer ein
paar Textdateien ein schlechtes Geschaeft.
"""

from __future__ import annotations

import posixpath
import re
import shlex

import docker
from docker.errors import APIError, ImageNotFound

# Auslesen, ohne irgendetwas im Image zu starten: Der Einstiegspunkt wird
# ueberschrieben, das Netz abgeschaltet, der Container danach entfernt.
SCAN = r"""
# Braucht dieses Programm --no-sandbox?
#
# Electron- und Chromium-Anwendungen legen ihre Sandbox ueber
# PID-Namespaces an. In einem Container ohne die noetigen Faehigkeiten
# scheitert das:
#
#   Failed to move to new namespace: ... errno = Operation not permitted
#   FATAL: Check failed: . : Invalid argument (22)
#
# Das Ergebnis ist ein schwarzer Bildschirm ohne Fehlermeldung im Stream.
# Die .desktop-Datei sagt darueber nichts — sie ist fuer einen normalen
# Desktop geschrieben. OTA weiss aber, dass es Container betreibt.
#
# Erkannt wird es an der Datei chrome-sandbox neben dem Programm: Die bringt
# jede Electron- und Chromium-Anwendung mit, und sonst niemand.
needs_no_sandbox() {
  bin=$(command -v "$1" 2>/dev/null) || return 1
  real=$(readlink -f "$bin" 2>/dev/null || echo "$bin")
  [ -e "$(dirname "$real")/chrome-sandbox" ] && return 0

  # Viele Pakete legen unter /usr/bin nur ein Startskript ab; das eigentliche
  # Programm liegt woanders. Google Chrome macht genau das — und weil die
  # Datei kein Symlink ist, fuehrt readlink nicht dorthin. Also die Pfade
  # durchsehen, die das Skript selbst nennt.
  head -c 2 "$real" 2>/dev/null | grep -q '#!' || return 1
  for p in $(grep -oE '/[A-Za-z0-9_./-]{6,}' "$real" 2>/dev/null | sort -u | head -40); do
    [ -e "$(dirname "$p")/chrome-sandbox" ] && return 0
  done
  return 1
}

for dir in /usr/share/applications /usr/local/share/applications /var/lib/flatpak/exports/share/applications; do
  [ -d "$dir" ] || continue
  for f in "$dir"/*.desktop; do
    [ -f "$f" ] || continue
    body=$(awk '/^\[Desktop Entry\]/{on=1;next} /^\[/{on=0} on' "$f")
    field() { printf '%s\n' "$body" | grep -m1 "^$1=" | cut -d= -f2-; }
    exec_line=$(field Exec)
    first=$(printf '%s' "$exec_line" | awk '{print $1}')
    sandbox=no
    needs_no_sandbox "$first" && sandbox=yes
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
      "$(basename "$f" .desktop)" \
      "$(field Name)" \
      "$exec_line" \
      "$(field NoDisplay)" \
      "$(field Terminal)" \
      "$(field Categories)" \
      "$sandbox"
  done
done
"""

# Platzhalter, die der Freedesktop-Standard in Exec erlaubt. Sie stehen fuer
# Dateien oder URLs, die beim Start uebergeben werden — beim blossen Oeffnen
# der Anwendung ist keiner davon gemeint.
FIELD_CODES = re.compile(r"%[fFuUdDnNickvm]")

# Kategorie -> Zeichen in der Oberflaeche. Die Zuordnung ist grob und soll es
# sein: Sie erspart das Aussuchen im Normalfall, ohne es zu ersetzen.
GLYPHS: tuple[tuple[str, str], ...] = (
    ("TerminalEmulator", "▮"),
    ("WebBrowser", "◎"),
    ("IDE", "⌨"),
    ("Development", "⌨"),
    ("Graphics", "◈"),
    ("AudioVideo", "▶"),
    ("Audio", "▶"),
    ("Video", "▶"),
    ("Office", "▤"),
    ("FileManager", "▦"),
    ("System", "⚙"),
    ("Network", "◍"),
    ("Utility", "▢"),
)

# Was niemand als Anwendung im Arbeitsplatz sehen will: Einstellungsdialoge
# einzelner Komponenten, Protokoll-Handler, Bildschirmschoner.
NOISE = re.compile(
    r"settings|preferences|url-handler|screensaver|autostart|"
    r"^xfce4-(about|accessibility|appearance|mime|notifyd|power|session|"
    r"settings|workspaces|keyboard|mouse|display|panel)",
    re.IGNORECASE,
)

# Startet nicht selbst etwas, sondern reicht an die eingestellte Standard-
# anwendung weiter ("Web Browser" -> was gerade als Browser gilt). Als Eintrag
# im Arbeitsplatz waere das eine Anwendung, die je nach Einstellung etwas
# anderes oeffnet — genau das, was niemand erwartet.
INDIRECT = {"exo-open", "xdg-open", "gio", "kde-open"}


def _glyph(categories: str) -> str:
    parts = [c for c in categories.split(";") if c]
    for key, glyph in GLYPHS:
        if key in parts:
            return glyph
    return "▢"


def _split_exec(raw: str) -> tuple[str, str]:
    """Zerlegt die Exec-Zeile in Befehl und Argumente.

    Die Platzhalter fliegen raus; ein Aufruf mit einem uebrig gebliebenen
    ``%U`` startet in vielen Programmen eine leere Datei statt der Anwendung.
    """
    cleaned = FIELD_CODES.sub("", raw).strip()
    try:
        parts = shlex.split(cleaned)
    except ValueError:
        parts = cleaned.split()
    if not parts:
        return "", ""
    # "env FOO=bar programm" kommt vor; das env-Praefix gehoert zum Befehl.
    return parts[0], " ".join(parts[1:])


def _slug(stem: str, name: str) -> str:
    base = (name or stem).lower()
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    return base[:64] or re.sub(r"[^a-z0-9]+", "-", stem.lower())[:64]


def applications(image_ref: str) -> list[dict[str, object]]:
    """Die startbaren Anwendungen eines Images, in lesbarer Form."""
    client = docker.from_env()
    try:
        client.images.get(image_ref)
    except ImageNotFound:
        raise ValueError(f"Das Image {image_ref} liegt nicht auf diesem Host.") from None

    try:
        raw = client.containers.run(
            image_ref,
            entrypoint=["/bin/bash", "-lc"],
            command=[SCAN],
            remove=True,
            user="root",
            network_disabled=True,
            mem_limit="256m",
            security_opt=["no-new-privileges:true"],
            cap_drop=["ALL"],
        )
    except APIError as exc:
        raise ValueError(f"Das Image liess sich nicht durchsehen: {exc}") from exc

    text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)

    found: dict[str, dict[str, object]] = {}
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) != 7:
            continue
        stem, name, exec_raw, no_display, terminal, categories, sandbox = (
            p.strip() for p in parts
        )
        if not name or not exec_raw:
            continue
        if no_display.lower() == "true":
            continue
        if NOISE.search(stem):
            continue

        cmd, args = _split_exec(exec_raw)
        if not cmd or posixpath.basename(cmd) in INDIRECT:
            continue

        # Ohne diesen Schalter startet eine Electron-Anwendung im Container
        # gar nicht — siehe needs_no_sandbox() im Scan-Skript.
        if sandbox == "yes" and "--no-sandbox" not in args:
            args = f"{args} --no-sandbox".strip()

        slug = _slug(stem, name)
        found.setdefault(slug, {
            "slug": slug,
            "name": name,
            "icon": _glyph(categories),
            "exec_cmd": cmd,
            "exec_args": args,
            "categories": [c for c in categories.split(";") if c],
            # Konsolenprogramme brauchen ein Terminal um sich herum. Sie werden
            # gezeigt, aber nicht vorausgewaehlt — der Arbeitsplatz startet sie
            # sonst auf einem leeren Bildschirm.
            "needs_terminal": terminal.lower() == "true",
            "binary": posixpath.basename(cmd),
        })

    return _dedupe(found)


def _dedupe(found: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    """Ein Programm, ein Eintrag.

    Mehrere .desktop-Dateien koennen auf dieselbe Binaerdatei zeigen. Thunar
    bringt drei mit: den Dateimanager, den Massen-Umbenenner und einen
    Einstellungsdialog. Frueher gewann die alphabetisch erste — und das war
    „Bulk Rename". Der Katalog bekam damit `thunar --bulk-rename` statt
    `thunar`, und wer auf „Dateien" klickte, landete im Umbenenner.

    Es gewinnt deshalb der schlichteste Aufruf: derselbe Befehl mit den
    wenigsten Argumenten ist der, der die Anwendung selbst oeffnet.
    """
    best: dict[str, dict[str, object]] = {}
    for entry in found.values():
        key = str(entry["binary"])
        rival = best.get(key)
        if rival is None or _plainness(entry) < _plainness(rival):
            best[key] = entry
    return sorted(best.values(), key=lambda a: str(a["name"]).lower())


def _plainness(entry: dict[str, object]) -> tuple[int, int]:
    args = str(entry.get("exec_args") or "")
    # --no-sandbox zaehlt nicht mit: Es ist von OTA und nicht vom Paket.
    count = len([a for a in args.split() if a != "--no-sandbox"])
    return (count, len(str(entry.get("slug") or "")))


# ---------------------------------------------------------------------------
# Paketpruefung
# ---------------------------------------------------------------------------

# Ein Build dauert Minuten. Ihn an einem Tippfehler oder an einem
# Debian-Namen auf einem Ubuntu-Image scheitern zu lassen, ist vermeidbar —
# die Frage "gibt es dieses Paket ueberhaupt" beantwortet apt in Sekunden.
CHECK = r"""
apt-get update >/dev/null 2>&1
for pkg in @NAMES@; do
  cand=$(apt-cache policy "$pkg" 2>/dev/null | awk '/Candidate:/{print $2; exit}')
  desc=$(apt-cache show "$pkg" 2>/dev/null | awk '/^Description(-en)?:/{print; exit}')
  if [ -z "$cand" ] || [ "$cand" = "(none)" ]; then
    near=$(apt-cache search --names-only "$pkg" 2>/dev/null | head -4 | cut -d' ' -f1 | tr '\n' ',')
    printf '%s\tno\t\t\t%s\n' "$pkg" "$near"
  else
    printf '%s\tyes\t%s\t%s\t\n' "$pkg" "$cand" "$desc"
  fi
done
"""


def check_packages(image_ref: str, names: list[str]) -> list[dict[str, object]]:
    """Sagt fuer jeden Paketnamen, ob dieses Image ihn kennt.

    Zwei Antworten sind dabei wichtig und beide unbequem:

    * **Gibt es nicht.** Meist ein Debian-Name auf einem Ubuntu-Image
      (`firefox-esr`) oder ein Tippfehler. Dann kommen aehnliche Namen mit.
    * **Gibt es, taugt aber nichts.** Ubuntu 22.04 fuehrt `firefox` nur noch
      als Uebergangspaket, das auf ein Snap zeigt. In einem Container laeuft
      kein Snap; installiert wird dann ein Platzhalter ohne Programm. Das
      sieht im Build wie Erfolg aus und faellt erst dem Nutzer auf.
    """
    if not names:
        return []
    safe = [n for n in names if re.fullmatch(r"[a-z0-9][a-z0-9+.:-]{0,80}", n)]
    if not safe:
        return [{"name": n, "available": False, "candidate": "",
                 "snap_stub": False, "suggestions": []} for n in names]

    client = docker.from_env()
    script = CHECK.replace("@NAMES@", " ".join(shlex.quote(n) for n in safe))
    try:
        raw = client.containers.run(
            image_ref, entrypoint=["/bin/bash", "-lc"], command=[script],
            remove=True, user="root", mem_limit="512m",
        )
    except (APIError, ImageNotFound) as exc:
        raise ValueError(f"Die Pakete liessen sich nicht pruefen: {exc}") from exc

    text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
    out: list[dict[str, object]] = []
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) < 5:
            continue
        name, ok, candidate, desc, near = (p.strip() for p in parts[:5])
        stub = ok == "yes" and "transitional" in desc.lower() and "snap" in desc.lower()
        out.append({
            "name": name,
            "available": ok == "yes" and not stub,
            "candidate": candidate,
            "snap_stub": stub,
            "suggestions": [s for s in near.split(",") if s and s != name][:4],
        })
    return out
