"""Step A of the hybrid pipeline (§4): product cut-out.

Background removal is the input to everything downstream, so its failure modes
matter more than its happy path. The hard cases for jewellery are fine chains
(thin, low-contrast strands the matte breaks up), prong settings (small gaps it
fills in) and polished metal (reflects the background, dragging the edge with
it). The post-processing here targets exactly those.

The rembg session is expensive to construct and is therefore built once and
reused. Inference is synchronous and slow enough to block the event loop, so
callers must go through `cutout_async`.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import logging
import threading
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from app.config.settings import get_settings

log = logging.getLogger(__name__)

#: Alpha below this is treated as background when measuring coverage.
ALPHA_FLOOR = 8

#: Connected alpha components smaller than this fraction of the largest one are
#: speckle — matte noise left on the backdrop — and get removed.
SPECKLE_FRACTION = 0.005

#: Halo-removal curve. The floor must exceed what a 3x3 blur pushes onto a
#: pixel just outside a straight edge (~64) so those go to zero. The gain is
#: derived rather than chosen so that 255 maps back to exactly 255 — a product
#: body left at 254 is not fully opaque and would composite with a faint veil.
HALO_FLOOR = 96.0
HALO_GAIN = 255.0 / (255.0 - HALO_FLOOR)


class CutoutError(RuntimeError):
    pass


@dataclass(frozen=True)
class CutoutResult:
    path: Path
    width: int
    height: int
    #: Fraction of the *original frame* that survived as foreground. Measured
    #: before trimming: a trimmed matte is foreground by definition, so
    #: measuring after would make the signal meaningless. Near 0 means the
    #: matte collapsed, near 1 means it kept the whole background.
    coverage: float
    cached: bool
    source_sha: str

    @property
    def looks_plausible(self) -> bool:
        return 0.005 <= self.coverage <= 0.95


# --- session management -----------------------------------------------------

_session = None
_session_lock = threading.Lock()


def get_session():
    """Build the rembg session once.

    First call downloads model weights — birefnet-general is ~970 MB, several
    minutes on a normal connection — and rembg writes its progress bar to
    stderr, not through any callback, so from the API's side it simply blocks.
    Callers should surface that in the step log or it reads as a hang.
    """
    global _session
    if _session is None:
        with _session_lock:
            if _session is None:
                from rembg import new_session

                name = get_settings().rembg_model
                log.info("Loading rembg session %r (first run downloads weights)", name)
                _session = new_session(name)
                log.info("rembg session ready")
    return _session


def reset_session() -> None:
    global _session
    _session = None


# --- alpha post-processing --------------------------------------------------


def refine_alpha(rgba: np.ndarray) -> np.ndarray:
    """Clean the matte without eating fine detail.

    Deliberately conservative: a chain is only a few pixels wide, so anything
    that erodes aggressively removes the product itself. Order matters —
    speckle is dropped before hole-filling, otherwise isolated noise gets
    treated as a hole boundary and filled into a blob.
    """
    alpha = rgba[:, :, 3]

    # 1. Drop speckle: matte noise on the backdrop, kept relative to the
    #    largest component so it scales with how much of the frame the piece
    #    occupies.
    binary = (alpha > ALPHA_FLOOR).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    if count > 1:
        areas = stats[1:, cv2.CC_STAT_AREA]
        cutoff = areas.max() * SPECKLE_FRACTION
        for idx, area in enumerate(areas, start=1):
            if area < cutoff:
                alpha[labels == idx] = 0

    # 2. Close pinholes inside stones and prong gaps. A 3x3 close is enough for
    #    single-pixel holes and will not bridge across a genuine gap.
    alpha = cv2.morphologyEx(alpha, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))

    # 3. Kill the halo. Polished metal reflects the backdrop, so the matte
    #    usually runs a pixel wide. Blur, then apply a contrast curve whose
    #    floor sits above what the blur pushes onto outside pixels (~0.25 x 255
    #    for a 3x3 kernel at a straight edge), so the edge is pulled in rather
    #    than smeared out. An erode would do this too, but would sever a chain
    #    only a few pixels wide.
    alpha = cv2.GaussianBlur(alpha, (3, 3), 0)
    alpha = np.clip((alpha.astype(np.float32) - HALO_FLOOR) * HALO_GAIN, 0, 255).astype(np.uint8)

    rgba[:, :, 3] = alpha
    return rgba


def trim_to_content(rgba: np.ndarray, pad: int = 8) -> np.ndarray:
    """Crop to the product's bounding box.

    Downstream scaling works in millimetres against the product's own extent,
    so leading whitespace would offset every composite. Padding keeps the
    contact shadow room to fall.
    """
    ys, xs = np.nonzero(rgba[:, :, 3] > ALPHA_FLOOR)
    if ys.size == 0:
        raise CutoutError("Background removal produced an empty matte.")
    y0, y1 = max(0, ys.min() - pad), min(rgba.shape[0], ys.max() + pad + 1)
    x0, x1 = max(0, xs.min() - pad), min(rgba.shape[1], xs.max() + pad + 1)
    return rgba[y0:y1, x0:x1]


# --- main entry points ------------------------------------------------------


def sha_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def cutout_path(product_id: str, angle: str) -> Path:
    return get_settings().cutouts_dir / product_id / f"{angle}.png"


def _sidecar(path: Path) -> Path:
    """Cache metadata beside the PNG.

    Holds the source hash *and* the pre-trim coverage, because coverage cannot
    be recovered from the trimmed file on a cache hit.
    """
    return path.with_suffix(".json")


def cutout(source: Path, product_id: str, angle: str, *, force: bool = False) -> CutoutResult:
    """Remove the background from one uploaded angle.

    Results are cached against the source file's hash, so re-running is free
    but re-uploading an angle invalidates automatically.
    """
    source = Path(source)
    if not source.exists():
        raise CutoutError(f"Source image missing: {source}")

    dest = cutout_path(product_id, angle)
    dest.parent.mkdir(parents=True, exist_ok=True)
    digest = sha_of(source)
    sidecar = _sidecar(dest)

    if not force and dest.exists() and sidecar.exists():
        try:
            meta = json.loads(sidecar.read_text())
        except json.JSONDecodeError:
            meta = {}
        if meta.get("sha") == digest:
            with Image.open(dest) as img:
                return CutoutResult(
                    dest, img.width, img.height, float(meta["coverage"]), True, digest
                )

    from rembg import remove

    try:
        raw = remove(source.read_bytes(), session=get_session())
    except Exception as exc:  # noqa: BLE001 — vendor errors vary wildly
        raise CutoutError(f"Background removal failed for {angle}: {exc}") from exc

    with Image.open(io.BytesIO(raw)) as img:
        rgba = np.array(img.convert("RGBA"))

    refined = refine_alpha(rgba)
    coverage = float((refined[:, :, 3] > ALPHA_FLOOR).mean())

    trimmed = trim_to_content(refined)
    Image.fromarray(trimmed, mode="RGBA").save(dest, format="PNG")
    sidecar.write_text(json.dumps({"sha": digest, "coverage": coverage}))

    result = CutoutResult(dest, trimmed.shape[1], trimmed.shape[0], coverage, False, digest)
    if not result.looks_plausible:
        log.warning(
            "Cut-out for %s/%s has implausible coverage %.3f — check the source background.",
            product_id,
            angle,
            coverage,
        )
    return result


async def cutout_async(source: Path, product_id: str, angle: str, *, force: bool = False):
    """Run `cutout` off the event loop.

    rembg inference is synchronous and takes seconds; calling it inline in a
    request handler stalls every other connection, including the progress
    stream the user is watching.
    """
    return await asyncio.to_thread(cutout, source, product_id, angle, force=force)
