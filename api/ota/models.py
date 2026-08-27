"""Datenmodell nach plan.md §5 und §9.7.

Abweichung, bewusst: Rechte einer Gruppe liegen als JSON-Liste in
``Group.permissions`` statt in einer eigenen Tabelle mit Join. Bei der
Groessenordnung dieser Installation ist das funktional gleichwertig und
spart zwei Tabellen; die Schluessel sind in ``PERMISSIONS`` festgelegt.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# Bekannte Rechte. "admin" schliesst alle anderen ein.
PERMISSIONS = (
    "admin",
    "templates.manage",
    "images.manage",
    "users.manage",
    "groups.manage",
    "sessions.view_all",
    "settings.manage",
    "audit.view",
    "registries.manage",
)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255))
    display_name: Mapped[str | None] = mapped_column(String(255))

    password_hash: Mapped[str | None] = mapped_column(Text)
    auth_provider: Mapped[str] = mapped_column(String(32), default="local")
    external_id: Mapped[str | None] = mapped_column(String(255))

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)

    totp_secret: Mapped[str | None] = mapped_column(String(64))

    locale: Mapped[str] = mapped_column(String(8), default="de")
    theme: Mapped[str] = mapped_column(String(16), default="dark")

    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # Erzwingt Abmeldung aller Sitzungen, wenn hochgezaehlt.
    token_epoch: Mapped[int] = mapped_column(Integer, default=0)

    groups: Mapped[list[Group]] = relationship(
        secondary="group_members", back_populates="members", lazy="selectin"
    )

    @property
    def permissions(self) -> set[str]:
        out: set[str] = set()
        for g in self.groups:
            out.update(g.permissions or [])
        return out

    @property
    def is_admin(self) -> bool:
        return "admin" in self.permissions


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    slug: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    # Kleinere Zahl gewinnt bei widersprechenden Abweichungen.
    priority: Mapped[int] = mapped_column(Integer, default=100)
    permissions: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    members: Mapped[list[User]] = relationship(
        secondary="group_members", back_populates="groups", lazy="selectin"
    )


class GroupMember(Base):
    __tablename__ = "group_members"
    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )


class Template(Base):
    __tablename__ = "templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    slug: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    friendly_name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    icon: Mapped[str] = mapped_column(String(16), default="▣")
    categories: Mapped[list] = mapped_column(JSONB, default=list)

    # "workspace" = ein Linux je Nutzer mit mehreren Apps (Kern).
    # "single_app" = eine Anwendung als Wegwerf-Container (Feature).
    mode: Mapped[str] = mapped_column(String(16), default="workspace")

    image_ref: Mapped[str] = mapped_column(String(512))
    cores: Mapped[float] = mapped_column(Float, default=2.0)
    memory_bytes: Mapped[int] = mapped_column(BigInteger, default=2 * 1024**3)
    x_res: Mapped[int] = mapped_column(Integer, default=1280)
    y_res: Mapped[int] = mapped_column(Integer, default=720)

    env: Mapped[dict] = mapped_column(JSONB, default=dict)
    rights: Mapped[dict] = mapped_column(JSONB, default=dict)

    persistence_scope: Mapped[str] = mapped_column(String(16), default="user")
    idle_minutes: Mapped[int] = mapped_column(Integer, default=60)
    idle_action: Mapped[str] = mapped_column(String(16), default="stop")
    session_time_limit: Mapped[int | None] = mapped_column(Integer)

    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False)

    # Herkunft, falls aus einer Registry importiert.
    source_registry_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("registries.id", ondelete="SET NULL")
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    apps: Mapped[list[TemplateApp]] = relationship(
        back_populates="template", cascade="all, delete-orphan",
        lazy="selectin", order_by="TemplateApp.sort_order",
    )
    overrides: Mapped[list[TemplateOverride]] = relationship(
        back_populates="template", cascade="all, delete-orphan", lazy="selectin"
    )
    groups: Mapped[list[Group]] = relationship(secondary="group_templates", lazy="selectin")
    builds: Mapped[list[ImageBuild]] = relationship(
        back_populates="template", cascade="all, delete-orphan",
        lazy="selectin", order_by="ImageBuild.version.desc()",
    )


class TemplateApp(Base):
    """Eine im Arbeitsplatz installierte Anwendung (plan.md §9.5)."""

    __tablename__ = "template_apps"
    __table_args__ = (UniqueConstraint("template_id", "slug"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("templates.id", ondelete="CASCADE"), index=True
    )
    slug: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255))
    icon: Mapped[str] = mapped_column(String(16), default="▢")
    exec_cmd: Mapped[str] = mapped_column(String(512))
    exec_args: Mapped[str] = mapped_column(String(512), default="")
    # Nur informativ fuers UI: woher diese App ihre Erweiterungen bezieht.
    registry_hint: Mapped[str | None] = mapped_column(String(64))
    # Wenn gesetzt, ist die App gesperrt und der Text erklaert warum.
    blocked_reason: Mapped[str | None] = mapped_column(Text)
    # Manche Anwendungen sind Einzelinstanzen: Ein zweiter Aufruf meldet sich
    # nur bei der laufenden Instanz und beendet sich, statt ein neues Fenster
    # zu oeffnen — VS Code, Chrome und Thunderbird verhalten sich so. Startet
    # das Image eine solche Anwendung bereits selbst, traegt sie hier ihr
    # Display ein und OTA startet sie nicht erneut, sondern zeigt sie nur an.
    fixed_display: Mapped[int | None] = mapped_column(Integer)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    template: Mapped[Template] = relationship(back_populates="apps")


class GroupTemplate(Base):
    __tablename__ = "group_templates"
    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("templates.id", ondelete="CASCADE"), primary_key=True
    )


class TemplateOverride(Base):
    """Abweichende Ressourcen je Gruppe oder je Nutzer (plan.md §5)."""

    __tablename__ = "template_overrides"
    __table_args__ = (UniqueConstraint("template_id", "scope", "target_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("templates.id", ondelete="CASCADE"), index=True
    )
    scope: Mapped[str] = mapped_column(String(8))          # "group" | "user"
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    # NULL bedeutet "erben".
    cores: Mapped[float | None] = mapped_column(Float)
    memory_bytes: Mapped[int | None] = mapped_column(BigInteger)

    template: Mapped[Template] = relationship(back_populates="overrides")


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("templates.id", ondelete="CASCADE"), index=True
    )
    container_id: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(16), default="starting", index=True)

    # Aufgeloeste Werte, festgeschrieben beim Start (plan.md §5).
    cores: Mapped[float] = mapped_column(Float)
    memory_bytes: Mapped[int] = mapped_column(BigInteger)

    # Zugangsdaten fuer KasmVNC. Verlassen den Server nie — Traefik setzt den
    # Authorization-Header serverseitig.
    vnc_user: Mapped[str] = mapped_column(String(64), default="kasm_user")
    vnc_secret: Mapped[str] = mapped_column(String(64))

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_reason: Mapped[str | None] = mapped_column(String(64))
    error: Mapped[str | None] = mapped_column(Text)

    user: Mapped[User] = relationship(lazy="selectin")
    template: Mapped[Template] = relationship(lazy="selectin")
    streams: Mapped[list[AppStream]] = relationship(
        back_populates="session", cascade="all, delete-orphan", lazy="selectin"
    )


class AppStream(Base):
    """Eine laufende App im Arbeitsplatz, mit eigenem Display (plan.md §9.2)."""

    __tablename__ = "app_streams"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    app_slug: Mapped[str] = mapped_column(String(64))
    display_num: Mapped[int] = mapped_column(Integer)
    port: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="starting")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    session: Mapped[Session] = relationship(back_populates="streams")


class ImageBuild(Base):
    """Eine Version eines Golden Image (plan.md §8.2).

    Genau eine Version je Vorlage ist ``is_current`` — neue Sessions nutzen
    sie. Laufende Sessions bleiben unberuehrt, und ein Rueckfall auf eine
    aeltere Version ist ein Klick.
    """

    __tablename__ = "image_builds"
    __table_args__ = (UniqueConstraint("template_id", "version"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("templates.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)

    base_image: Mapped[str] = mapped_column(String(512))
    apt_packages: Mapped[list] = mapped_column(JSONB, default=list)
    vscode_extensions: Mapped[list] = mapped_column(JSONB, default=list)
    setup_script: Mapped[str] = mapped_column(Text, default="")
    comment: Mapped[str] = mapped_column(String(512), default="")

    # queued | building | ok | failed | cancelled
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    log: Mapped[str] = mapped_column(Text, default="")
    image_ref: Mapped[str | None] = mapped_column(String(512))
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    digest: Mapped[str | None] = mapped_column(String(128))
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)

    built_by: Mapped[str | None] = mapped_column(String(128))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    template: Mapped[Template] = relationship(back_populates="builds")


class Registry(Base):
    __tablename__ = "registries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(String(512), unique=True)
    schema_version: Mapped[str] = mapped_column(String(16), default="1.1")
    icon_url: Mapped[str | None] = mapped_column(String(512))
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_update: Mapped[bool] = mapped_column(Boolean, default=False)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_modified: Mapped[int | None] = mapped_column(BigInteger)
    workspace_count: Mapped[int] = mapped_column(Integer, default=0)
    fetch_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    entries: Mapped[list[RegistryEntry]] = relationship(
        back_populates="registry", cascade="all, delete-orphan"
    )


class RegistryEntry(Base):
    __tablename__ = "registry_entries"
    __table_args__ = (UniqueConstraint("registry_id", "sha"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    registry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("registries.id", ondelete="CASCADE"), index=True
    )
    sha: Mapped[str] = mapped_column(String(64))
    friendly_name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    categories: Mapped[list] = mapped_column(JSONB, default=list)
    architectures: Mapped[list] = mapped_column(JSONB, default=list)
    icon_url: Mapped[str | None] = mapped_column(String(512))
    image_ref: Mapped[str] = mapped_column(String(512))
    available_tags: Mapped[list] = mapped_column(JSONB, default=list)
    uncompressed_size_mb: Mapped[int] = mapped_column(Integer, default=0)
    imported_template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("templates.id", ondelete="SET NULL")
    )

    registry: Mapped[Registry] = relationship(back_populates="entries")


class Backup(Base):
    """Eine einzelne Sicherung (plan.md §11.2).

    Drei Arten, bewusst getrennt:

    ``profile``   Das Home des Nutzers — seine eigentliche Arbeit. Der Regelfall.
    ``container`` Nur die Aenderungen ausserhalb des Home, ermittelt ueber
                  ``docker diff``. Ein voller Container-Export waere um ein
                  Vielfaches groesser und bestuende fast nur aus dem
                  Basisimage, das ohnehin reproduzierbar ist.
    ``database``  Nutzer, Gruppen, Vorlagen, Zuweisungen, Audit.
    """

    __tablename__ = "backups"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    kind: Mapped[str] = mapped_column(String(16), index=True)

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    # Auch nach dem Loeschen eines Kontos muss noch erkennbar sein, wessen
    # Sicherung das war.
    username: Mapped[str | None] = mapped_column(String(128), index=True)
    template_slug: Mapped[str | None] = mapped_column(String(128))

    path: Mapped[str | None] = mapped_column(String(1024))
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    file_count: Mapped[int] = mapped_column(Integer, default=0)

    # running | ok | failed
    status: Mapped[str] = mapped_column(String(16), default="running", index=True)
    error: Mapped[str | None] = mapped_column(Text)
    log: Mapped[str] = mapped_column(Text, default="")

    # manual | schedule | pre_restore
    trigger: Mapped[str] = mapped_column(String(16), default="manual")
    actor: Mapped[str | None] = mapped_column(String(128))

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BackupPolicy(Base):
    """Zeitplan und Aufbewahrung fuer automatische Sicherungen."""

    __tablename__ = "backup_policies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    # Uhrzeit im 24-Stunden-Format, Ortszeit des Servers.
    hour: Mapped[int] = mapped_column(Integer, default=3)
    minute: Mapped[int] = mapped_column(Integer, default=30)
    # Leere Liste = jeden Tag. Sonst 0=Montag .. 6=Sonntag.
    weekdays: Mapped[list] = mapped_column(JSONB, default=list)

    include_profiles: Mapped[bool] = mapped_column(Boolean, default=True)
    include_containers: Mapped[bool] = mapped_column(Boolean, default=False)
    include_database: Mapped[bool] = mapped_column(Boolean, default=True)

    keep_daily: Mapped[int] = mapped_column(Integer, default=7)
    keep_weekly: Mapped[int] = mapped_column(Integer, default=4)

    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_result: Mapped[str | None] = mapped_column(String(255))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    actor_name: Mapped[str | None] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(String(64), index=True)
    object_type: Mapped[str | None] = mapped_column(String(64))
    object_id: Mapped[str | None] = mapped_column(String(64))
    ip: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[dict] = mapped_column(JSONB, default=dict)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
