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

# `OTA_NO_PROXY` beim ersten Mal selbst zusammenstellen.
#
# Warum nicht einfach fest in der Vorlage: Die Liste muss den **eigenen** Host
# nennen, und wie der heisst, weiss die Vorlage nicht. Fehlt er, laeuft ein
# Aufruf an die eigene Adresse durch den Firmenproxy — und der kennt sie nicht.
#
# Ergaenzt wird nur, wenn nichts dasteht. Wer die Zeile von Hand gepflegt hat,
# behaelt sie.
no_proxy_vorschlagen() {
  local hn fqdn liste
  hn="$(hostname 2>/dev/null || true)"
  fqdn="$(hostname -f 2>/dev/null || true)"
  # Die eigenen Dienste, der Rueckkanal, die privaten Netze — und der Host
  # unter jedem Namen, unter dem er sich selbst kennt. Die privaten Bereiche
  # decken jede Docker-Bruecke ab, ohne sie einzeln aufzuzaehlen: Die legt
  # Docker erst beim Start an, lange nach diesem Skript.
  liste="localhost,127.0.0.1,::1"
  # **Beide Namen.** Im Compose-Netz erreichen sich die Dienste unter ihrem
  # Dienstnamen (`agent`), nicht unter dem Containernamen (`ota-agent`) — die
  # API ruft `http://agent:8100`. Steht nur der Containername in der Liste,
  # laeuft dieser Aufruf durch den Firmenproxy, und die API meldet „Der
  # Container-Dienst ist nicht erreichbar". Gemessen am 2026-09-03.
  liste="$liste,api,agent,db,keycloak,web,traefik,turn,registry"
  liste="$liste,ota-api,ota-agent,ota-db,ota-keycloak,ota-web,ota-traefik,ota-turn,ota-registry"
  [ -n "$hn" ]   && liste="$liste,$hn"
  [ -n "$fqdn" ] && [ "$fqdn" != "$hn" ] && liste="$liste,$fqdn"
  liste="$liste,.local,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
  printf '%s' "$liste"
}

if grep -qE "^OTA_NO_PROXY=.+" "$ENV"; then
  echo "  OTA_NO_PROXY — bleibt, wie es ist"
else
  WERT="$(no_proxy_vorschlagen)"
  python3 - "$ENV" "$WERT" <<'PY2'
import io, re, sys
pfad, wert = sys.argv[1], sys.argv[2]
s = io.open(pfad, encoding="utf8").read()
if re.search(r"^OTA_NO_PROXY=", s, flags=re.M):
    s = re.sub(r"^OTA_NO_PROXY=.*$", f"OTA_NO_PROXY={wert}", s, count=1, flags=re.M)
else:
    s += f"\nOTA_NO_PROXY={wert}\n"
io.open(pfad, "w", encoding="utf8").write(s)
PY2
  echo "  OTA_NO_PROXY — zusammengestellt (eigene Dienste, dieser Host, private Netze)"
fi
echo

echo "Geheimnisse in deploy/.env:"
fuellen POSTGRES_PASSWORD 32 "Datenbank"
fuellen OTA_JWT_SECRET    64 "Anmeldemerkmale"
fuellen OTA_AGENT_TOKEN   48 "API → Agent"
# Keycloak. Das erste Konto dient nur dazu, den Realm einzurichten; danach
# arbeitet OTA ueber sein eigenes Dienstkonto (`ota-manager`).
fuellen KEYCLOAK_ADMIN_PW 32 "Keycloak-Ersteinrichtung"
fuellen OTA_KEYCLOAK_SECRET 48 "OTA → Keycloak"

# Nur für die Prüfungen; ohne Wert wird `make test` es einfordern.
if ! grep -qE "^OTA_TEST_ADMIN_PW=.+" "$ENV"; then
  echo
  echo "Hinweis: OTA_TEST_ADMIN_PW ist leer. Das braucht nur 'make test' —"
  echo "         trag dort das Passwort deines Admin-Kontos ein."
fi

chmod 600 "$ENV"
