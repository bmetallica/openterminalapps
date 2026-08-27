"""Fehlende Spalten nachziehen.

`Base.metadata.create_all()` legt fehlende **Tabellen** an — fehlende
**Spalten** nicht. Das ist eine stille Falle, und sie hat am 2026-08-27
zugeschlagen: Eine neue Spalte im Modell, `create_all` meldete Erfolg, und
danach scheiterte jede Abfrage auf diese Tabelle mit
``column templates.start_script does not exist``. Für den Anwender sah das aus
wie „Die Daten konnten nicht geladen werden".

Was diese Datei tut, ist bewusst wenig: Sie vergleicht das Modell mit der
Datenbank und **fügt fehlende Spalten hinzu**. Sonst nichts.

Was sie ausdrücklich **nicht** tut, und warum das so bleiben soll:

* **Spalten entfernen.** Eine Spalte, die im Modell fehlt, kann ein
  vergessener Rest sein — oder die Datenbank ist neuer als der Code, weil ein
  Rollback lief. Im zweiten Fall wäre Löschen Datenverlust.
* **Typen ändern.** Was mit den vorhandenen Werten passieren soll, weiss nur
  ein Mensch.
* **Umbenennungen erkennen.** Aus Sicht des Vergleichs ist das eine gelöschte
  und eine neue Spalte.

Für alles darüber hinaus gibt es Alembic (`api/migrations/`). Diese Datei
ersetzt es nicht; sie deckt den Fall ab, der beim Weiterbauen ständig
vorkommt, und schweigt über den Rest nicht — was sie nicht kann, meldet sie.
"""

from __future__ import annotations

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.schema import CreateColumn

from .db import Base

log = logging.getLogger("ota.schema")


def sync(engine: Engine) -> list[str]:
    """Ergänzt fehlende Spalten. Gibt zurück, was geändert wurde."""
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    changed: list[str] = []

    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in tables:
                continue  # legt create_all an

            present = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in present:
                    continue

                clause = _add_clause(conn, column)
                if clause is None:
                    log.warning(
                        "Spalte %s.%s fehlt, lässt sich aber nicht gefahrlos "
                        "ergänzen — sie ist ohne Vorgabewert und darf nicht "
                        "leer sein. Bitte von Hand migrieren.",
                        table.name, column.name,
                    )
                    continue

                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN {clause}'))
                changed.append(f"{table.name}.{column.name}")
                log.info("Spalte ergänzt: %s.%s", table.name, column.name)

    return changed


def _add_clause(conn, column) -> str | None:
    """Baut die Spaltendefinition für ALTER TABLE.

    Der Knackpunkt sind Spalten, die nicht leer sein dürfen: Bestehende Zeilen
    brauchen einen Wert. Steht im Modell ein einfacher Vorgabewert, wird er als
    ``DEFAULT`` mitgegeben — dann füllt die Datenbank die Altbestände selbst.
    Steht dort keiner, wird nichts geraten.
    """
    ddl = CreateColumn(column).compile(dialect=conn.dialect).string

    if column.nullable or column.server_default is not None:
        return ddl

    default = getattr(column.default, "arg", None) if column.default is not None else None
    if callable(default) or default is None:
        # Etwa `default=uuid4` oder gar keiner. Für Altbestände unbrauchbar.
        return None

    literal = _literal(default)
    return f"{ddl} DEFAULT {literal}" if literal is not None else None


def _literal(value: object) -> str | None:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        escaped = value.replace("'", "''")
        return f"'{escaped}'"
    if isinstance(value, dict) and not value:
        return "'{}'::jsonb"
    if isinstance(value, list) and not value:
        return "'[]'::jsonb"
    return None
