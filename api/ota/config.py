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

    # Standardwerte, wenn ein Template nichts anderes sagt.
    default_idle_minutes: int = 60
    session_limit_per_user: int = 5

    cookie_secure: bool = True
    cookie_name: str = "ota_session"


@lru_cache
def settings() -> Settings:
    s = Settings()
    if not s.jwt_secret:
        import secrets

        s.jwt_secret = secrets.token_urlsafe(48)
    return s
