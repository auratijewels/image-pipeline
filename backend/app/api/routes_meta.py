"""Read-only metadata the frontend needs to render forms and galleries."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter

from app.config.anatomy import CATEGORY_MOUNT, RULERS, SCALE_ACCEPTANCE_PCT
from app.config.dimensions import CATEGORIES, CATEGORY_DIMENSIONS
from app.core.assets import ASSET_TYPES
from app.core.costs import get_ledger
from app.core.formats import FORMATS
from app.models.product import Angle, REQUIRED_ANGLES

router = APIRouter(tags=["meta"])


@router.get("/categories")
def categories() -> list[dict]:
    """Category list plus the dimension fields each one requires.

    The upload form is driven entirely by this — adding a category means
    editing config/dimensions.py, not the frontend.
    """
    return [
        {
            "key": key,
            "label": key.title(),
            "mount": CATEGORY_MOUNT[key].value,
            "dimensions": [asdict(f) for f in CATEGORY_DIMENSIONS[key]],
        }
        for key in CATEGORIES
    ]


@router.get("/angles")
def angles() -> dict:
    return {
        "all": [a.value for a in Angle],
        "required": [a.value for a in REQUIRED_ANGLES],
    }


@router.get("/asset-types")
def asset_types() -> list[dict]:
    return [asdict(a) | {"pipeline": a.pipeline.value, "kind": a.kind.value} for a in ASSET_TYPES]


@router.get("/formats")
def formats() -> list[dict]:
    return [asdict(f) for f in FORMATS]


@router.get("/anatomy")
def anatomy() -> dict:
    return {
        "rulers": {k.value: asdict(v) | {"mount": v.mount.value} for k, v in RULERS.items()},
        "category_mount": {k: v.value for k, v in CATEGORY_MOUNT.items()},
        "acceptance_pct": SCALE_ACCEPTANCE_PCT,
    }


@router.get("/costs")
def costs() -> dict:
    ledger = get_ledger()
    return {"total_inr": round(ledger.total_inr(), 2), "calls": len(ledger.entries())}
