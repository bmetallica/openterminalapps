"""Protokoll: IP-Adresse nur noch, wo sie einen Zweck hat

Revision ID: b7c3e9f1a425
Revises: a1d9e4b7c362
Create Date: 2026-11-19

Ab jetzt schreibt `audit.record` die IP nur noch bei gescheiterten oder
auffälligen Anmeldungen, bei Vorgängen von Konten mit Verwaltungsrechten und
bei Vorgängen ohne Konto (`audit.mit_ip`). Hier verschwindet sie aus den
älteren Einträgen nach derselben Regel; massgeblich sind die Rechte, die das
Konto heute hat. Kein Rückweg.
"""
from alembic import op

revision = 'b7c3e9f1a425'
down_revision = 'a1d9e4b7c362'
branch_labels = None
depends_on = None

IMMER = ("'login.failed','login.totp_failed','login.recovery_failed','login.recovery_used',"
         "'login.oidc_refused','login.oidc_rejected','login.oidc_state_mismatch'")
VERHALTEN = ("'login.ok','login.oidc_ok','login.failed','login.totp_failed',"
             "'login.recovery_failed','login.recovery_used','session.started',"
             "'session.stopped','session.deleted','app.started','app.stopped'")


def upgrade() -> None:
    op.execute(f"""
        DO $$
        BEGIN
          IF to_regclass('public.audit_log') IS NULL THEN
            RETURN;
          END IF;
          UPDATE audit_log a SET ip = NULL
           WHERE a.ip IS NOT NULL
             AND a.action NOT IN ({IMMER})
             AND (a.action IN ({VERHALTEN})
                  OR (a.actor_user_id IS NOT NULL AND NOT EXISTS (
                        SELECT 1 FROM group_members gm
                          JOIN groups g ON g.id = gm.group_id
                          CROSS JOIN LATERAL jsonb_array_elements_text(
                                coalesce(g.permissions, '[]'::jsonb)) AS r(recht)
                         WHERE gm.user_id = a.actor_user_id
                           AND r.recht <> 'arbeitsplatz.root'))
                  OR (a.actor_user_id IS NULL AND a.actor_name IS NOT NULL));
        END $$;
    """)


def downgrade() -> None:
    pass
