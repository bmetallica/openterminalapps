"""Welche Anwendungen in einem Container stecken (Softwaremonitoring).

Erfasst werden **Anwendungen, keine Versionen und keine Bibliotheken**:

* `apt`     — von Hand installierte Debian-Pakete. Wie `apt-mark showmanual`:
  alles, was dpkg als installiert führt, ohne das, was apt als automatisch
  mitgezogen vermerkt hat. Ein per `dpkg -i` eingespieltes `.deb` zählt mit.
* `desktop` — Programme mit Starteintrag (`*.desktop`), systemweit und im
  Zuhause (dort landen etwa AppImages und von Hand angelegte Einträge).
* `flatpak`, `snap` — erkannt an den Starteinträgen, die beide exportieren.

**Gelesen, nicht ausgeführt.** Die Dateien kommen über die Docker-Schnittstelle
(`get_archive`, wie `docker cp`), das Zuhause direkt vom Wirt. Ein `apt-mark`
im Container aufzurufen hiesse, einem Programm zu glauben, das in einem
Root-Arbeitsplatz der Nutzer selbst austauschen kann. Wer die Statusdateien
von dpkg von Hand fälscht, täuscht auch das hier — das ist Absicht und nicht
mehr Wildwuchs.
"""
from __future__ import annotations

import io
import logging
import os
import re
import tarfile
from typing import Any

from docker.errors import APIError, NotFound

log = logging.getLogger("otaagent.software")

# Systemweite Orte mit Starteinträgen — und woran man Flatpak und Snap erkennt.
DESKTOP_ORTE = (
    ("/usr/share/applications", "desktop"),
    ("/usr/local/share/applications", "desktop"),
    ("/var/lib/flatpak/exports/share/applications", "flatpak"),
    ("/var/lib/snapd/desktop/applications", "snap"),
)
# Im Zuhause, relativ dazu.
HEIM_ORTE = (
    (".local/share/applications", "desktop"),
    (".local/share/flatpak/exports/share/applications", "flatpak"),
)
# dpkg-Status ist auf einem vollen Arbeitsplatz einige MB gross; mehr ist kaputt.
MAX_DATEI = 64 * 1024 * 1024
NAME_OK = re.compile(r"[A-Za-z0-9][A-Za-z0-9.+_@-]{0,199}")


def _archiv(container, pfad: str) -> tarfile.TarFile | None:
    """Ein Pfad aus dem Container als Tar, oder None, wenn es ihn nicht gibt."""
    try:
        strom, info = container.get_archive(pfad)
    except NotFound:
        return None
    except APIError as exc:
        if getattr(exc, "status_code", None) == 404:
            return None
        raise
    if (info or {}).get("size", 0) > MAX_DATEI:
        return None
    puffer = io.BytesIO()
    for stueck in strom:
        puffer.write(stueck)
        if puffer.tell() > MAX_DATEI * 2:
            return None
    puffer.seek(0)
    return tarfile.open(fileobj=puffer)


def _datei(container, pfad: str) -> str | None:
    tar = _archiv(container, pfad)
    if tar is None:
        return None
    for m in tar.getmembers():
        if m.isfile():
            f = tar.extractfile(m)
            return f.read().decode("utf-8", "replace") if f else None
    return None


def dpkg_von_hand(status: str, erweitert: str | None) -> set[str]:
    """Installierte Pakete ohne die, die apt als automatisch vermerkt hat."""
    installiert: set[str] = set()
    for block in status.split("\n\n"):
        name = zustand = None
        for zeile in block.splitlines():
            if zeile.startswith("Package: "):
                name = zeile[9:].strip()
            elif zeile.startswith("Status: "):
                zustand = zeile[8:].strip()
        if name and zustand and zustand.endswith(" installed"):
            installiert.add(name)

    auto: set[str] = set()
    for block in (erweitert or "").split("\n\n"):
        name = None
        markiert = False
        for zeile in block.splitlines():
            if zeile.startswith("Package: "):
                name = zeile[9:].strip()
            elif zeile.replace(" ", "") == "Auto-Installed:1":
                markiert = True
        if name and markiert:
            auto.add(name)
    # extended_states führt Architektur-Varianten getrennt; der Name reicht.
    return installiert - auto


def desktop_eintrag(text: str) -> str | None:
    """Der sichtbare Name eines Starteintrags — None, wenn er versteckt ist."""
    im_abschnitt = False
    name = None
    typ = "Application"
    for zeile in text.splitlines():
        zeile = zeile.strip()
        if zeile.startswith("["):
            im_abschnitt = zeile == "[Desktop Entry]"
            continue
        if not im_abschnitt or "=" not in zeile:
            continue
        k, v = (t.strip() for t in zeile.split("=", 1))
        if k == "Name" and name is None:
            name = v
        elif k == "Type":
            typ = v
        elif k in ("NoDisplay", "Hidden") and v.lower() == "true":
            return None
    if typ != "Application":
        return None
    return name or ""


def _schluessel(dateiname: str) -> str | None:
    if not dateiname.endswith(".desktop"):
        return None
    name = dateiname[:-len(".desktop")].lower()
    return name if NAME_OK.fullmatch(name) else None


def _merken(aus: dict[str, dict], schluessel: str, quelle: str, titel: str) -> None:
    """Ein Name einmal. Kennt apt ihn schon, bekommt er hier nur den Titel dazu."""
    alt = aus.get(schluessel)
    if alt is None:
        aus[schluessel] = {"name": schluessel, "quelle": quelle, "titel": titel}
    elif titel and not alt["titel"]:
        alt["titel"] = titel


def _desktop_aus_tar(tar: tarfile.TarFile, quelle: str, aus: dict[str, dict]) -> None:
    for m in tar.getmembers():
        schluessel = _schluessel(os.path.basename(m.name))
        if not schluessel:
            continue
        titel = ""
        if m.isfile():
            f = tar.extractfile(m)
            titel = desktop_eintrag(f.read(256 * 1024).decode("utf-8", "replace")) if f else ""
            if titel is None:
                continue
        # Verweise (Flatpak exportiert so) zählen ohne Titel.
        _merken(aus, schluessel, quelle, titel or "")


def _desktop_aus_ordner(ordner: str, quelle: str, aus: dict[str, dict]) -> None:
    try:
        eintraege = list(os.scandir(ordner))
    except OSError:
        return
    for e in eintraege:
        schluessel = _schluessel(e.name)
        if not schluessel:
            continue
        titel = ""
        try:
            if e.is_file(follow_symlinks=False):
                with open(e.path, "rb") as fh:
                    titel = desktop_eintrag(fh.read(256 * 1024).decode("utf-8", "replace"))
        except OSError:
            pass
        if titel is None:
            continue
        _merken(aus, schluessel, quelle, titel or "")


def heim_quellen(container) -> list[str]:
    """Wo auf dem Wirt die Zuhause dieses Containers liegen (Bind-Mounts nach /home oder /root)."""
    quellen = []
    for m in container.attrs.get("Mounts") or []:
        ziel = str(m.get("Destination") or "")
        if m.get("Type") == "bind" and (ziel.startswith("/home/") or ziel == "/root"):
            quellen.append(str(m.get("Source") or ""))
    return [q for q in quellen if q and os.path.isdir(q)]


def inventar(container) -> list[dict[str, Any]]:
    """Alle Anwendungen eines Containers, je Name einmal."""
    aus: dict[str, dict] = {}

    status = _datei(container, "/var/lib/dpkg/status")
    if status:
        erweitert = _datei(container, "/var/lib/apt/extended_states")
        for name in dpkg_von_hand(status, erweitert):
            if NAME_OK.fullmatch(name):
                aus[name.lower()] = {"name": name.lower(), "quelle": "apt", "titel": ""}

    for ordner, quelle in DESKTOP_ORTE:
        tar = _archiv(container, ordner)
        if tar is not None:
            _desktop_aus_tar(tar, quelle, aus)

    for heim in heim_quellen(container):
        for relativ, quelle in HEIM_ORTE:
            _desktop_aus_ordner(os.path.join(heim, relativ), quelle, aus)

    return sorted(aus.values(), key=lambda a: a["name"])
