"""Landmark reading.

Geometry and the reject-rather-than-guess behaviour are tested against synthetic
landmark sets, so the safety property is verified exhaustively without needing a
photograph of a real person. A gated test runs the actual MediaPipe model over
any scene images the user drops in samples/scenes/.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from app.config.anatomy import (
    FACE_CHIN,
    FACE_LEFT_BELOW_EAR,
    FACE_LEFT_IRIS,
    FACE_LEFT_JAW,
    FACE_LEFT_TRAGION,
    FACE_RIGHT_BELOW_EAR,
    FACE_RIGHT_IRIS,
    FACE_RIGHT_JAW,
    FACE_RIGHT_TRAGION,
    HAND_INDEX_MCP,
    HAND_PINKY_MCP,
    HAND_RING_MCP,
    HAND_RING_PIP,
    HAND_WRIST,
    MountPoint,
)
from app.pipeline import landmarks as L

SCENES = Path(__file__).resolve().parents[2] / "samples" / "scenes"

#: 62 mm interpupillary distance rendered at 5 px/mm.
PX_PER_MM = 5.0
IPD_PX = 62 * PX_PER_MM        # 310
FACE_WIDTH_PX = 128 * PX_PER_MM  # 640


def face_points(ipd_px=IPD_PX, face_width_px=FACE_WIDTH_PX, roll_deg=0.0) -> list[tuple[float, float]]:
    """A synthetic 478-point face, upright and centred, with exact spans."""
    pts = [(450.0, 500.0)] * 478
    cx, cy = 450.0, 400.0

    half = ipd_px / 2
    theta = math.radians(roll_deg)
    dx, dy = math.cos(theta) * half, math.sin(theta) * half
    pts[FACE_LEFT_IRIS] = (cx - dx, cy - dy)
    pts[FACE_RIGHT_IRIS] = (cx + dx, cy + dy)

    hw = face_width_px / 2
    pts[FACE_LEFT_TRAGION] = (cx - hw, cy + 20)
    pts[FACE_RIGHT_TRAGION] = (cx + hw, cy + 20)
    pts[FACE_LEFT_BELOW_EAR] = (cx - hw + 20, cy + 20 + 0.45 * 19 * PX_PER_MM / 0.45)
    pts[FACE_RIGHT_BELOW_EAR] = (cx + hw - 20, cy + 20 + 0.45 * 19 * PX_PER_MM / 0.45)
    pts[FACE_LEFT_JAW] = (cx - hw + 60, cy + 300)
    pts[FACE_RIGHT_JAW] = (cx + hw - 60, cy + 300)
    pts[FACE_CHIN] = (cx, cy + 360)
    return pts


def hand_points(palm_px=78 * PX_PER_MM) -> list[tuple[float, float]]:
    pts = [(300.0, 300.0)] * 21
    pts[HAND_INDEX_MCP] = (300.0, 300.0)
    pts[HAND_PINKY_MCP] = (300.0 + palm_px, 300.0)
    pts[HAND_RING_MCP] = (360.0, 320.0)
    pts[HAND_RING_PIP] = (360.0, 420.0)
    pts[HAND_WRIST] = (330.0, 460.0)
    return pts


@pytest.fixture
def blank():
    return np.zeros((800, 900, 3), dtype=np.uint8)


# --- calibration ------------------------------------------------------------


def test_ipd_drives_pixels_per_mm(monkeypatch, blank):
    monkeypatch.setattr(L, "_face_points", lambda img: face_points())
    r = L.read_face(blank, MountPoint.EARLOBE)

    assert r.primary.span.key == "ipd"
    assert r.px_per_mm == pytest.approx(PX_PER_MM)


def test_crosscheck_is_measured_independently(monkeypatch, blank):
    monkeypatch.setattr(L, "_face_points", lambda img: face_points())
    r = L.read_face(blank, MountPoint.EARLOBE)

    assert r.crosscheck is not None
    assert r.crosscheck.span.key == "face_width"
    assert r.agreement_pct == pytest.approx(0.0, abs=0.5)


def test_disagreeing_rulers_are_rejected_rather_than_averaged(monkeypatch, blank):
    """A turned head makes face width shrink while IPD barely moves. Guessing
    from either one would silently mis-scale the product."""
    monkeypatch.setattr(
        L, "_face_points", lambda img: face_points(face_width_px=FACE_WIDTH_PX * 0.7)
    )
    with pytest.raises(L.LandmarkError, match="disagree"):
        L.read_face(blank, MountPoint.EARLOBE)


def test_disagreement_inside_tolerance_is_accepted(monkeypatch, blank):
    monkeypatch.setattr(
        L, "_face_points", lambda img: face_points(face_width_px=FACE_WIDTH_PX * 1.05)
    )
    r = L.read_face(blank, MountPoint.EARLOBE)
    assert r.agreement_pct == pytest.approx(5.0, abs=1.0)


def test_a_face_too_small_to_calibrate_is_rejected(monkeypatch, blank):
    monkeypatch.setattr(L, "_face_points", lambda img: face_points(ipd_px=4))
    with pytest.raises(L.LandmarkError, match="too small or too rotated|too small"):
        L.read_face(blank, MountPoint.EARLOBE)


def test_eye_corners_are_used_when_iris_landmarks_are_absent(monkeypatch, blank):
    """A 468-point model has no iris; the reading must still work."""
    full = face_points()
    short = full[:468]
    left, right = L.FACE_LEFT_EYE_CORNERS, L.FACE_RIGHT_EYE_CORNERS
    for idx in left:
        short[idx] = full[FACE_LEFT_IRIS]
    for idx in right:
        short[idx] = full[FACE_RIGHT_IRIS]

    monkeypatch.setattr(L, "_face_points", lambda img: short)
    r = L.read_face(blank, MountPoint.EARLOBE)
    assert r.px_per_mm == pytest.approx(PX_PER_MM, rel=0.02)
    assert r.diagnostics["landmark_count"] == 468


# --- anchors and axes -------------------------------------------------------


def test_earlobe_anchor_sits_below_the_tragion(monkeypatch, blank):
    monkeypatch.setattr(L, "_face_points", lambda img: face_points())
    r = L.read_face(blank, MountPoint.EARLOBE)
    pts = face_points()
    tragion_y = pts[FACE_LEFT_TRAGION][1]
    assert r.anchor[1] > tragion_y, "lobe anchor must hang below the tragion"


def test_head_roll_is_reported(monkeypatch, blank):
    monkeypatch.setattr(L, "_face_points", lambda img: face_points(roll_deg=15))
    r = L.read_face(blank, MountPoint.EARLOBE)
    assert r.axis_deg == pytest.approx(15, abs=1)


def test_roll_does_not_change_calibration(monkeypatch, blank):
    """Rotating the head must not change how many pixels a millimetre is."""
    readings = []
    for roll in (0, 10, -20):
        monkeypatch.setattr(L, "_face_points", lambda img, r=roll: face_points(roll_deg=r))
        readings.append(L.read_face(blank, MountPoint.EARLOBE).px_per_mm)
    assert readings == pytest.approx([PX_PER_MM] * 3, rel=1e-6)


def test_necklace_anchor_sits_below_the_chin(monkeypatch, blank):
    monkeypatch.setattr(L, "_face_points", lambda img: face_points())
    r = L.read_face(blank, MountPoint.NECK)
    assert r.anchor[1] > face_points()[FACE_CHIN][1] * 0.9


# --- hand -------------------------------------------------------------------


def test_palm_width_calibrates_the_hand(monkeypatch, blank):
    monkeypatch.setattr(L, "_hand_points", lambda img: hand_points())
    r = L.read_hand(blank, MountPoint.RING_FINGER)
    assert r.primary.span.key == "palm_width"
    assert r.px_per_mm == pytest.approx(PX_PER_MM)


def test_hand_has_no_crosscheck(monkeypatch, blank):
    """Documented deliberately: every candidate second span shares the MCP
    landmarks, so agreement would be circular."""
    monkeypatch.setattr(L, "_hand_points", lambda img: hand_points())
    r = L.read_hand(blank, MountPoint.RING_FINGER)
    assert r.crosscheck is None
    assert r.agreement_pct is None


def test_ring_anchor_sits_on_the_proximal_phalanx(monkeypatch, blank):
    monkeypatch.setattr(L, "_hand_points", lambda img: hand_points())
    r = L.read_hand(blank, MountPoint.RING_FINGER)
    mcp, pip = hand_points()[HAND_RING_MCP], hand_points()[HAND_RING_PIP]
    assert mcp[1] < r.anchor[1] < pip[1]


def test_ankle_is_flagged_low_confidence(monkeypatch, blank):
    monkeypatch.setattr(L, "_hand_points", lambda img: hand_points())
    r = L.read_hand(blank, MountPoint.ANKLE)
    assert "low_confidence" in r.diagnostics


def test_a_hand_too_small_to_calibrate_is_rejected(monkeypatch, blank):
    monkeypatch.setattr(L, "_hand_points", lambda img: hand_points(palm_px=5))
    with pytest.raises(L.LandmarkError, match="too small"):
        L.read_hand(blank, MountPoint.RING_FINGER)


# --- real model -------------------------------------------------------------


def test_missing_face_gives_an_actionable_message(blank):
    """Runs the real MediaPipe model on an empty frame. Bundles are ~11 MB and
    cached, so this stays fast."""
    with pytest.raises(L.LandmarkError, match="No face detected"):
        L.read_face(blank, MountPoint.EARLOBE)


scene_files = sorted(
    p for p in SCENES.glob("*") if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
) if SCENES.exists() else []


@pytest.mark.skipif(not scene_files, reason="no images in samples/scenes/")
@pytest.mark.parametrize("path", scene_files, ids=lambda p: p.name)
def test_real_scene_calibrates(path):
    r = L.read(path, MountPoint.EARLOBE)
    assert r.px_per_mm > 0
    assert abs(r.agreement_pct or 0) <= 12.0, r.diagnostics
