"""Cut-out generation and preview (§4 step A)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from app.core.store import ProductNotFound, get_store
from app.models.product import Angle
from app.pipeline.cutout import CutoutError, cutout_async, cutout_path

log = logging.getLogger(__name__)

router = APIRouter(prefix="/products/{product_id}/cutouts", tags=["cutouts"])


def _product(product_id: str):
    try:
        return get_store().get(product_id)
    except ProductNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.post("")
async def build_cutouts(product_id: str, force: bool = False) -> dict:
    """Cut out every uploaded angle.

    Returns per-angle results rather than failing the whole batch on one bad
    image: a poor matte on the 'extra' angle should not block the hero.
    """
    product = _product(product_id)
    if not product.angles:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No angles uploaded yet.")

    results, errors = {}, {}
    for angle, uploaded in product.angles.items():
        try:
            res = await cutout_async(uploaded.stored_path, product_id, angle.value, force=force)
            results[angle.value] = {
                "width": res.width,
                "height": res.height,
                "coverage": round(res.coverage, 4),
                "cached": res.cached,
                "plausible": res.looks_plausible,
            }
        except CutoutError as exc:
            log.warning("Cut-out failed for %s/%s: %s", product_id, angle.value, exc)
            errors[angle.value] = str(exc)

    if not results:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, {"errors": errors})
    return {"cutouts": results, "errors": errors}


@router.get("")
def list_cutouts(product_id: str) -> dict:
    product = _product(product_id)
    return {
        angle.value: cutout_path(product_id, angle.value).exists() for angle in product.angles
    }


@router.get("/{angle}/raw")
def get_cutout_image(product_id: str, angle: Angle) -> FileResponse:
    _product(product_id)
    path = cutout_path(product_id, angle.value)
    if not path.exists():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"No cut-out for {angle.value} yet. POST to this product's /cutouts first.",
        )
    return FileResponse(path, media_type="image/png")
