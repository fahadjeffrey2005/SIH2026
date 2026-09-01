from __future__ import annotations

import sqlite3
from contextlib import contextmanager

from .config import CATALOG_DB


@contextmanager
def catalog_conn():
    if not CATALOG_DB.exists():
        raise FileNotFoundError(
            f"{CATALOG_DB} not found -- run `python -m ingest.build_catalog` "
            "from pipeline/ first"
        )
    conn = sqlite3.connect(CATALOG_DB)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def row_corners(row: sqlite3.Row) -> dict:
    corners = {}
    for c in ("ul", "ur", "ll", "lr"):
        lat, lon = row[f"{c}_lat"], row[f"{c}_lon"]
        if lat is not None and lon is not None:
            corners[c] = (lat, lon)
    return corners
