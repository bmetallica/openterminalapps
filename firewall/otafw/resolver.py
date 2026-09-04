"""Der Resolver der Arbeitsplaetze — und die Freigaben nach Namen.

**Warum ein eigener.** Ein Name mit kurzer Lebensdauer oder mehreren Adressen
(jedes CDN, viele Firmendienste hinter einem Lastverteiler) liefert dem Browser
gleich eine andere Adresse als die, die vor fuenf Minuten in einer Freigabe
landete. Der Zugriff scheitert dann scheinbar grundlos, und beim Nachsehen ist
alles richtig eingetragen.

`dnsmasq` traegt beim **Beantworten** genau die Adresse in eine nftables-Menge
ein, die es gerade herausgibt — mit der Lebensdauer der Antwort. Freigabe und
Verbindung stammen damit aus derselben Auskunft und koennen nicht auseinander
laufen.

**Fremde Resolver braucht niemand zu sperren.** Aus einem `internal`-Netz gibt
es keinen Weg zu `8.8.8.8`; der einzige erreichbare Resolver ist dieser hier.
In Fassung 1 brauchte es dafuer drei Regelpaare — hier ist es eine Eigenschaft
des Aufbaus.
"""

from __future__ import annotations

import hashlib
import logging
import os
import signal
import subprocess
from pathlib import Path

log = logging.getLogger("otafw.resolver")

CONF = Path("/etc/dnsmasq.d/ota.conf")
PORT = int(os.environ.get("OTA_FW_DNS_PORT", "53"))

_prozess: subprocess.Popen | None = None
_pruefsumme = ""


def _upstream() -> list[str]:
    """Wen dieser Resolver fragt. Aus der Umgebung, sonst aus der resolv.conf."""
    gesetzt = os.environ.get("OTA_FW_DNS_UPSTREAM", "").strip()
    if gesetzt:
        return [t.strip() for t in gesetzt.split(",") if t.strip()]
    server = []
    try:
        for zeile in Path("/etc/resolv.conf").read_text().splitlines():
            teile = zeile.split()
            if len(teile) >= 2 and teile[0] == "nameserver" and not teile[1].startswith("127."):
                server.append(teile[1])
    except OSError:
        pass
    return server or ["9.9.9.9"]


def _konfiguration(zustand: dict) -> str:
    zeilen = [
        "# Erzeugt von ota-firewall. Handaenderungen werden ueberschrieben.",
        f"port={PORT}",
        # Neuen Bruecken folgen: Es kommt mit jeder Sitzung eine dazu.
        "bind-dynamic",
        # **Nicht auf dem Uplink lauschen.** Dort steht das Firmennetz, und ein
        # Resolver, der dorthin antwortet, ist ein offener Resolver. In
        # Fassung 1 ist genau das passiert.
        f"except-interface={zustand.get('uplink', 'eth0')}",
        "no-resolv",
        "cache-size=1000",
        "log-facility=-",
        "domain-needed",
        "bogus-priv",
    ]
    zeilen += [f"server={s}" for s in _upstream()]

    for s in zustand.get("sitzungen", []):
        namen = [n for n in s.get("namen", []) if n]
        if not namen:
            continue
        menge = "n_" + s["subnetz"].split("/")[0].replace(".", "_")
        # `--nftset` statt `--ipset`: Der Router arbeitet mit nftables, und
        # zwei Regelwerke, die sich gegenseitig nicht sehen, waeren schlimmer
        # als eins.
        zeilen.append("nftset=/" + "/".join(namen) + f"/inet#ota#{menge}")
    return "\n".join(zeilen) + "\n"


def anwenden(zustand: dict) -> dict:
    """Konfiguration schreiben, Resolver nur bei Aenderung neu starten."""
    global _prozess, _pruefsumme

    text = _konfiguration(zustand)
    neu = hashlib.sha256(text.encode()).hexdigest()
    CONF.parent.mkdir(parents=True, exist_ok=True)
    CONF.write_text(text, encoding="utf-8")

    laeuft = _prozess is not None and _prozess.poll() is None
    if laeuft and neu == _pruefsumme:
        return {"resolver": "unveraendert"}

    if laeuft:
        # `nftset=`-Zeilen liest dnsmasq nur beim Start; ein SIGHUP genuegt
        # dafuer nicht.
        _prozess.send_signal(signal.SIGTERM)
        try:
            _prozess.wait(timeout=10)
        except subprocess.TimeoutExpired:
            _prozess.kill()

    _prozess = subprocess.Popen(
        ["dnsmasq", "--keep-in-foreground", f"--conf-file={CONF}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    _pruefsumme = neu
    log.info("Resolver neu gestartet (%d Sitzungen mit Namen)",
             sum(1 for s in zustand.get("sitzungen", []) if s.get("namen")))
    return {"resolver": "neu gestartet"}


def laeuft() -> bool:
    return _prozess is not None and _prozess.poll() is None
