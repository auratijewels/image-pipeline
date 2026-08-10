"""MediaPipe model bundle download and cache.

MediaPipe 1.0 removed the legacy `mp.solutions` API and ships **no model assets**
in the package — the Tasks API requires each `.task` bundle to be fetched
separately. This is not mentioned in the brief and is easy to hit as a confusing
runtime failure, so the download is explicit, cached, and verified.

These are small (a few MB each), unlike the ~970 MB rembg weights.
"""

from __future__ import annotations

import logging
import threading
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from app.config.settings import REPO_ROOT

log = logging.getLogger(__name__)

WEIGHTS_DIR = REPO_ROOT / "models" / "weights"

BASE = "https://storage.googleapis.com/mediapipe-models"


@dataclass(frozen=True)
class Bundle:
    name: str
    url: str
    approx_mb: float


BUNDLES: dict[str, Bundle] = {
    "face_landmarker": Bundle(
        "face_landmarker.task",
        f"{BASE}/face_landmarker/face_landmarker/float16/1/face_landmarker.task",
        3.8,
    ),
    "hand_landmarker": Bundle(
        "hand_landmarker.task",
        f"{BASE}/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task",
        7.5,
    ),
}

#: A truncated download still writes a file, and MediaPipe's failure on a corrupt
#: bundle is opaque. Anything below this is treated as incomplete.
MIN_PLAUSIBLE_BYTES = 500_000

_lock = threading.Lock()


class AssetError(RuntimeError):
    pass


def bundle_path(key: str) -> Path:
    return WEIGHTS_DIR / BUNDLES[key].name


def ensure_bundle(key: str) -> Path:
    """Return the local path to a model bundle, downloading it if needed."""
    bundle = BUNDLES[key]
    dest = bundle_path(key)

    if dest.exists() and dest.stat().st_size >= MIN_PLAUSIBLE_BYTES:
        return dest

    with _lock:
        # Re-check inside the lock: a concurrent caller may have finished.
        if dest.exists() and dest.stat().st_size >= MIN_PLAUSIBLE_BYTES:
            return dest

        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".partial")
        log.info("Downloading %s (~%.1f MB) from %s", bundle.name, bundle.approx_mb, bundle.url)
        try:
            with urllib.request.urlopen(bundle.url, timeout=120) as resp, tmp.open("wb") as fh:
                while chunk := resp.read(1 << 16):
                    fh.write(chunk)
        except Exception as exc:  # noqa: BLE001 — network failures vary
            tmp.unlink(missing_ok=True)
            raise AssetError(
                f"Could not download {bundle.name} from {bundle.url}: {exc}"
            ) from exc

        size = tmp.stat().st_size
        if size < MIN_PLAUSIBLE_BYTES:
            tmp.unlink(missing_ok=True)
            raise AssetError(f"{bundle.name} downloaded only {size} bytes — treating as truncated.")

        # Atomic swap, so an interrupted run can never leave a half-written
        # bundle at the real path where it would fail opaquely inside MediaPipe.
        tmp.replace(dest)
        log.info("%s ready (%.1f MB)", bundle.name, size / 1e6)
        return dest


def ensure_all() -> dict[str, Path]:
    return {key: ensure_bundle(key) for key in BUNDLES}


def missing_bundles() -> list[str]:
    return [
        key
        for key in BUNDLES
        if not (bundle_path(key).exists() and bundle_path(key).stat().st_size >= MIN_PLAUSIBLE_BYTES)
    ]
