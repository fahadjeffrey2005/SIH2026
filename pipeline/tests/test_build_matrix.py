"""match.build_matrix: the interactive metrics-dashboard export.

Everything build_matrix.build() writes beyond the raw inlier/geoloc numbers
(crop images, per-point coordinates, the old-vs-new keypoint-budget replay)
exists to feed frontend/src/components/CorrespondenceViewer.jsx -- a bug
here doesn't fail loudly like a crash, it just makes the interactive viewer
silently render nothing or the wrong points. These tests exercise build()
against fake (but structurally real) MatchResult/context objects so they
run fast and don't need the actual catalog, crops, or DISK/LightGlue
weights -- match.compare.run_pair and match.learned.matcher.match are
mocked at the module level build_matrix imports them into.
"""

import json

import numpy as np
import pytest

import match.build_matrix as build_matrix
from match.classical.matcher import MatchResult

PAIR = {
    "product_a": "ch2_iir_nri_20211221t0324126144_d_img_hw1",
    "instrument_a": "IIRS",
    "product_b": "ch2_tmc_ncf_20240125t0622476078_d_img_d18",
    "instrument_b": "TMC-2",
    "incidence_gap_deg": 26.9,
}


def _result(method, pts_a, pts_b, raw=10, ratio_matches=None, inliers=None):
    pts_a = np.asarray(pts_a, dtype=np.float32)
    pts_b = np.asarray(pts_b, dtype=np.float32)
    n = len(pts_a)
    return MatchResult(
        method=method,
        keypoints_a=500,
        keypoints_b=480,
        raw_matches=raw,
        ratio_test_matches=ratio_matches if ratio_matches is not None else raw,
        inliers=inliers if inliers is not None else n,
        homography=None,
        pts_a=pts_a,
        pts_b=pts_b,
    )


def _fake_context():
    # Small real uint8 arrays so cv2.imwrite (unmocked) succeeds writing
    # actual PNGs -- exercising the real file-write path, not just the
    # JSON-shape assertions.
    crop_a = np.zeros((16, 16), dtype=np.uint8)
    crop_b = np.full((16, 16), 200, dtype=np.uint8)
    return {
        "loaded_a": object(), "loaded_b": object(),
        "crop_a": crop_a, "crop_b": crop_b,
        "origin_a": (0, 0), "origin_b": (0, 0),
        "scale_a": 1.0, "scale_b": 1.0,
    }


@pytest.fixture
def patched(monkeypatch, tmp_path):
    """Wires build_matrix's collaborators to deterministic fakes and
    redirects CELL_IMAGE_DIR under tmp_path so nothing touches the real
    docs/img/matrix_cells/ or the real catalog."""
    monkeypatch.setattr(build_matrix, "matchable_pairs", lambda: [dict(PAIR)])
    monkeypatch.setattr(build_matrix, "CELL_IMAGE_DIR", tmp_path / "matrix_cells")

    sift_pts_a = [[1, 2], [3, 4], [5, 6], [7, 8], [9, 10], [11, 12], [13, 14]]
    sift_pts_b = [[2, 3], [4, 5], [6, 7], [8, 9], [10, 11], [12, 13], [14, 15]]
    akaze_pts_a = [[1, 1], [2, 2]]
    akaze_pts_b = [[1, 2], [2, 3]]
    disk_pts_a = [[5, 5], [6, 6], [7, 7], [8, 8]]
    disk_pts_b = [[5, 6], [6, 7], [7, 8], [8, 9]]

    ctx = _fake_context()

    def fake_run_pair(id_a, id_b):
        results = {
            "sift": _result("sift", sift_pts_a, sift_pts_b, raw=25, ratio_matches=25, inliers=7),
            "akaze": _result("akaze", akaze_pts_a, akaze_pts_b, raw=6, ratio_matches=6, inliers=2),
            "disk_lightglue": _result("disk_lightglue", disk_pts_a, disk_pts_b, raw=11, ratio_matches=11, inliers=4),
        }
        geoloc = {
            "sift": {"median_m": 186679.5, "p90_m": 250000.0},
            "akaze": {"median_m": 190000.0, "p90_m": 260000.0},
            "disk_lightglue": {"median_m": 230124.4, "p90_m": 240000.0},
        }
        point_errors = {
            "sift": np.array([1.0] * len(sift_pts_a)),
            "akaze": np.array([2.0] * len(akaze_pts_a)),
            "disk_lightglue": np.array([3.0] * len(disk_pts_a)),
        }
        return {"results": results, "geoloc": geoloc, "point_errors": point_errors, "context": ctx}

    monkeypatch.setattr(build_matrix, "run_pair", fake_run_pair)

    # _old_disk_variant calls learned_matcher.match(...) directly, then
    # build_matrix's own imported geolocation_errors_m/summarize_errors --
    # fake all three so the "old" (pre-fix) replay is deterministic and
    # doesn't need real crops or a real BilinearGeoTransform.
    old_result = _result("disk_lightglue", [], [], raw=23, ratio_matches=23, inliers=0)
    monkeypatch.setattr(build_matrix.learned_matcher, "match", lambda *a, **k: old_result)
    monkeypatch.setattr(build_matrix, "geolocation_errors_m", lambda *a, **k: np.array([]))
    monkeypatch.setattr(build_matrix, "summarize_errors", lambda errors: {"median_m": None, "p90_m": None})

    return {"sift_n": len(sift_pts_a), "akaze_n": len(akaze_pts_a), "disk_n": len(disk_pts_a)}


def test_writes_one_crop_image_pair_per_pair(patched, tmp_path):
    matrix = build_matrix.build(tmp_path / "out.json")
    rows = matrix["rows"]

    image_files = {rows[0]["crop_image_a"], rows[0]["crop_image_b"]}
    assert len(image_files) == 2
    for row in rows:
        # Same pair -> same two crop filenames on every method's row.
        assert {row["crop_image_a"], row["crop_image_b"]} == image_files
        for fname in (row["crop_image_a"], row["crop_image_b"]):
            assert (build_matrix.CELL_IMAGE_DIR / fname).is_file()


def test_points_and_point_errors_round_trip_per_method(patched, tmp_path):
    matrix = build_matrix.build(tmp_path / "out.json")
    by_method = {r["method"]: r for r in matrix["rows"]}

    assert len(by_method["sift"]["points_a"]) == patched["sift_n"]
    assert len(by_method["sift"]["points_b"]) == patched["sift_n"]
    assert len(by_method["sift"]["point_geoloc_errors_m"]) == patched["sift_n"]
    # JSON-serializable plain lists, not numpy arrays.
    assert isinstance(by_method["sift"]["points_a"], list)
    assert isinstance(by_method["sift"]["points_a"][0], list)

    assert len(by_method["akaze"]["points_a"]) == patched["akaze_n"]
    assert len(by_method["disk_lightglue"]["points_a"]) == patched["disk_n"]


def test_keypoint_budget_comparison_only_on_disk_lightglue_rows(patched, tmp_path):
    matrix = build_matrix.build(tmp_path / "out.json")
    by_method = {r["method"]: r for r in matrix["rows"]}

    assert "keypoint_budget_comparison" not in by_method["sift"]
    assert "keypoint_budget_comparison" not in by_method["akaze"]

    comparison = by_method["disk_lightglue"]["keypoint_budget_comparison"]
    assert comparison["new"]["max_keypoints"] == 4096
    assert comparison["new"]["inliers"] == 4
    assert comparison["new"]["points_a"] == by_method["disk_lightglue"]["points_a"]

    assert comparison["old"]["max_keypoints"] == build_matrix.OLD_DISK_MAX_KEYPOINTS == 2048
    assert comparison["old"]["inliers"] == 0
    assert comparison["old"]["points_a"] == []
    assert comparison["old"]["points_b"] == []


def test_output_is_valid_json_written_to_disk(patched, tmp_path):
    out_path = tmp_path / "out.json"
    matrix = build_matrix.build(out_path)
    on_disk = json.loads(out_path.read_text())
    assert on_disk == matrix
    assert on_disk["generated_from"] == "pipeline/match/build_matrix.py"
    assert len(on_disk["rows"]) == 3  # sift, akaze, disk_lightglue for the one fake pair
