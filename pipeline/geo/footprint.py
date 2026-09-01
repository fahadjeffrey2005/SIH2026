"""Footprint overlap geometry.

This ports (into Python, generalized beyond the south-pole projection case)
the same rigorous spherical point-in-polygon method used earlier to verify
genuine multi-instrument overlap directly against ISSDC's raw WFS geometry --
because the portal's own AOI/bbox search is unreliable, we never trust a
catalog's "these overlap" claim without checking the actual corner geometry
ourselves. Naive lat/lon-as-planar-coordinates bounding boxes break down near
the poles (longitude convergence) and across the antimeridian; going through
unit-sphere vectors avoids both problems and is correct everywhere.

`bbox_overlap` is a cheap pre-filter; `quads_overlap` is the real,
projection-safe check and is what should gate any "these two products are a
candidate pair" decision.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

Corner = tuple[float, float]  # (lat_deg, lon_deg), lon in -180..180


@dataclass
class Footprint:
    product_id: str
    corners: dict[str, Corner]  # keys: 'ul','ur','ll','lr'

    @property
    def ordered_quad(self) -> list[Corner]:
        """Corners in a consistent winding order for polygon math."""
        return [self.corners["ul"], self.corners["ur"], self.corners["lr"], self.corners["ll"]]

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        """(min_lat, max_lat, min_lon, max_lon). Not antimeridian-safe -- fine
        for this project's AOIs, which don't cross +/-180 longitude."""
        lats = [c[0] for c in self.corners.values()]
        lons = [c[1] for c in self.corners.values()]
        return min(lats), max(lats), min(lons), max(lons)


def lonlat_to_xyz(lon_deg: float, lat_deg: float) -> tuple[float, float, float]:
    lon, lat = math.radians(lon_deg), math.radians(lat_deg)
    return (math.cos(lat) * math.cos(lon), math.cos(lat) * math.sin(lon), math.sin(lat))


def _normalize(v: tuple[float, float, float]) -> tuple[float, float, float]:
    n = math.sqrt(sum(c * c for c in v))
    return (v[0] / n, v[1] / n, v[2] / n)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def spherical_point_in_quad(target: Corner, quad: list[Corner]) -> bool:
    """Is `target` (lat, lon) inside the quad defined by 4 (lat, lon) corners?

    Projects the quad and target onto the local tangent plane at the quad's
    centroid (an equirectangular-safe local projection, valid even near the
    poles or across the antimeridian) and does ordinary 2D ray-casting there.
    """
    xyz = [lonlat_to_xyz(lon, lat) for lat, lon in quad]
    cx = tuple(sum(c[i] for c in xyz) / len(xyz) for i in range(3))
    center = _normalize(cx)

    up = (0.0, 0.0, 1.0) if abs(center[2]) < 0.99 else (1.0, 0.0, 0.0)
    east = _normalize(_cross(up, center))
    north = _cross(center, east)

    def project(p):
        pn = _normalize(p)
        return (_dot(pn, east), _dot(pn, north))

    poly2d = [project(p) for p in xyz]
    tlat, tlon = target
    t2d = project(lonlat_to_xyz(tlon, tlat))

    inside = False
    n = len(poly2d)
    for i in range(n):
        j = (i - 1) % n
        xi, yi = poly2d[i]
        xj, yj = poly2d[j]
        if (yi > t2d[1]) != (yj > t2d[1]):
            x_intersect = (xj - xi) * (t2d[1] - yi) / (yj - yi) + xi
            if t2d[0] < x_intersect:
                inside = not inside
    return inside


def bbox_overlap(a: Footprint, b: Footprint) -> bool:
    a_min_lat, a_max_lat, a_min_lon, a_max_lon = a.bbox
    b_min_lat, b_max_lat, b_min_lon, b_max_lon = b.bbox
    lat_ok = a_min_lat <= b_max_lat and b_min_lat <= a_max_lat
    lon_ok = a_min_lon <= b_max_lon and b_min_lon <= a_max_lon
    return lat_ok and lon_ok


def quads_overlap(a: Footprint, b: Footprint) -> bool:
    """True if the two footprints genuinely overlap.

    Cheap bbox pre-filter, then a real check: any corner of A inside B's
    quad, or vice versa. This catches the common cases (one product's swath
    crossing the other, or one nested inside the other) without needing full
    general polygon-clipping; it can in principle miss a "cross" overlap
    where the quads intersect but no corner of either lies inside the other
    (two long thin strips crossing like a plus sign) -- rare for these
    imaging swaths, but worth remembering if a suspiciously-false result
    ever needs debugging.
    """
    if not bbox_overlap(a, b):
        return False
    quad_a, quad_b = a.ordered_quad, b.ordered_quad
    if any(spherical_point_in_quad(c, quad_b) for c in quad_a):
        return True
    if any(spherical_point_in_quad(c, quad_a) for c in quad_b):
        return True
    return False
