"""Zero-cost provider for UI work and tests (§6 "dry-run mode").

Returns a deterministic placeholder image instead of calling any API, so the
whole orchestration path — progress log, format export, ZIP packaging — can be
exercised without spending credits. Placeholders are labelled and tinted per
prompt hash so a gallery of them is still visually distinguishable.
"""

from __future__ import annotations

import hashlib
import io
import textwrap

from PIL import Image, ImageDraw

from app.providers.base import (
    GenerationRequest,
    GenerationResult,
    ImageProvider,
    ReferenceImage,
)

RATIO_SIZES = {
    "1:1": (1024, 1024),
    "4:5": (1024, 1280),
    "9:16": (1024, 1820),
    "3:4": (1024, 1365),
    "2:3": (1024, 1536),
    "16:9": (1820, 1024),
    "3:2": (1536, 1024),
}

AURATI_NAVY = (41, 53, 79)
AURATI_PLATINUM = (234, 237, 243)


class DryRunProvider(ImageProvider):
    name = "dryrun"

    @property
    def model(self) -> str:
        return "dryrun-placeholder"

    def estimate_usd(self, req: GenerationRequest) -> float:
        return 0.0

    async def generate(self, req: GenerationRequest) -> GenerationResult:
        return self._render(req)

    async def edit(self, req: GenerationRequest, image: ReferenceImage) -> GenerationResult:
        # Echo the input back so composite-drift checks pass unchanged in dry-run.
        return GenerationResult(
            data=image.data,
            mime_type=image.mime_type,
            provider=self.name,
            model=self.model,
            usd=0.0,
            prompt=req.prompt,
            dry_run=True,
        )

    def _render(self, req: GenerationRequest) -> GenerationResult:
        w, h = RATIO_SIZES.get(req.aspect_ratio, (1024, 1024))
        digest = hashlib.sha256(req.prompt.encode()).digest()
        tint = tuple(
            int(base + (byte - 128) * 0.18)
            for base, byte in zip(AURATI_NAVY, digest[:3])
        )
        img = Image.new("RGB", (w, h), tint)
        draw = ImageDraw.Draw(img)
        draw.rectangle([40, 40, w - 40, h - 40], outline=AURATI_PLATINUM, width=6)
        caption = "DRY RUN — no API call\n\n" + "\n".join(
            textwrap.wrap(req.prompt[:400], width=44)
        )
        draw.multiline_text((72, 96), caption, fill=AURATI_PLATINUM, spacing=8)

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return GenerationResult(
            data=buf.getvalue(),
            mime_type="image/png",
            provider=self.name,
            model=self.model,
            usd=0.0,
            prompt=req.prompt,
            dry_run=True,
        )
