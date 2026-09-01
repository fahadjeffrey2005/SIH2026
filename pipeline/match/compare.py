"""Run both matching tracks (classical SIFT/AKAZE + learned DISK/LightGlue)
on one product pair and print a side-by-side comparison -- this is the
number the project's actual "sun-angle-invariance" claim rests on
(docs/architecture.md Sec. 5.4's crossed table, in miniature).

Usage:
    python -m match.compare <id_a> <id_b> [--out-dir /tmp]
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

import cv2

from .classical import matcher as classical_matcher
from .classical.demo import browse_gsd_m, draw_matches, load, prep_crop
from .learned import matcher as learned_matcher


def run_pair(id_a: str, id_b: str, out_dir: Optional[Path] = None) -> dict:
    a = load(id_a)
    b = load(id_b)
    target_gsd = max(browse_gsd_m(a), browse_gsd_m(b))
    crop_a, _ = prep_crop(a, b, target_gsd)
    crop_b, _ = prep_crop(b, a, target_gsd)

    results = {}
    for method in ("sift", "akaze"):
        results[method] = classical_matcher.match(crop_a, crop_b, method=method)
    results["disk_lightglue"] = learned_matcher.match(crop_a, crop_b)

    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
        for method, r in results.items():
            cv2.imwrite(str(out_dir / f"{id_a}__{id_b}__{method}.png"), draw_matches(crop_a, crop_b, r))

    return results


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("id_a")
    ap.add_argument("id_b")
    ap.add_argument("--out-dir", default=None, help="directory to save one match-overlay PNG per method")
    args = ap.parse_args()

    try:
        results = run_pair(args.id_a, args.id_b, Path(args.out_dir) if args.out_dir else None)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None

    print(f"{args.id_a} <-> {args.id_b}")
    print(f"{'method':<16} {'keypoints':<14} {'raw matches':<12} {'inliers':<8} {'inlier %':<9}")
    for method, r in results.items():
        kp = f"{r.keypoints_a}/{r.keypoints_b}"
        raw = getattr(r, "ratio_test_matches", None)
        if raw is None:
            raw = r.raw_matches
        print(f"{method:<16} {kp:<14} {raw:<12} {r.inliers:<8} {r.inlier_ratio:.0%}")


if __name__ == "__main__":
    main()
