"""File-backed product store.

One JSON document per product under data/products/, uploads alongside under
data/uploads/<product_id>/. No database: the working set is a few dozen products
on one machine, and keeping outputs inspectable on disk is worth more here than
query power.
"""

from __future__ import annotations

import json
import re
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path

from app.config.settings import get_settings
from app.models.product import Angle, Product, ProductCreate, ProductUpdate, Status

_SLUG_RE = re.compile(r"[^a-z0-9]+")


class ProductNotFound(KeyError):
    def __init__(self, product_id: str):
        self.product_id = product_id
        super().__init__(f"No product with id {product_id!r}")


class DuplicateProductCode(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(f"A product with code {code!r} already exists.")


def _slug(value: str) -> str:
    return _SLUG_RE.sub("-", value.lower()).strip("-") or "product"


class ProductStore:
    def __init__(self, root: Path | None = None):
        s = get_settings()
        self.root = root or (s.data_dir / "products")
        self.uploads_root = s.uploads_dir
        self.root.mkdir(parents=True, exist_ok=True)
        self.uploads_root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    # --- paths -----------------------------------------------------------

    def _path(self, product_id: str) -> Path:
        return self.root / f"{product_id}.json"

    def upload_dir(self, product_id: str) -> Path:
        d = self.uploads_root / product_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    # --- read ------------------------------------------------------------

    def list(self) -> list[Product]:
        products = [self._load(p) for p in sorted(self.root.glob("*.json"))]
        return sorted(products, key=lambda p: p.created_at, reverse=True)

    def get(self, product_id: str) -> Product:
        path = self._path(product_id)
        if not path.exists():
            raise ProductNotFound(product_id)
        return self._load(path)

    @staticmethod
    def _load(path: Path) -> Product:
        return Product.model_validate_json(path.read_text(encoding="utf-8"))

    # --- write -----------------------------------------------------------

    def create(self, payload: ProductCreate) -> Product:
        with self._lock:
            if any(p.code == payload.code for p in self.list()):
                raise DuplicateProductCode(payload.code)
            product = Product(id=self._allocate_id(payload.code), **payload.model_dump())
            product.status = Status.READY if product.is_ready else Status.DRAFT
            return self._save(product)

    def _allocate_id(self, code: str) -> str:
        base = _slug(code)
        candidate, n = base, 2
        while self._path(candidate).exists():
            candidate, n = f"{base}-{n}", n + 1
        return candidate

    def update(self, product_id: str, payload: ProductUpdate) -> Product:
        with self._lock:
            product = self.get(product_id)
            changes = payload.model_dump(exclude_unset=True, exclude_none=True)
            if changes:
                # Re-validate through the model so dimension rules still apply
                # after a category change.
                product = Product(**{**product.model_dump(), **changes})
            product.status = self._recompute_status(product)
            return self._save(product)

    def delete(self, product_id: str) -> None:
        with self._lock:
            path = self._path(product_id)
            if not path.exists():
                raise ProductNotFound(product_id)
            path.unlink()
            shutil.rmtree(self.uploads_root / product_id, ignore_errors=True)

    # --- angles ----------------------------------------------------------

    def set_angle(self, product_id: str, angle: Angle, uploaded) -> Product:
        with self._lock:
            product = self.get(product_id)
            product.angles[angle] = uploaded
            product.status = self._recompute_status(product)
            return self._save(product)

    def clear_angle(self, product_id: str, angle: Angle) -> Product:
        with self._lock:
            product = self.get(product_id)
            existing = product.angles.pop(angle, None)
            if existing:
                Path(existing.stored_path).unlink(missing_ok=True)
            product.status = self._recompute_status(product)
            return self._save(product)

    # --- internals -------------------------------------------------------

    @staticmethod
    def _recompute_status(product: Product) -> Status:
        # Never downgrade a finished or in-flight generation just because the
        # user is editing metadata.
        if product.status in (Status.GENERATING, Status.COMPLETE, Status.FAILED):
            return product.status
        return Status.READY if product.is_ready else Status.DRAFT

    def _save(self, product: Product) -> Product:
        product.updated_at = datetime.now(timezone.utc)
        path = self._path(product.id)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(product.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(path)  # atomic — a crash mid-write can't corrupt the record
        return product


_store: ProductStore | None = None


def get_store() -> ProductStore:
    global _store
    if _store is None:
        _store = ProductStore()
    return _store
