"""End-to-end tests for the FastAPI app against the real data/catalog.sqlite
and staged rasters (no mocking) -- this project's established discipline of
verifying against ground truth rather than static review, applied to the
backend layer. Two of these tests are direct regressions for bugs found
during this build:

  * test_pairs_suggest_excludes_non_overlapping_tmc2024_pair pins down the
    OHRC-2021 / TMC-2-2024-01-25 near-miss (see pipeline/tests/
    test_geo_footprint.py) at the API layer.
  * test_match_failure_path_settles_to_failed_not_hung is the regression
    test for the SystemExit-vs-ValueError bug: demo.load() used to raise
    SystemExit for an unregistered product, which escaped run_match_job's
    `except Exception` and left jobs stuck "running" forever. Fixed by
    raising ValueError instead (see pipeline/match/classical/demo.py).
"""

from __future__ import annotations

import io
import time

from fastapi.testclient import TestClient
from PIL import Image

from app.main import app

client = TestClient(app)

# Real catalog product ids (data/catalog.sqlite), reused across tests.
OHRC_2021 = "ch2_ohr_ncp_20210405t1606536730_d_img_d18"  # has raster (browse PNG)
OHRC_2021_NO_RASTER = "ch2_ohr_ncp_20210405t1606537227_d_img_d18"  # in catalog, no raster staged
TMC2_2024_NCF = "ch2_tmc_ncf_20240125t0622476078_d_img_d18"  # genuinely does NOT overlap OHRC_2021
TMC2_2024_NCA = "ch2_tmc_nca_20240125t0622476111_d_img_d18"  # same near-miss, different strip
TMC2_2025_NCF = "ch2_tmc_ncf_20250807t1904346039_d_img_d18"  # has raster, overlaps OHRC_2021
IIRS_2021 = "ch2_iir_nri_20211221t0324126144_d_img_hw1"  # has raster, overlaps everything here


def _poll_job(job_id: str, timeout_s: float = 60.0) -> dict:
    """TestClient's synchronous ASGI transport actually runs BackgroundTasks
    to completion before POST /match returns, so the job is usually already
    terminal by the time we get here -- but poll anyway rather than assuming
    that implementation detail, so this test survives a transport change."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        resp = client.get(f"/match/{job_id}")
        assert resp.status_code == 200
        body = resp.json()
        if body["status"] in ("done", "failed"):
            return body
        time.sleep(0.2)
    raise AssertionError(f"job {job_id} did not settle within {timeout_s}s")


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_list_products():
    resp = client.get("/products")
    assert resp.status_code == 200
    products = {p["product_id"]: p for p in resp.json()}

    assert OHRC_2021 in products
    assert products[OHRC_2021]["instrument"] == "OHRC"
    assert products[OHRC_2021]["has_raster"] is True

    # In the catalog with real metadata, but its raster hasn't been staged
    # past the label -- has_raster must say so honestly rather than default True.
    assert products[OHRC_2021_NO_RASTER]["has_raster"] is False

    assert products[IIRS_2021]["has_raster"] is True


def test_pairs_suggest_excludes_non_overlapping_tmc2024_pair():
    """API-level regression for the OHRC-2021 / TMC-2-2024-01-25 near-miss:
    bboxes overlap but the true footprints don't (see
    pipeline/tests/test_geo_footprint.py). /pairs/suggest must not offer
    either 2024-01-25 TMC-2 strip as a candidate for OHRC_2021, but must
    still offer the genuinely-overlapping 2025 strip and IIRS."""
    resp = client.get("/pairs/suggest", params={"product_id": OHRC_2021})
    assert resp.status_code == 200
    suggestions = {s["product_id"]: s for s in resp.json()}

    assert TMC2_2024_NCF not in suggestions
    assert TMC2_2024_NCA not in suggestions

    assert TMC2_2025_NCF in suggestions
    assert suggestions[TMC2_2025_NCF]["has_raster"] is True
    assert IIRS_2021 in suggestions

    # Sorted ascending by incidence gap.
    gaps = [s["incidence_gap_deg"] for s in resp.json() if s["incidence_gap_deg"] is not None]
    assert gaps == sorted(gaps)


def test_pairs_suggest_unknown_product_404():
    resp = client.get("/pairs/suggest", params={"product_id": "not_a_real_product"})
    assert resp.status_code == 404


def test_match_happy_path_sift():
    resp = client.post("/match", json={
        "product_a": OHRC_2021,
        "product_b": TMC2_2025_NCF,
        "method": "sift",
    })
    assert resp.status_code == 200
    job = resp.json()
    assert job["status"] in ("queued", "running", "done")

    settled = _poll_job(job["job_id"])
    assert settled["status"] == "done", settled.get("error")
    result = settled["result"]
    assert result["keypoints_a"] > 0
    assert result["keypoints_b"] > 0
    assert "raw_matches" in result
    assert "inlier_ratio" in result
    assert result["overlay_url"] == f"/match/{job['job_id']}/overlay"

    overlay = client.get(result["overlay_url"])
    assert overlay.status_code == 200
    assert overlay.headers["content-type"] == "image/png"


def test_match_happy_path_hopc():
    """Same shape as test_match_happy_path_sift, against the real
    IIRS_2021/TMC2_2024_NCF pair (26.9deg incidence gap) rather than
    OHRC_2021/TMC2_2025_NCF -- this is the pair HOPC's own tuned ratio
    threshold (match.classical.matcher.match's method-specific default, see
    that module) was verified to find a real, geolocation-consistent match
    on (see docs/baseline_results.md's "HOPC" section); the harder
    OHRC/TMC-2 pair is one of the two where HOPC's nominal RANSAC result
    was found NOT to hold up to scrutiny, so it isn't the right pair to
    lock in as a "this works" regression test."""
    resp = client.post("/match", json={
        "product_a": IIRS_2021,
        "product_b": TMC2_2024_NCF,
        "method": "hopc",
    })
    assert resp.status_code == 200
    job = resp.json()

    settled = _poll_job(job["job_id"])
    assert settled["status"] == "done", settled.get("error")
    result = settled["result"]
    assert result["keypoints_a"] > 0
    assert result["keypoints_b"] > 0
    assert result["inliers"] >= 5  # real run finds 14; a wide floor keeps this from being flaky

    overlay = client.get(result["overlay_url"])
    assert overlay.status_code == 200


def test_match_failure_path_settles_to_failed_not_hung():
    """Regression test: submitting a product with no raster staged used to
    raise SystemExit deep in demo.load(), which escaped run_match_job's
    `except Exception` and left the job stuck at status="running" forever
    (found via live end-to-end testing, not code review). It must now
    settle to "failed" with a readable error."""
    resp = client.post("/match", json={
        "product_a": OHRC_2021_NO_RASTER,
        "product_b": OHRC_2021,
        "method": "sift",
    })
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]

    settled = _poll_job(job_id)
    assert settled["status"] == "failed"
    assert settled["error"] is not None
    assert OHRC_2021_NO_RASTER in settled["error"]


def test_match_unknown_method_422():
    resp = client.post("/match", json={
        "product_a": OHRC_2021,
        "product_b": TMC2_2025_NCF,
        "method": "not_a_real_method",
    })
    assert resp.status_code == 422


def test_match_unknown_job_404():
    resp = client.get("/match/not_a_real_job_id")
    assert resp.status_code == 404


def test_metrics_matrix():
    resp = client.get("/metrics/matrix")
    assert resp.status_code == 200
    body = resp.json()
    rows = body["rows"]
    assert isinstance(rows, list)
    assert len(rows) > 0
    row = rows[0]
    for key in ("product_a", "product_b", "method", "inliers", "inlier_ratio"):
        assert key in row


def test_metrics_matrix_crop_serves_a_real_row_image():
    """The interactive correspondence viewer's whole premise is that
    crop_image_a/crop_image_b (from GET /metrics/matrix) are directly
    loadable via GET /metrics/matrix/crop/{filename} -- exercised here
    end-to-end against the real docs/baseline_matrix.json + docs/img/
    matrix_cells/ build_matrix.py already produced, not a mocked filename."""
    rows = client.get("/metrics/matrix").json()["rows"]
    filename = rows[0]["crop_image_a"]

    resp = client.get(f"/metrics/matrix/crop/{filename}")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert len(resp.content) > 0


def test_metrics_matrix_crop_404s_for_unknown_filename():
    resp = client.get("/metrics/matrix/crop/ch2_fake__ch2_alsofake__a.png")
    assert resp.status_code == 404


def test_metrics_matrix_crop_rejects_path_traversal():
    """_SAFE_FILENAME is a defense-in-depth guard against a filename that
    doesn't match build_matrix.py's own naming convention -- confirm a
    traversal attempt 404s rather than escaping CELL_IMAGE_DIR."""
    resp = client.get("/metrics/matrix/crop/..%2F..%2F..%2Fetc%2Fpasswd")
    assert resp.status_code == 404


def test_product_browse_serves_a_real_image_for_a_has_raster_product():
    """The 3D Moon drapes a product's own real image onto its footprint
    patch (GET /products/{id}/browse) rather than a flat color fill --
    exercised here against OHRC_2021's actual browse PNG on disk, not a
    mocked file."""
    resp = client.get(f"/products/{OHRC_2021}/browse")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"
    assert len(resp.content) > 0


def test_product_browse_caps_the_long_side_at_8192_for_a_larger_source_image():
    """OHRC_2021's real browse PNG is ~1200x9369 -- long past the resize
    cap. The 3D Moon lets a user zoom in close enough to fill the screen
    with one patch (MoonGlobe.jsx's MIN_CAMERA_DISTANCE), so this cap is a
    GPU-texture-size safety limit, not a "small enough" one -- confirm it's
    actually applied rather than silently serving the multi-thousand-pixel
    original."""
    resp = client.get(f"/products/{OHRC_2021}/browse")
    image = Image.open(io.BytesIO(resp.content))
    assert max(image.size) <= 8192


def test_product_browse_serves_an_already_small_image_at_full_resolution():
    """IIRS_2021's real browse PNG (175x3902) is already under the resize
    cap -- it should come back untouched, not needlessly downsampled."""
    resp = client.get(f"/products/{IIRS_2021}/browse")
    image = Image.open(io.BytesIO(resp.content))
    assert image.size == (175, 3902)


def test_product_browse_404s_for_a_product_with_no_raster_staged():
    resp = client.get(f"/products/{OHRC_2021_NO_RASTER}/browse")
    assert resp.status_code == 404


def test_product_browse_404s_for_an_unknown_product_id():
    resp = client.get("/products/not_a_real_product/browse")
    assert resp.status_code == 404
