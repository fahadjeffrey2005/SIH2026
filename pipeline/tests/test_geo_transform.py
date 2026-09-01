"""geo.transform.BilinearGeoTransform: round-trip accuracy of the
pixel<->lonlat pseudo-ground-truth transform."""

import pytest

from geo.transform import BilinearGeoTransform

# A mildly skewed quad (not an axis-aligned rectangle) so the test actually
# exercises the bilinear interpolation, not just a trivial affine case.
CORNERS = {
    "ul": (10.0, -20.0),
    "ur": (10.2, -18.0),
    "ll": (8.0, -20.1),
    "lr": (8.3, -18.1),
}
N_LINES, N_SAMPLES = 1000, 500


@pytest.fixture
def transform():
    return BilinearGeoTransform(CORNERS, n_lines=N_LINES, n_samples=N_SAMPLES)


@pytest.mark.parametrize("row,col", [
    (0, 0), (0, N_SAMPLES - 1), (N_LINES - 1, 0), (N_LINES - 1, N_SAMPLES - 1),
    (500, 250), (100, 400), (900, 50),
])
def test_pixel_lonlat_round_trip(transform, row, col):
    lat, lon = transform.pixel_to_lonlat(row, col)
    row2, col2 = transform.lonlat_to_pixel(lat, lon)
    assert row2 == pytest.approx(row, abs=1e-4)
    assert col2 == pytest.approx(col, abs=1e-4)


def test_corners_map_to_their_own_lonlat(transform):
    ul_lat, ul_lon = transform.pixel_to_lonlat(0, 0)
    assert (ul_lat, ul_lon) == pytest.approx(CORNERS["ul"])

    lr_lat, lr_lon = transform.pixel_to_lonlat(N_LINES - 1, N_SAMPLES - 1)
    assert (lr_lat, lr_lon) == pytest.approx(CORNERS["lr"])
