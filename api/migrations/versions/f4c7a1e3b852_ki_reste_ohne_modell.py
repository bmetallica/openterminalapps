"""KI-Statistik: Reste der Prüfabrufe in den Stundensummen

Revision ID: f4c7a1e3b852
Revises: e8a2c6d4f193
Create Date: 2026-11-17

`e8a2c6d4f193` hat die Prüfabrufe je Stunde von der Zeile mit derselben
Anwendung abgezogen. In der Stunde, in der `d5e1f3a9c724` (Anwendung in den
Stundensummen) eingespielt wurde, waren sie aber auf zwei Zeilen verteilt:
vor dem Update ohne Anwendung, danach mit. Abgezogen wurde alles von der
zweiten, der Rest blieb in der ersten stehen (auf einer Anlage 762 Abrufe
„Modell unbekannt“).

Seit `e8a2c6d4f193` hat jede gezählte Anfrage ein Modell (notfalls das des
Servers, siehe `ki_statistik._ohne_modell`). Anfragen ohne Modell in den
Stundensummen sind deshalb nur noch solche Reste: Sie werden auf null
gesetzt, und wo dann nichts übrig ist, verschwindet die Zeile. Verbindungen
(verschlüsselt, ohne Modell) bleiben.
"""
from alembic import op

revision = 'f4c7a1e3b852'
down_revision = 'e8a2c6d4f193'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
          IF to_regclass('public.ki_stunden') IS NULL THEN
            RETURN;
          END IF;
          UPDATE ki_stunden SET anfragen = 0, fehler = 0, ein = 0, aus = 0,
                                dauer_ms = CASE WHEN verbindungen > 0 THEN dauer_ms ELSE 0 END
           WHERE modell = '' AND anfragen > 0;
          DELETE FROM ki_stunden WHERE anfragen <= 0 AND verbindungen <= 0;
          IF to_regclass('public.ki_anfragen') IS NOT NULL THEN
            DELETE FROM ki_anfragen WHERE modell = '' AND weg <> 'tls';
          END IF;
        END $$;
    """)


def downgrade() -> None:
    pass
