"""Einstellungen, die zur Laufzeit aenderbar sein muessen.

Abgrenzung zu `config.py`: Dort steht, was beim Start aus der Umgebung kommt
und einen Neustart braucht — Datenbankadresse, Geheimnisse, Pfade. Hier steht,
was ein Administrator im laufenden Betrieb ueber die Oberflaeche dreht.

Die Werte liegen in der Tabelle `settings` als JSON. Ein winziger Zwischen-
speicher haelt sie im Prozess, damit nicht jede einzelne Anfrage die Datenbank
fragt — die Anmeldefrist wird bei *jedem* Request gebraucht.
"""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy.orm import Session as DbSession

from .models import Setting

# Wie lange jemand angemeldet bleibt, ohne etwas zu tun. Die Sitzung ist
# rollend: Jede Anfrage schiebt die Frist nach vorn. Wer arbeitet, wird nie
# herausgeworfen; wer den Rechner verlaesst, irgendwann schon.
AUTH_IDLE_MINUTES = "auth.idle_minutes"

# Die Stufen, die die Oberflaeche anbietet. Kein freies Zahlenfeld: Zwischen
# 30 Minuten und zwei Tagen gibt es keine Zahl, deren genauer Wert jemandem
# etwas bedeutet — die Groessenordnung ist die Entscheidung.
IDLE_STEPS = (30, 60, 120, 240, 480, 720, 1440, 2880)

# Wie viel Platz das Zuhause eines Nutzers belegen darf, in Gigabyte.
# 0 heisst: keine Grenze.
PROFILE_QUOTA_GB = "storage.profile_quota_gb"

# Wie viel freier Plattenplatz mindestens bleiben muss, damit noch eine
# Session startet. Ein volles Dateisystem ist kein Fehler, den ein Nutzer
# versteht — es ist ein Container, der beim Schreiben stehenbleibt.
DISK_FLOOR_GB = "storage.disk_floor_gb"

# Wohin eine externe Anwendung ihre Token bekommen darf.
#
# **Leer heisst: nichts ist erlaubt** — nicht: alles. Eine Schranke, die im
# Auslieferungszustand offen steht, wird nie geschlossen (auth-roadmap.md
# §5d). Eingetragen werden vollstaendige Herkuenfte mit Schema, damit ein
# `http://` sichtbar eine Entscheidung ist und kein Versehen.
APP_ORIGINS = "apps.allowed_origins"

# Das eine lokale Konto, das bleibt, wenn alles andere ueber Keycloak laeuft.
#
# Es steht hier und nicht als Feld am Konto, weil es genau **eines** sein
# soll: Ein Feld liesse sich an beliebig viele Konten haengen, und aus einem
# Notausgang wuerden viele (auth-roadmap.md §5.2).
BREAKGLASS = "auth.breakglass"

# Das Gesicht der Anlage: Name, Akzentfarbe, Zeichen. Es steht hier und nicht
# in der Umgebung, weil ein Administrator es im Betrieb aendern koennen soll —
# eine Marke waehlt niemand einmal beim Aufstellen und nie wieder. Das Zeichen
# liegt als Base64 in derselben JSONB-Spalte; die Begruendung dafuer steht in
# `routers/branding.py`.
BRAND_NAME = "brand.name"
BRAND_ACCENT = "brand.accent"
BRAND_LOGO = "brand.logo"
# Die Sprache fuer alle, die nicht selbst umschalten: Oberflaeche, Anmeldeseite
# von Keycloak, Handbuch. Kommt mit /api/branding, weil die Anmeldemaske sie
# braucht, bevor jemand angemeldet ist.
UI_SPRACHE = "ui.sprache"

# Freigaben, die fuer **alle** Arbeitsplaetze gelten — der Dateiserver, das
# interne Rechenzentrum, der Paketspiegel. An einer Stelle gepflegt statt in
# jedem Profil wiederholt.
FIREWALL_GLOBAL = "firewall.global"

# Paketquellen (Kapitel 26): wie Container das eigene Repository benutzen
# (aus / zuerst / nur), gegen welchen festgehaltenen Stand gebaut wird, und ab
# wie vielen Tagen das Alter des Spiegels gelb bzw. rot erscheint.
# Gesetzt von `make update`, solange es laeuft (Wert: Beginn als ISO-Zeit).
# Jede Seite zeigt dann ein Banner. Steht direkt in der Datenbank, weil die
# API waehrend des Updates neu startet — die Datenbank nicht.
WARTUNG_UPDATE = "wartung.update"

# Verzeichnisgruppen (Kapitel 08): wie oft abgeglichen wird (Minuten, 0 =
# aus), was der letzte Lauf ergab, und was ein Konto ohne jede Gruppe auf
# seinem Dashboard liest.
VERZEICHNIS_INTERVALL = "verzeichnis.intervall"
VERZEICHNIS_INTERVALL_STUFEN = (0, 15, 60, 360, 1440)
VERZEICHNIS_LETZTER = "verzeichnis.letzter_abgleich"
OHNE_GRUPPE_HINWEIS = "dashboard.ohne_gruppe_hinweis"

# OTA-Git (Kapitel 27): an/aus, Subdomain, berechtigte Gruppen (Kennungen)
# und die Adresse, unter der Browser OTA sehen — Forgejo findet Keycloak dort.
GIT_AN = "git.an"
GIT_DOMAIN = "git.domain"
GIT_GRUPPEN = "git.gruppen"
GIT_OTA_URL = "git.ota_url"

# Softwaremonitoring (Kapitel 11): was die letzte stündliche Erfassung ergab.
SOFTWARE_LETZTE = "software.letzte_erfassung"

REPO_MODUS = "repo.modus"
REPO_BAU_SNAPSHOT = "repo.bau_snapshot"
REPO_ALTER_GELB = "repo.alter_gelb"
REPO_ALTER_ROT = "repo.alter_rot"

DEFAULTS: dict[str, Any] = {
    # Acht Stunden: ein Arbeitstag. Wer morgens kommt, meldet sich einmal an.
    AUTH_IDLE_MINUTES: 480,
    PROFILE_QUOTA_GB: 20,
    DISK_FLOOR_GB: 5,
    BRAND_NAME: "OpenTerminalApps",
    # Dieselbe Zahl wie `--accent` in `web/src/styles/app.css`. Sie steht
    # zweimal, weil die Oberflaeche eine Farbe braucht, bevor sie den Server
    # gefragt hat — und beim Zuruecksetzen soll genau diese herauskommen.
    BRAND_ACCENT: "#06B6D4",
    BRAND_LOGO: None,
    UI_SPRACHE: "de",
    FIREWALL_GLOBAL: [],
    VERZEICHNIS_INTERVALL: 60,
    VERZEICHNIS_LETZTER: None,
    OHNE_GRUPPE_HINWEIS: ("Dir ist noch nichts zugewiesen. Wende dich an die Verwaltung, "
                          "damit sie dich einer Gruppe zuordnet."),
    SOFTWARE_LETZTE: None,
    GIT_AN: False,
    GIT_DOMAIN: "",
    GIT_GRUPPEN: [],
    GIT_OTA_URL: "",
    REPO_MODUS: "zuerst",
    REPO_BAU_SNAPSHOT: "",
    REPO_ALTER_GELB: 7,
    REPO_ALTER_ROT: 30,
}

_cache: dict[str, tuple[float, Any]] = {}
_TTL = 5.0


def get(db: DbSession, key: str) -> Any:
    hit = _cache.get(key)
    now = time.monotonic()
    if hit and now - hit[0] < _TTL:
        return hit[1]

    row = db.get(Setting, key)
    value = row.value.get("v") if row and isinstance(row.value, dict) else None
    if value is None:
        value = DEFAULTS.get(key)
    _cache[key] = (now, value)
    return value


def put(db: DbSession, key: str, value: Any) -> None:
    row = db.get(Setting, key)
    if row is None:
        row = Setting(key=key, value={"v": value})
        db.add(row)
    else:
        row.value = {"v": value}
    # Den neuen Wert merken, nicht nur den alten vergessen: Die Sitzungen
    # laufen ohne autoflush, und ein `get` vor dem Commit las sonst die alte
    # Zeile aus der Datenbank — und hielt sie fünf Sekunden lang fest.
    _cache[key] = (time.monotonic(), value)


def idle_minutes(db: DbSession) -> int:
    """Die Anmeldefrist, auf eine der angebotenen Stufen gerundet.

    Gerundet wird auch beim Lesen, nicht nur beim Schreiben: Ein Wert, der
    ueber die Datenbank von Hand hineingeraten ist, soll die Anmeldung nicht
    auf fuenf Sekunden setzen koennen.
    """
    raw = get(db, AUTH_IDLE_MINUTES)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULTS[AUTH_IDLE_MINUTES]
    return min(IDLE_STEPS, key=lambda step: abs(step - value))


def profile_quota_bytes(db: DbSession) -> int:
    """Die Grenze je Zuhause in Bytes. 0 heisst: keine."""
    try:
        gb = max(0, int(get(db, PROFILE_QUOTA_GB)))
    except (TypeError, ValueError):
        gb = DEFAULTS[PROFILE_QUOTA_GB]
    return gb * 1024 ** 3


def disk_floor_bytes(db: DbSession) -> int:
    """Was auf der Platte frei bleiben muss. 0 heisst: keine Untergrenze."""
    try:
        gb = max(0, int(get(db, DISK_FLOOR_GB)))
    except (TypeError, ValueError):
        gb = DEFAULTS[DISK_FLOOR_GB]
    return gb * 1024 ** 3


def allowed_origins(db: DbSession) -> list[str]:
    """Die erlaubten Ziele fuer externe Anwendungen. Leer heisst: keine."""
    wert = get(db, APP_ORIGINS)
    if isinstance(wert, list):
        return [str(x).strip().rstrip("/") for x in wert if str(x).strip()]
    return []


def breakglass(db: DbSession) -> str:
    """Der Name des Notfallkontos. Leer heisst: keines bestimmt."""
    return str(get(db, BREAKGLASS) or "")
