"""Ablagen — Dateien neben dem Container.

Es gibt **zwei**, und der Unterschied ist der Zweck:

* Die **gemeinsame Ablage** ist der Weg der Administration zu den Nutzern:
  ein Firmenzertifikat, ein Installationspaket, eine Vorlagendatei. In den
  Session-Containern liegt sie **nur lesbar** unter `/mnt/ota`; geschrieben
  wird ausschliesslich über die Oberfläche, und zwar nur von denen, die
  Vorlagen verwalten duerfen.
* Die **eigene Ablage** gehoert je einem Nutzer und liegt **beschreibbar**
  unter `/mnt/austausch`. Sie ist der schnelle Weg in den Container hinein
  und wieder heraus — in beide Richtungen, vom Browser und von innen.

Beide benutzen denselben Code. Was sie trennt, ist die Wurzel und wer
drankommt; darueber entscheidet die API, nicht diese Datei.

Warum das hier im Agent steht und nicht in der API: Die API fasst das
Dateisystem des Hosts nicht an. Sie entscheidet, wer was darf; ausgeführt
wird es hier — dieselbe Aufteilung wie bei Containern und Images.

**Der einzige Punkt, an dem hier etwas schiefgehen kann, ist der Pfad.**
Jede Angabe kommt aus dem Browser. `_resolve` ist deshalb die Stelle, die
diese Datei richtig oder falsch macht: Sie loest auf und prueft danach, ob das
Ergebnis noch unterhalb der Wurzel liegt. Vorher zu pruefen genuegt nicht —
ein Symlink, der aus der Ablage herauszeigt, faellt erst beim Aufloesen auf.
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

# Dateinamen, die im Betriebssystem etwas bedeuten. Sie kommen aus dem
# Browser und haetten dort nichts verloren.
FORBIDDEN = {"", ".", ".."}

# Was eine einzelne Datei hoechstens haben darf. Die Ablage ist fuer Pakete
# und Zertifikate gedacht, nicht als Datengrab.
MAX_BYTES = 2 * 1024**3


class SharedError(ValueError):
    """Eine Angabe taugt nicht. Die Meldung geht an den Menschen."""


# Wie die Wurzeln der Ablagen stehen sollen.
#
# **0700 und root.** Darunter liegen die Zuhause von Menschen, ihre Dateien und
# die Sicherungen; ein Datenbankabzug enthaelt Passwort-Hashes, TOTP-Startwerte
# und das Kennwort des Verzeichnis-Dienstkontos. Bis zum 2026-09-04 stand das
# alles auf 0755 — fuer jeden Benutzer des Wirts lesbar (`security.md`, M2).
#
# In die Container kommt trotzdem alles hinein: Der Docker-Daemon haengt die
# Unterverzeichnisse als root ein, und dabei entscheidet der Modus des
# eingehaengten Verzeichnisses, nicht der seiner Eltern.
WURZEL_MODUS = 0o700


def _wurzel(pfad: Path, *, eigner: int | None = None) -> Path:
    """Eine Ablagenwurzel anlegen und eng halten.

    `eigner` fuer die Wurzeln, die **selbst** in einen Container eingehaengt
    werden. Dort zaehlt ihr Modus auch im Container — und der laeuft als 1000.
    Bleibt so eine Wurzel root:0700, sieht der Arbeitsplatz ein leeres
    Verzeichnis statt der gemeinsamen Ablage. (Genau so gemessen am
    2026-09-04: `touch` meldete „Permission denied" statt „Read-only file
    system", und die Ablage war unlesbar.)

    Wurzeln, von denen nur **Unterverzeichnisse** eingehaengt werden — Profile,
    eigene Ablagen, Gruppenlaufwerke — brauchen das nicht: Der Docker-Daemon
    haengt als root ein, und im Container entscheidet dann der Modus des
    eingehaengten Verzeichnisses.
    """
    pfad.mkdir(parents=True, exist_ok=True)
    try:
        if eigner is not None:
            os.chown(pfad, eigner, eigner)
        pfad.chmod(WURZEL_MODUS)
    except OSError:
        pass
    return pfad


def root() -> Path:
    # Wird als Ganzes eingehaengt (nur lesbar) — deshalb gehoert sie 1000.
    return _wurzel(Path(os.environ.get("OTA_SHARED_ROOT", "/srv/ota/shared")),
                   eigner=1000).resolve()


# Ein Benutzername, wie er als Verzeichnisname taugt. Bewusst enger als das,
# was OTA als Anmeldenamen zulaesst: Hier wird ein Pfad daraus.
NAME_OK = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$", re.IGNORECASE)


def user_root(username: str) -> Path:
    """Die eigene Ablage eines Nutzers. Legt sie an, wenn es sie nicht gibt.

    Eigentuemer ist 1000:1000 — dieselbe Kennung, unter der die Kasm-Images
    laufen. Ohne das koennte der Container zwar lesen, aber nichts
    zurueckschreiben, und die Ablage waere eine Einbahnstrasse.
    """
    if not NAME_OK.match(username or ""):
        raise SharedError("Dieser Name taugt nicht als Ablage.")

    base = _wurzel(Path(os.environ.get("OTA_USERFILES_ROOT", "/srv/ota/userfiles")))
    target = (base / username).resolve()
    # Nach dem Aufloesen pruefen, nicht davor: Ein Symlink faellt sonst nicht
    # auf. Dieselbe Regel wie in `_resolve`.
    if base.resolve() not in target.parents:
        raise SharedError("Dieser Pfad liegt ausserhalb der Ablagen.")

    if not target.exists():
        target.mkdir(parents=True)
        try:
            os.chown(target, 1000, 1000)
        except (PermissionError, OSError):
            pass
        # 0700, nicht 0755: Es ist die Ablage **eines** Menschen. Im Container
        # laeuft alles als 1000, also aendert das dort nichts — auf dem Wirt
        # schon.
        os.chmod(target, 0o700)
    return target


def group_root(group_id: str) -> Path:
    """Das Laufwerk einer Gruppe. Legt es an, wenn es das nicht gibt.

    Benannt nach der **Kennung** der Gruppe, nicht nach ihrem Namen — aus
    demselben Grund wie bei den Profilen (siehe `security.profile_path` in der
    API): Ein Gruppenname laesst sich in der Verwaltung aendern, und ab diesem
    Moment zeigte der Pfad woanders hin. Im Container traegt der
    Einhaengepunkt dann trotzdem den Namen; er kommt von der API mit.

    Eigentuemer ist 1000:1000, und das Verzeichnis traegt das setgid-Bit:
    Alles, was darin entsteht, gehoert derselben Gruppe. Ohne das koennte ein
    Container Dateien anlegen, die ein anderer nicht mehr aendern kann — und
    genau das ist bei einem gemeinsamen Laufwerk der Normalfall, nicht die
    Ausnahme.
    """
    if not NAME_OK.match(group_id or ""):
        raise SharedError("Diese Gruppenkennung taugt nicht als Ablage.")

    base = _wurzel(Path(os.environ.get("OTA_GROUPFILES_ROOT", "/srv/ota/groupfiles")))
    target = (base / group_id).resolve()
    # Nach dem Aufloesen pruefen, nicht davor — dieselbe Regel wie in
    # `user_root` und `_resolve`.
    if base.resolve() not in target.parents:
        raise SharedError("Dieser Pfad liegt ausserhalb der Gruppenlaufwerke.")

    if not target.exists():
        target.mkdir(parents=True)
        try:
            os.chown(target, 1000, 1000)
        except (PermissionError, OSError):
            pass
        os.chmod(target, 0o2775)
    return target


def _resolve(rel: str, *, must_exist: bool = True, base: Path | None = None) -> Path:
    """Loest einen Pfad innerhalb einer Ablage auf — oder lehnt ab.

    Zuerst aufloesen, dann pruefen. Ein `..` faellt dabei genauso auf wie ein
    Symlink, der nach draussen zeigt.
    """
    base = base or root()
    rel = (rel or "").strip().strip("/")
    if any(part in FORBIDDEN for part in rel.split("/")) and rel:
        raise SharedError("Dieser Pfad ist nicht erlaubt.")

    target = (base / rel).resolve() if rel else base
    if target != base and base not in target.parents:
        raise SharedError("Dieser Pfad liegt ausserhalb der Ablage.")
    if must_exist and not target.exists():
        raise SharedError("Das gibt es hier nicht.")
    return target


def _safe_name(name: str) -> str:
    """Nimmt vom Dateinamen nur den Namen — kein Verzeichnis, kein Trick."""
    clean = os.path.basename((name or "").strip().replace("\\", "/"))
    if clean in FORBIDDEN or clean.startswith("."):
        raise SharedError(f"Dieser Dateiname geht nicht: {name!r}")
    return clean


def listing(rel: str = "", base: Path | None = None) -> dict:
    """Was in diesem Verzeichnis liegt. Ordner zuerst, dann Dateien."""
    base = base or root()
    target = _resolve(rel, base=base)
    if not target.is_dir():
        raise SharedError("Das ist kein Verzeichnis.")

    entries = []
    for item in sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
        try:
            stat = item.stat()
        except OSError:
            continue
        entries.append({
            "name": item.name,
            "is_dir": item.is_dir(),
            "size_bytes": 0 if item.is_dir() else stat.st_size,
            "modified": stat.st_mtime,
        })

    return {
        "path": "" if target == base else str(target.relative_to(base)),
        "entries": entries,
        "total_bytes": _size_of(base),
    }


def _size_of(path: Path) -> int:
    total = 0
    for dirpath, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(dirpath, name))
            except OSError:
                continue
    return total


def save(rel: str, name: str, data: bytes, base: Path | None = None) -> dict:
    if len(data) > MAX_BYTES:
        raise SharedError(
            f"Die Datei ist grösser als {MAX_BYTES // 1024**3} GB. Die Ablage "
            "ist für Pakete und Zertifikate gedacht, nicht für Datenbestände."
        )
    target = _resolve(rel, base=base) / _safe_name(name)
    if target.is_dir():
        raise SharedError("Dort liegt ein Verzeichnis mit diesem Namen.")

    target.write_bytes(data)
    # Lesbar fuer alle: In den Containern laeuft Nutzer 1000, hier der Agent.
    # In der eigenen Ablage muss der Container zusaetzlich schreiben duerfen,
    # deshalb wandert auch der Eigentuemer mit.
    os.chmod(target, 0o644)
    try:
        os.chown(target, 1000, 1000)
    except (PermissionError, OSError):
        pass
    return {"name": target.name, "size_bytes": len(data)}


def make_dir(rel: str, name: str, base: Path | None = None) -> dict:
    target = _resolve(rel, base=base) / _safe_name(name)
    if target.exists():
        raise SharedError("Das gibt es schon.")
    target.mkdir(parents=True)
    os.chmod(target, 0o755)
    try:
        os.chown(target, 1000, 1000)
    except (PermissionError, OSError):
        pass
    return {"name": target.name}


def remove(rel: str, base: Path | None = None) -> dict:
    base = base or root()
    target = _resolve(rel, base=base)
    if target == base:
        raise SharedError("Die Ablage selbst lässt sich nicht löschen.")
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()
    return {"status": "entfernt"}


def read(rel: str, base: Path | None = None) -> tuple[str, bytes]:
    """Eine Datei zum Herunterladen."""
    target = _resolve(rel, base=base)
    if not target.is_file():
        raise SharedError("Das ist keine Datei.")
    return target.name, target.read_bytes()


def verweis_setzen(ziel: Path, name: str) -> None:
    """Legt neben einem Verzeichnis einen Verweis unter dem Anmeldenamen an.

    Verzeichnisse heissen nach der Kennung — sie aendert sich nie, ein
    Anmeldename schon (siehe `security.profile_path` in der API). Fuer einen
    Menschen, der im Dateisystem nachsieht, ist eine Reihe von UUIDs aber
    unbrauchbar. Deshalb dieser Verweis: Er traegt den Namen, zeigt auf die
    Kennung und wird beim Umbenennen einfach neu gesetzt.

    Ein bestehender Verweis auf dasselbe Ziel bleibt. Ein **echtes**
    Verzeichnis dieses Namens wird nie angefasst: Dort liegen womoeglich die
    Daten von vor der Umstellung.
    """
    if not name or not NAME_OK.match(name):
        return
    try:
        ziel = ziel.resolve()
        verweis = ziel.parent / name
        if verweis.is_symlink():
            if os.readlink(verweis) == ziel.name:
                return
            verweis.unlink()
        elif verweis.exists():
            return
        os.symlink(ziel.name, verweis)
    except OSError:
        # Ein fehlender Verweis ist ein Schoenheitsfehler, kein Grund, einen
        # Start abzubrechen.
        pass
