"""Die einzige Stelle, an der OTA mit Keycloak spricht.

Dieselbe Idee wie [`agent_client.py`](agent_client.py) gegenüber Docker: Die
Eigenheiten der fremden Software stehen an **einer** Stelle und nicht verstreut
in fünfzehn Routern. Was oben herauskommt, sind Vorgänge in OTAs Sprache;
was unten hineingeht, ist Keycloaks Admin-API.

**Was hier nicht passiert: entscheiden, wer was darf.** Das tut `deps.py` wie
bisher. Diese Datei führt aus.

Zwei Betriebsarten (auth-roadmap.md §5b):

* **mitgeliefert** — der Keycloak aus diesem Stack. OTA ist im Realm führend
  und darf alles, was `scripts/keycloak-init.sh` ihm zugeteilt hat.
* **vorhanden** — ein fremder. Dann ist OTA **Gast**: Der Realm gehört jemand
  anderem, das Dienstkonto hat womöglich weniger Rechte, und was OTA nicht
  darf, darf es eben nicht.

Deshalb steht am Anfang `probe()` und nicht ein Aufruf. Erst nachsehen, was
geht — dann eine Oberfläche zeigen, die nur das anbietet. Ein Knopf, der in
einem 403 endet, ist schlimmer als keiner.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from .config import settings

log = logging.getLogger("ota.keycloak")

# Wie lange ein geholtes Merkmal benutzt wird, bevor ein neues geholt wird.
# Bewusst kürzer als seine Laufzeit: Ein Merkmal, das zwischen Prüfung und
# Benutzung abläuft, erzeugt einen Fehler, den niemand nachvollziehen kann.
SICHERHEITSABSTAND = 30.0

_merkmal: dict[str, Any] = {"wert": "", "gilt_bis": 0.0}


class KeycloakFehler(RuntimeError):
    """Etwas ging schief, und der Text ist für einen Menschen gedacht."""


def _basis() -> str:
    return settings().keycloak_base


def _realm() -> str:
    return settings().keycloak_realm


def token(erneuern: bool = False) -> str:
    """Ein Merkmal für das Dienstkonto, zwischengespeichert.

    Ohne Zwischenspeicher holte jede einzelne Verwaltungsaktion ein neues —
    das sind zwei Anfragen statt einer, bei jedem Tastendruck in einer
    Nutzerliste.
    """
    jetzt = time.monotonic()
    if not erneuern and _merkmal["wert"] and jetzt < _merkmal["gilt_bis"]:
        return str(_merkmal["wert"])

    cfg = settings()
    if not cfg.keycloak_secret:
        raise KeycloakFehler(
            "Für Keycloak ist kein Geheimnis hinterlegt. "
            "Bei der mitgelieferten Betriebsart legt es `make setup` an."
        )

    url = f"{_basis()}/realms/{_realm()}/protocol/openid-connect/token"
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, data={
                "client_id": "ota-manager",
                "client_secret": cfg.keycloak_secret,
                "grant_type": "client_credentials",
            })
    except httpx.HTTPError as exc:
        raise KeycloakFehler(f"Keycloak ist nicht erreichbar ({_basis()}).") from exc

    if resp.status_code >= 400:
        raise KeycloakFehler(
            "Das Dienstkonto `ota-manager` wurde abgewiesen. Stimmt das "
            "Geheimnis, und gibt es den Client in diesem Realm?"
        )

    daten = resp.json()
    _merkmal["wert"] = daten.get("access_token", "")
    _merkmal["gilt_bis"] = jetzt + max(0.0, float(daten.get("expires_in", 60)) - SICHERHEITSABSTAND)
    return str(_merkmal["wert"])


def ruf(method: str, pfad: str, **kw: Any) -> httpx.Response:
    """Ein Aufruf gegen die Admin-API dieses Realms.

    Bei 401 wird **einmal** ein frisches Merkmal geholt und wiederholt. Das ist
    kein Schönheitsfehler: Keycloak kann ein Merkmal für ungültig erklären,
    bevor es abläuft — etwa nach einem Neustart.
    """
    url = f"{_basis()}/admin/realms/{_realm()}{pfad}"

    def _einmal(merkmal: str) -> httpx.Response:
        with httpx.Client(timeout=30.0) as client:
            return client.request(
                method, url, headers={"Authorization": f"Bearer {merkmal}"}, **kw
            )

    try:
        resp = _einmal(token())
        if resp.status_code == 401:
            resp = _einmal(token(erneuern=True))
    except httpx.HTTPError as exc:
        raise KeycloakFehler(f"Keycloak ist nicht erreichbar ({_basis()}).") from exc
    return resp


# --- Nachsehen, was geht ------------------------------------------------

# Was OTA können will, und woran man es erkennt. Geprüft wird mit **lesenden**
# Aufrufen: Eine Rechteprüfung, die zum Prüfen etwas anlegt, hinterlässt Spuren
# in einer fremden Anlage — und das ist genau das, was ein Gast nicht tut.
FAEHIGKEITEN = {
    "konten": ("GET", "/users?max=1"),
    "gruppen": ("GET", "/groups?max=1"),
    "clients": ("GET", "/clients?max=1"),
    "verzeichnis": ("GET", "/components?type=org.keycloak.storage.UserStorageProvider"),
}


def erreichbar() -> bool:
    """Antwortet Keycloak gerade? Die billige Auskunft für `/healthz`.

    Bewusst **ohne** Merkmal und ohne den Zwischenspeicher: Der erste Versuch
    hier war `token()`, und der meldete „ok", während der Container schon
    gestoppt war — das Merkmal galt noch eine halbe Minute. Ein Health-Check,
    der aus dem Gedächtnis antwortet, prüft nichts.

    Die Entdeckungsadresse braucht keine Anmeldung und ist genau eine Anfrage.
    Sie sagt „der Dienst antwortet", nicht „OTA darf etwas" — und genau das
    ist die Frage, die `/healthz` stellt.
    """
    url = f"{_basis()}/realms/{_realm()}/.well-known/openid-configuration"
    try:
        with httpx.Client(timeout=5.0) as client:
            return client.get(url).status_code == 200
    except httpx.HTTPError:
        return False


def probe() -> dict[str, Any]:
    """Erreichbarkeit und Rechte — die Grundlage für die Oberfläche.

    Wirft nicht. Ein nicht erreichbares Keycloak ist ein Zustand, den OTA
    anzeigen können muss, kein Fehler, an dem es abbricht: Bei einem fremden
    Keycloak (§5b) kann es beim Hochfahren von OTA gerade neu starten oder
    hinter einem VPN liegen, das noch nicht oben ist.
    """
    cfg = settings()
    ergebnis: dict[str, Any] = {
        "betriebsart": cfg.idp_mode,
        "adresse": _basis(),
        "realm": _realm(),
        "erreichbar": False,
        "fehler": None,
        "faehigkeiten": {name: False for name in FAEHIGKEITEN},
    }

    try:
        token()
    except KeycloakFehler as exc:
        ergebnis["fehler"] = str(exc)
        return ergebnis

    ergebnis["erreichbar"] = True
    for name, (method, pfad) in FAEHIGKEITEN.items():
        try:
            ergebnis["faehigkeiten"][name] = ruf(method, pfad).status_code == 200
        except KeycloakFehler:
            ergebnis["faehigkeiten"][name] = False

    fehlend = [n for n, v in ergebnis["faehigkeiten"].items() if not v]
    if fehlend and cfg.idp_mode == "mitgeliefert":
        # Beim mitgelieferten ist das ein Einrichtungsfehler und keine
        # Absicht — dort hat OTA alles zugeteilt bekommen.
        ergebnis["fehler"] = (
            "Dem Dienstkonto fehlen Rechte (" + ", ".join(fehlend) + "). "
            "Nachholen mit:  make identity"
        )
    return ergebnis


def version() -> str | None:
    """Welche Fassung dort läuft. Nur zur Anzeige."""
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(f"{_basis()}/admin/serverinfo",
                              headers={"Authorization": f"Bearer {token()}"})
        if resp.status_code == 200:
            return str(resp.json().get("systemInfo", {}).get("version") or "") or None
    except (httpx.HTTPError, KeycloakFehler):
        pass
    return None
