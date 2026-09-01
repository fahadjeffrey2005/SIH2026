"""Scan data/raw/ for PDS4 labels and populate data/catalog.sqlite.

Usage:
    python -m ingest.build_catalog [--data-root ../data]

Only reads XML labels (fast, no huge .img/.qub files touched) so this is
safe to re-run any time new products are added to data/raw/.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from .pds4_label import parse_label

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    product_id          TEXT PRIMARY KEY,
    instrument          TEXT NOT NULL,
    start_time          TEXT,
    stop_time           TEXT,
    orbit_number        INTEGER,
    spacecraft_alt_km   REAL,
    sun_azimuth_deg     REAL,
    sun_elevation_deg   REAL,
    solar_incidence_deg REAL,
    corner_source       TEXT,
    ul_lat REAL, ul_lon REAL,
    ur_lat REAL, ur_lon REAL,
    ll_lat REAL, ll_lon REAL,
    lr_lat REAL, lr_lon REAL,
    xml_path            TEXT NOT NULL
);
"""

UPSERT = """
INSERT INTO products (
    product_id, instrument, start_time, stop_time, orbit_number,
    spacecraft_alt_km, sun_azimuth_deg, sun_elevation_deg, solar_incidence_deg,
    corner_source, ul_lat, ul_lon, ur_lat, ur_lon, ll_lat, ll_lon, lr_lat, lr_lon,
    xml_path
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(product_id) DO UPDATE SET
    instrument=excluded.instrument, start_time=excluded.start_time,
    stop_time=excluded.stop_time, orbit_number=excluded.orbit_number,
    spacecraft_alt_km=excluded.spacecraft_alt_km,
    sun_azimuth_deg=excluded.sun_azimuth_deg,
    sun_elevation_deg=excluded.sun_elevation_deg,
    solar_incidence_deg=excluded.solar_incidence_deg,
    corner_source=excluded.corner_source,
    ul_lat=excluded.ul_lat, ul_lon=excluded.ul_lon,
    ur_lat=excluded.ur_lat, ur_lon=excluded.ur_lon,
    ll_lat=excluded.ll_lat, ll_lon=excluded.ll_lon,
    lr_lat=excluded.lr_lat, lr_lon=excluded.lr_lon,
    xml_path=excluded.xml_path;
"""


def find_labels(data_root: Path) -> list[Path]:
    """All *_d_img_*.xml calibrated/raw data labels under data/raw/, skipping
    the browse/geometry/miscellaneous sidecar labels PDS4 zips also ship."""
    out = []
    for p in data_root.glob("raw/**/*.xml"):
        s = str(p)
        if "/browse/" in s or "/miscellaneous/" in s or "_g_grd_" in p.name or "_b_brw_" in p.name:
            continue
        out.append(p)
    return sorted(out)


def build(data_root: Path, db_path: Path) -> int:
    conn = sqlite3.connect(db_path)
    conn.execute(SCHEMA)

    n = 0
    for xml_path in find_labels(data_root):
        label = parse_label(xml_path)
        corners = label.corners
        row = (
            label.product_id,
            label.instrument,
            label.start_time,
            label.stop_time,
            label.orbit_number,
            label.spacecraft_altitude_km,
            label.sun_azimuth_deg,
            label.sun_elevation_deg,
            label.solar_incidence_deg,
            label.corner_source,
            *corners.get("ul", (None, None)),
            *corners.get("ur", (None, None)),
            *corners.get("ll", (None, None)),
            *corners.get("lr", (None, None)),
            str(xml_path),
        )
        conn.execute(UPSERT, row)
        n += 1
    conn.commit()
    conn.close()
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", default=str(Path(__file__).resolve().parents[2] / "data"))
    args = ap.parse_args()

    data_root = Path(args.data_root)
    db_path = data_root / "catalog.sqlite"
    n = build(data_root, db_path)
    print(f"indexed {n} products -> {db_path}")


if __name__ == "__main__":
    main()
