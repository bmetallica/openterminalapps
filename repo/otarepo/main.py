"""ota-repo — der Steuerdienst der Paketquellen (Handbuch Kapitel 26).

Mit diesem Dienst spricht die OTA-API, nie mit aptly direkt. Er tut vier Dinge:

* **Spiegel** von Debian 13 (main, updates, security) und Dockers Paketquelle
  abgleichen und veröffentlichen — immer über einen Snapshot, damit ein
  abgebrochener Abgleich nie einen halben Stand ausliefert.
* **Eigene Pakete** annehmen, prüfen (gültiges .deb), signiert veröffentlichen.
* **Snapshots** auf Knopfdruck festhalten, unter eigener Adresse
  veröffentlichen, auf sie zurückdrehen, sie löschen.
* **Dateien** ausserhalb von apt holen, die das Aufsetzen ohne Internet braucht
  (die Abhängigkeiten von Selkies, clipnotify, Sysbox).

**Alles hintereinander.** aptly verträgt keine zwei Aufrufe gleichzeitig auf
derselben Datenbank. Ein Abgleich dauert beim ersten Mal Stunden; solange er
läuft, wird ein Upload mit einer Erklärung abgelehnt statt eingereiht.

Erreichbar nur im internen Netz, geschützt mit demselben Token wie der Agent.
Ausgeliefert wird nicht hier, sondern von `repo-web` (nginx) unter `/repo`.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("otarepo")

TOKEN = os.environ.get("OTA_AGENT_TOKEN", "")
ROOT = Path(os.environ.get("OTA_REPO_ROOT", "/srv/ota/repo"))
APTLY_ROOT = ROOT / "aptly"
PUBLIC = APTLY_ROOT / "public"
DATEIEN = PUBLIC / "dateien"
GNUPGHOME = ROOT / "gpg"
KONF = ROOT / "aptly.conf"
META = ROOT / "meta.json"
EINGANG = ROOT / "eingang"

# Leer heisst: **Vollspiegel**. Ein Ausdruck in aptlys Filtersprache spiegelt
# nur diese Pakete samt Abhängigkeiten — zum Ausprobieren auf einer Maschine
# ohne 100 GB frei, oder für einen bewusst kleinen Spiegel.
FILTER = os.environ.get("OTA_REPO_FILTER", "").strip()

SELKIES_VERSION = os.environ.get("OTA_REPO_SELKIES_VERSION", "2.0.0")
SELKIES_LISTE = Path(os.environ.get("OTA_REPO_SELKIES_LISTE", "/app/selkies-abhaengigkeiten.txt"))
SYSBOX_VERSION = "0.7.1"
SYSBOX_SHA256 = "9d6d5484f980d0a17f86c492c1262015c2afb66280bdb97215b79fde6a0261c5"

# Was gespiegelt wird. `prefix` ist der Pfad unter /repo, `dist`/`comp` das,
# was in den Quellen der Container steht.
SPIEGEL: list[dict[str, str]] = [
    {"name": "debian-trixie", "url": "http://deb.debian.org/debian",
     "dist": "trixie", "comp": "main", "prefix": "debian"},
    {"name": "debian-trixie-updates", "url": "http://deb.debian.org/debian",
     "dist": "trixie-updates", "comp": "main", "prefix": "debian"},
    # Der Sicherheitsbereich heisst in Debians Release-Datei `updates/main`.
    # apt uebersetzt `main` selbst, aptly nicht: „component main not
    # available". Gespiegelt wird deshalb `updates/main`, veroeffentlicht als
    # `main` — die Quellen in den Containern bleiben einheitlich.
    {"name": "debian-trixie-security", "url": "http://security.debian.org/debian-security",
     "dist": "trixie-security", "comp": "main", "quell_comp": "updates/main",
     "prefix": "debian-security"},
    # Dockers Quelle, gefiltert auf das, was das Root-Image braucht. Ganz
    # gespiegelt wären es hunderte alte Versionen von docker-ce.
    #
    # **Nur die neueste Version je Paket.** Dockers Quelle fuehrt jede jemals
    # veroeffentlichte Fassung; gefiltert nur nach Namen waren es 160 Pakete
    # und 2,8 GB (gemessen 2026-10-07). aptly kennt kein „nur die neueste" —
    # die Liste der Quelle wird deshalb vorher gelesen und der Filter auf die
    # jeweils hoechste Version gesetzt (`neueste`).
    {"name": "docker", "url": "https://download.docker.com/linux/debian",
     "dist": "trixie", "comp": "stable", "prefix": "docker",
     "neueste": "docker-ce docker-ce-cli containerd.io docker-buildx-plugin "
                "docker-compose-plugin",
     "schluessel": "https://download.docker.com/linux/debian/gpg"},
]
EIGEN = {"name": "ota", "dist": "ota", "comp": "main", "prefix": "ota"}

NAME_OK = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")
# Paketname und Fassung nach Debian Policy (5.6.1, 5.6.12). Beide wandern in
# aptlys Abfragesprache; ein `)` oder `|` aus einem präparierten Paket träfe
# dort sonst mehr als das eine Paket.
PAKET_OK = re.compile(r"^[a-z0-9][a-z0-9.+-]+$")
FASSUNG_OK = re.compile(r"^[0-9A-Za-z.+~:-]+$")

app = FastAPI(title="OTA Paketquellen", docs_url=None, redoc_url=None)
_sperre = threading.Lock()
_auftrag: dict[str, Any] = {"art": "", "laeuft": False, "protokoll": "", "start": None,
                            "ende": None, "ergebnis": ""}


def _jetzt() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def require_token(x_agent_token: str = Header(default="")) -> None:
    if not TOKEN or not secrets.compare_digest(x_agent_token, TOKEN):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Token ungültig")


# --------------------------------------------------------------- Werkzeuge

def _umgebung() -> dict[str, str]:
    env = dict(os.environ)
    env["GNUPGHOME"] = str(GNUPGHOME)
    env["HOME"] = str(ROOT)
    return env


def _lauf(args: list[str], protokoll: bool = False, pruefen: bool = True,
          zeit: int | None = None) -> str:
    """Einen Befehl ausführen; mit `protokoll` geht die Ausgabe mit in den
    laufenden Auftrag (gekürzt), damit die Oberfläche zusehen kann."""
    if args and args[0] == "aptly":
        args = ["aptly", f"-config={KONF}"] + args[1:]
    if protokoll:
        _schreib(f"$ {' '.join(args)}\n")
    fertig = subprocess.run(args, capture_output=True, text=True, env=_umgebung(),
                            timeout=zeit)
    ausgabe = (fertig.stdout or "") + (fertig.stderr or "")
    if protokoll:
        # Ein Abgleich schreibt je Paket eine Zeile — beim Vollspiegel
        # zehntausende. Die Oberfläche braucht Anfang und Ende, nicht jede.
        zeilen = ausgabe.splitlines()
        if len(zeilen) > 60:
            zeilen = zeilen[:20] + [f"… {len(zeilen) - 40} Zeilen ausgelassen …"] + zeilen[-20:]
        _schreib("\n".join(zeilen) + ("\n" if zeilen else ""))
    if pruefen and fertig.returncode != 0:
        raise RuntimeError(f"{args[0]} {args[2] if len(args) > 2 else ''}: "
                           f"{ausgabe.strip()[-600:]}")
    return ausgabe


def _schreib(text: str) -> None:
    _auftrag["protokoll"] = (_auftrag["protokoll"] + text)[-200_000:]


def _meta() -> dict[str, Any]:
    try:
        return json.loads(META.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"abgleiche": [], "pakete": {}, "snapshots": {}, "aktuell": {}}


def _meta_schreiben(daten: dict[str, Any]) -> None:
    neu = META.with_suffix(".tmp")
    neu.write_text(json.dumps(daten, indent=1, ensure_ascii=False), encoding="utf-8")
    neu.replace(META)


def _schluessel_fpr() -> str:
    aus = _lauf(["gpg", "--batch", "--list-secret-keys", "--with-colons"], pruefen=False)
    for zeile in aus.splitlines():
        if zeile.startswith("fpr:"):
            return zeile.split(":")[9]
    return ""


def _veroeffentlicht() -> set[tuple[str, str]]:
    """(prefix, dist) aller Veröffentlichungen."""
    raus = set()
    for zeile in _lauf(["aptly", "publish", "list", "-raw"], pruefen=False).splitlines():
        teile = zeile.split()
        if len(teile) == 2:
            raus.add((teile[0], teile[1]))
    return raus


def _veroeffentlichen(snapshot: str, prefix: str, dist: str, comp: str,
                      protokoll: bool = True) -> None:
    """Snapshot unter prefix/dist ausliefern — neu oder umschalten."""
    fpr = _schluessel_fpr()
    if (prefix, dist) in _veroeffentlicht():
        _lauf(["aptly", "publish", "switch", "-batch", f"-gpg-key={fpr}",
               f"-component={comp}", dist, prefix, snapshot], protokoll)
    else:
        _lauf(["aptly", "publish", "snapshot", "-batch", f"-gpg-key={fpr}",
               f"-distribution={dist}", f"-component={comp}", snapshot, prefix], protokoll)


def _auto_wegraeumen(name: str, behalten: str, protokoll: bool = False) -> None:
    """Alte auto-Snapshots eines Spiegels wegwerfen. -force, weil aptly sonst
    jeden ablehnt, aus dem ein festgehaltener Stand zusammengeführt wurde —
    der festgehaltene behält seine Pakete trotzdem."""
    for snap in _lauf(["aptly", "snapshot", "list", "-raw"], pruefen=False).split():
        if snap.startswith("auto-") and snap.endswith(f"-{name}") and snap != behalten \
                and len(snap) == len(f"auto-00000000000000-{name}"):
            _lauf(["aptly", "snapshot", "drop", "-force", snap], protokoll, pruefen=False)


# -------------------------------------------------------------- Einrichten

def einrichten() -> None:
    """Beim Start: Verzeichnisse, Konfiguration, Schlüssel, eigenes Repo."""
    for pfad in (ROOT, APTLY_ROOT, PUBLIC, DATEIEN, EINGANG):
        pfad.mkdir(parents=True, exist_ok=True)
    GNUPGHOME.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(GNUPGHOME, 0o700)
    KONF.write_text(json.dumps({
        "rootDir": str(APTLY_ROOT),
        "downloadConcurrency": 4,
        "architectures": ["amd64"],
        "dependencyFollowSuggests": False,
        "dependencyFollowRecommends": False,
        "dependencyFollowAllVariants": False,
        "gpgProvider": "gpg",
        # Contents-Indizes braucht apt nicht; sie kosten beim Vollspiegel
        # Stunden und Gigabytes.
        "skipContentsPublishing": True,
        "skipBz2Publishing": True,
    }, indent=1), encoding="utf-8")

    if not _schluessel_fpr():
        log.info("Erzeuge den Signierschlüssel der Paketquelle")
        _lauf(["gpg", "--batch", "--pinentry-mode", "loopback", "--passphrase", "",
               "--quick-gen-key", "OpenTerminalApps Paketquelle <repo@ota.invalid>",
               "rsa4096", "sign", "never"])
    # Der öffentliche Teil — das, was jeder Container bekommt.
    oeffentlich = _lauf(["gpg", "--batch", "--armor", "--export", _schluessel_fpr()])
    (PUBLIC / "ota-repo.asc").write_text(oeffentlich, encoding="utf-8")

    # Debians Schlüssel, damit aptly die Spiegel prüfen kann.
    _lauf(["gpg", "--batch", "--no-default-keyring", "--keyring", "trustedkeys.gpg",
           "--import", "/usr/share/keyrings/debian-archive-keyring.gpg"], pruefen=False)

    if "ota" not in _lauf(["aptly", "repo", "list", "-raw"], pruefen=False).split():
        _lauf(["aptly", "repo", "create", f"-distribution={EIGEN['dist']}",
               f"-component={EIGEN['comp']}", EIGEN["name"]])
    # Auch leer veröffentlichen: Sonst stünde in jedem Container eine Quelle,
    # die mit 404 antwortet, und `apt update` meldete Fehler, bevor der
    # erste je ein Paket hochgeladen hat.
    if (EIGEN["prefix"], EIGEN["dist"]) not in _veroeffentlicht():
        _lauf(["aptly", "publish", "repo", "-batch", f"-gpg-key={_schluessel_fpr()}",
               f"-distribution={EIGEN['dist']}", f"-component={EIGEN['comp']}",
               EIGEN["name"], EIGEN["prefix"]], pruefen=False)


@app.on_event("startup")
def _start() -> None:
    try:
        einrichten()
    except Exception as exc:  # noqa: BLE001 — sichtbar im Status, nicht im Absturz
        log.exception("Einrichten gescheitert: %s", exc)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


# ------------------------------------------------------------------ Status

def _zahl(text: str, schluessel: str) -> int:
    treffer = re.search(rf"{re.escape(schluessel)}:\s*(\d+)", text)
    return int(treffer.group(1)) if treffer else 0


def _groesse(pfad: Path) -> int:
    try:
        aus = subprocess.run(["du", "-sb", str(pfad)], capture_output=True, text=True,
                             timeout=120).stdout.split()
        return int(aus[0]) if aus else 0
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return 0


@app.get("/status", dependencies=[Depends(require_token)])
def status_() -> dict[str, Any]:
    meta = _meta()
    vorhanden = set(_lauf(["aptly", "mirror", "list", "-raw"], pruefen=False).split())
    spiegel = []
    for s in SPIEGEL:
        eintrag: dict[str, Any] = {"name": s["name"], "quelle": f"{s['url']} {s['dist']} {s['comp']}",
                                   "pakete": 0, "angelegt": s["name"] in vorhanden,
                                   "aktuell": meta["aktuell"].get(s["name"], "")}
        if eintrag["angelegt"]:
            info = _lauf(["aptly", "mirror", "show", s["name"]], pruefen=False)
            eintrag["pakete"] = _zahl(info, "Number of packages")
        spiegel.append(eintrag)
    eigen = _lauf(["aptly", "repo", "show", "ota"], pruefen=False)
    plattenplatz = shutil.disk_usage(ROOT)
    return {
        "filter": FILTER,
        "vollspiegel": not FILTER,
        "spiegel": spiegel,
        "eigene_pakete": _zahl(eigen, "Number of packages"),
        "schluessel": _schluessel_fpr(),
        "belegt": _groesse(APTLY_ROOT),
        "frei": plattenplatz.free,
        "letzter_abgleich": (meta["abgleiche"] or [None])[-1],
        "auftrag": {k: v for k, v in _auftrag.items() if k != "protokoll"},
        "veroeffentlicht": sorted(f"{p} {d}" for p, d in _veroeffentlicht()),
        "snapshots": meta["snapshots"],
        "dateien": _dateien_liste(),
    }


@app.get("/auftrag", dependencies=[Depends(require_token)])
def auftrag() -> dict[str, Any]:
    return dict(_auftrag)


@app.get("/quellen", dependencies=[Depends(require_token)])
def quellen() -> dict[str, Any]:
    """Was ein Container eingetragen bekommt: die veroeffentlichten Staende
    (prefix, dist, comp) und der Schluessel. Schlank, weil die API das bei
    jedem Start eines Arbeitsplatzes fragt — ohne die Groessenmessung von
    `/status`, die beim Vollspiegel ueber 100 GB laeuft."""
    komps = {t["prefix"]: t["comp"] for t in _snapshot_teile()}
    raus = []
    for prefix, dist in sorted(_veroeffentlicht()):
        basis = prefix.split("/")[-1]
        raus.append({"prefix": prefix, "dist": dist, "comp": komps.get(basis, "main")})
    return {"quellen": raus, "schluessel": schluessel()}


@app.get("/schluessel", response_class=PlainTextResponse)
def schluessel() -> str:
    """Der öffentliche Schlüssel — kein Geheimnis, deshalb ohne Token."""
    return (PUBLIC / "ota-repo.asc").read_text(encoding="utf-8")


# ---------------------------------------------------------------- Aufträge

def _im_hintergrund(art: str, arbeit) -> dict[str, str]:
    if not _sperre.acquire(blocking=False):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Es läuft bereits: {_auftrag['art']}. Bitte warten, bis er fertig ist.")
    _auftrag.update({"art": art, "laeuft": True, "protokoll": "", "start": _jetzt(),
                     "ende": None, "ergebnis": ""})

    def lauf() -> None:
        try:
            arbeit()
            _auftrag["ergebnis"] = "ok"
        except Exception as exc:  # noqa: BLE001
            log.exception("%s gescheitert", art)
            _schreib(f"\nFEHLER: {exc}\n")
            _auftrag["ergebnis"] = f"fehlgeschlagen: {str(exc)[:300]}"
        finally:
            _auftrag.update({"laeuft": False, "ende": _jetzt()})
            _sperre.release()

    threading.Thread(target=lauf, daemon=True).start()
    return {"status": f"{art} gestartet"}


def _synchron(art: str):
    """Für kurze Aufträge (Upload, Snapshot): sofort oder mit 409."""
    if not _sperre.acquire(timeout=5):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Es läuft gerade: {_auftrag['art'] or 'ein Auftrag'}. "
                            "Bitte warten, bis er fertig ist.")
    return _sperre


# ----------------------------------------------------------------- Abgleich

def _neueste_filter(s: dict[str, str]) -> str:
    """aptly-Filter auf die jeweils hoechste Version der genannten Pakete.

    Gelesen wird die Paketliste der Quelle selbst; verglichen nach Debians
    Regeln (`dpkg --compare-versions`), nicht als Text — sonst gewaenne
    `5:28.10` gegen `5:29.0`.
    """
    import gzip
    import urllib.request

    url = f"{s['url']}/dists/{s['dist']}/{s['comp']}/binary-amd64/Packages.gz"
    _schreib(f"Lese {url}\n")
    with urllib.request.urlopen(url, timeout=120) as antwort:  # noqa: S310 — feste Quelle
        text = gzip.decompress(antwort.read()).decode("utf-8", "replace")
    gewollt = set(s["neueste"].split())
    beste: dict[str, str] = {}
    for block in text.split("\n\n"):
        felder = dict(z.split(": ", 1) for z in block.splitlines() if ": " in z)
        name, version = felder.get("Package", ""), felder.get("Version", "")
        if name not in gewollt or not version:
            continue
        if name not in beste or subprocess.run(
                ["dpkg", "--compare-versions", version, "gt", beste[name]]).returncode == 0:
            beste[name] = version
    if not beste:
        raise RuntimeError(f"In {url} keines der Pakete {sorted(gewollt)} gefunden")
    _schreib("Neueste: " + ", ".join(f"{n} {v}" for n, v in sorted(beste.items())) + "\n")
    return " | ".join(f"Name (= {n}), $Version (= {v})" for n, v in sorted(beste.items()))


def _abgleich() -> None:
    meta = _meta()
    vorhanden = set(_lauf(["aptly", "mirror", "list", "-raw"], pruefen=False).split())
    stempel = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    ergebnis = {"zeit": _jetzt(), "spiegel": {}}
    _schreib(f"Abgleich {stempel} — {'Vollspiegel' if not FILTER else 'gefiltert: ' + FILTER}\n\n")

    for s in SPIEGEL:
        name = s["name"]
        filt = _neueste_filter(s) if s.get("neueste") else (s.get("filter") or FILTER)
        if s.get("schluessel"):
            # Fremde Quelle: ihren Schlüssel holen, damit aptly sie prüfen kann.
            _lauf(["sh", "-c", f"curl -fsSL {s['schluessel']} | gpg --batch --no-default-keyring "
                               f"--keyring trustedkeys.gpg --import"], protokoll=True, pruefen=False)
        filterargs = [f"-filter={filt}", "-filter-with-deps"] if filt else ["-filter="]
        if name not in vorhanden:
            _lauf(["aptly", "mirror", "create", "-architectures=amd64", *filterargs,
                   name, s["url"], s["dist"], s.get("quell_comp", s["comp"])], protokoll=True)
        else:
            _lauf(["aptly", "mirror", "edit", *filterargs, name], protokoll=True)
        _lauf(["aptly", "mirror", "update", "-max-tries=3", name], protokoll=True)

        snap = f"auto-{stempel}-{name}"
        _lauf(["aptly", "snapshot", "create", snap, "from", "mirror", name], protokoll=True)
        _veroeffentlichen(snap, s["prefix"], s["dist"], s["comp"])
        meta["aktuell"][name] = snap
        _meta_schreiben(meta)
        _auto_wegraeumen(name, snap, protokoll=True)
        info = _lauf(["aptly", "mirror", "show", name], pruefen=False)
        ergebnis["spiegel"][name] = _zahl(info, "Number of packages")
        _schreib(f"→ {name}: {ergebnis['spiegel'][name]} Pakete veröffentlicht\n\n")

    _lauf(["aptly", "db", "cleanup"], protokoll=True)
    meta = _meta()
    meta["abgleiche"] = (meta["abgleiche"] + [ergebnis])[-50:]
    _meta_schreiben(meta)


@app.post("/abgleich", dependencies=[Depends(require_token)])
def abgleich() -> dict[str, str]:
    return _im_hintergrund("Abgleich", _abgleich)


# --------------------------------------------------------- Eigene Pakete

def _eigen_veroeffentlichen() -> None:
    fpr = _schluessel_fpr()
    if (EIGEN["prefix"], EIGEN["dist"]) in _veroeffentlicht():
        _lauf(["aptly", "publish", "update", "-batch", f"-gpg-key={fpr}",
               EIGEN["dist"], EIGEN["prefix"]])
    else:
        _lauf(["aptly", "publish", "repo", "-batch", f"-gpg-key={fpr}",
               f"-distribution={EIGEN['dist']}", f"-component={EIGEN['comp']}",
               EIGEN["name"], EIGEN["prefix"]])


@app.post("/pakete", dependencies=[Depends(require_token)])
async def hochladen(datei: UploadFile = File(...), von: str = Form("")) -> dict[str, Any]:
    """Ein .deb annehmen: prüfen, ins eigene Repo legen, signiert veröffentlichen."""
    EINGANG.mkdir(parents=True, exist_ok=True)
    ziel = EINGANG / f"{secrets.token_hex(8)}.deb"
    pruefsumme = hashlib.sha256()
    groesse = 0
    with open(ziel, "wb") as fh:
        while True:
            stueck = await datei.read(1 << 20)
            if not stueck:
                break
            groesse += len(stueck)
            pruefsumme.update(stueck)
            fh.write(stueck)
    try:
        felder = subprocess.run(["dpkg-deb", "-f", str(ziel), "Package", "Version", "Architecture"],
                                capture_output=True, text=True, timeout=60)
        werte = dict(z.split(": ", 1) for z in felder.stdout.splitlines() if ": " in z)
        name, version, arch = (werte.get("Package", ""), werte.get("Version", ""),
                               werte.get("Architecture", ""))
        if felder.returncode != 0 or not name or not version:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                "Das ist kein gültiges Debian-Paket (.deb) — "
                                "Name und Version liessen sich nicht lesen.")
        if arch not in ("amd64", "all"):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                f"Architektur „{arch}“ passt nicht — die Arbeitsplätze sind amd64.")
        if not PAKET_OK.match(name) or not FASSUNG_OK.match(version):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                "Name oder Fassung entsprechen nicht den Regeln von Debian.")
        sperre = _synchron("Upload")
        try:
            gleiche = _lauf(["aptly", "repo", "search", "ota",
                             f"Name (= {name}), $Version (= {version})"], pruefen=False)
            if f"{name}_{version}_" in gleiche:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    f"{name} {version} ist schon im Repository. Eine neue Fassung braucht "
                    "eine neue Versionsnummer — sonst sähen Arbeitsplätze unter derselben "
                    "Version verschiedene Inhalte.")
            _lauf(["aptly", "repo", "add", "ota", str(ziel)])
            _eigen_veroeffentlichen()
            meta = _meta()
            meta["pakete"][f"{name}_{version}_{arch}"] = {
                "name": name, "version": version, "arch": arch, "groesse": groesse,
                "sha256": pruefsumme.hexdigest(), "von": von, "zeit": _jetzt()}
            _meta_schreiben(meta)
        finally:
            sperre.release()
    finally:
        ziel.unlink(missing_ok=True)
    return {"name": name, "version": version, "arch": arch, "sha256": pruefsumme.hexdigest()}


@app.get("/pakete", dependencies=[Depends(require_token)])
def pakete() -> list[dict[str, Any]]:
    aus = _lauf(["aptly", "repo", "show", "-with-packages", "ota"], pruefen=False)
    meta = _meta()["pakete"]
    raus = []
    teil = aus.split("Packages:", 1)[1] if "Packages:" in aus else ""
    for zeile in teil.splitlines():
        schluessel = zeile.strip()
        if not schluessel or schluessel.count("_") < 2:
            continue
        name, version, arch = schluessel.split("_", 2)
        raus.append({"schluessel": schluessel, "name": name, "version": version, "arch": arch,
                     **{k: v for k, v in meta.get(schluessel, {}).items()
                        if k in ("groesse", "sha256", "von", "zeit")}})
    return sorted(raus, key=lambda p: (p["name"], p["version"]))


@app.delete("/pakete/{schluessel}", dependencies=[Depends(require_token)])
def paket_loeschen(schluessel: str) -> dict[str, str]:
    if schluessel.count("_") != 2:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ungültiger Paketschlüssel")
    name, version, arch = schluessel.split("_", 2)
    if not PAKET_OK.match(name) or not FASSUNG_OK.match(version) or arch not in ("amd64", "all"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ungültiger Paketschlüssel")
    sperre = _synchron("Löschen")
    try:
        _lauf(["aptly", "repo", "remove", "ota",
               f"Name (= {name}), $Version (= {version}), $Architecture (= {arch})"])
        _eigen_veroeffentlichen()
        meta = _meta()
        meta["pakete"].pop(schluessel, None)
        _meta_schreiben(meta)
    finally:
        sperre.release()
    return {"status": f"{name} {version} entfernt"}


# ---------------------------------------------------------------- Snapshots

class SnapshotIn(BaseModel):
    name: str
    notiz: str = ""
    von: str = ""


def _snapshot_teile() -> list[dict[str, str]]:
    return [*SPIEGEL, EIGEN]


@app.post("/snapshots", dependencies=[Depends(require_token)])
def snapshot_anlegen(body: SnapshotIn) -> dict[str, Any]:
    """Den ausgelieferten Stand festhalten — Spiegel und eigenes Repo zusammen.

    Veröffentlicht wird er zusätzlich unter `snap/<name>/…`, damit Bauten
    gegen genau diesen Stand laufen können. aptly legt dafür Hardlinks an;
    Platz kostet nur, was sich danach ändert.
    """
    if not NAME_OK.match(body.name):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Name: Kleinbuchstaben, Ziffern und Bindestriche, höchstens 41 Zeichen.")
    sperre = _synchron("Snapshot")
    try:
        meta = _meta()
        if body.name in meta["snapshots"]:
            raise HTTPException(status.HTTP_409_CONFLICT, f"Snapshot „{body.name}“ gibt es schon.")
        teile = []
        for t in _snapshot_teile():
            ziel = f"fest-{body.name}-{t['name']}"
            if t is EIGEN:
                _lauf(["aptly", "snapshot", "create", ziel, "from", "repo", "ota"])
            else:
                quelle = meta["aktuell"].get(t["name"])
                if not quelle:
                    continue  # Dieser Spiegel wurde noch nie abgeglichen.
                _lauf(["aptly", "snapshot", "merge", ziel, quelle])
            _veroeffentlichen(ziel, f"snap/{body.name}/{t['prefix']}", t["dist"], t["comp"],
                              protokoll=False)
            teile.append(t["name"])
        meta["snapshots"][body.name] = {"zeit": _jetzt(), "notiz": body.notiz, "von": body.von,
                                        "teile": teile}
        _meta_schreiben(meta)
        return {"name": body.name, "teile": teile}
    finally:
        sperre.release()


@app.delete("/snapshots/{name}", dependencies=[Depends(require_token)])
def snapshot_loeschen(name: str) -> dict[str, str]:
    if not NAME_OK.match(name):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ungültiger Name")
    sperre = _synchron("Snapshot löschen")
    try:
        meta = _meta()
        if name not in meta["snapshots"]:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Snapshot nicht gefunden")
        if any(v == f"fest-{name}-{k}" for k, v in meta["aktuell"].items()):
            raise HTTPException(status.HTTP_409_CONFLICT,
                                "Auf diesen Stand ist gerade zurückgedreht. Erst abgleichen "
                                "(das schaltet auf einen neuen Stand), dann löschen.")
        for t in _snapshot_teile():
            _lauf(["aptly", "publish", "drop", t["dist"], f"snap/{name}/{t['prefix']}"],
                  pruefen=False)
            _lauf(["aptly", "snapshot", "drop", f"fest-{name}-{t['name']}"], pruefen=False)
        _lauf(["aptly", "db", "cleanup"], pruefen=False)
        meta["snapshots"].pop(name, None)
        _meta_schreiben(meta)
        return {"status": f"Snapshot {name} gelöscht"}
    finally:
        sperre.release()


@app.post("/snapshots/{name}/zurueckdrehen", dependencies=[Depends(require_token)])
def zurueckdrehen(name: str) -> dict[str, str]:
    """Die Spiegel wieder auf diesen Stand ausliefern. Eigene Pakete bleiben
    beim aktuellen Stand — die verwaltet man einzeln."""
    sperre = _synchron("Zurückdrehen")
    try:
        meta = _meta()
        if name not in meta["snapshots"]:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Snapshot nicht gefunden")
        for s in SPIEGEL:
            ziel = f"fest-{name}-{s['name']}"
            if s["name"] not in meta["snapshots"][name]["teile"]:
                continue
            _veroeffentlichen(ziel, s["prefix"], s["dist"], s["comp"], protokoll=False)
            meta["aktuell"][s["name"]] = ziel
            _auto_wegraeumen(s["name"], "")
        _meta_schreiben(meta)
        return {"status": f"Die Spiegel liefern wieder den Stand „{name}“ aus."}
    finally:
        sperre.release()


# ----------------------------------------------------------------- Dateien

def _dateien_liste() -> list[dict[str, Any]]:
    raus = []
    if DATEIEN.is_dir():
        for pfad in sorted(DATEIEN.rglob("*")):
            # Der pip-Index unter pip/simple/ verweist nur auf dieselben Räder.
            if pfad.is_file() and not pfad.relative_to(DATEIEN).parts[:2] == ("pip", "simple"):
                raus.append({"pfad": str(pfad.relative_to(DATEIEN)),
                             "groesse": pfad.stat().st_size})
    return raus


def _holen(url: str, ziel: Path, sha256: str = "") -> None:
    ziel.parent.mkdir(parents=True, exist_ok=True)
    tmp = ziel.with_suffix(ziel.suffix + ".teil")
    _lauf(["curl", "-fsSL", "--retry", "3", "-o", str(tmp), url], protokoll=True)
    if sha256:
        ist = hashlib.sha256(tmp.read_bytes()).hexdigest()
        if ist != sha256:
            tmp.unlink(missing_ok=True)
            raise RuntimeError(f"Prüfsumme von {ziel.name} stimmt nicht ({ist})")
    tmp.replace(ziel)
    _schreib(f"→ {ziel.relative_to(DATEIEN)} ({ziel.stat().st_size} Bytes)\n")


def _dateien_holen() -> None:
    _schreib("Selkies-Abhängigkeiten, clipnotify und Sysbox für das Aufsetzen ohne Internet\n\n")
    _holen("https://github.com/cdown/clipnotify/archive/refs/heads/master.tar.gz",
           DATEIEN / "clipnotify" / "clipnotify.tar.gz")
    _holen(f"https://github.com/nestybox/sysbox/releases/download/v{SYSBOX_VERSION}/"
           f"sysbox-ce_{SYSBOX_VERSION}.linux_amd64.deb",
           DATEIEN / "sysbox" / f"sysbox-ce_{SYSBOX_VERSION}.linux_amd64.deb", SYSBOX_SHA256)

    # Die Abhängigkeiten von Selkies — genau die Liste, gegen die das
    # Basisimage gebaut wird (third_party/selkies/ota-abhaengigkeiten.txt, in
    # diesen Dienst eingehängt), mit Prüfsumme. Selkies selbst liegt als
    # Quellcode in OTAs Repository und braucht hier nichts. Dieser Dienst läuft
    # auf Debian 13 mit Python 3.13 — derselben Fassung wie das Basisimage,
    # also passen die Räder.
    if not SELKIES_LISTE.is_file():
        raise RuntimeError(f"{SELKIES_LISTE} fehlt — ist third_party/selkies eingehängt?")
    ziel = DATEIEN / "selkies" / SELKIES_VERSION / "raeder"
    teil = ziel.with_name("raeder.teil")
    shutil.rmtree(teil, ignore_errors=True)
    teil.mkdir(parents=True)
    with tempfile.TemporaryDirectory() as tmp:
        _lauf(["python3", "-m", "venv", f"{tmp}/venv"], protokoll=True)
        _lauf([f"{tmp}/venv/bin/pip", "download", "--dest", str(teil), "--no-deps",
               "--only-binary=:all:", "--require-hashes", "-r", str(SELKIES_LISTE)],
              protokoll=True, zeit=1800)
    # Erst wenn alles da und geprüft ist, ersetzt es den alten Stand — ein
    # abgebrochener Lauf lässt einen vollständigen Vorrat stehen.
    shutil.rmtree(ziel, ignore_errors=True)
    teil.rename(ziel)
    _schreib(f"→ selkies/{SELKIES_VERSION}/raeder: {len(list(ziel.glob('*.whl')))} Räder, "
             "jedes gegen seine Prüfsumme geprüft\n")


@app.post("/dateien", dependencies=[Depends(require_token)])
def dateien_holen() -> dict[str, str]:
    return _im_hintergrund("Dateien holen", _dateien_holen)
