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

from geo import Footprint, quads_overlap

from .classical.demo import BROWSE_PRODUCTS, DATA_ROOT, IIRS_PRODUCTS
from .compare import run_pair

CATALOG_DB = DATA_ROOT / "catalog.sqlite"


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


def build(out_path: Path) -> dict:
    pairs = matchable_pairs()
    rows = []
    for pair in pairs:
        t0 = time.time()
        out = run_pair(pair["product_a"], pair["product_b"])
        results, geoloc = out["results"], out["geoloc"]
        elapsed = time.time() - t0
        print(f"{pair['product_a']} <-> {pair['product_b']} "
              f"(gap {pair['incidence_gap_deg']:.1f}°): {elapsed:.1f}s")
        for method, r in results.items():
            raw = getattr(r, "ratio_test_matches", None)
            if raw is None:
                raw = r.raw_matches
            g = geoloc[method]
            rows.append({
                **pair,
                "method": method,
                "keypoints_a": r.keypoints_a,
                "keypoints_b": r.keypoints_b,
                "raw_matches": raw,
                "inliers": r.inliers,
                "inlier_ratio": r.inlier_ratio,
                "geoloc_median_m": g["median_m"],
                "geoloc_p90_m": g["p90_m"],
            })
            med_str = f"{g['median_m']:.0f}m" if g["median_m"] is not None else "-"
            print(f"  {method:<16} kp={r.keypoints_a}/{r.keypoints_b} "
                  f"raw={raw} inliers={r.inliers} ({r.inlier_ratio:.0%}) geoloc_median={med_str}")

    matrix = {"generated_from": "pipeline/match/build_matrix.py", "rows": rows}
    out_path.write_text(json.dumps(matrix, indent=2))
    print(f"\nwrote {len(rows)} rows -> {out_path}")
    return matrix


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[2] / "docs" / "baseline_matrix.json"))
    args = ap.parse_args()
    build(Path(args.out))


if __name__ == "__main__":
    main()
