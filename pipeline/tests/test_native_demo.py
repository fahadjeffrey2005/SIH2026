"""match.native_demo: regression checks for the native-resolution follow-up
result (docs/baseline_results.md's "Native-resolution follow-up" section).

Doesn't re-run matching (that needs torch/kornia and ~1 minute -- see
`python -m match.native_demo` to reproduce the actual numbers). Instead
pins down the two things most likely to silently drift and invalidate that
result without anyone noticing: the checked-in crop PNGs' shapes, and the
hardcoded native Axis_Array dimensions native_demo.py needs to build each
product's BilinearGeoTransform correctly (get either wrong and the
geolocation-agreement numbers reported in the docs would be silently
wrong, not crash).
"""

import cv2
import pytest

from ingest.pds4_label import parse_label
from match.native_demo import (
    OHRC_CROP_PNG,
    OHRC_NATIVE_SHAPE,
    OHRC_XML,
    TMC2_CROP_PNG,
    TMC2_NATIVE_SHAPE,
    TMC2_XML,
)


def _label_shape(xml_path) -> tuple[int, int]:
    label = parse_label(xml_path)
    axes = {a.axis_name: a.elements for a in label.axes}
    return axes["Line"], axes["Sample"]


def test_ohrc_native_shape_matches_its_own_pds4_label():
    assert _label_shape(OHRC_XML) == OHRC_NATIVE_SHAPE


def test_tmc2_native_shape_matches_its_own_pds4_label():
    assert _label_shape(TMC2_XML) == TMC2_NATIVE_SHAPE


def test_ohrc_crop_png_present_and_nonempty():
    img = cv2.imread(str(OHRC_CROP_PNG), cv2.IMREAD_UNCHANGED)
    assert img is not None, f"missing {OHRC_CROP_PNG}"
    assert img.shape[0] > 0 and img.shape[1] > 0


def test_tmc2_crop_png_present_and_nonempty():
    img = cv2.imread(str(TMC2_CROP_PNG), cv2.IMREAD_UNCHANGED)
    assert img is not None, f"missing {TMC2_CROP_PNG}"
    assert img.shape[0] > 0 and img.shape[1] > 0


def test_ohrc_crop_origin_and_scale_are_within_native_bounds():
    """origin + crop_size/scale must not exceed the native image -- a
    regression check that OHRC_ORIGIN/OHRC_RESIZE_SCALE and the actual crop
    PNG still agree with each other and with OHRC_NATIVE_SHAPE."""
    from match.native_demo import OHRC_ORIGIN, OHRC_RESIZE_SCALE

    img = cv2.imread(str(OHRC_CROP_PNG), cv2.IMREAD_UNCHANGED)
    row0, col0 = OHRC_ORIGIN
    native_rows_covered = row0 + img.shape[0] / OHRC_RESIZE_SCALE
    native_cols_covered = col0 + img.shape[1] / OHRC_RESIZE_SCALE
    assert native_rows_covered == pytest.approx(OHRC_NATIVE_SHAPE[0], rel=0.01)
    assert native_cols_covered == pytest.approx(OHRC_NATIVE_SHAPE[1], rel=0.01)


def test_tmc2_crop_origin_is_within_native_bounds():
    from match.native_demo import TMC2_ORIGIN, TMC2_RESIZE_SCALE

    assert TMC2_RESIZE_SCALE == 1.0  # TMC-2 crop is already at native GSD, no resize
    img = cv2.imread(str(TMC2_CROP_PNG), cv2.IMREAD_UNCHANGED)
    row0, col0 = TMC2_ORIGIN
    assert row0 + img.shape[0] <= TMC2_NATIVE_SHAPE[0]
    assert col0 + img.shape[1] <= TMC2_NATIVE_SHAPE[1]
