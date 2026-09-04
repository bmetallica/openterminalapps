"""Die eigene LDAP-Anbindung entfällt

Revision ID: a1c4e7b90f21
Revises: 379f500cf7f8
Create Date: 2026-09-04

Bis hierher sprach OTA selbst LDAP: eigene Anbindung, eigener nächtlicher
Abgleich, eigener Anmeldeweg. Mit der Übernahme der Konten nach Keycloak ist
das entfallen — ein Verzeichnis bindet man dort an, und Keycloak macht die
Anmeldung (`auth-roadmap.md`, Entscheidung 4).

**Die Tabelle geht mit, und das ist der Punkt.** In `identity_configs` stand
das Kennwort des Verzeichnis-Dienstkontos im Klartext (`security.md`, M2).
Eine Tabelle, die niemand mehr liest, bleibt sonst als Kopie eines
AD-Kennworts in jedem Datenbankabzug stehen — und in einem Jahr weiss
niemand mehr, warum sie da ist.

Zurücknehmen lässt sich das: `downgrade()` legt die Tabelle wieder an. Was
darin stand, kommt damit nicht zurück — es soll auch nicht.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'a1c4e7b90f21'
down_revision = '379f500cf7f8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table('identity_configs')


def downgrade() -> None:
    op.create_table(
        'identity_configs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('is_enabled', sa.Boolean(), nullable=False),
        sa.Column('server_uri', sa.String(length=512), nullable=False),
        sa.Column('tls_mode', sa.String(length=16), nullable=False),
        sa.Column('tls_verify', sa.Boolean(), nullable=False),
        sa.Column('ca_cert', sa.Text(), nullable=False),
        sa.Column('bind_dn', sa.String(length=512), nullable=False),
        sa.Column('bind_password', sa.Text(), nullable=False),
        sa.Column('base_dn', sa.String(length=512), nullable=False),
        sa.Column('login_attribute', sa.String(length=64), nullable=False),
        sa.Column('user_filter', sa.String(length=512), nullable=False),
        sa.Column('mail_attribute', sa.String(length=64), nullable=False),
        sa.Column('name_attribute', sa.String(length=64), nullable=False),
        sa.Column('group_base_dn', sa.String(length=512), nullable=False),
        sa.Column('group_filter', sa.String(length=512), nullable=False),
        sa.Column('member_attribute', sa.String(length=64), nullable=False),
        sa.Column('group_name_attribute', sa.String(length=64), nullable=False),
        sa.Column('group_map', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('jit_create', sa.Boolean(), nullable=False),
        sa.Column('sync_enabled', sa.Boolean(), nullable=False),
        sa.Column('last_sync_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
