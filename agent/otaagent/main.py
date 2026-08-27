"""OTA-Agent — der einzige Dienst mit Zugriff auf den Docker-Socket.

Bewusst schmal gehalten: Er nimmt konkrete Auftraege entgegen ("starte diesen
Container mit diesen Grenzen") und trifft keine Entscheidungen darueber, wer
was darf. Das passiert in der API.
"""

from __future__ import annotations

import base64
import logging
import os
import shutil
import secrets
import threading
from typing import Any

import docker
from docker.errors import APIError, ImageNotFound, NotFound
from fastapi import (
    Depends, FastAPI, File, Form, Header, HTTPException, Response, UploadFile, status,
)
from pydantic import BaseModel, Field

from . import apps as app_scripts
from . import backup as backup_ops
from . import builder
from . import clipboard as clip_scripts
from . import discover
from . import shared as shared_store

AGENT_TOKEN = os.environ.get("OTA_AGENT_TOKEN", "")
PROFILES_ROOT = os.environ.get("OTA_PROFILES_ROOT", "/srv/ota/profiles")
# Ablage fuer Dateien, die in Session-Container gemountet werden. Muss im
# Agent und auf dem Host unter demselben Pfad liegen — Docker loest Bind-Mounts
# gegen den Host auf, nicht gegen den Container, der sie anfordert.
RUNTIME_ROOT = os.environ.get("OTA_RUNTIME_ROOT", "/srv/ota/runtime")
# Adresse der eigenen Registry. Leer schaltet sie ab.
REGISTRY = os.environ.get("OTA_REGISTRY", "").strip()
# Gemeinsame Ablage. Liegt in jedem Session-Container **nur lesbar** — sie ist
# der Weg der Administration zu den Nutzern, nicht umgekehrt.
SHARED_ROOT = os.environ.get("OTA_SHARED_ROOT", "/srv/ota/shared")
SHARED_MOUNT = "/mnt/ota"
SESSION_NETWORK = os.environ.get("OTA_SESSION_NETWORK", "ota_sessions")
PUBLIC_NETWORK = os.environ.get("OTA_PUBLIC_NETWORK", "ota_public")

log = logging.getLogger("ota.agent")

app = FastAPI(title="OTA Agent", docs_url=None, redoc_url=None)
_client: docker.DockerClient | None = None


# Was `custom_startup.sh` in einem Arbeitsplatz tun soll: nichts.
#
# Die Kasm-Images fuer einzelne Anwendungen bringen ein `custom_startup.sh`
# mit, das "ihre" Anwendung startet. `vnc_startup.sh` beaufsichtigt dieses
# Skript und startet es **alle drei Sekunden neu**, sobald es sich beendet —
# der Kommentar dort sagt ausdruecklich: "custom startup scripts track the
# target process on their own, they should not exit".
#
# In einem abgeleiteten Arbeitsplatz-Image ist das verheerend. Gemessen am
# 2026-08-27 mit `ota/arbeitsplatz:v1` (abgeleitet von kasmweb/vs-code):
# Das geerbte Skript startete `code`, VS Code ist einzelinstanzig, die zweite
# Instanz reichte den Aufruf an die erste weiter und beendete sich — worauf
# die Aufsicht sie erneut startete. Ergebnis nach sechs Minuten: 119 leere
# VS-Code-Fenster, 2,5 GB belegt, der Bildschirm zeigte nur noch Schwarz.
#
# Ein Arbeitsplatz startet seine Anwendungen selbst, auf Zuruf. Das geerbte
# Skript wird deshalb ueberdeckt — durch eines, das einfach wartet und damit
# die Aufsicht zufriedenstellt.
WORKSPACE_STARTUP = """#!/usr/bin/env bash
# Von OpenTerminalApps eingehaengt. Ersetzt das custom_startup.sh des
# Basisimages, damit im Arbeitsplatz keine Anwendung von selbst startet.
# Anwendungen startet der OTA-Agent auf Zuruf, jede auf ihrem Display.
#
# Das Skript darf sich nicht beenden: vnc_startup.sh startet es sonst alle
# drei Sekunden neu.
while true; do sleep 3600; done
"""


def _workspace_startup_file() -> str:
    """Legt das Ersatzskript ab und gibt seinen Pfad zurueck."""
    os.makedirs(RUNTIME_ROOT, exist_ok=True)
    path = os.path.join(RUNTIME_ROOT, "workspace-startup.sh")
    current = ""
    try:
        with open(path, encoding="utf-8") as fh:
            current = fh.read()
    except OSError:
        pass
    if current != WORKSPACE_STARTUP:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(WORKSPACE_STARTUP)
    os.chmod(path, 0o755)
    return path


def dc() -> docker.DockerClient:
    global _client
    if _client is None:
        _client = docker.from_env()
    return _client


def require_token(x_agent_token: str = Header(default="")) -> None:
    # secrets.compare_digest verhindert, dass die Laufzeit etwas ueber den
    # Token verraet.
    if not AGENT_TOKEN or not secrets.compare_digest(x_agent_token, AGENT_TOKEN):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Agent-Token ungültig")


class StartRequest(BaseModel):
    session_id: str
    image: str
    cores: float = Field(gt=0)
    memory_bytes: int = Field(gt=0)
    env: dict[str, str] = {}
    profile_path: str = ""
    vnc_user: str = "kasm_user"
    vnc_secret: str
    mode: str = "workspace"
    labels: dict[str, str] = {}
    # Laeuft nach dem Start als Nutzer im Container. Siehe _run_start_script.
    start_script: str = ""
    # Darf der Anwender in seinem eigenen Container root werden? Setzt die
    # API fuer Administratoren. Siehe `_elevate()` — das ist eine bewusste
    # Lockerung, keine Nebenwirkung.
    elevated: bool = False


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/host", dependencies=[Depends(require_token)])
def host_info() -> dict[str, Any]:
    """Was der Host gerade hergibt. Grundlage fuer den Kapazitaets-Preflight."""
    info = dc().info()
    total = int(info.get("MemTotal", 0))

    # MemAvailable aus /proc ist die ehrliche Zahl: Es beruecksichtigt
    # zurueckgewinnbaren Cache, anders als "MemFree".
    available = 0
    try:
        with open("/proc/meminfo", encoding="ascii") as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    available = int(line.split()[1]) * 1024
                    break
    except OSError:
        available = total

    usage = shutil.disk_usage("/")
    return {
        "cores": info.get("NCPU", 0),
        "memory_total": total,
        "memory_available": available,
        "disk_total": usage.total,
        "disk_free": usage.free,
        "architecture": info.get("Architecture", ""),
        "docker_version": info.get("ServerVersion", ""),
        "running_containers": info.get("ContainersRunning", 0),
    }


# --------------------------------------------------------------------------
# Gemeinsame Ablage (siehe shared.py)
# --------------------------------------------------------------------------

class SharedNameRequest(BaseModel):
    path: str = ""
    name: str


def _shared(fn, *args):
    try:
        return fn(*args)
    except shared_store.SharedError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@app.get("/shared", dependencies=[Depends(require_token)])
def shared_list(path: str = "") -> dict[str, Any]:
    return _shared(shared_store.listing, path)


@app.post("/shared/upload", dependencies=[Depends(require_token)])
async def shared_upload(path: str = Form(default=""),
                        file: UploadFile = File(...)) -> dict[str, Any]:
    data = await file.read()
    return _shared(shared_store.save, path, file.filename or "datei", data)


@app.post("/shared/dir", dependencies=[Depends(require_token)])
def shared_mkdir(req: SharedNameRequest) -> dict[str, Any]:
    return _shared(shared_store.make_dir, req.path, req.name)


@app.delete("/shared", dependencies=[Depends(require_token)])
def shared_remove(path: str) -> dict[str, Any]:
    return _shared(shared_store.remove, path)


@app.get("/shared/file", dependencies=[Depends(require_token)])
def shared_read(path: str) -> Response:
    name, data = _shared(shared_store.read, path)
    return Response(
        content=data, media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@app.get("/images/applications", dependencies=[Depends(require_token)])
def image_applications(ref: str) -> list[dict[str, Any]]:
    """Welche Anwendungen in diesem Image installiert sind.

    Gelesen aus den .desktop-Dateien des Images — siehe discover.py.
    """
    try:
        return discover.applications(ref)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@app.get("/images/packages", dependencies=[Depends(require_token)])
def image_packages(ref: str, names: str = "") -> list[dict[str, Any]]:
    """Kennt dieses Image diese Pakete? Siehe discover.check_packages."""
    wanted = [n.strip() for n in names.split(",") if n.strip()]
    try:
        return discover.check_packages(ref, wanted)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@app.get("/images", dependencies=[Depends(require_token)])
def list_images() -> list[dict[str, Any]]:
    out = []
    for img in dc().images.list():
        for tag in img.tags:
            out.append({"ref": tag, "size_bytes": img.attrs.get("Size", 0)})
    return sorted(out, key=lambda i: i["ref"])


def _ensure_profile(path: str) -> None:
    """Legt das Profilverzeichnis an und setzt UID/GID 1000.

    Die Kasm-Images laufen als Nutzer 1000. Ohne diesen Schritt kann der
    Container in sein eigenes Home nicht schreiben.
    """
    if not path:
        return
    os.makedirs(path, exist_ok=True)
    try:
        os.chown(path, 1000, 1000)
    except PermissionError:
        pass


@app.post("/containers", dependencies=[Depends(require_token)])
def start_container(req: StartRequest) -> dict[str, Any]:
    client = dc()

    try:
        client.images.get(req.image)
    except ImageNotFound:
        # Aus der eigenen Registry nachholen, statt abzulehnen. Das ist der
        # Punkt, an dem sich die Registry auszahlt: Ein Host, der ein Golden
        # Image nie gebaut hat, kann es trotzdem starten.
        if not _fetch_from_registry(client, req.image):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Das Image {req.image} liegt nicht auf diesem Host und ist "
                "auch nicht in der Registry. Hole es unter Verwaltung → Images.",
            )

    env = dict(req.env)
    env.setdefault("VNC_PW", req.vnc_secret)
    env.setdefault("VNC_VIEW_ONLY_PW", secrets.token_urlsafe(16))
    # Ohne Verzoegerung zwischen Zwischenablage-Aktionen (plan.md §10.1).
    env.setdefault("VNCOPTIONS", "-PreferBandwidth -DynamicQualityMin=4 "
                                 "-DynamicQualityMax=7 -DLP_ClipDelay=0")

    mounts = []
    if req.mode == "workspace":
        # Siehe WORKSPACE_STARTUP: Das geerbte Startskript wuerde die
        # Anwendung des Basisimages im Drei-Sekunden-Takt neu starten.
        try:
            mounts.append(docker.types.Mount(
                target="/dockerstartup/custom_startup.sh",
                source=_workspace_startup_file(),
                type="bind", read_only=True,
            ))
        except OSError as exc:
            log.warning("Arbeitsplatz-Startskript nicht ablegbar: %s", exc)

    if req.profile_path:
        _ensure_profile(req.profile_path)
        mounts.append(docker.types.Mount(
            target="/home/kasm-user", source=req.profile_path, type="bind",
        ))

    # Die gemeinsame Ablage, nur lesbar. Sie haengt **nicht** im Home: Ein
    # Verzeichnis, das der Nutzer nicht beschreiben kann, mitten in seinem
    # eigenen Zuhause verwirrt mehr, als es hilft. Statt dessen ein eigener
    # Ort und ein Verweis darauf (siehe _link_shared).
    if os.path.isdir(SHARED_ROOT):
        mounts.append(docker.types.Mount(
            target=SHARED_MOUNT, source=SHARED_ROOT, type="bind", read_only=True,
        ))

    try:
        container = client.containers.run(
            req.image,
            detach=True,
            name=f"ota-s-{req.session_id[:12]}",
            environment=env,
            mounts=mounts,
            network=SESSION_NETWORK,
            labels=req.labels,
            nano_cpus=int(req.cores * 1_000_000_000),
            mem_limit=req.memory_bytes,
            # Grosszuegig, weil Browser und Electron-Anwendungen sonst
            # unvermittelt abstuerzen.
            shm_size="1g",
            # Administratoren duerfen in ihrem Container root werden — sonst
            # koennten sie nichts nachinstallieren. Das kostet zwei Sperren:
            #
            #   no-new-privileges  verhindert *jede* Rechteerhoehung, auch die
            #       ueber setuid. Mit dieser Sperre laeuft `sudo` gar nicht an.
            #   cap_drop ALL       nimmt unter anderem SETUID und SETGID; ohne
            #       die kann sudo den Benutzer nicht wechseln.
            #
            # Fuer alle anderen bleibt beides scharf. Wer nicht administriert,
            # bekommt auch keinen Weg zu root.
            security_opt=[] if req.elevated else ["no-new-privileges:true"],
            cap_drop=[] if req.elevated else ["ALL"],
            cap_add=["SYS_ADMIN"] if req.mode == "workspace" and not req.elevated else [],
            pids_limit=4096,
            restart_policy={"Name": "no"},
        )
    except APIError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Docker meldet: {exc}") from exc

    # Der Session-Container muss auch fuer Traefik erreichbar sein.
    try:
        client.networks.get(PUBLIC_NETWORK).connect(container.id)
    except (NotFound, APIError):
        pass

    if req.elevated:
        _elevate(container)

    _wait_for_vnc(container)
    _link_shared(container)
    if req.start_script.strip():
        _run_start_script(container, req.start_script)

    container.reload()
    return {"container_id": container.id, "status": container.status}


def _link_shared(container) -> None:
    """Legt einen Verweis auf die gemeinsame Ablage ins Home.

    Der eigentliche Einhaengepunkt liegt ausserhalb des Home, damit niemand
    ein unbeschreibbares Verzeichnis mitten in seinen eigenen Dateien hat.
    Findbar soll die Ablage trotzdem sein — deshalb der Verweis.

    Nur wenn dort noch nichts liegt: Wer einen eigenen Ordner „Gemeinsam"
    angelegt hat, behaelt ihn.
    """
    script = (
        f'[ -d {SHARED_MOUNT} ] || exit 0; '
        '[ -e "$HOME/Gemeinsam" ] && exit 0; '
        f'ln -s {SHARED_MOUNT} "$HOME/Gemeinsam"'
    )
    try:
        container.exec_run(["bash", "-lc", script], user="1000")
    except APIError as exc:
        log.warning("Verweis auf die Ablage nicht angelegt: %s", exc)


def _run_start_script(container, script: str) -> None:
    """Fuehrt das Startskript der Vorlage als Nutzer aus.

    Als Nutzer und nicht als root: Es geht um das Home, und was dort entsteht,
    soll dem Nutzer gehoeren. Ein Skript, das mit root-Rechten in ein
    Nutzerverzeichnis schreibt, hinterlaesst Dateien, die der Nutzer nicht
    mehr aendern kann — ein Fehler, der erst Wochen spaeter auffaellt.

    Scheitert es, wird der Start **nicht** abgebrochen. Der Arbeitsplatz laeuft
    ja; ihn wegen einer misslungenen Einrichtung ganz zu verweigern waere die
    schlechtere Antwort. Die Ausgabe steht im Container unter
    /tmp/ota-start.log und im Agent-Protokoll.
    """
    payload = base64.b64encode(script.encode("utf-8")).decode("ascii")
    # Ueber base64 statt direkt: Das Skript kommt aus einem Textfeld und
    # enthaelt Anfuehrungszeichen, Zeilenumbrueche und Dollarzeichen. Alles
    # davon wuerde beim Einbetten in eine Kommandozeile etwas anderes tun.
    runner = (
        f'echo {payload} | base64 -d > /tmp/ota-start.sh && '
        'chmod +x /tmp/ota-start.sh && '
        'exec bash /tmp/ota-start.sh > /tmp/ota-start.log 2>&1'
    )
    try:
        res = container.exec_run(
            ["bash", "-lc", runner], user="1000",
            environment={"HOME": "/home/kasm-user", "OTA_SHARED": SHARED_MOUNT},
        )
        if res.exit_code != 0:
            out = (res.output or b"").decode("utf-8", "replace")
            log.warning("Startskript in %s endete mit %s: %s",
                        container.name, res.exit_code, out[-400:])
    except APIError as exc:
        log.warning("Startskript nicht ausfuehrbar: %s", exc)


def _fetch_from_registry(client: docker.DockerClient, ref: str) -> bool:
    """Holt ein fehlendes Image, wenn es in der eigenen Registry liegt.

    Nur fuer Adressen, die auf genau diese Registry zeigen. Ein beliebiges
    Image aus dem Netz nachzuladen, weil beim Start eines auffiel, waere ein
    stiller Griff nach draussen — das gehoert in eine bewusste Handlung
    (Verwaltung → Images), nicht in einen Sessionstart.
    """
    if not REGISTRY or not ref.startswith(f"{REGISTRY}/"):
        return False
    try:
        log.info("Hole %s aus der Registry", ref)
        client.images.pull(ref)
        client.images.get(ref)
        return True
    except (APIError, ImageNotFound) as exc:
        log.warning("Registry-Abruf fuer %s gescheitert: %s", ref, exc)
        return False


def _wait_for_vnc(container, seconds: int = 40) -> bool:
    """Wartet, bis KasmVNC im Container Verbindungen annimmt.

    Ohne das meldet die API die Session als bereit, sobald Docker den Container
    gestartet hat — der Webserver darin braucht danach aber noch ein paar
    Sekunden. Wer sofort hinschaut, bekommt 502 und denkt, es sei kaputt.

    Geprueft wird von innen mit Bordmitteln: Bash kann ueber /dev/tcp eine
    Verbindung aufbauen. Das braucht kein zusaetzliches Werkzeug im Image und
    keinen Netzwerkweg vom Agent zum Container.
    """
    probe = (
        f"for i in $(seq 1 {seconds * 2}); do "
        "(exec 3<>/dev/tcp/127.0.0.1/6901) 2>/dev/null && exit 0; "
        "sleep 0.5; done; exit 1"
    )
    try:
        code, _out = _run_as_root(container, ["bash", "-lc", probe])
        if code != 0:
            log.warning("KasmVNC in %s war nach %ss noch nicht bereit",
                        container.name, seconds)
        return code == 0
    except APIError as exc:
        log.warning("Bereitschaft nicht pruefbar: %s", exc)
        return False


def _elevate(container) -> None:
    """Gibt dem Anwender im Container passwortloses sudo.

    Als Datei unter /etc/sudoers.d und nicht per `usermod -aG sudo`: Die
    Kasm-Images legen die Gruppe nicht in jedem Fall an, und eine eigene Datei
    ist beim Nachsehen sofort als von OTA gesetzt zu erkennen.

    Scheitert das, ist es kein Grund, den Start abzubrechen — dann hat jemand
    eben kein sudo und merkt das beim ersten Versuch. Ein Container, der gar
    nicht erst hochkommt, waere das schlechtere Ergebnis.
    """
    script = (
        "printf '%s\\n' 'kasm-user ALL=(ALL) NOPASSWD:ALL' "
        "> /etc/sudoers.d/ota-admin && chmod 0440 /etc/sudoers.d/ota-admin"
    )
    try:
        code, out = _run_as_root(container, ["bash", "-lc", script])
        if code != 0:
            log.warning("sudo konnte nicht eingerichtet werden: %s", out[:200])
    except APIError as exc:
        log.warning("sudo konnte nicht eingerichtet werden: %s", exc)


def _run_as_root(container, cmd: list[str]) -> tuple[int, str]:
    res = container.exec_run(cmd, user="root", demux=False)
    return res.exit_code, (res.output or b"").decode("utf-8", "replace")


@app.get("/containers/{cid}", dependencies=[Depends(require_token)])
def container_status(cid: str) -> dict[str, Any]:
    try:
        c = dc().containers.get(cid)
    except NotFound:
        return {"status": "gone"}
    c.reload()
    state = c.attrs.get("State", {})
    return {
        "status": c.status,
        "exit_code": state.get("ExitCode"),
        "started_at": state.get("StartedAt"),
        "oom_killed": state.get("OOMKilled", False),
    }


# Eigener Pfadabschnitt statt eines freien Platzhalters. Ein
# "/containers/{cid}/{action}" wuerde jede weitere Unterroute verdecken —
# etwa /containers/{cid}/apps, die dann als Aktion "apps" ankaeme.
@app.post("/containers/{cid}/action/{action}", dependencies=[Depends(require_token)])
def container_action(cid: str, action: str) -> dict[str, str]:
    if action not in {"pause", "unpause", "stop", "start", "restart"}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unbekannte Aktion")
    try:
        c = dc().containers.get(cid)
        getattr(c, action)()
    except NotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Container nicht gefunden")
    except APIError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    return {"status": action}


@app.delete("/containers/{cid}", dependencies=[Depends(require_token)])
def remove_container(cid: str) -> dict[str, str]:
    try:
        c = dc().containers.get(cid)
        c.remove(force=True)
    except NotFound:
        pass
    except APIError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    return {"status": "removed"}


@app.get("/orphans", dependencies=[Depends(require_token)])
def orphans() -> list[dict[str, str]]:
    """Container mit OTA-Kennzeichnung. Die API vergleicht sie mit der Datenbank."""
    out = []
    for c in dc().containers.list(all=True, filters={"label": "ota.session_id"}):
        out.append({
            "container_id": c.id,
            "session_id": c.labels.get("ota.session_id", ""),
            "status": c.status,
        })
    return out


class ExecRequest(BaseModel):
    cmd: list[str]


@app.post("/containers/{cid}/exec", dependencies=[Depends(require_token)])
def exec_in_container(cid: str, req: ExecRequest) -> dict[str, Any]:
    """Fuehrt einen Befehl im Container aus — fuer App-Starts im Arbeitsplatz."""
    try:
        c = dc().containers.get(cid)
        result = c.exec_run(req.cmd, detach=False, demux=False)
    except NotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Container nicht gefunden")
    except APIError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    output = result.output.decode("utf-8", "replace") if result.output else ""
    return {"exit_code": result.exit_code, "output": output[-4000:]}


# --------------------------------------------------------------------------
# Arbeitsplatz: Anwendungen auf eigenen Displays (plan.md §9.2)
# --------------------------------------------------------------------------

class AppStartRequest(BaseModel):
    slug: str
    command: str
    # Ab 1, nicht ab 2: Einzelinstanz-Anwendungen gehoeren auf den
    # Hauptbildschirm des Containers. Das Startskript legt auf einem bereits
    # offenen Display kein zweites an.
    display: int = Field(ge=1, le=9)
    geometry: str = "1280x720"
    title: str = "OTA"
    send_primary: bool = False


def _run(container, cmd: list[str]) -> tuple[int, str]:
    result = container.exec_run(cmd, user="1000", demux=False)
    return result.exit_code, (result.output or b"").decode("utf-8", "replace")


@app.post("/containers/{cid}/apps", dependencies=[Depends(require_token)])
def start_app(cid: str, req: AppStartRequest) -> dict[str, Any]:
    """Startet ein Display und darauf die Anwendung.

    Beides bei Bedarf: Ein Arbeitsplatz ohne geoeffnete Anwendung haelt kein
    einziges Display offen und kostet damit fast nichts.
    """
    try:
        container = dc().containers.get(cid)
    except NotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Container nicht gefunden")

    port = 6900 + req.display

    code, out = _run(container, app_scripts.display_script(
        req.display, port, req.geometry, req.title, req.send_primary,
    ))
    if code != 0 or "display-failed" in out:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f"Der Bildschirm für {req.slug} liess sich nicht starten: {out[-300:]}",
        )

    code, out = _run(container, app_scripts.app_script(req.display, req.slug, req.command))
    if code != 0:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f"{req.slug} liess sich nicht starten: {out[-300:]}",
        )

    return {"display": req.display, "port": port, "result": out.strip().splitlines()[-1:] or ["ok"]}


@app.delete("/containers/{cid}/apps/{display}", dependencies=[Depends(require_token)])
def stop_app(cid: str, display: int) -> dict[str, str]:
    try:
        container = dc().containers.get(cid)
    except NotFound:
        return {"status": "gone"}
    _run(container, app_scripts.stop_script(display))
    return {"status": "stopped"}


@app.get("/containers/{cid}/apps", dependencies=[Depends(require_token)])
def list_displays(cid: str) -> list[int]:
    """Welche Displays im Container gerade offen sind."""
    try:
        container = dc().containers.get(cid)
    except NotFound:
        return []
    _, out = _run(container, ["bash", "-lc", "ls /tmp/.X11-unix/ 2>/dev/null || true"])
    return sorted(int(x[1:]) for x in out.split() if x.startswith("X") and x[1:].isdigit())


# --------------------------------------------------------------------------
# Zwischenablage-Bruecke (plan.md §10.4)
# --------------------------------------------------------------------------

class BridgeRequest(BaseModel):
    enabled: bool = True
    interval: float = Field(default=0.5, ge=0.2, le=5.0)


@app.post("/containers/{cid}/clipboard-bridge", dependencies=[Depends(require_token)])
def clipboard_bridge(cid: str, req: BridgeRequest) -> dict[str, str]:
    """Startet oder stoppt die Spiegelung der Zwischenablage.

    Sie folgt den Rechten des Workspace: Ist das Kopieren dort abgeschaltet,
    laeuft die Bruecke bewusst nicht.
    """
    try:
        container = dc().containers.get(cid)
    except NotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Container nicht gefunden")

    if not req.enabled:
        _run(container, clip_scripts.stop_script())
        return {"status": "gestoppt"}

    code, out = _run(container, clip_scripts.install_script(req.interval))
    if code != 0 or "bridge-failed" in out:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f"Die Zwischenablage-Brücke liess sich nicht starten: {out[-200:]}",
        )
    return {"status": "läuft"}


# --------------------------------------------------------------------------
# Golden Images bauen (plan.md §8)
# --------------------------------------------------------------------------

class BuildRequest(BaseModel):
    tag: str
    base_image: str
    apt_packages: list[str] = []
    vscode_extensions: list[str] = []
    setup_script: str = ""
    # Arbeitsplatz oder Einzelanwendung. Entscheidet, ob das Startskript des
    # Basisimages ueberschrieben wird — siehe builder.render_dockerfile.
    mode: str = "workspace"
    # Container, die waehrend des Builds angehalten werden. Siehe builder._pause.
    pause_containers: list[str] = []


@app.post("/builds", dependencies=[Depends(require_token)])
def start_build(req: BuildRequest) -> dict[str, Any]:
    if builder.busy():
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Es läuft bereits ein Build. Sie laufen bewusst nacheinander, damit "
            "der Host die Sessions weiter bedienen kann.",
        )
    try:
        dc().images.get(req.base_image)
    except ImageNotFound:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Das Basisimage {req.base_image} liegt nicht auf diesem Host.",
        )
    return builder.start(
        req.tag, req.base_image, req.apt_packages,
        req.vscode_extensions, req.setup_script, req.pause_containers, req.mode,
    )


@app.get("/builds/{build_id}", dependencies=[Depends(require_token)])
def build_status(build_id: str) -> dict[str, Any]:
    state = builder.status(build_id)
    if state is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Build nicht gefunden")
    return state


# Laufende und abgeschlossene Ladevorgaenge. Ein Kasm-Image bringt ein bis
# drei Gigabyte mit; das dauert Minuten, und solange darf die Oberflaeche
# nicht auf eine Antwort warten.
_pulls: dict[str, dict[str, Any]] = {}


class PullRequest(BaseModel):
    ref: str


def _pull_worker(job_id: str, ref: str) -> None:
    state = _pulls[job_id]
    try:
        # low-level API statt images.pull(): Nur die liefert den Fortschritt
        # schichtweise, und ohne den steht die Oberflaeche minutenlang still.
        for chunk in dc().api.pull(ref, stream=True, decode=True):
            if "error" in chunk:
                state.update(status="failed", detail=str(chunk["error"]))
                return
            note = chunk.get("status") or ""
            layer = chunk.get("id")
            state["detail"] = f"{note} {layer}".strip() if layer else note
        image = dc().images.get(ref)
        state.update(status="ok", detail="geladen",
                     size_bytes=image.attrs.get("Size", 0))
    except (APIError, ImageNotFound) as exc:
        state.update(status="failed", detail=str(exc))
    except Exception as exc:  # noqa: BLE001 — der Arbeiter darf nie sterben
        state.update(status="failed", detail=str(exc))


@app.post("/images/pull", dependencies=[Depends(require_token)])
def pull_image(req: PullRequest) -> dict[str, Any]:
    """Holt ein Image aus seiner Registry auf diesen Host."""
    ref = req.ref.strip()
    if not ref:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Keine Adresse angegeben.")

    job_id = secrets.token_hex(8)
    _pulls[job_id] = {"id": job_id, "ref": ref, "status": "running",
                      "detail": "wird begonnen", "size_bytes": 0}
    threading.Thread(target=_pull_worker, args=(job_id, ref), daemon=True).start()
    return _pulls[job_id]


@app.get("/images/pull/{job_id}", dependencies=[Depends(require_token)])
def pull_status(job_id: str) -> dict[str, Any]:
    state = _pulls.get(job_id)
    if state is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ladevorgang nicht gefunden")
    return state


@app.delete("/images/{ref:path}", dependencies=[Depends(require_token)])
def remove_image(ref: str) -> dict[str, str]:
    """Entfernt eine alte Golden-Image-Version."""
    try:
        dc().images.remove(ref, force=False)
    except ImageNotFound:
        return {"status": "war nicht vorhanden"}
    except APIError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Image nicht entfernbar: {exc}")
    return {"status": "entfernt"}


@app.get("/images/exists/{ref:path}", dependencies=[Depends(require_token)])
def image_exists(ref: str) -> dict[str, Any]:
    """Liegt dieses Image im Image-Store?

    Gebraucht fuer die Nachpruefung nach einem Build: Auf einem Host, auf dem
    ein anderes System Images aufraeumt, kann ein erfolgreich gebautes Image
    Sekunden spaeter wieder verschwunden sein.
    """
    try:
        image = dc().images.get(ref)
    except ImageNotFound:
        return {"exists": False}
    return {"exists": True, "size_bytes": image.attrs.get("Size", 0)}


# --------------------------------------------------------------------------
# Sicherung und Wiederherstellung (plan.md §11.2)
# --------------------------------------------------------------------------

class ProfileBackupRequest(BaseModel):
    username: str
    scope: str = "user"


class ProfileRestoreRequest(BaseModel):
    username: str
    archive: str
    scope: str = "user"


class ContainerBackupRequest(BaseModel):
    container_id: str
    username: str
    template_slug: str


class ContainerRestoreRequest(BaseModel):
    container_id: str
    archive: str


@app.get("/backups/root", dependencies=[Depends(require_token)])
def backup_root() -> dict[str, Any]:
    return backup_ops.root_info()


@app.get("/backups/files", dependencies=[Depends(require_token)])
def backup_files() -> list[dict[str, Any]]:
    return backup_ops.list_files()


@app.post("/backups/profile", dependencies=[Depends(require_token)])
def backup_profile(req: ProfileBackupRequest) -> dict[str, Any]:
    try:
        return backup_ops.backup_profile(req.username, req.scope)
    except FileNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                            f"Sicherung fehlgeschlagen: {exc}") from exc


@app.post("/backups/profile/restore", dependencies=[Depends(require_token)])
def restore_profile(req: ProfileRestoreRequest) -> dict[str, Any]:
    try:
        return backup_ops.restore_profile(req.username, req.archive, req.scope)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                            f"Wiederherstellung fehlgeschlagen: {exc}") from exc


@app.post("/backups/container", dependencies=[Depends(require_token)])
def backup_container(req: ContainerBackupRequest) -> dict[str, Any]:
    try:
        container = dc().containers.get(req.container_id)
    except NotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Container nicht gefunden")
    try:
        return backup_ops.backup_container(container, req.username, req.template_slug)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                            f"Sicherung fehlgeschlagen: {exc}") from exc


@app.post("/backups/container/restore", dependencies=[Depends(require_token)])
def restore_container(req: ContainerRestoreRequest) -> dict[str, Any]:
    try:
        container = dc().containers.get(req.container_id)
    except NotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Container nicht gefunden")
    try:
        return backup_ops.restore_container(container, req.archive)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                            f"Wiederherstellung fehlgeschlagen: {exc}") from exc


class DatabaseBackupRequest(BaseModel):
    db_container: str
    db_user: str
    db_name: str


@app.post("/backups/database", dependencies=[Depends(require_token)])
def backup_database(req: DatabaseBackupRequest) -> dict[str, Any]:
    try:
        container = dc().containers.get(req.db_container)
    except NotFound:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Der Datenbank-Container {req.db_container} läuft nicht.",
        )
    try:
        return backup_ops.backup_database(container, req.db_user, req.db_name)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                            f"Datenbanksicherung fehlgeschlagen: {exc}") from exc


@app.delete("/backups/file", dependencies=[Depends(require_token)])
def delete_backup(path: str) -> dict[str, str]:
    try:
        return backup_ops.delete_file(path)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
