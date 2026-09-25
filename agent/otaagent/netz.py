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
FIREWALL = os.environ.get("OTA_FIREWALL_CONTAINER", "ota-firewall")

# Feste Adressen je Sitzungsnetz. Nicht dem Zufall ueberlassen, weil daran
# Regeln, Routen und die Netzuebersicht haengen:
#
#   .1   die Bruecke auf dem Wirt — ungenutzt, es gibt keinen Weg dorthin
#   .2   der Router (ota-fw)
#   .10  der Arbeitsplatz — so angefordert; tatsaechlich vergibt Docker
#        weiter von unten (gemessen am 2026-09-25: .3). Deshalb liest
#        `_platz_adresse` die echte Adresse, statt sie anzunehmen.
#   letzte  Traefik (.254 bei /24)
#
# **Auch Traefik fest.** Bis zum 2026-09-25 bekam Traefik, was Docker gerade
# frei hatte — im Normalfall die naechste nach dem Arbeitsplatz. Nach einem
# Neustart des Wirts aber startet Traefik vor dem Router, und dann ist .2 frei:
# Traefik nahm sie, und der Router liess sich mit seiner festen Adresse nicht
# mehr anbinden. Docker startete ihn daraufhin **gar nicht** („failed to set
# up container networking: Address already in use"), und jeder Arbeitsplatz
# war ohne Netz. Gefunden, weil der Router auf der Entwicklungsmaschine seit
# dem letzten Neustart stand.
#
# **Die letzte Adresse, nicht .3.** Der erste Versuch gab Traefik .3 — genau
# die, die Docker dem Arbeitsplatz gibt. Am oberen Ende vergibt Docker erst,
# wenn das Netz voll ist, und ein Netz je Sitzung wird nie voll.
ROUTER_HOST = 2
PLATZ_HOST = 10


def traefik_adresse(subnetz: str) -> str:
    return str(ipaddress.ip_network(subnetz)[-2])

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


def netz_anlegen(client, session_id: str, profil: dict,
                 wunsch: str = "") -> tuple[str, str]:
    """Netz anlegen und (Name, Subnetz) zurueckgeben. Idempotent.

    `wunsch` ist das Subnetz, das diesem Menschen an diesem Arbeitsplatz
    dauerhaft gehoert (`NetLease` in der API). Ist es belegt — etwa weil eine
    alte Sitzung noch aufraeumt —, wird ein freies genommen: **lieber eine
    wechselnde Adresse als kein Arbeitsplatz.**
    """
    name = netzname(session_id)
    with _vergabe:
        try:
            vorhanden = client.networks.get(name)
            konfig = (vorhanden.attrs.get("IPAM") or {}).get("Config") or [{}]
            return name, konfig[0].get("Subnet", "")
        except NotFound:
            pass

        subnetz = ""
        if wunsch:
            belegt = [ipaddress.ip_network(x, strict=False)
                      for x in _belegte_subnetze(client)]
            gewuenscht = ipaddress.ip_network(wunsch, strict=False)
            if not any(gewuenscht.overlaps(b) for b in belegt):
                subnetz = wunsch
            else:
                log.warning("Subnetz %s ist belegt — es wird ein freies genommen", wunsch)
        subnetz = subnetz or _freies_subnetz(client)
        netz = ipaddress.ip_network(subnetz)
        client.networks.create(
            name,
            driver="bridge",
            # **`internal`** — und das ist der Kern des ganzen Aufbaus: Docker
            # richtet fuer solche Netze kein NAT ein und legt nicht einmal eine
            # Standardroute an (gemessen). Ein Arbeitsplatz darin kommt
            # nirgendwohin, bis der Router ihm den Weg zeigt. Die Absicherung
            # ist damit eine Eigenschaft des Aufbaus und nicht eine Sammlung
            # von Regeln, die richtig greifen muessen.
            internal=True,
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
                # **Die Bruecke bekommt keine Adresse.** Ohne das haengt der
                # Wirt mit `10.99.k.1` im selben Netz, und der Arbeitsplatz
                # erreicht ihn dort direkt — nicht ueber den Router, sondern
                # ueber das Kabel. Gemessen: SSH des Wirts war so offen,
                # obwohl das Regelwerk vollstaendig stand. Der Verkehr wird
                # nicht weitergeleitet, also sieht ihn keine Forward-Regel.
                #
                # Ohne Adresse ist dort nichts, was man ansprechen koennte.
                "com.docker.network.bridge.inhibit_ipv4": "true",
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


def _verbinden(client, netzname_: str, container: str, adresse: str = "") -> None:
    try:
        netz = client.networks.get(netzname_)
        if adresse:
            netz.connect(container, ipv4_address=adresse)
        else:
            netz.connect(container)
    except NotFound:
        log.warning("Container %s nicht gefunden", container)
    except APIError as exc:
        if "already exists" not in str(exc):
            log.warning("%s nicht mit %s verbunden: %s", container, netzname_, exc)
            # **Den halben Eintrag wieder entfernen.** Docker behaelt ein
            # gescheitertes `connect` in der Konfiguration des Containers
            # („invalid IP"). Wird das Netz spaeter geloescht, startet der
            # Container nicht mehr: „network … not found". Gemessen am
            # 2026-09-25 an Traefik — OTAs Haupteingang war danach zu.
            try:
                client.networks.get(netzname_).disconnect(container, force=True)
            except (NotFound, APIError):
                pass


def router_verbinden(client, netzname_: str, subnetz: str) -> str:
    """Den Router in das Sitzungsnetz holen — auf eine **feste** Adresse.

    Fest, damit die Standardroute des Arbeitsplatzes vorher feststeht und
    nicht davon abhaengt, welche Adresse Docker gerade uebrig hatte.
    """
    adresse = str(ipaddress.ip_network(subnetz)[ROUTER_HOST])
    _verbinden(client, netzname_, FIREWALL, adresse)
    return adresse


def _subnetz(client, netzname_: str) -> str:
    try:
        konfig = (client.networks.get(netzname_).attrs.get("IPAM") or {}).get("Config") or [{}]
        return konfig[0].get("Subnet", "")
    except (NotFound, APIError):
        return ""


def traefik_verbinden(client, netzname_: str, subnetz: str = "") -> None:
    """Traefik in das Sitzungsnetz holen — sonst kommt kein Bild an.

    Frueher hingen alle Sitzungen gemeinsam in `ota_public`, und genau das war
    Befund H2: Was Traefik erreicht, erreichen sie auch untereinander.

    Gemessen (Etappe 0): Bei `internal`-Netzen bleibt der DNAT von Traefiks
    veroeffentlichtem Port dabei stehen. In Fassung 1 hatte genau dieser
    Beitritt OTAs Haupteingang zugemacht.

    Auf eine feste Adresse, die letzte im Netz — warum, steht bei
    `ROUTER_HOST`.
    """
    subnetz = subnetz or _subnetz(client, netzname_)
    adresse = traefik_adresse(subnetz) if subnetz else ""
    _verbinden(client, netzname_, TRAEFIK, adresse)


def traefik_trennen(client, netzname_: str) -> None:
    for container in (TRAEFIK, FIREWALL):
        try:
            client.networks.get(netzname_).disconnect(container, force=True)
        except (NotFound, APIError):
            pass


def platz_adresse(subnetz: str) -> str:
    """Die gewuenschte Adresse des Arbeitsplatzes — beim Anlegen."""
    return str(ipaddress.ip_network(subnetz)[PLATZ_HOST])


def _platz_adresse(client, session_id: str, netzname_: str) -> str:
    """Die Adresse, die der Arbeitsplatz wirklich hat."""
    if not session_id:
        return ""
    try:
        c = client.containers.get(f"ota-s-{session_id[:12]}")
        netze = c.attrs["NetworkSettings"]["Networks"]
        return (netze.get(netzname_) or {}).get("IPAddress", "")
    except (NotFound, APIError, KeyError):
        return ""


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
    # **`greedy=True` ist nicht Beiwerk.** Ohne liefert das Docker-SDK die
    # Netze ohne ihre Container (`Containers` ist `None`). Bis zum 2026-09-25
    # stand es so da, und zwei Stellen verliessen sich auf die Liste:
    # `anbindung_sichern` hielt jede Anbindung fuer fehlend (harmlos, Docker
    # lehnt die doppelte ab), und `waisen_aufraeumen` hielt **jedes** Netz fuer
    # verwaist — es haette Traefik und den Router aus laufenden Sitzungen
    # getrennt.
    for netz in client.networks.list(filters={"label": LABEL_SITZUNG}, greedy=True):
        konfig = (netz.attrs.get("IPAM") or {}).get("Config") or [{}]
        subnetz = konfig[0].get("Subnet", "")
        if not subnetz:
            continue
        roh = (netz.attrs.get("Labels") or {}).get(LABEL_PROFIL, "{}")
        try:
            profil = json.loads(roh)
        except ValueError:
            profil = {}
        sitzung = (netz.attrs.get("Labels") or {}).get(LABEL_SITZUNG, "")
        raus.append({
            "name": netz.name,
            "subnetz": subnetz,
            "session_id": sitzung,
            "gateway": str(ipaddress.ip_network(subnetz)[ROUTER_HOST]),
            "sandbox": _sandbox(client, sitzung),
            # Die **tatsaechliche** Adresse, nicht die erwartete. Docker
            # vergibt sie, und wer sie raet, leitet Ports irgendwohin.
            "adresse": _platz_adresse(client, sitzung, netz.name),
            "stufe": profil.get("stufe", "internet"),
            "freigaben": profil.get("freigaben", []),
            "namen": profil.get("namen", []),
            "container": list((netz.attrs.get("Containers") or {}).keys()),
        })
    return raus


def _sandbox(client, session_id: str) -> str:
    """Dockers Pfad zum Netzwerk-Namensraum des Arbeitsplatzes.

    Der Router betritt ihn, um die Standardroute zu setzen. Der Pfad kommt aus
    Docker selbst (`SandboxKey`) und wird nicht geraten.
    """
    if not session_id:
        return ""
    try:
        c = client.containers.get(f"ota-s-{session_id[:12]}")
        return c.attrs.get("NetworkSettings", {}).get("SandboxKey", "")
    except (NotFound, APIError):
        return ""


def anbindung_sichern(client) -> dict[str, int]:
    """Router und Traefik in jedem Sitzungsnetz — nachziehen, was fehlt.

    **Warum das noetig ist:** Ein Container, der neu erzeugt wird, bekommt nur
    die Netze aus der Compose-Datei. Alle zur Laufzeit angehaengten
    Sitzungsnetze sind weg. Beim Router heisst das: Jeder Arbeitsplatz hat
    zwar noch seine Standardroute auf 10.99.k.2, aber dort ist niemand mehr —
    kein Internet, keine Namensaufloesung, und nichts sagt es.

    Gemessen am 2026-09-04, nach einem `up -d --build firewall`: Der Router
    hing danach nur noch am Uplink, und der Arbeitsplatz war stumm vom Netz
    getrennt. Deshalb gehoert das in **jeden** Abgleich und nicht nur in den
    Start einer Sitzung.
    """
    nachgezogen = {"router": 0, "traefik": 0, "traefik_fest": 0}
    try:
        traefik_netze = client.containers.get(TRAEFIK).attrs["NetworkSettings"]["Networks"]
    except (NotFound, APIError, KeyError):
        traefik_netze = {}
    for netz in sitzungsnetze(client):
        drin = set()
        for cid in netz["container"]:
            try:
                drin.add(client.containers.get(cid).name)
            except (NotFound, APIError):
                continue
        if FIREWALL not in drin:
            router_verbinden(client, netz["name"], netz["subnetz"])
            nachgezogen["router"] += 1
        if TRAEFIK not in drin:
            traefik_verbinden(client, netz["name"], netz["subnetz"])
            nachgezogen["traefik"] += 1
        else:
            # Anlagen von vor dem 2026-09-25: Traefik haengt ohne feste
            # Adresse im Netz und nimmt dem Router beim naechsten Neustart
            # des Wirts womoeglich die seine. Einmal umhaengen — das kostet
            # diese Sitzung einen Augenblick Bild, und danach nie wieder.
            soll = traefik_adresse(netz["subnetz"])
            angaben = traefik_netze.get(netz["name"]) or {}
            fest = (angaben.get("IPAMConfig") or {}).get("IPv4Address", "")
            if fest != soll:
                try:
                    client.networks.get(netz["name"]).disconnect(TRAEFIK, force=True)
                except (NotFound, APIError):
                    pass
                traefik_verbinden(client, netz["name"], netz["subnetz"])
                nachgezogen["traefik_fest"] += 1
    if any(nachgezogen.values()):
        log.warning("Anbindung nachgezogen: %s", nachgezogen)
    router_wiederbeleben(client)
    return nachgezogen


def router_wiederbeleben(client) -> bool:
    """Den Router starten, wenn Docker ihn an einer Adresse hat scheitern lassen.

    Mit `restart: unless-stopped` versucht Docker es genau einmal. Scheitert
    der Start am Netz („Address already in use"), bleibt der Container liegen
    — und mit ihm jeder Arbeitsplatz ohne Netz, bis jemand von Hand startet.

    **Nur bei genau diesem Fehler.** Ein Router, den jemand absichtlich
    angehalten hat, bleibt angehalten; das hier ist keine Ueberwachung,
    sondern die Nachsorge fuer einen Fehler, den `anbindung_sichern` gerade
    behoben hat.
    """
    try:
        router = client.containers.get(FIREWALL)
    except (NotFound, APIError):
        return False
    zustand = router.attrs.get("State") or {}
    if router.status == "running" or "already in use" not in (zustand.get("Error") or ""):
        return False
    try:
        router.start()
        log.warning("Router %s neu gestartet — er war an einer belegten Adresse "
                    "gescheitert", FIREWALL)
        return True
    except APIError as exc:
        log.error("Router %s laesst sich nicht starten: %s", FIREWALL, exc)
        return False


def waisen_aufraeumen(client) -> int:
    """Netze ohne Sitzungscontainer verschwinden.

    Ohne das bleibt ihr Subnetz vergeben, und nach genug Waisen ist der Bereich
    voll — mit einer Fehlermeldung, die nach einem Docker-Problem aussieht und
    keines ist.
    """
    weg = 0
    for netz in sitzungsnetze(client):
        eigene = [c for c in netz["container"]]
        # Traefik und der Router zaehlen nicht: Die haengen in jedem Sitzungsnetz.
        richtige = []
        for cid in eigene:
            try:
                if client.containers.get(cid).name not in (TRAEFIK, FIREWALL):
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
