"""The asset-type registry (§2).

v1 ships seven image asset types. The registry is deliberately generic — a v2
video module registers here with `kind="video"` and the orchestrator, format
exporter and UI pick it up without refactoring.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class AssetKind(StrEnum):
    IMAGE = "image"
    VIDEO = "video"  # reserved for v2 — nothing registers as video in v1


class Pipeline(StrEnum):
    """How an asset is produced."""

    DIRECT = "direct"
    """Generate straight from the product cut-out — no human involved."""

    COMPOSITE = "composite"
    """Full hybrid pipeline (§4): generate scene, measure landmarks, scale and
    composite the real cut-out, harmonize. Used wherever a human body appears."""


@dataclass(frozen=True)
class AssetType:
    key: str
    label: str
    prompt_key: str
    native_ratio: str
    pipeline: Pipeline
    kind: AssetKind = AssetKind.IMAGE
    preferred_angles: tuple[str, ...] = ("front",)
    notes: str = ""
    formats: tuple[str, ...] = field(
        default=(
            "shopify_product",
            "shopify_lifestyle",
            "ig_square",
            "ig_portrait",
            "story_reel",
            "facebook_feed",
            "pinterest",
        )
    )


ASSET_TYPES: tuple[AssetType, ...] = (
    AssetType(
        key="white_hero",
        label="Catalog Photo — White Hero",
        prompt_key="white_hero",
        native_ratio="1:1",
        pipeline=Pipeline.DIRECT,
        preferred_angles=("front",),
        notes="Pure-white studio sweep, e-commerce grade.",
    ),
    AssetType(
        key="branded_backdrop",
        label="Catalog Photo — Branded Backdrop",
        prompt_key="branded_backdrop",
        native_ratio="1:1",
        pipeline=Pipeline.DIRECT,
        preferred_angles=("front", "left"),
        notes="Midnight-navy silk.",
    ),
    AssetType(
        key="macro_waterproof",
        label="Catalog Photo — Macro / Waterproof",
        prompt_key="macro_waterproof",
        native_ratio="1:1",
        pipeline=Pipeline.DIRECT,
        preferred_angles=("front", "extra"),
        notes="Droplets + ripple, the signature waterproof cue.",
    ),
    AssetType(
        key="on_model",
        label="Human-Worn Photo — On Model",
        prompt_key="on_model",
        native_ratio="4:5",
        pipeline=Pipeline.COMPOSITE,
        preferred_angles=("left", "right", "front"),
        notes="Scale-critical. Validated against the anatomy ruler at ±8%.",
    ),
    AssetType(
        key="skin_closeup",
        label="Human-Worn Photo — Skin Close-up",
        prompt_key="skin_closeup",
        native_ratio="4:5",
        pipeline=Pipeline.COMPOSITE,
        preferred_angles=("front", "left"),
        notes="Scale-critical. Macro on skin.",
    ),
    AssetType(
        key="flatlay",
        label="Instagram Post — Creative Flat-lay",
        prompt_key="flatlay",
        native_ratio="4:5",
        pipeline=Pipeline.DIRECT,
        preferred_angles=("front", "extra"),
        notes="Styled props, cream marble.",
    ),
    AssetType(
        key="signature_concept",
        label="Signature Concept — Hero Campaign",
        prompt_key="signature_concept",
        native_ratio="4:5",
        pipeline=Pipeline.DIRECT,
        preferred_angles=("front",),
        notes="One unique creative concept per product.",
    ),
)

ASSET_TYPES_BY_KEY: dict[str, AssetType] = {a.key: a for a in ASSET_TYPES}

SCALE_CRITICAL = tuple(a.key for a in ASSET_TYPES if a.pipeline is Pipeline.COMPOSITE)
