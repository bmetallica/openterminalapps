#!/usr/bin/env bash
# Legt ein **lokales** Konto für die Prüfreihen an (oder setzt es zurück).
#
#   scripts/lokales-testkonto.sh NAME PASSWORT EMAIL [GRUPPEN-SLUGS,KOMMA,GETRENNT]
#
# Seit dem 2026-10-08 entsteht jedes Konto, das die Verwaltung anlegt, in
# Keycloak; lokal ist nur noch das Notfallkonto. Die Prüfreihen messen aber an
# einem lokalen Konto, was nur dort gilt — Sperre je (Konto, Absender),
# Zeitverhalten, OTAs eigener zweiter Faktor —, und das ohne das Notfallkonto
# anzufassen. Dieses Skript schreibt ein solches Konto direkt in die
# Datenbank, so wie es Bestandskonten aus der Zeit vor Keycloak gibt. Es ist
# kein Weg der Verwaltung und gehört nicht in den Betrieb.
#
# Ausgabe: die Kennung des Kontos.
set -euo pipefail
NAME="${1:?Name}"; PW="${2:?Passwort}"; MAIL="${3:?E-Mail}"; GRUPPEN="${4:-users}"

docker exec -i -e N="$NAME" -e P="$PW" -e M="$MAIL" -e G="$GRUPPEN" ota-api python - <<'PY'
import os
from sqlalchemy import select
from ota.db import SessionLocal
from ota.models import Group, User
from ota.security import hash_password

db = SessionLocal()
u = db.scalar(select(User).where(User.username == os.environ["N"]))
if u is None:
    u = User(username=os.environ["N"], auth_provider="local", is_active=True)
    db.add(u)
if u.auth_provider != "local":
    raise SystemExit(f"{u.username} ist kein lokales Konto ({u.auth_provider}) — nicht angefasst")
u.email = os.environ["M"]
u.password_hash = hash_password(os.environ["P"])
u.must_change_password = False
u.is_active = True
u.locked_until = None
u.failed_logins = 0
slugs = [s for s in os.environ["G"].split(",") if s]
u.groups = list(db.scalars(select(Group).where(Group.slug.in_(slugs))).all())
db.commit()
print(u.id)
PY
