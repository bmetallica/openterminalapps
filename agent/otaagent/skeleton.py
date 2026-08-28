"""Skeleton-Profile — womit ein Zuhause anfängt.

Ein Skeleton ist ein Verzeichnisbaum je Workspace, der ins Home eines Nutzers
kommt. Zwei Zeitpunkte, und der Unterschied ist der ganze Sinn:

* **Beim ersten Start**, wenn das Zuhause noch leer ist, wird alles kopiert.
  Damit fängt niemand mit einem nackten Desktop an: Editor-Einstellungen,
  ein Firmenzertifikat, eine Vorlage, eine `.bashrc`.
* **Bei jedem Start** werden nur die Pfade kopiert, die der Administrator
  ausdrücklich als *durchgesetzt* markiert hat — und die überschreiben, was
  der Nutzer geändert hat.

Der zweite Fall ist mit Bedacht die Ausnahme. Ein Zuhause gehört dem Menschen,
der darin arbeitet; ihm bei jedem Start Einstellungen zu überschreiben, ist
etwas, das man begründen muss. Für eine Proxy-Konfiguration oder ein
Wurzelzertifikat ist es richtig, für ein Farbschema nicht.

Abgrenzung zum **Startskript** (`start_script`): Das ist der Weg für alles,
was *ausgeführt* werden muss — etwas holen, etwas erzeugen, etwas abfragen.
Das Skeleton ist der Weg für Dateien, die einfach da sein sollen. Wer die Wahl
hat, nimmt das Skeleton: Eine Datei, die man im Browser sieht, ist leichter zu
prüfen als eine Zeile Shell.

Warum das im Agent liegt: Die API fasst das Dateisystem des Hosts nicht an.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

FORBIDDEN = {"", ".", ".."}
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

# Ein Skeleton ist eine Handvoll Konfigurationsdateien, kein Datengrab.
MAX_BYTES = 256 * 1024**2

# Wohin im Container kopiert wird. Die Kasm-Images laufen als Nutzer 1000 mit
# genau diesem Zuhause.
HOME = "/home/kasm-user"


class SkeletonError(ValueError):
    """Eine Angabe taugt nicht. Die Meldung geht an den Menschen."""


def root(slug: str) -> Path:
    if not SLUG.match(slug or ""):
        raise SkeletonError("Das ist keine gültige Workspace-Kennung.")
    base = Path(os.environ.get("OTA_SKELETON_ROOT", "/srv/ota/skeletons")) / slug
    base.mkdir(parents=True, exist_ok=True)
    return base.resolve()


def _resolve(slug: str, rel: str, *, must_exist: bool = True) -> Path:
    """Loest einen Pfad im Skeleton auf — oder lehnt ab.

    Zuerst aufloesen, dann pruefen: Ein `..` faellt dabei genauso auf wie ein
    Symlink, der nach draussen zeigt. Dieselbe Reihenfolge wie in `shared.py`,
    und aus demselben Grund.
    """
    base = root(slug)
    rel = (rel or "").strip().strip("/")
    if rel and any(part in FORBIDDEN for part in rel.split("/")):
        raise SkeletonError("Dieser Pfad ist nicht erlaubt.")

    target = (base / rel).resolve() if rel else base
    if target != base and base not in target.parents:
        raise SkeletonError("Dieser Pfad liegt ausserhalb des Skeletons.")
    if must_exist and not target.exists():
        raise SkeletonError("Das gibt es hier nicht.")
    return target


def _safe_name(name: str) -> str:
    """Nimmt vom Dateinamen nur den Namen.

    Anders als bei der gemeinsamen Ablage sind **Punktdateien erlaubt** — ein
    Skeleton besteht zum grossen Teil aus ihnen (`.bashrc`, `.config/…`).
    Verboten bleiben nur die Namen, die im Dateisystem etwas anderes bedeuten.
    """
    clean = os.path.basename((name or "").strip().replace("\\", "/"))
    if clean in FORBIDDEN:
        raise SkeletonError(f"Dieser Dateiname geht nicht: {name!r}")
    return clean


def listing(slug: str, rel: str = "") -> dict[str, Any]:
    here = _resolve(slug, rel)
    if not here.is_dir():
        raise SkeletonError("Das ist kein Verzeichnis.")

    eintraege = []
    for kind in (True, False):          # Verzeichnisse zuerst
        for p in sorted(here.iterdir(), key=lambda x: x.name.lower()):
            if p.is_dir() != kind:
                continue
            eintraege.append({
                "name": p.name,
                "pfad": str(p.relative_to(root(slug))),
                "verzeichnis": p.is_dir(),
                "bytes": _size_of(p),
            })
    return {"pfad": rel.strip("/"), "eintraege": eintraege}


def _size_of(path: Path) -> int:
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    gesamt = 0
    for wurzel, _, dateien in os.walk(path):
        for d in dateien:
            try:
                gesamt += os.stat(os.path.join(wurzel, d)).st_size
            except OSError:
                pass
    return gesamt


def save(slug: str, rel: str, name: str, data: bytes) -> dict[str, Any]:
    if len(data) > MAX_BYTES:
        raise SkeletonError(
            f"Die Datei ist grösser als {MAX_BYTES // 1024**2} MB. Ein Skeleton "
            "ist für Einstellungen gedacht; grosse Dateien gehören in die "
            "gemeinsame Ablage."
        )
    ziel = _resolve(slug, rel) / _safe_name(name)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_bytes(data)
    _own(ziel)
    return {"pfad": str(ziel.relative_to(root(slug))), "bytes": len(data)}


def make_dir(slug: str, rel: str, name: str) -> dict[str, Any]:
    ziel = _resolve(slug, rel) / _safe_name(name)
    ziel.mkdir(parents=True, exist_ok=True)
    _own(ziel)
    return {"pfad": str(ziel.relative_to(root(slug)))}


def remove(slug: str, rel: str) -> dict[str, str]:
    ziel = _resolve(slug, rel)
    if ziel == root(slug):
        raise SkeletonError("Das Skeleton selbst lässt sich nicht löschen.")
    if ziel.is_dir():
        shutil.rmtree(ziel)
    else:
        ziel.unlink()
    return {"status": f"{ziel.name} gelöscht"}


def _own(path: Path) -> None:
    """Alles im Skeleton gehoert 1000:1000 — so landet es auch im Container."""
    try:
        os.chown(path, 1000, 1000)
    except (PermissionError, OSError):
        pass


def is_empty(profile_path: str) -> bool:
    """Ist dieses Zuhause noch unbenutzt?

    Nicht „gibt es das Verzeichnis" — das legt der Agent selbst an, bevor er
    den Container startet. Die Frage ist, ob schon jemand darin gearbeitet
    hat. Ein leeres Verzeichnis nach einer Wiederherstellung ins Nichts zaehlt
    ausdruecklich als unbenutzt.
    """
    if not profile_path or not os.path.isdir(profile_path):
        return True
    try:
        return not any(os.scandir(profile_path))
    except OSError:
        return False


def apply(container_id: str, slug: str, enforce: list[str], *,
          fresh: bool) -> dict[str, Any]:
    """Kopiert das Skeleton in den Container.

    ``fresh`` entscheidet ueber alles: Bei einem leeren Zuhause wandert der
    ganze Baum hinein, sonst nur die durchgesetzten Pfade.

    Kopiert wird mit ``docker cp`` und nicht ueber den Host-Pfad des Profils.
    Beides waere moeglich, aber ``docker cp`` geht auch dann, wenn ein
    Workspace gar kein persistentes Profil hat — und genau dort ist ein
    Skeleton besonders nuetzlich, weil sonst nichts uebrig bleibt.
    """
    try:
        base = root(slug)
    except SkeletonError:
        return {"kopiert": [], "grund": "kein Skeleton"}

    if not any(base.iterdir()):
        return {"kopiert": [], "grund": "Skeleton ist leer"}

    quellen: list[Path] = []
    if fresh:
        quellen = [base]
    else:
        for rel in enforce or []:
            try:
                quellen.append(_resolve(slug, rel))
            except SkeletonError:
                continue          # Pfad geloescht — kein Grund, den Start zu stoppen

    kopiert: list[str] = []
    for quelle in quellen:
        # Der Punkt am Ende bedeutet „der Inhalt", nicht „das Verzeichnis".
        # Ohne ihn entstuende /home/kasm-user/<slug>/…
        arg = f"{quelle}/." if quelle == base else str(quelle)
        ziel = HOME if quelle == base else f"{HOME}/{quelle.relative_to(base).parent}"
        try:
            subprocess.run(
                ["docker", "cp", arg, f"{container_id}:{ziel}"],
                capture_output=True, timeout=300, check=True,
            )
            kopiert.append(str(quelle.relative_to(base)) if quelle != base else ".")
        except (subprocess.SubprocessError, OSError):
            continue

    if kopiert:
        # Kopiert wurde als root. Ohne diesen Schritt gehoert dem Nutzer sein
        # eigenes Zuhause nicht mehr.
        subprocess.run(
            ["docker", "exec", "-u", "0", container_id,
             "chown", "-R", "1000:1000", HOME],
            capture_output=True, timeout=300,
        )

    return {"kopiert": kopiert, "grund": "erster Start" if fresh else "durchgesetzt"}
