"""Sicherung und Wiederherstellung (plan.md §11.2).

Alles landet als Tar-Archiv unter einem einzigen Wurzelverzeichnis. Das ist
Absicht: Es laesst sich spaeter ohne Aenderung an OTA durch einen NFS-Mount
ersetzen — die Anwendung sieht weiterhin nur einen Pfad.
"""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKUP_ROOT = Path(os.environ.get("OTA_BACKUP_ROOT", "/srv/ota/backups"))
PROFILES_ROOT = Path(os.environ.get("OTA_PROFILES_ROOT", "/srv/ota/profiles"))

# Was nie mitgesichert wird. Alles davon ist jederzeit neu erzeugbar und
# macht bei Browser- und Editor-Profilen schnell den groesseren Teil aus.
EXCLUDE_NAMES = {
    ".cache", "Cache", "CachedData", "Cache_Data", "GPUCache", "Code Cache",
    "ShaderCache", "GrShaderCache", "DawnCache", "blob_storage",
    "CachedProfilesData", "CachedExtensionVSIXs", "Crash Reports",
    "__pycache__", "node_modules", ".Trash",
}
EXCLUDE_SUFFIXES = (".sock", ".lock", ".pid", ".Xauthority", ".ICEauthority")
EXCLUDE_PREFIXES = ("core.", ".X11-unix", ".vnc/", "krb5cc_")

# Pfade im Container, die bei einer Container-Sicherung nie mitkommen:
# fluechtig, nutzlos oder geheim.
CONTAINER_SKIP = (
    "/tmp", "/proc", "/sys", "/dev", "/run", "/var/run", "/var/tmp",
    "/var/log", "/var/cache", "/home/kasm-user",
)


def _skip(path: Path) -> bool:
    name = path.name
    if name in EXCLUDE_NAMES:
        return True
    if name.endswith(EXCLUDE_SUFFIXES):
        return True
    if any(name.startswith(p) for p in EXCLUDE_PREFIXES):
        return True
    # Sockets und Named Pipes lassen sich nicht sinnvoll archivieren.
    try:
        if path.is_socket() or path.is_fifo():
            return True
    except OSError:
        return True
    return False


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def ensure_root() -> None:
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)


def root_info() -> dict[str, Any]:
    """Zustand des Sicherungsverzeichnisses — auch fuer die NFS-Frage."""
    ensure_root()
    usage = shutil.disk_usage(BACKUP_ROOT)

    # Die nuetzliche Frage ist nicht "eigener Mount?" — im Agent-Container ist
    # das Verzeichnis immer ein Bind-Mount und die Antwort damit wertlos.
    # Gefragt ist: Liegt hier schon ein Netzlaufwerk, oder noch die lokale Platte?
    fstype = ""
    source = ""
    try:
        with open("/proc/mounts", encoding="utf-8") as fh:
            best = ""
            for line in fh:
                parts = line.split()
                if len(parts) >= 3 and str(BACKUP_ROOT).startswith(parts[1]):
                    if len(parts[1]) >= len(best):
                        best, source, fstype = parts[1], parts[0], parts[2]
    except OSError:
        pass

    network = fstype.lower() in {"nfs", "nfs4", "cifs", "smb3", "smbfs", "fuse.sshfs"}

    total = 0
    for path in BACKUP_ROOT.rglob("*.tar.zst"):
        try:
            total += path.stat().st_size
        except OSError:
            pass

    writable = os.access(BACKUP_ROOT, os.W_OK)
    return {
        "path": str(BACKUP_ROOT),
        "writable": writable,
        "is_network": network,
        "fstype": fstype,
        "source": source,
        "disk_total": usage.total,
        "disk_free": usage.free,
        "used_by_backups": total,
    }


def _tar_directory(source: Path, target: Path) -> tuple[int, int, list[str]]:
    """Packt ein Verzeichnis nach ``target``. Gibt Groesse, Anzahl, Hinweise."""
    target.parent.mkdir(parents=True, exist_ok=True)
    notes: list[str] = []
    count = 0

    def filt(info: tarfile.TarInfo) -> tarfile.TarInfo | None:
        nonlocal count
        if _skip(Path(info.name)):
            return None
        if any(part in EXCLUDE_NAMES for part in Path(info.name).parts):
            return None
        if info.isfile() or info.isdir() or info.issym():
            count += 1
            return info
        return None

    # zstd, weil es bei diesen Daten deutlich schneller ist als gzip und
    # dabei besser komprimiert.
    tmp = target.with_suffix(target.suffix + ".part")
    with open(tmp, "wb") as out:
        # "-c" schreibt nach stdout. Ein "-o /dev/stdout" scheitert daran,
        # dass zstd die Zieldatei als vorhanden ansieht und nicht überschreibt.
        proc = subprocess.Popen(["zstd", "-q", "-3", "-T2", "-c"],
                                stdin=subprocess.PIPE, stdout=out,
                                stderr=subprocess.PIPE)
        assert proc.stdin is not None
        try:
            with tarfile.open(fileobj=proc.stdin, mode="w|") as tar:
                tar.add(source, arcname=".", filter=filt)
        except (OSError, tarfile.TarError) as exc:
            notes.append(f"Beim Packen übersprungen: {exc}")
        finally:
            proc.stdin.close()
            err = proc.stderr.read().decode() if proc.stderr else ""
            code = proc.wait()
        if code != 0:
            tmp.unlink(missing_ok=True)
            raise RuntimeError(f"Komprimierung fehlgeschlagen: {err[:300]}")

    tmp.replace(target)
    return target.stat().st_size, count, notes


def backup_profile(username: str, scope: str = "user") -> dict[str, Any]:
    source = PROFILES_ROOT / username / scope
    if not source.is_dir():
        raise FileNotFoundError(
            f"Für {username} gibt es unter {source} noch kein Profil. "
            "Es entsteht beim ersten Sessionstart."
        )
    ensure_root()
    target = BACKUP_ROOT / "profiles" / username / f"{stamp()}.tar.zst"
    size, count, notes = _tar_directory(source, target)
    return {
        "path": str(target), "size_bytes": size, "file_count": count,
        "log": "\n".join([f"Gesichert: {source}", f"Ziel: {target}",
                          f"Einträge: {count}", *notes]),
    }


def restore_profile(username: str, archive: str, scope: str = "user") -> dict[str, Any]:
    """Stellt ein Profil wieder her.

    Das bisherige Verzeichnis wird nicht geloescht, sondern beiseitegelegt.
    Eine Wiederherstellung, die im Fehlerfall nichts uebriglaesst, ist keine.
    """
    src = Path(archive)
    if not src.is_file():
        raise FileNotFoundError(f"Das Archiv {archive} gibt es nicht.")
    if BACKUP_ROOT not in src.parents:
        raise ValueError("Es dürfen nur Archive aus dem Sicherungsverzeichnis "
                         "wiederhergestellt werden.")

    dest = PROFILES_ROOT / username / scope
    dest.parent.mkdir(parents=True, exist_ok=True)

    aside = None
    if dest.exists():
        aside = dest.with_name(f"{scope}.vor-wiederherstellung-{stamp()}")
        dest.rename(aside)

    dest.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.Popen(["zstd", "-dq", "-c", str(src)],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert proc.stdout is not None
        with tarfile.open(fileobj=proc.stdout, mode="r|") as tar:
            tar.extractall(dest, filter="tar")
        proc.wait()
    except Exception:
        # Zurueck auf den alten Stand, damit niemand ohne Profil dasteht.
        shutil.rmtree(dest, ignore_errors=True)
        if aside is not None:
            aside.rename(dest)
        raise

    # Die Kasm-Images laufen als Nutzer 1000.
    for path in [dest, *dest.rglob("*")]:
        try:
            os.chown(path, 1000, 1000, follow_symlinks=False)
        except (PermissionError, OSError):
            pass

    return {
        "restored_to": str(dest),
        "previous_kept_at": str(aside) if aside else None,
        "log": (f"Wiederhergestellt nach {dest}\n"
                + (f"Bisheriger Stand liegt unter {aside}\n" if aside else "")),
    }


def backup_container(container, username: str, template_slug: str) -> dict[str, Any]:
    """Sichert nur die Aenderungen im Container ausserhalb des Home.

    Ein vollstaendiger Export waere um ein Vielfaches groesser und bestuende
    fast nur aus dem Basisimage, das ohnehin aus dem Golden Image
    reproduzierbar ist. Gesichert wird deshalb, was ``docker diff`` als
    hinzugefuegt oder geaendert meldet.
    """
    ensure_root()
    target = BACKUP_ROOT / "containers" / username / f"{template_slug}-{stamp()}.tar.zst"
    target.parent.mkdir(parents=True, exist_ok=True)

    changes = container.diff() or []
    wanted = [
        c["Path"] for c in changes
        if c.get("Kind") in (0, 1)  # 0 = geaendert, 1 = hinzugefuegt
        and not any(c["Path"].startswith(skip) for skip in CONTAINER_SKIP)
    ]

    if not wanted:
        return {"path": None, "size_bytes": 0, "file_count": 0,
                "log": "Ausserhalb des Home hat sich nichts geändert — "
                       "keine Sicherung nötig."}

    tmp = target.with_suffix(target.suffix + ".part")
    written = 0
    with open(tmp, "wb") as out:
        proc = subprocess.Popen(["zstd", "-q", "-3", "-T2", "-c"],
                                stdin=subprocess.PIPE, stdout=out,
                                stderr=subprocess.DEVNULL)
        assert proc.stdin is not None
        with tarfile.open(fileobj=proc.stdin, mode="w|") as tar:
            for path in wanted:
                try:
                    stream, _ = container.get_archive(path)
                except Exception:  # noqa: BLE001 — einzelne Pfade duerfen fehlen
                    continue
                buf = io.BytesIO(b"".join(stream))
                try:
                    with tarfile.open(fileobj=buf, mode="r|") as inner:
                        for member in inner:
                            if not (member.isfile() or member.isdir() or member.issym()):
                                continue
                            member.name = path.lstrip("/") if member.name == "." \
                                else f"{path.lstrip('/')}/{member.name}"
                            data = inner.extractfile(member) if member.isfile() else None
                            tar.addfile(member, data)
                            written += 1
                except tarfile.TarError:
                    continue
        proc.stdin.close()
        proc.wait()

    tmp.replace(target)
    return {
        "path": str(target), "size_bytes": target.stat().st_size,
        "file_count": written,
        "log": (f"{len(changes)} Änderungen im Container, davon {len(wanted)} "
                f"ausserhalb des Home gesichert.\nZiel: {target}"),
    }


def restore_container(container, archive: str) -> dict[str, Any]:
    src = Path(archive)
    if not src.is_file():
        raise FileNotFoundError(f"Das Archiv {archive} gibt es nicht.")
    if BACKUP_ROOT not in src.parents:
        raise ValueError("Es dürfen nur Archive aus dem Sicherungsverzeichnis "
                         "wiederhergestellt werden.")

    proc = subprocess.run(["zstd", "-dq", "-c", str(src)],
                          capture_output=True, check=True)
    container.put_archive("/", proc.stdout)
    return {"log": f"{src.name} in den Container zurückgespielt."}


def list_files() -> list[dict[str, Any]]:
    ensure_root()
    out = []
    for path in sorted(BACKUP_ROOT.rglob("*.tar.zst")):
        try:
            st = path.stat()
        except OSError:
            continue
        out.append({
            "path": str(path),
            "size_bytes": st.st_size,
            "modified": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(),
        })
    return out


def delete_file(path: str) -> dict[str, str]:
    target = Path(path)
    if BACKUP_ROOT not in target.parents:
        raise ValueError("Nur Dateien im Sicherungsverzeichnis dürfen entfernt werden.")
    target.unlink(missing_ok=True)
    return {"status": "entfernt"}
