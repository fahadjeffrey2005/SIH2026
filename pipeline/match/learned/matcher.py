"""Track B: pretrained learned matching (DISK + LightGlue, via kornia).

Why DISK+LightGlue and not LoFTR: docs/architecture.md originally named
LoFTR/LightGlue as the candidates. LoFTR's only pretrained weights kornia
ships (loftr_outdoor.ckpt) are hosted on cmp.felk.cvut.cz, which this
environment's egress policy blocks. DISK's weights (raw.githubusercontent.com)
and LightGlue's ("disk" flavor, github.com/cvg/LightGlue releases) both come
from GitHub, which is reachable -- so DISK (detector+descriptor) paired with
LightGlue (matcher) is the learned baseline that's actually runnable here,
not a change of plan for its own sake.

This is used *zero-shot*: both networks are pretrained on terrestrial photo
datasets (DISK on MegaDepth; LightGlue's "disk" weights on the same), with
no lunar-imagery fine-tuning. Whether that transfers at all to this domain
is an open, and answered, question -- see docs/baseline_results.md. Report
the number, don't assume it beats the classical track.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import cv2
import kornia.feature as KF
import numpy as np
import torch

_DISK = None
_LIGHTGLUE = None


def _get_models(checkpoint: str = "depth"):
    global _DISK, _LIGHTGLUE
    if _DISK is None:
        _DISK = KF.DISK.from_pretrained(checkpoint).eval()
    if _LIGHTGLUE is None:
        _LIGHTGLUE = KF.LightGlue("disk").eval()
    return _DISK, _LIGHTGLUE


@dataclass
class LearnedMatchResult:
    method: str
    keypoints_a: int
    keypoints_b: int
    raw_matches: int
    inliers: int
    homography: Optional[np.ndarray]
    pts_a: np.ndarray  # inlier points in image A, Nx2 (x, y)
    pts_b: np.ndarray  # inlier points in image B, Nx2 (x, y)

    @property
    def inlier_ratio(self) -> float:
        return self.inliers / self.raw_matches if self.raw_matches else 0.0


def _to_tensor(img: np.ndarray) -> torch.Tensor:
    """Grayscale uint8 HxW -> 1x3xHxW float tensor in [0,1] (DISK expects
    3-channel input; we just repeat the single band -- these are
    already-panchromatic/single-band rasters, there's no color information
    to lose)."""
    t = torch.from_numpy(img).float()[None, None] / 255.0
    return t.repeat(1, 3, 1, 1)


def match(
    img_a: np.ndarray,
    img_b: np.ndarray,
    max_keypoints: int = 2048,
    ransac_thresh: float = 4.0,
    checkpoint: str = "depth",
) -> LearnedMatchResult:
    """Detect with DISK, match with LightGlue, RANSAC-filter a homography --
    the same post-processing as match.classical.matcher.match, so the two
    tracks' outputs are directly comparable field-for-field.

    No resizing beyond what the caller already did (match.classical.demo's
    prep_crop, which aligns both crops to a common working GSD): unlike
    LoFTR's dense coarse-to-fine transformer (O(pixels^2) attention -- not
    practical on these thousands-of-pixels-long pushbroom crops on CPU),
    DISK+LightGlue's cost scales with `max_keypoints`, not image area, so
    there's no need to downsample these already-narrow strips further (an
    early attempt at capping the long side to 1024px crushed the short axis
    down to ~30-40px and destroyed almost all cross-track texture -- worth
    remembering if a change here reintroduces that).
    """
    disk, lightglue = _get_models(checkpoint)
    ta, tb = _to_tensor(img_a), _to_tensor(img_b)

    with torch.no_grad():
        feats_a = disk(ta, n=max_keypoints, pad_if_not_divisible=True)[0]
        feats_b = disk(tb, n=max_keypoints, pad_if_not_divisible=True)[0]

        if len(feats_a.keypoints) < 4 or len(feats_b.keypoints) < 4:
            return LearnedMatchResult(
                "disk_lightglue", len(feats_a.keypoints), len(feats_b.keypoints), 0, 0,
                None, np.zeros((0, 2), dtype=np.float32), np.zeros((0, 2), dtype=np.float32),
            )

        out = lightglue({
            "image0": {
                "keypoints": feats_a.keypoints[None],
                "descriptors": feats_a.descriptors[None],
                "image_size": torch.tensor(ta.shape[-2:][::-1])[None],
            },
            "image1": {
                "keypoints": feats_b.keypoints[None],
                "descriptors": feats_b.descriptors[None],
                "image_size": torch.tensor(tb.shape[-2:][::-1])[None],
            },
        })

    raw = out["matches"][0].numpy()
    n_kp_a, n_kp_b = len(feats_a.keypoints), len(feats_b.keypoints)

    if len(raw) < 4:
        return LearnedMatchResult(
            "disk_lightglue", n_kp_a, n_kp_b, len(raw), 0, None,
            np.zeros((0, 2), dtype=np.float32), np.zeros((0, 2), dtype=np.float32),
        )

    pts_a = feats_a.keypoints.numpy()[raw[:, 0]]
    pts_b = feats_b.keypoints.numpy()[raw[:, 1]]

    H, mask = cv2.findHomography(pts_a, pts_b, cv2.RANSAC, ransac_thresh)
    inlier_mask = mask.ravel().astype(bool) if mask is not None else np.zeros(len(raw), dtype=bool)

    return LearnedMatchResult(
        method="disk_lightglue",
        keypoints_a=n_kp_a,
        keypoints_b=n_kp_b,
        raw_matches=len(raw),
        inliers=int(inlier_mask.sum()),
        homography=H,
        pts_a=pts_a[inlier_mask],
        pts_b=pts_b[inlier_mask],
    )
