"""Product CRUD and the five-slot angle upload."""

from __future__ import annotations

import io
from datetime import datetime, timezone

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from PIL import Image, UnidentifiedImageError
from pydantic import ValidationError

from app.core.store import DuplicateProductCode, ProductNotFound, get_store
from app.models.product import (
    Angle,
    Product,
    ProductCreate,
    ProductUpdate,
    UploadedAngle,
)

router = APIRouter(prefix="/products", tags=["products"])

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MIN_EDGE_PX = 512
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "TIFF"}
EXT_FOR_FORMAT = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp", "TIFF": ".tif"}


def _get(product_id: str) -> Product:
    try:
        return get_store().get(product_id)
    except ProductNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


# --- CRUD -------------------------------------------------------------------


@router.get("", response_model=list[Product])
def list_products() -> list[Product]:
    return get_store().list()


@router.post("", response_model=Product, status_code=status.HTTP_201_CREATED)
def create_product(payload: ProductCreate) -> Product:
    try:
        return get_store().create(payload)
    except DuplicateProductCode as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.get("/{product_id}", response_model=Product)
def get_product(product_id: str) -> Product:
    return _get(product_id)


@router.patch("/{product_id}", response_model=Product)
def update_product(product_id: str, payload: ProductUpdate) -> Product:
    try:
        return get_store().update(product_id, payload)
    except ProductNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, exc.errors()) from exc


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(product_id: str) -> None:
    try:
        get_store().delete(product_id)
    except ProductNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


# --- angles -----------------------------------------------------------------


@router.put("/{product_id}/angles/{angle}", response_model=Product)
async def upload_angle(product_id: str, angle: Angle, file: UploadFile = File(...)) -> Product:
    store = get_store()
    _get(product_id)

    raw = await file.read()
    if not raw:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty upload.")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"File is {len(raw) / 1e6:.1f} MB; limit is {MAX_UPLOAD_BYTES / 1e6:.0f} MB.",
        )

    # Decode rather than trust the extension: the cut-out stage needs a real
    # image, and failing here is far cheaper than failing mid-generation.
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Not a readable image: {exc}") from exc

    fmt = (img.format or "").upper()
    if fmt not in ALLOWED_FORMATS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Unsupported format {fmt or 'unknown'}. Use {', '.join(sorted(ALLOWED_FORMATS))}.",
        )
    if min(img.size) < MIN_EDGE_PX:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Image is {img.width}x{img.height}. Shortest edge must be at least "
            f"{MIN_EDGE_PX}px, or the source can't fill a 2048px Shopify export.",
        )

    dest_dir = store.upload_dir(product_id)
    for stale in dest_dir.glob(f"{angle.value}.*"):
        stale.unlink(missing_ok=True)
    dest = dest_dir / f"{angle.value}{EXT_FOR_FORMAT[fmt]}"
    dest.write_bytes(raw)

    uploaded = UploadedAngle(
        angle=angle,
        filename=file.filename or dest.name,
        stored_path=str(dest),
        width=img.width,
        height=img.height,
        bytes=len(raw),
        uploaded_at=datetime.now(timezone.utc),
    )
    return store.set_angle(product_id, angle, uploaded)


@router.delete("/{product_id}/angles/{angle}", response_model=Product)
def delete_angle(product_id: str, angle: Angle) -> Product:
    try:
        return get_store().clear_angle(product_id, angle)
    except ProductNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.get("/{product_id}/angles/{angle}/raw")
def get_angle_image(product_id: str, angle: Angle) -> FileResponse:
    product = _get(product_id)
    uploaded = product.angles.get(angle)
    if not uploaded:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No {angle.value} image uploaded.")
    return FileResponse(uploaded.stored_path)
