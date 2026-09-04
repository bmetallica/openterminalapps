from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OTA_", extra="ignore")

    database_url: str = "postgresql+psycopg://ota:ota@db:5432/ota"

    # Wird beim ersten Start erzeugt, falls nicht gesetzt. In Produktion
    # gehoert er in die .env, sonst sind nach jedem Neustart alle Sitzungen
    # ungueltig.
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_days: int = 14

    # Basisadresse des Agents. Nur dieser Dienst fasst Docker an.
    agent_url: str = "http://agent:8100"
    agent_token: str = ""

    # Wohin die persistenten Profile gemountet werden.
    profiles_root: str = "/srv/ota/profiles"

    # Fuer die Datenbanksicherung: Der Agent ruft pg_dump im DB-Container auf.
    db_container: str = "ota-db"
    db_user: str = "ota"
    db_name: str = "ota"

    # Container, die waehrend eines Golden-Image-Builds angehalten werden.
    # Hintergrund: Kasms Agent raeumt im Modus "Aggressive" alle 30 Sekunden
    # jedes ihm unbekannte Image weg — auch frisch gebaute. Komma-getrennt.
    build_pause_containers: str = "kasm_agent"

    # Standardwerte, wenn ein Template nichts anderes sagt.
    default_idle_minutes: int = 60
    session_limit_per_user: int = 5

    cookie_secure: bool = True
    cookie_name: str = "ota_session"

    # Merkmal fuer einen Kennzahlen-Sammler (Prometheus). Leer heisst: nur
    # Administratoren kommen an /metrics. Absichtlich kein Standardwert —
    # ein voreingestelltes Merkmal ist kein Merkmal.
    metrics_token: str = ""

    # --- Identitaet (auth-roadmap.md) -----------------------------------
    #
    # Zwei Betriebsarten. "mitgeliefert" ist der Keycloak aus diesem Stack;
    # dort ist OTA fuehrend und darf den Realm einrichten. "vorhanden" ist ein
    # fremder; dort ist OTA Gast, loescht nichts und fasst nur die eigenen
    # Gruppen an (§5b).
    # Wo die oeffentlichen Zertifikate liegen. Nur zum Ausliefern der eigenen
    # CA unter /ca.crt — Schluessel liegen hier nie.
    certs_dir: str = "/app/certs"

    # --- Aufbewahrung des Protokolls ------------------------------------
    #
    # Zwei Fristen, weil im `audit_log` zwei verschiedene Dinge stehen.
    #
    #   **Verhalten** — Anmeldungen, Sitzungen, App-Starts. Daraus laesst sich
    #   lueckenlos ablesen, wann jemand gearbeitet hat, wie lange und woran.
    #   Genau darauf zielt Art. 5 Abs. 1 lit. e; hier ist die kuerzere Frist
    #   nicht Sparsamkeit, sondern der Zweck.
    #
    #   **Verwaltung** — wer wen angelegt, welche Rechte vergeben, welche
    #   Freigabe eingetragen und wer sich auf einen fremden Bildschirm
    #   geschaltet hat. Das muss eine Pruefung ein Jahr spaeter noch finden.
    #
    # 0 heisst: nie loeschen. Wer das setzt, hat es entschieden — und sollte
    # wissen, dass die Anlage dann Verhaltensdaten ohne Ende sammelt.
    protokoll_verhalten_tage: int = 90
    protokoll_verwaltung_tage: int = 365

    idp_mode: str = "mitgeliefert"
    # Leer heisst: der mitgelieferte unter seinem Dienstnamen.
    keycloak_url: str = ""
    keycloak_realm: str = "ota"
    keycloak_secret: str = ""

    @property
    def keycloak_base(self) -> str:
        """Wohin die API spricht. Ohne Schraegstrich am Ende."""
        if self.keycloak_url.strip():
            return self.keycloak_url.strip().rstrip("/")
        return "http://keycloak:8080/auth"


@lru_cache
def settings() -> Settings:
    s = Settings()
    if not s.jwt_secret:
        import secrets

        s.jwt_secret = secrets.token_urlsafe(48)
    return s
