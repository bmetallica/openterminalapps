"""Das Regelwerk des Routers — ein nftables-Satz, in einem Stück gesetzt.

**Warum nftables und nicht iptables.** Der Router hat seinen eigenen
Netzwerk-Namensraum; hier teilt er sich mit niemandem etwas. Ein vollständiger
Satz laesst sich atomar setzen (`nft -f -`), und benannte Mengen mit
Lebensdauer gibt es ohne Zusatzwerkzeug — genau das, was die Freigaben nach
Namen brauchen.

**Warum je Sitzung eine eigene Kette.** Nicht der Uebersicht wegen: An einer
eigenen Kette haengen eigene Zaehler. Durchsatz und verworfene Pakete je
Arbeitsplatz sind damit kostenlos zu haben — und wer das erst spaeter
nachruesten will, muss alles anfassen.

**Adressen sind fest vergeben** und nicht dem Zufall ueberlassen:

    10.99.k.1   die Bruecke auf dem Wirt (ungenutzt, es gibt keinen Weg dorthin)
    10.99.k.2   der Router
    10.99.k.10  der Arbeitsplatz

Das macht Regeln lesbar, die Netzuebersicht eindeutig und Fehlersuche moeglich.
"""

from __future__ import annotations

import logging
import subprocess

log = logging.getLogger("otafw.nft")

TABELLE = "ota"
# Was in der Stufe „internet" gesperrt bleibt. Der eigene Bereich liegt in
# 10/8 — damit sind die Nachbarsitzungen automatisch mit erfasst.
PRIVAT = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
          "169.254.0.0/16", "100.64.0.0/10")


class NftFehler(RuntimeError):
    pass


def _kettenname(subnetz: str) -> str:
    return "s_" + subnetz.split("/")[0].replace(".", "_")


def _mengenname(subnetz: str) -> str:
    return "n_" + subnetz.split("/")[0].replace(".", "_")


def _ports(spec: str) -> list[str]:
    """„443", „80,443", „8080-8090", „*" — in nftables-Schreibweise."""
    spec = (spec or "*").strip()
    if spec in ("", "*"):
        return []
    return [t.strip().replace("-", "-") for t in spec.split(",") if t.strip()]


def _protokolle(p: str) -> list[str]:
    p = (p or "beide").strip().lower()
    return ["tcp", "udp"] if p in ("beide", "both", "*") else [p]


def _freigabe_zeilen(ziel: str, ports: str, protokoll: str) -> list[str]:
    """Eine Zeile der Freigabeliste in nftables-Zeilen."""
    portliste = _ports(ports)
    if not portliste:
        # Ohne Portangabe gilt sie fuer alles zu diesem Ziel.
        return [f"ip daddr {ziel} counter accept"]
    raus = []
    for proto in _protokolle(protokoll):
        menge = ", ".join(portliste)
        raus.append(f"ip daddr {ziel} {proto} dport {{ {menge} }} counter accept")
    return raus


def regelwerk(zustand: dict) -> str:
    """Den vollstaendigen Satz bauen. Reine Funktion — leicht zu pruefen."""
    uplink = zustand.get("uplink") or "eth0"
    pool = zustand.get("pool", "10.99.0.0/16")
    sitzungen = zustand.get("sitzungen", [])

    zeilen: list[str] = [f"table inet {TABELLE} {{"]

    # Mengen fuer die Freigaben nach Namen. Der Resolver fuellt sie beim
    # Beantworten; `timeout` raeumt sie wieder ab, wenn die Auskunft alt wird.
    for s in sitzungen:
        if s.get("namen"):
            zeilen += [
                f"  set {_mengenname(s['subnetz'])} {{",
                "    type ipv4_addr",
                "    flags timeout",
                "    timeout 1h",
                "  }",
            ]

    # ---------------------------------------------------------- weiterleiten
    zeilen += [
        "  chain forward {",
        "    type filter hook forward priority filter; policy drop;",
        "    ct state established,related counter accept",
        # Traefik erreicht die Arbeitsplaetze direkt — er haengt im selben Netz
        # und laeuft nicht ueber diesen Router. Diese Zeile ist der Rueckweg
        # fuer alles, was der Arbeitsplatz von sich aus anfaengt.
    ]
    for s in sitzungen:
        zeilen.append(f"    ip saddr {s['subnetz']} counter jump {_kettenname(s['subnetz'])}")
    # Was per Portfreigabe hereinkommt, darf auch ankommen.
    #
    # Ohne diese Zeilen greift die Grundsperre darunter: Das Paket ist nach
    # dem DNAT an einen Arbeitsplatz adressiert, und `ip daddr <pool> drop`
    # trifft es. Der DNAT stand dann richtig da, und trotzdem kam nichts an.
    for w in zustand.get("weiterleitungen", []):
        zeilen.append(
            f"    ip daddr {w['ziel']} {w.get('protokoll', 'tcp')} "
            f"dport {w['innen']} counter accept")

    zeilen += [
        f"    ip saddr {pool} counter drop",
        f"    ip daddr {pool} counter drop",
        "  }",
    ]

    # ------------------------------------------------------- je Sitzung eine
    for s in sitzungen:
        kette = _kettenname(s["subnetz"])
        stufe = s.get("stufe", "internet")
        zeilen.append(f"  chain {kette} {{")

        if stufe == "aus":
            # „Aus" heisst nicht „ohne Firewall": Der Weg fuehrt weiter durch
            # diesen Router, er filtert nur nicht mehr. Der Zaehler bleibt.
            zeilen += ["    counter accept", "  }"]
            continue

        for ziel, ports, proto in zustand.get("grundfreigaben", []):
            zeilen += ["    " + z for z in _freigabe_zeilen(ziel, ports, proto)]
        for f in zustand.get("global", []):
            zeilen += ["    " + z for z in _freigabe_zeilen(
                f["ziel"], f.get("ports", "*"), f.get("protokoll", "beide"))]
        for f in s.get("freigaben", []):
            zeilen += ["    " + z for z in _freigabe_zeilen(
                f["ziel"], f.get("ports", "*"), f.get("protokoll", "beide"))]
        if s.get("namen"):
            zeilen.append(f"    ip daddr @{_mengenname(s['subnetz'])} counter accept")

        # Fremde Resolver sind zu. Sonst ist jede Freigabe nach Namen Zierde:
        # Wer `8.8.8.8` fragen darf, bekommt eine Adresse, die in keiner Menge
        # steht — oder umgeht die Liste ueber einen Namen, den unser Resolver
        # nie gesehen hat. (Gemessen: ohne diese Zeilen antwortete 8.8.8.8.)
        #
        # Den eigenen Resolver trifft das nicht: Er ist der Router selbst, und
        # Verkehr an ihn wird nicht weitergeleitet. Steht **nach** den
        # Freigaben — wer einen bestimmten Resolver ausdruecklich erlaubt,
        # bekommt ihn, und das ist dann eine Entscheidung.
        #
        # (DNS ueber HTTPS umgeht auch das. Die Grenze jeder namensbasierten
        # Freigabe, keine Luecke dieses Regelwerks — siehe firewall.md.)
        zeilen.append("    tcp dport 53 counter drop")
        zeilen.append("    udp dport 53 counter drop")

        if stufe == "abgeschottet":
            zeilen.append("    counter drop")
        else:  # internet
            for bereich in PRIVAT:
                zeilen.append(f"    ip daddr {bereich} counter drop")
            zeilen.append("    counter accept")
        zeilen.append("  }")

    # ------------------------------------------------------------------ NAT
    zeilen += [
        "  chain postrouting {",
        "    type nat hook postrouting priority srcnat; policy accept;",
        # Nach draussen unter **einer** Adresse. Fuer eine vorgelagerte
        # Firewall im Unternehmen ist das eine Regel statt 256.
        f"    oifname \"{uplink}\" ip saddr {pool} counter masquerade",
        "  }",
        "  chain prerouting {",
        "    type nat hook prerouting priority dstnat; policy accept;",
    ]
    for w in zustand.get("weiterleitungen", []):
        # `dnat ip to`, nicht `dnat to`: In einer `inet`-Tabelle ist beides
        # moeglich (v4 und v6), und nftables verlangt die Angabe —
        # „specify `dnat ip' or `dnat ip6' in inet table to disambiguate".
        zeilen.append(
            f"    iifname \"{uplink}\" {w.get('protokoll', 'tcp')} dport {w['aussen']} "
            f"counter dnat ip to {w['ziel']}:{w['innen']}")
    zeilen += ["  }", "}"]
    return "\n".join(zeilen) + "\n"


def anwenden(zustand: dict) -> dict:
    """Den Satz setzen — in einem Stueck, oder gar nicht.

    `nft -f` ist atomar: Entweder der ganze Satz gilt, oder der alte bleibt
    stehen. Ein halb gesetztes Regelwerk kann es damit nicht geben — und genau
    das waere der Zustand, in dem etwas offen ist, das zu sein glaubte.
    """
    # **`delete`, nicht `flush`.** `flush table` leert die Ketten, loescht sie
    # aber nicht: Jede beendete Sitzung liesse ihre leere Kette stehen, und
    # nach tausend Sitzungen stuenden tausend davon da — sichtbar erst, wenn
    # jemand `nft list table` aufruft und sich wundert. Erst anlegen (falls sie
    # fehlt), dann loeschen, dann neu schreiben; alles in einer Datei, also in
    # einem Zug.
    text = (f"table inet {TABELLE} {{}}\n"
            f"delete table inet {TABELLE}\n"
            + regelwerk(zustand))
    fertig = subprocess.run(["nft", "-f", "-"], input=text, capture_output=True,
                            text=True, timeout=30)
    if fertig.returncode != 0:
        raise NftFehler(f"nft: {fertig.stderr.strip()}\n--- Satz ---\n{text}")
    return {"ketten": len(zustand.get("sitzungen", [])), "zeichen": len(text)}


def tabelle_da() -> bool:
    fertig = subprocess.run(["nft", "list", "table", "inet", TABELLE],
                            capture_output=True, text=True)
    return fertig.returncode == 0


def zaehler() -> dict:
    """Die Zaehler je Sitzung — Grundlage fuer Durchsatz und Sicherheitssignale."""
    fertig = subprocess.run(["nft", "-j", "list", "table", "inet", TABELLE],
                            capture_output=True, text=True, timeout=20)
    if fertig.returncode != 0:
        return {}
    import json

    try:
        daten = json.loads(fertig.stdout)
    except ValueError:
        return {}

    raus: dict[str, dict[str, int]] = {}
    for eintrag in daten.get("nftables", []):
        regel = eintrag.get("rule")
        if not regel or not regel.get("chain", "").startswith("s_"):
            continue
        netz = regel["chain"][2:].replace("_", ".") + "/24"
        for ausdruck in regel.get("expr", []):
            z = ausdruck.get("counter")
            if not z:
                continue
            eintragung = raus.setdefault(netz, {"bytes": 0, "pakete": 0,
                                                "verworfen": 0, "verworfen_bytes": 0})
            verworfen = any("drop" in a for a in regel.get("expr", []))
            eintragung["bytes"] += z.get("bytes", 0)
            eintragung["pakete"] += z.get("packets", 0)
            if verworfen:
                eintragung["verworfen"] += z.get("packets", 0)
                eintragung["verworfen_bytes"] += z.get("bytes", 0)
    return raus


def uplink_finden() -> str:
    """Die Schnittstelle, ueber die es nach draussen geht.

    Ueber die Standardroute und nicht ueber den Namen: Welche Schnittstelle
    `eth0` heisst, haengt davon ab, in welcher Reihenfolge Docker die Netze
    angehaengt hat — und das aendert sich mit jeder Sitzung.
    """
    fertig = subprocess.run(["ip", "-o", "route", "show", "default"],
                            capture_output=True, text=True, timeout=10)
    for teil in fertig.stdout.split():
        if teil == "dev":
            return fertig.stdout.split()[fertig.stdout.split().index("dev") + 1]
    return "eth0"
