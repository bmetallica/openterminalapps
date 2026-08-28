from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


def _adresse(wert: object) -> str:
    """Eine E-Mail-Adresse pruefen — mit Mass.

    Bewusst **nicht** `EmailStr`. Dessen Vorgabe verlangt eine Adresse, die im
    Internet zustellbar waere, und lehnt damit `chef@firma.local`,
    `admin@ota.internal` und alles unter `.test` ab. OTA ist ein Werkzeug fuers
    interne Netz; dort sind solche Adressen der Normalfall, und Internetregeln
    darauf anzuwenden hiesse, die Haelfte der Anlagen auszusperren.

    Geprueft wird deshalb die **Form** — ein @-Zeichen, ein brauchbarer Teil
    davor und dahinter —, nicht die Erreichbarkeit. Ob jemand seine Post
    bekommt, entscheidet sein Mailserver und nicht dieses Feld.
    """
    import email_validator
    from email_validator import EmailNotValidError, validate_email

    # `.local` und `.internal` sind in Firmennetzen der Normalfall — die
    # Bibliothek lehnt sie ab, weil sie im Internet nicht zustellbar waeren.
    # Genau das ist hier aber egal. `localhost`, `arpa` und `onion` bleiben
    # draussen: Die sind auch intern keine Adresse.
    email_validator.SPECIAL_USE_DOMAIN_NAMES = ["arpa", "localhost", "onion"]

    text = str(wert or "").strip()
    if not text:
        raise ValueError("Eine E-Mail-Adresse wird gebraucht.")
    try:
        geprueft = validate_email(text, check_deliverability=False,
                                  globally_deliverable=False)
    except EmailNotValidError as exc:
        raise ValueError(f"Das ist keine E-Mail-Adresse: {exc}") from exc
    return str(geprueft.normalized)


Adresse = Annotated[str, BeforeValidator(_adresse)]


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
    require_totp: bool = False


class GroupIn(BaseModel):
    name: str = Field(min_length=2, max_length=128)
    description: str | None = None
    priority: int = Field(default=100, ge=1, le=9999)
    permissions: list[str] = []
    require_totp: bool = False


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
    # Eine Gruppe verlangt den zweiten Faktor, er ist aber nicht eingerichtet.
    must_setup_totp: bool = False


class AppOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    slug: str
    name: str
    icon: str
    registry_hint: str | None = None
    blocked_reason: str | None = None
    is_enabled: bool = True
    fixed_display: int | None = None
    group_ids: list[uuid.UUID] = []
    # NULL heisst: die Aufloesung des Arbeitsplatzes.
    x_res: int | None = None
    y_res: int | None = None


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
    skeleton_enforce: list[str] = []
    user_shelf: bool = True
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
    skeleton_enforce: list[str] = []
    user_shelf: bool = True
    is_enabled: bool = True
    # `None` heisst „nicht mitgeschickt" und laesst die Zuweisung stehen; eine
    # leere Liste heisst „niemand mehr". Ohne diese Unterscheidung nimmt ein
    # PUT, das die Zuweisung gar nicht erwaehnt, sie allen weg — und der
    # Workspace verschwindet wortlos von jedem Dashboard. Genau das ist am
    # 2026-08-28 passiert.
    group_ids: list[uuid.UUID] | None = None


class WebAppOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    name: str
    description: str
    icon: str
    url: str
    redirect_uri: str
    client_id: str
    is_enabled: bool
    sort_order: int
    group_ids: list[uuid.UUID] = []
    # Nur beim Anlegen gefuellt. Danach steht es allein in Keycloak — ein
    # zweiter Ort waere ein zweiter Ort, an dem es verlorengehen kann.
    client_secret: str | None = None


class WebAppIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str = ""
    description: str = ""
    icon: str = "\u25c7"
    url: str = Field(min_length=8)
    redirect_uri: str = Field(min_length=8)
    is_enabled: bool = True
    sort_order: int = 0
    group_ids: list[uuid.UUID] | None = None


class KcVerzeichnisIn(BaseModel):
    """Eine Verzeichnisanbindung, wie sie die Oberfläche schickt.

    Das Kennwort geht nur hinein. Leer heisst „nicht anfassen" — nicht
    „löschen": Sonst verlöre eine Änderung an der Adresse nebenbei die
    Zugangsdaten, und das fiele erst bei der nächsten Anmeldung auf.
    """
    server_uri: str = Field(min_length=3)
    base_dn: str = Field(min_length=3)
    bind_dn: str = ""
    bind_password: str = ""
    user_filter: str = ""
    login_attribute: str = ""
    kind: str = "ad"
    is_enabled: bool = True


class OidcTokenIn(BaseModel):
    """Ein ID-Token von Keycloak als Nachweis, wer da anklopft.

    Ausdrücklich das ID-Token: Es ist die Aussage über eine Person, und nur
    dort steht seit Keycloak 26 die Kennung (`sub`).
    """
    id_token: str = Field(min_length=16)


class OnceRunOut(BaseModel):
    """Ein Lauf, wie ihn die Verwaltung sieht."""
    model_config = ConfigDict(from_attributes=True)

    username: str
    ran_at: datetime
    exit_code: int
    output: str


class OnceScriptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    body: str
    is_enabled: bool
    sort_order: int
    created_at: datetime
    # Zusammenfassung statt roher Liste: Was die Verwaltung wissen will, ist
    # „bei wie vielen ist es gelaufen und bei wem ging es schief".
    ran_count: int = 0
    failed: list[OnceRunOut] = []


class OnceScriptIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    body: str = ""
    is_enabled: bool = True
    sort_order: int = 0


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
    # Leer heisst: fuer alle, die den Arbeitsplatz sehen.
    group_ids: list[uuid.UUID] = []
    # NULL heisst: die Aufloesung des Arbeitsplatzes.
    x_res: int | None = Field(default=None, ge=640, le=7680)
    y_res: int | None = Field(default=None, ge=480, le=4320)


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
    """Ein Konto, wie es die Verwaltung anlegt oder aendert.

    **Die E-Mail ist Pflicht.** Sie war es lange nicht, und das ging so lange
    gut, wie OTA das einzige war, das die Konten kannte. Seit sie an fremde
    Anwendungen weitergereicht wird, ist ein Konto ohne Adresse ein Konto, das
    sich dort nicht anmelden kann — gemessen an Open WebUI, das die Anmeldung
    mit „email is missing" abweist und dabei von einem falschen Passwort
    spricht. Aus einem Verzeichnis kommt sie ohnehin mit.
    """

    username: str = Field(min_length=2, max_length=128)
    display_name: str | None = None
    email: Adresse
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


class FreezeIn(BaseModel):
    comment: str = ""
    # Ausdrueckliche Bestaetigung, dass die als Geheimnis markierten Dateien
    # ins Image duerfen. Ohne sie wird abgelehnt — eine Vorschau, die man
    # uebergehen kann, ist Dekoration.
    trotz_geheimnissen: bool = False


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
    app_origins: list[str] | None = None
    # 0 heisst jeweils: keine Grenze.
    profile_quota_gb: int | None = None
    disk_floor_gb: int | None = None


class IdentityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    is_enabled: bool = False
    server_uri: str = ""
    tls_mode: str = "starttls"
    tls_verify: bool = True
    ca_cert: str = ""
    bind_dn: str = ""
    # Das Kennwort selbst kommt nie zurueck.
    has_bind_password: bool = False
    base_dn: str = ""
    login_attribute: str = "uid"
    user_filter: str = "(objectClass=inetOrgPerson)"
    mail_attribute: str = "mail"
    name_attribute: str = "cn"
    group_base_dn: str = ""
    group_filter: str = "(objectClass=groupOfNames)"
    member_attribute: str = "member"
    group_name_attribute: str = "cn"
    group_map: dict = {}
    jit_create: bool = True
    sync_enabled: bool = True
    last_sync_at: datetime | None = None
    last_error: str | None = None


class IdentityIn(BaseModel):
    # Alles optional: Die Oberflaeche schickt, was sie geaendert hat.
    is_enabled: bool | None = None
    server_uri: str | None = None
    tls_mode: str | None = None
    tls_verify: bool | None = None
    ca_cert: str | None = None
    bind_dn: str | None = None
    # Leer heisst „nicht geaendert", nicht „loeschen".
    bind_password: str | None = None
    base_dn: str | None = None
    login_attribute: str | None = None
    user_filter: str | None = None
    mail_attribute: str | None = None
    name_attribute: str | None = None
    group_base_dn: str | None = None
    group_filter: str | None = None
    member_attribute: str | None = None
    group_name_attribute: str | None = None
    group_map: dict | None = None
    jit_create: bool | None = None
    sync_enabled: bool | None = None


class IdentityTestIn(BaseModel):
    # Ein Name, an dem sich zeigen laesst, was das Verzeichnis liefert.
    probe_login: str = ""


class SkeletonDirIn(BaseModel):
    path: str = ""
    name: str


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


class RegistryIn(BaseModel):
    url: str
    schema_version: str = "1.1"
    auto_update: bool = False


class RegistryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    url: str
    schema_version: str
    icon_url: str | None
    is_enabled: bool
    auto_update: bool
    last_fetched_at: datetime | None
    workspace_count: int
    fetch_error: str | None
    entry_count: int = 0
    imported_count: int = 0


class RegistryEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    sha: str
    friendly_name: str
    description: str
    categories: list
    architectures: list
    icon_url: str | None
    image_ref: str
    available_tags: list
    uncompressed_size_mb: int
    imported_template_id: uuid.UUID | None


class RegistryImportIn(BaseModel):
    sha: str
    # Leer heisst: die Fassung nehmen, die der Katalog vorschlaegt.
    tag: str | None = None
    cores: float = Field(default=2.0, gt=0, le=64)
    memory_bytes: int = Field(default=2 * 1024**3, gt=0)
