"""Crop the pixel window in one product that covers another product's
footprint, so matching runs on the genuine overlap instead of an entire
multi-hundred-thousand-line strip most of which shares no ground with the
other product.
"""

from __future__ import annotations

from .footprint import Footprint
from .transform import BilinearGeoTransform


def overlap_crop(
    src_footprint: Footprint,
    src_transform: BilinearGeoTransform,
    target_footprint: Footprint,
    margin_frac: float = 0.15,
) -> tuple[int, int, int, int]:
    """Row/col window (row0, row1, col0, col1) in `src`'s pixel space that
    covers `target_footprint`'s bounding box.

    Padded by `margin_frac` of the window's own size on each side --
    corner geolocation has real error (see docs/architecture.md Sec. 9), so a
    plain bbox intersection can clip the true overlap right at its edge.
    Clamped to the source image's actual extent.

    Projects the lat/lon *bbox intersection* of the two footprints, not
    `target_footprint`'s raw bbox, onto `src`'s pixel grid. That matters when
    one footprint is much larger than the other (e.g. a small OHRC scene
    inside a long TMC-2 swath): projecting the huge footprint's bbox corners
    directly would ask the small footprint's bilinear transform to
    extrapolate to points enormously outside its own quad, which is
    numerically meaningless (Newton's method can diverge to points tens of
    thousands of pixels away). Intersecting first keeps every probe point
    within (or just outside) the source's own footprint, where the bilinear
    model is actually valid.
    """
    s_min_lat, s_max_lat, s_min_lon, s_max_lon = src_footprint.bbox
    t_min_lat, t_max_lat, t_min_lon, t_max_lon = target_footprint.bbox
    min_lat = max(s_min_lat, t_min_lat)
    max_lat = min(s_max_lat, t_max_lat)
    min_lon = max(s_min_lon, t_min_lon)
    max_lon = min(s_max_lon, t_max_lon)
    if min_lat > max_lat or min_lon > max_lon:
        # Bboxes don't actually intersect (shouldn't happen if the caller
        # already checked geo.quads_overlap) -- fall back to src's own full
        # extent rather than projecting nonsense.
        min_lat, max_lat, min_lon, max_lon = s_min_lat, s_max_lat, s_min_lon, s_max_lon

    probe_corners = [
        (min_lat, min_lon),
        (min_lat, max_lon),
        (max_lat, min_lon),
        (max_lat, max_lon),
    ]
    rows, cols = [], []
    for lat, lon in probe_corners:
        r, c = src_transform.lonlat_to_pixel(lat, lon)
        rows.append(r)
        cols.append(c)

    row0, row1 = min(rows), max(rows)
    col0, col1 = min(cols), max(cols)
    row_pad = (row1 - row0) * margin_frac
    col_pad = (col1 - col0) * margin_frac
    row0 -= row_pad
    row1 += row_pad
    col0 -= col_pad
    col1 += col_pad

    row0 = max(0, int(row0))
    col0 = max(0, int(col0))
    row1 = min(src_transform.n_lines - 1, int(round(row1)))
    col1 = min(src_transform.n_samples - 1, int(round(col1)))
    return row0, row1, col0, col1
