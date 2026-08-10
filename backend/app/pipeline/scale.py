"""Step D of the hybrid pipeline (§4): turn millimetres into pixels.

Pure arithmetic, no image operations, so the part of the system that actually
guarantees correct scale can be tested exhaustively without generating anything.

The subtlety this module exists to handle: a product's *primary dimension* is not
always the extent of its silhouette. An earring's drop is its height, so the
mapping is direct. A ring's inner diameter is the bore — the cut-out is wider
than that by twice the band. A bracelet is specified by inner circumference,
which is not a linear extent at all. Treating "36 mm" as "the cut-out is 36 mm
tall" is right for earrings and wrong for everything worn around something.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from app.config.anatomy import SCALE_ACCEPTANCE_PCT


class Axis(StrEnum):
    HEIGHT = "height"
    WIDTH = "width"


class ScaleError(ValueError):
    pass


@dataclass(frozen=True)
class PhysicalExtent:
    """The real-world size of the cut-out's bounding box, along one axis."""

    mm: float
    axis: Axis
    #: How it was derived, for the step log and for debugging a bad result.
    derivation: str


def physical_extent_mm(category: str, dims: dict[str, float]) -> PhysicalExtent:
    """Map a product's dimensions onto the silhouette extent the cut-out shows."""
    cat = category.lower()

    def need(key: str) -> float:
        if key not in dims:
            raise ScaleError(f"{cat} needs dimension {key!r} to compute scale; got {sorted(dims)}.")
        value = dims[key]
        if value <= 0:
            raise ScaleError(f"Dimension {key!r} must be positive, got {value}.")
        return value

    if cat == "earrings":
        drop = need("drop")
        return PhysicalExtent(drop, Axis.HEIGHT, f"drop {drop:g} mm is the full height")

    if cat in ("necklace", "set"):
        drop = need("pendant_drop")
        return PhysicalExtent(drop, Axis.HEIGHT, f"pendant drop {drop:g} mm is the full height")

    if cat == "ring":
        inner, band = need("inner_diameter"), need("band_width")
        outer = inner + 2 * band
        return PhysicalExtent(
            outer,
            Axis.WIDTH,
            f"outer diameter {outer:g} mm = inner {inner:g} + 2 x band {band:g}",
        )

    if cat in ("bracelet", "anklet"):
        circ, width = need("inner_circumference"), need("width")
        inner = circ / math.pi
        outer = inner + 2 * width
        return PhysicalExtent(
            outer,
            Axis.WIDTH,
            f"outer diameter {outer:g} mm = circumference {circ:g}/pi + 2 x width {width:g}",
        )

    raise ScaleError(f"No scale mapping defined for category {category!r}.")


@dataclass(frozen=True)
class ScalePlan:
    px_per_mm: float
    extent: PhysicalExtent
    #: What the cut-out's extent should measure once scaled.
    target_px: float
    #: What it measures now, before scaling.
    source_px: float

    @property
    def factor(self) -> float:
        return self.target_px / self.source_px

    def describe(self) -> str:
        return (
            f"{self.extent.derivation}; at {self.px_per_mm:.3f} px/mm that is "
            f"{self.target_px:.0f}px, scaling the cut-out by {self.factor:.3f}x"
        )


def plan(
    category: str,
    dims: dict[str, float],
    px_per_mm: float,
    cutout_size: tuple[int, int],
) -> ScalePlan:
    """Work out how much to resize a cut-out so it is physically correct."""
    if px_per_mm <= 0:
        raise ScaleError(f"px_per_mm must be positive, got {px_per_mm}.")

    extent = physical_extent_mm(category, dims)
    width, height = cutout_size
    source_px = height if extent.axis is Axis.HEIGHT else width
    if source_px <= 0:
        raise ScaleError(f"Cut-out has no {extent.axis.value} ({cutout_size}).")

    return ScalePlan(px_per_mm, extent, extent.mm * px_per_mm, float(source_px))


@dataclass(frozen=True)
class ScaleCheck:
    """The §10 acceptance check, run against the finished composite."""

    expected_mm: float
    measured_mm: float
    error_pct: float
    passed: bool
    tolerance_pct: float = SCALE_ACCEPTANCE_PCT

    def describe(self) -> str:
        verdict = "pass" if self.passed else "FAIL"
        return (
            f"{verdict}: expected {self.expected_mm:.1f} mm, measured "
            f"{self.measured_mm:.1f} mm ({self.error_pct:+.1f}%, tolerance "
            f"±{self.tolerance_pct:.0f}%)"
        )


def verify(plan_: ScalePlan, measured_px: float, tolerance_pct: float = SCALE_ACCEPTANCE_PCT) -> ScaleCheck:
    """Measure the composited product back against its true size.

    This is the §10 acceptance criterion. It runs on the actual output rather
    than on the intended transform, so it catches rounding, rotation-bounding
    and cropping errors that the plan alone cannot.
    """
    if measured_px <= 0:
        raise ScaleError("Composited product has zero extent — nothing was placed.")

    measured_mm = measured_px / plan_.px_per_mm
    expected_mm = plan_.extent.mm
    error_pct = (measured_mm - expected_mm) / expected_mm * 100
    return ScaleCheck(
        expected_mm=expected_mm,
        measured_mm=measured_mm,
        error_pct=error_pct,
        passed=abs(error_pct) <= tolerance_pct,
        tolerance_pct=tolerance_pct,
    )
