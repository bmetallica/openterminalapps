"""Das Protokoll zusätzlich an einen Syslog-Server (Handbuch Kapitel 11).

Unter Einstellungen → Protokoll an Syslog ein- und ausschaltbar. Jeder
Eintrag im Protokoll von OTA (`audit_log`) geht dann **zusätzlich** an einen
Syslog-Server, im Format RFC 5424, über UDP, TCP oder TLS (RFC 5425).

**Wozu:** Ein Administrator mit Zugriff auf die Datenbank könnte Einträge
über sich selbst ändern oder löschen. Eine Kopie an einem Ort, den er nicht
verwaltet, macht das sichtbar (Art. 5 Abs. 2 und Art. 32 DSGVO). Ohne diese
Kopie stand in dsgvo.md Abschnitt 10: „eine Kopie an einen getrennten Ort
gibt es nicht“.

**Wie, ohne etwas zu verlieren:** Nicht im Augenblick des Schreibens, sondern
im Takt aus der Tabelle (`takt`, alle fünf Sekunden). Was nicht ankam, bleibt
in der Tabelle und geht beim nächsten Versuch mit — auch nach einem Neustart
der API oder einem Ausfall des Syslog-Servers. Der Stand (`syslog.stand`)
merkt sich den Zeitpunkt des letzten gesendeten Eintrags und die Kennungen
der Einträge aus den letzten zwei Minuten davor: Ein Eintrag, dessen
Transaktion länger brauchte, trägt eine ältere Zeit als ein schon gesendeter
und würde sonst übersprungen. Ein Eintrag kann im Fehlerfall zweimal
ankommen, aber nie gar nicht (solange er nicht vorher nach seiner Frist
gelöscht wurde).

**Was gesendet wird:** derselbe Eintrag wie im Protokoll — Zeit, Aktion,
handelndes Konto, Objekt, gegebenenfalls Adresse, Einzelheiten — als JSON in
der Nachricht. Mit dem Umfang „ohne Alltag“ bleiben erfolgreiche Anmeldungen
und Sitzungsbeginn und -ende in OTA: Sie sagen viel über die Arbeitszeit
eines Menschen und wenig über Angriffe. Gescheiterte Anmeldungen gehen mit.
"""
from __future__ import annotations

import json
import logging
import socket
import ssl
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from . import settings_store
from .models import AuditLog

log = logging.getLogger("ota.syslog")

PROTOKOLLE = ("udp", "tcp", "tls")
RAHMUNGEN = ("laenge", "zeilenumbruch")
UMFAENGE = ("alle", "ohne_alltag")
# Was „ohne Alltag“ zurückhält: erfolgreiche Anmeldungen und Sitzungen.
ALLTAG = ("login.ok", "login.oidc_ok", "session.started", "session.stopped", "session.deleted")
# RFC 5424, Abschnitt 6.2.1
FACILITIES = {"auth": 4, "authpriv": 10, "daemon": 3, "user": 1, "local0": 16, "local1": 17,
              "local2": 18, "local3": 19, "local4": 20, "local5": 21, "local6": 22, "local7": 23}

VORGABE: dict[str, Any] = {
    "an": False,
    "host": "",
    "port": 514,
    "protokoll": "tcp",
    "rahmung": "laenge",
    "ca": "",
    "facility": "authpriv",
    "absender": "ota",
    "umfang": "ohne_alltag",
}

FENSTER = timedelta(minutes=2)
STAPEL = 500
TAKT_SEKUNDEN = 5
GRENZE_UDP = 8192
GRENZE_TCP = 65536


class SyslogFehler(ValueError):
    pass


# Zustand dieses Prozesses, für die Anzeige. Die API läuft mit einem Worker.
_lage_sperre = threading.Lock()
_lage: dict[str, Any] = {"gesendet": 0, "zuletzt": None, "fehler": None, "fehler_seit": None}


def lage() -> dict[str, Any]:
    with _lage_sperre:
        return dict(_lage)


def _lage_setzen(**werte: Any) -> None:
    with _lage_sperre:
        _lage.update(werte)


def einstellungen(db: DbSession) -> dict[str, Any]:
    roh = settings_store.get(db, settings_store.SYSLOG)
    e = {**VORGABE, **(roh if isinstance(roh, dict) else {})}
    return _bereinigt(e, streng=False)


def _bereinigt(e: dict[str, Any], streng: bool) -> dict[str, Any]:
    def fehler(text: str, ersatz: Any) -> Any:
        if streng:
            raise SyslogFehler(text)
        return ersatz

    aus: dict[str, Any] = {"an": bool(e.get("an"))}
    host = str(e.get("host") or "").strip()
    if host and (len(host) > 253 or any(c.isspace() or c in "/@:" for c in host.strip("[]"))
                 and not host.startswith("[")):
        host = fehler("Der Server ist ein Name oder eine Adresse, ohne Schema und Port.", "")
    aus["host"] = host.strip("[]")
    try:
        port = int(e.get("port") or 514)
    except (TypeError, ValueError):
        port = 0
    if not 1 <= port <= 65535:
        port = fehler("Der Port liegt zwischen 1 und 65535.", 514)
    aus["port"] = port
    for k, erlaubt in (("protokoll", PROTOKOLLE), ("rahmung", RAHMUNGEN), ("umfang", UMFAENGE)):
        wert = e.get(k)
        aus[k] = wert if wert in erlaubt else fehler(f"Unbekannter Wert für {k}.", VORGABE[k])
    fac = e.get("facility")
    aus["facility"] = fac if fac in FACILITIES else fehler("Unbekannte Facility.", "authpriv")
    absender = str(e.get("absender") or "ota").strip()
    if not absender.isascii() or any(not 33 <= ord(c) <= 126 for c in absender) or len(absender) > 64:
        absender = fehler("Der Absendername besteht aus sichtbaren ASCII-Zeichen, höchstens 64.",
                          "ota")
    aus["absender"] = absender
    ca = str(e.get("ca") or "").strip()
    if ca and "-----BEGIN CERTIFICATE-----" not in ca:
        ca = fehler("Das CA-Zertifikat im PEM-Format, beginnend mit -----BEGIN CERTIFICATE-----.",
                    "")
    if ca and streng:
        try:
            ssl.create_default_context(cadata=ca)
        except ssl.SSLError as exc:
            raise SyslogFehler(f"Das CA-Zertifikat lässt sich nicht lesen: {exc}") from exc
    aus["ca"] = ca
    if streng and aus["an"] and not aus["host"]:
        raise SyslogFehler("Erst einen Syslog-Server eintragen.")
    return aus


def speichern(db: DbSession, eingabe: dict[str, Any]) -> dict[str, Any]:
    alt = einstellungen(db)
    neu = _bereinigt({**alt, **{k: v for k, v in eingabe.items() if k in VORGABE}}, streng=True)
    settings_store.put(db, settings_store.SYSLOG, neu)
    if neu["an"] and not alt["an"]:
        # Ab jetzt — nicht das ganze bisherige Protokoll auf einmal.
        settings_store.put(db, settings_store.SYSLOG_STAND,
                           {"ts": datetime.now(timezone.utc).isoformat(), "ids": []})
        _lage_setzen(fehler=None, fehler_seit=None)
    return neu


# ------------------------------------------------------------------ Format

def _schwere(action: str) -> int:
    """RFC 5424: 4 Warnung für Gescheitertes und Abgewiesenes, sonst 5 Notiz."""
    if any(w in action for w in ("failed", "refused", "rejected", "mismatch", "gesperrt",
                                 "denied", "verweigert")):
        return 4
    return 5


def _feld(text: str, laenge: int) -> str:
    """Ein Kopffeld nach RFC 5424: sichtbares ASCII, ohne Leerzeichen."""
    sauber = "".join(c if 33 <= ord(c) <= 126 else "_" for c in text)[:laenge]
    return sauber or "-"


def nachricht(e: dict[str, Any], eintrag: dict[str, Any]) -> bytes:
    ts = eintrag["ts"]
    zeit = ts.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    pri = FACILITIES[e["facility"]] * 8 + _schwere(eintrag["action"])
    inhalt = json.dumps({
        "id": eintrag["id"], "ts": zeit, "action": eintrag["action"],
        "actor": eintrag.get("actor"), "object_type": eintrag.get("object_type"),
        "object_id": eintrag.get("object_id"), "ip": eintrag.get("ip"),
        "detail": eintrag.get("detail") or {},
    }, ensure_ascii=False, separators=(",", ":"), default=str)
    kopf = (f"<{pri}>1 {zeit} {_feld(e['absender'], 255)} ota - "
            f"{_feld(eintrag['action'], 32)} - ")
    roh = (kopf + inhalt).encode("utf-8")
    grenze = GRENZE_UDP if e["protokoll"] == "udp" else GRENZE_TCP
    if len(roh) > grenze:
        # Zu lang (große Einzelheiten): ohne sie, mit einem Hinweis.
        kurz = json.dumps({"id": eintrag["id"], "ts": zeit, "action": eintrag["action"],
                           "actor": eintrag.get("actor"), "object_type": eintrag.get("object_type"),
                           "object_id": eintrag.get("object_id"), "ip": eintrag.get("ip"),
                           "detail_gekuerzt": True}, ensure_ascii=False, separators=(",", ":"))
        roh = (kopf + kurz).encode("utf-8")[:grenze]
    return roh


# ------------------------------------------------------------------ Senden

class _Verbindung:
    def __init__(self, e: dict[str, Any], zeitlimit: float = 10.0) -> None:
        self.e = e
        self.udp = e["protokoll"] == "udp"
        familie = socket.getaddrinfo(e["host"], e["port"], 0,
                                     socket.SOCK_DGRAM if self.udp else socket.SOCK_STREAM)
        if not familie:
            raise OSError(f"{e['host']} ist nicht auflösbar")
        if self.udp:
            af, art, proto, _, self.adresse = familie[0]
            self.sock = socket.socket(af, art, proto)
            return
        # Jede Adresse des Namens, bis eine annimmt — „localhost“ etwa ist
        # zuerst ::1, der Dienst lauscht aber vielleicht nur auf 127.0.0.1.
        letzter: OSError | None = None
        for af, art, proto, _, adresse in familie:
            s = socket.socket(af, art, proto)
            s.settimeout(zeitlimit)
            try:
                s.connect(adresse)
                break
            except OSError as exc:
                s.close()
                letzter = exc
        else:
            raise letzter or OSError("keine Adresse")
        self.adresse = adresse
        if e["protokoll"] == "tls":
            ctx = ssl.create_default_context(cadata=e["ca"] or None)
            if not e["ca"]:
                ctx.load_default_certs()
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2
            s = ctx.wrap_socket(s, server_hostname=e["host"])
        self.sock = s

    def senden(self, roh: bytes) -> None:
        if self.udp:
            self.sock.sendto(roh, self.adresse)
            return
        if self.e["rahmung"] == "laenge" or self.e["protokoll"] == "tls":
            # RFC 6587 3.4.1 / RFC 5425: Länge, Leerzeichen, Nachricht.
            self.sock.sendall(str(len(roh)).encode() + b" " + roh)
        else:
            self.sock.sendall(roh.replace(b"\n", b" ") + b"\n")

    def schliessen(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


def _eintrag(a: AuditLog) -> dict[str, Any]:
    return {"id": str(a.id), "ts": a.ts, "action": a.action, "actor": a.actor_name,
            "object_type": a.object_type, "object_id": a.object_id, "ip": a.ip,
            "detail": a.detail}


def testen(db: DbSession, eingabe: dict[str, Any] | None = None) -> dict[str, Any]:
    """Eine Testnachricht — mit den gespeicherten Werten oder denen aus dem
    Formular (noch ungespeichert)."""
    e = _bereinigt({**einstellungen(db), **{k: v for k, v in (eingabe or {}).items()
                                           if k in VORGABE}, "an": True}, streng=True)
    beginn = time.monotonic()
    try:
        v = _Verbindung(e)
        try:
            v.senden(nachricht(e, {"id": "test", "ts": datetime.now(timezone.utc),
                                   "action": "syslog.test",
                                   "detail": {"text": "Testnachricht von OTA"}}))
        finally:
            v.schliessen()
    except (OSError, ssl.SSLError) as exc:
        return {"ok": False, "fehler": _grund(exc), "ms": int((time.monotonic() - beginn) * 1000)}
    return {"ok": True, "ms": int((time.monotonic() - beginn) * 1000),
            "udp": e["protokoll"] == "udp"}


def _grund(exc: BaseException) -> str:
    if isinstance(exc, ssl.SSLCertVerificationError):
        return f"Zertifikat abgelehnt: {exc.verify_message}"
    if isinstance(exc, socket.gaierror):
        return "Der Name des Servers lässt sich nicht auflösen."
    if isinstance(exc, ConnectionRefusedError):
        return "Verbindung abgelehnt — läuft dort ein Syslog-Dienst auf diesem Port?"
    if isinstance(exc, TimeoutError | socket.timeout):
        return "Keine Antwort — Server, Port oder Firewall prüfen."
    return f"{type(exc).__name__}: {exc}"


def _stand(db: DbSession) -> tuple[datetime, set[str]]:
    roh = settings_store.get(db, settings_store.SYSLOG_STAND)
    roh = roh if isinstance(roh, dict) else {}
    try:
        ts = datetime.fromisoformat(roh["ts"])
    except (KeyError, TypeError, ValueError):
        ts = datetime.now(timezone.utc)
    return ts, {str(i) for i in roh.get("ids") or []}


def takt(db: DbSession) -> int:
    """Was seit dem letzten Mal ins Protokoll kam, senden. Gibt zurück, wie
    viele Einträge gesendet wurden. Ein Fehler lässt den Stand, wo er war."""
    e = einstellungen(db)
    if not e["an"] or not e["host"]:
        return 0
    stand_ts, stand_ids = _stand(db)
    zeilen = db.scalars(select(AuditLog).where(AuditLog.ts > stand_ts - FENSTER)
                        .order_by(AuditLog.ts, AuditLog.id).limit(STAPEL + len(stand_ids))).all()
    neu = [a for a in zeilen if str(a.id) not in stand_ids][:STAPEL]
    if not neu:
        return 0
    gesendet = 0
    erledigt: list[AuditLog] = []
    verbindung: _Verbindung | None = None
    try:
        for a in neu:
            if e["umfang"] == "ohne_alltag" and a.action in ALLTAG:
                erledigt.append(a)
                continue
            if verbindung is None:
                verbindung = _Verbindung(e)
            verbindung.senden(nachricht(e, _eintrag(a)))
            erledigt.append(a)
            gesendet += 1
    except (OSError, ssl.SSLError) as exc:
        grund = _grund(exc)
        if lage().get("fehler") != grund:
            log.warning("Syslog: %s", grund)
        _lage_setzen(fehler=grund, fehler_seit=lage().get("fehler_seit")
                     or datetime.now(timezone.utc).isoformat())
    finally:
        if verbindung is not None:
            verbindung.schliessen()
    if erledigt:
        neuer_ts = max(stand_ts, max(a.ts for a in erledigt))
        ids = {i for i in stand_ids}
        ids.update(str(a.id) for a in erledigt)
        # Nur, was noch im Fenster liegt: Ältere fragt die nächste Abfrage
        # nicht mehr ab.
        behalten = {str(a.id) for a in zeilen if a.ts >= neuer_ts - FENSTER and str(a.id) in ids}
        settings_store.put(db, settings_store.SYSLOG_STAND,
                           {"ts": neuer_ts.isoformat(), "ids": sorted(behalten)})
        db.commit()
    if gesendet and len(erledigt) == len(neu):
        _lage_setzen(gesendet=lage()["gesendet"] + gesendet,
                     zuletzt=datetime.now(timezone.utc).isoformat(), fehler=None, fehler_seit=None)
    elif gesendet:
        _lage_setzen(gesendet=lage()["gesendet"] + gesendet)
    return gesendet


def rueckstand(db: DbSession) -> int:
    """Wie viele Einträge noch nicht gesendet sind (ungefähr: ohne den Alltag
    abzuziehen, den „ohne Alltag“ nicht sendet)."""
    e = einstellungen(db)
    if not e["an"]:
        return 0
    stand_ts, stand_ids = _stand(db)
    from sqlalchemy import func
    n = db.execute(select(func.count()).select_from(AuditLog)
                   .where(AuditLog.ts > stand_ts - FENSTER)).scalar() or 0
    return max(n - len(stand_ids), 0)
