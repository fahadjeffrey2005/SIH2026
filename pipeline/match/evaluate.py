"""Independent accuracy metric for match results: geolocation agreement.

Everything reported in docs/baseline_results.md so far (inlier counts,
inlier ratios) measures *internal* consistency -- whether a set of matched
points fits a single homography well enough to survive RANSAC. That says
nothing about whether the matched points are actually the same spot on the
lunar surface; a homography can fit a self-consistent but wrong set of
correspondences just as happily as a correct one, and inlier ratios aren't
even comparable across pairs since RANSAC's pixel threshold means something
different at each pair's working GSD.

Every product's PDS4 corner geolocation (geo.BilinearGeoTransform) gives an
independent way to check this: project each inlier match's pixel coordinates
in *both* images back to (lat, lon) using their own product's own transform,
and measure the great-circle distance between the two estimates. A
correspondence on the same physical point should agree to roughly the size
of each product's own georeferencing error; a mismatch reports the actual
disagreement in meters -- a real, physically-interpretable number that's
directly comparable across pairs, methods, and instruments, unlike inlier
ratios.

Caveat inherited from geo/transform.py: BilinearGeoTransform is *pseudo*
ground truth (a single bilinear quad per product, not a bundle-adjusted
sensor model), so this metric's floor is each product's own corner-geolocation
precision, not zero. It's still an independent, physically-grounded check
that inlier-ratio alone can't provide -- see docs/baseline_results.md for how
these numbers read in practice.
"""

from __future__ import annotations

import math

import numpy as np

# IAU mean lunar radius (m) -- same value used earlier in this project for
# decoding the Chandrayaan-3 landing-zone polar-stereographic projection
# (EPSG:100011), kept consistent here for the same body.
MOON_RADIUS_M = 1_737_400.0


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * MOON_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def crop_point_to_lonlat(loaded, origin: tuple[int, int], resize_scale: float, x: float, y: float) -> tuple[float, float]:
    """Map a point (x, y) = (col, row) in a match.classical.demo.prep_crop
    output -- i.e. already cropped to `origin` and resized by `resize_scale`
    -- back to (lat, lon) via `loaded`'s own BilinearGeoTransform, which is
    defined over `loaded.image`'s original (uncropped, unresized) pixel
    grid. Inverts prep_crop's two transforms in order: undo the GSD resize,
    then add back the crop's (row0, col0) origin."""
    row0, col0 = origin
    row = row0 + y / resize_scale
    col = col0 + x / resize_scale
    return loaded.transform.pixel_to_lonlat(row, col)


def geolocation_errors_m(
    loaded_a, origin_a: tuple[int, int], scale_a: float,
    loaded_b, origin_b: tuple[int, int], scale_b: float,
    pts_a: np.ndarray, pts_b: np.ndarray,
) -> np.ndarray:
    """Great-circle distance (meters) between each pts_a[i]/pts_b[i]
    correspondence's independently-derived lat/lon, via each product's own
    corner geolocation. `pts_a`/`pts_b` are Nx2 (x, y) arrays in the same
    coordinate space match.*.matcher.match() was called on (i.e. the
    prep_crop output) -- typically a MatchResult's inlier pts_a/pts_b.
    Empty input returns an empty array rather than raising, since a
    zero-match result is a normal, expected outcome throughout this
    project."""
    if len(pts_a) == 0:
        return np.zeros(0, dtype=np.float64)
    errors = np.empty(len(pts_a), dtype=np.float64)
    for i, ((xa, ya), (xb, yb)) in enumerate(zip(pts_a, pts_b)):
        lat_a, lon_a = crop_point_to_lonlat(loaded_a, origin_a, scale_a, xa, ya)
        lat_b, lon_b = crop_point_to_lonlat(loaded_b, origin_b, scale_b, xb, yb)
        errors[i] = _haversine_m(lat_a, lon_a, lat_b, lon_b)
    return errors


def summarize_errors(errors: np.ndarray) -> dict:
    """Summary stats for a matrix/report row. None fields (not 0) when there
    are no inliers to evaluate -- a genuine "nothing to measure" case,
    distinct from "measured and found 0m agreement"."""
    if len(errors) == 0:
        return {"n": 0, "median_m": None, "mean_m": None, "p90_m": None, "max_m": None}
    return {
        "n": int(len(errors)),
        "median_m": float(np.median(errors)),
        "mean_m": float(np.mean(errors)),
        "p90_m": float(np.percentile(errors, 90)),
        "max_m": float(np.max(errors)),
    }
