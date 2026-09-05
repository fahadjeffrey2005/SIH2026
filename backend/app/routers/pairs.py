from __future__ import annotations

from fastapi import APIRouter, HTTPException
from geo import Footprint, quads_overlap
from match.classical.demo import BROWSE_PRODUCTS

from ..db import catalog_conn, row_corners
from ..schemas import PairSuggestion

router = APIRouter(tags=["pairs"])

_HAS_RASTER = set(BROWSE_PRODUCTS)


@router.get("/pairs/suggest", response_model=list[PairSuggestion])
def suggest_pairs(product_id: str):
    """Every other catalog product whose footprint genuinely overlaps
    `product_id` (real spherical point-in-quad geometry, not a date or bbox
    guess -- see geo/footprint.py), sorted by ascending solar-incidence gap
    so the easiest (low sun-angle-gap) candidates come first."""
    with catalog_conn() as conn:
        rows = {r["product_id"]: r for r in conn.execute("SELECT * FROM products").fetchall()}

    if product_id not in rows:
        raise HTTPException(404, f"unknown product_id {product_id!r}")

    target = rows[product_id]
    target_corners = row_corners(target)
    if not target_corners:
        raise HTTPException(422, f"{product_id} has no footprint corners in the catalog")
    target_fp = Footprint(product_id, target_corners)

    out = []
    for pid, row in rows.items():
        if pid == product_id:
            continue
        corners = row_corners(row)
        if not corners:
            continue
        if not quads_overlap(target_fp, Footprint(pid, corners)):
            continue
        gap = None
        if target["solar_incidence_deg"] is not None and row["solar_incidence_deg"] is not None:
            gap = abs(target["solar_incidence_deg"] - row["solar_incidence_deg"])
        out.append(PairSuggestion(
            product_id=pid,
            instrument=row["instrument"],
            solar_incidence_deg=row["solar_incidence_deg"],
            incidence_gap_deg=gap,
            has_raster=pid in _HAS_RASTER,
        ))
    out.sort(key=lambda p: (p.incidence_gap_deg is None, p.incidence_gap_deg or 0.0))
    return out
