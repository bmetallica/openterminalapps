"""Rezepte verwalten (siehe ota/recipes.py)."""

from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from .. import audit, recipes as cook
from ..db import get_db
from ..deps import current_user, require_permission
from ..models import Recipe, User
from ..schemas import RecipeIn, RecipeOut, RecipePreviewIn

router = APIRouter(prefix="/api/admin/recipes", tags=["recipes"])
manage = require_permission("images.manage", "templates.manage")

SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def _slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return base[:64] or "rezept"


def _unique(db: DbSession, wanted: str, skip: uuid.UUID | None = None) -> str:
    slug, n = wanted, 2
    while True:
        clash = db.scalar(select(Recipe).where(Recipe.slug == slug))
        if clash is None or clash.id == skip:
            return slug
        slug, n = f"{wanted}-{n}", n + 1


@router.get("", response_model=list[RecipeOut])
def list_recipes(db: DbSession = Depends(get_db),
                 _: User = Depends(manage)) -> list[Recipe]:
    return list(db.scalars(
        select(Recipe).order_by(Recipe.is_builtin.desc(), Recipe.name)
    ).all())


@router.post("/preview", dependencies=[Depends(manage)])
def preview(body: RecipePreviewIn) -> dict:
    """Zeigt, was aus den Angaben wird — bevor irgendetwas gespeichert ist.

    Der Sinn der Fuehrung ist nicht, das Skript zu verstecken, sondern es
    nicht von Hand schreiben zu muessen. Wer sehen will, was passiert, sieht
    es hier; wer es anders will, schreibt darin weiter.
    """
    try:
        return {"script": cook.render(body.kind, body.params)}
    except cook.RecipeError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.post("", response_model=RecipeOut, status_code=status.HTTP_201_CREATED)
def create_recipe(body: RecipeIn, request: Request,
                  actor: User = Depends(manage),
                  db: DbSession = Depends(get_db)) -> Recipe:
    if body.kind not in cook.KINDS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unbekannte Art.")

    script = body.script.strip() or _render(body)
    if not script.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Ein Rezept ohne Schritte hat keinen Zweck.")

    recipe = Recipe(
        slug=_unique(db, _slugify(body.name)),
        name=body.name.strip(), glyph=body.glyph or "▢",
        why=body.why.strip(), kind=body.kind, params=body.params,
        script=script, is_builtin=False, created_by=actor.username,
    )
    db.add(recipe)
    audit.record(db, "recipe.created", actor=actor, object_type="recipe",
                 object_id=recipe.slug, request=request)
    db.commit()
    db.refresh(recipe)
    return recipe


@router.put("/{recipe_id}", response_model=RecipeOut)
def update_recipe(recipe_id: uuid.UUID, body: RecipeIn, request: Request,
                  actor: User = Depends(manage),
                  db: DbSession = Depends(get_db)) -> Recipe:
    recipe = db.get(Recipe, recipe_id)
    if not recipe:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rezept nicht gefunden")
    if recipe.is_builtin:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Mitgelieferte Rezepte lassen sich nicht ändern. Leg eine Kopie an "
            "und ändere die — dann bleibt das Original als Vergleich stehen.",
        )

    recipe.name = body.name.strip()
    recipe.glyph = body.glyph or "▢"
    recipe.why = body.why.strip()
    recipe.kind = body.kind
    recipe.params = body.params
    recipe.script = body.script.strip() or _render(body)
    recipe.slug = _unique(db, _slugify(recipe.name), skip=recipe.id)
    audit.record(db, "recipe.updated", actor=actor, object_type="recipe",
                 object_id=recipe.slug, request=request)
    db.commit()
    db.refresh(recipe)
    return recipe


@router.delete("/{recipe_id}")
def delete_recipe(recipe_id: uuid.UUID, request: Request,
                  actor: User = Depends(manage),
                  db: DbSession = Depends(get_db)) -> dict:
    recipe = db.get(Recipe, recipe_id)
    if not recipe:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rezept nicht gefunden")
    if recipe.is_builtin:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Mitgelieferte Rezepte lassen sich nicht löschen.")
    name = recipe.name
    db.delete(recipe)
    audit.record(db, "recipe.deleted", actor=actor, object_type="recipe",
                 object_id=recipe.slug, request=request, name=name)
    db.commit()
    return {"status": f"{name} gelöscht"}


def _render(body: RecipeIn) -> str:
    try:
        return cook.render(body.kind, body.params)
    except cook.RecipeError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
