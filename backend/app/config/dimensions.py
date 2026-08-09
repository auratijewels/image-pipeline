"""Per-category dimension specs.

Dimensions are mandatory (§1) because they drive the whole scale pipeline, but
"the dimension" is not one number — a ring is defined by its inner diameter, an
earring by its drop. Exactly one field per category is marked `primary`: that is
the measurement composited against the anatomical ruler in §4 step D. The rest
are captured for prompt copy and for the size-check UI.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config.anatomy import CATEGORY_MOUNT


@dataclass(frozen=True)
class DimensionField:
    key: str
    label: str
    required: bool = True
    primary: bool = False
    hint: str = ""


CATEGORY_DIMENSIONS: dict[str, tuple[DimensionField, ...]] = {
    "necklace": (
        DimensionField("pendant_drop", "Pendant drop", primary=True,
                       hint="Top of bail to lowest point of the pendant."),
        DimensionField("pendant_width", "Pendant width"),
        DimensionField("chain_length", "Chain length", required=False,
                       hint="Full clasped length. Sets where the pendant sits."),
    ),
    "earrings": (
        DimensionField("drop", "Drop", primary=True,
                       hint="Top of the post/hook to the lowest point."),
        DimensionField("width", "Width at widest point"),
    ),
    "ring": (
        DimensionField("inner_diameter", "Inner diameter", primary=True,
                       hint="Not the ring size number — the actual bore in mm."),
        DimensionField("band_width", "Band width"),
        DimensionField("face_height", "Face / stone height", required=False),
    ),
    "bracelet": (
        DimensionField("inner_circumference", "Inner circumference", primary=True,
                       hint="Measured around the inside, clasped."),
        DimensionField("width", "Band width"),
    ),
    "anklet": (
        DimensionField("inner_circumference", "Inner circumference", primary=True),
        DimensionField("width", "Band width"),
    ),
    "set": (
        DimensionField("pendant_drop", "Necklace pendant drop", primary=True),
        DimensionField("pendant_width", "Necklace pendant width"),
        DimensionField("earring_drop", "Earring drop"),
        DimensionField("earring_width", "Earring width", required=False),
    ),
}

CATEGORIES: tuple[str, ...] = tuple(CATEGORY_DIMENSIONS)

# Every category must have a mount point, or the composite pipeline has no ruler.
assert set(CATEGORIES) == set(CATEGORY_MOUNT), "dimensions and anatomy disagree on categories"


def fields_for(category: str) -> tuple[DimensionField, ...]:
    return CATEGORY_DIMENSIONS[category.lower()]


def primary_field(category: str) -> DimensionField:
    """The measurement the on-model composite is scaled by."""
    for f in fields_for(category):
        if f.primary:
            return f
    raise KeyError(f"no primary dimension declared for {category!r}")


def required_keys(category: str) -> tuple[str, ...]:
    return tuple(f.key for f in fields_for(category) if f.required)


for _cat in CATEGORIES:
    # Fail at import, not mid-generation, if a category is misconfigured.
    primary_field(_cat)
