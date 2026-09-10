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

# Neue Einstellungen aus der Vorlage nachtragen.
#
# Das ist der Teil, der bei einem `git pull` zaehlt: Bringt eine Fassung eine
# neue Variable mit, stand sie bis dahin **nur** in der Vorlage. Der Dienst
# lief trotzdem — Compose hat fuer fast alles einen Vorgabewert —, aber der
# Betreiber erfuhr nie, dass es den Schalter gibt. Genau so ist der ganze
# Netzblock ein halbes Jahr unsichtbar geblieben.
#
# Nachgetragen wird **nur, was fehlt**, mitsamt dem Kommentar davor; er ist
# der Grund, aus dem die Zeile ueberhaupt verstaendlich ist. Vorhandene Werte
# bleiben unangetastet — auch leere: Wer eine Zeile absichtlich leer laesst,
# hat entschieden.
nachtragen() {
  python3 - "$ENV" "$VORLAGE" <<'PY3'
import io, re, sys

ziel, vorlage = sys.argv[1], sys.argv[2]
alt = io.open(ziel, encoding="utf8").read()
da = set(re.findall(r"^([A-Za-z_][A-Za-z_0-9]*)=", alt, flags=re.M))

# Die Vorlage in Bloecke zerlegen: die Kommentarzeilen unmittelbar vor einer
# Zuweisung gehoeren zu ihr. Eine Leerzeile trennt.
bloecke, puffer = [], []
for zeile in io.open(vorlage, encoding="utf8").read().splitlines():
    treffer = re.match(r"^([A-Za-z_][A-Za-z_0-9]*)=", zeile)
    if treffer:
        bloecke.append((treffer.group(1), puffer + [zeile]))
        puffer = []
    elif zeile.strip() == "":
        puffer = []
    else:
        puffer.append(zeile)

neu = [b for name, b in bloecke if name not in da]
if not neu:
    print("  keine neuen Einstellungen")
    sys.exit(0)

teile = ["", "# --- Nachgetragen aus deploy/.env.example -------------------------------",
         "#", "# Vorgaben. Was hier steht, galt vorher auch schon — es stand nur",
         "# nirgends. Anpassen nach Bedarf; die Vorlage erklaert jede Zeile.", ""]
for block in neu:
    teile.extend(block)
    teile.append("")

with io.open(ziel, "a", encoding="utf8") as fh:
    fh.write("\n".join(teile).rstrip() + "\n")

for name, _ in bloecke:
    if name not in da:
        print(f"  {name} — nachgetragen")
PY3
}

echo "Einstellungen in deploy/.env:"
nachtragen
echo

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

# Wohin die Browser greifen, um den Medienstrom zu holen.
#
# **Ohne diesen Wert kommt kein Bild an**, seit Selkies die Vorgabe ist: Der
# Strom laeuft nicht durch Traefik, sondern ueber den TURN-Dienst, und der
# braucht eine Adresse, unter der ihn die **Browser** erreichen — nicht die
# eines Docker-Netzes und nicht 0.0.0.0.
#
# Geraten wird die erste eigene Adresse, die kein Rueckkanal ist. Das ist ein
# Vorschlag und keine Wahrheit: Wer ueber ein VPN zugreift, traegt hier die
# Adresse ein, die **im Tunnel** erreichbar ist. Ergaenzt wird nur, wenn nichts
# dasteht.
if grep -qE "^OTA_TURN_HOST=.+" "$ENV"; then
  echo "  OTA_TURN_HOST — bleibt, wie es ist"
else
  RATEN="$(hostname -I 2>/dev/null | tr ' ' '\n' | grep -vE '^(127\.|172\.1[6-9]\.|172\.2[0-9]\.|172\.3[01]\.|10\.99\.)' | head -1)"
  if [ -n "$RATEN" ]; then
    python3 - "$ENV" "$RATEN" <<'PY3'
import io, re, sys
pfad, wert = sys.argv[1], sys.argv[2]
s = io.open(pfad, encoding="utf8").read()
if re.search(r"^OTA_TURN_HOST=", s, flags=re.M):
    s = re.sub(r"^OTA_TURN_HOST=.*$", f"OTA_TURN_HOST={wert}", s, count=1, flags=re.M)
else:
    s += f"\nOTA_TURN_HOST={wert}\n"
io.open(pfad, "w", encoding="utf8").write(s)
PY3
    echo "  OTA_TURN_HOST — auf $RATEN gesetzt (Vorschlag)"
    echo "                  Das muss die Adresse sein, unter der die BROWSER"
    echo "                  diesen Host erreichen. Ueber ein VPN ist das die"
    echo "                  Adresse im Tunnel — dann hier korrigieren."
  else
    echo "  OTA_TURN_HOST — leer, und keine Adresse zu raten."
    echo "                  Ohne sie kommt kein Bild an: eintragen und 'make up'."
  fi
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
# Der Medienweg. **Das war bis zum 2026-09-10 das einzige Geheimnis, das hier
# fehlte** — und ohne es kommt kein Bild an, seit Selkies die Vorgabe ist. Die
# Vorlage sagte „erzeugen mit openssl rand", also ein Schritt, den man genau
# einmal vergisst; danach steht die Sitzung, und im Browser steht nichts.
fuellen OTA_TURN_SECRET 48 "Medienweg (TURN)"

# Nur für die Prüfungen; ohne Wert wird `make test` es einfordern.
if ! grep -qE "^OTA_TEST_ADMIN_PW=.+" "$ENV"; then
  echo
  echo "Hinweis: OTA_TEST_ADMIN_PW ist leer. Das braucht nur 'make test' —"
  echo "         trag dort das Passwort deines Admin-Kontos ein."
fi

chmod 600 "$ENV"
