"""Read-only metadata the frontend needs to render forms and galleries."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter

from app.config.anatomy import (
    CATEGORY_MOUNT,
    CROSSCHECK_SPAN,
    CROSSCHECK_TOLERANCE_PCT,
    MOUNT_DETECTOR,
    PRIMARY_SPAN,
    SCALE_ACCEPTANCE_PCT,
)
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
    """The rulers scale is derived from, and the tolerances applied to them."""

    def span(s) -> dict:
        return asdict(s) | {"detector": s.detector.value}

    return {
        "primary_spans": {d.value: span(s) for d, s in PRIMARY_SPAN.items()},
        "crosscheck_spans": {
            d.value: (span(s) if s else None) for d, s in CROSSCHECK_SPAN.items()
        },
        "category_mount": {k: v.value for k, v in CATEGORY_MOUNT.items()},
        "mount_detector": {m.value: d.value for m, d in MOUNT_DETECTOR.items()},
        "acceptance_pct": SCALE_ACCEPTANCE_PCT,
        "crosscheck_tolerance_pct": CROSSCHECK_TOLERANCE_PCT,
    }


@router.get("/costs")
def costs() -> dict:
    ledger = get_ledger()
    return {"total_inr": round(ledger.total_inr(), 2), "calls": len(ledger.entries())}
