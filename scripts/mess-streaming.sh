#!/usr/bin/env bash
# Vergleicht die beiden Streaming-Maschinen unter derselben Last.
#
# **Warum.** Die Umstellung auf Selkies fiel funktional, nicht auf Zahlen. Was
# eine Sitzung an CPU kostet, entscheidet aber, wie viele Menschen gleichzeitig
# arbeiten koennen — x264 laeuft hier in Software, die Maschine hat keine GPU.
#
# Gemessen wird je Maschine zweimal dieselbe Last, einmal ohne und einmal mit
# Betrachter. Die Differenz ist der Preis des Stroms; alles andere kuerzt sich
# heraus. Dazu die Reaktionszeit von Glas zu Glas und die Bandbreite aus dem
# Zaehler der Netzkarte. Die Einzelheiten stehen in `mess-streaming.mjs`.
#
# **Der Pruefbrowser laeuft im Standardnetz**, wie in der Streaming-Pruefung:
# Von dort ist der Session-Container nicht direkt erreichbar, der Medienweg
# muss also durch den TURN. Ein Browser auf dem Server selbst faende einen
# kurzen Weg, den kein Anwender hat, und meldete zu gute Zahlen.
#
# Aufruf:  scripts/mess-streaming.sh [selkies-slug] [kasmvnc-slug]
# Dauer:   rund zehn Minuten. Waehrenddessen nichts anderes auf der Maschine
#          starten — jede fremde Last faelscht das Ergebnis.

set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CN="ota-mess-browser"
CDP_PORT=9225
BROWSER_IMAGE="${OTA_TEST_BROWSER_IMAGE:-127.0.0.1:5000/ota/arbeitsplatz:v13}"
AUSGABE="${OTA_MESS_AUSGABE:-$ROOT/docs/messungen}"

set -a; . "$ROOT/deploy/.env" 2>/dev/null; set +a

vorlage() {  # vorlage <maschine> — die erste passende Arbeitsplatz-Vorlage
  docker exec ota-db psql -U "${POSTGRES_USER:-ota}" -d "${POSTGRES_DB:-ota}" -tAc \
    "select slug from templates where stream_engine='$1' and is_enabled and mode='workspace' order by slug limit 1;" \
    2>/dev/null | tr -d ' '
}

SELKIES="${1:-$(vorlage selkies)}"
KASMVNC="${2:-$(vorlage kasmvnc)}"

echo "Messung der Streaming-Maschinen"
echo "  Selkies: ${SELKIES:-—}    KasmVNC: ${KASMVNC:-—}"
[ -n "$SELKIES" ] || { echo "  Keine Selkies-Vorlage gefunden." >&2; exit 2; }
[ -n "$KASMVNC" ] || { echo "  Keine KasmVNC-Vorlage gefunden." >&2; exit 2; }

# Fremde Last verfaelscht jede Zahl hier. Nicht abbrechen, aber sagen.
LAST=$(cut -d' ' -f1 /proc/loadavg)
echo "  Grundlast der Maschine: $LAST (bei $(nproc) Kernen)"
LAUFEND=$(docker ps --filter 'name=ota-s-' -q | wc -l)
[ "$LAUFEND" = "0" ] || echo "  ⚠ Es laufen bereits $LAUFEND Sitzungen — die Messung wird zu hoch ausfallen."

aufraeumen() { docker rm -f "$CN" >/dev/null 2>&1; }
trap aufraeumen EXIT
docker rm -f "$CN" >/dev/null 2>&1

# `socat` davor, weil Chrome seine Fernsteuerung nur auf dem Rueckkanal
# anbietet — dieselbe Huerde wie in test-streaming.sh.
docker run -d --name "$CN" --network bridge --shm-size=1g \
  -p "127.0.0.1:$CDP_PORT:$CDP_PORT" --entrypoint /bin/bash \
  "$BROWSER_IMAGE" -c "
    socat TCP-LISTEN:$CDP_PORT,fork,reuseaddr TCP:127.0.0.1:9222 &
    exec /opt/google/chrome/chrome --headless=new --no-sandbox \
      --disable-dev-shm-usage --disable-gpu --ignore-certificate-errors \
      --autoplay-policy=no-user-gesture-required --user-data-dir=/tmp/chrome \
      --remote-debugging-port=9222 --window-size=1280,720 about:blank" >/dev/null \
  || { echo "Der Pruefbrowser liess sich nicht starten" >&2; exit 1; }

for _ in $(seq 1 30); do
  curl -s -m2 "http://127.0.0.1:$CDP_PORT/json/version" >/dev/null 2>&1 && break
  sleep 1
done

mkdir -p "$AUSGABE"
STAND="$AUSGABE/streaming-$(date +%Y-%m-%d).json"
echo '[' > "$STAND"

erste=1
for slug in "$SELKIES" "$KASMVNC"; do
  echo
  echo "── $slug ──────────────────────────────"
  ZEILE=$(OTA_CDP="http://127.0.0.1:$CDP_PORT" OTA_PROBE="$CN" \
          node "$ROOT/scripts/mess-streaming.mjs" "$slug" | tail -1)
  [ "$erste" = "1" ] || echo ',' >> "$STAND"
  erste=0
  # Kein `${ZEILE:-…}` mit geschweiften Klammern im Ersatzwert: Die Shell
  # beendet die Ersetzung an der ersten Klammer und haengt den Rest als Text
  # an — im ersten Messlauf stand deshalb eine Klammer zu viel in der Datei.
  [ -n "$ZEILE" ] || ZEILE="{\"slug\":\"$slug\",\"fehler\":\"keine Ausgabe\"}"
  printf '%s' "$ZEILE" >> "$STAND"
  # Zwischen den Laeufen zur Ruhe kommen lassen: Ein gerade beendeter
  # Container raeumt noch auf, und das faellt sonst der naechsten Messung
  # zur Last.
  sleep 20
done
echo ']' >> "$STAND"

echo
python3 - "$STAND" <<'PYENDE'
import json, sys
daten = json.load(open(sys.argv[1]))
def z(x, n=2): return "—" if x is None else f"{x:.{n}f}"

print("─" * 78)
print(f"{'':22}{'Selkies':>18}{'KasmVNC':>18}")
print("─" * 78)
m = {d.get("maschine") or d["slug"]: d for d in daten}
s, k = m.get("selkies", {}), m.get("kasmvnc", {})

def paar(titel, hol, n=2, einheit=""):
    a, b = hol(s), hol(k)
    print(f"{titel:22}{z(a,n)+einheit:>18}{z(b,n)+einheit:>18}")

def strom(d, last):
    o, mi = d.get("ohne", {}).get(last), d.get("mit", {}).get(last)
    return None if not o or not mi else mi["kerne"] - o["kerne"]

grenze = {n: d.get("kerneGrenze") for n, d in (("selkies", s), ("kasmvnc", k))}
gemessen = {n: max([w["kerne"] for p in ("ohne", "mit")
                    for w in (d.get(p) or {}).values()] or [0])
            for n, d in (("selkies", s), ("kasmvnc", k))}
for n in ("selkies", "kasmvnc"):
    if grenze[n] and gemessen[n] > 0.9 * grenze[n]:
        print(f"⚠ {n}: gemessen {gemessen[n]:.2f} Kerne bei einer Grenze von "
              f"{grenze[n]:.0f} — der Wert ist gedeckelt und zu klein.")
paar("Kerngrenze der Vorlage", lambda d: d.get("kerneGrenze"), 0)
print()
print("CPU im Container (Kerne)")
paar("  Leerlauf, ohne", lambda d: d.get("ohne", {}).get("leerlauf", {}).get("kerne"))
paar("  Leerlauf, mit",  lambda d: d.get("mit", {}).get("leerlauf", {}).get("kerne"))
paar("  → Strom kostet", lambda d: strom(d, "leerlauf"))
paar("  Text, ohne",     lambda d: d.get("ohne", {}).get("text", {}).get("kerne"))
paar("  Text, mit",      lambda d: d.get("mit", {}).get("text", {}).get("kerne"))
paar("  → Strom kostet", lambda d: strom(d, "text"))
print()
print("Dekodieren im Browser (Kerne)")
paar("  Leerlauf", lambda d: d.get("mit", {}).get("leerlauf", {}).get("browserKerne"))
paar("  Text",     lambda d: d.get("mit", {}).get("text", {}).get("browserKerne"))
print()
print("Bandbreite (Mbit/s)")
paar("  Leerlauf", lambda d: d.get("mit", {}).get("leerlauf", {}).get("mbitS"))
paar("  Text",     lambda d: d.get("mit", {}).get("text", {}).get("mbitS"))
print()
print("Reaktionszeit von Glas zu Glas (ms)")
paar("  Median",     lambda d: (d.get("reaktion") or {}).get("median"), 0, "")
paar("  schnellste", lambda d: (d.get("reaktion") or {}).get("schnellste"), 0, "")
paar("  langsamste", lambda d: (d.get("reaktion") or {}).get("langsamste"), 0, "")
paar("  verlorene Blitze", lambda d: (d.get("reaktion") or {}).get("verloren"), 0, "")
print()
for name, d in (("Selkies", s), ("KasmVNC", k)):
    if d.get("bild"): print(f"  {name}: {d['bild']}")
    if d.get("fehler"): print(f"  {name}: ABBRUCH — {d['fehler']}")
print("─" * 78)
PYENDE
echo
echo "Rohdaten: $STAND"
