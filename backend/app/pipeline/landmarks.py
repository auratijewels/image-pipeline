"""Step C of the hybrid pipeline (§4): landmark measurement.

Reads a generated scene and returns everything the composite needs: a calibration
span in pixels, an independent cross-check span, the mount anchor, and the axis
the product should be rotated to.

Two things this module deliberately does *not* do:

- It never guesses. If the primary and cross-check rulers disagree beyond
  tolerance, or a required landmark is missing, it raises. A confidently wrong
  measurement produces a wrongly-scaled product that looks plausible, which is
  far worse than a refusal the orchestrator can retry.
- It never uses the anchor to calibrate. Anchors are estimated from surrounding
  geometry and are only accurate enough for placement; scale comes from spans
  that are directly measured. See config/anatomy.py for why.
"""

from __future__ import annotations

import logging
import math
import threading
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from app.config.anatomy import (
    CROSSCHECK_SPAN,
    CROSSCHECK_TOLERANCE_PCT,
    EARLOBE_PLAUSIBLE_MM,
    FACE_CHIN,
    FACE_LEFT_BELOW_EAR,
    FACE_LEFT_EYE_CORNERS,
    FACE_LEFT_IRIS,
    FACE_LEFT_JAW,
    FACE_LEFT_TRAGION,
    FACE_RIGHT_BELOW_EAR,
    FACE_RIGHT_EYE_CORNERS,
    FACE_RIGHT_IRIS,
    FACE_RIGHT_JAW,
    FACE_RIGHT_TRAGION,
    HAND_INDEX_MCP,
    HAND_PINKY_MCP,
    HAND_RING_MCP,
    HAND_RING_PIP,
    HAND_WRIST,
    PRIMARY_SPAN,
    CalibrationSpan,
    Detector,
    MountPoint,
)
from app.pipeline import mp_assets

log = logging.getLogger(__name__)

Point = tuple[float, float]


class LandmarkError(RuntimeError):
    """No usable measurement. Carries a reason the UI can show verbatim."""


@dataclass
class Measurement:
    span: CalibrationSpan
    pixels: float

    @property
    def px_per_mm(self) -> float:
        return self.pixels / self.span.mm


@dataclass
class LandmarkReading:
    detector: Detector
    mount: MountPoint
    primary: Measurement
    anchor: Point
    #: Degrees the product should be rotated to sit along the body part's axis.
    axis_deg: float
    crosscheck: Measurement | None = None
    #: Signed disagreement between the two rulers, as a percentage of primary.
    agreement_pct: float | None = None
    diagnostics: dict = field(default_factory=dict)

    @property
    def px_per_mm(self) -> float:
        return self.primary.px_per_mm


def _dist(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _mid(a: Point, b: Point) -> Point:
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


# --- landmarker construction ------------------------------------------------

_landmarkers: dict[str, object] = {}
_lock = threading.Lock()


def _get_landmarker(kind: str):
    """Build a Tasks-API landmarker once and reuse it.

    Construction loads and warms a model; doing it per call would dominate
    runtime the same way rebuilding the rembg session would.
    """
    if kind in _landmarkers:
        return _landmarkers[kind]
    with _lock:
        if kind in _landmarkers:
            return _landmarkers[kind]

        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision

        path = str(mp_assets.ensure_bundle(kind))
        base = mp_python.BaseOptions(model_asset_path=path)

        if kind == "face_landmarker":
            opts = vision.FaceLandmarkerOptions(base_options=base, num_faces=1)
            lm = vision.FaceLandmarker.create_from_options(opts)
        elif kind == "hand_landmarker":
            opts = vision.HandLandmarkerOptions(base_options=base, num_hands=1)
            lm = vision.HandLandmarker.create_from_options(opts)
        else:
            raise LandmarkError(f"Unknown landmarker {kind!r}")

        _landmarkers[kind] = lm
        return lm


def reset_landmarkers() -> None:
    _landmarkers.clear()


def _as_mp_image(image: np.ndarray):
    import mediapipe as mp

    rgb = image[:, :, :3] if image.shape[2] == 4 else image
    return mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))


def _load(path: Path) -> np.ndarray:
    from PIL import Image

    with Image.open(path) as img:
        return np.array(img.convert("RGB"))


# --- face ------------------------------------------------------------------


def _face_points(image: np.ndarray) -> list[Point]:
    result = _get_landmarker("face_landmarker").detect(_as_mp_image(image))
    faces = getattr(result, "face_landmarks", None) or []
    if not faces:
        raise LandmarkError(
            "No face detected in the generated scene. Regenerate the scene, or check that "
            "the model's face is unobstructed and roughly frontal."
        )
    h, w = image.shape[:2]
    return [(lm.x * w, lm.y * h) for lm in faces[0]]


def _iris_centres(pts: list[Point]) -> tuple[Point, Point]:
    """Pupil centres, preferring iris landmarks over eye-corner midpoints.

    The 478-point bundle includes iris refinement; a 468-point model does not.
    Eye-corner midpoints are a close but slightly noisier substitute.
    """
    if len(pts) > max(FACE_LEFT_IRIS, FACE_RIGHT_IRIS):
        return pts[FACE_LEFT_IRIS], pts[FACE_RIGHT_IRIS]
    log.info("Face model returned %d landmarks (no iris) — using eye corners.", len(pts))
    return (
        _mid(pts[FACE_LEFT_EYE_CORNERS[0]], pts[FACE_LEFT_EYE_CORNERS[1]]),
        _mid(pts[FACE_RIGHT_EYE_CORNERS[0]], pts[FACE_RIGHT_EYE_CORNERS[1]]),
    )


def _face_axes(left_eye: Point, right_eye: Point) -> tuple[float, Point]:
    """Head roll in degrees, and the unit vector pointing toward the chin."""
    dx, dy = right_eye[0] - left_eye[0], right_eye[1] - left_eye[1]
    roll = math.degrees(math.atan2(dy, dx))
    length = math.hypot(dx, dy) or 1.0
    # Rotate the eye-line 90° to get the head's vertical axis. Image y grows
    # downward, so this points from the eyes toward the chin.
    return roll, (-dy / length, dx / length)


def read_face(image: np.ndarray, mount: MountPoint) -> LandmarkReading:
    pts = _face_points(image)
    left_eye, right_eye = _iris_centres(pts)

    ipd_px = _dist(left_eye, right_eye)
    if ipd_px < 8:
        raise LandmarkError(
            f"Interpupillary distance measured only {ipd_px:.1f}px. The face is too small "
            "or too rotated to calibrate from — regenerate the scene with a closer crop."
        )

    primary = Measurement(PRIMARY_SPAN[Detector.FACE], ipd_px)

    cross_span = CROSSCHECK_SPAN[Detector.FACE]
    crosscheck = None
    agreement = None
    if cross_span is not None:
        width_px = _dist(pts[FACE_LEFT_TRAGION], pts[FACE_RIGHT_TRAGION])
        crosscheck = Measurement(cross_span, width_px)
        agreement = (crosscheck.px_per_mm - primary.px_per_mm) / primary.px_per_mm * 100
        if abs(agreement) > CROSSCHECK_TOLERANCE_PCT:
            raise LandmarkError(
                f"Scale rulers disagree by {agreement:+.1f}% (tolerance "
                f"±{CROSSCHECK_TOLERANCE_PCT:.0f}%). Interpupillary distance implies "
                f"{primary.px_per_mm:.3f} px/mm but face width implies "
                f"{crosscheck.px_per_mm:.3f}. The head is probably turned too far, or the "
                "face is partly occluded. Regenerate the scene."
            )

    roll, down = _face_axes(left_eye, right_eye)
    eye_mid = _mid(left_eye, right_eye)

    diagnostics: dict = {"landmark_count": len(pts), "head_roll_deg": round(roll, 2)}

    if mount is MountPoint.EARLOBE:
        # Use whichever ear is farther from the face midline: in a three-quarter
        # view that is the one turned toward camera.
        left_d = abs(pts[FACE_LEFT_TRAGION][0] - eye_mid[0])
        right_d = abs(pts[FACE_RIGHT_TRAGION][0] - eye_mid[0])
        if left_d >= right_d:
            tragion, below = pts[FACE_LEFT_TRAGION], pts[FACE_LEFT_BELOW_EAR]
            side = "left"
        else:
            tragion, below = pts[FACE_RIGHT_TRAGION], pts[FACE_RIGHT_BELOW_EAR]
            side = "right"

        # The lobe hangs below the tragion. Anatomically that drop is ~0.42x
        # the interpupillary distance; an estimate is fine here because this
        # positions the product, it does not scale it.
        anchor = (tragion[0] + down[0] * 0.42 * ipd_px, tragion[1] + down[1] * 0.42 * ipd_px)

        # Coarse diagnostic only. This spans the whole ear region rather than
        # the lobe alone, so it catches an anatomically broken generation
        # without being precise enough to calibrate from.
        ear_region_mm = _dist(tragion, below) / primary.px_per_mm
        lo, hi = EARLOBE_PLAUSIBLE_MM
        diagnostics |= {
            "ear_side": side,
            "ear_region_mm": round(ear_region_mm, 1),
            "ear_region_plausible": lo <= ear_region_mm * 0.45 <= hi,
        }
        if not diagnostics["ear_region_plausible"]:
            log.warning(
                "Inferred ear region %.1f mm is anatomically odd — scale still comes from "
                "IPD, but the generated face may be malformed.",
                ear_region_mm,
            )
        return LandmarkReading(
            Detector.FACE, mount, primary, anchor, roll, crosscheck, agreement, diagnostics
        )

    # Necklace: sit the piece below the jaw, on the head's vertical axis.
    jaw_mid = _mid(pts[FACE_LEFT_JAW], pts[FACE_RIGHT_JAW])
    chin = pts[FACE_CHIN]
    base = _mid(jaw_mid, chin)
    anchor = (base[0] + down[0] * 0.55 * ipd_px, base[1] + down[1] * 0.55 * ipd_px)
    return LandmarkReading(
        Detector.FACE, mount, primary, anchor, roll, crosscheck, agreement, diagnostics
    )


# --- hand ------------------------------------------------------------------


def _hand_points(image: np.ndarray) -> list[Point]:
    result = _get_landmarker("hand_landmarker").detect(_as_mp_image(image))
    hands = getattr(result, "hand_landmarks", None) or []
    if not hands:
        raise LandmarkError(
            "No hand detected in the generated scene. Regenerate it with the hand fully "
            "visible and unobstructed."
        )
    h, w = image.shape[:2]
    return [(lm.x * w, lm.y * h) for lm in hands[0]]


def read_hand(image: np.ndarray, mount: MountPoint) -> LandmarkReading:
    pts = _hand_points(image)

    palm_px = _dist(pts[HAND_INDEX_MCP], pts[HAND_PINKY_MCP])
    if palm_px < 8:
        raise LandmarkError(
            f"Palm width measured only {palm_px:.1f}px — the hand is too small in frame "
            "to calibrate from. Regenerate with a closer crop."
        )
    primary = Measurement(PRIMARY_SPAN[Detector.HAND], palm_px)

    mcp, pip = pts[HAND_RING_MCP], pts[HAND_RING_PIP]
    finger_deg = math.degrees(math.atan2(pip[1] - mcp[1], pip[0] - mcp[0]))

    diagnostics = {"landmark_count": len(pts)}

    if mount is MountPoint.RING_FINGER:
        # A ring sits on the proximal phalanx, between knuckle and first joint.
        anchor = (mcp[0] + (pip[0] - mcp[0]) * 0.45, mcp[1] + (pip[1] - mcp[1]) * 0.45)
        # Rotate to the finger's axis, less the 90° offset so the band sits
        # across the finger rather than along it.
        axis = finger_deg - 90
    else:
        # Bracelet / anklet: at the wrist landmark, across the forearm axis.
        wrist = pts[HAND_WRIST]
        palm_mid = _mid(pts[HAND_INDEX_MCP], pts[HAND_PINKY_MCP])
        axis = math.degrees(math.atan2(palm_mid[1] - wrist[1], palm_mid[0] - wrist[0])) - 90
        anchor = wrist
        if mount is MountPoint.ANKLE:
            diagnostics["low_confidence"] = "hand model used for ankle framing"

    return LandmarkReading(
        Detector.HAND, mount, primary, anchor, axis, None, None, diagnostics
    )


# --- entry point ------------------------------------------------------------


def read(image: np.ndarray | Path | str, mount: MountPoint) -> LandmarkReading:
    """Measure a scene for the given mount point."""
    from app.config.anatomy import MOUNT_DETECTOR

    if isinstance(image, (str, Path)):
        image = _load(Path(image))

    detector = MOUNT_DETECTOR[mount]
    return read_face(image, mount) if detector is Detector.FACE else read_hand(image, mount)
