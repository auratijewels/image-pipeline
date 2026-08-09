"""Product domain model."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator

from app.config.dimensions import CATEGORIES, fields_for, primary_field, required_keys


class Category(StrEnum):
    NECKLACE = "necklace"
    EARRINGS = "earrings"
    RING = "ring"
    BRACELET = "bracelet"
    ANKLET = "anklet"
    SET = "set"


class Angle(StrEnum):
    FRONT = "front"
    BACK = "back"
    LEFT = "left"
    RIGHT = "right"
    EXTRA = "extra"


#: Front is the only angle the pipeline cannot proceed without.
REQUIRED_ANGLES: tuple[Angle, ...] = (Angle.FRONT,)

CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")


class Status(StrEnum):
    DRAFT = "draft"          # created, still missing uploads or dimensions
    READY = "ready"          # everything needed to generate is present
    GENERATING = "generating"
    COMPLETE = "complete"
    FAILED = "failed"


class UploadedAngle(BaseModel):
    angle: Angle
    filename: str
    stored_path: str
    width: int
    height: int
    bytes: int
    uploaded_at: datetime


class ProductBase(BaseModel):
    code: Annotated[str, Field(description="Aurati product code, e.g. E425")]
    name: Annotated[str, Field(min_length=1, max_length=120)]
    category: Category
    description: Annotated[str, Field(default="", max_length=600)]
    #: Real-world measurements in millimetres, keyed by DimensionField.key.
    dimensions_mm: dict[str, float] = Field(default_factory=dict)
    #: Optional creative brief for the signature concept asset.
    concept: str = ""

    @field_validator("code")
    @classmethod
    def _valid_code(cls, v: str) -> str:
        v = v.strip()
        if not CODE_RE.match(v):
            raise ValueError(
                "Code must be 1-32 chars, alphanumeric plus . _ -, and start alphanumeric."
            )
        return v.upper()

    @model_validator(mode="after")
    def _validate_dimensions(self):
        allowed = {f.key for f in fields_for(self.category)}
        unknown = set(self.dimensions_mm) - allowed
        if unknown:
            raise ValueError(
                f"Unknown dimension(s) for {self.category}: {sorted(unknown)}. Allowed: {sorted(allowed)}"
            )
        for key, value in self.dimensions_mm.items():
            if value <= 0:
                raise ValueError(f"Dimension {key} must be greater than 0 mm.")
            if value > 2000:
                raise ValueError(f"Dimension {key} = {value} mm looks wrong — millimetres, not microns.")
        return self

    # --- derived ---------------------------------------------------------

    @property
    def missing_dimensions(self) -> list[str]:
        return [k for k in required_keys(self.category) if k not in self.dimensions_mm]

    @computed_field
    @property
    def primary_dimension_key(self) -> str:
        return primary_field(self.category).key

    @computed_field
    @property
    def primary_mm(self) -> float | None:
        """The measurement the on-model composite is scaled by."""
        return self.dimensions_mm.get(self.primary_dimension_key)

    def dimensions_phrase(self) -> str:
        """Human-readable dimensions for prompt injection, e.g. '36 mm drop x 12 mm wide'."""
        if not self.dimensions_mm:
            return "unspecified dimensions"
        parts = [
            f"{self.dimensions_mm[f.key]:g} mm {f.label.lower()}"
            for f in fields_for(self.category)
            if f.key in self.dimensions_mm
        ]
        return ", ".join(parts)


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    """All fields optional; only what's supplied is changed."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    category: Category | None = None
    description: str | None = Field(default=None, max_length=600)
    dimensions_mm: dict[str, float] | None = None
    concept: str | None = None


class Product(ProductBase):
    id: str
    status: Status = Status.DRAFT
    angles: dict[Angle, UploadedAngle] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def missing_angles(self) -> list[str]:
        return [a.value for a in REQUIRED_ANGLES if a not in self.angles]

    @computed_field
    @property
    def blockers(self) -> list[str]:
        """Everything standing between this product and a Generate click.

        Serialised with the product so the UI can render the exact reason the
        Generate button is disabled, rather than a bare disabled state.
        """
        out: list[str] = []
        for key in self.missing_dimensions:
            label = next(f.label for f in fields_for(self.category) if f.key == key)
            out.append(f"Missing dimension: {label}")
        for angle in self.missing_angles:
            out.append(f"Missing required angle: {angle}")
        return out

    @computed_field
    @property
    def is_ready(self) -> bool:
        return not self.blockers


__all__ = [
    "Angle",
    "CATEGORIES",
    "Category",
    "Product",
    "ProductCreate",
    "ProductUpdate",
    "REQUIRED_ANGLES",
    "Status",
    "UploadedAngle",
]
