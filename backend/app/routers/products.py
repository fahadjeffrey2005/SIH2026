from __future__ import annotations

from pathlib import Path

import cv2
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from match.classical.demo import BROWSE_PRODUCTS

from ..config import DATA_ROOT
from ..db import catalog_conn, row_corners
from ..schemas import ProductOut

router = APIRouter(tags=["products"])

_HAS_RASTER = set(BROWSE_PRODUCTS)

# product_id -> its real browse-resolution PNG, relative to DATA_ROOT. Reuses
# the exact same source images match/classical/demo.py already loads for
# matching (BROWSE_PRODUCTS's band-40-derived PNG for IIRS included) except
# for IIRS specifically, which gets its own separate ISRO-provided browse
# thumbnail here instead -- a nicer-looking real preview for the 3D Moon
# than the single spectral band used for matching, even though both are
# real imagery of the same product.
_BROWSE_IMAGE = {pid: png_rel for pid, (_xml_rel, png_rel) in BROWSE_PRODUCTS.items()}
_BROWSE_IMAGE["ch2_iir_nri_20211221t0324126144_d_img_hw1"] = (
    "raw/iirs/ch2_iir_nri_20211221/browse/raw/20211221/ch2_iir_nri_20211221T0324126144_b_brw_hw1.png"
)

_GLOBE_TEXTURE_DIR = DATA_ROOT / "processed" / "moon_globe_textures"
_GLOBE_TEXTURE_DIR.mkdir(parents=True, exist_ok=True)
# The 3D Moon now lets the camera zoom in close enough to fill the screen
# with a single patch (see MoonGlobe.jsx's MIN_CAMERA_DISTANCE/FOCUS_DISTANCE),
# so a low cap here directly shows up as lost detail once zoomed in -- these
# source PNGs run up to ~7MB / 9000-29000px on the long side (IIRS's is
# already under this cap and gets served at its full original resolution,
# untouched). 8192 is close to the practical ceiling for real-world GPU
# texture-size support: WebGL2 only *requires* 2048, but every real desktop
# and laptop GPU from the last decade (and effectively all current mobile
# GPUs) supports at least 8192, whereas 16384 -- which would nearly cover
# OHRC's ~9369px full native length -- is common on discrete desktop GPUs
# but not guaranteed on integrated/mobile ones, and a texture the GPU
# silently refuses to allocate is worse than one that's merely downsized.
# TMC-2's two products are long pushbroom strips (20650px and 29523px) --
# even at this cap they're downsized ~2.5-3.6x, so some real detail loss on
# those two specifically is an honest, inherent limit of a single WebGL
# texture covering a whole 35-48deg-long swath, not something this cap
# alone can fully solve.
_GLOBE_TEXTURE_MAX_SIDE = 8192


def _globe_texture_path(product_id: str) -> Path:
    """Resizes+re-encodes a product's real browse image the first time it's
    requested (a one-time cost, not paid on every request) and caches the
    result on disk; later requests just serve the cached JPEG. Long, thin
    strips (some over 20x taller than wide) are capped on their LONG side so
    the short side doesn't get downsampled to nothing."""
    cached = _GLOBE_TEXTURE_DIR / f"{product_id}.jpg"
    if cached.exists():
        return cached
    src = DATA_ROOT / _BROWSE_IMAGE[product_id]
    image = cv2.imread(str(src), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise HTTPException(404, f"browse image missing on disk for {product_id!r} (expected {src})")
    h, w = image.shape[:2]
    scale = _GLOBE_TEXTURE_MAX_SIDE / max(h, w)
    if scale < 1:
        image = cv2.resize(image, (max(1, round(w * scale)), max(1, round(h * scale))), interpolation=cv2.INTER_AREA)
    # 95 rather than 92 -- these get zoomed in close enough that JPEG
    # blocking artifacts on a real grayscale image are easy to mistake for
    # actual surface detail (or lack of it); the extra few % filesize isn't
    # worth trading for that at this resolution.
    cv2.imwrite(str(cached), image, [cv2.IMWRITE_JPEG_QUALITY, 95])
    return cached


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


@router.get("/products/{product_id}/browse")
def get_product_browse(product_id: str):
    """A real, actual-pixel-data preview image of this product -- used by
    the 3D Moon (frontend/src/components/MoonGlobe.jsx) to drape the real
    Chandrayaan-2 image onto its footprint patch on the globe, instead of a
    flat color fill. `product_id` is only ever looked up in `_BROWSE_IMAGE`
    (never used to build a filesystem path directly), so there's no path-
    traversal surface here.

    Only available for the same products `has_raster` is true for (GET
    /products) -- the other 4 have real metadata/corners but their raw zips
    aren't unpacked past their PDS4 labels yet, so there's no pixel data to
    show; the frontend falls back to a flat color patch for those."""
    if product_id not in _BROWSE_IMAGE:
        raise HTTPException(404, f"no browse image available for {product_id!r}")
    return FileResponse(_globe_texture_path(product_id), media_type="image/jpeg")
