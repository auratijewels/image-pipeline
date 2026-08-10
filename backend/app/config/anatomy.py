"""Calibrated anatomical constants — the reference rulers for scale (§4 step C).

Every on-model composite is scaled by measuring a body span whose real-world size
we know, in pixels, then deriving pixels-per-mm. The accuracy of the whole product
is bounded by the accuracy of these constants, so they live in one file, are
documented, and are overridable per shot.

**Design note — why this deviates from §4 step C of the brief.**

The brief calibrates on earlobe height (≈19 mm). Two problems:

1. MediaPipe exposes no earlobe landmark. Neither the 478-point FaceLandmarker
   nor the removed FaceMesh has one — the face oval's outermost points sit at the
   tragion, not the lobe. Any earlobe measurement is inferred from surrounding
   geometry, i.e. estimated rather than measured.
2. Earlobe height varies roughly 15% across adults. The §10 acceptance criterion
   is ±8%. A ruler whose own population variance is nearly double the tolerance
   cannot meet that criterion however good the detector is.

So calibration and placement are separated, which the brief conflates:

- a CALIBRATION span, chosen for detection reliability and low population
  variance, used only to derive pixels-per-mm;
- a MOUNT ANCHOR, where the product is placed. Being a few pixels off here is a
  composition issue, not a scale error.

Interpupillary distance is the primary ruler: the most reliably detected span on
the face, and at ~4% variance it leaves real headroom under an 8% budget.
Bizygomatic width is measured independently as a cross-check — when two rulers
disagree beyond tolerance the detection is untrustworthy (head rotation, partial
occlusion, a bad frame) and the shot is rejected rather than silently mis-scaled.

The brief's 19 mm earlobe figure is still used, but as a *diagnostic*: we infer
the generated model's earlobe height from the IPD-derived scale and warn if it
is implausible. That surfaces a bad generation without letting it drive scale.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class MountPoint(StrEnum):
    """Where on the body a category is worn."""

    EARLOBE = "earlobe"
    NECK = "neck"
    RING_FINGER = "ring_finger"
    WRIST = "wrist"
    ANKLE = "ankle"


class Detector(StrEnum):
    FACE = "face"
    HAND = "hand"


# --- MediaPipe landmark indices ---------------------------------------------
# FaceLandmarker returns 478 points when the iris refinement is present (468
# base + 10 iris). Iris centres are the most stable eye reference available.

FACE_LEFT_IRIS = 468
FACE_RIGHT_IRIS = 473
# Eye corners, used to synthesise a pupil centre if a model without iris
# refinement returns only 468 points.
FACE_LEFT_EYE_CORNERS = (33, 133)
FACE_RIGHT_EYE_CORNERS = (362, 263)
# Face oval extremes, level with the tragion.
FACE_LEFT_TRAGION = 234
FACE_RIGHT_TRAGION = 454
# Jaw contour just below each ear — the lower bound of the earlobe estimate.
FACE_LEFT_BELOW_EAR = 93
FACE_RIGHT_BELOW_EAR = 323
# Base of the neck, approximated from the chin and jaw corners.
FACE_CHIN = 152
FACE_LEFT_JAW = 172
FACE_RIGHT_JAW = 397

# HandLandmarker returns 21 points.
HAND_INDEX_MCP = 5
HAND_PINKY_MCP = 17
HAND_RING_MCP = 13
HAND_RING_PIP = 14
HAND_WRIST = 0


@dataclass(frozen=True)
class CalibrationSpan:
    """A measurable distance between two landmarks, of known real-world size."""

    key: str
    label: str
    mm: float
    #: Population coefficient of variation, as a percentage. This is the error
    #: floor: no detector can calibrate more accurately than the ruler varies.
    variance_pct: float
    detector: Detector

    def px_per_mm(self, measured_px: float) -> float:
        return measured_px / self.mm


# Adult female averages — Aurati's primary model cohort.
IPD = CalibrationSpan("ipd", "Interpupillary distance", 62.0, 4.0, Detector.FACE)
FACE_WIDTH = CalibrationSpan("face_width", "Bizygomatic width", 128.0, 5.0, Detector.FACE)
PALM_WIDTH = CalibrationSpan("palm_width", "Palm width, index to pinky MCP", 78.0, 5.0, Detector.HAND)

#: Primary ruler per detector, and the independent span used to cross-check it.
PRIMARY_SPAN: dict[Detector, CalibrationSpan] = {
    Detector.FACE: IPD,
    Detector.HAND: PALM_WIDTH,
}
CROSSCHECK_SPAN: dict[Detector, CalibrationSpan | None] = {
    Detector.FACE: FACE_WIDTH,
    #: The hand has no second span that is both reliable and independent —
    #: every candidate shares the same MCP landmarks, so agreement would be
    #: circular and prove nothing.
    Detector.HAND: None,
}

#: Which detector and mount each product category needs.
CATEGORY_MOUNT: dict[str, MountPoint] = {
    "necklace": MountPoint.NECK,
    "earrings": MountPoint.EARLOBE,
    "ring": MountPoint.RING_FINGER,
    "bracelet": MountPoint.WRIST,
    "anklet": MountPoint.ANKLE,
    "set": MountPoint.NECK,
}

MOUNT_DETECTOR: dict[MountPoint, Detector] = {
    MountPoint.EARLOBE: Detector.FACE,
    MountPoint.NECK: Detector.FACE,
    MountPoint.RING_FINGER: Detector.HAND,
    MountPoint.WRIST: Detector.HAND,
    #: No dedicated ankle detector; the hand model is used on ankle framing as a
    #: fallback and flagged low-confidence.
    MountPoint.ANKLE: Detector.HAND,
}

# --- tolerances -------------------------------------------------------------

#: §10 acceptance: a composited product must measure within this percentage of
#: its true millimetre size.
SCALE_ACCEPTANCE_PCT = 8.0

#: How far the primary and cross-check rulers may disagree before the detection
#: is treated as unreliable. Set from the two rulers' combined variance — below
#: this, disagreement is expected population spread rather than a bad reading.
CROSSCHECK_TOLERANCE_PCT = 12.0

#: The brief's earlobe figure, kept as a diagnostic (see module docstring).
#: If a generated model's inferred earlobe falls outside this range, the scene
#: is anatomically odd and worth regenerating.
EARLOBE_NOMINAL_MM = 19.0
EARLOBE_PLAUSIBLE_MM = (12.0, 30.0)


def detector_for_category(category: str) -> Detector:
    return MOUNT_DETECTOR[CATEGORY_MOUNT[category.lower()]]


def mount_for_category(category: str) -> MountPoint:
    return CATEGORY_MOUNT[category.lower()]


def primary_span_for_category(category: str) -> CalibrationSpan:
    return PRIMARY_SPAN[detector_for_category(category)]
