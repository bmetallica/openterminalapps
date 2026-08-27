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


class PasswordIn(BaseModel):
    password: str


class LocaleIn(BaseModel):
    locale: str


class TotpSetupOut(BaseModel):
    # Das Geheimnis geht mit, damit es auch von Hand eingetippt werden kann —
    # nicht jede Umgebung laesst das Abscannen eines Codes zu.
    secret: str
    uri: str
    qr_svg: str


class TotpActivateIn(BaseModel):
    secret: str
    code: str


class TotpDisableIn(BaseModel):
    password: str
    code: str


class TotpCodesOut(BaseModel):
    codes: list[str]


class GroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    slug: str
    priority: int
    permissions: list[str] = []
    member_count: int = 0
    is_system: bool = False


class GroupIn(BaseModel):
    name: str = Field(min_length=2, max_length=128)
    description: str | None = None
    priority: int = Field(default=100, ge=1, le=9999)
    permissions: list[str] = []


class SessionAdminOut(BaseModel):
    id: uuid.UUID
    username: str
    template_name: str
    template_icon: str
    status: str
    cores: float
    memory_bytes: int
    started_at: datetime
    last_seen_at: datetime
    app_count: int = 0


class MeOut(BaseModel):
    id: uuid.UUID
    username: str
    display_name: str | None
    is_admin: bool
    permissions: list[str]
    groups: list[str]
    locale: str
    must_change_password: bool
    # Ist der zweite Faktor eingerichtet, und wie viele Rueckfallcodes sind
    # noch uebrig? Das Geheimnis selbst verlaesst den Server nie.
    totp_enabled: bool = False
    recovery_left: int = 0


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
    start_script: str = ""
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
    start_script: str = ""
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


class BuildIn(BaseModel):
    # Leer bedeutet: das derzeitige Image der Vorlage als Basis nehmen.
    base_image: str = ""
    apt_packages: list[str] = []
    vscode_extensions: list[str] = []
    setup_script: str = ""
    comment: str = ""
    # Fremde Aufräumdienste für die Dauer des Builds anhalten. Standardmässig
    # an, weil ein Golden Image sonst auf diesem Host keine Minute überlebt.
    pause_foreign_cleanup: bool = True


class BuildOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    version: int
    base_image: str
    apt_packages: list[str]
    vscode_extensions: list[str]
    setup_script: str
    comment: str
    status: str
    log: str
    image_ref: str | None
    size_bytes: int
    is_current: bool
    built_by: str | None
    started_at: datetime
    finished_at: datetime | None


class BackupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    kind: str
    username: str | None
    template_slug: str | None
    path: str | None
    size_bytes: int
    file_count: int
    status: str
    error: str | None
    log: str
    trigger: str
    actor: str | None
    started_at: datetime
    finished_at: datetime | None


class BackupRunIn(BaseModel):
    # Ohne Namen werden alle aktiven Nutzer gesichert.
    username: str | None = None
    include_container: bool = False
    # Nur die Datenbank sichern, ohne Profile.
    database_only: bool = False


class BackupPolicyIn(BaseModel):
    is_enabled: bool = False
    hour: int = Field(default=3, ge=0, le=23)
    minute: int = Field(default=30, ge=0, le=59)
    weekdays: list[int] = []
    include_profiles: bool = True
    include_containers: bool = False
    include_database: bool = True
    keep_daily: int = Field(default=7, ge=1, le=90)
    keep_weekly: int = Field(default=4, ge=0, le=52)


class BackupPolicyOut(BackupPolicyIn):
    model_config = ConfigDict(from_attributes=True)
    last_run_at: datetime | None = None
    last_result: str | None = None


class BackupStorageOut(BaseModel):
    path: str
    writable: bool
    # Liegt hier bereits ein Netzlaufwerk (NFS, CIFS) oder noch die lokale Platte?
    is_network: bool = False
    fstype: str = ""
    source: str = ""
    disk_total: int
    disk_free: int
    used_by_backups: int


class HostOut(BaseModel):
    cores: int
    memory_total: int
    memory_available: int
    disk_total: int
    disk_free: int
    docker_version: str = ""
    architecture: str = ""
    running_containers: int = 0


class HelpChapter(BaseModel):
    slug: str
    title: str
    section: str


class HelpPage(BaseModel):
    slug: str
    title: str
    markdown: str


class SettingsIn(BaseModel):
    # Optional, damit spaetere Einstellungen einzeln gesetzt werden koennen,
    # ohne die uebrigen mitzuschicken.
    auth_idle_minutes: int | None = None


class ImagePullIn(BaseModel):
    ref: str


class RecipeIn(BaseModel):
    name: str
    glyph: str = "▢"
    why: str = ""
    kind: str = "script"
    params: dict = {}
    # Leer heisst: aus kind und params erzeugen. Gefuellt heisst: so nehmen.
    script: str = ""


class RecipePreviewIn(BaseModel):
    kind: str
    params: dict = {}


class RecipeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    slug: str
    name: str
    glyph: str
    why: str
    kind: str
    params: dict
    script: str
    is_builtin: bool
    created_by: str | None


class SharedDirIn(BaseModel):
    path: str = ""
    name: str
