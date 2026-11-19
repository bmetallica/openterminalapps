"""Protokoll: keine Einträge mehr über geöffnete Anwendungen

Revision ID: a1d9e4b7c362
Revises: f4c7a1e3b852
Create Date: 2026-11-19

Bis hierher stand jedes Öffnen und Schliessen einer Anwendung über OTA als
`app.started` / `app.stopped` im `audit_log`, mit Person, Zeit und IP. Für die
Funktion braucht OTA das nicht (`app_streams` trägt den laufenden Zustand);
es ergab nur ein Profil, wer wann wie lange womit gearbeitet hat. Die API
schreibt diese Einträge nicht mehr, und die vorhandenen verschwinden hier.

Kein Rückweg: Gelöschte Protokolleinträge lassen sich nicht wiederherstellen.
"""
from alembic import op

revision = 'a1d9e4b7c362'
down_revision = 'f4c7a1e3b852'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
          IF to_regclass('public.audit_log') IS NOT NULL THEN
            DELETE FROM audit_log WHERE action IN ('app.started', 'app.stopped');
          END IF;
        END $$;
    """)


def downgrade() -> None:
    pass
