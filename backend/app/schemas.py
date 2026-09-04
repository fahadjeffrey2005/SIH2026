from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class ProductOut(BaseModel):
    product_id: str
    instrument: str
    start_time: Optional[str] = None
    stop_time: Optional[str] = None
    orbit_number: Optional[int] = None
    sun_azimuth_deg: Optional[float] = None
    sun_elevation_deg: Optional[float] = None
    solar_incidence_deg: Optional[float] = None
    corner_source: Optional[str] = None
    corners: dict
    has_raster: bool


class PairSuggestion(BaseModel):
    product_id: str
    instrument: str
    solar_incidence_deg: Optional[float] = None
    incidence_gap_deg: Optional[float] = None
    has_raster: bool  # whether match/classical/demo.py can currently load pixel data for it


class MatchRequest(BaseModel):
    product_a: str
    product_b: str
    method: str = "sift"  # "sift" | "akaze" | "hopc" (Track A, classical) | "disk_lightglue" (Track B, learned)


class MatchJobOut(BaseModel):
    job_id: str
    status: str  # "queued" | "running" | "done" | "failed"
    product_a: str
    product_b: str
    method: str
    error: Optional[str] = None
    result: Optional[dict] = None
