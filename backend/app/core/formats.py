"""The output format matrix (§3).

Every generated image is exported to every format whose `applies_to` includes
its asset type. Generation always happens at the largest edge in the matrix and
downscales from there — we never upscale past the source.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OutputFormat:
    key: str
    purpose: str
    ratio: str
    width: int
    height: int

    @property
    def aspect(self) -> float:
        return self.width / self.height

    @property
    def filename_suffix(self) -> str:
        return f"{self.key}_{self.width}x{self.height}"


FORMATS: tuple[OutputFormat, ...] = (
    OutputFormat("shopify_product", "Shopify product image", "1:1", 2048, 2048),
    OutputFormat("shopify_lifestyle", "Shopify lifestyle", "4:5", 1600, 2000),
    OutputFormat("ig_square", "Instagram feed (square)", "1:1", 1080, 1080),
    OutputFormat("ig_portrait", "Instagram feed (portrait)", "4:5", 1080, 1350),
    OutputFormat("story_reel", "Instagram/FB Story & Reel cover", "9:16", 1080, 1920),
    OutputFormat("facebook_feed", "Facebook feed", "1.91:1", 1200, 630),
    OutputFormat("pinterest", "Pinterest", "2:3", 1000, 1500),
)

FORMATS_BY_KEY: dict[str, OutputFormat] = {f.key: f for f in FORMATS}

# Generate at this edge so every format downscales rather than upscales.
MASTER_LONG_EDGE = max(max(f.width, f.height) for f in FORMATS)
