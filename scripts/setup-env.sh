#!/usr/bin/env bash
# Legt deploy/.env an und füllt die Geheimnisse.
#
# Früher druckte `make setup` die erzeugten Werte nur aus und überliess das
# Eintragen dem Menschen. Wer der Anleitung wörtlich folgte, scheiterte beim
# nächsten Befehl an einem leeren OTA_JWT_SECRET — und die Fehlermeldung kam
# aus Docker Compose, nicht aus OTA. Ein Schnellstart, dessen zweiter Schritt
# scheitert, ist keiner.
#
# **Vorhandene Werte werden nie überschrieben.** Das Skript lässt sich also
# gefahrlos erneut aufrufen, etwa wenn nach einem Update eine neue Variable
# dazugekommen ist.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV="$ROOT/deploy/.env"
VORLAGE="$ROOT/deploy/.env.example"

if [ ! -f "$ENV" ]; then
  cp "$VORLAGE" "$ENV"
  chmod 600 "$ENV"
  echo "deploy/.env aus der Vorlage angelegt."
fi

zufall() {  # zufall <länge>
  openssl rand -base64 64 | tr -d '\n=+/' | head -c "$1"
}

fuellen() {  # fuellen <name> <länge> <beschreibung>
  local name="$1" laenge="$2" was="$3" wert
  # Nur, wenn die Zeile fehlt oder leer ist.
  if grep -qE "^${name}=.+" "$ENV"; then
    echo "  $name — bleibt, wie es ist"
    return
  fi
  wert="$(zufall "$laenge")"
  if grep -qE "^${name}=" "$ENV"; then
    # In-place ersetzen, ohne sed-Sonderzeichen: der Wert ist alphanumerisch.
    python3 - "$ENV" "$name" "$wert" <<'PY'
import io, re, sys
pfad, name, wert = sys.argv[1], sys.argv[2], sys.argv[3]
s = io.open(pfad, encoding="utf8").read()
s = re.sub(rf"^{re.escape(name)}=.*$", f"{name}={wert}", s, count=1, flags=re.M)
io.open(pfad, "w", encoding="utf8").write(s)
PY
  else
    printf '%s=%s\n' "$name" "$wert" >> "$ENV"
  fi
  echo "  $name — erzeugt ($was)"
}

echo "Geheimnisse in deploy/.env:"
fuellen POSTGRES_PASSWORD 32 "Datenbank"
fuellen OTA_JWT_SECRET    64 "Anmeldemerkmale"
fuellen OTA_AGENT_TOKEN   48 "API → Agent"

# Nur für die Prüfungen; ohne Wert wird `make test` es einfordern.
if ! grep -qE "^OTA_TEST_ADMIN_PW=.+" "$ENV"; then
  echo
  echo "Hinweis: OTA_TEST_ADMIN_PW ist leer. Das braucht nur 'make test' —"
  echo "         trag dort das Passwort deines Admin-Kontos ein."
fi

chmod 600 "$ENV"
