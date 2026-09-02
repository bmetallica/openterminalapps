"""Skeleton-Profile — womit ein Zuhause anfängt.

Ein Skeleton ist ein Verzeichnisbaum je Workspace, der ins Home eines Nutzers
kommt. Zwei Zeitpunkte, und der Unterschied ist der ganze Sinn:

* **Beim ersten Start**, wenn das Zuhause noch leer ist, wird alles kopiert.
  Damit fängt niemand mit einem nackten Desktop an: Editor-Einstellungen,
  ein Firmenzertifikat, eine Vorlage, eine `.bashrc`.
* **Bei jedem Start** werden nur die Pfade kopiert, die der Administrator
  ausdrücklich als *durchgesetzt* markiert hat — und die überschreiben, was
  der Nutzer geändert hat.
* **Beim ersten Start einer einzelnen Anwendung** ihr eigener Teilbaum, falls
  einer hinterlegt ist. Er liegt unter ``.apps/<anwendung>`` im Skeleton des
  Workspace und wird beim Workspace-Start ausdrücklich **nicht** mitkopiert.

  Warum eigenständig: Ein Arbeitsplatz trägt ein Dutzend Anwendungen, und
  nicht jeder Mensch startet jede davon. Die Einstellungen von IntelliJ ins
  Zuhause von jemandem zu legen, der nur das Terminal benutzt, macht das
  Zuhause voll und die Fehlersuche schwer. Gemerkt wird das im Zuhause selbst
  (``~/.ota/app-skeleton/<anwendung>``) und nicht in der Datenbank — der
  Anwendungskatalog wird beim Speichern komplett ersetzt, eine daran hängende
  Buchführung wäre jedes Mal weg.

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


# Wo die Teilbaeume der einzelnen Anwendungen liegen — innerhalb des
# Skeletons des Workspace, damit Sicherung und Umzug beides zusammen fassen,
# aber mit fuehrendem Punkt und ausdruecklich vom Rundumkopieren ausgenommen.
APPS_DIR = ".apps"

# Woran ein Container erkennt, dass der Teilbaum einer Anwendung schon
# angekommen ist. Im Zuhause, nicht in der Datenbank — siehe Modulkopf.
MARKER_DIR = ".ota/app-skeleton"


def root(slug: str, app: str | None = None) -> Path:
    """Das Skeleton eines Workspace — oder das einer einzelnen Anwendung."""
    if not SLUG.match(slug or ""):
        raise SkeletonError("Das ist keine gültige Workspace-Kennung.")
    base = Path(os.environ.get("OTA_SKELETON_ROOT", "/srv/ota/skeletons")) / slug
    if app is not None:
        if not SLUG.match(app or ""):
            raise SkeletonError("Das ist keine gültige Anwendungs-Kennung.")
        base = base / APPS_DIR / app
    base.mkdir(parents=True, exist_ok=True)
    return base.resolve()


def _resolve(slug: str, rel: str, *, must_exist: bool = True,
             app: str | None = None) -> Path:
    """Loest einen Pfad im Skeleton auf — oder lehnt ab.

    Zuerst aufloesen, dann pruefen: Ein `..` faellt dabei genauso auf wie ein
    Symlink, der nach draussen zeigt. Dieselbe Reihenfolge wie in `shared.py`,
    und aus demselben Grund.
    """
    base = root(slug, app)
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


def listing(slug: str, rel: str = "", app: str | None = None) -> dict[str, Any]:
    here = _resolve(slug, rel, app=app)
    if not here.is_dir():
        raise SkeletonError("Das ist kein Verzeichnis.")

    basis = root(slug, app)
    eintraege = []
    for kind in (True, False):          # Verzeichnisse zuerst
        for p in sorted(here.iterdir(), key=lambda x: x.name.lower()):
            if p.is_dir() != kind:
                continue
            # Die Teilbaeume der Anwendungen sind kein Inhalt des Workspace-
            # Skeletons. Sie haetten dort nur eine Bedeutung: „Verzeichnis,
            # das man besser nicht anfasst."
            if app is None and here == basis and p.name == APPS_DIR:
                continue
            eintraege.append({
                "name": p.name,
                "pfad": str(p.relative_to(basis)),
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


def save(slug: str, rel: str, name: str, data: bytes,
         app: str | None = None) -> dict[str, Any]:
    if len(data) > MAX_BYTES:
        raise SkeletonError(
            f"Die Datei ist grösser als {MAX_BYTES // 1024**2} MB. Ein Skeleton "
            "ist für Einstellungen gedacht; grosse Dateien gehören in die "
            "gemeinsame Ablage."
        )
    ziel = _resolve(slug, rel, app=app) / _safe_name(name)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_bytes(data)
    _own(ziel)
    return {"pfad": str(ziel.relative_to(root(slug, app))), "bytes": len(data)}


def make_dir(slug: str, rel: str, name: str, app: str | None = None) -> dict[str, Any]:
    ziel = _resolve(slug, rel, app=app) / _safe_name(name)
    ziel.mkdir(parents=True, exist_ok=True)
    _own(ziel)
    return {"pfad": str(ziel.relative_to(root(slug, app)))}


def remove(slug: str, rel: str, app: str | None = None) -> dict[str, str]:
    ziel = _resolve(slug, rel, app=app)
    if ziel == root(slug, app):
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

    inhalt = [p for p in base.iterdir() if p.name != APPS_DIR]
    if not inhalt:
        return {"kopiert": [], "grund": "Skeleton ist leer"}

    quellen: list[Path] = []
    if fresh:
        # Der ganze Baum — aber ohne `.apps`. Frueher stand hier `[base]` und
        # damit ein `docker cp <base>/. `; das haette die Teilbaeume aller
        # Anwendungen als sichtbares Verzeichnis im Zuhause abgelegt.
        quellen = inhalt
    else:
        for rel in enforce or []:
            try:
                quellen.append(_resolve(slug, rel))
            except SkeletonError:
                continue          # Pfad geloescht — kein Grund, den Start zu stoppen

    kopiert = _kopiere(container_id, base, quellen)
    return {"kopiert": kopiert, "grund": "erster Start" if fresh else "durchgesetzt"}


def _kopiere(container_id: str, base: Path, quellen: list[Path]) -> list[str]:
    """Legt die genannten Quellen an ihrer Stelle im Zuhause ab."""
    kopiert: list[str] = []
    for quelle in quellen:
        rel = quelle.relative_to(base)
        ziel = f"{HOME}/{rel.parent}" if str(rel.parent) != "." else HOME
        try:
            subprocess.run(
                ["docker", "cp", str(quelle), f"{container_id}:{ziel}"],
                capture_output=True, timeout=300, check=True,
            )
            kopiert.append(str(rel))
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
    return kopiert


def apply_app(container_id: str, slug: str, app: str) -> dict[str, Any]:
    """Legt den Teilbaum einer einzelnen Anwendung ins Zuhause — **einmal**.

    Gemerkt wird es im Zuhause selbst, unter ``~/.ota/app-skeleton/<app>``.
    Das ist Absicht und nicht Bequemlichkeit:

    * Der Anwendungskatalog wird beim Speichern komplett ersetzt (`set_apps`
      in der API), die Zeilen bekommen dabei neue Kennungen. Eine Buchfuehrung
      an der Datenbankzeile waere nach jeder Katalogaenderung weg.
    * Die Frage lautet ohnehin „hat **dieses Zuhause** den Teilbaum schon?" —
      und nur das Zuhause kann sie beantworten. Ein Workspace ohne
      persistentes Profil bekommt ihn folgerichtig bei jedem Start neu.

    Wer den Teilbaum erneut ausrollen will, loescht die Merkdatei — dieselbe
    Geste wie das „Nochmal" bei den Einmal-Skripten.
    """
    try:
        base = root(slug, app)
    except SkeletonError:
        return {"kopiert": [], "grund": "kein Teilbaum"}

    inhalt = list(base.iterdir())
    if not inhalt:
        return {"kopiert": [], "grund": "kein Teilbaum"}

    marker = f"{HOME}/{MARKER_DIR}/{app}"
    schon = subprocess.run(
        ["docker", "exec", "-u", "1000", container_id, "test", "-e", marker],
        capture_output=True, timeout=30,
    )
    if schon.returncode == 0:
        return {"kopiert": [], "grund": "war schon da"}

    kopiert = _kopiere(container_id, base, inhalt)
    if kopiert:
        subprocess.run(
            ["docker", "exec", "-u", "1000", container_id, "sh", "-c",
             f"mkdir -p {HOME}/{MARKER_DIR} && date -Iseconds > {marker}"],
            capture_output=True, timeout=30,
        )
    return {"kopiert": kopiert, "grund": "erster Start dieser Anwendung"}
