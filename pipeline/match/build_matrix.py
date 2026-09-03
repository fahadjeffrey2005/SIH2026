"""Build the full classical-vs-learned comparison matrix across every
overlapping, raster-available pair in the catalog, and write it to
docs/baseline_matrix.json for the frontend's metrics dashboard (and for
docs/baseline_results.md to cite) to read as data rather than everyone
re-deriving it by hand.

Which pairs go in the matrix isn't hardcoded: it's every combination of the
raster-available products (match.classical.demo's registries) whose real
footprint geometry genuinely overlaps (geo.quads_overlap against
data/catalog.sqlite) -- the same check the backend's /pairs/suggest makes.

Usage:
    python -m match.build_matrix [--out ../docs/baseline_matrix.json]
"""

from __future__ import annotations

import argparse
import itertools
import json
import sqlite3
import time
from pathlib import Path

import cv2

from geo import Footprint, quads_overlap

from .classical.demo import BROWSE_PRODUCTS, DATA_ROOT, IIRS_PRODUCTS
from .compare import run_pair
from .evaluate import geolocation_errors_m, summarize_errors
from .learned import matcher as learned_matcher

CATALOG_DB = DATA_ROOT / "catalog.sqlite"

# Where the interactive metrics-dashboard viewer's crop images live -- one
# pair of PNGs (the two crops, identical across all 3 methods within a
# pair) per matchable pair, referenced by filename from every method's row
# below so the frontend can load them without a separate lookup.
CELL_IMAGE_DIR = Path(__file__).resolve().parents[2] / "docs" / "img" / "matrix_cells"

# The keypoint-budget fix (docs/baseline_results.md's "Track B keypoint-
# budget fix"): DISK+LightGlue's max_keypoints default moved from 2048 to
# 4096 after finding 2048 was starving it of coverage on these low-texture
# crops. The interactive viewer's before/after toggle needs both variants'
# real points, not just the current default's -- this constant documents
# what "before" means without hardcoding 2048 in two places.
OLD_DISK_MAX_KEYPOINTS = 2048


def _row_corners(row: sqlite3.Row) -> dict:
    corners = {}
    for c in ("ul", "ur", "ll", "lr"):
        lat, lon = row[f"{c}_lat"], row[f"{c}_lon"]
        if lat is not None and lon is not None:
            corners[c] = (lat, lon)
    return corners


def matchable_pairs() -> list[dict]:
    has_raster = sorted(set(BROWSE_PRODUCTS) | set(IIRS_PRODUCTS))
    conn = sqlite3.connect(CATALOG_DB)
    conn.row_factory = sqlite3.Row
    rows = {r["product_id"]: r for r in conn.execute("SELECT * FROM products").fetchall()}
    conn.close()

    pairs = []
    for a, b in itertools.combinations(has_raster, 2):
        if a not in rows or b not in rows:
            continue
        fa = Footprint(a, _row_corners(rows[a]))
        fb = Footprint(b, _row_corners(rows[b]))
        if not quads_overlap(fa, fb):
            continue
        gap = None
        if rows[a]["solar_incidence_deg"] is not None and rows[b]["solar_incidence_deg"] is not None:
            gap = abs(rows[a]["solar_incidence_deg"] - rows[b]["solar_incidence_deg"])
        pairs.append({
            "product_a": a, "instrument_a": rows[a]["instrument"],
            "product_b": b, "instrument_b": rows[b]["instrument"],
            "incidence_gap_deg": gap,
        })
    pairs.sort(key=lambda p: (p["incidence_gap_deg"] is None, p["incidence_gap_deg"] or 0.0))
    return pairs


def _pair_key(product_a: str, product_b: str) -> str:
    return f"{product_a}__{product_b}"


def _points_payload(r) -> dict:
    """RANSAC-inlier points as plain JSON-serializable lists, in the same
    crop-pixel (x, y) coordinate space the saved crop images use -- this is
    exactly what the interactive viewer draws its correspondence lines
    from, no further transform needed on the frontend."""
    return {"points_a": r.pts_a.tolist(), "points_b": r.pts_b.tolist()}


def _old_disk_variant(ctx: dict) -> dict:
    """Re-runs DISK+LightGlue at the pre-fix keypoint budget (2048) against
    the exact same crops, for the interactive viewer's before/after toggle
    (see docs/baseline_results.md's "Track B keypoint-budget fix"). Real
    numbers, not fabricated: same code path, same crops, only the keypoint
    cap differs."""
    r_old = learned_matcher.match(ctx["crop_a"], ctx["crop_b"], max_keypoints=OLD_DISK_MAX_KEYPOINTS)
    errors_old = geolocation_errors_m(
        ctx["loaded_a"], ctx["origin_a"], ctx["scale_a"],
        ctx["loaded_b"], ctx["origin_b"], ctx["scale_b"],
        r_old.pts_a, r_old.pts_b,
    )
    return {
        "max_keypoints": OLD_DISK_MAX_KEYPOINTS,
        "raw_matches": r_old.raw_matches,
        "inliers": r_old.inliers,
        "inlier_ratio": r_old.inlier_ratio,
        "geoloc_median_m": summarize_errors(errors_old)["median_m"],
        **_points_payload(r_old),
    }


def build(out_path: Path) -> dict:
    pairs = matchable_pairs()
    rows = []
    CELL_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    for pair in pairs:
        t0 = time.time()
        out = run_pair(pair["product_a"], pair["product_b"])
        results, geoloc, point_errors, ctx = out["results"], out["geoloc"], out["point_errors"], out["context"]
        elapsed = time.time() - t0
        print(f"{pair['product_a']} <-> {pair['product_b']} "
              f"(gap {pair['incidence_gap_deg']:.1f}°): {elapsed:.1f}s")

        # One pair of crop images per pair (identical across its 3 method
        # rows) for the interactive viewer -- saved once here, referenced
        # by filename from every row below.
        key = _pair_key(pair["product_a"], pair["product_b"])
        image_a_file, image_b_file = f"{key}__a.png", f"{key}__b.png"
        png_params = [cv2.IMWRITE_PNG_COMPRESSION, 9]
        cv2.imwrite(str(CELL_IMAGE_DIR / image_a_file), ctx["crop_a"], png_params)
        cv2.imwrite(str(CELL_IMAGE_DIR / image_b_file), ctx["crop_b"], png_params)

        for method, r in results.items():
            raw = getattr(r, "ratio_test_matches", None)
            if raw is None:
                raw = r.raw_matches
            g = geoloc[method]
            row = {
                **pair,
                "method": method,
                "keypoints_a": r.keypoints_a,
                "keypoints_b": r.keypoints_b,
                "raw_matches": raw,
                "inliers": r.inliers,
                "inlier_ratio": r.inlier_ratio,
                "geoloc_median_m": g["median_m"],
                "geoloc_p90_m": g["p90_m"],
                "crop_image_a": image_a_file,
                "crop_image_b": image_b_file,
                "point_geoloc_errors_m": point_errors[method].tolist(),
                **_points_payload(r),
            }
            if method == "disk_lightglue":
                row["keypoint_budget_comparison"] = {
                    "new": {
                        "max_keypoints": 4096,
                        "raw_matches": raw,
                        "inliers": r.inliers,
                        "inlier_ratio": r.inlier_ratio,
                        "geoloc_median_m": g["median_m"],
                        **_points_payload(r),
                    },
                    "old": _old_disk_variant(ctx),
                }
            rows.append(row)
            med_str = f"{g['median_m']:.0f}m" if g["median_m"] is not None else "-"
            print(f"  {method:<16} kp={r.keypoints_a}/{r.keypoints_b} "
                  f"raw={raw} inliers={r.inliers} ({r.inlier_ratio:.0%}) geoloc_median={med_str}")

    matrix = {"generated_from": "pipeline/match/build_matrix.py", "rows": rows}
    out_path.write_text(json.dumps(matrix, indent=2))
    print(f"\nwrote {len(rows)} rows and {len(pairs) * 2} crop images -> {out_path}")
    return matrix


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[2] / "docs" / "baseline_matrix.json"))
    args = ap.parse_args()
    build(Path(args.out))


if __name__ == "__main__":
    main()
