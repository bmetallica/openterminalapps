"""Ein Netz je Sitzung — anlegen, vergeben, aufraeumen.

**Warum je Sitzung ein eigenes Netz und nicht ein gemeinsames.** Verkehr
zwischen zwei Containern auf **derselben** Bruecke wird gebrueckt, nicht
geroutet — und laeuft damit an iptables vollstaendig vorbei, solange
`br_netfilter` nicht geladen ist (auf dieser Maschine ist es das nicht,
gemessen). Eine Firewall ueber einem gemeinsamen Sitzungsnetz saehe diesen
Verkehr nie. Erst verschiedene Netze zwingen den Kernel zum Routen, und erst
dann greift `FORWARD` und damit `DOCKER-USER`.

**Warum ein eigener Adressbereich.** Dockers Standardvorrat ist auf einer
gewachsenen Maschine schnell leer (gemessen: 172.17–172.31 belegt, vom zweiten
Vorrat 14 Netze frei — fuer alle Stapel zusammen). Ein Netz je Sitzung
braeuchte ihn in einer Woche auf, und der Fehler lautet dann `could not find an
available, non-overlapping IPv4 address pool`. Mit einem eigenen Bereich
vergibt OTA selbst und kollidiert mit niemandem.

**Und nicht `192.168.x`.** Das ist in vielen Firmennetzen die LAN-Adresse.

**Das Netz traegt sein Profil als Beschriftung.** Damit kann der Agent nach
einem Neustart den gewuenschten Gesamtzustand allein aus Docker rekonstruieren,
ohne die API zu fragen. Ein Dienst, der seinen Zustand nur im Speicher haelt,
verliert ihn genau dann, wenn es darauf ankommt.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import os
import threading

import docker
from docker.errors import APIError, NotFound

log = logging.getLogger("ota.agent.netz")

POOL = os.environ.get("OTA_SESSION_POOL", "10.99.0.0/16")
# Wie gross ein Sitzungsnetz ist. /24 gibt 253 nutzbare Adressen je Sitzung —
# mehr als genug — und 256 Sitzungen aus einem /16.
NETZGROESSE = int(os.environ.get("OTA_SESSION_PREFIX", "24"))
LABEL_SITZUNG = "ota.session"
LABEL_PROFIL = "ota.netzprofil"
TRAEFIK = os.environ.get("OTA_TRAEFIK_CONTAINER", "ota-traefik")

_vergabe = threading.Lock()


def netzname(session_id: str) -> str:
    return f"ota-n-{session_id[:12]}"


def _belegte_subnetze(client) -> set[str]:
    belegt: set[str] = set()
    for netz in client.networks.list():
        for eintrag in (netz.attrs.get("IPAM") or {}).get("Config") or []:
            if eintrag.get("Subnet"):
                belegt.add(eintrag["Subnet"])
    return belegt


def _freies_subnetz(client) -> str:
    """Das erste freie Stueck aus dem eigenen Bereich.

    Verglichen wird auf Ueberschneidung und nicht auf Gleichheit: Ein fremdes
    Netz koennte ein groesseres Stueck aus demselben Bereich halten, und zwei
    sich ueberlappende Netze ergeben Fehler, die niemand versteht.
    """
    pool = ipaddress.ip_network(POOL)
    belegt = [ipaddress.ip_network(s, strict=False) for s in _belegte_subnetze(client)]
    for kandidat in pool.subnets(new_prefix=NETZGROESSE):
        if not any(kandidat.overlaps(b) for b in belegt):
            return str(kandidat)
    raise RuntimeError(
        f"Kein freies Subnetz mehr in {POOL}. "
        f"Entweder liegen Waisen herum oder der Bereich ist zu klein.")


def netz_anlegen(client, session_id: str, profil: dict) -> tuple[str, str]:
    """Netz anlegen und (Name, Subnetz) zurueckgeben. Idempotent."""
    name = netzname(session_id)
    with _vergabe:
        try:
            vorhanden = client.networks.get(name)
            konfig = (vorhanden.attrs.get("IPAM") or {}).get("Config") or [{}]
            return name, konfig[0].get("Subnet", "")
        except NotFound:
            pass

        subnetz = _freies_subnetz(client)
        netz = ipaddress.ip_network(subnetz)
        client.networks.create(
            name,
            driver="bridge",
            ipam=docker.types.IPAMConfig(pool_configs=[
                docker.types.IPAMPool(subnet=subnetz, gateway=str(netz[1]))
            ]),
            labels={
                LABEL_SITZUNG: session_id,
                LABEL_PROFIL: json.dumps(profil, ensure_ascii=False),
            },
            options={
                # Die Bruecke erbt sonst die Vorgabe des Wirts. Wer ueber einen
                # Tunnel mit kleiner Paketgroesse arbeitet, sucht den Fehler
                # sonst spaeter an der falschen Stelle — dieses Projekt hat mit
                # der MTU schon einmal zwei Tage verloren.
                "com.docker.network.driver.mtu": os.environ.get("OTA_SESSION_MTU", "1500"),
            },
        )
        log.info("Netz %s angelegt (%s)", name, subnetz)
        return name, subnetz


def netz_entfernen(client, session_id: str) -> None:
    name = netzname(session_id)
    try:
        netz = client.networks.get(name)
    except NotFound:
        return
    # Erst alles abhaengen, was noch daran haengt — sonst bleibt das Netz
    # stehen und sein Subnetz ist dauerhaft vergeben.
    for container in netz.attrs.get("Containers", {}) or {}:
        try:
            netz.disconnect(container, force=True)
        except APIError:
            pass
    try:
        netz.remove()
        log.info("Netz %s entfernt", name)
    except APIError as exc:
        log.warning("Netz %s liess sich nicht entfernen: %s", name, exc)


def traefik_verbinden(client, netzname_: str) -> None:
    """Traefik in das Sitzungsnetz holen — sonst kommt kein Bild an.

    Frueher hingen alle Sitzungen gemeinsam in `ota_public`, und genau das war
    Befund H2: Was Traefik erreicht, erreichen sie auch untereinander.
    """
    try:
        netz = client.networks.get(netzname_)
        netz.connect(TRAEFIK)
    except NotFound:
        log.warning("Traefik-Container %s nicht gefunden", TRAEFIK)
    except APIError as exc:
        if "already exists" not in str(exc):
            log.warning("Traefik nicht mit %s verbunden: %s", netzname_, exc)


def traefik_trennen(client, netzname_: str) -> None:
    try:
        client.networks.get(netzname_).disconnect(TRAEFIK, force=True)
    except (NotFound, APIError):
        pass


def traefik_adressen(client) -> list[str]:
    """**Alle** Adressen, unter denen Traefik in Sitzungsnetze spricht.

    Mehrzahl, und das ist der Punkt: Traefik haengt in jedem Sitzungsnetz und
    hat dort je eine eigene Adresse. Wer nur die erste freigibt, bekommt das
    Bild in genau einer Sitzung — und in allen anderen „Waiting for stream",
    ohne dass irgendwo ein Fehler auftaucht.
    """
    try:
        traefik = client.containers.get(TRAEFIK)
    except (NotFound, APIError):
        return []
    netze = traefik.attrs["NetworkSettings"]["Networks"]
    return sorted({angaben["IPAddress"]
                   for name, angaben in netze.items()
                   if name.startswith("ota-n-") and angaben.get("IPAddress")})


def sitzungsnetze(client) -> list[dict]:
    """Alle Sitzungsnetze samt Profil — die Wahrheit fuer den Abgleich."""
    raus = []
    for netz in client.networks.list(filters={"label": LABEL_SITZUNG}):
        konfig = (netz.attrs.get("IPAM") or {}).get("Config") or [{}]
        subnetz = konfig[0].get("Subnet", "")
        if not subnetz:
            continue
        roh = (netz.attrs.get("Labels") or {}).get(LABEL_PROFIL, "{}")
        try:
            profil = json.loads(roh)
        except ValueError:
            profil = {}
        raus.append({
            "name": netz.name,
            "subnetz": subnetz,
            "session_id": (netz.attrs.get("Labels") or {}).get(LABEL_SITZUNG, ""),
            "stufe": profil.get("stufe", "internet"),
            "freigaben": profil.get("freigaben", []),
            "namen": profil.get("namen", []),
            "container": list((netz.attrs.get("Containers") or {}).keys()),
        })
    return raus


def waisen_aufraeumen(client) -> int:
    """Netze ohne Sitzungscontainer verschwinden.

    Ohne das bleibt ihr Subnetz vergeben, und nach genug Waisen ist der Bereich
    voll — mit einer Fehlermeldung, die nach einem Docker-Problem aussieht und
    keines ist.
    """
    weg = 0
    for netz in sitzungsnetze(client):
        eigene = [c for c in netz["container"]]
        # Traefik zaehlt nicht: Er haengt in jedem Sitzungsnetz.
        richtige = []
        for cid in eigene:
            try:
                if client.containers.get(cid).name != TRAEFIK:
                    richtige.append(cid)
            except (NotFound, APIError):
                continue
        if richtige:
            continue
        traefik_trennen(client, netz["name"])
        try:
            client.networks.get(netz["name"]).remove()
            weg += 1
            log.info("Waisennetz %s entfernt", netz["name"])
        except (NotFound, APIError) as exc:
            log.warning("Waisennetz %s bleibt: %s", netz["name"], exc)
    return weg
