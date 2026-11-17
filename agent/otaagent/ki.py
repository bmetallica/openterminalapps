"""Der KI-Durchgang (ota-ki) — was der Agent dafür tut (Handbuch Kapitel 28).

Der Durchgang selbst hängt nur am Namensraum der Firewall und an diesem
Ablageverzeichnis. Er hat keine Datenbank und keinen Weg zur API; beides geht
über den Agent:

* **Konfiguration hinein.** Die API schickt Server, Schlüssel, Modelle und ob
  gezählt wird; der Agent legt es als `ki/konfig.json` ab. Der Durchgang liest
  die Datei neu, sobald sie sich ändert.
* **Zahlen heraus.** Der Durchgang schreibt jede Anfrage als Zeile in eine
  Spool-Datei und schließt sie jede Minute ab (`fertig-*.jsonl`). Die API holt
  abgeschlossene Dateien hier ab und lässt sie erst löschen, wenn sie in der
  Datenbank stehen — geht dazwischen etwas schief, kommt die Datei beim
  nächsten Mal noch einmal.
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

log = logging.getLogger("otaagent.ki")

RUNTIME_ROOT = os.environ.get("OTA_RUNTIME_ROOT", "/srv/ota/runtime")
KI_DIR = Path(RUNTIME_ROOT) / "ki"
KONFIG = KI_DIR / "konfig.json"
SPOOL = KI_DIR / "spool"
# Der Durchgang läuft als dieser Nutzer (ki/Dockerfile).
KI_UID = 10001
NAME_OK = re.compile(r"fertig-[0-9A-Za-z_.-]{1,80}\.jsonl")
# Je Abruf höchstens so viele Dateien — eine lange Pause der API soll nicht
# in einer einzigen riesigen Antwort enden.
JE_ABRUF = 20


def _verzeichnisse() -> None:
    for d in (KI_DIR, SPOOL):
        d.mkdir(parents=True, exist_ok=True)
        try:
            os.chown(d, KI_UID, KI_UID)
            os.chmod(d, 0o750)
        except OSError as exc:
            log.warning("Rechte für %s nicht setzbar: %s", d, exc)


def konfig_setzen(daten: dict) -> dict:
    """Atomar schreiben: Der Durchgang soll nie eine halbe Datei lesen."""
    _verzeichnisse()
    tmp = KONFIG.with_suffix(".tmp")
    tmp.write_text(json.dumps(daten), encoding="utf-8")
    os.chmod(tmp, 0o600)
    try:
        os.chown(tmp, KI_UID, KI_UID)
    except OSError:
        pass
    os.replace(tmp, KONFIG)
    return {"ok": True}


def spool_lesen() -> dict:
    _verzeichnisse()
    dateien = sorted(p for p in SPOOL.iterdir() if NAME_OK.fullmatch(p.name))
    raus = []
    for p in dateien[:JE_ABRUF]:
        try:
            zeilen = []
            for z in p.read_text(encoding="utf-8").splitlines():
                try:
                    zeilen.append(json.loads(z))
                except ValueError:
                    continue  # eine abgerissene Zeile — die übrigen zählen
            raus.append({"name": p.name, "zeilen": zeilen})
        except OSError as exc:
            log.warning("Spool %s nicht lesbar: %s", p.name, exc)
    return {"dateien": raus, "mehr": len(dateien) > JE_ABRUF}


def spool_loeschen(name: str) -> dict:
    if not NAME_OK.fullmatch(name):
        return {"ok": False}
    try:
        (SPOOL / name).unlink()
    except FileNotFoundError:
        pass
    return {"ok": True}


def status() -> dict:
    """Was der Durchgang über sich selbst schreibt (alle zehn Sekunden)."""
    try:
        return json.loads((KI_DIR / "status.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def durchgang_nachziehen(client) -> bool:
    """ota-ki neu starten, wenn die Firewall nach ihm gestartet wurde.

    Er teilt sich den Netzwerk-Namensraum der Firewall. Startet die Firewall
    neu, hängt er im alten, leeren Namensraum: Er läuft, aber niemand erreicht
    ihn — die Firewall nimmt dann die Umleitung heraus (sicher), und `ki.ota`
    antwortet nicht mehr (nicht sicher). Docker zieht ihn nicht von selbst nach.
    """
    from docker.errors import APIError, NotFound

    try:
        ki = client.containers.get("ota-ki")
        fw = client.containers.get("ota-firewall")
    except (NotFound, APIError):
        return False
    if ki.status != "running" or fw.status != "running":
        return False
    ki_start = (ki.attrs.get("State") or {}).get("StartedAt", "")
    fw_start = (fw.attrs.get("State") or {}).get("StartedAt", "")
    if not ki_start or not fw_start or ki_start >= fw_start:
        return False
    try:
        ki.restart(timeout=10)
        log.warning("ota-ki neu gestartet — die Firewall war nach ihm gestartet worden")
        return True
    except APIError as exc:
        log.error("ota-ki lässt sich nicht neu starten: %s", exc)
        return False
