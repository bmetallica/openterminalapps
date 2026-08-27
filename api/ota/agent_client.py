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
    try:
        with httpx.Client(timeout=60.0) as client:
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


def list_images() -> list[dict[str, Any]]:
    return _call("GET", "/images")


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


def stop_app(cid: str, display: int) -> dict[str, Any]:
    return _call("DELETE", f"/containers/{cid}/apps/{display}")


def clipboard_bridge(cid: str, enabled: bool, interval: float = 0.5) -> dict[str, Any]:
    return _call("POST", f"/containers/{cid}/clipboard-bridge",
                 json={"enabled": enabled, "interval": interval})


def start_build(payload: dict[str, Any]) -> dict[str, Any]:
    return _call("POST", "/builds", json=payload)


def build_status(build_id: str) -> dict[str, Any]:
    return _call("GET", f"/builds/{build_id}")


def remove_image(ref: str) -> dict[str, Any]:
    return _call("DELETE", f"/images/{ref}")


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
