"""ota-ki — der KI-Durchgang (Handbuch Kapitel 28).

Steht zwischen den Arbeitsplätzen und den KI-Servern. Zwei Wege führen her:

* **Über den Namen** `ki.ota:8790`. So sprechen Continue und opencode ihn an,
  wenn der Durchgang an ist. Sie sehen *ein* Modellverzeichnis über alle
  Server; der Durchgang leitet nach dem Modellnamen weiter und setzt den
  Schlüssel des Servers ein. In den Arbeitsplätzen steht kein Schlüssel.
* **Abgefangen.** Die Firewall leitet alles, was aus einem Arbeitsplatz an
  die Adresse eines eingetragenen KI-Servers geht, hierher um (nft
  `redirect`). Das ursprüngliche Ziel steht in der Verbindung
  (`SO_ORIGINAL_DST`): Die Anfrage geht genau dorthin weiter, wohin sie
  wollte — nur gezählt. So erscheinen auch Skripte und alte Konfigurationen
  mit der echten Adresse in der Statistik.

**Was gezählt wird:** Zeit, Arbeitsplatz (aus der Absenderadresse), Server,
Modell, Pfad, Status, Dauer, Tokens. **Nie Inhalte.** Und nur, wenn die
Statistik eingeschaltet ist — sonst reicht der Durchgang nur weiter.

**TLS** lässt sich nicht aufbrechen, ohne den Arbeitsplätzen eine fremde CA
unterzuschieben. Direktes HTTPS an einen KI-Server wird deshalb unverändert
durchgereicht und nur als Verbindung gezählt (mit dem Namen aus dem
Client-Hello). Wer volle Zahlen will, nimmt den Weg über `ki.ota` — von dort
spricht der Durchgang selbst HTTPS zum Server.

**Kein Eingriff, wo er nicht hingehört:** Eine Verbindung an eine Adresse und
einen Port, die kein eingetragener Server sind (zwei Server auf einer
Adresse, die Firewall fängt je Port ab), geht Byte für Byte unverändert weiter.
"""
from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import json
import logging
import os
import secrets
import socket
import struct
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import h11
import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("otaki")

PORT = int(os.environ.get("OTA_KI_PORT", "8790"))
KI_DIR = Path(os.environ.get("OTA_KI_DIR", "/srv/ota/runtime/ki"))
KONFIG = KI_DIR / "konfig.json"
SPOOL = KI_DIR / "spool"
FW_ZUSTAND = Path(os.environ.get("OTA_FW_STATE", "/var/lib/ota-firewall/zustand.json"))
FASSUNG = "1"

SO_ORIGINAL_DST = 80
KOERPER_GRENZE = 64 * 1024 * 1024        # Anfragen: Bilder in Chats sind groß
MITLESEN_GRENZE = 16 * 1024 * 1024       # Antworten ohne Strom: für `usage`
LEERLAUF = 300                           # offene Verbindung ohne Anfrage
SPOOL_WECHSEL = 60

# Kopfzeilen, die nur für eine Teilstrecke gelten (RFC 9110 §7.6.1), und
# solche, die der Durchgang selbst neu setzt.
TEILSTRECKE = {b"connection", b"keep-alive", b"proxy-connection", b"proxy-authorization",
               b"proxy-authenticate", b"te", b"trailer", b"transfer-encoding", b"upgrade",
               b"host", b"content-length", b"accept-encoding", b"expect"}
PLATZHALTER = {"", "ota"}


# --------------------------------------------------------------------- Zustand

class Lage:
    """Was der Durchgang weiß: Konfiguration, Server, Sitzungsnetze."""

    def __init__(self) -> None:
        self.konfig: dict[str, Any] = {}
        self.konfig_mtime = 0.0
        self.server: list[dict[str, Any]] = []
        # (ip, port) -> Server
        self.nach_ziel: dict[tuple[str, int], dict[str, Any]] = {}
        # Modellname nach außen -> (Server, echter Name)
        self.modelle: dict[str, tuple[dict[str, Any], str]] = {}
        self.netze: list[tuple[ipaddress.IPv4Network, str]] = []
        self.fw_mtime = 0.0
        self.client: httpx.AsyncClient | None = None
        self.zaehler = {"anfragen": 0, "verbindungen": 0, "fehler": 0, "abgefangen": 0}

    @property
    def statistik(self) -> bool:
        return bool(self.konfig.get("statistik"))

    async def neu_laden(self, erzwingen: bool = False) -> None:
        try:
            m = KONFIG.stat().st_mtime
        except OSError:
            m = 0.0
        if m and (erzwingen or m != self.konfig_mtime):
            try:
                self.konfig = json.loads(KONFIG.read_text(encoding="utf-8"))
                self.konfig_mtime = m
                await self._server_aufbauen()
                log.info("Konfiguration gelesen: %d Server, %d Modelle, Statistik %s",
                         len(self.server), len(self.modelle), "an" if self.statistik else "aus")
            except (OSError, ValueError) as exc:
                log.error("Konfiguration nicht lesbar: %s", exc)
        try:
            m = FW_ZUSTAND.stat().st_mtime
        except OSError:
            m = 0.0
        if m and m != self.fw_mtime:
            try:
                z = json.loads(FW_ZUSTAND.read_text(encoding="utf-8"))
                self.netze = [(ipaddress.ip_network(s["subnetz"], strict=False), s.get("session_id", ""))
                              for s in z.get("sitzungen", []) if s.get("subnetz")]
                self.fw_mtime = m
            except (OSError, ValueError, KeyError) as exc:
                log.warning("Zustand der Firewall nicht lesbar: %s", exc)

    async def _server_aufbauen(self) -> None:
        server, nach_ziel, modelle = [], {}, {}
        loop = asyncio.get_running_loop()
        for s in self.konfig.get("server", []):
            teile = urlparse(s.get("url", ""))
            if not teile.hostname:
                continue
            port = teile.port or (443 if teile.scheme == "https" else 80)
            eintrag = {**s, "port": port, "schema": teile.scheme,
                       "ursprung": f"{teile.scheme}://{teile.netloc}",
                       "basis": s["url"].rstrip("/")}
            server.append(eintrag)
            try:
                infos = await loop.getaddrinfo(teile.hostname, port, family=socket.AF_INET,
                                               type=socket.SOCK_STREAM)
                # Zwei Einträge mit derselben Adresse: der erste gilt.
                for info in infos:
                    nach_ziel.setdefault((info[4][0], port), eintrag)
            except OSError as exc:
                log.warning("%s: Name %s nicht auflösbar (%s) — wird nur über ki.ota erreicht",
                            s.get("kuerzel"), teile.hostname, exc)
            for m in s.get("modelle", []):
                modelle.setdefault(m["aussen"], (eintrag, m["echt"]))
        self.server, self.nach_ziel, self.modelle = server, nach_ziel, modelle
        alt = self.client
        zeit = float(self.konfig.get("zeitlimit") or 600)
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=zeit, write=60.0, pool=30.0),
            trust_env=not self.konfig.get("ohne_proxy", True), follow_redirects=False,
            limits=httpx.Limits(max_connections=200, max_keepalive_connections=40))
        if alt is not None:
            # Laufende Anfragen behalten ihren Client noch eine Weile.
            asyncio.get_running_loop().call_later(
                zeit + 60, lambda: asyncio.ensure_future(alt.aclose()))

    def erlaubt(self, server: dict[str, Any], sitzung: str) -> bool:
        """Darf diese Sitzung an diesen Server? Ein Server mit Gruppen nennt
        die Sitzungen, deren Mensch ihn bekommt (die API rechnet das aus)."""
        if server.get("alle", True):
            return True
        return bool(sitzung) and sitzung in set(server.get("sitzungen") or [])

    def sitzung(self, ip: str) -> str:
        try:
            a = ipaddress.ip_address(ip)
        except ValueError:
            return ""
        for netz, sid in self.netze:
            if a in netz:
                return sid
        return ""


LAGE = Lage()


# ----------------------------------------------------------------------- Spool

class Spool:
    """Eine Zeile je Anfrage; die Datei wird jede Minute abgeschlossen."""

    def __init__(self) -> None:
        self.datei: Path | None = None
        self.seit = 0.0

    def schreiben(self, zeile: dict[str, Any]) -> None:
        if not LAGE.statistik:
            return
        try:
            if self.datei is None:
                SPOOL.mkdir(parents=True, exist_ok=True)
                self.datei = SPOOL / f"laufend-{int(time.time())}-{secrets.token_hex(3)}.jsonl"
                self.seit = time.monotonic()
            with self.datei.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(zeile, ensure_ascii=False) + "\n")
        except OSError as exc:
            log.error("Spool nicht schreibbar: %s", exc)

    def abschliessen(self, immer: bool = False) -> None:
        if self.datei is None or (not immer and time.monotonic() - self.seit < SPOOL_WECHSEL):
            return
        try:
            self.datei.rename(self.datei.with_name(self.datei.name.replace("laufend-", "fertig-", 1)))
        except OSError as exc:
            log.error("Spool nicht abschließbar: %s", exc)
        self.datei = None

    def aufraeumen_beim_start(self) -> None:
        """Was ein abgebrochener Lauf offen ließ, ist trotzdem gezählt."""
        try:
            for p in SPOOL.glob("laufend-*.jsonl"):
                p.rename(p.with_name(p.name.replace("laufend-", "fertig-", 1)))
        except OSError:
            pass


SPOOL_ = Spool()


def _jetzt() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _werkzeug(ua: str) -> str:
    u = ua.lower()
    if "opencode" in u or "ai-sdk" in u:
        return "opencode"
    if "continue" in u:
        return "continue"
    if "python" in u or "curl" in u or "node" in u or "go-http" in u:
        return "skript"
    return "sonstiges"


# ------------------------------------------------------------------ Hilfen

def _ursprungsziel(sock: socket.socket) -> tuple[str, int]:
    roh = sock.getsockopt(socket.SOL_IP, SO_ORIGINAL_DST, 16)
    port, = struct.unpack_from("!H", roh, 2)
    return socket.inet_ntoa(roh[4:8]), port


def _sni(daten: bytes) -> str:
    """Den Servernamen aus einem TLS-ClientHello — oder leer."""
    try:
        if len(daten) < 43 or daten[0] != 0x16 or daten[5] != 0x01:
            return ""
        i = 43
        i += 1 + daten[i]                                   # Sitzungs-ID
        i += 2 + struct.unpack_from("!H", daten, i)[0]      # Chiffren
        i += 1 + daten[i]                                   # Kompression
        ende = i + 2 + struct.unpack_from("!H", daten, i)[0]
        i += 2
        while i + 4 <= ende and i + 4 <= len(daten):
            art, laenge = struct.unpack_from("!HH", daten, i)
            i += 4
            if art == 0:
                n = struct.unpack_from("!H", daten, i + 3)[0]
                return daten[i + 5:i + 5 + n].decode("ascii", "replace")[:200]
            i += laenge
    except (IndexError, struct.error):
        pass
    return ""


async def _durchreichen(anfang: bytes, reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                        ziel: tuple[str, int]) -> tuple[int, int]:
    """Byte für Byte weiter — für TLS und für alles, was kein KI-Server ist."""
    try:
        r2, w2 = await asyncio.wait_for(asyncio.open_connection(*ziel), 15)
    except (OSError, asyncio.TimeoutError):
        return 0, 0
    zaehler = [len(anfang), 0]
    w2.write(anfang)

    async def pumpe(von: asyncio.StreamReader, nach: asyncio.StreamWriter, i: int) -> None:
        try:
            while True:
                stueck = await von.read(65536)
                if not stueck:
                    break
                zaehler[i] += len(stueck)
                nach.write(stueck)
                await nach.drain()
        except (OSError, asyncio.IncompleteReadError):
            pass
        finally:
            with contextlib.suppress(OSError, RuntimeError):
                if nach.can_write_eof():
                    nach.write_eof()

    await asyncio.gather(pumpe(reader, w2, 0), pumpe(r2, writer, 1))
    with contextlib.suppress(OSError):
        w2.close()
    return zaehler[0], zaehler[1]


def _fehler(code: int, text: str) -> tuple[int, list[tuple[bytes, bytes]], bytes]:
    koerper = json.dumps({"error": {"message": text, "type": "ota_ki", "code": code}},
                         ensure_ascii=False).encode()
    return code, [(b"content-type", b"application/json")], koerper


# ------------------------------------------------------------- Verbindungen

async def verbindung(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    LAGE.zaehler["verbindungen"] += 1
    sock = writer.get_extra_info("socket")
    quelle = (writer.get_extra_info("peername") or ("", 0))[0]
    try:
        ziel = _ursprungsziel(sock)
    except OSError:
        ziel = (writer.get_extra_info("sockname") or ("", 0))[:2]
    try:
        await LAGE.neu_laden()
        server = LAGE.nach_ziel.get(ziel)
        if server is None and ziel[1] != PORT:
            # Kein eingetragener Server (Menge je Port): nicht eingreifen.
            anfang = await asyncio.wait_for(reader.read(65536), 30)
            await _durchreichen(anfang, reader, writer, ziel)
            return
        anfang = await asyncio.wait_for(reader.read(65536), 30)
        if not anfang:
            return
        if anfang[0] == 0x16:
            if server is None:
                return  # TLS an den Durchgang selbst: spricht er nicht
            if not LAGE.erlaubt(server, LAGE.sitzung(quelle)):
                return  # keine HTTP-Antwort möglich: die Verbindung endet hier
            LAGE.zaehler["abgefangen"] += 1
            beginn = time.monotonic()
            zeit = _jetzt()
            hin, her = await _durchreichen(anfang, reader, writer, ziel)
            SPOOL_.schreiben({"zeit": zeit, "quelle": quelle, "session_id": LAGE.sitzung(quelle),
                              "weg": "tls", "server": server.get("kuerzel", ""),
                              "sni": _sni(anfang), "dauer_ms": int((time.monotonic() - beginn) * 1000),
                              "bytes_hin": hin, "bytes_her": her})
            return
        if server is not None:
            LAGE.zaehler["abgefangen"] += 1
        await _http(anfang, reader, writer, quelle, server)
    except (asyncio.TimeoutError, ConnectionError, OSError):
        pass
    except Exception as exc:  # noqa: BLE001 — eine Verbindung darf den Dienst nicht reißen
        LAGE.zaehler["fehler"] += 1
        log.exception("Verbindung von %s: %s", quelle, exc)
    finally:
        with contextlib.suppress(OSError, RuntimeError):
            writer.close()


async def _http(anfang: bytes, reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                quelle: str, server: dict[str, Any] | None) -> None:
    conn = h11.Connection(h11.SERVER)
    conn.receive_data(anfang)
    while True:
        # --- eine Anfrage vollständig lesen
        anfrage: h11.Request | None = None
        koerper = bytearray()
        while True:
            ereignis = conn.next_event()
            if ereignis is h11.NEED_DATA:
                if conn.they_are_waiting_for_100_continue:
                    writer.write(conn.send(h11.InformationalResponse(status_code=100, headers=[])))
                daten = await asyncio.wait_for(reader.read(65536), LEERLAUF)
                conn.receive_data(daten)
                continue
            if isinstance(ereignis, h11.Request):
                anfrage = ereignis
            elif isinstance(ereignis, h11.Data):
                koerper += ereignis.data
                if len(koerper) > KOERPER_GRENZE:
                    await _senden(conn, writer, *_fehler(413, "Die Anfrage ist zu groß."))
                    return
            elif isinstance(ereignis, h11.EndOfMessage):
                break
            elif isinstance(ereignis, h11.ConnectionClosed) or ereignis is h11.PAUSED:
                return
        if anfrage is None:
            return
        await _beantworten(conn, writer, anfrage, bytes(koerper), quelle, server)
        if conn.our_state is h11.MUST_CLOSE or conn.their_state is h11.MUST_CLOSE:
            return
        try:
            conn.start_next_cycle()
        except h11.LocalProtocolError:
            return


async def _senden(conn: h11.Connection, writer: asyncio.StreamWriter, code: int,
                  kopf: list[tuple[bytes, bytes]], koerper: bytes) -> None:
    writer.write(conn.send(h11.Response(status_code=code,
                                        headers=kopf + [(b"content-length", str(len(koerper)).encode())])))
    writer.write(conn.send(h11.Data(data=koerper)))
    writer.write(conn.send(h11.EndOfMessage()))
    await writer.drain()


def _modellliste(sitzung: str) -> bytes:
    daten = [{"id": aussen, "object": "model", "owned_by": s.get("name") or s.get("kuerzel", "")}
             for aussen, (s, _echt) in LAGE.modelle.items() if LAGE.erlaubt(s, sitzung)]
    return json.dumps({"object": "list", "data": daten}, ensure_ascii=False).encode()


async def _beantworten(conn: h11.Connection, writer: asyncio.StreamWriter, anfrage: h11.Request,
                       koerper: bytes, quelle: str, server: dict[str, Any] | None) -> None:
    LAGE.zaehler["anfragen"] += 1
    beginn = time.monotonic()
    zeit = _jetzt()
    methode = anfrage.method.decode()
    pfad = anfrage.target.decode("latin-1")
    kopf = {k.lower(): v for k, v in anfrage.headers}
    ua = kopf.get(b"user-agent", b"").decode("latin-1")
    ueber_name = server is None
    sitzung = LAGE.sitzung(quelle)

    # --- Körper lesen: Modell, Strom
    daten: dict[str, Any] | None = None
    if koerper[:1] == b"{":
        with contextlib.suppress(ValueError):
            geladen = json.loads(koerper)
            daten = geladen if isinstance(geladen, dict) else None
    modell = str((daten or {}).get("model") or "")
    echt = modell

    # --- Ziel bestimmen
    if ueber_name:
        if methode == "GET" and pfad.split("?")[0].rstrip("/") in ("/v1/models", "/models"):
            await _senden(conn, writer, 200, [(b"content-type", b"application/json")], _modellliste(sitzung))
            return
        if modell:
            treffer = LAGE.modelle.get(modell)
            if treffer is None:
                await _senden(conn, writer, *_fehler(
                    404, f"Das Modell „{modell}“ ist in OTA nicht eingetragen "
                         "(Einstellungen → IDE-AI)."))
                return
            server, echt = treffer
        elif LAGE.server:
            server = LAGE.server[0]
        else:
            await _senden(conn, writer, *_fehler(503, "In OTA ist kein KI-Server eingetragen."))
            return
        # Der Pfad hängt am Basispfad des Servers: /v1/chat/completions an
        # http://x/api/v1 wird http://x/api/v1/chat/completions.
        rest = pfad[3:] if pfad.startswith("/v1") else pfad
        url = server["basis"] + rest
    else:
        url = server["ursprung"] + pfad
    if not LAGE.erlaubt(server, sitzung):
        SPOOL_.schreiben({"zeit": zeit, "quelle": quelle, "session_id": sitzung,
                          "weg": "name" if ueber_name else "abgefangen", "server": server.get("kuerzel", ""),
                          "modell": modell, "pfad": pfad.split("?")[0][:120], "werkzeug": _werkzeug(ua),
                          "status": 403, "dauer_ms": 0, "erstes_ms": None, "ein": None, "aus": None})
        await _senden(conn, writer, *_fehler(
            403, f"Der KI-Server {server.get('name') or server.get('kuerzel')} ist für dich nicht "
                 "freigegeben. Freigeben kann ihn die Verwaltung (Einstellungen → IDE-AI)."))
        return

    # --- Körper anpassen
    neu = False
    streicht_nutzung = False
    if daten is not None:
        if echt != modell:
            daten["model"] = echt
            neu = True
        if LAGE.statistik and daten.get("stream") is True:
            so = daten.get("stream_options")
            so = dict(so) if isinstance(so, dict) else {}
            if not so.get("include_usage"):
                so["include_usage"] = True
                daten["stream_options"] = so
                streicht_nutzung = True
                neu = True
    if neu:
        koerper = json.dumps(daten, ensure_ascii=False).encode()

    # --- Kopfzeilen: Schlüssel des Servers, wo der Arbeitsplatz keinen hat
    weiter = [(k, v) for k, v in anfrage.headers if k.lower() not in TEILSTRECKE]
    auth = kopf.get(b"authorization", b"").decode("latin-1")
    traeger = auth[7:].strip() if auth.lower().startswith("bearer ") else auth.strip()
    schluessel = server.get("api_key") or ""
    if schluessel and (ueber_name or traeger in PLATZHALTER):
        weiter = [(k, v) for k, v in weiter if k.lower() != b"authorization"]
        weiter.append((b"authorization", f"Bearer {schluessel}".encode()))
    weiter.append((b"accept-encoding", b"identity"))

    zeile: dict[str, Any] = {
        "zeit": zeit, "quelle": quelle, "session_id": sitzung,
        "weg": "name" if ueber_name else "abgefangen", "server": server.get("kuerzel", ""),
        "modell": modell, "pfad": pfad.split("?")[0][:120], "werkzeug": _werkzeug(ua),
        "status": 0, "dauer_ms": 0, "erstes_ms": None, "ein": None, "aus": None,
    }
    try:
        assert LAGE.client is not None
        anf = LAGE.client.build_request(methode, url, headers=weiter, content=koerper)
        antwort = await LAGE.client.send(anf, stream=True)
    except (httpx.HTTPError, AssertionError) as exc:
        zeile.update(status=502, dauer_ms=int((time.monotonic() - beginn) * 1000))
        SPOOL_.schreiben(zeile)
        await _senden(conn, writer, *_fehler(
            502, f"Der KI-Server {server.get('name') or server.get('kuerzel')} antwortet nicht "
                 f"({type(exc).__name__})."))
        return

    zeile["status"] = antwort.status_code
    art = antwort.headers.get("content-type", "")
    strom = "text/event-stream" in art
    kopf_raus = [(k.encode(), v.encode()) for k, v in antwort.headers.items()
                 if k.lower().encode() not in TEILSTRECKE and k.lower() != "content-encoding"]
    try:
        writer.write(conn.send(h11.Response(status_code=antwort.status_code, headers=kopf_raus)))
        if strom and LAGE.statistik:
            await _strom(conn, writer, antwort, zeile, beginn, streicht_nutzung)
        else:
            mit = bytearray()
            async for stueck in antwort.aiter_raw():
                if zeile["erstes_ms"] is None:
                    zeile["erstes_ms"] = int((time.monotonic() - beginn) * 1000)
                if LAGE.statistik and not strom and len(mit) < MITLESEN_GRENZE:
                    mit += stueck
                writer.write(conn.send(h11.Data(data=stueck)))
                await writer.drain()
            if mit and "json" in art:
                with contextlib.suppress(ValueError, AttributeError, TypeError):
                    _nutzung(json.loads(bytes(mit)).get("usage"), zeile)
        writer.write(conn.send(h11.EndOfMessage()))
        await writer.drain()
    finally:
        await antwort.aclose()
        zeile["dauer_ms"] = int((time.monotonic() - beginn) * 1000)
        SPOOL_.schreiben(zeile)


def _nutzung(u: Any, zeile: dict[str, Any]) -> None:
    if isinstance(u, dict):
        if isinstance(u.get("prompt_tokens"), int):
            zeile["ein"] = u["prompt_tokens"]
        if isinstance(u.get("completion_tokens"), int):
            zeile["aus"] = u["completion_tokens"]


async def _strom(conn: h11.Connection, writer: asyncio.StreamWriter, antwort: httpx.Response,
                 zeile: dict[str, Any], beginn: float, streicht_nutzung: bool) -> None:
    """Server-Sent Events Ereignis für Ereignis: `usage` mitlesen, und das
    Nutzungs-Ereignis, das nur der Durchgang bestellt hat, nicht weitergeben."""
    puffer = b""
    async for stueck in antwort.aiter_raw():
        if zeile["erstes_ms"] is None:
            zeile["erstes_ms"] = int((time.monotonic() - beginn) * 1000)
        puffer += stueck.replace(b"\r\n", b"\n")
        raus = bytearray()
        while b"\n\n" in puffer:
            ereignis, puffer = puffer.split(b"\n\n", 1)
            weg = False
            for z in ereignis.split(b"\n"):
                if z.startswith(b"data:") and b'"usage"' in z:
                    with contextlib.suppress(ValueError, AttributeError):
                        d = json.loads(z[5:].strip())
                        _nutzung(d.get("usage"), zeile)
                        if streicht_nutzung and d.get("usage") and not d.get("choices"):
                            weg = True
            if not weg:
                raus += ereignis + b"\n\n"
        if raus:
            writer.write(conn.send(h11.Data(data=bytes(raus))))
            await writer.drain()
    if puffer:
        writer.write(conn.send(h11.Data(data=puffer)))


# ------------------------------------------------------------------ Betrieb

async def _haushalt() -> None:
    while True:
        await asyncio.sleep(10)
        with contextlib.suppress(Exception):
            await LAGE.neu_laden()
            SPOOL_.abschliessen()
            status = {"zeit": _jetzt(), "fassung": FASSUNG, "statistik": LAGE.statistik,
                      "server": [s.get("kuerzel") for s in LAGE.server],
                      "modelle": len(LAGE.modelle), **LAGE.zaehler}
            tmp = KI_DIR / "status.tmp"
            tmp.write_text(json.dumps(status), encoding="utf-8")
            os.replace(tmp, KI_DIR / "status.json")


async def _haupt() -> None:
    SPOOL_.aufraeumen_beim_start()
    await LAGE.neu_laden(erzwingen=True)
    if LAGE.client is None:
        LAGE.client = httpx.AsyncClient(timeout=httpx.Timeout(connect=10.0, read=600.0, write=60.0,
                                                              pool=30.0), trust_env=False)
    dienst = await asyncio.start_server(verbindung, host="0.0.0.0", port=PORT, backlog=512)
    log.info("KI-Durchgang lauscht auf :%d", PORT)
    asyncio.ensure_future(_haushalt())
    async with dienst:
        await dienst.serve_forever()


def main() -> None:
    try:
        asyncio.run(_haupt())
    finally:
        SPOOL_.abschliessen(immer=True)
