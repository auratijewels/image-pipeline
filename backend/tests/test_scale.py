"""Scale arithmetic — the part of the system that guarantees §10.

No imagery and no models here, so these run in milliseconds and cover cases that
would be impractical to generate.
"""

from __future__ import annotations

import math

import pytest

from app.pipeline.scale import Axis, ScaleError, physical_extent_mm, plan, verify

# --- mapping dimensions onto the silhouette ---------------------------------


def test_earring_drop_is_the_full_height():
    e = physical_extent_mm("earrings", {"drop": 36, "width": 12})
    assert e.mm == 36
    assert e.axis is Axis.HEIGHT


def test_ring_inner_diameter_is_not_the_silhouette():
    """The bore is 18 mm but the cut-out spans the band on both sides."""
    e = physical_extent_mm("ring", {"inner_diameter": 18, "band_width": 2.5})
    assert e.mm == pytest.approx(23.0)  # 18 + 2 x 2.5
    assert e.axis is Axis.WIDTH


def test_bracelet_circumference_becomes_a_diameter():
    e = physical_extent_mm("bracelet", {"inner_circumference": 180, "width": 6})
    assert e.mm == pytest.approx(180 / math.pi + 12)
    assert e.axis is Axis.WIDTH


def test_necklace_and_set_use_pendant_drop():
    for cat in ("necklace", "set"):
        assert physical_extent_mm(cat, {"pendant_drop": 40, "pendant_width": 15}).mm == 40


def test_missing_dimension_names_what_is_missing():
    with pytest.raises(ScaleError, match="band_width"):
        physical_extent_mm("ring", {"inner_diameter": 18})


def test_unknown_category_is_rejected():
    with pytest.raises(ScaleError, match="No scale mapping"):
        physical_extent_mm("tiara", {"drop": 10})


@pytest.mark.parametrize("bad", [0, -5])
def test_non_positive_dimensions_are_rejected(bad):
    with pytest.raises(ScaleError, match="must be positive"):
        physical_extent_mm("earrings", {"drop": bad})


# --- planning ---------------------------------------------------------------


def test_plan_scales_a_cutout_to_true_size():
    """A 36 mm earring at 4 px/mm must end up 144 px tall."""
    p = plan("earrings", {"drop": 36}, px_per_mm=4.0, cutout_size=(200, 720))
    assert p.target_px == pytest.approx(144.0)
    assert p.source_px == 720
    assert p.factor == pytest.approx(0.2)


def test_plan_uses_width_for_rings_not_height():
    p = plan("ring", {"inner_diameter": 18, "band_width": 2}, px_per_mm=5.0, cutout_size=(400, 300))
    assert p.extent.axis is Axis.WIDTH
    assert p.source_px == 400
    assert p.target_px == pytest.approx(110.0)  # (18 + 4) x 5


def test_plan_rejects_impossible_calibration():
    with pytest.raises(ScaleError, match="px_per_mm"):
        plan("earrings", {"drop": 36}, px_per_mm=0, cutout_size=(100, 100))


# --- the acceptance check ---------------------------------------------------


def test_perfect_composite_passes():
    p = plan("earrings", {"drop": 36}, px_per_mm=4.0, cutout_size=(200, 720))
    check = verify(p, measured_px=144.0)
    assert check.passed
    assert check.error_pct == pytest.approx(0.0)
    assert check.measured_mm == pytest.approx(36.0)


@pytest.mark.parametrize(
    "measured_px,expected_pass",
    [
        (144.0, True),    # exact
        (152.0, True),    # +5.6%, inside tolerance
        (155.5, True),    # +7.99%, just inside
        (156.0, False),   # +8.3%, just outside
        (132.0, False),   # -8.3%, just outside
        (288.0, False),   # 2x too big, the classic try-on failure
    ],
)
def test_acceptance_boundary_is_enforced_at_8_percent(measured_px, expected_pass):
    p = plan("earrings", {"drop": 36}, px_per_mm=4.0, cutout_size=(200, 720))
    assert verify(p, measured_px).passed is expected_pass


def test_check_reports_millimetres_not_just_a_verdict():
    """The UI shows this string, so it has to be readable on its own."""
    p = plan("earrings", {"drop": 36}, px_per_mm=4.0, cutout_size=(200, 720))
    text = verify(p, measured_px=160.0).describe()
    assert "expected 36.0 mm" in text
    assert "measured 40.0 mm" in text
    assert "FAIL" in text


def test_empty_composite_is_an_error_not_a_failed_check():
    p = plan("earrings", {"drop": 36}, px_per_mm=4.0, cutout_size=(200, 720))
    with pytest.raises(ScaleError, match="zero extent"):
        verify(p, measured_px=0)


def test_scale_is_independent_of_source_resolution():
    """Same product, same scene, different cut-out resolution: same result."""
    targets = {
        plan("earrings", {"drop": 36}, 4.0, (w, h)).target_px
        for w, h in [(100, 360), (200, 720), (400, 1440)]
    }
    assert len(targets) == 1
