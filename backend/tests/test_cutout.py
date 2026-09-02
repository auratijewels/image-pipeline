"""Cut-out tests.

The matte-refinement and caching logic is tested against a stubbed rembg, so
the suite stays fast and does not pull ~970 MB of model weights. A separate
test runs the real model, but only when sample photos are present — see
samples/README.md.
"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.pipeline import cutout as C

SAMPLES = Path(__file__).resolve().parents[2] / "samples"


# --- alpha refinement -------------------------------------------------------


def rgba(width=100, height=100) -> np.ndarray:
    return np.zeros((height, width, 4), dtype=np.uint8)


def test_speckle_is_removed_but_the_product_survives():
    img = rgba()
    img[20:80, 20:80, 3] = 255  # the product
    img[5:7, 5:7, 3] = 255      # matte noise on the backdrop

    out = C.refine_alpha(img.copy())

    assert out[50, 50, 3] > 200, "product body was erased"
    assert out[5, 5, 3] == 0, "speckle survived"


def test_pinholes_inside_the_product_are_closed():
    img = rgba()
    img[20:80, 20:80, 3] = 255
    img[50, 50, 3] = 0  # single-pixel hole, e.g. inside a stone

    out = C.refine_alpha(img.copy())

    assert out[50, 50, 3] > 200, "pinhole was not filled"


def test_thin_chains_are_not_severed():
    """The refinement must not erode: a chain is only a few pixels wide."""
    img = rgba()
    img[10:90, 48:52, 3] = 255  # 4px-wide vertical strand

    out = C.refine_alpha(img.copy())

    centre = out[10:90, 49, 3]
    assert (centre > 128).all(), "thin strand was broken by refinement"


def test_trim_crops_to_the_product_with_padding():
    img = rgba(200, 200)
    img[80:120, 90:110, 3] = 255

    out = C.trim_to_content(img, pad=8)

    assert out.shape[0] == 40 + 16
    assert out.shape[1] == 20 + 16


def test_trim_rejects_an_empty_matte():
    with pytest.raises(C.CutoutError, match="empty matte"):
        C.trim_to_content(rgba())


# --- caching and orchestration (rembg stubbed) ------------------------------


def source_image(tmp_path: Path, name="front.jpg", size=(600, 600)) -> Path:
    path = tmp_path / name
    Image.new("RGB", size, (210, 200, 180)).save(path)
    return path


def test_cutout_produces_a_real_alpha_channel(stub_rembg, tmp_path):
    src = source_image(tmp_path)
    res = C.cutout(src, "p1", "front")

    assert res.path.exists()
    with Image.open(res.path) as img:
        assert img.mode == "RGBA"
        alpha = np.array(img)[:, :, 3]
    # A cut-out with a uniform alpha channel is not a cut-out.
    assert alpha.min() == 0 and alpha.max() == 255
    assert res.looks_plausible


def test_cutout_is_cached_and_reused(stub_rembg, tmp_path):
    src = source_image(tmp_path)

    first = C.cutout(src, "p2", "front")
    second = C.cutout(src, "p2", "front")

    assert first.cached is False
    assert second.cached is True
    assert stub_rembg["n"] == 1, "cache did not prevent a second inference"


def test_reuploading_an_angle_invalidates_the_cache(stub_rembg, tmp_path):
    src = source_image(tmp_path)
    C.cutout(src, "p3", "front")

    # Same path, different bytes — as happens on re-upload.
    Image.new("RGB", (700, 700), (100, 90, 80)).save(src)
    again = C.cutout(src, "p3", "front")

    assert again.cached is False
    assert stub_rembg["n"] == 2


def test_force_bypasses_the_cache(stub_rembg, tmp_path):
    src = source_image(tmp_path)
    C.cutout(src, "p4", "front")
    forced = C.cutout(src, "p4", "front", force=True)

    assert forced.cached is False
    assert stub_rembg["n"] == 2


def test_missing_source_is_a_clear_error(stub_rembg, tmp_path):
    with pytest.raises(C.CutoutError, match="Source image missing"):
        C.cutout(tmp_path / "nope.jpg", "p5", "front")


def test_cutout_is_trimmed_to_the_product(stub_rembg, tmp_path):
    """Trim must not drift the edges — downstream mm scaling uses this extent."""
    src = source_image(tmp_path, size=(600, 600))
    res = C.cutout(src, "p6", "front")
    # Stub keeps a centred 300px square; trim adds 8px padding each side and
    # the halo curve must not expand the matte outward.
    assert res.width == 300 + 16
    assert res.height == 300 + 16


def test_coverage_reflects_the_original_frame_not_the_trimmed_output(stub_rembg, tmp_path):
    """A trimmed matte is foreground by definition, so coverage is pre-trim."""
    src = source_image(tmp_path, size=(600, 600))
    res = C.cutout(src, "p7", "front")
    assert 0.20 < res.coverage < 0.30, res.coverage


def test_cached_result_reports_the_same_coverage(stub_rembg, tmp_path):
    src = source_image(tmp_path, size=(600, 600))
    fresh = C.cutout(src, "p8", "front")
    cached = C.cutout(src, "p8", "front")
    assert cached.cached is True
    assert cached.coverage == pytest.approx(fresh.coverage)


# --- HTTP ------------------------------------------------------------------


def test_cutout_endpoints(client, stub_rembg, tmp_path):
    from tests.conftest import make_image

    pid = client.post(
        "/api/products",
        json={
            "code": "C001",
            "name": "Test Piece",
            "category": "earrings",
            "dimensions_mm": {"drop": 30, "width": 10},
        },
    ).json()["id"]

    client.put(
        f"/api/products/{pid}/angles/front",
        files={"file": ("front.jpg", make_image(800, 800), "image/jpeg")},
    )

    assert client.get(f"/api/products/{pid}/cutouts/front/raw").status_code == 404

    built = client.post(f"/api/products/{pid}/cutouts")
    assert built.status_code == 200
    body = built.json()
    assert body["errors"] == {}
    assert body["cutouts"]["front"]["plausible"] is True

    raw = client.get(f"/api/products/{pid}/cutouts/front/raw")
    assert raw.status_code == 200
    assert raw.headers["content-type"] == "image/png"

    assert client.get(f"/api/products/{pid}/cutouts").json() == {"front": True}


def test_building_cutouts_without_uploads_is_rejected(client, stub_rembg):
    pid = client.post(
        "/api/products",
        json={
            "code": "C002",
            "name": "No Angles",
            "category": "ring",
            "dimensions_mm": {"inner_diameter": 18, "band_width": 3},
        },
    ).json()["id"]

    res = client.post(f"/api/products/{pid}/cutouts")
    assert res.status_code == 400
    assert "No angles uploaded" in res.text


# --- real model, only when sample photos exist ------------------------------

sample_files = sorted(
    p for p in SAMPLES.glob("*") if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
)


@pytest.mark.skipif(not sample_files, reason="no photos in samples/ — see samples/README.md")
@pytest.mark.parametrize("src", sample_files, ids=lambda p: p.name)
def test_real_photos_produce_a_plausible_matte(src):
    """Runs the actual BiRefNet model. Slow, and downloads weights on first use."""
    res = C.cutout(src, "sample", src.stem, force=True)
    assert res.looks_plausible, (
        f"{src.name}: coverage {res.coverage:.3f} is implausible — "
        "the matte either collapsed or kept the background."
    )
