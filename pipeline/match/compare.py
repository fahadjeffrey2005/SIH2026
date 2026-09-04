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
from .evaluate import geolocation_errors_m, summarize_errors
from .learned import matcher as learned_matcher


def run_pair(id_a: str, id_b: str, out_dir: Optional[Path] = None) -> dict:
    """Returns {"results": {method: MatchResult}, "geoloc": {method: summary},
    "point_errors": {method: np.ndarray}, "context": {...}}.

    `geoloc` is the independent accuracy check from match.evaluate -- see
    that module's docstring for why inlier counts/ratios alone aren't
    enough to compare methods across pairs at different working GSDs.
    `point_errors` is that same check's *per-correspondence* array before
    it gets collapsed into `geoloc`'s median/p90 summary -- kept around for
    callers (build_matrix.py's interactive-viewer export) that want to show
    an individual matched point's own disagreement, not just the aggregate.

    `context` exposes the loaded products, crops, and crop-placement info
    (origin/scale) this function already computed internally, so a caller
    can re-run additional method variants against the exact same crops
    (e.g. build_matrix.py's old-vs-new DISK+LightGlue keypoint-budget
    comparison) without reloading/re-cropping from scratch."""
    a = load(id_a)
    b = load(id_b)
    target_gsd = max(browse_gsd_m(a), browse_gsd_m(b))
    scale_a = browse_gsd_m(a) / target_gsd
    scale_b = browse_gsd_m(b) / target_gsd
    crop_a, origin_a = prep_crop(a, b, target_gsd)
    crop_b, origin_b = prep_crop(b, a, target_gsd)

    results = {}
    for method in ("sift", "akaze", "hopc"):
        results[method] = classical_matcher.match(crop_a, crop_b, method=method)
    results["disk_lightglue"] = learned_matcher.match(crop_a, crop_b)

    geoloc = {}
    point_errors = {}
    for method, r in results.items():
        errors = geolocation_errors_m(a, origin_a, scale_a, b, origin_b, scale_b, r.pts_a, r.pts_b)
        point_errors[method] = errors
        geoloc[method] = summarize_errors(errors)

    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
        for method, r in results.items():
            cv2.imwrite(str(out_dir / f"{id_a}__{id_b}__{method}.png"), draw_matches(crop_a, crop_b, r))

    context = {
        "loaded_a": a, "loaded_b": b,
        "crop_a": crop_a, "crop_b": crop_b,
        "origin_a": origin_a, "origin_b": origin_b,
        "scale_a": scale_a, "scale_b": scale_b,
    }
    return {"results": results, "geoloc": geoloc, "point_errors": point_errors, "context": context}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("id_a")
    ap.add_argument("id_b")
    ap.add_argument("--out-dir", default=None, help="directory to save one match-overlay PNG per method")
    args = ap.parse_args()

    try:
        out = run_pair(args.id_a, args.id_b, Path(args.out_dir) if args.out_dir else None)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None

    results, geoloc = out["results"], out["geoloc"]
    print(f"{args.id_a} <-> {args.id_b}")
    print(f"{'method':<16} {'keypoints':<14} {'raw matches':<12} {'inliers':<8} {'inlier %':<9} {'geoloc median':<14} {'p90':<10}")
    for method, r in results.items():
        kp = f"{r.keypoints_a}/{r.keypoints_b}"
        raw = getattr(r, "ratio_test_matches", None)
        if raw is None:
            raw = r.raw_matches
        g = geoloc[method]
        med = f"{g['median_m']:.0f} m" if g["median_m"] is not None else "-"
        p90 = f"{g['p90_m']:.0f} m" if g["p90_m"] is not None else "-"
        print(f"{method:<16} {kp:<14} {raw:<12} {r.inliers:<8} {r.inlier_ratio:.0%}      {med:<14} {p90:<10}")


if __name__ == "__main__":
    main()
