from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LoginIn(BaseModel):
    username: str
    password: str
    totp: str | None = None


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str


class GroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    slug: str
    priority: int
    permissions: list[str] = []
    member_count: int = 0
    is_system: bool = False


class MeOut(BaseModel):
    id: uuid.UUID
    username: str
    display_name: str | None
    is_admin: bool
    permissions: list[str]
    groups: list[str]
    locale: str
    must_change_password: bool


class AppOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    slug: str
    name: str
    icon: str
    registry_hint: str | None = None
    blocked_reason: str | None = None
    is_enabled: bool = True
    fixed_display: int | None = None


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    slug: str
    friendly_name: str
    description: str
    icon: str
    categories: list[str]
    mode: str
    image_ref: str
    cores: float
    memory_bytes: int
    x_res: int
    y_res: int
    idle_minutes: int
    idle_action: str
    persistence_scope: str
    rights: dict
    env: dict
    is_enabled: bool
    apps: list[AppOut] = []
    group_ids: list[uuid.UUID] = []
    # Was fuer den anfragenden Nutzer tatsaechlich gilt.
    effective_cores: float | None = None
    effective_memory_bytes: int | None = None


class TemplateIn(BaseModel):
    friendly_name: str
    description: str = ""
    icon: str = "▣"
    categories: list[str] = []
    mode: str = "workspace"
    image_ref: str
    cores: float = Field(gt=0, le=64)
    memory_bytes: int = Field(gt=0)
    x_res: int = 1280
    y_res: int = 720
    idle_minutes: int = 60
    idle_action: str = "stop"
    persistence_scope: str = "user"
    rights: dict = {}
    env: dict = {}
    is_enabled: bool = True
    group_ids: list[uuid.UUID] = []


class OverrideIn(BaseModel):
    scope: str
    target_id: uuid.UUID
    cores: float | None = None
    memory_bytes: int | None = None


class OverrideOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    scope: str
    target_id: uuid.UUID
    cores: float | None
    memory_bytes: int | None


class AllocationOut(BaseModel):
    """Was fuer einen Nutzer bei einem Template gilt, samt Herkunft."""
    user_id: uuid.UUID
    username: str
    cores: float
    memory_bytes: int
    cores_from: str
    memory_from: str
    has_own_override: bool


class StreamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    app_slug: str
    display_num: int
    status: str
    url: str = ""


class AppIn(BaseModel):
    slug: str
    name: str
    icon: str = "▢"
    exec_cmd: str
    exec_args: str = ""
    registry_hint: str | None = None
    blocked_reason: str | None = None
    is_enabled: bool = True
    # Fuer Einzelinstanz-Anwendungen, die das Image schon selbst startet.
    fixed_display: int | None = None


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    template_id: uuid.UUID
    template_name: str
    template_icon: str
    template_mode: str
    username: str
    status: str
    cores: float
    memory_bytes: int
    started_at: datetime
    last_seen_at: datetime
    error: str | None = None
    url: str
    streams: list[StreamOut] = []


class SessionStartIn(BaseModel):
    template_id: uuid.UUID


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    username: str
    display_name: str | None
    email: str | None
    is_active: bool
    is_locked: bool
    auth_provider: str
    last_login_at: datetime | None
    group_ids: list[uuid.UUID] = []


class UserIn(BaseModel):
    username: str = Field(min_length=2, max_length=128)
    display_name: str | None = None
    email: str | None = None
    password: str | None = None
    is_active: bool = True
    group_ids: list[uuid.UUID] = []


class HostOut(BaseModel):
    cores: int
    memory_total: int
    memory_available: int
    disk_total: int
    disk_free: int
    docker_version: str = ""
    architecture: str = ""
    running_containers: int = 0
