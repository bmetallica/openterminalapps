"""Identität verwalten: Keycloak, das Verzeichnis dahinter, der Notzugang.

**Ein Weg, nicht zwei.** Bis zum 2026-09-04 sprach OTA selbst LDAP — eigene
Anbindung, eigener Abgleich, eigene Anmeldung. Dieser Weg ist entfallen: Ein
Verzeichnis bindet man in Keycloak an, und Keycloak macht die Anmeldung
(`auth-roadmap.md`, Entscheidung 4). Zwei Wege zu derselben Sache waren einer
zu viel — und der alte war der, den niemand mehr pflegte.

Das Kennwort des Dienstkontos geht nur **hinein**. Es kommt nie zurück; die
Oberfläche zeigt statt dessen, ob eines hinterlegt ist.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from .. import audit, keycloak, settings_store, uebernahme
from ..db import get_db
from ..deps import current_user, require_permission
from ..models import Group, User
from ..schemas import KcVerzeichnisIn

router = APIRouter(prefix="/api/admin/identity", tags=["identity"])
manage = require_permission("users.manage", "settings.manage")


# --------------------------------------------------------------------------
# Keycloak — Zustand und Rechte (auth-roadmap.md, Etappe A)
#
# Noch **ohne Wirkung auf die Anmeldung**: OTA meldet sich weiterhin selbst an.
# Was hier steht, beantwortet nur die Frage, die vor jedem weiteren Schritt
# steht — läuft es, und was darf OTA darin?
#
# Bewusst ein eigener Pfad und nicht ein Feld in der Verzeichniskonfiguration:
# Die beiden haben nichts miteinander zu tun, solange die Umstellung nicht
# abgeschlossen ist, und die alte Anbindung soll bis dahin unberührt bleiben.
# --------------------------------------------------------------------------

@router.get("/keycloak", dependencies=[Depends(manage)])
def keycloak_status() -> dict:
    """Erreichbarkeit, Betriebsart und was das Dienstkonto darf.

    Wirft nicht. Ein Keycloak, das gerade schweigt, ist ein Zustand, den die
    Oberfläche anzeigen soll — nicht ein Fehler, an dem sie stehenbleibt.
    """
    zustand = keycloak.probe()
    zustand["version"] = keycloak.version() if zustand["erreichbar"] else None
    return zustand


# --------------------------------------------------------------------------
# Die Verzeichnisanbindung in Keycloak (Etappe C)
#
# Der Punkt der ganzen Übung: Ein Administrator richtet hier ein Active
# Directory ein und muss Keycloak dafür nicht öffnen.
#
# Das Kennwort des Dienstkontos geht nur **hinein** — dieselbe Regel wie bei
# der alten Anbindung oben. Zurück kommt nur die Auskunft, ob eines hinterlegt
# ist.
# --------------------------------------------------------------------------


@router.get("/keycloak/verzeichnis", dependencies=[Depends(manage)])
def kc_verzeichnis() -> dict:
    try:
        return {"eingerichtet": True, **(keycloak.verzeichnis_lesen() or {})} \
            if keycloak.verzeichnis_lesen() else {"eingerichtet": False}
    except keycloak.KeycloakFehler as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc


@router.put("/keycloak/verzeichnis", dependencies=[Depends(manage)])
def kc_verzeichnis_setzen(body: KcVerzeichnisIn, request: Request,
                          actor: User = Depends(current_user),
                          db: DbSession = Depends(get_db)) -> dict:
    try:
        daten = keycloak.verzeichnis_setzen(
            body.model_dump(exclude={"bind_password"}), body.bind_password or None)
    except keycloak.KeycloakFehler as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    # Im Protokoll steht, **wer** es veranlasst hat. Keycloaks eigene
    # Ereignisse sagen nur „ota-manager hat etwas geändert" (§5.5).
    audit.record(db, "keycloak.verzeichnis_gesetzt", actor=actor, request=request,
                 server=body.server_uri, base=body.base_dn)
    db.commit()
    return {"eingerichtet": True, **daten}


@router.delete("/keycloak/verzeichnis", dependencies=[Depends(manage)])
def kc_verzeichnis_weg(request: Request, actor: User = Depends(current_user),
                       db: DbSession = Depends(get_db)) -> dict:
    try:
        keycloak.verzeichnis_entfernen()
    except keycloak.KeycloakFehler as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    audit.record(db, "keycloak.verzeichnis_entfernt", actor=actor, request=request)
    db.commit()
    return {"eingerichtet": False}


@router.post("/keycloak/verzeichnis/test", dependencies=[Depends(manage)])
def kc_verzeichnis_test(body: KcVerzeichnisIn) -> dict:
    """Prüfen, ohne zu speichern. Genau die beiden Fragen, an denen es scheitert."""
    kennwort = body.bind_password or None
    if not kennwort:
        # Kein Kennwort mitgeschickt heisst: das gespeicherte benutzen. Dafür
        # muss Keycloak es kennen — sonst kann hier nichts geprüft werden.
        vorhanden = keycloak.verzeichnis_lesen()
        if not vorhanden or not vorhanden.get("hat_kennwort"):
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "Zum Prüfen wird das Kennwort des Dienstkontos gebraucht.")
    try:
        return keycloak.verzeichnis_testen(
            body.model_dump(exclude={"bind_password"}), kennwort)
    except keycloak.KeycloakFehler as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc


@router.post("/keycloak/verzeichnis/abgleich", dependencies=[Depends(manage)])
def kc_verzeichnis_abgleich(request: Request, voll: bool = False,
                            actor: User = Depends(current_user),
                            db: DbSession = Depends(get_db)) -> dict:
    try:
        ergebnis = keycloak.verzeichnis_abgleichen(voll=voll)
    except keycloak.KeycloakFehler as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    audit.record(db, "keycloak.verzeichnis_abgleich", actor=actor, request=request,
                 voll=voll)
    db.commit()
    return ergebnis


# --------------------------------------------------------------------------
# Notfallkonto und Übernahme (auth-roadmap.md, Etappe E)
#
# Die Reihenfolge ist hier kein Vorschlag: Erst muss ein Notfallkonto stehen,
# dann darf übernommen werden. Wer alle Konten auf einen Dienst umstellt, der
# ausfallen kann, braucht vorher einen Weg zurück.
# --------------------------------------------------------------------------


@router.get("/notfallkonto", dependencies=[Depends(manage)])
def notfallkonto(db: DbSession = Depends(get_db)) -> dict:
    name = settings_store.breakglass(db)
    konto = db.scalar(select(User).where(User.username == name)) if name else None
    return {
        "name": name,
        "vorhanden": konto is not None,
        "brauchbar": bool(konto and konto.auth_provider == "local"
                          and konto.password_hash and konto.is_admin
                          and konto.is_active and not konto.is_locked),
    }


@router.put("/notfallkonto", dependencies=[Depends(manage)])
def notfallkonto_setzen(body: dict, request: Request,
                        actor: User = Depends(current_user),
                        db: DbSession = Depends(get_db)) -> dict:
    """Bestimmt das eine lokale Konto, das bleibt.

    Geprüft wird sofort und vollständig — ein Notausgang, der erst im Ernstfall
    als verschlossen auffällt, ist schlimmer als keiner.
    """
    name = str(body.get("name") or "").strip().lower()
    if not name:
        settings_store.put(db, settings_store.BREAKGLASS, "")
        audit.record(db, "notfallkonto.entfernt", actor=actor, request=request)
        db.commit()
        return {"name": "", "vorhanden": False, "brauchbar": False}

    konto = db.scalar(select(User).where(User.username == name))
    if konto is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"„{name}“ gibt es nicht.")
    if konto.auth_provider != "local" or not konto.password_hash:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"„{name}“ hat kein lokales Passwort. Genau das ist aber sein Zweck — "
            "es soll auch dann funktionieren, wenn Keycloak schweigt.")
    if not konto.is_admin:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"„{name}“ ist kein Administrator.")

    settings_store.put(db, settings_store.BREAKGLASS, name)
    audit.record(db, "notfallkonto.gesetzt", actor=actor, request=request, konto=name)
    db.commit()
    return {"name": name, "vorhanden": True, "brauchbar": True}


@router.get("/uebernahme", dependencies=[Depends(manage)])
def uebernahme_stand(db: DbSession = Depends(get_db)) -> dict:
    """Was noch zu übernehmen wäre — ohne etwas zu ändern."""
    try:
        return uebernahme.lauf(db, probe=True)
    except uebernahme.NichtBereit as exc:
        return {"bereit": False, "grund": str(exc),
                "offen": len(uebernahme.offen(db))}


@router.post("/uebernahme", dependencies=[Depends(manage)])
def uebernahme_starten(request: Request, actor: User = Depends(current_user),
                       db: DbSession = Depends(get_db)) -> dict:
    """Übernimmt die Bestandskonten. Die Einmal-Passwörter kommen **einmal**."""
    try:
        ergebnis = uebernahme.lauf(db, probe=False)
    except uebernahme.NichtBereit as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    audit.record(db, "uebernahme.gelaufen", actor=actor, request=request,
                 uebernommen=len(ergebnis["uebernommen"]),
                 gescheitert=len(ergebnis["gescheitert"]))
    db.commit()
    return ergebnis


@router.post("/uebernahme/zuruecknehmen", dependencies=[Depends(manage)])
def uebernahme_zurueck(body: dict, request: Request,
                       actor: User = Depends(current_user),
                       db: DbSession = Depends(get_db)) -> dict:
    """Ein einzelnes Konto wieder lokal machen.

    Der Rückweg, den man hoffentlich nie braucht. Er existiert, weil die
    Übernahme das Einzige im ganzen Umbau ist, das ein bestehendes Konto
    verändert — und weil ein Weg zurück, den es erst im Notfall zu erfinden
    gilt, kein Weg ist.

    Das Konto in Keycloak bleibt stehen und wird nur **deaktiviert**: Löschen
    wäre in einem fremden Realm nicht unsere Sache, und hier wäre es die
    Vernichtung des Beweises, dass es die Übernahme gab.
    """
    from ..security import hash_password, password_problem

    name = str(body.get("username") or "").strip().lower()
    passwort = str(body.get("password") or "")

    konto = db.scalar(select(User).where(User.username == name))
    if konto is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"„{name}“ gibt es nicht.")
    if konto.auth_provider != "keycloak":
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"„{name}“ ist gar kein übernommenes Konto.")

    problem = password_problem(passwort)
    if problem:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, problem)

    if konto.external_id:
        try:
            keycloak.konto_sperren(konto.external_id, True)
        except keycloak.KeycloakFehler:
            # Keycloak schweigt womöglich — und genau dann braucht man diesen
            # Weg. Das darf ihn nicht blockieren.
            pass

    konto.auth_provider = "local"
    konto.external_id = None
    konto.password_hash = hash_password(passwort)
    konto.must_change_password = True
    konto.token_epoch = (konto.token_epoch or 0) + 1

    audit.record(db, "uebernahme.zurueckgenommen", actor=actor, request=request,
                 konto=name)
    db.commit()
    return {"username": name, "auth_provider": konto.auth_provider}
