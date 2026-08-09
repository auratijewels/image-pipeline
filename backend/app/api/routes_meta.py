"""Read-only metadata the frontend needs to render forms and galleries."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter

from app.config.anatomy import CATEGORY_MOUNT, RULERS, SCALE_ACCEPTANCE_PCT
from app.core.assets import ASSET_TYPES
from app.core.costs import get_ledger
from app.core.formats import FORMATS

router = APIRouter(tags=["meta"])


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
