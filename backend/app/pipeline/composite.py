"""Steps D–E of the hybrid pipeline (§4): place the real product, then blend it in.

The generative model never places the product. It paints the scene; the actual
cut-out is scaled from measurement and composited here. That is the whole reason
the product exists — see README, "How the scale pipeline works".

The realism pass is deliberately restrained. Contact shadow and colour matching
make the composite sit in the scene, but neither may alter the product's shape or
size: the §10 acceptance check runs on the finished pixels, and anything that
moves the silhouette shows up there as a scale error.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

from app.config.anatomy import MountPoint
from app.pipeline.landmarks import LandmarkReading
from app.pipeline.scale import Axis, ScaleCheck, ScalePlan, plan as plan_scale, verify

log = logging.getLogger(__name__)

ALPHA_FLOOR = 8

#: Mounts where the piece hangs from the anchor rather than sitting centred on
#: it. An earring's post is at the lobe and the drop falls below; a ring's band
#: wraps the finger and is centred.
HANGS_FROM_ANCHOR = {MountPoint.EARLOBE, MountPoint.NECK}


class CompositeError(RuntimeError):
    pass


@dataclass
class CompositeResult:
    image: Image.Image
    plan: ScalePlan
    check: ScaleCheck
    anchor: tuple[float, float]
    rotation_deg: float

    @property
    def passed(self) -> bool:
        return self.check.passed


# --- geometry ---------------------------------------------------------------


def _alpha_bbox(rgba: np.ndarray) -> tuple[int, int, int, int]:
    ys, xs = np.nonzero(rgba[:, :, 3] > ALPHA_FLOOR)
    if ys.size == 0:
        raise CompositeError("Cut-out is empty — nothing to composite.")
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def measure_extent(image: Image.Image, axis: Axis) -> float:
    """Measure the visible product's extent, ignoring transparent padding.

    Measured from alpha rather than from image dimensions: rotation expands the
    canvas with transparent corners, so the canvas is larger than the product.
    """
    x0, y0, x1, y1 = _alpha_bbox(np.array(image.convert("RGBA")))
    return float(y1 - y0 if axis is Axis.HEIGHT else x1 - x0)


# --- realism ----------------------------------------------------------------


def contact_shadow(product: Image.Image, offset: tuple[int, int] = (0, 0), blur: float = 0.0) -> Image.Image:
    """A soft dark copy of the product's alpha, to ground it against skin.

    Scaled from the product itself so a small earring gets a small shadow.
    """
    w, h = product.size
    blur = blur or max(2.0, min(w, h) * 0.045)
    off = offset if any(offset) else (max(1, int(w * 0.02)), max(1, int(h * 0.025)))

    alpha = product.getchannel("A").filter(ImageFilter.GaussianBlur(blur))
    alpha = alpha.point(lambda v: int(v * 0.45))

    pad = int(blur * 2)
    canvas = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    shadow = Image.new("RGBA", (w, h), (18, 14, 12, 255))
    shadow.putalpha(alpha)
    canvas.paste(shadow, (pad + off[0], pad + off[1]), shadow)
    return canvas


def match_lighting(product: Image.Image, scene: Image.Image, anchor: tuple[float, float], strength: float = 0.35) -> Image.Image:
    """Nudge the product's colour temperature toward the local scene lighting.

    Samples a neighbourhood around the anchor rather than the whole frame — a
    piece worn on a face lit warm from one side should pick up that side's cast,
    not the average of the backdrop.

    Only channel gains are applied. Nothing here can move a pixel, so the
    silhouette — and therefore the measured scale — is untouched.
    """
    if strength <= 0:
        return product

    arr = np.array(scene.convert("RGB"), dtype=np.float32)
    h, w = arr.shape[:2]
    radius = max(16, int(min(w, h) * 0.12))
    cx, cy = int(anchor[0]), int(anchor[1])
    patch = arr[
        max(0, cy - radius) : min(h, cy + radius),
        max(0, cx - radius) : min(w, cx + radius),
    ]
    if patch.size == 0:
        return product

    scene_mean = patch.reshape(-1, 3).mean(axis=0)
    if scene_mean.mean() < 1e-3:
        return product

    prod = np.array(product.convert("RGBA"), dtype=np.float32)
    mask = prod[:, :, 3] > ALPHA_FLOOR
    if not mask.any():
        return product

    prod_mean = prod[:, :, :3][mask].mean(axis=0)
    prod_mean = np.where(prod_mean < 1e-3, 1e-3, prod_mean)

    # Normalise the gain so we shift colour balance without changing overall
    # brightness — the product should not darken just because the backdrop is.
    gain = (scene_mean / scene_mean.mean()) / (prod_mean / prod_mean.mean())
    gain = 1.0 + (gain - 1.0) * strength

    prod[:, :, :3] = np.clip(prod[:, :, :3] * gain, 0, 255)
    return Image.fromarray(prod.astype(np.uint8), mode="RGBA")


# --- main -------------------------------------------------------------------


def composite(
    scene: Image.Image | Path | str,
    cutout: Image.Image | Path | str,
    reading: LandmarkReading,
    category: str,
    dimensions_mm: dict[str, float],
    *,
    size_nudge: float = 1.0,
    rotate_nudge: float = 0.0,
    shadow: bool = True,
    relight: bool = True,
) -> CompositeResult:
    """Scale, rotate and place the product, then verify the result measures right.

    `size_nudge` and `rotate_nudge` are the §4F manual overrides. They default to
    neutral and are applied on top of the computed values, so the check below
    still reports honestly when a user has overridden the scale.
    """
    scene_img = _as_image(scene).convert("RGBA")
    cut = _as_image(cutout).convert("RGBA")

    # Trim any transparent padding first, or it inflates the measured extent and
    # the product comes out too small.
    cut = cut.crop(_alpha_bbox(np.array(cut)))

    plan = plan_scale(category, dimensions_mm, reading.px_per_mm, cut.size)
    factor = plan.factor * size_nudge
    if factor <= 0 or not math.isfinite(factor):
        raise CompositeError(f"Computed a nonsensical scale factor ({factor}).")

    target = (max(1, round(cut.width * factor)), max(1, round(cut.height * factor)))
    scaled = cut.resize(target, Image.LANCZOS)

    rotation = reading.axis_deg + rotate_nudge
    if abs(rotation) > 0.01:
        scaled = scaled.rotate(-rotation, resample=Image.BICUBIC, expand=True)

    if relight:
        scaled = match_lighting(scaled, scene_img, reading.anchor)

    out = scene_img.copy()
    x0, y0 = _placement(scaled.size, reading.anchor, reading.mount)

    if shadow:
        shadow_layer = contact_shadow(scaled)
        pad = (shadow_layer.width - scaled.width) // 2
        out.alpha_composite(shadow_layer, (int(x0 - pad), int(y0 - pad)))

    out.alpha_composite(scaled, (int(x0), int(y0)))

    # Verify against the finished pixels, not the intended transform, so
    # rounding and rotation-bounding errors are caught rather than assumed away.
    measured = measure_extent(scaled, plan.extent.axis)
    check = verify(plan, measured)
    if not check.passed:
        log.warning("Scale check failed for %s: %s", category, check.describe())

    return CompositeResult(out, plan, check, reading.anchor, rotation)


def _placement(size: tuple[int, int], anchor: tuple[float, float], mount: MountPoint) -> tuple[float, float]:
    w, h = size
    ax, ay = anchor
    if mount in HANGS_FROM_ANCHOR:
        # Top-centre of the piece meets the anchor; the drop falls below it.
        return ax - w / 2, ay
    return ax - w / 2, ay - h / 2


def _as_image(src: Image.Image | Path | str) -> Image.Image:
    if isinstance(src, Image.Image):
        return src
    return Image.open(Path(src))
