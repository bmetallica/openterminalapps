"""Kasm-Registries einbinden und Einträge daraus übernehmen.

Der Wunsch dahinter: nicht jede Anwendung selbst bauen müssen. Kasm
veröffentlicht Kataloge mit fertigen Images — 86 allein im offiziellen —, und
die lassen sich in OTA anbieten, ohne dass jemand Image-Namen abschreibt.

**Ein Import lädt nichts herunter.** Er legt eine Vorlage an, mehr nicht. Das
Image kommt erst beim ersten Start oder wenn es jemand unter *Images* holt —
und bis dahin steht seine Grösse in der Oberfläche. Bei 9,7 GB ist das eine
Entscheidung und keine Nebensache.

**Eine Registry ist eine Vertrauensentscheidung.** Ihr Katalog trägt zwar eine
Signatur, aber der Schlüssel dafür liegt bei Kasm; OTA prüft sie nicht. Was
importiert wird, läuft anschliessend im eigenen Netz. Die Oberfläche sagt das,
statt es zu verschweigen.
"""

from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from .. import agent_client, audit
from ..db import get_db
from ..deps import current_user, require_permission
from ..models import Registry, RegistryEntry, Template, User
from ..schemas import RegistryEntryOut, RegistryImportIn, RegistryIn, RegistryOut

router = APIRouter(prefix="/api/admin/registries", tags=["registries"])
manage = require_permission("registries.manage", "templates.manage")

# Die drei, die Kasm selbst betreibt bzw. die verbreitet sind. Vorgeschlagen,
# nicht eingetragen: Wer eine Registry will, sagt es.
SUGGESTED = (
    {"name": "Kasm Technologies", "url": "https://registry.kasmweb.com"},
    {"name": "Kasm AI Images", "url": "https://ai.registry.kasmweb.com"},
    {"name": "LinuxServer.io", "url": "https://kasmregistry.linuxserver.io"},
)


def _slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return base[:60] or "import"


def _unique_slug(db: DbSession, wanted: str) -> str:
    slug, n = wanted, 2
    while db.scalar(select(Template).where(Template.slug == slug)) is not None:
        slug, n = f"{wanted}-{n}", n + 1
    return slug


def _out(r: Registry) -> RegistryOut:
    data = RegistryOut.model_validate(r)
    data.entry_count = len(r.entries)
    data.imported_count = sum(1 for e in r.entries if e.imported_template_id)
    return data


@router.get("/suggested", dependencies=[Depends(manage)])
def suggested() -> list[dict]:
    """Bekannte Registries als Vorschlag. Eingetragen wird keine von selbst."""
    return list(SUGGESTED)


@router.get("", response_model=list[RegistryOut])
def list_registries(db: DbSession = Depends(get_db),
                    _: User = Depends(manage)) -> list[RegistryOut]:
    rows = db.scalars(select(Registry).order_by(Registry.name)).all()
    return [_out(r) for r in rows]


@router.post("", response_model=RegistryOut, status_code=status.HTTP_201_CREATED)
def add_registry(body: RegistryIn, request: Request,
                 actor: User = Depends(manage),
                 db: DbSession = Depends(get_db)) -> RegistryOut:
    url = body.url.strip().rstrip("/")
    if db.scalar(select(Registry).where(Registry.url == url)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Diese Registry ist schon eingetragen.")

    # Erst lesen, dann anlegen: Eine Registry, deren Katalog sich nicht laden
    # laesst, in der Liste stehen zu haben, hilft niemandem.
    catalog = agent_client.registry_fetch(url, body.schema_version)

    registry = Registry(
        name=catalog["name"] or url, url=url,
        schema_version=body.schema_version,
        icon_url=catalog.get("icon_url"),
        is_enabled=True, auto_update=body.auto_update,
    )
    db.add(registry)
    db.flush()
    _store(db, registry, catalog)

    audit.record(db, "registry.added", actor=actor, object_type="registry",
                 object_id=url, request=request, entries=len(registry.entries))
    db.commit()
    db.refresh(registry)
    return _out(registry)


@router.post("/{registry_id}/refresh", response_model=RegistryOut)
def refresh(registry_id: uuid.UUID, request: Request,
            actor: User = Depends(manage),
            db: DbSession = Depends(get_db)) -> RegistryOut:
    registry = db.get(Registry, registry_id)
    if not registry:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Registry nicht gefunden")

    try:
        catalog = agent_client.registry_fetch(registry.url, registry.schema_version)
    except HTTPException as exc:
        # Den Fehler behalten statt ihn nur zu melden: Wer morgen in die Liste
        # schaut, soll sehen, dass diese Registry seit gestern klemmt.
        registry.fetch_error = str(exc.detail)[:500]
        db.commit()
        raise

    _store(db, registry, catalog)
    audit.record(db, "registry.refreshed", actor=actor, object_type="registry",
                 object_id=registry.url, request=request)
    db.commit()
    db.refresh(registry)
    return _out(registry)


@router.delete("/{registry_id}")
def remove(registry_id: uuid.UUID, request: Request,
           actor: User = Depends(manage),
           db: DbSession = Depends(get_db)) -> dict:
    registry = db.get(Registry, registry_id)
    if not registry:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Registry nicht gefunden")

    # Die Vorlagen bleiben. Sie stehen auf eigenen Füssen — der Katalog war
    # nur der Weg, wie sie entstanden sind.
    name = registry.name
    db.delete(registry)
    audit.record(db, "registry.removed", actor=actor, object_type="registry",
                 object_id=registry.url, request=request, name=name)
    db.commit()
    return {"status": f"{name} entfernt. Bereits übernommene Workspaces bleiben."}


@router.get("/{registry_id}/entries", response_model=list[RegistryEntryOut])
def entries(registry_id: uuid.UUID, db: DbSession = Depends(get_db),
            _: User = Depends(manage)) -> list[RegistryEntryOut]:
    registry = db.get(Registry, registry_id)
    if not registry:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Registry nicht gefunden")
    return [
        RegistryEntryOut.model_validate(e)
        for e in sorted(registry.entries, key=lambda x: x.friendly_name.lower())
    ]


@router.get("/{registry_id}/icon")
def icon(registry_id: uuid.UUID, sha: str, db: DbSession = Depends(get_db),
         _: User = Depends(manage)) -> Response:
    """Reicht das Symbol eines Eintrags durch.

    Nicht, weil es hübscher wäre, sondern weil die Inhaltsregel der Anwendung
    keine fremden Bildquellen zulässt (`img-src 'self'`). Die Alternative wäre,
    sie für jede eingetragene Registry aufzuweichen — für ein Symbol ein
    schlechter Tausch. So verlässt der Browser die eigene Herkunft nicht.
    """
    registry = db.get(Registry, registry_id)
    if not registry:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Registry nicht gefunden")
    entry = next((e for e in registry.entries if e.sha == sha), None)
    if entry is None or not entry.icon_url:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kein Symbol vorhanden")

    raw, kind = agent_client.registry_icon(entry.icon_url, registry.url)
    return Response(content=raw, media_type=kind,
                    headers={"Cache-Control": "public, max-age=86400"})


@router.post("/{registry_id}/import", response_model=dict)
def import_entry(registry_id: uuid.UUID, body: RegistryImportIn, request: Request,
                 actor: User = Depends(manage),
                 db: DbSession = Depends(get_db)) -> dict:
    """Macht aus einem Katalogeintrag eine Vorlage.

    Als `single_app`: Ein Kasm-Image bringt genau eine Anwendung mit und
    startet sie selbst. Ein Arbeitsplatz waere die falsche Betriebsart —
    dessen Startskript wird ueberdeckt, und dann startete gar nichts.
    """
    registry = db.get(Registry, registry_id)
    if not registry:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Registry nicht gefunden")

    entry = next((e for e in registry.entries if e.sha == body.sha), None)
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dieser Eintrag steht nicht im Katalog.")
    if entry.imported_template_id:
        existing = db.get(Template, entry.imported_template_id)
        if existing is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"„{entry.friendly_name}“ ist schon übernommen — als "
                f"„{existing.friendly_name}“.",
            )

    image = entry.image_ref
    if body.tag:
        if body.tag not in entry.available_tags:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "Diese Fassung steht für den Eintrag nicht zur Wahl.")
        image = f"{image.rsplit(':', 1)[0]}:{body.tag}"

    tpl = Template(
        slug=_unique_slug(db, _slugify(entry.friendly_name)),
        friendly_name=entry.friendly_name,
        description=entry.description[:500],
        icon="▢",
        categories=entry.categories,
        mode="single_app",
        image_ref=image,
        cores=body.cores, memory_bytes=body.memory_bytes,
        # Nicht sichtbar, bis jemand sie zuweist: Ein Import soll nicht
        # ungefragt auf den Dashboards aller Nutzer auftauchen.
        is_enabled=False,
        # Ein fremdes Image bekommt ein eigenes Zuhause. In das gemeinsame
        # Profil zu schreiben, waere ihm zu viel zugetraut.
        persistence_scope="template",
        source_registry_id=registry.id,
    )
    db.add(tpl)
    db.flush()
    entry.imported_template_id = tpl.id

    audit.record(db, "registry.imported", actor=actor, object_type="template",
                 object_id=tpl.slug, request=request,
                 registry=registry.name, image=image)
    db.commit()
    return {
        "template_id": str(tpl.id),
        "slug": tpl.slug,
        "image_ref": image,
        "status": (f"„{entry.friendly_name}“ übernommen. Der Workspace ist noch "
                   "abgeschaltet — weise ihn einer Gruppe zu und schalte ihn ein."),
    }


def _store(db: DbSession, registry: Registry, catalog: dict) -> None:
    """Schreibt den gelesenen Katalog in die Datenbank.

    Bestehende Eintraege werden aktualisiert statt ersetzt: An ihnen haengt,
    was daraus schon uebernommen wurde.
    """
    from datetime import datetime, timezone

    known = {e.sha: e for e in registry.entries}
    seen: set[str] = set()

    for item in catalog.get("entries", []):
        sha = item["sha"]
        seen.add(sha)
        entry = known.get(sha) or RegistryEntry(registry_id=registry.id, sha=sha)
        entry.friendly_name = item["friendly_name"]
        entry.description = item["description"]
        entry.categories = item["categories"]
        entry.architectures = item["architectures"]
        entry.icon_url = item["icon_url"]
        entry.image_ref = item["image_ref"]
        entry.available_tags = item["available_tags"]
        entry.uncompressed_size_mb = item["uncompressed_size_mb"]
        if sha not in known:
            db.add(entry)

    # Was aus dem Katalog verschwunden ist, fliegt raus — ausser es wurde
    # uebernommen. Dann bleibt der Eintrag als Herkunftsnachweis stehen.
    for sha, entry in known.items():
        if sha not in seen and not entry.imported_template_id:
            db.delete(entry)

    registry.name = catalog.get("name") or registry.name
    registry.icon_url = catalog.get("icon_url") or registry.icon_url
    registry.workspace_count = catalog.get("workspace_count") or 0
    registry.last_modified = catalog.get("modified")
    registry.last_fetched_at = datetime.now(timezone.utc)
    registry.fetch_error = None
