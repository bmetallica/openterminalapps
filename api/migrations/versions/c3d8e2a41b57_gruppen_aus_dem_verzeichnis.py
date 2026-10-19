"""Gruppen aus dem Verzeichnis, und strenger Zugang zu Anwendungen

Revision ID: c3d8e2a41b57
Revises: a1c4e7b90f21
Create Date: 2026-10-19

Drei Dinge, die zusammengehören (Handbuch Kapitel 08, Verzeichnisgruppen):

* `group_members` sagt, **woher** eine Mitgliedschaft kommt: von Hand, aus
  dem Verzeichnis, oder beides. Alles, was es bisher gab, ist von Hand.
* `group_directory_links` koppelt eine OTA-Gruppe an Verzeichnisgruppen.
* `web_apps.fuer_alle`: Eine Anwendung ohne Gruppe ist ab jetzt für
  **niemanden** offen. Bisher hiess das „für alle" — damit nach dem Update
  nichts bricht, bekommt jede Anwendung ohne Gruppe hier ausdrücklich
  „für alle" (Betreiber, 2026-10-19).
"""
from alembic import op

revision = 'c3d8e2a41b57'
down_revision = 'a1c4e7b90f21'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Jeder Schritt verträgt, dass er schon getan ist. Scheitert eine Migration
    # mittendrin, ergänzt `schema_sync` beim Start die Spalten — und ein
    # zweiter Lauf dieser Migration darf dann nicht an „gibt es schon"
    # scheitern, sonst bliebe die Übernahme „für alle" unten aus, und jede
    # bestehende Anwendung wäre für alle gesperrt.
    op.execute("ALTER TABLE group_members ADD COLUMN IF NOT EXISTS von_hand "
               "BOOLEAN NOT NULL DEFAULT true")
    op.execute("ALTER TABLE group_members ADD COLUMN IF NOT EXISTS aus_verzeichnis "
               "BOOLEAN NOT NULL DEFAULT false")
    op.execute("""
        CREATE TABLE IF NOT EXISTS group_directory_links (
            group_id UUID NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
            ldap_gruppe VARCHAR(255) NOT NULL,
            PRIMARY KEY (group_id, ldap_gruppe)
        )""")
    op.execute("ALTER TABLE web_apps ADD COLUMN IF NOT EXISTS fuer_alle "
               "BOOLEAN NOT NULL DEFAULT false")
    op.execute("""
        UPDATE web_apps SET fuer_alle = true
         WHERE NOT EXISTS (SELECT 1 FROM group_web_apps g WHERE g.web_app_id = web_apps.id)
    """)


def downgrade() -> None:
    op.drop_column('web_apps', 'fuer_alle')
    op.drop_table('group_directory_links')
    op.drop_column('group_members', 'aus_verzeichnis')
    op.drop_column('group_members', 'von_hand')
