"""Shared paths. The backend reads pipeline/'s outputs directly (the sqlite
catalog, and reuses pipeline/ code for matching) rather than duplicating
anything -- see main.py for how pipeline/ gets onto sys.path.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_DIR = REPO_ROOT / "pipeline"
DATA_ROOT = REPO_ROOT / "data"
CATALOG_DB = DATA_ROOT / "catalog.sqlite"

MATCH_OUTPUT_DIR = DATA_ROOT / "processed" / "match_overlays"
MATCH_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
