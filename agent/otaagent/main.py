"""OTA-Agent — der einzige Dienst mit Zugriff auf den Docker-Socket.

Bewusst schmal gehalten: Er nimmt konkrete Auftraege entgegen ("starte diesen
Container mit diesen Grenzen") und trifft keine Entscheidungen darueber, wer
was darf. Das passiert in der API.
"""

from __future__ import annotations

import os
import shutil
import secrets
from typing import Any

import docker
from docker.errors import APIError, ImageNotFound, NotFound
from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

from . import apps as app_scripts
from . import backup as backup_ops
from . import builder
from . import clipboard as clip_scripts

AGENT_TOKEN = os.environ.get("OTA_AGENT_TOKEN", "")
PROFILES_ROOT = os.environ.get("OTA_PROFILES_ROOT", "/srv/ota/profiles")
SESSION_NETWORK = os.environ.get("OTA_SESSION_NETWORK", "ota_sessions")
PUBLIC_NETWORK = os.environ.get("OTA_PUBLIC_NETWORK", "ota_public")

app = FastAPI(title="OTA Agent", docs_url=None, redoc_url=None)
_client: docker.DockerClient | None = None


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
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Das Image {req.image} liegt nicht auf diesem Host. "
            "Es muss zuerst geladen werden.",
        )

    env = dict(req.env)
    env.setdefault("VNC_PW", req.vnc_secret)
    env.setdefault("VNC_VIEW_ONLY_PW", secrets.token_urlsafe(16))
    # Ohne Verzoegerung zwischen Zwischenablage-Aktionen (plan.md §10.1).
    env.setdefault("VNCOPTIONS", "-PreferBandwidth -DynamicQualityMin=4 "
                                 "-DynamicQualityMax=7 -DLP_ClipDelay=0")

    mounts = []
    if req.profile_path:
        _ensure_profile(req.profile_path)
        mounts.append(docker.types.Mount(
            target="/home/kasm-user", source=req.profile_path, type="bind",
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
            security_opt=["no-new-privileges:true"],
            cap_drop=["ALL"],
            cap_add=["SYS_ADMIN"] if req.mode == "workspace" else [],
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

    container.reload()
    return {"container_id": container.id, "status": container.status}


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
    display: int = Field(ge=2, le=9)
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
        req.vscode_extensions, req.setup_script, req.pause_containers,
    )


@app.get("/builds/{build_id}", dependencies=[Depends(require_token)])
def build_status(build_id: str) -> dict[str, Any]:
    state = builder.status(build_id)
    if state is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Build nicht gefunden")
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
