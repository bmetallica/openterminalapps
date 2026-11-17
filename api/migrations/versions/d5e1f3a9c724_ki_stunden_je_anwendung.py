"""KI-Stundensummen auch je Anwendung

Revision ID: d5e1f3a9c724
Revises: c3d8e2a41b57
Create Date: 2026-11-17

`ki_stunden` zählt bisher je Stunde, Mensch, Arbeitsplatz, Server und
Modell. Für den Filter „je Anwendung“ und den Ring „Anwendung“ auf der
Seite KI-Nutzung (Handbuch Kapitel 28) kommt die Anwendung dazu — als Teil
des Schlüssels, sonst liefen die Summen zweier Anwendungen in einer Zeile
zusammen. Was vor diesem Update gezählt wurde, steht mit leerer Anwendung da
(„nicht erfasst“).

Die Tabelle entsteht über `create_all`, nicht über eine Migration: Auf einer
neuen Datenbank gibt es sie hier noch nicht, dann ist nichts zu tun, und
`create_all` legt sie gleich mit dem neuen Schlüssel an. Jeder Schritt
verträgt, dass er schon getan ist.
"""
from alembic import op

revision = 'd5e1f3a9c724'
down_revision = 'c3d8e2a41b57'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
          IF to_regclass('public.ki_stunden') IS NULL THEN
            RETURN;
          END IF;
          ALTER TABLE ki_stunden ADD COLUMN IF NOT EXISTS werkzeug VARCHAR(16) NOT NULL DEFAULT '';
          IF NOT EXISTS (
              SELECT 1 FROM pg_index i
                JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
               WHERE i.indrelid = 'public.ki_stunden'::regclass AND i.indisprimary
                 AND a.attname = 'werkzeug') THEN
            ALTER TABLE ki_stunden DROP CONSTRAINT IF EXISTS ki_stunden_pkey;
            ALTER TABLE ki_stunden ADD CONSTRAINT ki_stunden_pkey
              PRIMARY KEY (stunde, user_id, template_id, server, modell, werkzeug);
          END IF;
        END $$;
    """)


def downgrade() -> None:
    # Zurück geht nur, wenn die Summen je Anwendung wieder zusammenfallen.
    op.execute("""
        DO $$
        BEGIN
          IF to_regclass('public.ki_stunden') IS NULL THEN
            RETURN;
          END IF;
          CREATE TEMP TABLE ki_stunden_alt AS
            SELECT stunde, user_id, template_id, server, modell,
                   max(user_name) AS user_name, max(arbeitsplatz) AS arbeitsplatz,
                   sum(anfragen) AS anfragen, sum(fehler) AS fehler,
                   sum(verbindungen) AS verbindungen, sum(ein) AS ein, sum(aus) AS aus,
                   sum(dauer_ms) AS dauer_ms, sum(bytes) AS bytes
              FROM ki_stunden GROUP BY 1, 2, 3, 4, 5;
          DELETE FROM ki_stunden;
          ALTER TABLE ki_stunden DROP CONSTRAINT ki_stunden_pkey;
          ALTER TABLE ki_stunden DROP COLUMN werkzeug;
          INSERT INTO ki_stunden (stunde, user_id, template_id, server, modell, user_name,
                                  arbeitsplatz, anfragen, fehler, verbindungen, ein, aus,
                                  dauer_ms, bytes)
            SELECT * FROM ki_stunden_alt;
          ALTER TABLE ki_stunden ADD CONSTRAINT ki_stunden_pkey
            PRIMARY KEY (stunde, user_id, template_id, server, modell);
        END $$;
    """)
