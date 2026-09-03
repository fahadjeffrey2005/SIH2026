from __future__ import annotations

import json
import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..config import REPO_ROOT

router = APIRouter(tags=["metrics"])

MATRIX_PATH = REPO_ROOT / "docs" / "baseline_matrix.json"
CELL_IMAGE_DIR = REPO_ROOT / "docs" / "img" / "matrix_cells"

# Filenames here are always ones build_matrix.py generated itself
# (`{product_a}__{product_b}__{a|b}.png`, product ids are lowercase
# alphanumeric/underscore) and are only ever read back via the exact
# `crop_image_a`/`crop_image_b` strings baseline_matrix.json already
# handed the frontend -- this pattern is a defense-in-depth path-traversal
# guard, not a real access-control boundary.
_SAFE_FILENAME = re.compile(r"^[a-z0-9_]+__[a-z0-9_]+__[ab]\.png$")


@router.get("/metrics/matrix")
def get_matrix():
    """The classical-vs-learned comparison matrix (docs/architecture.md
    Sec. 5.4 / 7's "metrics dashboard"): every geometrically-confirmed
    overlapping, raster-available pair x every method (SIFT, AKAZE,
    DISK+LightGlue).

    Served from docs/baseline_matrix.json rather than computed per-request
    -- a full DISK+LightGlue pass over the larger crops in this matrix
    takes ~50s each, which is a bad idea to put behind a synchronous GET.
    Regenerate it with `python -m match.build_matrix` (pipeline/) after
    adding a new raster-available product or re-running with different
    matcher settings.
    """
    if not MATRIX_PATH.exists():
        raise HTTPException(
            404,
            "baseline_matrix.json not found -- run `python -m match.build_matrix` "
            "from pipeline/ first",
        )
    return json.loads(MATRIX_PATH.read_text())


@router.get("/metrics/matrix/crop/{filename}")
def get_matrix_crop(filename: str):
    """One of the two source crop images behind a metrics-matrix cell (see
    each row's `crop_image_a`/`crop_image_b` in GET /metrics/matrix) -- the
    interactive correspondence viewer loads these directly and draws its
    own point/line overlay on top, rather than a single flattened overlay
    PNG, so individual matches stay hoverable."""
    if not _SAFE_FILENAME.match(filename):
        raise HTTPException(404, f"no such crop image {filename!r}")
    path = CELL_IMAGE_DIR / filename
    if not path.exists():
        raise HTTPException(404, f"no such crop image {filename!r}")
    return FileResponse(path, media_type="image/png")
