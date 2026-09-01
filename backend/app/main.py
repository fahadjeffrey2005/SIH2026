"""FastAPI app wrapping pipeline/ for the frontend (docs/architecture.md Sec. 6).

pipeline/'s modules (geo, ingest, match, preprocess) are plain top-level
packages meant to be run with `pipeline/` as the working directory (see
pipeline/README usage) -- there's no installed `sih26166-pipeline` package.
Rather than duplicate that code here, we put pipeline/ onto sys.path
ourselves, once, before any of this app's modules import from it. That
sys.path mutation MUST happen before the `from .routers import ...` line
below, since routers/jobs import `geo`/`match`/`ingest` at module load time.
"""

from __future__ import annotations

import sys

from .config import PIPELINE_DIR

if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from .routers import match, metrics, pairs, products  # noqa: E402

app = FastAPI(
    title="SIH26166 Correspondence API",
    description="Multi-modal, sun-angle and scale-invariant lunar image correspondence -- backend for the pipeline in pipeline/.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # hackathon scale; tighten before any real deployment
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(products.router)
app.include_router(pairs.router)
app.include_router(match.router)
app.include_router(metrics.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}
