"""Track A: classical feature matching (SIFT / AKAZE / HOPC) + ratio test +
RANSAC.

This is the baseline the learned track (DISK+LightGlue, Track B -- see
docs/architecture.md Sec. 5) is measured against. The three detectors are
worth trying because they fail differently under a large sun-angle gap:
SIFT's DoG blobs are sensitive to the shadow-driven local-contrast changes
a low sun elevation produces; AKAZE's nonlinear-diffusion scale space tends
to survive that better, at the cost of fewer keypoints on smooth terrain;
HOPC (see .hopc) sidesteps intensity gradients entirely in favor of
phase-congruency structure, which is illumination-independent by
construction -- see hopc.py's module docstring for the physical reasoning.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

from . import hopc


@dataclass
class MatchResult:
    method: str
    keypoints_a: int
    keypoints_b: int
    raw_matches: int
    ratio_test_matches: int
    inliers: int
    homography: Optional[np.ndarray]
    pts_a: np.ndarray  # inlier points in image A, Nx2 (x, y)
    pts_b: np.ndarray  # inlier points in image B, Nx2 (x, y)

    @property
    def inlier_ratio(self) -> float:
        return self.inliers / self.ratio_test_matches if self.ratio_test_matches else 0.0


def _empty(method: str, n_kp_a: int, n_kp_b: int, n_raw: int = 0, n_good: int = 0) -> MatchResult:
    return MatchResult(method, n_kp_a, n_kp_b, n_raw, n_good, 0, None,
                        np.zeros((0, 2), dtype=np.float32), np.zeros((0, 2), dtype=np.float32))


def _detector(method: str):
    if method == "sift":
        return cv2.SIFT_create(nfeatures=8000)
    if method == "akaze":
        return cv2.AKAZE_create()
    raise ValueError(f"unknown method: {method!r} (expected 'sift', 'akaze', or 'hopc')")


def _detect_and_describe(img: np.ndarray, method: str):
    """Returns (keypoints, descriptors) in the same shape cv2's own
    `detector.detectAndCompute` returns, whether `method` is a real cv2
    detector or HOPC's own implementation (hopc.py) -- so the ratio-test/
    RANSAC code below doesn't need to know or care which one it's using."""
    if method == "hopc":
        return hopc.detect_and_compute(img)
    det = _detector(method)
    kp, desc = det.detectAndCompute(img, None)
    return kp or [], desc


def match(
    img_a: np.ndarray,
    img_b: np.ndarray,
    method: str = "sift",
    ratio: Optional[float] = None,
    ransac_thresh: float = 4.0,
) -> MatchResult:
    """Detect, describe, ratio-test match, and RANSAC-filter a homography
    between two already-cropped, already-illumination-normalized images
    (see preprocess.normalize + geo.overlap_crop).

    `ratio=None` (the default) picks a per-method Lowe's-ratio-test
    threshold: 0.75 (Lowe's own original SIFT recommendation, also used
    here for AKAZE) unless `method == "hopc"`, which uses 0.85. This isn't
    an arbitrary loosening -- it's a real, measured fix. HOPC's descriptor
    (a coarse, 16-cell orientation-energy histogram) is less discriminative
    than SIFT's, so its nearest/second-nearest-neighbor distance ratios
    cluster much closer to 1.0 even for genuinely correct matches (checked
    directly against this project's own real catalog pairs): at 0.75, HOPC
    found a real, RANSAC-and-geolocation-confirmed match on zero of the 5
    confirmed-overlapping real pairs in this catalog; at 0.85 it found one
    on 3 of them, with geolocation agreement in the same range SIFT/AKAZE
    get on the same pairs (see docs/baseline_results.md's "HOPC" section --
    including the honest caveat about the other 2 pairs' nominal matches
    NOT holding up to visual/statistical scrutiny at this threshold)."""
    if ratio is None:
        ratio = 0.85 if method == "hopc" else 0.75
    kp_a, desc_a = _detect_and_describe(img_a, method)
    kp_b, desc_b = _detect_and_describe(img_b, method)
    kp_a, kp_b = kp_a or [], kp_b or []

    if desc_a is None or desc_b is None or len(kp_a) < 4 or len(kp_b) < 4:
        return _empty(method, len(kp_a), len(kp_b))

    # HOPC's descriptor is a real-valued (L2-comparable) histogram vector,
    # same as SIFT's -- only AKAZE's binary descriptor needs Hamming.
    norm = cv2.NORM_HAMMING if method == "akaze" else cv2.NORM_L2
    bf = cv2.BFMatcher(norm)
    raw = bf.knnMatch(desc_a, desc_b, k=2)
    good = [m for pair in raw if len(pair) == 2 for m, n in [pair] if m.distance < ratio * n.distance]

    if len(good) < 4:
        return _empty(method, len(kp_a), len(kp_b), len(raw), len(good))

    pts_a = np.float32([kp_a[m.queryIdx].pt for m in good])
    pts_b = np.float32([kp_b[m.trainIdx].pt for m in good])

    H, mask = cv2.findHomography(pts_a, pts_b, cv2.RANSAC, ransac_thresh)
    inlier_mask = mask.ravel().astype(bool) if mask is not None else np.zeros(len(good), dtype=bool)

    return MatchResult(
        method=method,
        keypoints_a=len(kp_a),
        keypoints_b=len(kp_b),
        raw_matches=len(raw),
        ratio_test_matches=len(good),
        inliers=int(inlier_mask.sum()),
        homography=H,
        pts_a=pts_a[inlier_mask],
        pts_b=pts_b[inlier_mask],
    )
