"""Calibrated anatomical constants — the reference rulers for scale (§4 step C).

Every on-model composite is scaled by measuring a body part whose real-world
size we know, in pixels, then deriving pixels-per-mm. These constants are the
"known size" half of that equation, so their accuracy directly bounds the
accuracy of every on-model shot. Values are adult averages from anthropometric
literature; each is overridable per shot in the UI.
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


@dataclass(frozen=True)
class AnatomyRuler:
    """A measurable span used to derive pixels-per-mm.

    `mm` is the real-world size of the span the landmark detector measures.
    `tolerance_pct` is how far a measured value may sit from the expected
    aspect before we treat the detection as unreliable and fall back.
    """

    mount: MountPoint
    span: str
    mm: float
    tolerance_pct: float = 15.0


# Adult female averages — Aurati's primary model cohort.
RULERS: dict[MountPoint, AnatomyRuler] = {
    MountPoint.EARLOBE: AnatomyRuler(MountPoint.EARLOBE, "earlobe height (intertragic notch to lobule base)", 19.0),
    MountPoint.NECK: AnatomyRuler(MountPoint.NECK, "base-of-neck width at clavicle", 120.0),
    MountPoint.RING_FINGER: AnatomyRuler(MountPoint.RING_FINGER, "ring finger width at proximal phalanx", 17.0),
    MountPoint.WRIST: AnatomyRuler(MountPoint.WRIST, "wrist width at styloid process", 55.0),
    MountPoint.ANKLE: AnatomyRuler(MountPoint.ANKLE, "ankle width at malleolus", 68.0),
}

# Which ruler each product category is measured against.
CATEGORY_MOUNT: dict[str, MountPoint] = {
    "necklace": MountPoint.NECK,
    "earrings": MountPoint.EARLOBE,
    "ring": MountPoint.RING_FINGER,
    "bracelet": MountPoint.WRIST,
    "anklet": MountPoint.ANKLE,
    "set": MountPoint.NECK,
}

# Acceptance criterion §10: measured size must land within ±8% of the true mm.
SCALE_ACCEPTANCE_PCT = 8.0


def ruler_for_category(category: str) -> AnatomyRuler:
    mount = CATEGORY_MOUNT[category.lower()]
    return RULERS[mount]
