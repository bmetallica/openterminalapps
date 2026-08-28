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


# --- Token prüfen -------------------------------------------------------
#
# Ab hier geht es nicht mehr um Verwaltung, sondern um Identität: Ein Token,
# das jemand mitbringt, wird zum Beweis, wer er ist. Das ist die Stelle, an
# der Nachlässigkeit teuer wird.
#
# Geprüft wird deshalb **vollständig** und gegen den öffentlichen Schlüssel
# des Realms, nie gegen etwas, das im Token selbst steht:
#
#   Signatur   gegen JWKS, RS256 — nicht `verify_signature=False`
#   Aussteller muss unser Realm sein
#   Laufzeit   exp und nbf
#   Empfänger  azp/aud muss einer unserer Clients sein
#
# Der letzte Punkt ist der, den man am ehesten weglässt: Ohne ihn gälte ein
# Token, das für eine *andere* Anwendung in diesem Realm ausgestellt wurde,
# auch hier. Wer Open WebUI betreibt, könnte sich damit bei OTA anmelden.

_jwks: dict[str, Any] = {"client": None, "fuer": ""}

# Wessen Token OTA als Beweis annimmt. `ota` ist die Anmeldung im Browser,
# `ota-tests` der Weg der Prüfreihen ohne Browser (§5e).
EIGENE_CLIENTS = ("ota", "ota-tests")


def _jwks_client():
    from jwt import PyJWKClient

    url = f"{_basis()}/realms/{_realm()}/protocol/openid-connect/certs"
    if _jwks["client"] is None or _jwks["fuer"] != url:
        # PyJWKClient hält die Schlüssel selbst vor und holt sie nur nach,
        # wenn eine unbekannte Kennung auftaucht — genau das Verhalten, das
        # ein Schlüsselwechsel im Realm braucht.
        _jwks["client"] = PyJWKClient(url, cache_keys=True, lifespan=3600)
        _jwks["fuer"] = url
    return _jwks["client"]


def pruefe_token(rohtoken: str) -> dict[str, Any]:
    """Ein **ID-Token** von Keycloak in geprüfte Angaben verwandeln.

    Ausdrücklich das ID-Token und nicht das Zugriffstoken. Zwei Gründe, und
    der zweite ist gemessen:

    1. Das ID-Token *ist* die Aussage über eine Person; das Zugriffstoken ist
       eine Vollmacht für eine Schnittstelle. Wer Identität aus einer Vollmacht
       liest, verwechselt zwei Dinge.
    2. Keycloak 26 legt in ein Zugriffstoken **kein `sub`** mehr. Gemessen am
       2026-08-28: Anmeldename und Gruppen standen darin, die Kennung nicht —
       und die ist hier der Schlüssel (§4).

    Geprüft wird vollständig gegen den öffentlichen Schlüssel des Realms:
    Signatur, Laufzeit, Empfänger. Niemals gegen etwas, das im Token steht.
    """
    import jwt as _jwt

    if not rohtoken or rohtoken.count(".") != 2:
        raise KeycloakFehler("Das ist kein Token.")

    try:
        schluessel = _jwks_client().get_signing_key_from_jwt(rohtoken)
        daten = _jwt.decode(
            rohtoken, schluessel.key, algorithms=["RS256"],
            # Der Empfänger wird gleich selbst geprüft, weil ein ID-Token je
            # nach Bereichen mehrere führen kann.
            options={"verify_aud": False, "require": ["exp", "iat", "sub"]},
        )
    except _jwt.PyJWTError as exc:
        raise KeycloakFehler(f"Das Token gilt hier nicht: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 — JWKS nicht erreichbar
        raise KeycloakFehler("Die Schlüssel des Realms sind nicht abrufbar.") from exc

    # Aussteller: geprüft wird der **Realm**, nicht der Rechnername.
    #
    # Das sieht nachlässig aus und ist es nicht. Dieselbe Anlage ist unter
    # mehreren Adressen erreichbar — im LAN über die IP, von aussen über den
    # Namen am Reverse Proxy, aus den Containern über den Dienstnamen —, und
    # Keycloak schreibt in `iss` die Adresse, über die gefragt wurde. Ein
    # fester Rechnername lehnte deshalb jeweils die anderen Wege ab. Gemessen
    # am 2026-08-28, als ein Token mit `iss=http://ota-keycloak:8080/...`
    # gegen die Erwartung `http://keycloak:8080/...` fiel — dasselbe Keycloak,
    # zwei Dienstnamen.
    #
    # Was die Echtheit trägt, ist die Signatur: Die Schlüssel kommen von einer
    # festen, internen Adresse, die niemand von aussen beeinflusst. Nur wer
    # den privaten Schlüssel dieses Realms hat, kommt hier durch — der
    # Rechnername im Token fügt dem nichts hinzu.
    iss = str(daten.get("iss") or "")
    if not iss.endswith(f"/realms/{_realm()}"):
        raise KeycloakFehler(f"Das Token gehört zu einem anderen Realm ({iss}).")

    empfaenger = daten.get("aud")
    liste = [empfaenger] if isinstance(empfaenger, str) else list(empfaenger or [])
    if daten.get("azp"):
        liste.append(str(daten["azp"]))
    if not any(c in EIGENE_CLIENTS for c in liste):
        raise KeycloakFehler(
            "Dieses Token wurde für eine andere Anwendung ausgestellt."
        )
    return daten


def angaben(daten: dict[str, Any]) -> dict[str, Any]:
    """Aus den Token-Angaben das, was OTA über einen Menschen wissen will.

    `sub` ist der Schlüssel und nicht der Name: Im Verzeichnis wird geheiratet,
    und aus `anna.schmidt` wird `anna.mueller` (auth-roadmap.md §4).
    """
    return {
        "sub": str(daten.get("sub") or ""),
        "username": str(daten.get("preferred_username") or "").strip().lower(),
        "email": (daten.get("email") or None),
        "display_name": (daten.get("name") or None),
        "groups": [str(g).lstrip("/") for g in (daten.get("groups") or [])],
    }


# --- Der Weg im Browser -------------------------------------------------

def authorize_url(redirect_uri: str, state: str, challenge: str,
                  oeffentlich: str | None = None) -> str:
    """Wohin der Browser geschickt wird, um sich anzumelden.

    `oeffentlich` ist die Adresse, unter der **der Browser** Keycloak sieht.
    Sie ist nicht dieselbe wie die, unter der die API es sieht: Diese Anlage
    ist unter mehreren Namen erreichbar, und der Browser muss unter dem
    bleiben, mit dem er angefangen hat — sonst steht plötzlich eine fremde
    Herkunft in der Adresszeile, und die Desktop-Verknüpfungen verlassen
    ihren Geltungsbereich (§5.6).
    """
    from urllib.parse import urlencode

    basis = (oeffentlich or _basis()).rstrip("/")
    frage = urlencode({
        "client_id": "ota",
        "response_type": "code",
        "scope": "openid profile email",
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    return f"{basis}/realms/{_realm()}/protocol/openid-connect/auth?{frage}"


def tausche_code(code: str, redirect_uri: str, verifier: str) -> dict[str, Any]:
    """Den Code gegen Token eintauschen. Läuft über die **interne** Adresse.

    Der Browser hat Keycloak unter seinem öffentlichen Namen gesehen; dieser
    Aufruf geht direkt, ohne Umweg über Traefik. Das ist kein Widerspruch —
    `redirect_uri` muss nur mit der übereinstimmen, die beim Hinweg
    mitgeschickt wurde.
    """
    cfg = settings()
    url = f"{_basis()}/realms/{_realm()}/protocol/openid-connect/token"
    try:
        with httpx.Client(timeout=20.0) as client:
            resp = client.post(url, data={
                "grant_type": "authorization_code",
                "client_id": "ota",
                "client_secret": f"{cfg.keycloak_secret}-app",
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": verifier,
            })
    except httpx.HTTPError as exc:
        raise KeycloakFehler("Keycloak antwortet gerade nicht.") from exc

    if resp.status_code >= 400:
        # Der Text von Keycloak ist für Entwickler gedacht, nicht für den
        # Menschen vor dem Bildschirm. Er steht im Protokoll, nicht auf der Seite.
        log.warning("Code-Tausch abgelehnt: %s %s", resp.status_code, resp.text[:300])
        raise KeycloakFehler("Die Anmeldung liess sich nicht abschliessen.")
    return resp.json()


def abmelde_url(oeffentlich: str, danach: str, id_token: str | None = None) -> str:
    """Wohin, wenn jemand sich überall abmelden will."""
    from urllib.parse import urlencode

    frage: dict[str, str] = {"post_logout_redirect_uri": danach, "client_id": "ota"}
    if id_token:
        frage["id_token_hint"] = id_token
    return (f"{oeffentlich.rstrip('/')}/realms/{_realm()}"
            f"/protocol/openid-connect/logout?{urlencode(frage)}")


def pruefe_abmeldetoken(rohtoken: str) -> dict[str, Any]:
    """Ein Abmeldetoken, das Keycloak von sich aus schickt.

    Es kommt über den **Rückkanal**: Keycloak ruft OTA auf, nicht der Browser.
    Deshalb gilt hier dieselbe Strenge wie bei der Anmeldung — wer diesen
    Aufruf fälschen könnte, könnte beliebige Leute aus ihren Sitzungen werfen.

    Ein Abmeldetoken sieht anders aus als ein ID-Token: Es hat kein `iat` als
    Pflichtfeld, dafür einen Ereignisbereich, und es trägt entweder `sub`
    (dieser Mensch) oder `sid` (diese eine Sitzung).
    """
    import jwt as _jwt

    try:
        schluessel = _jwks_client().get_signing_key_from_jwt(rohtoken)
        daten = _jwt.decode(rohtoken, schluessel.key, algorithms=["RS256"],
                            options={"verify_aud": False})
    except Exception as exc:  # noqa: BLE001
        raise KeycloakFehler(f"Abmeldetoken ungültig: {exc}") from exc

    if not str(daten.get("iss", "")).endswith(f"/realms/{_realm()}"):
        raise KeycloakFehler("Abmeldetoken gehört zu einem anderen Realm.")

    # Der Ereignisbereich ist das, was es von einem ID-Token unterscheidet.
    # Ohne diese Prüfung liesse sich ein gewöhnliches ID-Token als Abmeldung
    # ausgeben — und damit jeder aus seiner Sitzung werfen, dessen Token man
    # einmal gesehen hat.
    ereignisse = daten.get("events") or {}
    if "http://schemas.openid.net/event/backchannel-logout" not in ereignisse:
        raise KeycloakFehler("Das ist kein Abmeldetoken.")

    if not daten.get("sub") and not daten.get("sid"):
        raise KeycloakFehler("Das Abmeldetoken nennt niemanden.")
    return daten
