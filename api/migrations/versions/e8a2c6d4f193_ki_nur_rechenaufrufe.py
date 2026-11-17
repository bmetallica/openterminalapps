"""KI-Statistik: nur Rechenaufrufe zählen, bisherige Prüfabrufe herausnehmen

Revision ID: e8a2c6d4f193
Revises: d5e1f3a9c724
Create Date: 2026-11-17

Der Durchgang fängt jeden Abruf an der Adresse eines KI-Servers ab, und die
API hat bisher jeden davon als Anfrage gezählt — auch `/v1/models`,
`/health` und eine Anmeldeseite, die eine Gesundheitsprüfung im
Sechs-Sekunden-Takt abrief. Sie standen als „Modell unbekannt“ in der
Statistik und machten dort den Großteil aus. Ab jetzt zählt nur noch, was
`ki_statistik.rechenaufruf` als Aufruf eines Modells erkennt.

Hier verschwinden die bisherigen: aus den Einzelanfragen gelöscht, und
dieselben Mengen von den Stundensummen abgezogen (dort steht kein Pfad).
Stundensummen älter als die Einzelanfragen lassen sich so nicht mehr
bereinigen; die Statistik ist aber jünger als deren Frist.
Die Liste der Pfade muss zu `RECHNEN` in ki_statistik.py passen.
"""
from alembic import op

revision = 'e8a2c6d4f193'
down_revision = 'd5e1f3a9c724'
branch_labels = None
depends_on = None

_RECHNEN = ("/completions", "/embeddings", "/responses", "/messages", "/rerank",
            "/api/chat", "/api/generate", "/api/embed", "/api/embeddings",
            "/completion", "/infill", "/embedding")


def upgrade() -> None:
    bedingung = " OR ".join(f"rtrim(lower(pfad), '/') LIKE '%{p}'" for p in _RECHNEN)
    op.execute(f"""
        DO $$
        DECLARE r record;
        BEGIN
          IF to_regclass('public.ki_anfragen') IS NULL OR to_regclass('public.ki_stunden') IS NULL THEN
            RETURN;
          END IF;
          CREATE TEMP TABLE ki_weg ON COMMIT DROP AS
            WITH weg AS (
              DELETE FROM ki_anfragen WHERE weg <> 'tls' AND NOT ({bedingung})
              RETURNING ts, user_id, template_id, server, modell, werkzeug, status, dauer_ms, ein, aus)
            SELECT date_trunc('hour', ts) AS stunde,
                   coalesce(user_id, '00000000-0000-0000-0000-000000000000'::uuid) AS user_id,
                   coalesce(template_id, '00000000-0000-0000-0000-000000000000'::uuid) AS template_id,
                   server, modell, werkzeug,
                   count(*) AS anfragen,
                   count(*) FILTER (WHERE status = 0 OR status >= 400) AS fehler,
                   sum(dauer_ms) AS dauer_ms,
                   sum(coalesce(ein, 0)) AS ein, sum(coalesce(aus, 0)) AS aus
              FROM weg GROUP BY 1, 2, 3, 4, 5, 6;
          -- In den Stundensummen steht die Anwendung erst seit d5e1f3a9c724;
          -- davor ist sie leer. Erst die passende Zeile, sonst die leere.
          FOR r IN SELECT * FROM ki_weg LOOP
            UPDATE ki_stunden s
               SET anfragen = greatest(0, s.anfragen - r.anfragen),
                   fehler = greatest(0, s.fehler - r.fehler),
                   dauer_ms = greatest(0, s.dauer_ms - r.dauer_ms),
                   ein = greatest(0, s.ein - r.ein), aus = greatest(0, s.aus - r.aus)
             WHERE s.stunde = r.stunde AND s.user_id = r.user_id AND s.template_id = r.template_id
               AND s.server = r.server AND s.modell = r.modell
               AND s.werkzeug = (CASE WHEN EXISTS (
                     SELECT 1 FROM ki_stunden x
                      WHERE x.stunde = r.stunde AND x.user_id = r.user_id
                        AND x.template_id = r.template_id AND x.server = r.server
                        AND x.modell = r.modell AND x.werkzeug = r.werkzeug)
                   THEN r.werkzeug ELSE '' END);
          END LOOP;
          DELETE FROM ki_stunden WHERE anfragen <= 0 AND verbindungen <= 0;
        END $$;
    """)


def downgrade() -> None:
    # Gelöschte Prüfabrufe kommen nicht zurück — und sollen es auch nicht.
    pass
