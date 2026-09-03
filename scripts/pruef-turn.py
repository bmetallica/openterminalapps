#!/usr/bin/env python3
"""Prüft, ob der TURN-Server wirklich vermittelt — und mit welcher Absenderadresse.

Aufruf ohne Argumente; die Angaben kommen aus `deploy/.env`:

    python3 scripts/pruef-turn.py

**Wozu.** Ein TURN-Server, der nicht vermittelt, sagt das nicht. Er nimmt die
Anmeldung an, meldet eine Relay-Adresse zurück und schweigt dann. Im Browser
steht "Waiting for stream", im Session-Container "Fatal SSL error" beim
DTLS-Handschlag — an keiner der beiden Stellen steht der Grund.

Dieses Skript schickt ein Paket durch den Server und schaut nach, was auf der
anderen Seite ankommt. Entscheidend ist Schritt 5: Kommt das Paket beim
Gegenüber von **derselben** Adresse an, die TURN als Relay gemeldet hat? Wenn
nicht, verwirft jeder WebRTC-Stack es, und das Bild bleibt schwarz.

Genau daran ist der erste Anlauf gescheitert — ein TURN je Sitzung, im
Session-Container, hinter einer Docker-Bridge:

    2. Allocate mit Anmeldung  -> Relay 192.168.66.224:65502
    5. Client -> Relay -> Peer: b'HINAUS' von 192.168.0.4:65502
       Absender != Relay 192.168.66.224:65502  [ausgehend KAPUTT]

Deshalb läuft TURN seither als Dienst `turn` im Stack, auf dem Netz des Hosts
(`deploy/docker-compose.yml`).

**Was das Skript nicht prüft.** Es läuft auf dem Host und misst damit den Weg
Host → TURN → Host. Ob ein Browser im Firmennetz oder über VPN denselben Weg
hat, sagt erst ein Aufruf von dort — die Ports aus OTA_TURN_MIN/MAX müssen
dafür als UDP offen sein.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import socket
import struct
import sys
import time
from pathlib import Path

COOKIE = 0x2112A442
WARTE = 4.0

# STUN/TURN-Attribute und -Nachrichtentypen, nur die hier gebrauchten.
A_USERNAME, A_REALM, A_NONCE = 0x0006, 0x0014, 0x0015
A_INTEGRITY, A_ERROR, A_DATA = 0x0008, 0x0009, 0x0013
A_PEER, A_RELAYED, A_TRANSPORT = 0x0012, 0x0016, 0x0019
M_ALLOCATE, M_PERMISSION, M_SEND = 0x0003, 0x0008, 0x0016
R_ALLOCATE_OK, R_PERMISSION_OK, I_DATA = 0x0103, 0x0108, 0x0017


def env_lesen(pfad: Path) -> dict[str, str]:
    werte: dict[str, str] = {}
    if not pfad.exists():
        return werte
    for zeile in pfad.read_text().splitlines():
        zeile = zeile.strip()
        if zeile and not zeile.startswith("#") and "=" in zeile:
            name, _, wert = zeile.partition("=")
            werte[name.strip()] = wert.strip()
    return werte


def attribut(typ: int, wert: bytes) -> bytes:
    return struct.pack("!HH", typ, len(wert)) + wert + b"\x00" * ((-len(wert)) % 4)


def nachricht(methode: int, tid: bytes, attrs: list[bytes],
              schluessel: bytes | None = None) -> bytes:
    koerper = b"".join(attrs)
    if schluessel is not None:
        # Die Prüfsumme geht über die Nachricht, deren Längenfeld sie schon
        # mitzählt — sonst stimmt sie nie.
        kopf = struct.pack("!HHI", methode, len(koerper) + 24, COOKIE) + tid
        koerper += attribut(A_INTEGRITY,
                            hmac.new(schluessel, kopf + koerper, hashlib.sha1).digest())
    return struct.pack("!HHI", methode, len(koerper), COOKIE) + tid + koerper


def zerlege(daten: bytes) -> tuple[int, dict[int, bytes]]:
    typ, laenge = struct.unpack("!HH", daten[:4])
    attrs: dict[int, bytes] = {}
    i = 20
    while i + 4 <= 20 + laenge:
        t, l = struct.unpack("!HH", daten[i:i + 4])
        attrs.setdefault(t, daten[i + 4:i + 4 + l])
        i += 4 + l + ((-l) % 4)
    return typ, attrs


def adresse_lesen(wert: bytes) -> tuple[str, int]:
    port = struct.unpack("!H", wert[2:4])[0] ^ (COOKIE >> 16)
    ip = bytes(a ^ b for a, b in zip(wert[4:8], struct.pack("!I", COOKIE)))
    return socket.inet_ntoa(ip), port


def adresse_schreiben(ip: str, port: int) -> bytes:
    return (struct.pack("!HH", 0x0001, port ^ (COOKIE >> 16))
            + bytes(a ^ b for a, b in zip(socket.inet_aton(ip), struct.pack("!I", COOKIE))))


def fehlertext(attrs: dict[int, bytes]) -> str:
    roh = attrs.get(A_ERROR, b"")
    if len(roh) < 4:
        return "ohne Begründung"
    return f"{roh[2] * 100 + roh[3]} {roh[4:].decode(errors='replace')}"


def main() -> int:
    wurzel = Path(__file__).resolve().parent.parent
    env = env_lesen(wurzel / "deploy" / ".env")

    host = os.environ.get("OTA_TURN_HOST") or env.get("OTA_TURN_HOST", "")
    port = int(os.environ.get("OTA_TURN_PORT") or env.get("OTA_TURN_PORT", "3478"))
    geheim = os.environ.get("OTA_TURN_SECRET") or env.get("OTA_TURN_SECRET", "")

    if not host:
        print("OTA_TURN_HOST ist nicht gesetzt — ohne Selkies wird kein TURN "
              "gebraucht, und ohne Adresse lässt sich keiner prüfen.")
        return 2
    if not geheim:
        print("OTA_TURN_SECRET fehlt. Ohne das Geheimnis kommt weder dieses "
              "Skript noch Selkies am TURN vorbei.")
        return 2

    # Dieselben kurzlebigen Anmeldedaten, die auch Selkies sich ausrechnet:
    # Der Nutzername ist der Ablaufzeitpunkt, das Passwort seine Prüfsumme.
    nutzer = f"{int(time.time()) + 600}"
    passwort = hmac.new(geheim.encode(), nutzer.encode(), hashlib.sha1).digest()
    import base64
    passwort_b64 = base64.b64encode(passwort).decode()

    print(f"TURN {host}:{port}, Zugang gültig bis {nutzer}\n")

    client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client.settimeout(WARTE)
    peer = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    peer.settimeout(WARTE)
    peer.bind(("0.0.0.0", 0))
    peer_port = peer.getsockname()[1]

    transport = attribut(A_TRANSPORT, b"\x11\x00\x00\x00")   # 17 = UDP

    try:
        client.sendto(nachricht(M_ALLOCATE, secrets.token_bytes(12), [transport]),
                      (host, port))
        _, attrs = zerlege(client.recvfrom(2048)[0])
    except socket.timeout:
        print("1. Allocate -> keine Antwort. Läuft der Dienst `turn`, und ist "
              f"UDP {port} von hier aus offen?")
        return 1
    realm, nonce = attrs.get(A_REALM, b""), attrs.get(A_NONCE, b"")
    print(f"1. Allocate ohne Anmeldung  -> 401, realm={realm.decode()}")

    schluessel = hashlib.md5(
        f"{nutzer}:{realm.decode()}:{passwort_b64}".encode()).digest()
    zugang = [attribut(A_USERNAME, nutzer.encode()),
              attribut(A_REALM, realm), attribut(A_NONCE, nonce)]

    client.sendto(nachricht(M_ALLOCATE, secrets.token_bytes(12),
                            [transport] + zugang, schluessel), (host, port))
    typ, attrs = zerlege(client.recvfrom(2048)[0])
    if typ != R_ALLOCATE_OK:
        print(f"2. Allocate mit Anmeldung   -> ABGELEHNT: {fehlertext(attrs)}")
        print("   Stimmt OTA_TURN_SECRET auf beiden Seiten überein?")
        return 1
    relay = adresse_lesen(attrs[A_RELAYED])
    print(f"2. Allocate mit Anmeldung   -> Relay {relay[0]}:{relay[1]}")

    peer_attr = attribut(A_PEER, adresse_schreiben(host, peer_port))
    client.sendto(nachricht(M_PERMISSION, secrets.token_bytes(12),
                            [peer_attr] + zugang, schluessel), (host, port))
    typ, attrs = zerlege(client.recvfrom(2048)[0])
    if typ != R_PERMISSION_OK:
        print(f"3. Erlaubnis für {host}:{peer_port} -> ABGELEHNT: {fehlertext(attrs)}")
        print("   Sperrt eine `--denied-peer-ip`-Zeile diese Adresse aus?")
        return 1
    print(f"3. Erlaubnis für Gegenüber  -> ok ({host}:{peer_port})")

    fehler = 0
    peer.sendto(b"HINEIN", relay)
    try:
        ende = time.monotonic() + WARTE
        while time.monotonic() < ende:
            typ, attrs = zerlege(client.recvfrom(2048)[0])
            if typ == I_DATA:
                print(f"4. Gegenüber -> Relay -> Client: {attrs[A_DATA]!r}"
                      f" von {adresse_lesen(attrs[A_PEER])}  [eingehend ok]")
                break
        else:
            raise socket.timeout
    except socket.timeout:
        print("4. Gegenüber -> Relay -> Client: NICHTS  [eingehend KAPUTT]")
        fehler += 1

    client.sendto(nachricht(M_SEND, secrets.token_bytes(12),
                            [peer_attr, attribut(A_DATA, b"HINAUS")]), (host, port))
    try:
        daten, quelle = peer.recvfrom(2048)
        print(f"5. Client -> Relay -> Gegenüber: {daten!r} von {quelle[0]}:{quelle[1]}")
        if quelle == relay:
            print(f"   Absender == Relay {relay[0]}:{relay[1]}  [ausgehend ok]")
        else:
            print(f"   Absender != Relay {relay[0]}:{relay[1]}  "
                  "[ausgehend KAPUTT — jeder WebRTC-Stack verwirft das]")
            fehler += 1
    except socket.timeout:
        print("5. Client -> Relay -> Gegenüber: NICHTS  [ausgehend KAPUTT]")
        fehler += 1

    print()
    print("TURN vermittelt." if not fehler else
          "TURN vermittelt NICHT — Selkies-Sitzungen bleiben schwarz.")
    return 0 if not fehler else 1


if __name__ == "__main__":
    sys.exit(main())
