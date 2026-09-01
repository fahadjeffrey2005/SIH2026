from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

from ..config import REPO_ROOT

router = APIRouter(tags=["metrics"])

MATRIX_PATH = REPO_ROOT / "docs" / "baseline_matrix.json"


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
