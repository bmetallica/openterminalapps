"""Root-Arbeitsplätze, die ein gescheiterter Start auf „failed" setzte, zurückholen

Bis zum 2026-11-21 setzte ein gescheiterter Start jede Sitzung auf `failed`,
auch einen angehaltenen Root-Arbeitsplatz ohne Container, der dabei neu
aufgebaut werden sollte. Er verschwand damit aus Betrieb → Arbeitsplätze, und
jeder weitere Versuch legte einen neuen Platz mit neuer Kennung an. Seine
Kennung ist aber der Schlüssel zu seinen Docker-Daten (Volume
`ota-platz-docker-<Kennung>`).

Zurück auf „angehalten" kommt je Nutzer und Root-Vorlage **eine** Zeile, und
nur, wenn es dort keinen laufenden oder angehaltenen Platz gibt: die jüngste
fehlgeschlagene, die nachweislich lief (`session.started`, `platz.angehalten`
oder `platz.fortgesetzt` mit ihrer Kennung), und von mehreren die, die zuletzt
lief. `platz.neu_aufgesetzt` allein zählt nicht: Auf der Produktion hatte auch
ein Fehlversuch, der nie lief, so einen Eintrag. Platzhalter aus
Fehlversuchen bleiben, wie sie sind.

Revision ID: c5e8a2d7f316
Revises: b7c3e9f1a425
Create Date: 2026-11-21
"""
from alembic import op

revision = 'c5e8a2d7f316'
down_revision = 'b7c3e9f1a425'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        WITH lief AS (
            SELECT a.object_id, max(a.ts) AS zuletzt
            FROM audit_log a
            WHERE a.action IN ('session.started', 'platz.angehalten', 'platz.fortgesetzt')
            GROUP BY a.object_id
        ), kandidat AS (
            SELECT DISTINCT ON (s.user_id, s.template_id) s.id
            FROM sessions s
            JOIN templates t ON t.id = s.template_id AND t.klasse = 'root'
            JOIN lief l ON l.object_id = s.id::text
            WHERE s.status = 'failed'
              AND NOT EXISTS (
                  SELECT 1 FROM sessions x
                  WHERE x.user_id = s.user_id AND x.template_id = s.template_id
                    AND x.status IN ('starting', 'running', 'paused', 'angehalten'))
            ORDER BY s.user_id, s.template_id, l.zuletzt DESC
        )
        UPDATE sessions SET status = 'angehalten', container_id = NULL,
               end_reason = 'start_gescheitert', ended_at = now()
        WHERE id IN (SELECT id FROM kandidat)
    """)


def downgrade() -> None:
    # Nichts: „failed" war der Fehler.
    pass
