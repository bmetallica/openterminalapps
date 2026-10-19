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

# Aktionen, die OTA bei Keycloak anstossen darf (Application-Initiated
# Actions). Nur diese: Der Name kommt aus einer Adresse, und Keycloak kennt
# noch andere, die hier niemand ausloesen soll.
AKTIONEN = ("UPDATE_PASSWORD", "CONFIGURE_TOTP", "webauthn-register")


def authorize_url(redirect_uri: str, state: str, challenge: str,
                  oeffentlich: str | None = None, *, aktion: str = "",
                  login_hint: str = "") -> str:
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
        # Passwort aendern, zweiten Faktor einrichten — Keycloak fuehrt die
        # Aktion aus und schickt zurueck. OTA sieht dabei kein Passwort.
        **({"kc_action": aktion} if aktion in AKTIONEN else {}),
        # Der Name ist schon bekannt (etwa von /login): nicht zweimal tippen.
        **({"login_hint": login_hint} if login_hint else {}),
    })
    return f"{basis}/realms/{_realm()}/protocol/openid-connect/auth?{frage}"


class SitzungWeg(KeycloakFehler):
    """Keycloak kennt die Sitzung nicht mehr (abgemeldet, abgelaufen, beendet)."""


def auffrischen(refresh_token: str) -> dict[str, Any]:
    """Die Keycloak-Sitzung am Leben halten: Refresh-Token gegen neue Token.

    Jede Auffrischung setzt Keycloaks Leerlauf-Uhr der SSO-Sitzung zurück.
    Darum geht es: Solange jemand in OTA arbeitet, soll eine fremde Anwendung
    ihn über die zentrale Anmeldung ohne Maske hereinlassen (2026-10-08).
    Vorher lief Keycloaks Sitzung nach 30 Minuten ohne Kontakt ab, während
    OTA längst nur noch mit seinem eigenen Cookie arbeitete.

    `SitzungWeg`, wenn Keycloak das Token ablehnt; `KeycloakFehler`, wenn
    Keycloak nicht antwortet — das ist kein Grund, jemanden abzumelden.
    """
    cfg = settings()
    url = f"{_basis()}/realms/{_realm()}/protocol/openid-connect/token"
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(url, headers=_wie_ausgestellt(refresh_token), data={
                "grant_type": "refresh_token",
                "client_id": "ota",
                "client_secret": f"{cfg.keycloak_secret}-app",
                "refresh_token": refresh_token,
            })
    except httpx.HTTPError as exc:
        raise KeycloakFehler("Keycloak antwortet gerade nicht.") from exc
    if resp.status_code == 400:
        raise SitzungWeg(resp.text[:200])
    if resp.status_code >= 400:
        raise KeycloakFehler(f"Auffrischen abgelehnt: {resp.status_code}")
    return resp.json()


def _wie_ausgestellt(token: str) -> dict[str, str]:
    """Kopfzeilen, unter denen Keycloak sich so sieht wie beim Ausstellen.

    Der Browser hat sich unter der öffentlichen Adresse angemeldet; dort steht
    der Aussteller im Token (`https://ota.firma.de/auth/realms/ota`). OTA
    spricht Keycloak aber intern an (`http://keycloak:8080`), und beim
    Auffrischen vergleicht Keycloak den Aussteller mit der Adresse, unter der
    er gerade gefragt wird: „Invalid token issuer". Beim Code-Tausch spielt
    das keine Rolle, beim Auffrischen schon. Keycloak liest die
    X-Forwarded-Kopfzeilen (KC_PROXY_HEADERS=xforwarded) — dieselben, die
    Traefik für den Browser setzt.
    """
    import base64
    import json
    from urllib.parse import urlparse

    try:
        teil = token.split(".")[1]
        daten = json.loads(base64.urlsafe_b64decode(teil + "=" * (-len(teil) % 4)))
        aussteller = urlparse(str(daten.get("iss") or ""))
    except (IndexError, ValueError):
        return {}
    if aussteller.scheme not in ("http", "https") or not aussteller.hostname \
            or not aussteller.path.endswith(f"/realms/{_realm()}"):
        return {}
    port = aussteller.port or (443 if aussteller.scheme == "https" else 80)
    return {
        "X-Forwarded-Proto": aussteller.scheme,
        "X-Forwarded-Host": aussteller.netloc,
        "X-Forwarded-Port": str(port),
    }


# Obergrenze einer SSO-Sitzung. OTA selbst kennt keine — seine Sitzung rollt,
# solange jemand arbeitet. Keycloaks Vorgabe (10 Stunden) hätte jeden, der
# länger am Stück arbeitet, aus OTA geworfen, seit beide Sitzungen zusammen
# enden. Eine Woche ist die Grenze für den, der seinen Rechner nie ausmacht.
SSO_HOECHSTENS_S = 7 * 24 * 3600


def sitzungsfristen_setzen(leerlauf_minuten: int) -> None:
    """Keycloaks Leerlauf-Frist der SSO-Sitzung = OTAs Anmeldefrist.

    Damit gilt eine Uhr: Wer in OTA angemeldet ist, ist es auch in Keycloak,
    und eine fremde Anwendung lässt ihn ohne Maske herein — auch wenn der
    OTA-Tab eine Weile zu war.
    """
    leerlauf = int(leerlauf_minuten) * 60
    resp = ruf("PUT", "", json={
        "ssoSessionIdleTimeout": leerlauf,
        "ssoSessionMaxLifespan": max(leerlauf, SSO_HOECHSTENS_S),
    })
    if resp.status_code not in (200, 204):
        raise KeycloakFehler(f"Sitzungsfristen nicht gesetzt: {resp.text[:200]}")


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


# --- Die Verzeichnisanbindung verwalten (Etappe C) ----------------------
#
# Das ist der eigentliche Gewinn des Umbaus: Eine Administration soll ein
# Active Directory in **OTAs** Oberfläche einrichten und Keycloak dafür nicht
# öffnen müssen.
#
# Wichtig und leicht zu verwechseln: Die LDAP-Anbindung ist in Keycloak
# **keine** „Identity-Provider"-Ressource — das sind fremde OIDC- und
# SAML-Anbieter. Sie ist eine *Benutzer-Föderation* und liegt unter
# `components`. Daran hängt auch, warum das Dienstkonto `manage-realm`
# braucht (§5.5).

LDAP_PROVIDER = "org.keycloak.storage.UserStorageProvider"
LDAP_NAME = "ota-verzeichnis"


def _eins(wert: Any) -> list[str]:
    """Keycloak führt Komponentenwerte als Listen, auch einzelne."""
    return [str(wert)]


def verzeichnis_lesen() -> dict[str, Any] | None:
    """Die eingerichtete Anbindung, oder nichts."""
    resp = ruf("GET", f"/components?type={LDAP_PROVIDER}")
    if resp.status_code != 200:
        raise KeycloakFehler("Die Verzeichnisanbindung liess sich nicht lesen.")
    for teil in resp.json():
        if teil.get("name") == LDAP_NAME:
            werte = teil.get("config", {})
            return {
                "id": teil["id"],
                "server_uri": (werte.get("connectionUrl") or [""])[0],
                "base_dn": (werte.get("usersDn") or [""])[0],
                "bind_dn": (werte.get("bindDn") or [""])[0],
                "user_filter": (werte.get("customUserSearchFilter") or [""])[0],
                "login_attribute": (werte.get("usernameLDAPAttribute") or [""])[0],
                "kind": (werte.get("vendor") or [""])[0],
                "hat_kennwort": bool((werte.get("bindCredential") or [""])[0]),
                "is_enabled": (werte.get("enabled") or ["true"])[0] == "true",
            }
    return None


def _config(daten: dict[str, Any], kennwort: str | None) -> dict[str, Any]:
    """Aus OTAs Feldern die Komponentenkonfiguration von Keycloak."""
    art = daten.get("kind") or "ad"
    ist_ad = art == "ad"
    config: dict[str, Any] = {
        "enabled": _eins("true" if daten.get("is_enabled", True) else "false"),
        "vendor": _eins("ad" if ist_ad else "other"),
        "connectionUrl": _eins(daten["server_uri"]),
        "usersDn": _eins(daten["base_dn"]),
        "authType": _eins("simple"),
        "bindDn": _eins(daten.get("bind_dn") or ""),
        # Der Anmeldename. Bei einem Active Directory ist das
        # `sAMAccountName`, bei OpenLDAP `uid` — die häufigste Stolperstelle
        # bei dieser Einrichtung überhaupt.
        "usernameLDAPAttribute": _eins(daten.get("login_attribute")
                                       or ("sAMAccountName" if ist_ad else "uid")),
        "rdnLDAPAttribute": _eins("cn" if ist_ad else "uid"),
        "uuidLDAPAttribute": _eins("objectGUID" if ist_ad else "entryUUID"),
        "userObjectClasses": _eins("person, organizationalPerson, user"
                                   if ist_ad else "inetOrgPerson, organizationalPerson"),
        "searchScope": _eins("2"),
        # **Nur lesen.** OTA schreibt nicht ins Verzeichnis zurück, und schon
        # gar nicht Passwörter. Wer im AD etwas ändern will, tut das im AD.
        "editMode": _eins("READ_ONLY"),
        "importEnabled": _eins("true"),
        "syncRegistrations": _eins("false"),
        "trustEmail": _eins("true"),
        "connectionPooling": _eins("true"),
        "pagination": _eins("true"),
    }
    if daten.get("user_filter"):
        config["customUserSearchFilter"] = _eins(daten["user_filter"])
    if kennwort:
        config["bindCredential"] = _eins(kennwort)
    return config


def verzeichnis_setzen(daten: dict[str, Any], kennwort: str | None) -> dict[str, Any]:
    """Anbindung anlegen oder ändern.

    Ein leeres Kennwort heisst „nicht anfassen", nicht „löschen": Sonst
    verlöre eine Änderung an der Adresse nebenbei die Zugangsdaten, und das
    fiele erst bei der nächsten Anmeldung auf.
    """
    vorhanden = verzeichnis_lesen()
    config = _config(daten, kennwort)

    if vorhanden is None:
        if not kennwort:
            raise KeycloakFehler(
                "Für eine neue Anbindung wird das Kennwort des Dienstkontos gebraucht."
            )
        resp = ruf("POST", "/components", json={
            "name": LDAP_NAME, "providerId": "ldap",
            "providerType": LDAP_PROVIDER, "config": config,
        })
        if resp.status_code != 201:
            raise KeycloakFehler(f"Anlegen abgelehnt: {resp.text[:200]}")
        return verzeichnis_lesen() or {}

    # Ändern: Keycloak will die vollständige Darstellung zurück.
    alt = ruf("GET", f"/components/{vorhanden['id']}")
    if alt.status_code != 200:
        raise KeycloakFehler("Die vorhandene Anbindung liess sich nicht lesen.")
    darstellung = alt.json()
    darstellung["config"] = {**darstellung.get("config", {}), **config}
    resp = ruf("PUT", f"/components/{vorhanden['id']}", json=darstellung)
    if resp.status_code not in (204, 200):
        raise KeycloakFehler(f"Ändern abgelehnt: {resp.text[:200]}")
    return verzeichnis_lesen() or {}


def verzeichnis_entfernen() -> None:
    vorhanden = verzeichnis_lesen()
    if vorhanden is None:
        return
    resp = ruf("DELETE", f"/components/{vorhanden['id']}")
    if resp.status_code not in (204, 200):
        raise KeycloakFehler("Die Anbindung liess sich nicht entfernen.")


# Was Keycloak bei einer gescheiterten Verbindung meldet — und was es heisst.
#
# Bis zum 2026-09-25 stand fuer jeden Fall derselbe Satz da: „Der Server ist
# nicht erreichbar." Bei `ldaps://` mit einem Zertifikat aus einer Firmen-CA
# war das falsch und schickte die Suche an die Firewall, waehrend Keycloak
# laengst antwortete: Es kannte die CA nicht (`SSLHandshakeFailed`, im
# Protokoll „PKIX path building failed"). Keycloak liefert den Grund mit;
# er wurde nur nie gelesen.
_LDAP_FEHLER = {
    "SSLHandshakeFailed":
        "Der Server antwortet, aber die verschlüsselte Verbindung scheitert. "
        "Meist kennt Keycloak die CA des Verzeichnisses nicht — sie gehört als "
        "PEM-Datei nach deploy/keycloak-truststore/, danach Keycloak neu "
        "starten. Oder das Zertifikat passt nicht zur Adresse: Wer "
        "ldaps://<IP> einträgt, braucht ein Zertifikat mit dieser IP.",
    "UnknownHost":
        "Den Namen des Servers kann Keycloak nicht auflösen. Adresse prüfen, "
        "oder den Namensdienst des Hosts.",
    "SocketReset":
        "Am Port antwortet kein Verzeichnis. ldaps:// gehört zu Port 636, "
        "ldap:// zu 389.",
    "ConnectionRefused":
        "Der Server lehnt die Verbindung ab — stimmt der Port?",
}


def _verbindungsfehler(resp) -> str:
    try:
        code = (resp.json() or {}).get("errorMessage", "")
    except ValueError:
        code = ""
    hinweis = _LDAP_FEHLER.get(code)
    if hinweis:
        return hinweis
    zusatz = f" (Keycloak meldet: {code})" if code else ""
    return ("Der Server ist nicht erreichbar. Stimmen Adresse und Port, und "
            "kommt Keycloak überhaupt dorthin — steht eine Firewall dazwischen, "
            f"muss sie 636 bzw. 389 vom OTA-Host zum Verzeichnis freigeben?{zusatz}")


def verzeichnis_testen(daten: dict[str, Any], kennwort: str | None) -> dict[str, Any]:
    """Verbindung und Anmeldung des Dienstkontos prüfen, ohne etwas zu speichern.

    Keycloak bringt dafür einen eigenen Aufruf mit. Er prüft genau die beiden
    Dinge, an denen es in der Praxis scheitert: Kommt man an den Server heran,
    und lässt er das Dienstkonto herein?
    """
    ergebnis: dict[str, Any] = {"verbindung": False, "anmeldung": False, "hinweise": []}

    grund = {"action": "testConnection", "connectionUrl": daten["server_uri"],
             "bindDn": daten.get("bind_dn") or "", "bindCredential": kennwort or "",
             "authType": "simple", "useTruststoreSpi": "always",
             "connectionTimeout": "10000", "startTls": "false"}

    resp = ruf("POST", "/testLDAPConnection", json=grund)
    ergebnis["verbindung"] = resp.status_code == 204
    if not ergebnis["verbindung"]:
        ergebnis["hinweise"].append(_verbindungsfehler(resp))
        return ergebnis

    resp = ruf("POST", "/testLDAPConnection",
               json={**grund, "action": "testAuthentication"})
    ergebnis["anmeldung"] = resp.status_code == 204
    if not ergebnis["anmeldung"]:
        ergebnis["hinweise"].append(
            "Der Server antwortet, lässt das Dienstkonto aber nicht herein. "
            "Stimmen Bind-DN und Kennwort?")
    return ergebnis


def verzeichnis_abgleichen(voll: bool = False) -> dict[str, Any]:
    """Konten aus dem Verzeichnis holen.

    `voll` liest alles, sonst nur das seit dem letzten Mal Geänderte. Der
    volle Lauf ist der, den man nach dem Einrichten einmal braucht.
    """
    vorhanden = verzeichnis_lesen()
    if vorhanden is None:
        raise KeycloakFehler("Es ist keine Verzeichnisanbindung eingerichtet.")
    art = "triggerFullSync" if voll else "triggerChangedUsersSync"
    resp = ruf("POST", f"/user-storage/{vorhanden['id']}/sync?action={art}")
    if resp.status_code not in (200, 204):
        raise KeycloakFehler(f"Der Abgleich scheiterte: {resp.text[:200]}")
    try:
        return resp.json()
    except Exception:  # noqa: BLE001
        return {"status": "ok"}


# --- Clients für fremde Anwendungen (Etappe D) --------------------------

def client_anlegen(client_id: str, name: str, redirect_uri: str) -> str:
    """Legt einen OIDC-Client an und gibt sein Geheimnis zurück — einmal.

    Das Geheimnis wird hier erzeugt und **nicht** in OTA gespeichert. Es steht
    danach nur noch in Keycloak; wer es verliert, lässt ein neues erzeugen.
    Ein zweiter Ort, an dem es liegt, wäre ein zweiter Ort, an dem es
    verlorengehen kann.

    Der Gruppen-Bereich `ota-groups` ist voreingestellt: Ohne ihn stünde im
    Token keine Gruppenzugehörigkeit, und die fremde Anwendung könnte ihre
    eigenen Rechte nicht daran hängen.
    """
    import secrets as _secrets

    geheimnis = _secrets.token_urlsafe(32)
    resp = ruf("POST", "/clients", json={
        "clientId": client_id,
        "name": name,
        "enabled": True,
        "publicClient": False,
        "secret": geheimnis,
        "standardFlowEnabled": True,
        "directAccessGrantsEnabled": False,
        "serviceAccountsEnabled": False,
        "protocol": "openid-connect",
        "redirectUris": [redirect_uri],
        "webOrigins": ["+"],
        "defaultClientScopes": ["profile", "email", "roles", "ota-groups"],
    })
    if resp.status_code == 409:
        raise KeycloakFehler(f"Den Client \u201e{client_id}\u201c gibt es in Keycloak schon.")
    if resp.status_code != 201:
        raise KeycloakFehler(f"Client anlegen abgelehnt: {resp.text[:200]}")
    return geheimnis


def client_entfernen(client_id: str) -> None:
    resp = ruf("GET", f"/clients?clientId={client_id}")
    if resp.status_code != 200 or not resp.json():
        return
    kid = resp.json()[0]["id"]
    ruf("DELETE", f"/clients/{kid}")


def client_neues_geheimnis(client_id: str) -> str:
    resp = ruf("GET", f"/clients?clientId={client_id}")
    if resp.status_code != 200 or not resp.json():
        raise KeycloakFehler(f"Den Client \u201e{client_id}\u201c gibt es in Keycloak nicht.")
    kid = resp.json()[0]["id"]
    neu = ruf("POST", f"/clients/{kid}/client-secret")
    if neu.status_code not in (200, 201):
        raise KeycloakFehler("Ein neues Geheimnis liess sich nicht erzeugen.")
    return str(neu.json().get("value") or "")


def client_da(client_id: str) -> bool:
    resp = ruf("GET", f"/clients?clientId={client_id}")
    return resp.status_code == 200 and bool(resp.json())


# --- Konten und Gruppen (Etappe C, zweite Hälfte) -----------------------
#
# Ab hier legt OTA in Keycloak an, statt nur zu lesen. Zwei Regeln, die aus
# §5b folgen und hier nicht verhandelbar sind:
#
#   * **Nichts löschen.** Ein Konto wird deaktiviert, nicht entfernt. In einem
#     fremden Realm gehört es womöglich noch drei anderen Anwendungen.
#   * **Nur die eigenen Gruppen.** OTA arbeitet unterhalb eines vereinbarten
#     Pfads und lässt alles daneben in Ruhe.

GRUPPEN_WURZEL = "ota"


def konto_finden(username: str) -> dict[str, Any] | None:
    resp = ruf("GET", "/users", params={"username": username, "exact": "true"})
    if resp.status_code != 200:
        raise KeycloakFehler("Die Kontenliste liess sich nicht lesen.")
    treffer = resp.json()
    return treffer[0] if treffer else None


def konto_anlegen(username: str, *, email: str | None, anzeigename: str | None,
                  passwort: str, wechseln: bool = True) -> str:
    """Legt ein Konto an und gibt seine Kennung zurück.

    `wechseln` setzt die erforderliche Aktion „Passwort ändern". Das ist der
    Normalfall bei der Übernahme (§5.1): Der Mensch bekommt ein Einmal-Passwort
    und vergibt beim ersten Anmelden sein eigenes.

    Vor- und Nachname werden mitgegeben, auch wenn OTA sie nicht kennt.
    Keycloak verlangt ein vollständiges Profil, sonst lehnt es die Anmeldung
    mit „Account is not fully set up" ab — eine Meldung, die niemand mit einem
    fehlenden Nachnamen in Verbindung bringt. Gemessen am 2026-08-28.
    """
    teile = (anzeigename or username).split(" ", 1)
    korpus = {
        "username": username,
        "enabled": True,
        "emailVerified": True,
        "firstName": teile[0][:64] or username,
        "lastName": (teile[1] if len(teile) > 1 else username)[:64],
        "requiredActions": ["UPDATE_PASSWORD"] if wechseln else [],
        "credentials": [{"type": "password", "value": passwort, "temporary": False}],
    }
    if email:
        korpus["email"] = email

    resp = ruf("POST", "/users", json=korpus)
    if resp.status_code == 409:
        raise KeycloakFehler(f"Ein Konto {username} gibt es in Keycloak schon.")
    if resp.status_code != 201:
        raise KeycloakFehler(f"Konto anlegen abgelehnt: {resp.text[:200]}")

    angelegt = konto_finden(username)
    if angelegt is None:
        raise KeycloakFehler("Das Konto wurde angelegt, ist aber nicht auffindbar.")
    return str(angelegt["id"])


def konto_sperren(sub: str, gesperrt: bool = True) -> None:
    """Deaktiviert ein Konto — und löscht es nie."""
    resp = ruf("PUT", f"/users/{sub}", json={"enabled": not gesperrt})
    if resp.status_code not in (204, 200):
        raise KeycloakFehler(f"Das Konto liess sich nicht ändern: {resp.text[:150]}")


def gruppe_sorgen(name: str) -> str:
    """Die OTA-Gruppe mit diesem Namen — angelegt, falls es sie nicht gibt.

    Unterhalb von `/ota`, damit in einem fremden Realm klar ist, was OTA
    gehört und was nicht anzufassen ist.
    """
    resp = ruf("GET", "/groups", params={"search": GRUPPEN_WURZEL})
    wurzel = None
    if resp.status_code == 200:
        wurzel = next((g for g in resp.json() if g["name"] == GRUPPEN_WURZEL), None)

    if wurzel is None:
        neu = ruf("POST", "/groups", json={"name": GRUPPEN_WURZEL})
        if neu.status_code not in (201, 409):
            raise KeycloakFehler(f"Gruppenwurzel anlegen: {neu.text[:150]}")
        resp = ruf("GET", "/groups", params={"search": GRUPPEN_WURZEL})
        wurzel = next((g for g in resp.json() if g["name"] == GRUPPEN_WURZEL), None)
    if wurzel is None:
        raise KeycloakFehler("Die Gruppenwurzel ist nicht auffindbar.")

    kinder = ruf("GET", f"/groups/{wurzel['id']}/children")
    if kinder.status_code == 200:
        treffer = next((g for g in kinder.json() if g["name"] == name), None)
        if treffer:
            return str(treffer["id"])

    angelegt = ruf("POST", f"/groups/{wurzel['id']}/children", json={"name": name})
    if angelegt.status_code not in (201, 409):
        raise KeycloakFehler(f"Gruppe {name} anlegen: {angelegt.text[:150]}")

    kinder = ruf("GET", f"/groups/{wurzel['id']}/children")
    treffer = next((g for g in kinder.json() if g["name"] == name), None)
    if treffer is None:
        raise KeycloakFehler(f"Die Gruppe {name} ist nach dem Anlegen nicht auffindbar.")
    return str(treffer["id"])


def gruppen_setzen(sub: str, namen: list[str]) -> None:
    """Setzt die OTA-Gruppen eines Kontos — und lässt fremde in Ruhe."""
    ist = ruf("GET", f"/users/{sub}/groups")
    if ist.status_code != 200:
        raise KeycloakFehler("Die Gruppen des Kontos liessen sich nicht lesen.")

    # Nur, was unterhalb von /ota liegt. Alles andere gehört jemand anderem.
    unsere = {g["name"]: g["id"] for g in ist.json()
              if str(g.get("path", "")).startswith(f"/{GRUPPEN_WURZEL}/")}

    for name in namen:
        if name not in unsere:
            gid = gruppe_sorgen(name)
            ruf("PUT", f"/users/{sub}/groups/{gid}")

    for name, gid in unsere.items():
        if name not in namen:
            ruf("DELETE", f"/users/{sub}/groups/{gid}")


def rolle_setzen(sub: str, rolle: str, an: bool) -> None:
    """Weist eine Realm-Rolle zu oder nimmt sie weg. Für `zweiter-faktor`."""
    r = ruf("GET", f"/roles/{rolle}")
    if r.status_code != 200:
        raise KeycloakFehler(f"Die Rolle {rolle} gibt es nicht.")
    korpus = [r.json()]
    weg = "POST" if an else "DELETE"
    resp = ruf(weg, f"/users/{sub}/role-mappings/realm", json=korpus)
    if resp.status_code not in (204, 200):
        raise KeycloakFehler(f"Rolle {rolle} setzen: {resp.text[:150]}")


# --- Konten, die OTA in Keycloak verwaltet (2026-10-08) -------------------
#
# Seit dem 2026-10-08 entsteht ein Konto, das in OTA angelegt wird, direkt in
# Keycloak — lokal bleibt nur das Notfallkonto (Betreiber). Was dafuer noch
# fehlte: ein Konto lesen, sein Passwort setzen, sein Profil pflegen, seinen
# zweiten Faktor zuruecksetzen.

def konto_lesen(sub: str) -> dict[str, Any] | None:
    resp = ruf("GET", f"/users/{sub}")
    if resp.status_code == 404:
        return None
    if resp.status_code != 200:
        raise KeycloakFehler(f"Das Konto liess sich nicht lesen: {resp.text[:150]}")
    return resp.json()


def aus_verzeichnis(konto: dict[str, Any] | None) -> bool:
    """Gehoert das Konto einem Verzeichnis (AD/LDAP ueber die Foederation)?
    Dann gehoeren ihm auch Passwort, Name und Adresse — nicht OTA."""
    return bool(konto and konto.get("federationLink"))


def konto_passwort(sub: str, passwort: str, wechseln: bool) -> None:
    """Setzt das Passwort. `wechseln` heisst: beim naechsten Anmelden aendern."""
    resp = ruf("PUT", f"/users/{sub}/reset-password",
               json={"type": "password", "value": passwort, "temporary": bool(wechseln)})
    if resp.status_code not in (200, 204):
        # Keycloaks Meldung zur Passwortregel ist das, was der Mensch wissen muss.
        try:
            grund = resp.json().get("error_description") or resp.json().get("errorMessage") \
                or resp.text
        except ValueError:
            grund = resp.text
        raise KeycloakFehler(f"Keycloak nimmt das Passwort nicht an: {str(grund)[:200]}")


def konto_profil(sub: str, *, anzeigename: str | None, email: str | None,
                 aktiv: bool, verzeichnis: bool) -> None:
    """Name, Adresse und aktiv/gesperrt. Bei einem Verzeichniskonto nur der
    Schalter — Name und Adresse kommen dort aus dem Verzeichnis, und ein
    nur lesend angebundenes laesst sie sich nicht ueberschreiben."""
    korpus: dict[str, Any] = {"enabled": bool(aktiv)}
    if not verzeichnis:
        teile = (anzeigename or "").split(" ", 1)
        if anzeigename:
            korpus["firstName"] = teile[0][:64]
            korpus["lastName"] = (teile[1] if len(teile) > 1 else teile[0])[:64]
        korpus["email"] = email or None
        korpus["emailVerified"] = bool(email)
    resp = ruf("PUT", f"/users/{sub}", json=korpus)
    if resp.status_code not in (200, 204):
        raise KeycloakFehler(f"Das Konto liess sich nicht ändern: {resp.text[:150]}")


def zweiten_faktor_entfernen(sub: str) -> int:
    """Entfernt Einmalkennwort und Passkeys eines Kontos. Gibt die Anzahl zurueck.
    Das Passwort bleibt."""
    resp = ruf("GET", f"/users/{sub}/credentials")
    if resp.status_code != 200:
        raise KeycloakFehler("Die Anmeldemittel des Kontos liessen sich nicht lesen.")
    weg = 0
    for c in resp.json():
        if c.get("type") in ("otp", "webauthn", "webauthn-passwordless"):
            r = ruf("DELETE", f"/users/{sub}/credentials/{c['id']}")
            if r.status_code in (200, 204):
                weg += 1
    return weg


# --- Gruppen aus dem Verzeichnis (Handbuch Kapitel 08) --------------------
#
# Keycloak liest die Gruppen eines angebundenen Verzeichnisses und fuehrt sie
# als **Rollen des Clients `ota-verzeichnis`** — nicht als Gruppen. Das ist
# die eine Entscheidung, an der hier alles haengt: Gruppen stuenden im Token
# unter `groups`, neben den OTA-Gruppen und mit demselben kurzen Namen. Eine
# Verzeichnisgruppe „admins" machte dann jeden ihrer Mitglieder zum
# OTA-Administrator. Als Rollen eines eigenen Clients stehen sie getrennt, und
# was daraus in OTA wird, entscheidet allein die Kopplung an einer OTA-Gruppe.
#
# Gelesen wird **live** (`cachePolicy: NO_CACHE`): Eine Aenderung im
# Verzeichnis gilt bei der naechsten Anmeldung, ohne auf einen Abgleich zu
# warten. Gemessen am 2026-10-19 gegen Keycloak 26.7: Mit dem Vorgabe-Cache
# sah eine Anmeldung noch Minuten spaeter die alte Mitgliedschaft.

VERZEICHNIS_CLIENT = "ota-verzeichnis"
GRUPPEN_MAPPER = "ota-gruppen"
MAPPER_TYP = "org.keycloak.storage.ldap.mappers.LDAPStorageMapper"

# Die drei Formen, in denen ein Verzeichnis Gruppen ablegt: Objektklasse,
# Attribut der Mitglieder, und ob darin ein DN oder ein Anmeldename steht.
GRUPPENFORMEN: dict[str, tuple[str, str, str]] = {
    "groupOfNames": ("groupOfNames", "member", "DN"),
    "groupOfUniqueNames": ("groupOfUniqueNames", "uniqueMember", "DN"),
    "posixGroup": ("posixGroup", "memberUid", "UID"),
}


def _verzeichnis_client() -> str:
    """Die interne Kennung von `ota-verzeichnis` — legt den Client an, wenn
    noch keiner da ist. Er meldet niemanden an (`bearerOnly`); er traegt nur
    die Rollen."""
    resp = ruf("GET", "/clients", params={"clientId": VERZEICHNIS_CLIENT})
    if resp.status_code == 200 and resp.json():
        return str(resp.json()[0]["id"])
    neu = ruf("POST", "/clients", json={
        "clientId": VERZEICHNIS_CLIENT, "name": "Verzeichnisgruppen (OTA)",
        "enabled": True, "publicClient": False, "bearerOnly": True,
        "standardFlowEnabled": False, "directAccessGrantsEnabled": False,
        "description": "Gruppen aus dem Verzeichnis, als Rollen. Von OTA verwaltet.",
    })
    if neu.status_code not in (201, 409):
        raise KeycloakFehler(f"Client {VERZEICHNIS_CLIENT} anlegen: {neu.text[:150]}")
    resp = ruf("GET", "/clients", params={"clientId": VERZEICHNIS_CLIENT})
    return str(resp.json()[0]["id"])


def _gruppen_mapper(fid: str) -> dict[str, Any] | None:
    resp = ruf("GET", "/components", params={"parent": fid, "type": MAPPER_TYP})
    if resp.status_code != 200:
        raise KeycloakFehler("Die Zuordnungen der Anbindung liessen sich nicht lesen.")
    return next((m for m in resp.json() if m.get("name") == GRUPPEN_MAPPER), None)


def verzeichnisgruppen_lesen() -> dict[str, Any] | None:
    """Wie die Gruppen gelesen werden — oder nichts, wenn gar nicht."""
    anbindung = verzeichnis_lesen()
    if anbindung is None:
        return None
    m = _gruppen_mapper(anbindung["id"])
    if m is None:
        return None
    c = m.get("config", {})
    klasse = (c.get("role.object.classes") or [""])[0]
    form = next((k for k, v in GRUPPENFORMEN.items() if v[0] == klasse), klasse)
    return {
        "gruppen_dn": (c.get("roles.dn") or [""])[0],
        "form": form,
        "filter": (c.get("roles.ldap.filter") or [""])[0],
    }


def _mapper_setzen(fid: str, gruppen_dn: str, form: str, filt: str,
                   login_attribut: str) -> str:
    klasse, attribut, art = GRUPPENFORMEN[form]
    vorhanden = _gruppen_mapper(fid)
    if vorhanden is not None:
        ruf("DELETE", f"/components/{vorhanden['id']}")
    resp = ruf("POST", "/components", json={
        "name": GRUPPEN_MAPPER, "providerId": "role-ldap-mapper",
        "providerType": MAPPER_TYP, "parentId": fid,
        "config": {
            "roles.dn": [gruppen_dn],
            "role.name.ldap.attribute": ["cn"],
            "role.object.classes": [klasse],
            "membership.ldap.attribute": [attribut],
            "membership.attribute.type": [art],
            "membership.user.ldap.attribute": [login_attribut or "uid"],
            "roles.ldap.filter": [filt],
            # Nur lesen — wie die ganze Anbindung.
            "mode": ["READ_ONLY"],
            "user.roles.retrieve.strategy": ["LOAD_ROLES_BY_MEMBER_ATTRIBUTE"],
            "use.realm.roles.mapping": ["false"],
            "client.id": [VERZEICHNIS_CLIENT],
        },
    })
    if resp.status_code != 201:
        raise KeycloakFehler(f"Gruppenzuordnung anlegen abgelehnt: {resp.text[:200]}")
    return _gruppen_mapper(fid)["id"]


def _rollen_leeren(cid: str) -> None:
    """Alle Rollen von `ota-verzeichnis` weg. Sie sind nur ein Abbild des
    Verzeichnisses; nach einer geaenderten Einstellung stuenden sonst Gruppen
    darin, die es unter der neuen gar nicht gibt."""
    for rolle in ruf("GET", f"/clients/{cid}/roles").json() or []:
        ruf("DELETE", f"/clients/{cid}/roles/{rolle['name']}")


def _mapper_abgleichen(fid: str, mid: str) -> int:
    """Holt die Gruppen ins Abbild. Rueckgabe: wie viele es sind."""
    resp = ruf("POST", f"/user-storage/{fid}/mappers/{mid}/sync",
               params={"direction": "fedToKeycloak"})
    if resp.status_code not in (200, 204):
        raise KeycloakFehler(f"Gruppen holen scheiterte: {resp.text[:200]}")
    try:
        d = resp.json()
        return int(d.get("added", 0)) + int(d.get("updated", 0))
    except (ValueError, AttributeError):
        return 0


def verzeichnisgruppen_setzen(gruppen_dn: str, form: str, filt: str = "") -> dict[str, Any]:
    """Richtet das Lesen der Gruppen ein. `form` darf `auto` sein: Dann wird
    jede Form probiert, und die erste, unter der Gruppen auftauchen, bleibt.
    Rueckgabe: die gewaehlte Form und die gefundenen Gruppen."""
    anbindung = verzeichnis_lesen()
    if anbindung is None:
        raise KeycloakFehler("Erst das Verzeichnis anbinden, dann die Gruppen.")
    fid = anbindung["id"]
    cid = _verzeichnis_client()
    filt = (filt or "").strip()
    if filt and not (filt.startswith("(") and filt.endswith(")")):
        raise KeycloakFehler("Ein LDAP-Filter steht in Klammern, z. B. (cn=ki-*).")

    # Live lesen, nicht aus Keycloaks Zwischenspeicher.
    komp = ruf("GET", f"/components/{fid}").json()
    if (komp.get("config", {}).get("cachePolicy") or [""])[0] != "NO_CACHE":
        komp.setdefault("config", {})["cachePolicy"] = ["NO_CACHE"]
        ruf("PUT", f"/components/{fid}", json=komp)

    formen = list(GRUPPENFORMEN) if form == "auto" else [form]
    if any(f not in GRUPPENFORMEN for f in formen):
        raise KeycloakFehler(f"Unbekannte Form: {form}")
    gewaehlt, anzahl = formen[0], 0
    for f in formen:
        _rollen_leeren(cid)
        mid = _mapper_setzen(fid, gruppen_dn, f, filt, anbindung.get("login_attribute") or "uid")
        anzahl = _mapper_abgleichen(fid, mid)
        gewaehlt = f
        if anzahl:
            break
    return {"gruppen_dn": gruppen_dn, "form": gewaehlt, "filter": filt,
            "gruppen": verzeichnisgruppen_liste()}


def verzeichnisgruppen_entfernen() -> None:
    anbindung = verzeichnis_lesen()
    if anbindung is None:
        return
    m = _gruppen_mapper(anbindung["id"])
    if m is not None:
        ruf("DELETE", f"/components/{m['id']}")
    _rollen_leeren(_verzeichnis_client())


def verzeichnisgruppen_abgleichen() -> int:
    """Neue und verschwundene Gruppen ins Abbild. Mitgliedschaften liest
    Keycloak ohnehin live."""
    anbindung = verzeichnis_lesen()
    if anbindung is None:
        return 0
    m = _gruppen_mapper(anbindung["id"])
    if m is None:
        return 0
    return _mapper_abgleichen(anbindung["id"], m["id"])


def verzeichnisgruppen_liste() -> list[str]:
    resp = ruf("GET", f"/clients/{_verzeichnis_client()}/roles")
    if resp.status_code != 200:
        raise KeycloakFehler("Die Verzeichnisgruppen liessen sich nicht lesen.")
    return sorted(r["name"] for r in resp.json())


def verzeichnisgruppe_mitglieder(name: str) -> list[dict[str, str]]:
    """Wer im Verzeichnis in dieser Gruppe ist: `sub` und Anmeldename.

    Leer, wenn es die Gruppe nicht (mehr) gibt — eine verschwundene Gruppe hat
    keine Mitglieder, und genau so soll der Abgleich sie behandeln.
    """
    cid = _verzeichnis_client()
    raus: list[dict[str, str]] = []
    erstes = 0
    while True:
        resp = ruf("GET", f"/clients/{cid}/roles/{name}/users",
                   params={"first": erstes, "max": 500})
        if resp.status_code == 404:
            return []
        if resp.status_code != 200:
            raise KeycloakFehler(f"Mitglieder von {name} liessen sich nicht lesen.")
        teil = resp.json()
        raus += [{"sub": str(u["id"]), "username": u.get("username", "")} for u in teil]
        if len(teil) < 500:
            return raus
        erstes += 500


def verzeichnisgruppen_von(sub: str) -> list[str]:
    """Die Verzeichnisgruppen eines Kontos, live aus dem Verzeichnis."""
    resp = ruf("GET", f"/users/{sub}/role-mappings/clients/{_verzeichnis_client()}")
    if resp.status_code == 404:
        return []
    if resp.status_code != 200:
        raise KeycloakFehler("Die Verzeichnisgruppen des Kontos liessen sich nicht lesen.")
    return sorted(r["name"] for r in resp.json())


# --- Zugang zu fremden Anwendungen (Handbuch Kapitel 18) ------------------
#
# Bis zum 2026-10-19 entschieden die Gruppen einer Anwendung nur, wer ihre
# Kachel **sieht**. Anmelden konnte sich jedes Konto des Realms — wer die
# Adresse kannte, kam hinein. Jetzt prueft Keycloak selbst: Jede Anwendung hat
# die Rolle `zugang`, OTA haengt sie an die Keycloak-Gruppen `/ota/<gruppe>`
# der zugewiesenen Gruppen, und ein eigener Anmeldefluss weist ab, wem sie
# fehlt.
#
# **Der Fluss ist eine Kopie des Anmeldeflusses des Realms**, mit der Pruefung
# in **beiden** Zweigen: nach dem Formular und nach der SSO-Sitzung. Oben auf
# den Fluss gesetzt ginge nicht — Keycloak ignoriert Alternativen (die
# SSO-Sitzung) auf einer Ebene, auf der etwas Pflicht ist. Und nur im
# Formular-Zweig kaeme jeder, der in OTA schon angemeldet ist, ungeprueft
# durch. Beides gemessen am 2026-10-19.
#
# Weil es eine Kopie ist, veraltet sie, wenn sich der Anmeldefluss des Realms
# aendert (ein neuer zweiter Faktor). Der Name traegt deshalb einen
# Fingerabdruck des Vorbilds; `anwendungen_nachziehen()` baut beim Start neu,
# was nicht mehr passt.

ZUGANG_ROLLE = "zugang"
FLUSS_PRAEFIX = "ota-app"


def _q(text: str) -> str:
    from urllib.parse import quote
    return quote(text, safe="")


def _client(client_id: str) -> dict[str, Any]:
    resp = ruf("GET", "/clients", params={"clientId": client_id})
    if resp.status_code != 200 or not resp.json():
        raise KeycloakFehler(f"Den Client „{client_id}“ gibt es in Keycloak nicht.")
    return resp.json()[0]


def _vorbild() -> tuple[str, str]:
    """Der Anmeldefluss des Realms und sein Fingerabdruck."""
    import hashlib
    import json as _json

    alias = ruf("GET", "").json().get("browserFlow") or "browser"
    schritte = ruf("GET", f"/authentication/flows/{_q(alias)}/executions").json()
    kern = [(s.get("level"), s.get("index"), s.get("providerId") or s.get("displayName"),
             s.get("requirement"), bool(s.get("authenticationConfig"))) for s in schritte]
    return alias, hashlib.sha1(_json.dumps(kern).encode()).hexdigest()[:8]


def _fluss_bauen(alias: str, vorbild: str, rolle: str) -> str:
    """Kopiert das Vorbild und setzt die Pruefung in beide Zweige."""
    resp = ruf("POST", f"/authentication/flows/{_q(vorbild)}/copy", json={"newName": alias})
    if resp.status_code not in (201, 409):
        raise KeycloakFehler(f"Anmeldefluss kopieren: {resp.text[:200]}")

    def schritte() -> list[dict[str, Any]]:
        return ruf("GET", f"/authentication/flows/{_q(alias)}/executions").json()

    def pflicht(sid: str, wert: str) -> None:
        s = next(x for x in schritte() if x["id"] == sid)
        s["requirement"] = wert
        r = ruf("PUT", f"/authentication/flows/{_q(alias)}/executions", json=s)
        if r.status_code not in (200, 204):
            raise KeycloakFehler(f"Anmeldefluss einstellen: {r.text[:200]}")

    def unterfluss(oben: str, name: str) -> dict[str, Any]:
        r = ruf("POST", f"/authentication/flows/{_q(oben)}/executions/flow",
                json={"alias": name, "type": "basic-flow",
                      "provider": "registration-page-form", "description": ""})
        if r.status_code != 201:
            raise KeycloakFehler(f"Anmeldefluss erweitern: {r.text[:200]}")
        return next(x for x in schritte() if x.get("displayName") == name)

    def schritt(oben: str, anbieter: str) -> dict[str, Any]:
        r = ruf("POST", f"/authentication/flows/{_q(oben)}/executions/execution",
                json={"provider": anbieter})
        if r.status_code != 201:
            raise KeycloakFehler(f"Anmeldefluss erweitern: {r.text[:200]}")
        return [x for x in schritte() if x.get("providerId") == anbieter][-1]

    def pruefung(oben: str, name: str) -> None:
        zweig = unterfluss(oben, name)
        pflicht(zweig["id"], "CONDITIONAL")
        bed = schritt(name, "conditional-user-role")
        pflicht(bed["id"], "REQUIRED")
        ruf("POST", f"/authentication/executions/{bed['id']}/config",
            json={"alias": f"{name} bedingung",
                  "config": {"condUserRole": rolle, "negate": "true"}})
        nein = schritt(name, "deny-access-authenticator")
        pflicht(nein["id"], "REQUIRED")
        ruf("POST", f"/authentication/executions/{nein['id']}/config",
            json={"alias": f"{name} meldung",
                  "config": {"denyErrorMessage":
                             "Kein Zugang zu dieser Anwendung. Die Verwaltung von "
                             "OpenTerminalApps kann ihn freigeben."}})

    oben = [x for x in schritte() if x["level"] == 0]
    formular = next((x for x in oben if x.get("authenticationFlow")
                     and str(x.get("displayName", "")).endswith(" forms")), None)
    keks = next((x for x in oben if x.get("providerId") == "auth-cookie"), None)
    if formular is None or keks is None:
        raise KeycloakFehler("Der Anmeldefluss des Realms hat nicht die erwartete Form "
                             "(Cookie und Formular). Die Pruefung je Anwendung geht so nicht.")

    pruefung(formular["displayName"], f"{alias} zugang formular")
    sso = unterfluss(alias, f"{alias} sso")
    pflicht(sso["id"], "ALTERNATIVE")
    neu_keks = schritt(f"{alias} sso", "auth-cookie")
    pflicht(neu_keks["id"], "REQUIRED")
    pruefung(f"{alias} sso", f"{alias} zugang sso")
    ruf("DELETE", f"/authentication/executions/{keks['id']}")
    for _ in range(12):
        s = next(x for x in schritte() if x.get("displayName") == f"{alias} sso")
        if s["index"] == 0:
            break
        ruf("POST", f"/authentication/executions/{s['id']}/raise-priority")
    return next(f["id"] for f in ruf("GET", "/authentication/flows").json()
                if f["alias"] == alias)


def _fluss_weg(fluss_id: str | None) -> None:
    if not fluss_id:
        return
    f = ruf("GET", f"/authentication/flows/{fluss_id}")
    if f.status_code == 200 and str(f.json().get("alias", "")).startswith(FLUSS_PRAEFIX + " "):
        ruf("DELETE", f"/authentication/flows/{fluss_id}")


def anwendung_zugang(client_id: str, gruppen: list[str], fuer_alle: bool) -> None:
    """Wer sich bei dieser Anwendung anmelden darf.

    `fuer_alle`: jeder mit einem Konto — dann gilt der gewoehnliche
    Anmeldefluss. Sonst nur Mitglieder der genannten OTA-Gruppen, und ohne
    Gruppe niemand.
    """
    c = _client(client_id)
    cid = c["id"]
    if ruf("GET", f"/clients/{cid}/roles/{ZUGANG_ROLLE}").status_code == 404:
        ruf("POST", f"/clients/{cid}/roles", json={
            "name": ZUGANG_ROLLE,
            "description": "Darf sich anmelden. Von OTA an die Gruppen gehaengt."})
    rolle = ruf("GET", f"/clients/{cid}/roles/{ZUGANG_ROLLE}").json()

    soll = set() if fuer_alle else {gruppe_sorgen(n) for n in gruppen}
    ist = {str(g["id"]) for g in
           (ruf("GET", f"/clients/{cid}/roles/{ZUGANG_ROLLE}/groups").json() or [])}
    for gid in soll - ist:
        ruf("POST", f"/groups/{gid}/role-mappings/clients/{cid}", json=[rolle])
    for gid in ist - soll:
        ruf("DELETE", f"/groups/{gid}/role-mappings/clients/{cid}", json=[rolle])

    gebunden = (c.get("authenticationFlowBindingOverrides") or {}).get("browser")
    if fuer_alle:
        if gebunden:
            # Ein leerer Wert, kein fehlender Schluessel: Fehlt er, laesst
            # Keycloak die alte Zuordnung stehen (gemessen 2026-10-19).
            c["authenticationFlowBindingOverrides"] = {
                **c["authenticationFlowBindingOverrides"], "browser": ""}
            ruf("PUT", f"/clients/{cid}", json=c)
            _fluss_weg(gebunden)
        return

    vorbild, abdruck = _vorbild()
    alias = f"{FLUSS_PRAEFIX} {client_id} {abdruck}"
    if gebunden:
        g = ruf("GET", f"/authentication/flows/{gebunden}")
        if g.status_code == 200 and g.json().get("alias") == alias:
            return
    vorhanden = next((f["id"] for f in ruf("GET", "/authentication/flows").json()
                      if f["alias"] == alias), None)
    if vorhanden:
        ruf("DELETE", f"/authentication/flows/{vorhanden}")
    neu = _fluss_bauen(alias, vorbild, f"{client_id}.{ZUGANG_ROLLE}")
    c = _client(client_id)
    c["authenticationFlowBindingOverrides"] = {
        **(c.get("authenticationFlowBindingOverrides") or {}), "browser": neu}
    r = ruf("PUT", f"/clients/{cid}", json=c)
    if r.status_code not in (200, 204):
        raise KeycloakFehler(f"Anmeldefluss zuordnen: {r.text[:200]}")
    if gebunden and gebunden != neu:
        _fluss_weg(gebunden)


def anwendung_fluss_entfernen(client_id: str) -> None:
    """Der eigene Anmeldefluss einer Anwendung, die geht."""
    try:
        c = _client(client_id)
    except KeycloakFehler:
        c = None
    gebunden = ((c or {}).get("authenticationFlowBindingOverrides") or {}).get("browser")
    if c is not None and gebunden:
        c["authenticationFlowBindingOverrides"] = {
            **c["authenticationFlowBindingOverrides"], "browser": ""}
        ruf("PUT", f"/clients/{c['id']}", json=c)
    _fluss_weg(gebunden)
    # Und was eine fruehere Fassung liegen liess.
    for f in ruf("GET", "/authentication/flows").json() or []:
        if str(f.get("alias", "")).startswith(f"{FLUSS_PRAEFIX} {client_id} "):
            ruf("DELETE", f"/authentication/flows/{f['id']}")
