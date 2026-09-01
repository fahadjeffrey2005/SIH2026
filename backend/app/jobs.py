"""In-memory job store for matching runs.

Hackathon-scale choice per docs/architecture.md Sec. 6: FastAPI
BackgroundTasks + an in-memory dict is enough here; jobs don't survive a
server restart, and that's an acceptable tradeoff until queueing actually
becomes a bottleneck (at which point: Celery/RQ + a real broker).

Matching itself reuses pipeline/match/classical/demo.py's load/crop/prep
functions verbatim rather than reimplementing them here -- see main.py for
how pipeline/ gets onto sys.path before this module is imported.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Optional

import cv2
from match.classical import matcher as classical_matcher
from match.classical.demo import browse_gsd_m, draw_matches, load, prep_crop
from match.learned import matcher as learned_matcher

from .config import MATCH_OUTPUT_DIR

_JOBS: dict[str, "Job"] = {}

_CLASSICAL_METHODS = ("sift", "akaze")
_LEARNED_METHODS = ("disk_lightglue",)
ALL_METHODS = _CLASSICAL_METHODS + _LEARNED_METHODS


@dataclass
class Job:
    job_id: str
    product_a: str
    product_b: str
    method: str
    status: str = "queued"
    error: Optional[str] = None
    result: Optional[dict] = None


def create_job(product_a: str, product_b: str, method: str) -> Job:
    job = Job(job_id=uuid.uuid4().hex[:12], product_a=product_a, product_b=product_b, method=method)
    _JOBS[job.job_id] = job
    return job


def get_job(job_id: str) -> Optional[Job]:
    return _JOBS.get(job_id)


def run_match_job(job_id: str) -> None:
    job = _JOBS[job_id]
    job.status = "running"
    try:
        a = load(job.product_a)
        b = load(job.product_b)
        target_gsd = max(browse_gsd_m(a), browse_gsd_m(b))
        crop_a, _origin_a = prep_crop(a, b, target_gsd)
        crop_b, _origin_b = prep_crop(b, a, target_gsd)

        if job.method in _CLASSICAL_METHODS:
            result = classical_matcher.match(crop_a, crop_b, method=job.method)
            raw_matches = result.ratio_test_matches
        elif job.method in _LEARNED_METHODS:
            result = learned_matcher.match(crop_a, crop_b)
            raw_matches = result.raw_matches
        else:
            raise ValueError(f"unknown method {job.method!r}, expected one of {ALL_METHODS}")

        overlay_path = MATCH_OUTPUT_DIR / f"{job_id}.png"
        vis = draw_matches(crop_a, crop_b, result)
        cv2.imwrite(str(overlay_path), vis)

        job.result = {
            "keypoints_a": result.keypoints_a,
            "keypoints_b": result.keypoints_b,
            "raw_matches": raw_matches,
            "inliers": result.inliers,
            "inlier_ratio": result.inlier_ratio,
            "overlay_url": f"/match/{job_id}/overlay",
            "working_gsd_m": target_gsd,
        }
        job.status = "done"
    except Exception as exc:
        # Surfaced via GET /match/{id} as status="failed" rather than a 500
        # from the background task (which FastAPI would otherwise just log
        # and the client would never see) -- the job already exists and the
        # client is polling it.
        job.status = "failed"
        job.error = str(exc)
