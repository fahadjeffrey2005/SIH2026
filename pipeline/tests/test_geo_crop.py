"""geo.crop.overlap_crop: regression test for the extrapolation blowup found
while building the classical matching baseline.

Projecting a huge footprint's raw bbox corners onto a much smaller
footprint's bilinear transform sent Newton's method to points tens of
thousands of pixels outside the image (see git history / demo.py's
docstring) -- fixed by intersecting the two footprints' bboxes first, so
every probe point stays near the small footprint's own domain.
"""

from geo.crop import overlap_crop
from geo.footprint import Footprint
from geo.transform import BilinearGeoTransform

# Proportioned like the real bug: OHRC's tiny scene against TMC-2's long,
# barely-overlapping swath (see test_geo_footprint.py for the real
# coordinates this is modeled on).
SMALL = Footprint("small", {
    "ul": (-2.576048, -23.513766),
    "ur": (-2.579083, -23.410545),
    "ll": (-3.413866, -23.515354),
    "lr": (-3.416904, -23.412227),
})
SMALL_TRANSFORM = BilinearGeoTransform(SMALL.corners, n_lines=9369, n_samples=1200)

LARGE = Footprint("large", {
    "ul": (43.095893, -20.838351),
    "ur": (43.131132, -22.015005),
    "ll": (-4.962184, -22.957478),
    "lr": (-4.93821, -23.761254),
})


def test_crop_window_stays_within_image_bounds():
    row0, row1, col0, col1 = overlap_crop(SMALL, SMALL_TRANSFORM, LARGE)
    assert 0 <= row0 <= row1 <= SMALL_TRANSFORM.n_lines - 1
    assert 0 <= col0 <= col1 <= SMALL_TRANSFORM.n_samples - 1


def test_crop_window_covers_most_of_small_image():
    """SMALL's whole footprint sits inside LARGE's bbox, so the true
    overlap crop should be nearly the entire small image, not some tiny
    sliver left over from a bad bbox intersection."""
    row0, row1, col0, col1 = overlap_crop(SMALL, SMALL_TRANSFORM, LARGE)
    assert (row1 - row0) > 0.8 * SMALL_TRANSFORM.n_lines
    assert (col1 - col0) > 0.8 * SMALL_TRANSFORM.n_samples


def test_crop_falls_back_to_full_extent_when_bboxes_disjoint():
    disjoint = Footprint("disjoint", {"ul": (80, 170), "ur": (80, 179), "ll": (70, 170), "lr": (70, 179)})
    row0, row1, col0, col1 = overlap_crop(SMALL, SMALL_TRANSFORM, disjoint)
    assert row0 == 0 and col0 == 0
    assert row1 == SMALL_TRANSFORM.n_lines - 1
    assert col1 == SMALL_TRANSFORM.n_samples - 1
