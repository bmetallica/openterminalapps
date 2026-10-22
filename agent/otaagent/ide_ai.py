"""IDE-AI im Arbeitsplatz (Handbuch Kapitel 28): Continue in VS Code,
VSCodium und JetBrains-IDEs, verbunden mit dem eigenen KI-Server.

Die API sagt, **was** gelten soll: die Fassungen der Pakete aus der eigenen
Paketquelle und die fertige Konfiguration. Der Agent setzt es um, bei jedem
Start und jedem Fortsetzen:

1. **Konfiguration** nach `~/.continue/config.yaml` — sofort, vor dem Editor.
   Eine Datei ohne OTAs erste Zeile gehört dem Menschen und bleibt, wie sie
   ist. Dazu die Telemetrie von Continue aus.
2. **Pakete** — im Hintergrund, damit der Start nicht wartet. Nur für
   Editoren, die es im Container gibt, und nur, wenn die Fassung nicht schon
   installiert ist. Der Agent holt die Datei selbst aus der Paketquelle und
   spielt sie mit dpkg ein: So kommt IDE-AI auch in Images, in die OTA keine
   Paketquelle einträgt (Ubuntu, Kasm-Images), und der Arbeitsplatz braucht
   dafür keinen Weg ins Netz.

Leere Angaben heißen: IDE-AI ist aus oder nicht für diesen Menschen. Dann
verschwinden die Verknüpfungen in den Editoren und OTAs Konfiguration; die
Pakete selbst bleiben liegen (sie tun ohne Verknüpfung nichts).
"""
from __future__ import annotations

import base64
import io
import logging
import os
import re
import tarfile
import threading
import urllib.error
import urllib.request
from typing import Any, Callable


log = logging.getLogger("otaagent.ide_ai")

ARTEN = ("vscode", "jetbrains")
REPO = os.environ.get("OTA_REPO_STEUERUNG", "http://ota-repo:8200")
RUNTIME_ROOT = os.environ.get("OTA_RUNTIME_ROOT", "/srv/ota/runtime")
FASSUNG_OK = re.compile(r"[0-9A-Za-z.+~:-]{1,80}")

_laufend: set[str] = set()
_sperre = threading.Lock()

# Was es im Container gibt: Editor da? Welche Fassung installiert?
_ERKUNDEN = r"""
command -v dpkg >/dev/null 2>&1 || { echo "kein-dpkg"; exit 0; }
vs=0; jb=0
for d in /usr/share/codium /usr/share/code /opt/visual-studio-code /opt/vscodium; do
  [ -d "$d/resources/app/extensions" ] && vs=1
done
for f in /opt/*/product-info.json /opt/*/*/product-info.json /usr/share/*/product-info.json; do
  [ -f "$f" ] && [ -d "$(dirname "$f")/plugins" ] && jb=1
done
echo "vscode $vs $(dpkg-query -W -f='${Version}' ota-ide-ai-vscode 2>/dev/null)"
echo "jetbrains $jb $(dpkg-query -W -f='${Version}' ota-ide-ai-jetbrains 2>/dev/null)"
"""

# $1 Zuhause, $2 Konfiguration (base64) oder leer = wegräumen.
_KONFIG = r"""
# M: die erste Zeile jeder Datei, die OTA schreibt (api/ota/ide_ai.py). Fehlt
# sie, gehört die Datei dem Menschen — und OTA fasst sie nicht mehr an.
H="$1"; K="$2"; M='# Verwaltet von OTA (IDE-AI).'
[ -d "$H" ] || exit 0
B=$(stat -c %u:%g "$H")
D="$H/.continue"; F="$D/config.yaml"
JB=/usr/share/ota-ide-ai/jetbrains/continue-intellij-extension

# JetBrains-IDEs laden zusätzliche Plugins nur aus dem Plugin-Verzeichnis im
# Zuhause, je IDE und Fassung (~/.local/share/JetBrains/PyCharm2026.2) —
# nicht aus ihrem eigenen plugins/ (packaging/ota-ide-ai/verknuepfen). Dort
# liegt nur eine Verknüpfung; das Plugin selbst bleibt im Paket.
jetbrains() {
  for f in /opt/*/product-info.json /opt/*/*/product-info.json /usr/share/*/product-info.json; do
    [ -f "$f" ] || continue
    n=$(sed -n 's/.*"dataDirectoryName": *"\([A-Za-z0-9._-]*\)".*/\1/p' "$f" | head -1)
    [ -n "$n" ] || continue
    P="$H/.local/share/JetBrains/$n"
    if [ "$1" = an ] && [ -d "$JB" ]; then
      for d in "$H/.local" "$H/.local/share" "$H/.local/share/JetBrains" "$P"; do
        [ -d "$d" ] || { mkdir "$d" && chown "$B" "$d"; }
      done
      [ "$(readlink "$P/ota-continue")" = "$JB" ] || {
        ln -sfn "$JB" "$P/ota-continue" && chown -h "$B" "$P/ota-continue" && echo "verknüpft: $P"; }
    elif [ -L "$P/ota-continue" ]; then
      rm -f "$P/ota-continue" && echo "weg: $P"
    fi
  done
}

if [ -z "$K" ]; then
  [ -f "$F" ] && head -1 "$F" | grep -qF "$M" && rm -f "$F" && echo "konfig-weg"
  for v in /usr/lib/ota-ide-ai/verknuepfen-*; do [ -x "$v" ] && "$v" weg; done
  jetbrains weg
  exit 0
fi
if [ -f "$F" ] && ! head -1 "$F" | grep -qF "$M"; then
  echo "konfig-eigen"
else
  mkdir -p "$D" && chown "$B" "$D"
  echo "$K" | base64 -d > "$F.ota" && chown "$B" "$F.ota" && chmod 600 "$F.ota" && mv "$F.ota" "$F"
  echo "konfig-gesetzt"
fi
# Telemetrie aus. Continue liest das aus seinem globalen Zustand; eine Zeile
# in config.yaml gibt es dafür nicht. Vorhandenes bleibt, nur der Schalter
# wird gesetzt.
G="$D/index/globalContext.json"
mkdir -p "$D/index" && chown "$B" "$D/index"
if command -v python3 >/dev/null 2>&1; then
  python3 - "$G" <<'PY' && chown "$B" "$G"
import json, sys
p = sys.argv[1]
try:
    d = json.load(open(p))
    if not isinstance(d, dict):
        d = {}
except (OSError, ValueError):
    d = {}
s = d.get("sharedConfig") if isinstance(d.get("sharedConfig"), dict) else {}
if s.get("allowAnonymousTelemetry") is not False:
    s["allowAnonymousTelemetry"] = False
    d["sharedConfig"] = s
    json.dump(d, open(p, "w"))
PY
elif [ ! -f "$G" ]; then
  echo '{"sharedConfig":{"allowAnonymousTelemetry":false}}' > "$G" && chown "$B" "$G"
fi
for v in /usr/lib/ota-ide-ai/verknuepfen-*; do [ -x "$v" ] && "$v"; done
jetbrains an
exit 0
"""


def _datei(name: str, fassung: str) -> str:
    """Die .deb-Datei aus der Paketquelle, zwischengespeichert je Fassung."""
    ordner = os.path.join(RUNTIME_ROOT, "ide-ai")
    os.makedirs(ordner, exist_ok=True)
    pfad = os.path.join(ordner, f"{name}_{fassung}.deb")
    if os.path.exists(pfad):
        return pfad
    frage = urllib.request.Request(f"{REPO}/pakete/{name}/{fassung}/datei",
                                   headers={"X-Agent-Token": os.environ.get("OTA_AGENT_TOKEN", "")})
    # Ohne Proxy: Die Paketquelle ist ein Dienst nebenan.
    oeffner = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with oeffner.open(frage, timeout=120) as r, open(pfad + ".neu", "wb") as fh:
        while stueck := r.read(1 << 20):
            fh.write(stueck)
    os.replace(pfad + ".neu", pfad)
    # Alte Fassungen weg — gebraucht wird nur die neueste.
    for alt in os.listdir(ordner):
        if alt.startswith(f"{name}_") and alt != os.path.basename(pfad):
            os.remove(os.path.join(ordner, alt))
    return pfad


def _hinein(container, pfad: str) -> str:
    """Die Datei nach /tmp im Container."""
    puffer = io.BytesIO()
    ziel = os.path.basename(pfad)
    with tarfile.open(fileobj=puffer, mode="w") as tar:
        tar.add(pfad, arcname=ziel)
    container.put_archive("/tmp", puffer.getvalue())
    return f"/tmp/{ziel}"


def _pakete(container, fassungen: dict[str, str], run_as_root: Callable) -> bool:
    """True, wenn ein Paket neu installiert oder angehoben wurde."""
    code, out = run_as_root(container, ["sh", "-c", _ERKUNDEN])
    if "kein-dpkg" in out:
        log.info("IDE-AI in %s: kein dpkg — nichts installiert", container.name)
        return False
    neu = False
    for zeile in out.splitlines():
        teile = zeile.split()
        if len(teile) < 2 or teile[0] not in ARTEN:
            continue
        art, editor, ist = teile[0], teile[1] == "1", (teile[2] if len(teile) > 2 else "")
        soll = str(fassungen.get(art) or "")
        if not editor or not soll or not FASSUNG_OK.fullmatch(soll) or ist == soll:
            continue
        name = f"ota-ide-ai-{art}"
        if ist:
            c, _ = run_as_root(container, ["dpkg", "--compare-versions", ist, "gt", soll])
            if c == 0:
                continue
        try:
            datei = _hinein(container, _datei(name, soll))
        except (urllib.error.URLError, OSError) as exc:
            log.warning("IDE-AI in %s: %s %s nicht geholt: %s", container.name, name, soll, exc)
            continue
        c, aus = run_as_root(container, ["sh", "-c",
                                         f"DEBIAN_FRONTEND=noninteractive dpkg -i '{datei}' 2>&1; "
                                         f"r=$?; rm -f '{datei}'; exit $r"])
        if c == 0:
            neu = True
            log.info("IDE-AI in %s: %s %s -> %s", container.name, name, ist or "neu", soll)
        else:
            log.warning("IDE-AI in %s: %s nicht installiert: %s", container.name, name,
                        aus.strip()[-300:])
    return neu


def im_container(container, angaben: dict[str, Any], heim: str, run_as_root: Callable) -> None:
    """Konfiguration sofort, Pakete im Hintergrund. Scheitert etwas, startet
    der Arbeitsplatz trotzdem — dann eben ohne IDE-AI."""
    konfig = str(angaben.get("config") or "")
    k64 = base64.b64encode(konfig.encode()).decode() if konfig else ""
    try:
        code, out = run_as_root(container, ["sh", "-c", _KONFIG, "sh", heim, k64])
        if code != 0:
            log.warning("IDE-AI in %s: %s", container.name, out.strip()[-300:])
        elif "konfig-eigen" in out:
            log.info("IDE-AI in %s: eigene config.yaml — bleibt unverändert", container.name)
    except Exception as exc:  # noqa: BLE001 — darf keinen Start kippen
        log.warning("IDE-AI in %s nicht eingerichtet: %s", container.name, exc)
        return
    if not konfig:
        return

    def hintergrund() -> None:
        try:
            # War ein Paket neu, noch einmal einrichten: Erst jetzt gibt es,
            # was zu verknüpfen ist.
            if _pakete(container, angaben.get("fassungen") or {}, run_as_root):
                run_as_root(container, ["sh", "-c", _KONFIG, "sh", heim, k64])
        except Exception as exc:  # noqa: BLE001 — Container kann inzwischen weg sein
            log.warning("IDE-AI in %s: Pakete nicht eingerichtet: %s", container.name, exc)
        finally:
            with _sperre:
                _laufend.discard(container.id)

    with _sperre:
        if container.id in _laufend:
            return
        _laufend.add(container.id)
    threading.Thread(target=hintergrund, name=f"ide-ai-{container.name}", daemon=True).start()
