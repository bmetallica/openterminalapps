"""Schmaler Client zum Agent. Die API fasst Docker nie direkt an."""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import HTTPException, status

from .config import settings


def _headers() -> dict[str, str]:
    return {"X-Agent-Token": settings().agent_token}


def _call(method: str, path: str, **kw: Any) -> Any:
    url = f"{settings().agent_url.rstrip('/')}{path}"
    # Grosszuegig, weil hier auch Dateien durchgehen: Ein Gigabyte in die
    # gemeinsame Ablage braucht laenger als eine Minute.
    timeout = kw.pop("timeout", None) or (300.0 if "files" in kw else 60.0)
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.request(method, url, headers=_headers(), **kw)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Der Container-Dienst ist nicht erreichbar. Läuft ota-agent?",
        ) from exc

    if resp.status_code >= 400:
        detail = "Unbekannter Fehler im Container-Dienst"
        try:
            detail = resp.json().get("detail", detail)
        except Exception:
            detail = resp.text[:300] or detail
        raise HTTPException(resp.status_code, detail)
    return resp.json()


def host_info() -> dict[str, Any]:
    return _call("GET", "/host")


# `app` waehlt den Teilbaum einer einzelnen Anwendung. Leer heisst: das
# Skeleton des Workspace selbst.

def skeleton_list(slug: str, path: str = "", app: str = "") -> dict[str, Any]:
    from urllib.parse import quote
    return _call("GET", f"/skeleton/{slug}?pfad={quote(path)}&app_slug={quote(app)}")


def skeleton_upload(slug: str, path: str, name: str, data: bytes,
                    app: str = "") -> dict[str, Any]:
    return _call("POST", f"/skeleton/{slug}/upload",
                 data={"pfad": path, "app_slug": app},
                 files={"files": (name, data)})


def skeleton_mkdir(slug: str, path: str, name: str, app: str = "") -> dict[str, Any]:
    return _call("POST", f"/skeleton/{slug}/dir",
                 json={"pfad": path, "name": name, "app_slug": app})


def skeleton_remove(slug: str, path: str, app: str = "") -> dict[str, Any]:
    from urllib.parse import quote
    return _call("DELETE", f"/skeleton/{slug}?pfad={quote(path)}&app_slug={quote(app)}")


def freeze_preview(container_id: str) -> dict[str, Any]:
    return _call("GET", f"/freeze/{container_id}/preview")


def freeze_commit(body: dict[str, Any]) -> dict[str, Any]:
    # Ein Container mit fuenf Gigabyte braucht fuer `docker commit` und das
    # anschliessende Ablegen in der Registry Minuten, nicht Sekunden.
    return _call("POST", "/freeze", json=body, timeout=1800.0)


def profile_usage(username: str, fresh: bool = False) -> dict[str, Any]:
    suffix = "?fresh=true" if fresh else ""
    return _call("GET", f"/profiles/{username}/usage{suffix}")


def list_images() -> list[dict[str, Any]]:
    return _call("GET", "/images")


def image_applications(ref: str) -> list[dict[str, Any]]:
    return _call("GET", "/images/applications", params={"ref": ref})


def image_packages(ref: str, names: list[str]) -> list[dict[str, Any]]:
    return _call("GET", "/images/packages",
                 params={"ref": ref, "names": ",".join(names)})


def start_container(payload: dict[str, Any]) -> dict[str, Any]:
    return _call("POST", "/containers", json=payload)


def container_status(cid: str) -> dict[str, Any]:
    return _call("GET", f"/containers/{cid}")


def container_action(cid: str, action: str) -> dict[str, Any]:
    return _call("POST", f"/containers/{cid}/action/{action}")


def remove_container(cid: str) -> dict[str, Any]:
    return _call("DELETE", f"/containers/{cid}")


def orphans() -> list[dict[str, Any]]:
    return _call("GET", "/orphans")


def start_app(cid: str, payload: dict[str, Any]) -> dict[str, Any]:
    return _call("POST", f"/containers/{cid}/apps", json=payload)


def list_displays(cid: str) -> list[int]:
    return _call("GET", f"/containers/{cid}/apps")


def stop_app(cid: str, display: int, engine: str = "kasmvnc") -> dict[str, Any]:
    return _call("DELETE", f"/containers/{cid}/apps/{display}?engine={engine}")


def clipboard_bridge(cid: str, enabled: bool, interval: float = 0.5) -> dict[str, Any]:
    return _call("POST", f"/containers/{cid}/clipboard-bridge",
                 json={"enabled": enabled, "interval": interval})


def start_build(payload: dict[str, Any]) -> dict[str, Any]:
    return _call("POST", "/builds", json=payload)


def build_status(build_id: str) -> dict[str, Any]:
    return _call("GET", f"/builds/{build_id}")


def remove_image(ref: str) -> dict[str, Any]:
    return _call("DELETE", f"/images/{ref}")


def registry_fetch(url: str, schema_version: str = "1.1") -> dict[str, Any]:
    return _call("POST", "/registry/fetch",
                 json={"url": url, "schema_version": schema_version})


def registry_icon(url: str, base: str) -> tuple[bytes, str]:
    """Das Symbol und sein Typ. Kein JSON, deshalb der eigene Weg."""
    import httpx

    endpoint = f"{settings().agent_url.rstrip('/')}/registry/icon"
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(endpoint, headers=_headers(),
                          params={"url": url, "base": base})
    if resp.status_code >= 400:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Symbol nicht verfügbar")
    return resp.content, resp.headers.get("content-type", "image/png")


# --- Gemeinsame Ablage ---------------------------------------------------

def shared_list(path: str = "") -> dict[str, Any]:
    return _call("GET", "/shared", params={"path": path})


def shared_upload(path: str, name: str, data: bytes) -> dict[str, Any]:
    return _call("POST", "/shared/upload", data={"path": path},
                 files={"file": (name, data)})


def shared_mkdir(path: str, name: str) -> dict[str, Any]:
    return _call("POST", "/shared/dir", json={"path": path, "name": name})


def shared_remove(path: str) -> dict[str, Any]:
    return _call("DELETE", "/shared", params={"path": path})


def shared_read(path: str) -> tuple[bytes, str]:
    """Der Inhalt einer Datei und ihr Name.

    Anders als die uebrigen Aufrufe kommt hier kein JSON zurueck, sondern die
    Datei selbst — deshalb der eigene Weg an `_call` vorbei.
    """
    import httpx

    url = f"{settings().agent_url.rstrip('/')}/shared/file"
    with httpx.Client(timeout=300.0) as client:
        resp = client.get(url, headers=_headers(), params={"path": path})
    if resp.status_code >= 400:
        raise HTTPException(resp.status_code, "Die Datei liess sich nicht lesen.")
    name = path.rsplit("/", 1)[-1] or "datei"
    return resp.content, name


# --- Eigene Ablage je Nutzer ---------------------------------------------

def user_list(username: str, path: str = "") -> dict[str, Any]:
    return _call("GET", f"/userfiles/{username}", params={"path": path})


def user_upload(username: str, path: str, name: str, data: bytes) -> dict[str, Any]:
    return _call("POST", f"/userfiles/{username}/upload", data={"path": path},
                 files={"file": (name, data)})


def user_mkdir(username: str, path: str, name: str) -> dict[str, Any]:
    return _call("POST", f"/userfiles/{username}/dir",
                 json={"path": path, "name": name})


def user_remove(username: str, path: str) -> dict[str, Any]:
    return _call("DELETE", f"/userfiles/{username}", params={"path": path})


def user_read(username: str, path: str) -> tuple[bytes, str]:
    """Der Inhalt einer Datei und ihr Name. Kein JSON, deshalb der eigene Weg."""
    import httpx

    url = f"{settings().agent_url.rstrip('/')}/userfiles/{username}/file"
    with httpx.Client(timeout=300.0) as client:
        resp = client.get(url, headers=_headers(), params={"path": path})
    if resp.status_code >= 400:
        raise HTTPException(resp.status_code, "Die Datei liess sich nicht lesen.")
    name = path.rsplit("/", 1)[-1] or "datei"
    return resp.content, name


# --- Gruppenlaufwerke ----------------------------------------------------
#
# Wer in eine Gruppe gehoert, entscheidet die API (routers/groupfiles.py).
# Hier steht nur der Weg zum Agent.

def group_list(group_id: str, path: str = "") -> dict[str, Any]:
    return _call("GET", f"/groupfiles/{group_id}", params={"path": path})


def group_upload(group_id: str, path: str, name: str, data: bytes) -> dict[str, Any]:
    return _call("POST", f"/groupfiles/{group_id}/upload", data={"path": path},
                 files={"file": (name, data)})


def group_mkdir(group_id: str, path: str, name: str) -> dict[str, Any]:
    return _call("POST", f"/groupfiles/{group_id}/dir",
                 json={"path": path, "name": name})


def group_remove(group_id: str, path: str) -> dict[str, Any]:
    return _call("DELETE", f"/groupfiles/{group_id}", params={"path": path})


def group_read(group_id: str, path: str) -> tuple[bytes, str]:
    """Der Inhalt einer Datei und ihr Name. Kein JSON, deshalb der eigene Weg."""
    import httpx

    url = f"{settings().agent_url.rstrip('/')}/groupfiles/{group_id}/file"
    with httpx.Client(timeout=300.0) as client:
        resp = client.get(url, headers=_headers(), params={"path": path})
    if resp.status_code >= 400:
        raise HTTPException(resp.status_code, "Die Datei liess sich nicht lesen.")
    name = path.rsplit("/", 1)[-1] or "datei"
    return resp.content, name


def pull_image(ref: str) -> dict[str, Any]:
    return _call("POST", "/images/pull", json={"ref": ref})


def pull_status(job_id: str) -> dict[str, Any]:
    return _call("GET", f"/images/pull/{job_id}")


def image_exists(ref: str) -> dict[str, Any]:
    return _call("GET", f"/images/exists/{ref}")


# --- Sicherung ---------------------------------------------------------

def backup_root() -> dict[str, Any]:
    return _call("GET", "/backups/root")


def backup_files() -> list[dict[str, Any]]:
    return _call("GET", "/backups/files")


def backup_profile(username: str, scope: str = "user") -> dict[str, Any]:
    return _call("POST", "/backups/profile",
                 json={"username": username, "scope": scope})


def restore_profile(username: str, archive: str, scope: str = "user") -> dict[str, Any]:
    return _call("POST", "/backups/profile/restore",
                 json={"username": username, "archive": archive, "scope": scope})


def backup_container(container_id: str, username: str, template_slug: str) -> dict[str, Any]:
    return _call("POST", "/backups/container",
                 json={"container_id": container_id, "username": username,
                       "template_slug": template_slug})


def restore_container(container_id: str, archive: str) -> dict[str, Any]:
    return _call("POST", "/backups/container/restore",
                 json={"container_id": container_id, "archive": archive})


def delete_backup_file(path: str) -> dict[str, Any]:
    return _call("DELETE", "/backups/file", params={"path": path})


def backup_database(db_container: str, db_user: str, db_name: str) -> dict[str, Any]:
    return _call("POST", "/backups/database",
                 json={"db_container": db_container, "db_user": db_user,
                       "db_name": db_name})
