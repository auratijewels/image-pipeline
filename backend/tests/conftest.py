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
def client():
    """A TestClient used as a context manager.

    This matters for generation tests: entering the context starts a portal
    whose event loop persists across requests. Without it, Starlette tears the
    loop down after each request, so the background task started by
    POST /generate is orphaned the moment the response returns and the job
    hangs forever at its first await.
    """
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


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


@pytest.fixture
def stub_rembg(monkeypatch):
    """Replace rembg inference with a deterministic fake, and count calls.

    Keeps the suite fast and avoids pulling ~970 MB of BiRefNet weights. The
    fake keeps a centred quarter of the frame, roughly what a real product photo
    yields — a matte that keeps almost everything is indistinguishable from one
    that failed to remove the background at all.
    """
    import numpy as np

    from app.pipeline import cutout as C

    calls = {"n": 0}

    def fake_remove(data, session=None):
        calls["n"] += 1
        with Image.open(io.BytesIO(data)) as src:
            h, w = src.height, src.width
        arr = np.zeros((h, w, 4), dtype=np.uint8)
        arr[h // 4 : 3 * h // 4, w // 4 : 3 * w // 4] = [180, 150, 90, 255]
        buf = io.BytesIO()
        Image.fromarray(arr, mode="RGBA").save(buf, format="PNG")
        return buf.getvalue()

    import rembg

    monkeypatch.setattr(rembg, "remove", fake_remove)
    monkeypatch.setattr(C, "get_session", lambda: object())
    return calls
