"""Freigaben nach Namen — mit einem eigenen Resolver.

**Warum nicht einfach aufloesen und die Adresse eintragen.** Ein Name mit
kurzer Lebensdauer oder mehreren Adressen (jedes CDN, viele Firmendienste
hinter einem Lastverteiler) liefert dem Browser gleich eine andere Adresse als
die, die vor fuenf Minuten in der Freigabe landete. Der Zugriff scheitert dann
scheinbar grundlos, und beim Nachsehen ist alles richtig eingetragen.

**Deshalb der Umweg ueber den eigenen Resolver.** `dnsmasq` traegt beim
*Beantworten* genau die Adresse in eine Menge ein, die es gerade herausgibt —
mit der Lebensdauer der Antwort. Freigabe und Verbindung stammen damit aus
derselben Auskunft und koennen nicht auseinanderlaufen.

**Und deshalb sind fremde Resolver gesperrt** (`regeln.py`, INPUT-Kette und die
Sperre der privaten Bereiche): Wer `8.8.8.8` fragen darf, bekommt eine Adresse,
die in keiner Menge steht — oder umgeht die Liste ueber einen Namen, den unser
Resolver nie gesehen hat.

**Wenn `ipset` fehlt**, faellt der Dienst auf regelmaessiges Aufloesen zurueck.
Das ist schlechter, aber es ist nicht stumm: Der Zustand sagt es.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import signal
import socket
import subprocess
from pathlib import Path

log = logging.getLogger("otafw.resolver")

CONF = Path("/etc/dnsmasq.d/ota.conf")
DNS_PORT = int(os.environ.get("OTA_FW_DNS_PORT", "53"))

_prozess: subprocess.Popen | None = None
_letzte_pruefsumme = ""
_ipset_geht: bool | None = None


def mengenname(subnetz: str) -> str:
    """Ein Mengenname je Sitzungsnetz. `ipset` erlaubt 31 Zeichen."""
    return "ota-" + subnetz.split("/")[0].replace(".", "-")


def ipset_verfuegbar() -> bool:
    """Einmal ausprobieren, nicht raten.

    Das Kernelmodul laedt sich beim ersten Anlegen selbst nach; scheitert das
    (weil der Wirt es nicht hat), faellt der Dienst auf Aufloesen zurueck.
    """
    global _ipset_geht
    if _ipset_geht is not None:
        return _ipset_geht
    try:
        subprocess.run(["ipset", "create", "ota-probe", "hash:ip", "timeout", "60"],
                       capture_output=True, timeout=10, check=True)
        subprocess.run(["ipset", "destroy", "ota-probe"], capture_output=True, timeout=10)
        _ipset_geht = True
    except (subprocess.SubprocessError, OSError) as exc:
        log.warning("ipset steht nicht zur Verfuegung (%s) — Namen werden aufgeloest", exc)
        _ipset_geht = False
    return _ipset_geht


def menge_sicherstellen(name: str) -> None:
    subprocess.run(["ipset", "create", "-exist", name, "hash:ip", "timeout", "3600"],
                   capture_output=True, timeout=10)


def menge_entfernen(name: str) -> None:
    subprocess.run(["ipset", "destroy", name], capture_output=True, timeout=10)


def _upstream() -> list[str]:
    """Wen der eigene Resolver fragt.

    Aus der Umgebung, sonst aus der `resolv.conf` des Wirts. Eigene Adressen
    (`127.x`) fallen heraus — sonst fragt dnsmasq sich selbst.
    """
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
        f"port={DNS_PORT}",
        # Auf allen Schnittstellen lauschen und neuen Bruecken folgen: Es
        # kommen staendig welche dazu. Erreichbar ist der Resolver trotzdem
        # nur aus den Sitzungsnetzen — dafuer sorgt die INPUT-Kette.
        "bind-dynamic",
        "no-resolv",
        "cache-size=1000",
        "log-facility=-",
        # Keine Weiterleitung von Namen ohne Punkt und von privaten
        # Rueckwaertsanfragen — das spart Verkehr und verraet weniger.
        "domain-needed",
        "bogus-priv",
    ]
    zeilen += [f"server={s}" for s in _upstream()]

    if ipset_verfuegbar():
        for sitzung in zustand.get("sitzungen", []):
            namen = [n for n in sitzung.get("namen", []) if n]
            if not namen:
                continue
            menge = mengenname(sitzung["subnetz"])
            menge_sicherstellen(menge)
            zeilen.append("ipset=/" + "/".join(namen) + f"/{menge}")
    return "\n".join(zeilen) + "\n"


def anwenden(zustand: dict) -> dict:
    """Konfiguration schreiben und den Resolver nur bei Aenderung neu starten."""
    global _prozess, _letzte_pruefsumme

    text = _konfiguration(zustand)
    pruefsumme = hashlib.sha256(text.encode()).hexdigest()
    CONF.parent.mkdir(parents=True, exist_ok=True)
    CONF.write_text(text, encoding="utf-8")

    laeuft = _prozess is not None and _prozess.poll() is None
    if laeuft and pruefsumme == _letzte_pruefsumme:
        return {"resolver": "unveraendert", "ipset": ipset_verfuegbar()}

    if laeuft:
        # `ipset=`-Zeilen liest dnsmasq nur beim Start. Ein SIGHUP genuegt
        # dafuer nicht — deshalb wirklich neu starten.
        _prozess.send_signal(signal.SIGTERM)
        try:
            _prozess.wait(timeout=10)
        except subprocess.TimeoutExpired:
            _prozess.kill()

    _prozess = subprocess.Popen(
        ["dnsmasq", "--keep-in-foreground", "--conf-file=" + str(CONF)],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    _letzte_pruefsumme = pruefsumme
    log.info("Resolver neu gestartet (%d Sitzungen mit Namen)",
             sum(1 for s in zustand.get("sitzungen", []) if s.get("namen")))
    return {"resolver": "neu gestartet", "ipset": ipset_verfuegbar()}


NAME = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$")


def aufloesen(namen: list[str]) -> list[str]:
    """Rueckfallebene ohne `ipset`: Namen zu Adressen, so gut es geht."""
    adressen: list[str] = []
    for name in namen:
        if not NAME.match(name or ""):
            continue
        try:
            for eintrag in socket.getaddrinfo(name, None, socket.AF_INET):
                adressen.append(eintrag[4][0])
        except OSError:
            log.warning("Name nicht aufloesbar: %s", name)
    return sorted(set(adressen))


def laeuft() -> bool:
    return _prozess is not None and _prozess.poll() is None
