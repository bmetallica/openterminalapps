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
    # Externe Anwendungen anlegen heisst: einen OIDC-Client in Keycloak
    # erzeugen und bestimmen, wohin dessen Token fliessen. Das ist
    # kategorisch etwas anderes als einen Arbeitsplatz zusammenzustellen —
    # das eine bleibt auf dem Rechner, das andere leitet Identitaeten nach
    # draussen (auth-roadmap.md §5d). Deshalb ein eigenes Recht.
    "anwendungen.verwalten",
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
    # Rueckfallcodes fuer den zweiten Faktor, **gehasht** wie Passwoerter.
    # Wer sein Telefon verliert, kaeme sonst nicht mehr herein — und ein
    # Administrator, der den zweiten Faktor einfach abschalten kann, waere
    # genau die Hintertuer, die er verhindern soll.
    totp_recovery: Mapped[list] = mapped_column(JSONB, default=list)

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
    # Verlangt diese Gruppe einen zweiten Faktor? Durchgesetzt wird das beim
    # Start einer Session, nicht bei der Anmeldung: Wer sich nicht anmelden
    # kann, kann auch keinen zweiten Faktor einrichten.
    require_totp: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    members: Mapped[list[User]] = relationship(
        secondary="group_members", back_populates="groups", lazy="selectin"
    )



class IdentityConfig(Base):
    """Die Anbindung an ein Verzeichnis (plan.md §9.4).

    Genau eine Zeile. Ein zweites Verzeichnis waere ein anderes Feature —
    dann muss entschieden werden, welches bei gleichem Namen gewinnt, und
    diese Frage hat noch niemand gestellt.

    **Abgeschaltet ist die Voreinstellung.** Solange `is_enabled` falsch ist,
    aendert sich an der Anmeldung nichts. Das ist keine Vorsicht, sondern die
    einzige Einstellung, bei der ein Fehler niemanden aussperrt.
    """

    __tablename__ = "identity_configs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    # ldap://host:389 oder ldaps://host:636
    server_uri: Mapped[str] = mapped_column(String(512), default="")
    # none | starttls  (bei ldaps:// ist die Verbindung ohnehin verschluesselt)
    tls_mode: Mapped[str] = mapped_column(String(16), default="starttls")
    # Ob das Zertifikat des Verzeichnisses geprueft wird. Abschalten laesst
    # sich das, aber es steht als Warnung in der Oberflaeche: Eine
    # unverifizierte TLS-Verbindung schuetzt gegen Mitlesen, nicht gegen
    # jemanden, der sich dazwischensetzt — und dann geht das Passwort an ihn.
    tls_verify: Mapped[bool] = mapped_column(Boolean, default=True)
    ca_cert: Mapped[str] = mapped_column(Text, default="")

    # Dienstkonto zum Suchen. Es braucht nur Leserecht.
    bind_dn: Mapped[str] = mapped_column(String(512), default="")
    bind_password: Mapped[str] = mapped_column(Text, default="")

    base_dn: Mapped[str] = mapped_column(String(512), default="")
    # Womit sich jemand anmeldet: `uid` bei OpenLDAP,
    # `sAMAccountName` oder `userPrincipalName` im Active Directory.
    login_attribute: Mapped[str] = mapped_column(String(64), default="uid")
    user_filter: Mapped[str] = mapped_column(String(512), default="(objectClass=inetOrgPerson)")
    mail_attribute: Mapped[str] = mapped_column(String(64), default="mail")
    name_attribute: Mapped[str] = mapped_column(String(64), default="cn")

    group_base_dn: Mapped[str] = mapped_column(String(512), default="")
    group_filter: Mapped[str] = mapped_column(String(512), default="(objectClass=groupOfNames)")
    # Wie eine Gruppe ihre Mitglieder nennt: `member` bei groupOfNames,
    # `memberUid` bei posixGroup.
    member_attribute: Mapped[str] = mapped_column(String(64), default="member")
    group_name_attribute: Mapped[str] = mapped_column(String(64), default="cn")

    # {"<gruppenname im verzeichnis>": "<gruppen-uuid in ota>"}
    #
    # Ausdrueckliche Abbildung statt automatischer Uebernahme: Eine Gruppe im
    # Verzeichnis heisst selten so wie eine in OTA, und wer sie automatisch
    # anlegen liesse, haette nach dem ersten Abgleich vierzig Gruppen, die
    # niemand wollte.
    group_map: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Beim ersten erfolgreichen Anmelden ein Konto anlegen.
    jit_create: Mapped[bool] = mapped_column(Boolean, default=True)
    # Naechtlicher Abgleich der Mitgliedschaften.
    sync_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


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

    # Laeuft bei jedem Sessionstart als Nutzer im Container, bevor die Session
    # als bereit gilt. Gedacht fuer alles, was ins Home gehoert, aber nicht ins
    # Image: Firmenzertifikate nachziehen, Einstellungen setzen, ein Verzeichnis
    # anlegen. Nicht fuer Installationen — die gehoeren ins Golden Image (§8),
    # sonst wartet jeder Nutzer bei jedem Start darauf.
    start_script: Mapped[str] = mapped_column(Text, default="")
    # Pfade im Skeleton, die bei **jedem** Start ueberschreiben. Der Rest
    # kommt nur ins leere Zuhause. Die Ausnahme ist mit Bedacht die Ausnahme:
    # Ein Zuhause gehoert dem Menschen, der darin arbeitet.
    skeleton_enforce: Mapped[list] = mapped_column(JSONB, default=list)

    # Haengt die eigene Ablage des Nutzers beschreibbar in den Container?
    # Vorgabe an: Sie ist der uebliche Weg, Dateien hinein und heraus zu
    # bekommen. Abschaltbar bleibt sie fuer Arbeitsplaetze, aus denen bewusst
    # nichts herausgetragen werden soll.
    user_shelf: Mapped[bool] = mapped_column(Boolean, default=True,
                                             server_default="true")

    # Haengt die Laufwerke der Gruppen ein, in denen der Nutzer ist — unter
    # /mnt/gruppen/<name>, beschreibbar, ein Ordner je Gruppe.
    #
    # Vorgabe an, aus demselben Grund wie oben: Ein gemeinsames Laufwerk ist
    # der uebliche Weg, im Team an denselben Dateien zu arbeiten. Wer einen
    # Arbeitsplatz bewusst abgeschottet haben will, schaltet es hier ab.
    group_shelf: Mapped[bool] = mapped_column(Boolean, default=True,
                                              server_default="true")

    # Welche Streaming-Maschine den Bildschirm überträgt.
    #
    # `kasmvnc` ist die Vorgabe und bleibt es: Sie trägt heute jeden
    # Arbeitsplatz. `selkies` ist der zweite Weg — H.264 über WebRTC statt
    # rechteckiger Bildausschnitte über RFB. Er steckt noch im Versuch und
    # bringt eine Einschränkung mit, die man kennen muss: **ein Bildschirm je
    # Sitzung**, keine Anwendung je Display.
    stream_engine: Mapped[str] = mapped_column(String(16), default="kasmvnc",
                                               server_default="kasmvnc")

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

    once_scripts: Mapped[list[OnceScript]] = relationship(
        cascade="all, delete-orphan", lazy="selectin",
        order_by="OnceScript.sort_order",
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


class OnceScript(Base):
    """Ein Skript, das je Nutzer **genau einmal** laeuft (plan.md §9.6).

    Der Fall, fuer den es das gibt: Ein neues Golden Image bringt eine
    Anwendung in einer neuen Fassung mit, und die braucht eine Aenderung im
    Zuhause — eine umgezogene Einstellungsdatei, ein neuer Pfad. Das Skeleton
    hilft nicht, denn das Zuhause ist laengst nicht mehr leer. Das Startskript
    hilft, aber es laeuft dann bei jedem Start wieder, obwohl die Sache nach
    dem ersten Mal erledigt ist.

    Gebucht wird je Nutzer und Skript (`OnceScriptRun`), nicht je Session:
    Wer drei Arbeitsplaetze derselben Vorlage nacheinander startet, bekommt es
    einmal. Ein neues Skript ist ein neuer Eintrag und laeuft wieder fuer alle
    — genau so ist es gemeint.
    """

    __tablename__ = "once_scripts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("templates.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text, default="")
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    runs: Mapped[list[OnceScriptRun]] = relationship(
        back_populates="script", cascade="all, delete-orphan", lazy="selectin"
    )


class OnceScriptRun(Base):
    """Dass ein Einmal-Skript fuer einen Nutzer gelaufen ist — und wie.

    Der Eintrag entsteht auch dann, wenn das Skript mit einem Fehler endet.
    Sonst liefe ein kaputtes Skript bei **jedem** Start jedes Nutzers erneut,
    und aus einem Fehler wuerde eine Dauerbelastung. Was misslungen ist, steht
    im Rueckgabewert und in der Ausgabe; die Verwaltung sieht es und kann es
    ausdruecklich noch einmal laufen lassen.

    Kein Eintrag entsteht, wenn der Lauf gar nicht zustande kam — dann war
    nicht das Skript das Problem, sondern der Weg dorthin, und der naechste
    Start versucht es wieder.
    """

    __tablename__ = "once_script_runs"
    __table_args__ = (UniqueConstraint("script_id", "user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    script_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("once_scripts.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    ran_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    exit_code: Mapped[int] = mapped_column(Integer, default=0)
    output: Mapped[str] = mapped_column(Text, default="")

    script: Mapped[OnceScript] = relationship(back_populates="runs")
    user: Mapped[User] = relationship(lazy="selectin")


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
    # Das echte Symbol aus dem Paket, als Datenadresse (`data:image/png;…`).
    # Leer heisst: Das Image bringt keins mit, dann zeigt die Oberflaeche das
    # Zeichen oben.
    #
    # In der Datenbank und nicht als Datei: Es gehoert zu genau diesem
    # Katalogeintrag, wiegt nach dem Verkleinern (`ota/icons.py`) wenige
    # Kilobyte und wandert damit von selbst durch Sicherung und
    # Wiederherstellung. Eine Datei daneben waere ein zweiter Ort, der beim
    # Zurueckspielen fehlen kann.
    icon_data: Mapped[str | None] = mapped_column(Text)
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
    # Bevorzugte Aufloesung dieser Anwendung. NULL heisst: die des
    # Arbeitsplatzes. Gedacht fuer den Fall, dass eine Anwendung mehr Flaeche
    # braucht als die uebrigen — eine Entwicklungsumgebung neben einem
    # Terminal — oder weniger, weil sie sonst unnoetig Bandbreite kostet.
    x_res: Mapped[int | None] = mapped_column(Integer)
    y_res: Mapped[int | None] = mapped_column(Integer)
    # Sichtbarkeit je Gruppe. **Leer heisst: fuer alle**, die den Arbeitsplatz
    # ueberhaupt sehen — sonst wuerde das Einfuehren dieser Spalte jeden
    # bestehenden Katalog auf einen Schlag leerraeumen.
    #
    # Als Liste an der App und nicht als eigene Tabelle, weil `set_apps` den
    # ganzen Katalog ersetzt: Die Zeilen bekaemen bei jedem Speichern neue
    # Kennungen, und eine daran haengende Zuordnung waere jedes Mal weg.
    group_ids: Mapped[list] = mapped_column(JSONB, default=list)

    template: Mapped[Template] = relationship(back_populates="apps")


class WebApp(Base):
    """Eine fremde Web-Anwendung im Katalog (auth-roadmap.md, Etappe D).

    OTA betreibt sie nicht — es kennt sie nur, entscheidet, wer sie sieht, und
    hat in Keycloak den OIDC-Client dafuer angelegt. Was jemand *innerhalb*
    der Anwendung darf, entscheidet die Anwendung selbst; OTA baut ihr
    Rechtemodell nicht nach.
    """

    __tablename__ = "web_apps"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    icon: Mapped[str] = mapped_column(String(16), default="◇")
    # Wohin die Kachel fuehrt.
    url: Mapped[str] = mapped_column(String(512))
    # Wohin Keycloak den Code schickt. Der eigentlich heikle Wert.
    redirect_uri: Mapped[str] = mapped_column(String(512))
    # Der Client in Keycloak. Das Geheimnis steht **nicht** hier: Es wird beim
    # Anlegen einmal gezeigt und danach nur noch in Keycloak gehalten.
    client_id: Mapped[str] = mapped_column(String(128))
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    groups: Mapped[list[Group]] = relationship(secondary="group_web_apps", lazy="selectin")


class GroupWebApp(Base):
    __tablename__ = "group_web_apps"
    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True
    )
    web_app_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("web_apps.id", ondelete="CASCADE"), primary_key=True
    )


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


class Recipe(Base):
    """Ein Bauplan fuer Software, die kein einfaches Paket ist.

    Die drei mitgelieferten Rezepte (Firefox, Chrome, VSCodium) standen
    anfangs im Frontend. Das war zu wenig: Wer eine vierte Anwendung
    braucht, sass wieder vor einem leeren Skriptfeld — genau dem, was diese
    Oberflaeche vermeiden soll.

    `kind` sagt, nach welchem Muster das Skript entsteht; `params` haelt die
    Antworten der Fuehrung. Beides wird aufgehoben, damit sich ein Rezept
    spaeter aendern laesst, ohne es neu zu erfinden. `script` ist das
    Ergebnis — und die Wahrheit: Wer den Text von Hand nachbessert, dessen
    Fassung gilt.
    """

    __tablename__ = "recipes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    glyph: Mapped[str] = mapped_column(String(8), default="\u25a2")
    # Warum es dieses Rezept braucht — steht als Hinweis an der Schaltflaeche.
    why: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(24), default="script")
    params: Mapped[dict] = mapped_column(JSONB, default=dict)
    script: Mapped[str] = mapped_column(Text, default="")
    # Mitgeliefert oder selbst gebaut. Mitgelieferte lassen sich nicht
    # loeschen, aber kopieren.
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
