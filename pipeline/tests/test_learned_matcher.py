"""match.learned.matcher: DISK+LightGlue sanity checks.

Marked `slow` -- first run on a machine without the weights already cached
downloads ~50MB from GitHub (raw.githubusercontent.com /
github.com/cvg/LightGlue releases; see matcher.py's docstring for why those
hosts specifically). Skip with `pytest -m "not slow"` if torch/kornia
aren't installed or the network is unavailable.
"""

import cv2
import numpy as np
import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("kornia")

from match.learned.matcher import match  # noqa: E402


def _synthetic_textured_image(size: int = 400, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    img = np.full((size, size), 60, dtype=np.uint8)
    for _ in range(120):
        x, y = rng.integers(0, size, 2)
        r = rng.integers(4, 30)
        shade = int(rng.integers(20, 230))
        cv2.circle(img, (int(x), int(y)), int(r), shade, -1)
    return img


@pytest.mark.slow
def test_disk_lightglue_self_match_rotated():
    img = _synthetic_textured_image()
    center = (img.shape[1] / 2, img.shape[0] / 2)
    rot = cv2.getRotationMatrix2D(center, 8, 1.0)
    warped = cv2.warpAffine(img, rot, (img.shape[1], img.shape[0]))

    result = match(img, warped)

    assert result.keypoints_a > 0 and result.keypoints_b > 0
    assert result.raw_matches > 0
    assert result.inlier_ratio > 0.8


@pytest.mark.slow
def test_no_crash_on_large_image():
    """Regression test for a real bug: DISK's dense per-pixel feature maps
    scale with image area (unlike SIFT/AKAZE's sparse detection), and an
    early version of this matcher with no size guard got the process
    SIGKILLed by the OOM killer on one of this project's actual overlap
    crops (~13700x400, ~5.5 megapixels -- see docs/baseline_results.md).
    This uses a smaller stand-in (large enough to trigger the area-cap
    downscale in matcher.py, small enough to run quickly in CI) to prove
    the resize-and-rescale path works end to end without needing minutes of
    runtime."""
    img_a = _synthetic_textured_image(size=1600, seed=1)
    img_b = _synthetic_textured_image(size=1600, seed=1)  # identical -> should still find matches post-resize

    result = match(img_a, img_b, max_keypoints=512)

    assert result.keypoints_a > 0
    # Not asserting on inlier count here -- the point is that it completes
    # without crashing and returns a well-formed result, not matching
    # quality at a heavily downscaled resolution.
    assert result.pts_a.shape[1] == 2
    assert result.pts_b.shape[1] == 2


@pytest.mark.slow
def test_returns_empty_result_on_blank_image():
    blank_a = np.full((64, 64), 128, dtype=np.uint8)
    blank_b = np.full((64, 64), 128, dtype=np.uint8)

    result = match(blank_a, blank_b)

    assert result.inliers == 0
    assert result.inlier_ratio == 0.0
