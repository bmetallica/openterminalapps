"""Kasm-Registries lesen.

Kasm veröffentlicht seine Kataloge als schlichte JSON-Datei unter einer festen
Adresse: ``{registry_url}/{schema_version}/list.json``. Wer eine solche Adresse
einträgt, bekommt deren Anwendungen in OTA angeboten.

Warum das im Agent liegt und nicht in der API: Es ist ein Griff nach draussen
ins Netz, und diese Trennung gilt hier wie bei Docker und beim Dateisystem —
die API entscheidet, wer was darf, ausgeführt wird es hier. Ausserdem kennt
nur der Agent die Architektur des Hosts, und die entscheidet mit, was überhaupt
angeboten werden kann.

**Zwei Dinge, die dieser Leser bewusst nicht tut:**

* **Die Signatur prüfen.** Der Katalog trägt ein ES256-JWT über einen Hash
  seines Inhalts, der öffentliche Schlüssel liegt bei Kasm. Solange OTA ihn
  nicht hat, wäre eine Prüfung Theater. Stattdessen sagt die Oberfläche
  deutlich, dass eine Registry eine Vertrauensentscheidung ist.
* **Etwas herunterladen.** Gelesen wird nur der Katalog. Das Image kommt erst,
  wenn jemand es bewusst holt — und dann steht seine Grösse vorher da.
"""

from __future__ import annotations

import json
import platform
import re
import urllib.error
import urllib.request
from typing import Any

# Der Katalog ist eine Textdatei von gut hundert Kilobyte. Alles jenseits davon
# ist entweder ein Fehler oder ein Angriff.
MAX_BYTES = 16 * 1024 * 1024
TIMEOUT = 30

# Nur https. Ein Katalog über eine ungesicherte Verbindung ist ein Katalog, den
# unterwegs jemand ändern kann — und daraus entstehen Image-Referenzen, die
# anschliessend im eigenen Netz laufen.
URL = re.compile(r"^https://[\w.-]+(?::\d{1,5})?(?:/[\w.~!$&'()*+,;=:@%/-]*)?$")

# Wie Docker die Architektur nennt, gegenüber dem, was Python meldet.
ARCH_MAP = {
    "x86_64": "amd64", "amd64": "amd64",
    "aarch64": "arm64", "arm64": "arm64",
    "armv7l": "arm", "armhf": "arm",
}


class RegistryError(ValueError):
    """Die Registry taugt nicht. Die Meldung geht an den Menschen."""


def host_arch() -> str:
    return ARCH_MAP.get(platform.machine().lower(), platform.machine().lower())


def _catalog_url(base: str, schema: str) -> str:
    return f"{base.rstrip('/')}/{schema}/list.json"


def fetch(base_url: str, schema: str = "1.1") -> dict[str, Any]:
    """Liest den Katalog einer Registry.

    Zurück kommt eine aufbereitete Form: die Angaben der Registry selbst und
    ihre Einträge, jeder schon auf das reduziert, was OTA braucht.
    """
    base = (base_url or "").strip().rstrip("/")
    if not URL.match(base):
        raise RegistryError(
            "Das muss eine https-Adresse sein — zum Beispiel "
            "https://registry.kasmweb.com"
        )
    if not re.fullmatch(r"[0-9.]{1,8}", schema or ""):
        raise RegistryError("Die Schema-Version sieht nicht aus wie eine Version.")

    url = _catalog_url(base, schema)
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "OpenTerminalApps"})
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            raw = response.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise RegistryError(
            f"Die Registry antwortet mit {exc.code}. Stimmt die Adresse, und "
            f"gibt es dort ein Schema {schema}?"
        ) from exc
    except (urllib.error.URLError, OSError) as exc:
        raise RegistryError(f"Die Registry ist nicht erreichbar: {exc}") from exc

    if len(raw) > MAX_BYTES:
        raise RegistryError("Der Katalog ist unerwartet gross und wurde verworfen.")

    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RegistryError("Das ist kein lesbarer Katalog.") from exc
    if not isinstance(data, dict) or not isinstance(data.get("workspaces"), list):
        raise RegistryError("Der Katalog hat nicht die erwartete Form.")

    arch = host_arch()
    return {
        "name": str(data.get("name") or base),
        "description": str(data.get("description") or ""),
        "icon_url": _absolute(base, data.get("icon")),
        "workspace_count": len(data["workspaces"]),
        "modified": _int(data.get("modified")),
        "channels": [str(c) for c in (data.get("channels") or [])],
        "default_channel": str(data.get("default_channel") or ""),
        # Nur ein Hinweis, keine Prüfung — siehe Kopf dieser Datei.
        "signed": bool(data.get("signature")),
        "host_arch": arch,
        "entries": [
            entry for entry in (_entry(base, schema, w, arch) for w in data["workspaces"])
            if entry is not None
        ],
    }


def _entry(base: str, schema: str, w: Any, arch: str) -> dict[str, Any] | None:
    if not isinstance(w, dict):
        return None
    name = str(w.get("friendly_name") or "").strip()
    sha = str(w.get("sha") or "").strip()
    if not name or not sha:
        return None

    architectures = [str(a) for a in (w.get("architecture") or [])]

    best = _pick(w.get("compatibility") or [])
    if best is None:
        return None

    return {
        "sha": sha,
        "friendly_name": name,
        "description": str(w.get("description") or ""),
        "categories": [str(c) for c in (w.get("categories") or [])],
        "architectures": architectures,
        "icon_url": _icon_url(base, schema, w.get("image_src")),
        "image_ref": str(best["image"]),
        "available_tags": [str(t) for t in (best.get("available_tags") or [])],
        "uncompressed_size_mb": int(best.get("uncompressed_size_mb") or 0),
        # Läuft das hier überhaupt? Ein Eintrag ohne passende Architektur wird
        # gezeigt, aber nicht zum Import angeboten — ihn zu verschweigen
        # erzeugt nur die Frage, warum er fehlt.
        "runs_here": not architectures or arch in architectures,
    }


def _pick(compatibility: list) -> dict[str, Any] | None:
    """Welche Fassung vorgeschlagen wird.

    Der Katalog listet je Eintrag mehrere Kasm-Versionen. Naiv die letzte zu
    nehmen ist falsch: Bei AlmaLinux 8 zeigen die beiden neuesten auf
    ``kasmweb/almalinux-8-desktop:develop`` — einen rollenden
    Entwicklungsstand, und der letzte davon mit Groesse 0, also noch gar nicht
    gebaut.

    Vorgeschlagen wird deshalb die neueste Fassung, die **kein develop** ist
    und eine echte Groesse hat. Nur wenn es die nicht gibt, faellt die Wahl auf
    das Uebriggebliebene — dann steht im Katalog eben nichts Besseres.

    Eine andere Fassung laesst sich beim Import waehlen; `available_tags` sagt,
    welche.
    """
    usable = [
        c for c in compatibility
        if isinstance(c, dict) and c.get("image")
    ]
    if not usable:
        return None

    def stable(c: dict) -> bool:
        tag = str(c["image"]).rsplit(":", 1)[-1]
        return "develop" not in tag and int(c.get("uncompressed_size_mb") or 0) > 0

    preferred = [c for c in usable if stable(c)]
    if preferred:
        return preferred[-1]
    sized = [c for c in usable if int(c.get("uncompressed_size_mb") or 0) > 0]
    return (sized or usable)[-1]


def _icon_url(base: str, schema: str, value: Any) -> str | None:
    """Macht aus ``almalinux.svg`` eine vollständige Adresse.

    Die Symbole der Eintraege liegen **nicht** in der Wurzel der Registry,
    sondern neben dem Katalog unter ``{schema}/icons/``. Am echten Katalog
    nachgesehen: ``registry.kasmweb.com/almalinux.svg`` gibt 404,
    ``registry.kasmweb.com/1.1/icons/almalinux.svg`` gibt das Bild.
    """
    if not value:
        return None
    text = str(value)
    if text.startswith(("http://", "https://")):
        return text
    return f"{base}/{schema}/icons/{text.lstrip('/')}"


def _absolute(base: str, value: Any) -> str | None:
    """Eine Adresse relativ zur Wurzel der Registry.

    Fuer das Symbol der Registry selbst — das steht als ``/img/favicon.png``
    im Katalog, also von der Wurzel aus.
    """
    if not value:
        return None
    text = str(value)
    if text.startswith(("http://", "https://")):
        return text
    return f"{base}/{text.lstrip('/')}"


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# Symbole sind klein und werden oft geholt. Ein Zwischenspeicher im Prozess
# erspart der fremden Registry den wiederholten Zugriff — und uns die
# Wartezeit beim Blaettern durch 86 Eintraege.
_icons: dict[str, tuple[bytes, str]] = {}
MAX_ICON = 512 * 1024


def icon(url: str, allowed_base: str) -> tuple[bytes, str]:
    """Holt ein Symbol — aber nur von der Registry, zu der es gehoert.

    Der Aufrufer nennt die erlaubte Wurzel. Ohne diese Fessel waere das hier
    ein Werkzeug, mit dem sich ueber OTA beliebige Adressen abrufen liessen,
    auch solche im internen Netz.
    """
    target = (url or "").strip()
    base = (allowed_base or "").strip().rstrip("/")
    if not target or not base or not target.startswith(base + "/"):
        raise RegistryError("Dieses Symbol gehört nicht zu dieser Registry.")

    hit = _icons.get(target)
    if hit is not None:
        return hit

    try:
        request = urllib.request.Request(target, headers={"User-Agent": "OpenTerminalApps"})
        with urllib.request.urlopen(request, timeout=15) as response:
            raw = response.read(MAX_ICON + 1)
            kind = response.headers.get("Content-Type", "application/octet-stream")
    except (urllib.error.URLError, OSError) as exc:
        raise RegistryError(f"Symbol nicht erreichbar: {exc}") from exc

    if len(raw) > MAX_ICON:
        raise RegistryError("Das Symbol ist unerwartet gross.")
    # Nur Bilder. Was sonst zurueckkommt, wird nicht weitergereicht.
    if not kind.split(";")[0].strip().startswith("image/"):
        raise RegistryError("Das ist kein Bild.")

    if len(_icons) > 500:
        _icons.clear()
    _icons[target] = (raw, kind)
    return raw, kind
