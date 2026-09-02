"""match.evaluate: the geolocation-agreement accuracy metric.

Unlike inlier counts/ratios (internal consistency only), this checks each
correspondence against each product's own PDS4 corner geolocation
independently -- see match/evaluate.py's docstring. These tests pin down
the coordinate-frame bookkeeping (crop origin + GSD-resize inversion) that
metric depends on, since getting that wrong would silently under- or
over-state every reported accuracy number without ever crashing.
"""

from dataclasses import dataclass

import numpy as np
import pytest

from geo.transform import BilinearGeoTransform
from match.evaluate import _haversine_m, crop_point_to_lonlat, geolocation_errors_m, summarize_errors

# A small, clearly non-square quad (~1km scale) so lat and lon aren't
# accidentally interchangeable in a bug.
CORNERS = {
    "ul": (-2.000000, -23.500000),
    "ur": (-2.000000, -23.490000),
    "ll": (-2.010000, -23.500000),
    "lr": (-2.010000, -23.490000),
}


@dataclass
class _StubLoaded:
    transform: BilinearGeoTransform


def _make_loaded(n_lines=1000, n_samples=1000) -> _StubLoaded:
    return _StubLoaded(BilinearGeoTransform(CORNERS, n_lines=n_lines, n_samples=n_samples))


def test_haversine_matches_small_angle_approximation():
    """For a short north-south hop, great-circle distance should reduce to
    radius * delta_lat_rad to within a fraction of a percent."""
    lat1, lon = -2.0, -23.5
    delta_deg = 0.01
    lat2 = lat1 - delta_deg
    d = _haversine_m(lat1, lon, lat2, lon)
    expected = 1_737_400.0 * np.radians(delta_deg)
    assert d == pytest.approx(expected, rel=1e-3)


def test_haversine_zero_for_identical_point():
    assert _haversine_m(-2.0, -23.5, -2.0, -23.5) == pytest.approx(0.0, abs=1e-9)


def test_crop_point_to_lonlat_identity_when_no_crop_or_resize():
    """origin=(0,0), scale=1.0 should be a pure passthrough to
    transform.pixel_to_lonlat -- this is the case prep_crop degenerates to
    when a product is loaded at its own native/working GSD."""
    loaded = _make_loaded()
    row, col = 300.0, 450.0
    expected = loaded.transform.pixel_to_lonlat(row, col)
    # crop_point_to_lonlat takes (x, y) = (col, row), matching pts_a/pts_b's
    # convention everywhere else in this codebase.
    got = crop_point_to_lonlat(loaded, origin=(0, 0), resize_scale=1.0, x=col, y=row)
    assert got == pytest.approx(expected)


def test_crop_point_to_lonlat_inverts_origin_and_resize():
    """A point at crop-space (x, y) with a crop origin of (row0, col0) and a
    resize scale should land on the same (lat, lon) as directly querying the
    corresponding original-image pixel -- i.e. the resize-then-crop math is
    correctly inverted, not just approximately right."""
    loaded = _make_loaded()
    row0, col0 = 100, 50
    scale = 2.0  # crop was upsampled 2x relative to the native raster
    x, y = 40.0, 20.0  # crop-space coords
    # Same physical pixel in original-image space:
    orig_row, orig_col = row0 + y / scale, col0 + x / scale
    expected = loaded.transform.pixel_to_lonlat(orig_row, orig_col)
    got = crop_point_to_lonlat(loaded, origin=(row0, col0), resize_scale=scale, x=x, y=y)
    assert got == pytest.approx(expected)


def test_geolocation_errors_near_zero_for_true_self_match():
    """The same physical pixel, referenced through the SAME product's
    transform on both sides (the trivial 'perfect correspondence' case),
    should report ~0m disagreement -- this is this metric's own version of
    the self-match sanity check used throughout the project."""
    loaded = _make_loaded()
    pts = np.array([[100.0, 200.0], [300.0, 150.0], [500.0, 500.0]], dtype=np.float32)
    errors = geolocation_errors_m(loaded, (0, 0), 1.0, loaded, (0, 0), 1.0, pts, pts)
    assert errors.shape == (3,)
    assert np.all(errors < 1e-6)


def test_geolocation_errors_nonzero_for_offset_points():
    """A deliberate few-pixel offset between the two 'products' (here the
    same transform, so this isolates the metric's sensitivity from any
    cross-product geolocation differences) should report a real, nonzero
    distance, not silently collapse to 0."""
    loaded = _make_loaded()
    pts_a = np.array([[100.0, 200.0]], dtype=np.float32)
    pts_b = np.array([[100.0, 210.0]], dtype=np.float32)  # 10px row offset
    errors = geolocation_errors_m(loaded, (0, 0), 1.0, loaded, (0, 0), 1.0, pts_a, pts_b)
    assert errors[0] > 1.0  # a real, non-negligible distance in meters


def test_geolocation_errors_empty_input_returns_empty_array():
    """Mirrors this project's blank-image / zero-match convention: no
    correspondences to evaluate is a normal outcome, not an error."""
    loaded = _make_loaded()
    empty = np.zeros((0, 2), dtype=np.float32)
    errors = geolocation_errors_m(loaded, (0, 0), 1.0, loaded, (0, 0), 1.0, empty, empty)
    assert errors.shape == (0,)


def test_summarize_errors_empty_gives_none_not_zero():
    """A genuine 'nothing to measure' case must report None, not 0 -- 0m
    error would misleadingly read as 'perfect agreement.'"""
    summary = summarize_errors(np.zeros(0))
    assert summary == {"n": 0, "median_m": None, "mean_m": None, "p90_m": None, "max_m": None}


def test_summarize_errors_stats():
    errors = np.array([1.0, 2.0, 3.0, 4.0, 100.0])
    summary = summarize_errors(errors)
    assert summary["n"] == 5
    assert summary["median_m"] == pytest.approx(3.0)
    assert summary["mean_m"] == pytest.approx(22.0)
    assert summary["max_m"] == pytest.approx(100.0)
