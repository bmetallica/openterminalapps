"""Das Regelwerk — aus dem gewuenschten Zustand wird ein Satz iptables-Regeln.

**Warum Vollabgleich und keine Einzelbefehle.** Der Agent sagt nicht „fuege
diese Regel hinzu", sondern „so sieht die Welt aus". Bei Einzelbefehlen fuehrt
jeder verlorene Aufruf zu einem Regelwerk, das von der Wirklichkeit abweicht —
und niemand merkt es, weil nichts kaputtgeht, sondern nur etwas offen bleibt.
Beim Vollabgleich heilt sich das von selbst, und ein Neustart von Docker (der
die Ketten wegwirft) ebenso.

**Warum zwei Ketten.** `DOCKER-USER` haengt in `FORWARD` und sieht nur
weitergeleiteten Verkehr. Was ein Container an den **Wirt selbst** schickt,
laeuft durch `INPUT` und wuerde dort nie geprueft — genau dort lagen SSH,
Elasticsearch und Redis in Befund H1.

**Und eine Feinheit, die erst beim Messen auffiel:** Ein *veroeffentlichter*
Port eines fremden Containers (`-p 9200:9200`) ist kein Dienst des Wirts. Er
wird in `nat/PREROUTING` umgeschrieben und danach **weitergeleitet** — er
gehoert also in die FORWARD-Kette, obwohl er unter der Adresse des Wirts
erreichbar ist. Nach dem Umschreiben zeigt das Ziel auf das Containernetz des
fremden Stapels, und das faellt unter die privaten Bereiche. Die Sperre der
privaten Bereiche erledigt ihn deshalb mit.
"""

from __future__ import annotations

# Was als „privat" gilt und in der Stufe „internet" gesperrt bleibt.
#
# `100.64/10` ist der Bereich fuer Carrier-NAT und taucht in Firmennetzen
# gelegentlich auf; `169.254/16` ist die Selbstvergabe und fuehrt unter anderem
# zu den Metadatendiensten der Cloud-Anbieter.
PRIVAT = (
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "169.254.0.0/16",
    "100.64.0.0/10",
    "127.0.0.0/8",
)

KETTE_FWD = "OTA-FW"
KETTE_IN = "OTA-FW-INPUT"


def _ports(spec: str) -> list[str]:
    """„443", „8080-8090", „*" — in das, was iptables versteht."""
    spec = (spec or "*").strip()
    if spec in ("", "*"):
        return []
    return [t.strip().replace("-", ":") for t in spec.split(",") if t.strip()]


def _protokolle(p: str) -> list[str]:
    p = (p or "beide").strip().lower()
    return ["tcp", "udp"] if p in ("beide", "both", "*") else [p]


def _freigabe(quelle: str, ziel: str, ports: str, protokoll: str) -> list[list[str]]:
    """Eine Zeile der Freigabeliste in Regeln uebersetzen."""
    raus: list[list[str]] = []
    portliste = _ports(ports)
    if not portliste:
        # Ohne Portangabe gilt sie fuer jedes Protokoll — auch fuer ICMP, damit
        # ein freigegebenes Ziel auch anpingbar ist. Wer Ports nennt, meint TCP
        # oder UDP und nichts sonst.
        raus.append(["-s", quelle, "-d", ziel, "-j", "RETURN"])
        return raus
    for proto in _protokolle(protokoll):
        for port in portliste:
            raus.append(["-s", quelle, "-d", ziel, "-p", proto,
                         "--dport", port, "-j", "RETURN"])
    return raus


def forward_regeln(zustand: dict) -> list[list[str]]:
    """Die Kette fuer weitergeleiteten Verkehr, von oben nach unten gelesen."""
    pool = zustand["pool"]
    regeln: list[list[str]] = []

    # 1. Antwortpakete. Ohne diese Zeile bricht jede bestehende Verbindung ab,
    #    sobald sich das Regelwerk aendert.
    regeln.append(["-m", "conntrack", "--ctstate", "ESTABLISHED,RELATED", "-j", "RETURN"])

    # 2. Traefik darf in die Sitzungen hinein — das ist der Weg des Bildes.
    #    Nur von seinen Adressen, nicht aus seinem ganzen Netz.
    #
    #    **Adressen, Mehrzahl.** Traefik haengt in jedem Sitzungsnetz und hat
    #    dort je eine eigene. Mit nur einer Regel kaeme das Bild in genau einer
    #    Sitzung an — und in allen anderen stuende „Waiting for stream", ohne
    #    dass irgendwo ein Fehler auftauchte.
    for adresse in zustand.get("traefik_ips") or []:
        regeln.append(["-s", adresse, "-d", pool, "-j", "RETURN"])
        # Und **zu** Traefik hin, aus jeder Richtung.
        #
        # Beim Messen aufgefallen und der unangenehmste Fund dieses Umbaus:
        # Sobald Traefik mit einem Sitzungsnetz verbunden wird, schreibt Docker
        # den DNAT seines veroeffentlichten Ports auf **diese** Adresse um —
        # `-j DNAT --to-destination 10.99.0.3:8443`. Die Grundsperre am Ende
        # dieser Kette (`-d <pool> -j DROP`) traf damit OTAs eigenen
        # Haupteingang: Von aussen kam niemand mehr herein, und im Protokoll
        # stand nichts. Diese Zeile ist die Ausnahme dafuer.
        regeln.append(["-d", adresse, "-j", "RETURN"])

    for sitzung in zustand.get("sitzungen", []):
        netz = sitzung["subnetz"]
        stufe = sitzung.get("stufe", "internet")

        if stufe == "offen":
            regeln.append(["-s", netz, "-j", "RETURN"])
            continue

        # 3. Der Grundregelsatz, den OTA selbst braucht — unabhaengig von der
        #    Stufe, sonst funktioniert nicht einmal „abgeschottet".
        for ziel, ports, proto in zustand.get("grundfreigaben", []):
            regeln.extend(_freigabe(netz, ziel, ports, proto))

        # 4. Was der Administrator ausdruecklich erlaubt hat.
        for f in sitzung.get("freigaben", []):
            regeln.extend(_freigabe(netz, f["ziel"], f.get("ports", "*"),
                                    f.get("protokoll", "beide")))

        # 5. Namen: Was der eigene Resolver gerade herausgegeben hat, steht in
        #    einer Menge. Siehe `resolver.py` — die Menge fuellt sich beim
        #    Beantworten, nicht aus einer Aufloesung von vorgestern.
        if sitzung.get("mengenname"):
            regeln.append(["-s", netz, "-m", "set", "--match-set",
                           sitzung["mengenname"], "dst", "-j", "RETURN"])

        # 6. Fremde Resolver sind zu — sonst ist die ganze Namensfreigabe
        #    Zierde: Wer `8.8.8.8` fragen darf, bekommt eine Adresse, die in
        #    keiner Menge steht, oder umgeht die Liste ueber einen Namen, den
        #    unser Resolver nie gesehen hat. Der eigene Resolver ist davon
        #    nicht betroffen — er sitzt auf dem Wirt und laeuft ueber INPUT.
        #
        #    Steht nach den Freigaben: Wer einen bestimmten Resolver
        #    ausdruecklich erlaubt, bekommt ihn. Das ist dann eine Entscheidung
        #    und kein Versehen.
        #
        #    (DNS ueber HTTPS umgeht auch das. Das ist die Grenze jeder
        #    namensbasierten Freigabe, keine Luecke dieses Regelwerks — es
        #    steht in firewall.md.)
        for proto in ("udp", "tcp"):
            regeln.append(["-s", netz, "-p", proto, "--dport", "53", "-j", "DROP"])

        # 7. Die Stufe entscheidet ueber den Rest.
        if stufe == "abgeschottet":
            regeln.append(["-s", netz, "-j", "DROP"])
        else:  # internet
            # Alles Private bleibt zu — darin liegen das Firmennetz, die
            # anderen Sitzungen (10.99/16 ist Teil von 10/8) und die
            # Containernetze der fremden Stapel auf diesem Wirt.
            for bereich in PRIVAT:
                regeln.append(["-s", netz, "-d", bereich, "-j", "DROP"])
            regeln.append(["-s", netz, "-j", "RETURN"])

    # 8. Die Grundsperre. Sie steht am Ende der Kette und gilt fuer jedes Netz
    #    aus dem Bereich, fuer das oben nichts stand — also auch fuer ein
    #    gerade erst angelegtes, dessen Regeln noch nicht da sind.
    regeln.append(["-s", pool, "-j", "DROP"])
    regeln.append(["-d", pool, "-j", "DROP"])
    return regeln


def input_regeln(zustand: dict) -> list[list[str]]:
    """Die Kette fuer Verkehr an den Wirt selbst."""
    pool = zustand["pool"]
    regeln: list[list[str]] = []
    regeln.append(["-s", pool, "-m", "conntrack", "--ctstate",
                   "ESTABLISHED,RELATED", "-j", "RETURN"])

    # Der eigene Resolver. Er lauscht im Namensraum des Wirts auf **jeder**
    # Schnittstelle — `bind-dynamic` muss das, weil staendig neue Bruecken
    # dazukommen. Damit stuende er ohne die folgenden Zeilen als offener
    # Resolver im Firmennetz: DNS-Verstaerkungsangriffe, und ein Dienst, den
    # niemand bestellt hat. (Beim Nachmessen aufgefallen: dnsmasq lauschte
    # prompt auch auf der LAN-Adresse des Wirts.)
    #
    # Also: aus den Sitzungen erlaubt, vom Wirt selbst erlaubt, von ueberall
    # sonst verworfen.
    if zustand.get("dns_port"):
        port = str(zustand["dns_port"])
        for proto in ("udp", "tcp"):
            regeln.append(["-i", "lo", "-p", proto, "--dport", port, "-j", "RETURN"])
        for proto in ("udp", "tcp"):
            regeln.append(["-s", pool, "-p", proto, "--dport", port, "-j", "RETURN"])
        for proto in ("udp", "tcp"):
            regeln.append(["!", "-s", pool, "-p", proto, "--dport", port, "-j", "DROP"])

    # Der Medienweg. TURN laeuft als Dienst im Wirtsnamensraum, ist also aus
    # Sicht des Containers ein Dienst des Wirts.
    turn = zustand.get("turn") or {}
    if turn.get("port"):
        for proto in ("udp", "tcp"):
            regeln.append(["-s", pool, "-p", proto, "--dport",
                           str(turn["port"]), "-j", "RETURN"])
    if turn.get("min") and turn.get("max"):
        for proto in ("udp", "tcp"):
            regeln.append(["-s", pool, "-p", proto, "--dport",
                           f"{turn['min']}:{turn['max']}", "-j", "RETURN"])

    regeln.append(["-s", pool, "-j", "DROP"])
    return regeln
