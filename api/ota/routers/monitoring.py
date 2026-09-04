"""Zustand und Kennzahlen — für Überwachung, nicht für Menschen.

Zwei Endpunkte mit sehr verschiedenen Ansprüchen:

``/healthz`` beantwortet **eine** Frage: Kann dieser Dienst gerade arbeiten?
Er ist billig, braucht keine Anmeldung und antwortet mit 503, wenn etwas
fehlt. Ein Health-Check, der immer „ok" sagt, ist ein Health-Check, der nichts
prüft — und genau das war er hier bis zum 2026-08-27.

``/metrics`` liefert Zahlen im Prometheus-Textformat. Der Umweg über eine
Bibliothek lohnt nicht: Das Format ist eine Zeile je Messwert, und
handgeschrieben steht wenigstens dabei, was gemessen wird.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session as DbSession

from .. import agent_client, keycloak
from ..config import settings
from ..db import get_db
from ..deps import current_user
from ..models import ImageBuild, Registry, Session as SessionModel, Template, User

router = APIRouter(tags=["monitoring"])

# Der Zustand des Hosts kostet einen Aufruf beim Agent. Ein Prometheus fragt
# im 15-Sekunden-Takt, oft aus mehreren Instanzen — ohne diesen Puffer waere
# der Agent damit beschaeftigt, immer wieder dasselbe zu antworten.
_HOST_TTL = 15.0
_host_cache: tuple[float, dict[str, Any] | None] = (0.0, None)


def _host() -> dict[str, Any] | None:
    global _host_cache
    age, data = _host_cache
    now = time.monotonic()
    if data is not None and now - age < _HOST_TTL:
        return data
    try:
        data = agent_client.host_info()
    except Exception:  # noqa: BLE001 — Kennzahlen duerfen nie etwas umwerfen
        data = None
    _host_cache = (now, data)
    return data


@router.get("/healthz")
def healthz(response: Response, db: DbSession = Depends(get_db)) -> dict[str, Any]:
    """Kann dieser Dienst arbeiten?

    Geprüft wird, was ohne den Dienst nicht geht: die Datenbank, und der
    Agent — ohne ihn lässt sich keine Session starten. Ein fehlender Agent ist
    kein Grund, die API für tot zu erklären; sie kann weiter anmelden und
    anzeigen. Er steht deshalb im Ergebnis, ohne es auf 503 zu ziehen.
    """
    out: dict[str, Any] = {"status": "ok", "db": "ok", "agent": "ok", "keycloak": "ok"}

    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        out["db"] = f"fehlt: {type(exc).__name__}"
        out["status"] = "degraded"

    try:
        agent_client.host_info()
    except Exception as exc:  # noqa: BLE001
        out["agent"] = f"fehlt: {type(exc).__name__}"

    # Keycloak steht hier, weil an ihm kuenftig jede Anmeldung haengt — und
    # weil ein fremdes (auth-roadmap.md §5b) beim Hochfahren gerade schweigen
    # kann. Solange die Anmeldung noch OTA selbst macht, zieht es nichts auf
    # 503; sichtbar sein soll es trotzdem, und zwar bevor es weh tut.
    try:
        if not keycloak.erreichbar():
            out["keycloak"] = "nicht erreichbar"
    except Exception as exc:  # noqa: BLE001
        out["keycloak"] = f"fehlt: {type(exc).__name__}"

    # Ohne Datenbank ist die API nicht benutzbar. Ohne Agent schon — dann
    # laesst sich nur nichts starten.
    if out["db"] != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return out


@router.get("/ca.crt")
def ca_zertifikat() -> Response:
    """Die eigene CA zum Herunterladen — ohne Anmeldung.

    Das ist kein Versehen und keine Bequemlichkeit. Ein CA-Zertifikat enthaelt
    einen oeffentlichen Schluessel und Namen, sonst nichts; es ist zum
    Verteilen gemacht. Und es muss **vor** dem Vertrauen erreichbar sein —
    eine Anmeldung davor waere ein Kreis: Wer der Anlage noch nicht traut,
    kann sich bei ihr auch nicht anmelden.

    Wozu: Eine fremde Anwendung, die sich gegen OTA anmelden soll, muss dem
    Zertifikat des Anmeldedienstes vertrauen. In einer frischen Anlage gibt es
    kein oeffentliches Zertifikat, sondern die CA, die `make setup` erzeugt
    hat. Statt sie auf dem Host zu suchen, holt man sie hier ab:

        curl -o ota-ca.crt https://<host>/ca.crt

    Laeuft die Anlage hinter einem echten Zertifikat, gibt es hier nichts —
    dann ist auch nichts zu verteilen.
    """
    pfad = Path(settings().certs_dir) / "ota-ca.crt"
    try:
        inhalt = pfad.read_bytes()
    except OSError:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Diese Anlage benutzt keine eigene CA. Dann braucht auch niemand "
            "eine zu importieren.",
        ) from None

    return Response(
        content=inhalt, media_type="application/x-pem-file",
        headers={"Content-Disposition": 'attachment; filename="ota-ca.crt"',
                 "Cache-Control": "public, max-age=3600"},
    )


def _metrics_allowed(request: Request, db: DbSession) -> None:
    """Zwei Wege herein: ein Sammler mit Merkmal, oder ein Administrator.

    Die Zahlen verraten für sich genommen wenig — aber sie verraten, wie viele
    Menschen hier arbeiten und wann. Das ist nichts fürs offene Netz.
    """
    token = settings().metrics_token
    if token:
        head = request.headers.get("authorization", "")
        if head.startswith("Bearer ") and head[7:] == token:
            return

    try:
        user = current_user(request, Response(), db)
    except HTTPException:
        # Gar nicht angemeldet. 401 heisst „melde dich an" — und genau das
        # ist hier die Antwort.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            "Kennzahlen brauchen eine Anmeldung.") from None

    if user.is_admin or "settings.manage" in user.permissions:
        return

    # Angemeldet, aber nicht befugt. Das ist 403: Ein zweiter Anlauf mit
    # denselben Zugangsdaten aendert nichts daran.
    raise HTTPException(status.HTTP_403_FORBIDDEN,
                        "Für die Kennzahlen fehlen dir die Rechte.")


@router.get("/metrics")
def metrics(request: Request, db: DbSession = Depends(get_db)) -> Response:
    _metrics_allowed(request, db)

    lines: list[str] = []

    def gauge(name: str, help_text: str, value: float, **labels: str) -> None:
        if not any(line.startswith(f"# TYPE {name} ") for line in lines):
            lines.append(f"# HELP {name} {help_text}")
            lines.append(f"# TYPE {name} gauge")
        tag = ""
        if labels:
            inner = ",".join(f'{k}="{v}"' for k, v in labels.items())
            tag = f"{{{inner}}}"
        lines.append(f"{name}{tag} {value}")

    # Das Netz je Arbeitsplatz. Die Zahlen kommen live aus den Zaehlern des
    # Routers und werden **nirgends aufbewahrt** — es gibt also keine
    # Verlaufsdaten und damit auch nichts zu loeschen. Wer eine Zeitreihe
    # daraus macht (Prometheus tut genau das), legt personenbezogene Daten an
    # und braucht eine Frist; der Vorschlag steht in `dsgvo.md`.
    #
    # Beschriftet wird mit dem **Netz**, nicht mit dem Namen des Menschen. Wer
    # dahintersteht, loest die Oberflaeche auf — und dafuer braucht es Rechte.
    try:
        netz = agent_client.firewall_uebersicht()
        for subnetz, werte in (netz.get("zaehler") or {}).items():
            gauge("ota_netz_bytes", "Verkehr eines Arbeitsplatzes seit dem Start des Routers",
                  werte.get("bytes", 0), netz=subnetz)
            gauge("ota_netz_verworfen",
                  "Verworfene Pakete eines Arbeitsplatzes — das Signal fuer einen Portscan",
                  werte.get("verworfen", 0), netz=subnetz)
    except Exception:  # noqa: BLE001 — Kennzahlen duerfen nie eine Antwort kippen
        pass

    # Sessions nach Zustand. Der interessante Wert ist nicht die Summe,
    # sondern wie viele gerade Speicher belegen.
    by_status = db.execute(
        select(SessionModel.status, func.count()).group_by(SessionModel.status)
    ).all()
    for st, count in by_status:
        gauge("ota_sessions", "Sessions je Zustand", count, status=str(st))
    if not by_status:
        gauge("ota_sessions", "Sessions je Zustand", 0, status="running")

    gauge("ota_users", "Angelegte Konten", db.scalar(select(func.count(User.id))) or 0)
    gauge("ota_users_active", "Konten, die sich anmelden dürfen",
          db.scalar(select(func.count(User.id)).where(
              User.is_active.is_(True), User.is_locked.is_(False))) or 0)
    gauge("ota_users_totp", "Konten mit zweitem Faktor",
          db.scalar(select(func.count(User.id)).where(
              User.totp_secret.is_not(None))) or 0)
    gauge("ota_templates", "Angelegte Workspaces",
          db.scalar(select(func.count(Template.id))) or 0)
    gauge("ota_templates_enabled", "Workspaces, die jemand starten kann",
          db.scalar(select(func.count(Template.id)).where(
              Template.is_enabled.is_(True))) or 0)
    gauge("ota_registries", "Eingetragene Kataloge",
          db.scalar(select(func.count(Registry.id))) or 0)

    # Ein Build, der seit Stunden „building" ist, ist ein haengender Build.
    for st, count in db.execute(
        select(ImageBuild.status, func.count()).group_by(ImageBuild.status)
    ).all():
        gauge("ota_builds", "Image-Builds je Zustand", count, status=str(st))

    host = _host()
    if host:
        gauge("ota_host_memory_bytes", "Arbeitsspeicher des Hosts",
              host.get("memory_total", 0))
        gauge("ota_host_memory_available_bytes", "Davon verfügbar",
              host.get("memory_available", 0))
        gauge("ota_host_disk_free_bytes", "Freier Plattenplatz",
              host.get("disk_free", 0))
        gauge("ota_host_cores", "Kerne des Hosts", host.get("cores", 0))
        gauge("ota_agent_up", "Ist der Agent erreichbar?", 1)
    else:
        gauge("ota_agent_up", "Ist der Agent erreichbar?", 0)

    return Response("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")
