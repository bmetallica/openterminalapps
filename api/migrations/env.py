import logging
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from ota.config import settings
from ota.db import Base
import ota.models  # noqa: F401  — registriert alle Tabellen

config = context.config
config.set_main_option("sqlalchemy.url", settings().database_url)

# Nur, wenn noch niemand das Protokoll eingerichtet hat (Aufruf von Hand).
# Beim Start der API schaltete die Datei sonst jeden vorhandenen Logger ab und
# setzte die Wurzel auf WARN — danach stand von `ota.*` keine einzige
# Info-Zeile mehr im Protokoll (bemerkt am 2026-10-27).
if config.config_file_name is not None and not logging.getLogger().handlers:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata, compare_type=True
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
