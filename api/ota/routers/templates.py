from __future__ import annotations

import base64
import binascii
import hashlib
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from .. import agent_client, audit, icons
from ..db import get_db
from ..deps import current_user, require_permission
from ..models import (
    Group, OnceScript, Session as SessionModel, Template, TemplateApp,
    TemplateOverride, User,
)
from ..schemas import (
    AllocationOut, AppIn, OnceRunOut, OnceScriptIn, OnceScriptOut, OverrideIn,
    OverrideOut, TemplateIn, TemplateOut,
)
from ..security import effective_resources, user_can_see_app, user_can_see_template

router = APIRouter(prefix="/api/templates", tags=["templates"])
manage = require_permission("templates.manage")


def _slugify(value: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return s or "workspace"


def _out(tpl: Template, user: User | None = None) -> TemplateOut:
    data = TemplateOut.model_validate(tpl)
    data.group_ids = [g.id for g in tpl.groups]
    if user is not None:
        # Was der Nutzer nicht sehen darf, taucht hier gar nicht erst auf.
        # Der Start prueft es noch einmal — diese Liste ist Anzeige, nicht
        # Absicherung.
        data.apps = [
            a for a, orig in zip(data.apps, tpl.apps)
            if user_can_see_app(orig, user)
        ]
        cores, mem, _, _ = effective_resources(tpl, user)
        data.effective_cores = cores
        data.effective_memory_bytes = mem
    return data


@router.get("")
def list_templates(
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> list[TemplateOut]:
    """Admins sehen alles, alle anderen ausschliesslich Zugewiesenes.

    Die Einschraenkung passiert hier in der Abfrage, nicht im Frontend.
    """
    templates = db.scalars(select(Template).order_by(Template.friendly_name)).all()
    return [_out(t, user) for t in templates if user_can_see_template(t, user)]


def _maschine(body: TemplateIn, vorher: str = "selkies") -> str:
    """Welche Streaming-Maschine gilt — angegeben oder aus dem Image abgeleitet.

    Wer sie ausdrücklich setzt, bekommt sie. Wer nichts sagt, bekommt die,
    **die das Image mitbringt**: OTAs eigenes Basisimage meldet sich über
    `SELKIES_HOME`, Kasm-Images tun das nicht.

    Ohne diese Ableitung bekäme ein Arbeitsplatz auf einem Kasm-Image seit
    der Umstellung stillschweigend Selkies. Der Agent wartete dann neunzig
    Sekunden auf einen Port, den niemand öffnet, die Sitzung käme nie hoch,
    und in der Oberfläche stünde „Der Container-Dienst ist nicht erreichbar" —
    ein Satz, der auf etwas ganz anderes zeigt. Gemessen an der Prüfreihe:
    18 Fehlschläge, alle mit derselben Wurzel.
    """
    if body.stream_engine:
        return body.stream_engine
    erkannt = agent_client.image_engine(body.image_ref)
    return erkannt or vorher


@router.post("", dependencies=[Depends(manage)], status_code=status.HTTP_201_CREATED)
def create_template(
    body: TemplateIn,
    request: Request,
    actor: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> TemplateOut:
    slug = _slugify(body.friendly_name)
    if db.scalar(select(Template).where(Template.slug == slug)):
        slug = f"{slug}-{uuid.uuid4().hex[:6]}"

    daten = body.model_dump(exclude={"group_ids"})
    daten["stream_engine"] = _maschine(body)
    tpl = Template(slug=slug, **daten)
    tpl.groups = list(
        db.scalars(select(Group).where(Group.id.in_(body.group_ids or []))).all()
    )
    db.add(tpl)
    audit.record(db, "template.created", actor=actor, object_type="template",
                 object_id=slug, request=request, name=body.friendly_name)
    db.commit()
    return _out(tpl)


@router.get("/{template_id}")
def get_template(
    template_id: uuid.UUID,
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> TemplateOut:
    tpl = db.get(Template, template_id)
    if not tpl or not user_can_see_template(tpl, user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace nicht gefunden")
    return _out(tpl, user)


@router.put("/{template_id}", dependencies=[Depends(manage)])
def update_template(
    template_id: uuid.UUID,
    body: TemplateIn,
    request: Request,
    actor: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> TemplateOut:
    tpl = db.get(Template, template_id)
    if not tpl:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace nicht gefunden")

    daten = body.model_dump(exclude={"group_ids"})
    # Beim Ändern zählt der bisherige Wert als Rückfallebene: Wer die Maschine
    # nicht erwähnt, soll sie nicht verlieren.
    daten["stream_engine"] = _maschine(body, tpl.stream_engine)
    for key, value in daten.items():
        setattr(tpl, key, value)
    # Nur anfassen, wenn die Zuweisung mitgeschickt wurde. Siehe `TemplateIn`:
    # Ein PUT, das sie nicht erwaehnt, soll sie nicht loeschen.
    if body.group_ids is not None:
        tpl.groups = list(
            db.scalars(select(Group).where(Group.id.in_(body.group_ids))).all()
        )

    audit.record(db, "template.updated", actor=actor, object_type="template",
                 object_id=tpl.slug, request=request)
    db.commit()
    return _out(tpl)


@router.delete("/{template_id}", dependencies=[Depends(manage)])
def delete_template(
    template_id: uuid.UUID,
    request: Request,
    actor: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> dict[str, str]:
    tpl = db.get(Template, template_id)
    if not tpl:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace nicht gefunden")

    # Ein Workspace mit laufenden Sessions wird nicht weggezogen. Die Container
    # blieben sonst als Waisen zurueck, und ihre Nutzer saehen mitten in der
    # Arbeit eine Fehlerseite statt einer Erklaerung.
    live = db.scalars(select(SessionModel).where(
        SessionModel.template_id == tpl.id,
        SessionModel.status.in_(("starting", "running", "paused")),
    )).all()
    if live:
        who = ", ".join(sorted({s.user.username for s in live}))
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Hier läuft noch etwas: {who}. Beende die Sessions unter "
            "Betrieb, dann lässt sich der Workspace löschen.",
        )

    name = tpl.friendly_name
    db.delete(tpl)
    audit.record(db, "template.deleted", actor=actor, object_type="template",
                 object_id=tpl.slug, request=request, name=name)
    db.commit()
    return {"status": f"{name} gelöscht"}


# --------------------------------------------------------------------------
# Zuteilung je Nutzer (plan.md §5)
# --------------------------------------------------------------------------

@router.get("/{template_id}/allocations", dependencies=[Depends(manage)])
def allocations(
    template_id: uuid.UUID,
    db: DbSession = Depends(get_db),
) -> list[AllocationOut]:
    """Was fuer jeden erreichbaren Nutzer tatsaechlich gilt.

    Auch Nutzer ohne eigene Abweichung erscheinen — sonst muesste man raten,
    wen die Vorlage betrifft.
    """
    tpl = db.get(Template, template_id)
    if not tpl:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace nicht gefunden")

    group_ids = {g.id for g in tpl.groups}
    own = {o.target_id for o in tpl.overrides if o.scope == "user"}

    out: list[AllocationOut] = []
    for user in db.scalars(select(User).order_by(User.username)).all():
        if not group_ids & {g.id for g in user.groups}:
            continue
        cores, mem, cf, mf = effective_resources(tpl, user)
        out.append(AllocationOut(
            user_id=user.id, username=user.username,
            cores=cores, memory_bytes=mem,
            cores_from=cf, memory_from=mf,
            has_own_override=user.id in own,
        ))
    return out


@router.get("/{template_id}/overrides", dependencies=[Depends(manage)])
def list_overrides(
    template_id: uuid.UUID, db: DbSession = Depends(get_db)
) -> list[OverrideOut]:
    tpl = db.get(Template, template_id)
    if not tpl:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace nicht gefunden")
    return [OverrideOut.model_validate(o) for o in tpl.overrides]


@router.put("/{template_id}/overrides", dependencies=[Depends(manage)])
def set_override(
    template_id: uuid.UUID,
    body: OverrideIn,
    request: Request,
    actor: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> dict[str, str]:
    """Setzt oder entfernt eine Abweichung.

    Sind beide Werte None, wird die Abweichung geloescht — dann erbt der
    Nutzer wieder.
    """
    tpl = db.get(Template, template_id)
    if not tpl:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace nicht gefunden")
    if body.scope not in {"user", "group"}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "scope muss 'user' oder 'group' sein")

    existing = db.scalar(select(TemplateOverride).where(
        TemplateOverride.template_id == template_id,
        TemplateOverride.scope == body.scope,
        TemplateOverride.target_id == body.target_id,
    ))

    if body.cores is None and body.memory_bytes is None:
        if existing:
            db.delete(existing)
        audit.record(db, "override.cleared", actor=actor, object_type="template",
                     object_id=tpl.slug, request=request,
                     scope=body.scope, target=str(body.target_id))
        db.commit()
        return {"status": "Abweichung entfernt"}

    if existing:
        existing.cores = body.cores
        existing.memory_bytes = body.memory_bytes
    else:
        db.add(TemplateOverride(template_id=template_id, **body.model_dump()))

    audit.record(db, "override.set", actor=actor, object_type="template",
                 object_id=tpl.slug, request=request,
                 scope=body.scope, target=str(body.target_id),
                 cores=body.cores, memory_bytes=body.memory_bytes)
    db.commit()
    return {"status": "Abweichung gespeichert"}


# --------------------------------------------------------------------------
# App-Katalog des Arbeitsplatzes (plan.md §9.5)
# --------------------------------------------------------------------------

@router.get("/{template_id}/packages", dependencies=[Depends(manage)])
def check_packages(
    template_id: uuid.UUID,
    names: str = "",
    db: DbSession = Depends(get_db),
) -> list[dict]:
    """Kennt das Image dieser Vorlage diese Pakete?

    Gefragt wird, bevor gebaut wird. Ein Build dauert Minuten, und an einem
    Debian-Namen auf einem Ubuntu-Image (`firefox-esr`) scheitert er erst am
    Ende — mit einer Meldung, die in hundert Zeilen Protokoll steht.
    """
    tpl = db.get(Template, template_id)
    if not tpl:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace nicht gefunden")
    wanted = [n.strip() for n in names.split(",") if n.strip()]
    if not wanted:
        return []
    return agent_client.image_packages(tpl.image_ref, wanted)


@router.get("/{template_id}/apps/discover", dependencies=[Depends(manage)])
def discover_apps(
    template_id: uuid.UUID,
    db: DbSession = Depends(get_db),
) -> list[dict]:
    """Welche Anwendungen im Image dieser Vorlage installiert sind.

    Der Weg vom „Firefox einbauen" zum „Firefox im Dashboard" fuehrt sonst
    ueber drei Fragen, die niemand beantworten will: Wie heisst die
    Binaerdatei, wo liegt sie, und wie soll das Ding in der Oberflaeche
    heissen. Das steht alles in den .desktop-Dateien des Images.

    Zurueck kommt die Vereinigung aus Gefundenem und bereits Eingetragenem.
    `in_catalog` sagt, was schon im Arbeitsplatz angeboten wird; `missing`
    markiert Eintraege, die im Katalog stehen, aber im Image nicht mehr
    vorkommen — etwa nach einem Basiswechsel.
    """
    tpl = db.get(Template, template_id)
    if not tpl:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace nicht gefunden")

    found = agent_client.image_applications(tpl.image_ref)

    # Zuordnung ueber zwei Wege, weil beide vorkommen: Der Katalog kann eine
    # eigene Kennung tragen (`vscode`), waehrend die .desktop-Datei einen
    # anderen Namen hat (`visual-studio-code`). Was zaehlt, ist das Programm —
    # also auch der Name der Binaerdatei.
    known = {a.slug: a for a in tpl.apps}
    by_binary = {a.exec_cmd.rsplit("/", 1)[-1]: a for a in tpl.apps}

    out: list[dict] = []
    matched: set[str] = set()
    seen: set[str] = set()
    for entry in found:
        current = known.get(entry["slug"]) or by_binary.get(str(entry["binary"]))
        if current is not None:
            matched.add(current.slug)
            # Die Kennung des Katalogs behalten: An ihr haengt die
            # Displaynummer und damit die Traefik-Route.
            entry = {**entry, "slug": current.slug}
        # Zwei .desktop-Dateien koennen auf dasselbe Programm zeigen (Thunar
        # bringt eine fuer die Anwendung und eine fuer den Ordner-Handler mit).
        # Nach der Zuordnung faellt das zusammen — hier einmal reicht.
        if entry["slug"] in seen:
            continue
        seen.add(str(entry["slug"]))
        out.append({
            **entry,
            "in_catalog": current is not None,
            "is_enabled": current.is_enabled if current else False,
            "fixed_display": current.fixed_display if current else None,
            # Eine schon gesetzte Sichtbarkeit ueberlebt das Durchsehen. Sonst
            # waere jede Einschraenkung nach dem naechsten Build wieder weg.
            "group_ids": (current.group_ids or []) if current else [],
            "x_res": current.x_res if current else None,
            "y_res": current.y_res if current else None,
            "missing": False,
            # Name und Zeichen aus dem Katalog haben Vorrang: Wer sie
            # angepasst hat, will das nicht bei jedem Durchsehen verlieren.
            "name": current.name if current else entry["name"],
            "icon": current.icon if current else entry["icon"],
            # Das Symbol dagegen kommt **immer** frisch aus dem Image, solange
            # es dort eins gibt: Es ist keine Einstellung, sondern das, was
            # das Paket mitbringt — und nach einem Update sieht es womoeglich
            # anders aus. Nur wenn das Image keins hergibt, bleibt das schon
            # gespeicherte stehen.
            "icon_data": (icons.verkleinern(str(entry.get("icon_data") or ""))
                          or (current.icon_data if current else "") or ""),
        })

    for slug, app in known.items():
        if slug in matched:
            continue
        out.append({
            "slug": slug, "name": app.name, "icon": app.icon,
            "icon_data": app.icon_data or "",
            "exec_cmd": app.exec_cmd, "exec_args": app.exec_args,
            "categories": [], "needs_terminal": False,
            "binary": app.exec_cmd.rsplit("/", 1)[-1],
            "in_catalog": True, "is_enabled": app.is_enabled,
            "fixed_display": app.fixed_display, "missing": True,
            "group_ids": app.group_ids or [],
            "x_res": app.x_res, "y_res": app.y_res,
        })

    return sorted(out, key=lambda a: (a["missing"], str(a["name"]).lower()))


@router.get("/{template_id}/apps/{slug}/icon")
def app_icon(
    template_id: uuid.UUID,
    slug: str,
    request: Request,
    v: str = "",
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> Response:
    """Das Symbol einer Anwendung als Bild.

    Warum ein eigener Weg und nicht die Datenadresse im Katalog: Das Dashboard
    laedt die Vorlagen alle 15 Sekunden neu (siehe `AppOut.icon_url`). Als
    Adresse holt der Browser jedes Symbol **einmal** und legt es beiseite.

    Der Fingerabdruck steckt im Anhang `?v=`; er ist Teil der Adresse und
    damit Teil dessen, was der Browser sich merkt. Aendert sich das Symbol
    nach einem Image-Update, aendert sich die Adresse — und das alte kommt
    nicht mehr aus dem Zwischenspeicher. Deshalb darf hier lange
    zwischengespeichert werden, ohne dass jemand ein veraltetes Bild sieht.

    Sichtbar fuer jeden, der die Vorlage ueberhaupt sehen darf. Ein Symbol ist
    kein Geheimnis — aber die Liste der Anwendungen eines fremden
    Arbeitsplatzes ist eine Auskunft, und die gibt es hier so wenig wie
    anderswo.
    """
    tpl = db.get(Template, template_id)
    if not tpl or not user_can_see_template(tpl, user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nicht gefunden")

    app = next((a for a in tpl.apps if a.slug == slug), None)
    if app is None or not app.icon_data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kein Symbol hinterlegt")

    treffer = re.match(r"^data:(image/[a-z+]+);base64,(.+)$", app.icon_data, re.S)
    if not treffer:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kein Symbol hinterlegt")
    try:
        rohdaten = base64.b64decode(treffer.group(2))
    except (binascii.Error, ValueError):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kein Symbol hinterlegt") from None

    marke = hashlib.sha256(app.icon_data.encode("utf-8", "replace")).hexdigest()[:8]
    etag = f'"{marke}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag})

    return Response(
        content=rohdaten,
        media_type=treffer.group(1),
        headers={
            # Ein Tag, und ausdruecklich `private`: Das Symbol haengt an einer
            # Vorlage, die nicht jeder sehen darf — es hat in keinem
            # gemeinsamen Zwischenspeicher zu liegen.
            "Cache-Control": "private, max-age=86400",
            "ETag": etag,
        },
    )


@router.put("/{template_id}/apps", dependencies=[Depends(manage)])
def set_apps(
    template_id: uuid.UUID,
    body: list[AppIn],
    request: Request,
    actor: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> TemplateOut:
    """Ersetzt den App-Katalog einer Vorlage.

    Die Reihenfolge ist bedeutsam: Aus ihr leitet sich die Displaynummer ab,
    und die Traefik-Routen dafuer werden beim Containerstart auf Vorrat
    angelegt. Wer die Reihenfolge aendert, aendert die Displayzuordnung —
    laufende Sessions muessen dafuer neu gestartet werden.
    """
    tpl = db.get(Template, template_id)
    if not tpl:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace nicht gefunden")
    if tpl.mode != "workspace":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Ein App-Katalog ergibt nur beim Arbeitsplatz Sinn. "
            "Stelle die Betriebsart um, wenn du mehrere Anwendungen willst.",
        )

    seen: set[str] = set()
    for entry in body:
        if entry.slug in seen:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                f"Die Kennung {entry.slug} kommt doppelt vor.")
        seen.add(entry.slug)

    known_groups = set(db.scalars(select(Group.id)).all())

    # Die Symbole der bisherigen Eintraege merken. Der Katalog wird gleich
    # komplett ersetzt, und wer ihn speichert, ohne vorher das Image
    # durchgesehen zu haben, schickt keins mit — ohne diese Zeile waeren
    # danach alle Symbole weg.
    alte_symbole = {a.slug: (a.icon_data or "") for a in tpl.apps}

    tpl.apps.clear()
    db.flush()
    for order, entry in enumerate(body):
        fields = entry.model_dump()
        # JSONB nimmt keine UUID-Objekte. Und Gruppen, die es nicht gibt,
        # sollen gar nicht erst gespeichert werden — sonst steht in der
        # Oberfläche gleich wieder eine Auswahl, die niemand getroffen hat.
        fields["group_ids"] = [str(g) for g in fields.get("group_ids") or [] if g in known_groups]
        # Das Symbol kommt aus dem Browser und ist damit fremde Eingabe: Es
        # geht durch dieselbe Pruefung wie eines aus einem Image — richtiges
        # Format, kleine Kante, keine Verweise nach draussen. Was dabei
        # durchfaellt, wird still zu „kein Symbol"; die Oberflaeche zeigt dann
        # das Zeichen.
        fields["icon_data"] = (icons.verkleinern(fields.get("icon_data") or "")
                               or alte_symbole.get(entry.slug, ""))
        tpl.apps.append(TemplateApp(sort_order=order, **fields))

    audit.record(db, "template.apps_set", actor=actor, object_type="template",
                 object_id=tpl.slug, request=request, count=len(body))
    db.commit()
    db.refresh(tpl)
    return _out(tpl)


# --------------------------------------------------------------------------
# Einmal-Skripte
#
# Der Fall: Ein neues Golden Image bringt eine neue Fassung mit, und die
# braucht eine Aenderung im Zuhause — eine umgezogene Einstellungsdatei, ein
# neuer Pfad. Das Skeleton greift nicht mehr (das Zuhause ist nicht leer), das
# Startskript liefe bei jedem Start wieder. Also: einmal je Nutzer.
#
# Gebucht wird je Nutzer und Skript, nicht je Session. Ein neues Skript ist
# ein neuer Eintrag und laeuft wieder fuer alle.
# --------------------------------------------------------------------------

def _once_out(script: OnceScript) -> OnceScriptOut:
    daten = OnceScriptOut.model_validate(script)
    daten.ran_count = len(script.runs)
    daten.failed = [
        OnceRunOut(username=r.user.username, ran_at=r.ran_at,
                   exit_code=r.exit_code, output=r.output)
        for r in script.runs if r.exit_code != 0
    ]
    return daten


@router.get("/{template_id}/once", dependencies=[Depends(manage)])
def list_once(template_id: uuid.UUID,
              db: DbSession = Depends(get_db)) -> list[OnceScriptOut]:
    tpl = db.get(Template, template_id)
    if not tpl:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace nicht gefunden")
    return [_once_out(x) for x in tpl.once_scripts]


@router.post("/{template_id}/once", dependencies=[Depends(manage)],
             status_code=status.HTTP_201_CREATED)
def create_once(template_id: uuid.UUID, body: OnceScriptIn, request: Request,
                actor: User = Depends(current_user),
                db: DbSession = Depends(get_db)) -> OnceScriptOut:
    tpl = db.get(Template, template_id)
    if not tpl:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace nicht gefunden")

    script = OnceScript(template_id=tpl.id, **body.model_dump())
    db.add(script)
    audit.record(db, "once_script.created", actor=actor, object_type="template",
                 object_id=tpl.slug, request=request, name=body.name)
    db.commit()
    db.refresh(script)
    return _once_out(script)


@router.put("/{template_id}/once/{script_id}", dependencies=[Depends(manage)])
def update_once(template_id: uuid.UUID, script_id: uuid.UUID, body: OnceScriptIn,
                request: Request, actor: User = Depends(current_user),
                db: DbSession = Depends(get_db)) -> OnceScriptOut:
    script = db.get(OnceScript, script_id)
    if not script or script.template_id != template_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Skript nicht gefunden")

    # Der Text aendert sich, die Buchfuehrung bleibt: Wer es schon hatte,
    # bekommt es **nicht** noch einmal.
    #
    # Das ist die unbequeme, aber ehrliche Antwort. Ein Skript, das nach jeder
    # Korrektur an einem Tippfehler bei allen erneut liefe, waere keine
    # Einmal-Sache mehr, und niemand traute sich, es anzufassen. Wer den Lauf
    # wirklich wiederholen will, sagt das ausdruecklich — dafuer gibt es
    # „nochmal".
    for key, value in body.model_dump().items():
        setattr(script, key, value)
    audit.record(db, "once_script.updated", actor=actor, object_type="template",
                 object_id=str(script_id), request=request, name=body.name)
    db.commit()
    db.refresh(script)
    return _once_out(script)


@router.delete("/{template_id}/once/{script_id}", dependencies=[Depends(manage)])
def delete_once(template_id: uuid.UUID, script_id: uuid.UUID, request: Request,
                actor: User = Depends(current_user),
                db: DbSession = Depends(get_db)) -> dict:
    script = db.get(OnceScript, script_id)
    if not script or script.template_id != template_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Skript nicht gefunden")
    name = script.name
    db.delete(script)
    audit.record(db, "once_script.deleted", actor=actor, object_type="template",
                 object_id=str(script_id), request=request, name=name)
    db.commit()
    return {"status": "geloescht"}


@router.post("/{template_id}/once/{script_id}/again", dependencies=[Depends(manage)])
def run_once_again(template_id: uuid.UUID, script_id: uuid.UUID, request: Request,
                   nur_gescheiterte: bool = False,
                   actor: User = Depends(current_user),
                   db: DbSession = Depends(get_db)) -> dict:
    """Loescht die Buchfuehrung, damit es beim naechsten Start wieder laeuft.

    Ausgefuehrt wird hier nichts: Ein Einmal-Skript laeuft im Container, und
    der laeuft vielleicht gerade gar nicht. Was hier passiert, ist das
    Zuruecknehmen der Notiz „ist schon gelaufen" — beim naechsten Start jedes
    betroffenen Nutzers holt der Agent es dann nach.
    """
    script = db.get(OnceScript, script_id)
    if not script or script.template_id != template_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Skript nicht gefunden")

    betroffen = [r for r in script.runs
                 if not nur_gescheiterte or r.exit_code != 0]
    for lauf in betroffen:
        db.delete(lauf)
    audit.record(db, "once_script.reset", actor=actor, object_type="template",
                 object_id=str(script_id), request=request,
                 name=script.name, count=len(betroffen))
    db.commit()
    return {"status": "zurueckgesetzt", "count": len(betroffen)}
