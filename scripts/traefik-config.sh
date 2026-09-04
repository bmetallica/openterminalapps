#!/usr/bin/env bash
# Erzeugt deploy/traefik/traefik.yml aus der Vorlage.
#
# Warum ueberhaupt: Traefik liest seine statische Konfiguration aus **genau
# einer** Quelle. Sobald die Datei da ist, ignoriert es Umgebungsvariablen und
# Kommandozeilenargumente — gemessen am 2026-08-29. Ein Wert, der je Anlage
# anders aussieht (die Adresse des eigenen Reverse Proxy), muss deshalb vor dem
# Start in die Datei geschrieben werden.
#
# Die erzeugte Datei steht nicht in der Versionsverwaltung. Wer etwas aendern
# will, aendert die Vorlage.

set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VORLAGE="$ROOT/deploy/traefik/traefik.yml.vorlage"
ZIEL="$ROOT/deploy/traefik/traefik.yml"

[ -f "$ROOT/deploy/.env" ] && { set -a; . "$ROOT/deploy/.env"; set +a; }
PROXIES="${OTA_TRUSTED_PROXIES:-}"

if [ ! -f "$VORLAGE" ]; then
  echo "Vorlage fehlt: $VORLAGE" >&2
  exit 1
fi

# Der Block wird ganz weggelassen, wenn niemand einzutragen ist. Ein leeres
# `trustedIPs: []` waere dasselbe, sagt aber weniger: So steht in der Datei
# nichts, was man fuer eine Einstellung halten koennte.
if [ -z "$PROXIES" ]; then
  BLOCK="    # Kein vorgelagerter Reverse Proxy eingetragen (OTA_TRUSTED_PROXIES in deploy/.env)."
else
  BLOCK="    forwardedHeaders:
      trustedIPs:"
  # Komma-getrennt, Leerzeichen egal.
  IFS=',' read -ra LISTE <<< "$PROXIES"
  for eintrag in "${LISTE[@]}"; do
    eintrag="$(echo "$eintrag" | tr -d '[:space:]')"
    [ -z "$eintrag" ] && continue
    BLOCK="$BLOCK
        - \"$eintrag\""
  done
fi

python3 - "$VORLAGE" "$ZIEL" "$BLOCK" <<'PY'
import io, sys
vorlage, ziel, block = sys.argv[1], sys.argv[2], sys.argv[3]
inhalt = io.open(vorlage, encoding="utf8").read()
kopf = ("# ERZEUGT von scripts/traefik-config.sh — Aenderungen hier gehen beim\n"
        "# naechsten `make up` verloren. Bitte traefik.yml.vorlage aendern.\n")
io.open(ziel, "w", encoding="utf8").write(kopf + inhalt.replace("@@FORWARDED_HEADERS@@", block))
PY

if [ -n "$PROXIES" ]; then
  echo "  traefik.yml erzeugt (vertraut: $PROXIES)"
else
  echo "  traefik.yml erzeugt (kein vorgelagerter Proxy)"
fi

# --------------------------------------------------------------------------
# Die Bremse vor der lokalen Anmeldung
# --------------------------------------------------------------------------
#
# Sie steht hier und nicht in `dynamic/middlewares.yml`, weil sie dasselbe
# wissen muss wie der Block oben: **welcher Absender der echte ist.** Steht ein
# Reverse Proxy davor, kommt jede Anfrage von dessen Adresse — eine Bremse je
# Absender wuerde dann alle in denselben Topf werfen und die ganze Firma auf
# fuenf Anmeldungen je Minute setzen. `excludedIPs` sagt Traefik, welche
# Adressen es aus `X-Forwarded-For` herausrechnen soll, um den echten Absender
# zu finden. Beides aus derselben Quelle zu erzeugen ist die einzige Art, die
# nicht irgendwann auseinanderlaeuft.
#
# **Warum ausgerechnet dieser eine Pfad:** `/api/auth/login` ist die Nottuer,
# nicht die Haupttuer. Konten aus Keycloak werden dort abgewiesen und zur
# zentralen Anmeldung geschickt; hier herein kommt praktisch nur `notfall`.
# Fuenf Versuche je Minute kosten deshalb niemanden etwas — und decken die
# Rechenzeit, die jeder Versuch an Argon2 verbrennt.
BREMSE="$ROOT/deploy/traefik/dynamic/anmeldebremse.yml"
{
  echo "# ERZEUGT von scripts/traefik-config.sh — Aenderungen gehen beim"
  echo "# naechsten \`make up\` verloren. Bitte das Skript aendern."
  echo "http:"
  echo "  middlewares:"
  echo "    ota-anmeldebremse:"
  echo "      rateLimit:"
  echo "        average: ${OTA_ANMELDUNG_PRO_MINUTE:-10}"
  echo "        period: 1m"
  echo "        burst: ${OTA_ANMELDUNG_STOSS:-30}"
  if [ -n "$PROXIES" ]; then
    echo "        sourceCriterion:"
    echo "          ipStrategy:"
    echo "            excludedIPs:"
    IFS=',' read -ra LISTE2 <<< "$PROXIES"
    for eintrag in "${LISTE2[@]}"; do
      eintrag="$(echo "$eintrag" | tr -d '[:space:]')"
      [ -z "$eintrag" ] && continue
      echo "              - \"$eintrag\""
    done
  else
    echo "        # Kein vorgelagerter Proxy: Die Adresse der Verbindung ist"
    echo "        # die des Absenders, und Traefik nimmt sie von selbst."
  fi
} > "$BREMSE"
echo "  anmeldebremse.yml erzeugt (${OTA_ANMELDUNG_PRO_MINUTE:-10}/min, Stoss ${OTA_ANMELDUNG_STOSS:-30})"
