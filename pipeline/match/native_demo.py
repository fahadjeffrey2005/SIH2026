"""Native-resolution follow-up on one specific pair: OHRC 2021-04-05 vs
TMC-2 2025-08-07 (the 34.7 deg sun-incidence-gap pair that found zero
matches at the 1/10-browse resolution match.classical.demo.py normally
uses -- see docs/baseline_results.md's main matrix). Reads the two small
pre-cropped PNGs `pipeline/tools/extract_native_crop.py` produces (checked
into data/native_crops/, no need to regenerate them to just re-run this)
and runs the same classical + learned matching and geolocation-agreement
evaluation as match.compare, so the numbers are directly comparable.

Why this is a separate script rather than a new match.classical.demo.py
BROWSE_PRODUCTS-style registration: that registry assumes a uniform
"load a browse PNG at NOMINAL_GSD_M x BROWSE_DOWNSAMPLE" model for every
product. Native OHRC/TMC-2 rasters are 300MB-2.2GB uncompressed each (see
pipeline/tools/extract_native_crop.py's docstring) -- not something this
pipeline environment keeps staged -- so "loading" a native product here
actually means "reading the specific small crop someone already extracted
elsewhere for this specific pair," which is a different enough contract
that forcing it into the general demo.py loader would obscure more than it
clarifies. This script documents that contract explicitly instead.

Working resolution for this pair: 5m/px (TMC-2's own native GSD -- its
crop needs no resize). OHRC's native GSD is 0.25m, so its crop is
downsampled 20x, same ratio as the browse-resolution run (2.5m browse ->
50m target was also a 20x reduction) -- the difference is that here TMC-2
itself is at its true native 5m/px, not degraded 10x to a 50m/px browse
thumbnail first. That's the whole effect being tested.

Usage:
    python -m match.native_demo
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2

from geo import BilinearGeoTransform
from ingest.pds4_label import parse_label
from preprocess import clahe_normalize

from .classical import matcher as classical_matcher
from .classical.demo import draw_matches
from .evaluate import geolocation_errors_m, summarize_errors
from .learned import matcher as learned_matcher

DATA_ROOT = Path(__file__).resolve().parents[2] / "data"

OHRC_XML = DATA_ROOT / "raw/ohrc/ch2_ohr_ncp_20210405T1606536730_d_img_d18.xml"
TMC2_XML = DATA_ROOT / "raw/tmc2/ch2_tmc_ncf_20250807T1904346039_d_img_d18.xml"
OHRC_CROP_PNG = DATA_ROOT / "native_crops/ohrc_native5m_crop.png"
TMC2_CROP_PNG = DATA_ROOT / "native_crops/tmc2_native5m_crop.png"

# Native Axis_Array dimensions from each product's own PDS4 label (see
# extract_native_crop.py's docstring for the byte-size cross-check) --
# BilinearGeoTransform needs the FULL native image's shape, not the crop's,
# since pixel_to_lonlat's (u, v) fractions are defined over the whole frame.
OHRC_NATIVE_SHAPE = (93693, 12000)  # (n_lines, n_samples)
TMC2_NATIVE_SHAPE = (295234, 4000)

# Where each crop sits in its own product's native pixel grid, and the
# resize factor applied (see extract_native_crop.py) -- both needed to map
# a point in the crop PNG back to native-image pixel coordinates for the
# geolocation-agreement check.
OHRC_ORIGIN, OHRC_RESIZE_SCALE = (0, 0), 0.25 / 5.0  # 20x downsample to 5m/px
TMC2_ORIGIN, TMC2_RESIZE_SCALE = (279899, 2451), 1.0  # already native 5m/px


@dataclass
class _Loaded:
    transform: BilinearGeoTransform


def main():
    ohrc_label = parse_label(OHRC_XML)
    tmc2_label = parse_label(TMC2_XML)
    ohrc_loaded = _Loaded(BilinearGeoTransform(ohrc_label.corners, *OHRC_NATIVE_SHAPE))
    tmc2_loaded = _Loaded(BilinearGeoTransform(tmc2_label.corners, *TMC2_NATIVE_SHAPE))

    crop_a = clahe_normalize(cv2.imread(str(OHRC_CROP_PNG), cv2.IMREAD_UNCHANGED))
    crop_b = clahe_normalize(cv2.imread(str(TMC2_CROP_PNG), cv2.IMREAD_UNCHANGED))
    print(f"OHRC crop: {crop_a.shape} (native 0.25m/px, downsampled 20x -> 5m/px)")
    print(f"TMC-2 crop: {crop_b.shape} (native 5m/px, no resize)")
    print()

    results = {}
    for method in ("sift", "akaze"):
        results[method] = classical_matcher.match(crop_a, crop_b, method=method)
    results["disk_lightglue"] = learned_matcher.match(crop_a, crop_b)

    print(f"{'method':<16} {'keypoints':<14} {'raw matches':<12} {'inliers':<8} {'inlier %':<9} {'geoloc median':<14} {'p90':<10}")
    for method, r in results.items():
        kp = f"{r.keypoints_a}/{r.keypoints_b}"
        raw = getattr(r, "ratio_test_matches", None)
        if raw is None:
            raw = r.raw_matches
        errors = geolocation_errors_m(
            ohrc_loaded, OHRC_ORIGIN, OHRC_RESIZE_SCALE,
            tmc2_loaded, TMC2_ORIGIN, TMC2_RESIZE_SCALE,
            r.pts_a, r.pts_b,
        )
        g = summarize_errors(errors)
        med = f"{g['median_m']:.0f} m" if g["median_m"] is not None else "-"
        p90 = f"{g['p90_m']:.0f} m" if g["p90_m"] is not None else "-"
        print(f"{method:<16} {kp:<14} {raw:<12} {r.inliers:<8} {r.inlier_ratio:.0%}      {med:<14} {p90:<10}")

    out = Path("/tmp/native_ohrc_tmc2025_sift.png")
    cv2.imwrite(str(out), draw_matches(crop_a, crop_b, results["sift"]))
    print(f"\nsaved SIFT match visualization -> {out}")


if __name__ == "__main__":
    main()
