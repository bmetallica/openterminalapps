"""Anbindung an ein Verzeichnis (LDAP, Active Directory) — plan.md §9.4.

**Die wichtigste Regel steht ganz oben, weil sie alles andere überlagert:**

    Ein lokales Konto wird niemals über das Verzeichnis angemeldet,
    und ein Verzeichniseintrag kann ein lokales Konto niemals übernehmen.

Was daran hängt: Der erste Administrator einer Anlage ist ein lokales Konto.
Könnte ein gleichnamiger Verzeichniseintrag ihn übernehmen, hätte jeder, der
im Verzeichnis einen Eintrag anlegen darf, damit die Anlage. Deshalb
entscheidet ausschliesslich `users.auth_provider`, wo ein Passwort geprüft
wird — und dieser Wert ändert sich nie von selbst.

**Warum das hier in der API liegt und nicht im Agent.** Sonst geht bei OTA
jeder Griff nach draussen über den Agent
([ADR-002](../../docs/adr/002-nur-der-agent-fasst-docker-an.md)). Hier nicht,
und der Grund ist der Inhalt: Beim Anmelden wandert das Passwort eines
Menschen durch diesen Code. Es zusätzlich über eine interne HTTP-Verbindung
an einen zweiten Dienst zu reichen, verteilt ein Geheimnis auf mehr Stellen,
statt es zu schützen. Die Trennung dient der Angriffsfläche; sie hier
anzuwenden würde ihr schaden.

**Was dieser Code nicht tut:** Passwörter durchreichen. Weg 4 aus `plan.md`
§9.4 (das Anmeldepasswort an den Container geben, damit er selbst Laufwerke
einhängt) ist bewusst nicht gebaut — siehe `plan.md` §17.9.
"""

from __future__ import annotations

import logging
import ssl
from dataclasses import dataclass, field
from typing import Any

import ldap3
from ldap3.core.exceptions import LDAPException

log = logging.getLogger("ota.directory")

# Ein Verzeichnis, das nicht antwortet, darf die Anmeldung nicht aufhalten.
# Fünf Sekunden sind grosszügig für ein Netz, in dem beide Seiten stehen.
TIMEOUT = 5


class DirectoryError(RuntimeError):
    """Etwas am Verzeichnis stimmt nicht. Die Meldung geht an einen Menschen."""


@dataclass
class Person:
    """Was OTA von einem Verzeichniseintrag braucht."""
    dn: str
    login: str
    display_name: str = ""
    email: str = ""
    groups: list[str] = field(default_factory=list)
    uid_number: int | None = None


def _escape(value: str) -> str:
    """Entschärft eine Eingabe für einen LDAP-Filter (RFC 4515).

    Ohne das könnte ein Benutzername den Filter umschreiben — der
    LDAP-Verwandte der SQL-Injektion. `*` genügte, um die Suche auf jeden
    Eintrag zu öffnen.
    """
    out = []
    for ch in value or "":
        if ch in "\\*()\0":
            out.append("\\%02x" % ord(ch))
        else:
            out.append(ch)
    return "".join(out)


def _tls(cfg) -> ldap3.Tls | None:
    if cfg.server_uri.lower().startswith("ldaps://") or cfg.tls_mode == "starttls":
        return ldap3.Tls(
            validate=ssl.CERT_REQUIRED if cfg.tls_verify else ssl.CERT_NONE,
            ca_certs_data=cfg.ca_cert or None,
        )
    return None


def _server(cfg) -> ldap3.Server:
    if not cfg.server_uri:
        raise DirectoryError("Es ist keine Verzeichnis-Adresse hinterlegt.")
    return ldap3.Server(cfg.server_uri, tls=_tls(cfg),
                        connect_timeout=TIMEOUT, get_info=ldap3.NONE)


def _bind(cfg, dn: str, password: str) -> ldap3.Connection:
    """Verbindet und meldet sich an — oder wirft."""
    try:
        conn = ldap3.Connection(
            _server(cfg), user=dn or None, password=password or None,
            auto_bind=False, receive_timeout=TIMEOUT,
            raise_exceptions=False,
        )
        if cfg.tls_mode == "starttls" and not cfg.server_uri.lower().startswith("ldaps://"):
            if not conn.start_tls():
                raise DirectoryError(
                    "StartTLS wurde abgelehnt. Wenn das Verzeichnis kein TLS "
                    "kann, ist das eine Entscheidung — dann bitte ausdrücklich "
                    "auf „ohne“ stellen."
                )
        if not conn.bind():
            raise DirectoryError(_reason(conn))
        return conn
    except LDAPException as exc:
        raise DirectoryError(f"Das Verzeichnis ist nicht erreichbar: {exc}") from exc


def _reason(conn: ldap3.Connection) -> str:
    """Macht aus einer LDAP-Antwort einen Satz, mit dem jemand etwas anfangen kann."""
    result = getattr(conn, "result", None) or {}
    code = result.get("result")
    if code == 49:
        return "Benutzername oder Passwort stimmt nicht."
    if code == 50:
        return ("Dem Dienstkonto fehlt die Berechtigung. Es braucht Leserecht "
                "auf die Basis.")
    if code == 32:
        return ("Die Basis gibt es dort nicht — oder das Dienstkonto darf sie "
                "nicht sehen. OpenLDAP meldet beides als „No such object“.")
    return str(result.get("description") or result.get("message") or "Abgelehnt")


def _text(entry, attribute: str) -> str:
    if not attribute:
        return ""
    value = entry.get(attribute)
    if isinstance(value, list):
        value = value[0] if value else ""
    return str(value or "")


def find_person(cfg, login: str) -> Person | None:
    """Sucht einen Eintrag über das Anmeldemerkmal.

    Gebunden wird dafür mit dem **Dienstkonto**: Wer sich anmeldet, kennt
    seinen eigenen DN nicht, und ihn aus dem Namen zusammenzusetzen geht nur,
    solange alle Konten im selben Zweig liegen. In einem gewachsenen
    Verzeichnis tun sie das nie.
    """
    conn = _bind(cfg, cfg.bind_dn, cfg.bind_password)
    try:
        such = f"(&{cfg.user_filter}({cfg.login_attribute}={_escape(login)}))"
        attrs = [a for a in (cfg.login_attribute, cfg.name_attribute,
                             cfg.mail_attribute, "uidNumber") if a]
        if not conn.search(cfg.base_dn, such, attributes=attrs):
            if (conn.result or {}).get("result") not in (0, 32):
                raise DirectoryError(_reason(conn))
            return None
        if not conn.entries:
            return None
        if len(conn.entries) > 1:
            raise DirectoryError(
                f"Der Name {login!r} kommt im Verzeichnis mehrfach vor. Solange "
                "das so ist, lässt sich nicht entscheiden, wer gemeint ist."
            )

        raw = conn.entries[0].entry_attributes_as_dict
        dn = conn.entries[0].entry_dn
        nummer = raw.get("uidNumber") or []
        try:
            uid_number = int(nummer[0]) if nummer else None
        except (TypeError, ValueError):
            uid_number = None

        return Person(
            dn=dn,
            login=_text(raw, cfg.login_attribute) or login,
            display_name=_text(raw, cfg.name_attribute),
            email=_text(raw, cfg.mail_attribute),
            groups=_groups_of(conn, cfg, dn, login),
            uid_number=uid_number,
        )
    finally:
        conn.unbind()


def _groups_of(conn: ldap3.Connection, cfg, dn: str, login: str) -> list[str]:
    """Die Gruppennamen, in denen dieser Eintrag Mitglied ist.

    Gesucht wird über das Mitglieds-Attribut der Gruppe und nicht über
    `memberOf` am Nutzer: `memberOf` ist im Active Directory da, in OpenLDAP
    aber nur mit einem eigens geladenen Modul. Der Weg über die Gruppe
    funktioniert bei beiden.

    Beide Schreibweisen werden abgedeckt: `member` trägt den ganzen DN,
    `memberUid` nur den Anmeldenamen.
    """
    basis = cfg.group_base_dn or cfg.base_dn
    if not basis:
        return []
    wert = _escape(dn) if cfg.member_attribute.lower() != "memberuid" else _escape(login)
    such = f"(&{cfg.group_filter}({cfg.member_attribute}={wert}))"
    try:
        if not conn.search(basis, such, attributes=[cfg.group_name_attribute]):
            return []
    except LDAPException as exc:
        log.warning("Gruppensuche fehlgeschlagen: %s", exc)
        return []
    namen = []
    for eintrag in conn.entries:
        name = _text(eintrag.entry_attributes_as_dict, cfg.group_name_attribute)
        if name:
            namen.append(name)
    return sorted(namen)


def authenticate(cfg, login: str, password: str) -> Person | None:
    """Prüft ein Passwort gegen das Verzeichnis.

    Zwei Schritte, und beide sind nötig: erst mit dem Dienstkonto den Eintrag
    **suchen**, dann mit dem gefundenen DN und dem eingegebenen Passwort
    **binden**. Der zweite Schritt ist die eigentliche Prüfung — er lässt das
    Verzeichnis entscheiden, nicht uns.

    Ein leeres Passwort wird abgelehnt, bevor es hingeht: Ein LDAP-Bind ohne
    Passwort gilt als anonyme Anmeldung und **gelingt**. Wer das übersieht,
    baut eine Anmeldung, bei der ein leeres Feld jeden hereinlässt.
    """
    if not password:
        return None

    person = find_person(cfg, login)
    if person is None:
        return None

    conn = _bind(cfg, person.dn, password)
    conn.unbind()
    return person


def check(cfg, probe_login: str = "") -> dict[str, Any]:
    """Der Prüf-Knopf: Geht die Verbindung, und was findet sie?

    Er meldet **keinen** Erfolg, wenn nur die Verbindung steht. Ein
    Dienstkonto, das sich anmelden kann, aber nichts sieht, ist der häufigste
    Fall — und der, den eine reine Verbindungsprüfung übersieht.
    """
    out: dict[str, Any] = {"verbunden": False, "eintraege": 0, "gruppen": [],
                           "person": None, "hinweise": []}

    conn = _bind(cfg, cfg.bind_dn, cfg.bind_password)
    out["verbunden"] = True
    try:
        conn.search(cfg.base_dn, cfg.user_filter, attributes=[cfg.login_attribute])
        out["eintraege"] = len(conn.entries)
        if out["eintraege"] == 0:
            out["hinweise"].append(
                "Die Verbindung steht, aber das Dienstkonto sieht keinen "
                "einzigen Eintrag. Meist fehlt ihm das Leserecht auf die "
                "Basis — OpenLDAP meldet das als „No such object“."
            )

        basis = cfg.group_base_dn or cfg.base_dn
        if basis:
            conn.search(basis, cfg.group_filter, attributes=[cfg.group_name_attribute])
            out["gruppen"] = sorted(
                _text(e.entry_attributes_as_dict, cfg.group_name_attribute)
                for e in conn.entries
            )
    finally:
        conn.unbind()

    if probe_login:
        person = find_person(cfg, probe_login)
        if person is None:
            out["hinweise"].append(
                f"{probe_login!r} wurde nicht gefunden. Stimmt das "
                f"Anmeldemerkmal ({cfg.login_attribute})?"
            )
        else:
            out["person"] = {
                "dn": person.dn, "login": person.login,
                "name": person.display_name, "mail": person.email,
                "gruppen": person.groups,
            }
    return out
