from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.orm import Session as DbSession

from .models import AuditLog, User


def absender(request: Request | None) -> str | None:
    """Von welcher Adresse die Anfrage kam.

    **Wem wir dabei glauben:** Den Kopf `X-Forwarded-For` setzt Traefik selbst;
    einen mitgeschickten uebernimmt es nur von Absendern, die in
    `OTA_TRUSTED_PROXIES` stehen. Ohne diese Kette waere der Wert frei waehlbar
    — und eine Bremse, die sich am Absender orientiert, waere wirkungslos: Wer
    den Kopf selbst setzt, ist bei jedem Versuch jemand anderes.

    Diese Funktion steht hier und nicht zweimal im Quelltext, weil das Protokoll
    und die Anmeldebremse dieselbe Adresse meinen muessen. Sonst steht im
    Protokoll ein anderer Absender als der, den die Bremse gezaehlt hat.
    """
    if request is None:
        return None
    return request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (
        request.client.host if request.client else None
    )


# --------------------------------------------------------------------------
# Wann die IP-Adresse mitkommt
# --------------------------------------------------------------------------
#
# Seit 2026-11-19 nur noch dort, wo sie einen Zweck hat (Art. 5 Abs. 1 lit. c):
#
#   * **Gescheiterte und auffaellige Anmeldungen** — sie ist der einzige
#     Hinweis darauf, von wo jemand Passwoerter durchprobiert.
#   * **Vorgaenge von Konten mit Verwaltungsrechten** — wird ein solches Konto
#     missbraucht, ist sie der wichtigste Beleg, von wo aus.
#   * Vorgaenge ohne angemeldetes Konto.
#
# Nicht bei erfolgreichen Anmeldungen, Sitzungen und allem, was normale Nutzer
# tun: Bei einem internen System steht eine Adresse meist fuer einen Rechner
# oder Ort, und sie schaerfte nur das Arbeitszeitprofil. Die Sperre nach
# Fehlversuchen braucht das Protokoll nicht (`users.failed_from`).
# Migration `b7c3e9f1a425` hat die Adressen aus aelteren Eintraegen genommen.
IMMER_MIT_IP = (
    "login.failed",
    "login.totp_failed",
    "login.recovery_failed",
    "login.recovery_used",
    "login.oidc_refused",
    "login.oidc_rejected",
    "login.oidc_state_mismatch",
)
# Rechte, die kein Verwaltungsrecht sind: ein Werkzeug fuer Entwickler.
NUTZER_RECHTE = frozenset({"arbeitsplatz.root"})


def mit_ip(action: str, actor: User | None) -> bool:
    if action in IMMER_MIT_IP:
        return True
    if action in VERHALTEN:
        return False
    if actor is None:
        return True
    return bool(actor.permissions - NUTZER_RECHTE)


def record(
    db: DbSession,
    action: str,
    *,
    actor: User | None = None,
    object_type: str | None = None,
    object_id: str | None = None,
    request: Request | None = None,
    **detail,
) -> None:
    """Schreibt einen Audit-Eintrag. Inhalte werden nie erfasst, nur Vorgaenge."""
    ip = absender(request) if mit_ip(action, actor) else None
    db.add(AuditLog(
        actor_user_id=actor.id if actor else None,
        actor_name=actor.username if actor else None,
        action=action,
        object_type=object_type,
        object_id=str(object_id) if object_id else None,
        ip=ip,
        detail=detail,
    ))


# --------------------------------------------------------------------------
# Aufbewahrung
# --------------------------------------------------------------------------
#
# Bis zum 2026-09-05 loeschte sich hier **nichts**. Gemessen an dem Tag: 11.174
# Eintraege in zehn Tagen, und **jeder einzelne** mit einer IP-Adresse. Das ist
# kein Platzproblem — 270 Byte je Eintrag, gut 350 MB im Jahr bei zwanzig
# Arbeitsplaetzen. Es ist ein Datenschutzproblem: Aus `login.ok`,
# `session.started` (und damals `app.started`) eines Menschen liess sich
# lueckenlos ablesen, wann er gearbeitet hat, wie lange und woran.
#
# Deshalb zwei Fristen (`config.py`), und die kurze ist eine **ausdrueckliche
# Liste**, keine Regel ueber Praefixe. Das ist Absicht: `session.attached` faengt
# mit `session.` an, gehoert aber in die lange Klasse — es ist der Eintrag, den
# ein Betroffener oder ein Betriebsrat spaeter nachlesen koennen muss. Eine
# Praefix-Regel haette ihn stillschweigend mitgeloescht.
#
# Was nicht in der Liste steht, wird **behalten**. Wer eine neue, haeufige
# Aktion einfuehrt, traegt sie hier ein — vergessen kostet Platz, aber es
# loescht nichts, was jemand gebraucht haette.
VERHALTEN = (
    "login.ok",
    "login.oidc_ok",
    "login.failed",
    "login.totp_failed",
    "login.recovery_failed",
    "login.recovery_used",
    "session.started",
    "session.stopped",
    "session.deleted",
    # `app.started` / `app.stopped` gibt es seit 2026-11-19 nicht mehr
    # (Migration a1d9e4b7c362); welche Anwendung jemand öffnet, wird nicht
    # protokolliert.
)

# In Haeppchen loeschen statt in einem Rutsch: Ein `DELETE` ueber Hunderttausende
# Zeilen haelt die Tabelle waehrend seiner ganzen Laufzeit fest, und in dieser
# Tabelle schreibt jede Anmeldung.
STAPEL = 5000


def _weg(db: DbSession, grenze: datetime, aktionen: tuple[str, ...] | None) -> int:
    """Loescht alte Eintraege in Haeppchen. Gibt zurueck, wie viele."""
    gesamt = 0
    while True:
        # `ctid` ist Postgres' Zeilenadresse — der billigste Weg, ein DELETE
        # zu begrenzen; ein LIMIT direkt am DELETE gibt es nicht.
        stmt = text(
            "DELETE FROM audit_log WHERE ctid IN ("
            "  SELECT ctid FROM audit_log"
            "   WHERE ts < :grenze"
            + ("   AND action = ANY(:aktionen)" if aktionen is not None
               else "   AND NOT (action = ANY(:aktionen))")
            + "   LIMIT :stapel)"
        )
        werte = {"grenze": grenze, "stapel": STAPEL,
                 "aktionen": list(aktionen if aktionen is not None else VERHALTEN)}
        weg = db.execute(stmt, werte).rowcount or 0
        db.commit()
        gesamt += weg
        if weg < STAPEL:
            return gesamt


def aufraeumen(db: DbSession) -> dict[str, int]:
    """Wendet beide Fristen an. Gibt zurueck, was weggefallen ist."""
    from .config import settings

    s = settings()
    jetzt = datetime.now(timezone.utc)
    raus = {"verhalten": 0, "verwaltung": 0}

    if s.protokoll_verhalten_tage > 0:
        raus["verhalten"] = _weg(
            db, jetzt - timedelta(days=s.protokoll_verhalten_tage), VERHALTEN)
    if s.protokoll_verwaltung_tage > 0:
        raus["verwaltung"] = _weg(
            db, jetzt - timedelta(days=s.protokoll_verwaltung_tage), None)

    # Das Terminal-Protokoll laeuft mit der Verwaltungsklasse: Was ein
    # Administrator in fremden Arbeitsplaetzen getippt hat, muss eine Pruefung
    # so lange finden koennen wie jeden anderen Verwaltungsvorgang — und nicht
    # laenger. Ohne diese Zeilen waere es das einzige Protokoll ohne Frist.
    if s.protokoll_verwaltung_tage > 0:
        from .models import TerminalEintrag
        from sqlalchemy import delete as _delete
        raus["terminal"] = db.execute(_delete(TerminalEintrag).where(
            TerminalEintrag.ts < jetzt - timedelta(days=s.protokoll_verwaltung_tage)
        )).rowcount or 0
        db.commit()

    # Dass aufgeraeumt wurde, gehoert selbst ins Protokoll — sonst sieht ein
    # Loch in den Daten spaeter aus wie ein Ausfall. Der Eintrag steht in der
    # langen Klasse und ueberlebt damit den naechsten Durchlauf.
    if raus["verhalten"] or raus["verwaltung"] or raus.get("terminal"):
        record(db, "protokoll.aufgeraeumt", **raus)
        db.commit()
    return raus
