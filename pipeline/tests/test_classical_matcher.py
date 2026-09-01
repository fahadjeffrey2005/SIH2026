"""match.classical.matcher: the self-match sanity check used throughout this
project's build (rotate a synthetic image slightly, match it against
itself) as an automated regression test, so "zero matches" in a real run
stays trustworthy as a genuine finding instead of a silent pipeline break.
"""

import cv2
import numpy as np

from match.classical.matcher import match


def _synthetic_textured_image(size: int = 400, seed: int = 0) -> np.ndarray:
    """A crater-field-ish synthetic image: enough distinct circular/blob
    features for SIFT/AKAZE to actually have something to detect, unlike
    flat noise or a blank image."""
    rng = np.random.default_rng(seed)
    img = np.full((size, size), 60, dtype=np.uint8)
    for _ in range(120):
        x, y = rng.integers(0, size, 2)
        r = rng.integers(4, 30)
        shade = int(rng.integers(20, 230))
        cv2.circle(img, (int(x), int(y)), int(r), shade, -1)
    return img


def test_sift_self_match_rotated():
    img = _synthetic_textured_image()
    center = (img.shape[1] / 2, img.shape[0] / 2)
    rot = cv2.getRotationMatrix2D(center, 8, 1.0)
    warped = cv2.warpAffine(img, rot, (img.shape[1], img.shape[0]))

    result = match(img, warped, method="sift")

    assert result.keypoints_a > 0 and result.keypoints_b > 0
    assert result.ratio_test_matches > 0
    # A small rotation of the same image should be matched almost entirely
    # as inliers -- this is the bar "genuine zero matches" gets judged
    # against in docs/baseline_results.md.
    assert result.inlier_ratio > 0.8


def test_akaze_self_match_rotated():
    img = _synthetic_textured_image()
    center = (img.shape[1] / 2, img.shape[0] / 2)
    rot = cv2.getRotationMatrix2D(center, 8, 1.0)
    warped = cv2.warpAffine(img, rot, (img.shape[1], img.shape[0]))

    result = match(img, warped, method="akaze")

    assert result.ratio_test_matches > 0
    assert result.inlier_ratio > 0.7


def test_no_crash_on_blank_image():
    """A featureless crop (e.g. a tiny sliver from an aggressive
    overlap_crop margin) shouldn't raise -- it should just report zero
    keypoints/matches."""
    blank_a = np.full((50, 50), 128, dtype=np.uint8)
    blank_b = np.full((50, 50), 128, dtype=np.uint8)

    result = match(blank_a, blank_b, method="sift")

    assert result.inliers == 0
    assert result.inlier_ratio == 0.0
