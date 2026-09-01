from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse

from ..config import MATCH_OUTPUT_DIR
from ..jobs import create_job, get_job, run_match_job
from ..schemas import MatchJobOut, MatchRequest

router = APIRouter(tags=["match"])


def _job_out(job) -> MatchJobOut:
    return MatchJobOut(
        job_id=job.job_id, status=job.status, product_a=job.product_a,
        product_b=job.product_b, method=job.method, error=job.error, result=job.result,
    )


@router.post("/match", response_model=MatchJobOut)
def submit_match(req: MatchRequest, background_tasks: BackgroundTasks):
    if req.method not in ("sift", "akaze"):
        raise HTTPException(422, f"unknown method {req.method!r}, expected 'sift' or 'akaze'")
    job = create_job(req.product_a, req.product_b, req.method)
    background_tasks.add_task(run_match_job, job.job_id)
    return _job_out(job)


@router.get("/match/{job_id}", response_model=MatchJobOut)
def get_match(job_id: str):
    job = get_job(job_id)
    if job is None:
        raise HTTPException(404, f"no job {job_id!r}")
    return _job_out(job)


@router.get("/match/{job_id}/overlay")
def get_overlay(job_id: str):
    job = get_job(job_id)
    if job is None:
        raise HTTPException(404, f"no job {job_id!r}")
    path = MATCH_OUTPUT_DIR / f"{job_id}.png"
    if not path.exists():
        raise HTTPException(409, f"job {job_id!r} status is {job.status!r}, no overlay yet")
    return FileResponse(path, media_type="image/png")
