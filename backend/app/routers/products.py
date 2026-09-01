from __future__ import annotations

from fastapi import APIRouter
from match.classical.demo import BROWSE_PRODUCTS, IIRS_PRODUCTS

from ..db import catalog_conn, row_corners
from ..schemas import ProductOut

router = APIRouter(tags=["products"])

_HAS_RASTER = set(BROWSE_PRODUCTS) | set(IIRS_PRODUCTS)


@router.get("/products", response_model=list[ProductOut])
def list_products():
    """All products in the catalog (built by `python -m ingest.build_catalog`
    from pipeline/). `has_raster` flags whether /match can currently load
    pixel data for it -- today that's the 4 products wired into
    match/classical/demo.py (3 browse PNGs + the locally staged IIRS cube);
    the other 4 (OHRC/TMC-2 zips not yet unpacked past their labels) show up
    in the catalog with real metadata but can't be matched until their
    rasters are staged."""
    with catalog_conn() as conn:
        rows = conn.execute("SELECT * FROM products ORDER BY instrument, start_time").fetchall()
    return [
        ProductOut(
            product_id=r["product_id"],
            instrument=r["instrument"],
            start_time=r["start_time"],
            stop_time=r["stop_time"],
            orbit_number=r["orbit_number"],
            sun_azimuth_deg=r["sun_azimuth_deg"],
            sun_elevation_deg=r["sun_elevation_deg"],
            solar_incidence_deg=r["solar_incidence_deg"],
            corner_source=r["corner_source"],
            corners=row_corners(r),
            has_raster=r["product_id"] in _HAS_RASTER,
        )
        for r in rows
    ]
