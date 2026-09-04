"""match.classical.hopc: phase-congruency sanity checks plus the same kind
of self-match regression test test_classical_matcher.py uses for SIFT/AKAZE
-- and, honestly, a test of the one real limitation HOPC's own module
docstring calls out: unlike SIFT, this descriptor has no per-keypoint
dominant-orientation alignment, so it is NOT rotation-invariant. That's
fine for this project (products are already geolocated into a shared,
unrotated working frame before matching ever runs -- see
match.classical.demo.prep_crop), but it's a real, measured limitation, not
a hypothetical one, and it's asserted here rather than just claimed in a
docstring.

The actual illumination-robustness claim (HOPC's whole reason for
existing) is checked against real project data instead of a synthetic
stand-in -- see docs/baseline_results.md's "HOPC" section for those
numbers. A synthetic "shadow flip" turned out to be surprisingly hard to
simulate fairly (a smooth height-field render gives classical detectors
nothing to key on at all; adding matchable fine texture ends up handing
every method -- HOPC included -- an unrealistically easy, shared texture
pattern that has nothing to do with the actual illumination question) --
rather than lock in a synthetic result that might just be an artifact of
how the synthetic scene happens to be built, this module sticks to what a
synthetic test can honestly verify: the descriptor's basic correctness and
its real, known limitation.
"""

import cv2
import numpy as np

from match.classical.hopc import detect_and_compute, phase_congruency_energy
from match.classical.matcher import match


def _synthetic_textured_image(size: int = 400, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    img = np.full((size, size), 60, dtype=np.uint8)
    for _ in range(120):
        x, y = rng.integers(0, size, 2)
        r = rng.integers(4, 30)
        shade = int(rng.integers(20, 230))
        cv2.circle(img, (int(x), int(y)), int(r), shade, -1)
    return img


def test_phase_congruency_energy_shape_and_range():
    img = _synthetic_textured_image(size=128)
    pc = phase_congruency_energy(img.astype(np.float64) / 255.0, nscale=3, norient=6)

    assert pc.shape == (6, 128, 128)
    assert np.isfinite(pc).all()
    assert pc.min() >= 0.0 and pc.max() <= 1.0
    # A textured image should have *some* real structure detected somewhere
    # -- this would also catch a filter bank that's silently all-zero.
    assert pc.max() > 0.05


def test_detect_and_compute_finds_real_keypoints():
    img = _synthetic_textured_image()
    kp, desc = detect_and_compute(img)

    assert len(kp) > 0
    assert desc is not None
    assert desc.shape == (len(kp), 16 * 8)  # 4x4 cells x 8 orientations (NORIENT default)
    # Every descriptor is L2-normalized (post clip-and-renormalize) -- exact
    # unit norm isn't guaranteed after the clip step, but it should be close.
    norms = np.linalg.norm(desc, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-3)


def test_detect_and_compute_returns_empty_for_a_crop_smaller_than_the_patch():
    """A crop smaller than PATCH_SIZE (16px) can't support even one
    descriptor window -- must degrade gracefully, not crash (mirrors
    test_no_crash_on_blank_image below and the real "aggressive
    overlap_crop margin" scenario that motivated it)."""
    tiny = np.full((10, 10), 128, dtype=np.uint8)
    kp, desc = detect_and_compute(tiny)

    assert kp == []
    assert desc is None


def test_hopc_self_match_translated():
    """The core match() pipeline (detect, describe, ratio-test, RANSAC) works
    end-to-end for HOPC. Uses a pure translation rather than the rotation
    test_classical_matcher.py uses for SIFT/AKAZE -- see this module's
    docstring and test_hopc_is_not_rotation_invariant below for why."""
    img = _synthetic_textured_image()
    shifted = cv2.warpAffine(img, np.float32([[1, 0, 7], [0, 1, -5]]), (img.shape[1], img.shape[0]))

    result = match(img, shifted, method="hopc")

    assert result.keypoints_a > 0 and result.keypoints_b > 0
    assert result.ratio_test_matches > 0
    assert result.inlier_ratio > 0.8


def test_hopc_is_not_rotation_invariant():
    """Real, measured limitation (see module docstring): with no per-keypoint
    dominant-orientation alignment, HOPC's fixed axis-aligned descriptor
    grid degrades sharply past a small rotation, while SIFT (which
    normalizes against each keypoint's own dominant gradient direction)
    keeps matching almost the whole image. Measured directly: at a 30deg
    rotation of the same synthetic image, HOPC's inlier ratio collapses to
    ~0.1-0.3 while SIFT's stays ~0.95+ -- asserted here with a wide margin
    so this doesn't become a flaky test, not tuned to the exact numbers."""
    img = _synthetic_textured_image()
    rot = cv2.getRotationMatrix2D((img.shape[1] / 2, img.shape[0] / 2), 30, 1.0)
    warped = cv2.warpAffine(img, rot, (img.shape[1], img.shape[0]))

    hopc_result = match(img, warped, method="hopc")
    sift_result = match(img, warped, method="sift")

    assert sift_result.inlier_ratio > 0.85
    assert hopc_result.inlier_ratio < 0.5
    assert hopc_result.inlier_ratio < sift_result.inlier_ratio


def test_no_crash_on_blank_image():
    blank_a = np.full((50, 50), 128, dtype=np.uint8)
    blank_b = np.full((50, 50), 128, dtype=np.uint8)

    result = match(blank_a, blank_b, method="hopc")

    assert result.inliers == 0
    assert result.inlier_ratio == 0.0
