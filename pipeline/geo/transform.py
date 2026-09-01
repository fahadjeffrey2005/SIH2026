"""Bilinear pixel <-> (lat, lon) transform from a product's 4 corner points.

This is deliberately the *simple* georeferencing model flagged as an open
question in docs/architecture.md Section 9: pushbroom sensors like OHRC/
TMC-2 are not perfectly described by a single bilinear quad (there's
along-track curvature from orbit dynamics a true sensor model would
capture), and PDS4 corner geolocation itself has some inherent error. Treat
transform_lonlat's output as *pseudo*-ground-truth, accurate to roughly the
corner metadata's own precision -- good enough to seed and evaluate a
matcher, not a substitute for photogrammetric bundle adjustment.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BilinearGeoTransform:
    """corners: {'ul','ur','ll','lr'} -> (lat_deg, lon_deg).
    n_lines / n_samples: image shape this transform is defined over
    (row 0 = top/UL-UR edge, col 0 = left/UL-LL edge).
    """

    corners: dict[str, tuple[float, float]]
    n_lines: int
    n_samples: int

    def pixel_to_lonlat(self, row: float, col: float) -> tuple[float, float]:
        u = col / max(self.n_samples - 1, 1)
        v = row / max(self.n_lines - 1, 1)
        ul_lat, ul_lon = self.corners["ul"]
        ur_lat, ur_lon = self.corners["ur"]
        ll_lat, ll_lon = self.corners["ll"]
        lr_lat, lr_lon = self.corners["lr"]

        top_lat = ul_lat + u * (ur_lat - ul_lat)
        top_lon = ul_lon + u * (ur_lon - ul_lon)
        bot_lat = ll_lat + u * (lr_lat - ll_lat)
        bot_lon = ll_lon + u * (lr_lon - ll_lon)

        lat = top_lat + v * (bot_lat - top_lat)
        lon = top_lon + v * (bot_lon - top_lon)
        return lat, lon

    def lonlat_to_pixel(
        self, lat: float, lon: float, max_iter: int = 25, tol: float = 1e-9
    ) -> tuple[float, float]:
        """Inverse of pixel_to_lonlat via Newton's method on (u, v) in [0,1]^2.

        A general bilinear quad inverse has a closed-form quadratic solution,
        but it degenerates (division by ~0) for near-parallelogram quads --
        exactly the common case for these narrow, near-rectangular imaging
        swaths. Newton's method has no such degeneracy and converges in a
        handful of iterations for a quad this close to affine; that's a
        better trade for a hackathon codebase than special-casing the
        quadratic's edge cases.
        """
        ul_lat, ul_lon = self.corners["ul"]
        ur_lat, ur_lon = self.corners["ur"]
        ll_lat, ll_lon = self.corners["ll"]
        lr_lat, lr_lon = self.corners["lr"]

        u, v = 0.5, 0.5
        for _ in range(max_iter):
            top_lat = ul_lat + u * (ur_lat - ul_lat)
            top_lon = ul_lon + u * (ur_lon - ul_lon)
            bot_lat = ll_lat + u * (lr_lat - ll_lat)
            bot_lon = ll_lon + u * (lr_lon - ll_lon)
            f_lat = top_lat + v * (bot_lat - top_lat) - lat
            f_lon = top_lon + v * (bot_lon - top_lon) - lon

            # Jacobian d(f_lat, f_lon) / d(u, v)
            d_top_lat_du = ur_lat - ul_lat
            d_top_lon_du = ur_lon - ul_lon
            d_bot_lat_du = lr_lat - ll_lat
            d_bot_lon_du = lr_lon - ll_lon

            df_lat_du = d_top_lat_du + v * (d_bot_lat_du - d_top_lat_du)
            df_lon_du = d_top_lon_du + v * (d_bot_lon_du - d_top_lon_du)
            df_lat_dv = bot_lat - top_lat
            df_lon_dv = bot_lon - top_lon

            det = df_lat_du * df_lon_dv - df_lat_dv * df_lon_du
            if abs(det) < 1e-15:
                break
            du = (f_lat * df_lon_dv - f_lon * df_lat_dv) / det
            dv = (df_lat_du * f_lon - df_lon_du * f_lat) / det
            u -= du
            v -= dv
            if abs(du) < tol and abs(dv) < tol:
                break

        row = v * max(self.n_lines - 1, 1)
        col = u * max(self.n_samples - 1, 1)
        return row, col
