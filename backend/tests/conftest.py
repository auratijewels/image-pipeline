"""Test fixtures.

Storage roots are redirected to a temp directory *before* anything imports
settings, so tests never touch the real data/ or outputs/ trees.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="aurati-test-"))
os.environ["DATA_DIR"] = str(_TMP / "data")
os.environ["OUTPUT_DIR"] = str(_TMP / "outputs")
os.environ["IMAGE_PROVIDER"] = "dryrun"
os.environ["GOOGLE_API_KEY"] = ""

import io  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402


@pytest.fixture(scope="session")
def client() -> TestClient:
    from app.main import app

    return TestClient(app)


@pytest.fixture(autouse=True)
def _clean_products():
    """Each test starts with an empty store."""
    from app.core.store import get_store

    store = get_store()
    for product in store.list():
        store.delete(product.id)
    yield


def make_image(width: int = 1200, height: int = 1200, fmt: str = "JPEG") -> bytes:
    img = Image.new("RGB", (width, height), (200, 190, 170))
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()
