"""Baupläne für Software, die kein einfaches Paket ist.

Der Normalfall ist ein apt-Paket: anklicken, bauen, fertig. Für den Rest gab
es bisher nur ein leeres Skriptfeld — und drei fest eingebaute Rezepte, an
denen sich nichts aendern liess.

Hier entstehen Rezepte aus wenigen Fragen. Vier Muster decken fast alles ab,
was in einem Arbeitsplatz landen soll:

  ``apt_repo``   Ein fremdes APT-Depot einbinden und daraus installieren.
                 Der haeufigste Fall — Firefox, Chrome, VSCodium.
  ``deb_url``    Eine .deb-Datei von einer Adresse holen und einspielen.
  ``tarball``    Ein Archiv nach /opt auspacken und einen Starter anlegen.
                 JetBrains, Blender, alles mit eigenem Verzeichnis.
  ``appimage``   Eine AppImage-Datei ablegen und ausfuehrbar machen.
  ``script``     Freier Text. Das Rezept ist dann nur eine Ablage dafuer.

Erzeugt wird Bash. Absichtlich lesbar und nicht verschachtelt: Der Text steht
in der Oberflaeche und soll dort nachbesserbar sein, ohne dass jemand raten
muss, was passiert.
"""

from __future__ import annotations

import re
import shlex

KINDS = ("apt_repo", "deb_url", "tarball", "appimage", "script")

# Was hier hineingeht, wird zu einer Shell-Zeile. Adressen werden zusaetzlich
# auf http(s) eingegrenzt: Ein `file://` oder ein Semikolon hat in einem
# Rezept nichts zu suchen.
URL = re.compile(r"^https://[\w.-]+(?::\d{1,5})?(?:/[\w.~!$&'()*+,;=:@%/-]*)?$")
NAME = re.compile(r"^[a-z0-9][a-z0-9+._-]{0,80}$")
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

HEAD = "set -e\n"
TOOLS = (
    "apt-get update\n"
    "apt-get install -y --no-install-recommends wget ca-certificates gnupg\n"
)
TAIL = "apt-get clean && rm -rf /var/lib/apt/lists/*\n"


class RecipeError(ValueError):
    """Eine Angabe taugt nicht. Die Meldung geht an den Menschen."""


def _url(value: str, what: str) -> str:
    value = (value or "").strip()
    if not URL.match(value):
        raise RecipeError(
            f"{what} muss eine https-Adresse sein. Http ohne s wird nicht "
            "angenommen — ein Schlüssel oder ein Paket über eine ungesicherte "
            "Verbindung ist kein Schlüssel und kein Paket."
        )
    return value


def _pkg(value: str, what: str = "Der Paketname") -> str:
    value = (value or "").strip()
    if not NAME.match(value):
        raise RecipeError(f"{what} sieht nicht nach einem Paketnamen aus: {value!r}")
    return value


def _apt_repo(p: dict) -> str:
    """Fremdes APT-Depot einbinden und daraus installieren."""
    key = _url(p.get("key_url", ""), "Die Adresse des Schlüssels")
    repo = (p.get("repo_line") or "").strip()
    if not repo.startswith("deb "):
        raise RecipeError(
            "Die Depot-Zeile muss mit „deb " "beginnen — so, wie sie in einer "
            "sources.list stünde. Beispiel: "
            "deb https://packages.mozilla.org/apt mozilla main"
        )
    if any(c in repo for c in "\n\r;`$"):
        raise RecipeError("Die Depot-Zeile enthält Zeichen, die dort nicht hingehören.")

    package = _pkg(p.get("package", ""))
    name = _pkg(p.get("slug") or package, "Die Kennung")
    pin = bool(p.get("pin"))

    # Die Zeile bekommt den Schluessel angeheftet, der gleich abgelegt wird.
    signed = f"[signed-by=/etc/apt/keyrings/{name}.asc]"
    body = repo[4:].strip()

    out = [
        f"# {package} aus einem eigenen APT-Depot.",
        HEAD.rstrip(),
        TOOLS.rstrip(),
        "install -d -m 0755 /etc/apt/keyrings",
        f"wget -qO- {shlex.quote(key)} \\",
        f"  > /etc/apt/keyrings/{name}.asc",
        f'echo "deb {signed} {body}" \\',
        f"  > /etc/apt/sources.list.d/{name}.list",
    ]
    if pin:
        host = repo.split("//", 1)[-1].split("/", 1)[0].split(":")[0]
        out += [
            "# Vorrang, damit ein gleichnamiges Paket der Distribution die",
            "# echte Fassung nicht wieder verdrängt.",
            f'printf "Package: *\\nPin: origin {host}\\nPin-Priority: 1000\\n" \\',
            f"  > /etc/apt/preferences.d/{name}",
        ]
    out += [
        "apt-get update",
        f"apt-get install -y --no-install-recommends {package}",
        TAIL.rstrip(),
    ]
    return "\n".join(out) + "\n"


def _deb_url(p: dict) -> str:
    """Eine .deb-Datei holen und einspielen."""
    url = _url(p.get("url", ""), "Die Adresse der .deb-Datei")
    return "\n".join([
        "# Ein einzelnes Debian-Paket von einer Adresse.",
        HEAD.rstrip(),
        TOOLS.rstrip(),
        f"wget -qO /tmp/ota-paket.deb {shlex.quote(url)}",
        "# apt statt dpkg: Es zieht fehlende Abhängigkeiten selbst nach.",
        "apt-get install -y --no-install-recommends /tmp/ota-paket.deb",
        "rm -f /tmp/ota-paket.deb",
        TAIL.rstrip(),
    ]) + "\n"


def _tarball(p: dict) -> str:
    """Ein Archiv nach /opt auspacken und einen Starter anlegen."""
    url = _url(p.get("url", ""), "Die Adresse des Archivs")
    name = _pkg(p.get("slug", ""), "Die Kennung")
    binary = (p.get("binary") or "").strip()
    if not binary or any(c in binary for c in " ;`$\n"):
        raise RecipeError(
            "Der Pfad zum Programm im Archiv fehlt oder enthält Zeichen, die "
            "dort nicht hingehören. Beispiel: bin/idea.sh"
        )
    label = (p.get("name") or name).strip()
    if any(c in label for c in "\n\r`$"):
        raise RecipeError("Der Anzeigename enthält Zeichen, die dort nicht hingehören.")

    return "\n".join([
        f"# {label} als Archiv nach /opt/{name}.",
        HEAD.rstrip(),
        TOOLS.rstrip(),
        f"mkdir -p /opt/{name}",
        f"wget -qO /tmp/{name}.tar.gz {shlex.quote(url)}",
        "# --strip-components=1: Archive bringen fast immer ein eigenes",
        "# Wurzelverzeichnis mit, das sonst doppelt im Pfad landet.",
        f"tar -xzf /tmp/{name}.tar.gz -C /opt/{name} --strip-components=1",
        f"rm -f /tmp/{name}.tar.gz",
        "# Ein Starter im Pfad und ein Menüeintrag — Letzterer ist der Grund,",
        "# warum OTA die Anwendung nachher von selbst findet.",
        f"ln -sf /opt/{name}/{binary} /usr/local/bin/{name}",
        f"chmod +x /opt/{name}/{binary}",
        f"cat > /usr/share/applications/{name}.desktop <<'DESKTOP'",
        "[Desktop Entry]",
        "Type=Application",
        f"Name={label}",
        f"Exec=/usr/local/bin/{name}",
        "Terminal=false",
        "Categories=Utility;",
        "DESKTOP",
        TAIL.rstrip(),
    ]) + "\n"


def _appimage(p: dict) -> str:
    """Eine AppImage-Datei ablegen und ausfuehrbar machen."""
    url = _url(p.get("url", ""), "Die Adresse der AppImage-Datei")
    name = _pkg(p.get("slug", ""), "Die Kennung")
    label = (p.get("name") or name).strip()
    if any(c in label for c in "\n\r`$"):
        raise RecipeError("Der Anzeigename enthält Zeichen, die dort nicht hingehören.")

    return "\n".join([
        f"# {label} als AppImage.",
        HEAD.rstrip(),
        TOOLS.rstrip(),
        "# fuse2 wird gebraucht: Ein AppImage hängt sich beim Start selbst ein.",
        "apt-get install -y --no-install-recommends libfuse2",
        f"wget -qO /opt/{name}.AppImage {shlex.quote(url)}",
        f"chmod +x /opt/{name}.AppImage",
        f"ln -sf /opt/{name}.AppImage /usr/local/bin/{name}",
        f"cat > /usr/share/applications/{name}.desktop <<'DESKTOP'",
        "[Desktop Entry]",
        "Type=Application",
        f"Name={label}",
        f"Exec=/usr/local/bin/{name}",
        "Terminal=false",
        "Categories=Utility;",
        "DESKTOP",
        TAIL.rstrip(),
    ]) + "\n"


BUILDERS = {
    "apt_repo": _apt_repo,
    "deb_url": _deb_url,
    "tarball": _tarball,
    "appimage": _appimage,
}


def render(kind: str, params: dict) -> str:
    """Erzeugt das Skript zu einem Muster.

    Bei ``script`` wird nichts erzeugt — dort ist der Text die Angabe.
    """
    if kind == "script":
        return str(params.get("script") or "")
    builder = BUILDERS.get(kind)
    if builder is None:
        raise RecipeError(f"Unbekannte Art: {kind}")
    return builder(params)


# ---------------------------------------------------------------------------
# Mitgelieferte Rezepte
# ---------------------------------------------------------------------------

# Sie liegen in derselben Tabelle wie selbst gebaute, damit es nur eine Quelle
# gibt. Aendern lassen sie sich nicht — kopieren schon; dann bleibt das
# Original als Vergleich stehen.
BUILTIN: tuple[dict, ...] = (
    {
        "slug": "firefox",
        "name": "Firefox",
        "glyph": "◎",
        "why": ("Auf Ubuntu nur noch als Verweis auf ein Snap paketiert — im "
                "Container unbrauchbar. Dieses Rezept holt Firefox aus dem "
                "APT-Depot von Mozilla."),
        "kind": "apt_repo",
        "params": {
            "key_url": "https://packages.mozilla.org/apt/repo-signing-key.gpg",
            "repo_line": "deb https://packages.mozilla.org/apt mozilla main",
            "package": "firefox",
            "slug": "mozilla",
            "pin": True,
        },
    },
    {
        "slug": "google-chrome",
        "name": "Google Chrome",
        "glyph": "◎",
        "why": "Nicht in den Ubuntu-Quellen. Kommt aus dem Depot von Google.",
        "kind": "apt_repo",
        "params": {
            "key_url": "https://dl.google.com/linux/linux_signing_key.pub",
            "repo_line": ("deb https://dl.google.com/linux/chrome/deb/ "
                          "stable main"),
            "package": "google-chrome-stable",
            "slug": "google-chrome",
            "pin": False,
        },
    },
    {
        "slug": "vscodium",
        "name": "VSCodium",
        "glyph": "⌨",
        "why": ("Die Fassung von VS Code ohne Telemetrie und ohne die "
                "Lizenzbedingungen von Microsoft. Eigenes Depot."),
        "kind": "apt_repo",
        "params": {
            "key_url": ("https://gitlab.com/paulcarroty/vscodium-deb-rpm-repo/"
                        "raw/master/pub.gpg"),
            "repo_line": "deb https://download.vscodium.com/debs vscodium main",
            "package": "codium",
            "slug": "vscodium",
            "pin": False,
        },
    },
)


def ensure_builtins(db) -> None:
    """Legt die mitgelieferten Rezepte an, falls sie fehlen.

    Idempotent und ohne Ueberschreiben: Wer ein mitgeliefertes Rezept
    geloescht hat, bekommt es beim naechsten Start zurueck — das ist gewollt,
    denn loeschen laesst es sich ohnehin nicht.
    """
    from .models import Recipe  # spaet, um einen Ringschluss zu vermeiden

    for spec in BUILTIN:
        exists = db.query(Recipe).filter(Recipe.slug == spec["slug"]).first()
        if exists is not None:
            continue
        db.add(Recipe(script=render(spec["kind"], spec["params"]),
                      is_builtin=True, created_by=None, **spec))
    db.commit()
