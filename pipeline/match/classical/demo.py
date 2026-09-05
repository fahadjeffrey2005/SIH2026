"""End-to-end classical-matching demo on the true geometric overlap between
two products: crop with footprint geometry, normalize illumination, run
SIFT/AKAZE + RANSAC.

Usage:
    python -m match.classical.demo <id_a> <id_b> [--method sift|akaze] [--out out.png]

Example (the real cross-instrument, high-sun-angle-gap pair confirmed
overlapping in docs/architecture.md / README.md):
    python -m match.classical.demo \\
        ch2_ohr_ncp_20210405t1606536730_d_img_d18 \\
        ch2_tmc_ncf_20250807t1904346039_d_img_d18 --out /tmp/match.png

Currently wired to browse-resolution PNGs (data/browse/, README.md's data
table) rather than the native full-resolution OHRC/TMC-2 rasters, which
haven't been staged into this environment (they're 300-800MB zips). Each
OHRC/TMC-2 browse PNG is a verified-exact 1/10 downsample of its native
raster (checked against the label's own Axis_Array line/sample counts), so
a BilinearGeoTransform built with n_lines/n_samples = the browse image's
own shape maps its pixel coordinates correctly. IIRS's entry is different
in kind, not just source: it's the exact native-resolution band-40 array
(no downsampling at all), just persisted as a small PNG instead of being
re-read from its 681MB native cube on every load -- see the comment above
IIRS's entry below for how it was produced and how to regenerate it.
Swap BROWSE_PRODUCTS's OHRC/TMC-2 entries for native-raster paths (via
ingest.reader.load_product) once those are staged -- nothing else here
needs to change.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from geo import BilinearGeoTransform, Footprint, overlap_crop
from ingest.pds4_label import parse_label
from preprocess import clahe_normalize

from .matcher import match

DATA_ROOT = Path(__file__).resolve().parents[3] / "data"

# Native ground sample distance (meters/pixel) per instrument -- see
# docs/architecture.md Sec. 1 (problem restatement).
NOMINAL_GSD_M = {"OHRC": 0.25, "TMC-2": 5.0, "IIRS": 80.0}

# Verified against each label's Axis_Array line/sample counts vs. the browse
# PNG's actual shape (see conversation notes / build log): exactly 10x for
# OHRC/TMC-2's registered browse-PNG products. IIRS's factor is unused --
# see browse_gsd_m below, it's keyed off instrument, not off which dict a
# product came from.
BROWSE_DOWNSAMPLE = 10

# instrument -> source products: (xml relative path, png relative path).
# OHRC/TMC-2 entries are the browse-preview PNGs pulled straight out of the
# product zips during data acquisition (1/10 native resolution, see the
# module docstring). IIRS's entry is a full-native-resolution derivative,
# not a downsample: generated once from the real 681MB PDS4 cube via
#     from ingest.reader import load_product
#     from preprocess import to_uint8
#     band = to_uint8(load_product(<iirs xml path>).band(40))
#     cv2.imwrite("data/browse/ch2_iir_nri_20211221T0324126144_d_img_hw1_band40.png", band)
# -- the exact same band-40-via-to_uint8 array every documented IIRS result
# in docs/baseline_results.md was already computed from; reading it back
# with cv2.imread(..., cv2.IMREAD_UNCHANGED) was verified byte-identical to
# that in-memory array before this file started using it, so folding IIRS
# into this dict changes nothing about any existing result -- it only
# avoids needing the 681MB cube (which isn't committed to git) at load
# time. Regenerate this PNG with the 4 lines above if IIRS data changes.
BROWSE_PRODUCTS = {
    "ch2_ohr_ncp_20210405t1606536730_d_img_d18": (
        "raw/ohrc/ch2_ohr_ncp_20210405T1606536730_d_img_d18.xml",
        "browse/ch2_ohr_ncp_20210405T1606536730_d_img_d18.png",
    ),
    "ch2_tmc_ncf_20240125t0622476078_d_img_d18": (
        "raw/tmc2/ch2_tmc_ncf_20240125T0622476078_d_img_d18.xml",
        "browse/ch2_tmc_ncf_20240125T0622476078_d_img_d18.png",
    ),
    "ch2_tmc_ncf_20250807t1904346039_d_img_d18": (
        "raw/tmc2/ch2_tmc_ncf_20250807T1904346039_d_img_d18.xml",
        "browse/ch2_tmc_ncf_20250807T1904346039_d_img_d18.png",
    ),
    "ch2_iir_nri_20211221t0324126144_d_img_hw1": (
        "raw/iirs/ch2_iir_nri_20211221/data/raw/20211221/ch2_iir_nri_20211221T0324126144_d_img_hw1.xml",
        "browse/ch2_iir_nri_20211221T0324126144_d_img_hw1_band40.png",
    ),
}


@dataclass
class Loaded:
    product_id: str
    instrument: str
    footprint: Footprint
    transform: BilinearGeoTransform
    image: np.ndarray


def load(product_id: str) -> Loaded:
    """Raises `ValueError` (not `SystemExit`) on any lookup/read failure --
    this is imported as a library by backend/app/jobs.py, not just run as a
    CLI, and SystemExit isn't an Exception subclass: it would sail straight
    past a background job's `except Exception`, leaving the job stuck
    "running" forever instead of recorded as "failed" (caught the hard way
    while testing the backend -- see docs/baseline_results.md history)."""
    if product_id in BROWSE_PRODUCTS:
        xml_rel, png_rel = BROWSE_PRODUCTS[product_id]
        label = parse_label(DATA_ROOT / xml_rel)
        image = cv2.imread(str(DATA_ROOT / png_rel), cv2.IMREAD_UNCHANGED)
        if image is None:
            raise ValueError(f"failed to read {DATA_ROOT / png_rel}")
    else:
        raise ValueError(
            f"no data registered for {product_id!r}. Available: {sorted(BROWSE_PRODUCTS)}"
        )

    footprint = Footprint(product_id, label.corners)
    transform = BilinearGeoTransform(label.corners, n_lines=image.shape[0], n_samples=image.shape[1])
    return Loaded(product_id, label.instrument, footprint, transform, image)


def browse_gsd_m(loaded: Loaded) -> float:
    """Effective ground sample distance of the loaded raster: for OHRC/TMC-2
    this is the browse PNG (native GSD x the verified browse downsample
    factor); IIRS is loaded at native resolution so no downsample applies."""
    factor = 1 if loaded.instrument == "IIRS" else BROWSE_DOWNSAMPLE
    return NOMINAL_GSD_M[loaded.instrument] * factor


def prep_crop(loaded: Loaded, other: Loaded, target_gsd_m: float) -> tuple[np.ndarray, tuple[int, int]]:
    row0, row1, col0, col1 = overlap_crop(loaded.footprint, loaded.transform, other.footprint)
    crop = loaded.image[row0:row1, col0:col1]

    scale = browse_gsd_m(loaded) / target_gsd_m
    if abs(scale - 1.0) > 0.02:
        interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
        crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=interp)
    return clahe_normalize(crop), (row0, col0)


def draw_matches(img_a: np.ndarray, img_b: np.ndarray, result) -> np.ndarray:
    kp_a = [cv2.KeyPoint(float(x), float(y), 5) for x, y in result.pts_a]
    kp_b = [cv2.KeyPoint(float(x), float(y), 5) for x, y in result.pts_b]
    dmatches = [cv2.DMatch(i, i, 0) for i in range(len(kp_a))]
    return cv2.drawMatches(
        img_a, kp_a, img_b, kp_b, dmatches, None,
        flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS,
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("id_a")
    ap.add_argument("id_b")
    ap.add_argument("--method", choices=["sift", "akaze", "hopc"], default="sift")
    ap.add_argument("--out", default=None, help="path to save a match visualization PNG")
    args = ap.parse_args()

    try:
        a = load(args.id_a)
        b = load(args.id_b)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None

    # Work at the coarser instrument's GSD -- downsample the finer image
    # rather than upsampling the coarser one, which would just invent detail
    # for SIFT/AKAZE to spuriously "match" on.
    target_gsd = max(browse_gsd_m(a), browse_gsd_m(b))

    crop_a, origin_a = prep_crop(a, b, target_gsd)
    crop_b, origin_b = prep_crop(b, a, target_gsd)

    print(f"{a.product_id} ({a.instrument}): crop {crop_a.shape}, "
          f"origin(row,col)={origin_a}, native GSD {NOMINAL_GSD_M[a.instrument]}m")
    print(f"{b.product_id} ({b.instrument}): crop {crop_b.shape}, "
          f"origin(row,col)={origin_b}, native GSD {NOMINAL_GSD_M[b.instrument]}m")
    print(f"working resolution: ~{target_gsd:.1f} m/px")

    result = match(crop_a, crop_b, method=args.method)
    print(f"[{result.method}] keypoints: {result.keypoints_a} / {result.keypoints_b}")
    print(f"  ratio-test matches: {result.ratio_test_matches}")
    print(f"  RANSAC inliers: {result.inliers} ({result.inlier_ratio:.1%} of ratio-test matches)")

    if args.out:
        vis = draw_matches(crop_a, crop_b, result)
        cv2.imwrite(args.out, vis)
        print(f"  saved visualization -> {args.out}")


if __name__ == "__main__":
    main()
