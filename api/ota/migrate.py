"""Migrationen beim Start ausführen.

Bis hierher entstand das Schema ausschliesslich über `create_all()` plus
`schema_sync`. Das reicht für „eine Spalte kam dazu", aber nicht für alles
Weitere — und Alembic lag ungenutzt daneben.

Der Ablauf beim Start, in dieser Reihenfolge:

1. **Bestehende Anlage übernehmen.** Stehen schon Tabellen da, aber es gibt
   keine `alembic_version`, dann ist diese Datenbank vor Alembic entstanden.
   Sie wird auf den Ausgangsstand gestempelt statt migriert — ein
   ``CREATE TABLE`` auf bestehende Tabellen würde nur scheitern.
2. **`alembic upgrade head`.** Auf einer leeren Datenbank baut das alles auf;
   auf einer gestempelten laufen nur die neueren Schritte.
3. Danach greifen weiterhin `create_all` und `schema_sync` — siehe
   `schema_sync.py`. Das ist kein Widerspruch, sondern ein Netz: Wer beim
   Weiterbauen eine Spalte hinzufügt und die Migration vergisst, legt damit
   nicht die Anlage lahm. Was dabei ergänzt wurde, steht im Protokoll und
   gehört in eine Migration nachgetragen.

Scheitert die Migration, **wird der Start nicht abgebrochen**. Ein Dienst, der
wegen eines Migrationsproblems gar nicht erst hochkommt, lässt sich auch nicht
mehr reparieren — die Meldung steht im Protokoll, und Schritt 3 fängt den
häufigsten Fall ohnehin ab.
"""

from __future__ import annotations

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from .config import settings

log = logging.getLogger("ota.migrate")

# alembic.ini liegt neben dem Paket, im Arbeitsverzeichnis des Dienstes.
ROOT = Path(__file__).resolve().parent.parent


def _config() -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", settings().database_url)
    return cfg


def run(engine: Engine) -> None:
    cfg = _config()
    if not (ROOT / "migrations" / "versions").is_dir():
        log.warning("Keine Migrationen vorhanden — übersprungen")
        return

    try:
        with engine.connect() as conn:
            context = MigrationContext.configure(conn)
            stamped = context.get_current_revision()
            existing = set(inspect(conn).get_table_names()) - {"alembic_version"}

        if stamped is None and existing:
            # Vor Alembic entstanden. Auf den Ausgangsstand stempeln, damit
            # die naechsten Schritte greifen, ohne Bestehendes anzufassen.
            log.info("Bestehendes Schema wird als Ausgangsstand übernommen "
                     "(%d Tabellen)", len(existing))
            command.stamp(cfg, "base")
            command.stamp(cfg, "head")
            return

        command.upgrade(cfg, "head")
    except Exception as exc:  # noqa: BLE001 — der Start darf daran nicht scheitern
        log.warning("Migration nicht ausgeführt: %s", exc)
