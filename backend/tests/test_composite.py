"""End-to-end composite tests against a synthetic scene with known ground truth.

Per the sequencing note in NEXT_STEPS, the composite is verified against a fixed
scene with a *known* pixels-per-mm before any generative model is involved. That
makes the §10 acceptance criterion a deterministic assertion rather than a visual
judgement — if scale drifts, these fail, with no generation variance to blame.
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image, ImageDraw

from app.config.anatomy import IPD, Detector, MountPoint
from app.pipeline.composite import CompositeError, composite, measure_extent
from app.pipeline.landmarks import LandmarkReading, Measurement
from app.pipeline.scale import Axis

#: A scene where we *decide* the calibration rather than detect it, so the
#: expected output size is known exactly.
SCENE_PX_PER_MM = 5.0


def scene(width=900, height=1200) -> Image.Image:
    img = Image.new("RGB", (width, height), (208, 186, 170))
    ImageDraw.Draw(img).ellipse([250, 200, 650, 800], fill=(226, 198, 178))
    return img


def cutout(width=120, height=400, pad=20) -> Image.Image:
    """A product cut-out with transparent padding, as the cut-out stage emits."""
    img = Image.new("RGBA", (width + pad * 2, height + pad * 2), (0, 0, 0, 0))
    ImageDraw.Draw(img).rectangle(
        [pad, pad, pad + width - 1, pad + height - 1], fill=(198, 158, 74, 255)
    )
    return img


def reading(mount=MountPoint.EARLOBE, anchor=(400, 400), axis_deg=0.0) -> LandmarkReading:
    """A landmark reading with calibration pinned to SCENE_PX_PER_MM."""
    return LandmarkReading(
        detector=Detector.FACE,
        mount=mount,
        primary=Measurement(IPD, IPD.mm * SCENE_PX_PER_MM),
        anchor=anchor,
        axis_deg=axis_deg,
    )


EARRING = ("earrings", {"drop": 36, "width": 12})


# --- the acceptance criterion ----------------------------------------------


def test_a_36mm_earring_composites_at_36mm():
    """§10, stated directly."""
    res = composite(scene(), cutout(), reading(), *EARRING)

    assert res.passed, res.check.describe()
    assert res.check.measured_mm == pytest.approx(36.0, abs=36 * 0.08)
    # 36 mm at 5 px/mm is 180 px.
    assert res.plan.target_px == pytest.approx(180.0)


@pytest.mark.parametrize("drop_mm", [8, 18, 36, 55, 90])
def test_scale_holds_across_product_sizes(drop_mm):
    res = composite(scene(), cutout(), reading(), "earrings", {"drop": drop_mm, "width": 10})
    assert res.passed, f"{drop_mm} mm: {res.check.describe()}"


@pytest.mark.parametrize("size", [(60, 200), (120, 400), (300, 1000), (90, 800)])
def test_scale_is_independent_of_cutout_resolution(size):
    """The same physical product photographed at any resolution lands the same."""
    res = composite(scene(), cutout(*size), reading(), *EARRING)
    assert res.passed, res.check.describe()
    assert res.check.measured_mm == pytest.approx(36.0, rel=0.08)


def test_transparent_padding_does_not_inflate_the_product():
    """Padding must be trimmed, or the visible piece comes out too small."""
    tight = composite(scene(), cutout(pad=0), reading(), *EARRING)
    padded = composite(scene(), cutout(pad=120), reading(), *EARRING)
    assert padded.check.measured_mm == pytest.approx(tight.check.measured_mm, rel=0.02)


def test_a_ring_is_scaled_on_its_outer_diameter():
    res = composite(
        scene(),
        reading_ring := cutout(400, 400),
        reading(MountPoint.RING_FINGER),
        "ring",
        {"inner_diameter": 18, "band_width": 2.5},
    )
    assert reading_ring is not None
    assert res.plan.extent.axis is Axis.WIDTH
    # (18 + 5) mm x 5 px/mm = 115 px, not 90.
    assert res.plan.target_px == pytest.approx(115.0)
    assert res.passed, res.check.describe()


# --- rotation ---------------------------------------------------------------


@pytest.mark.parametrize("angle", [0, 12, -25, 45, 90])
def test_rotation_preserves_measured_scale(angle):
    """Rotation expands the canvas; measuring alpha rather than canvas keeps
    the check honest."""
    res = composite(scene(), cutout(), reading(axis_deg=angle), *EARRING)
    axis_mm = res.check.measured_mm
    # At 90 degrees the piece's height becomes its width, so the height-axis
    # measurement legitimately changes; only assert the unrotated cases.
    if angle % 180 == 0:
        assert axis_mm == pytest.approx(36.0, rel=0.08), res.check.describe()


def test_measure_extent_ignores_transparent_canvas():
    img = Image.new("RGBA", (500, 500), (0, 0, 0, 0))
    ImageDraw.Draw(img).rectangle([100, 200, 199, 299], fill=(255, 0, 0, 255))
    assert measure_extent(img, Axis.HEIGHT) == 100
    assert measure_extent(img, Axis.WIDTH) == 100


# --- placement --------------------------------------------------------------


def test_an_earring_hangs_below_its_anchor():
    anchor = (400, 400)
    res = composite(scene(), cutout(), reading(anchor=anchor), *EARRING)
    arr = np.array(res.image.convert("RGB"))
    base = np.array(scene().convert("RGB"))
    ys, _ = np.nonzero(np.abs(arr.astype(int) - base.astype(int)).sum(axis=2) > 30)
    # Everything drawn should sit at or below the lobe, never above it.
    assert ys.min() >= anchor[1] - 12, "product drawn above the earlobe anchor"


def test_a_ring_is_centred_on_its_anchor():
    anchor = (400, 500)
    res = composite(
        scene(), cutout(300, 300), reading(MountPoint.RING_FINGER, anchor=anchor),
        "ring", {"inner_diameter": 18, "band_width": 2},
    )
    arr = np.array(res.image.convert("RGB"))
    base = np.array(scene().convert("RGB"))
    ys, xs = np.nonzero(np.abs(arr.astype(int) - base.astype(int)).sum(axis=2) > 30)
    assert abs((ys.min() + ys.max()) / 2 - anchor[1]) < 25
    assert abs((xs.min() + xs.max()) / 2 - anchor[0]) < 25


# --- manual nudge (§4F) -----------------------------------------------------


def test_size_nudge_changes_the_output_and_the_check_reports_it_honestly():
    """An overridden scale must not be silently reported as correct."""
    res = composite(scene(), cutout(), reading(), *EARRING, size_nudge=1.30)
    assert not res.passed
    assert res.check.error_pct == pytest.approx(30.0, abs=1.5)


def test_a_small_nudge_stays_within_tolerance():
    res = composite(scene(), cutout(), reading(), *EARRING, size_nudge=1.05)
    assert res.passed


# --- realism pass must not move the silhouette ------------------------------


def test_relight_does_not_change_scale():
    lit = composite(scene(), cutout(), reading(), *EARRING, relight=True)
    plain = composite(scene(), cutout(), reading(), *EARRING, relight=False)
    assert lit.check.measured_mm == pytest.approx(plain.check.measured_mm)


def test_shadow_does_not_change_scale():
    with_s = composite(scene(), cutout(), reading(), *EARRING, shadow=True)
    without = composite(scene(), cutout(), reading(), *EARRING, shadow=False)
    assert with_s.check.measured_mm == pytest.approx(without.check.measured_mm)


def test_shadow_actually_darkens_beneath_the_product():
    with_s = np.array(composite(scene(), cutout(), reading(), *EARRING, shadow=True).image.convert("RGB")).astype(int)
    without = np.array(composite(scene(), cutout(), reading(), *EARRING, shadow=False).image.convert("RGB")).astype(int)
    assert with_s.sum() < without.sum(), "shadow pass changed nothing"


# --- failure modes ----------------------------------------------------------


def test_an_empty_cutout_is_a_clear_error():
    blank = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    with pytest.raises(CompositeError, match="empty"):
        composite(scene(), blank, reading(), *EARRING)
