# SIH26166 — Multi-Modal, Sun-Angle & Scale-Invariant Lunar Image Correspondence

Chandrayaan-2 OHRC / TMC-2 / IIRS image correspondence pipeline for Smart India Hackathon 2026, problem statement SIH26166.

See [`docs/architecture.md`](docs/architecture.md) for the full system design, ML approach, and phased plan.

## Repo layout

- `pipeline/` — pure-Python ingest, georeferencing, preprocessing, matching (classical + learned), and evaluation code. No web framework dependency — runs standalone from notebooks or the CLI.
- `backend/` — FastAPI service wrapping `pipeline/` for the frontend.
- `frontend/` — React demo/judging UI.
- `data/` — raw PDS4 downloads (`data/raw/`), processed arrays/tiles (`data/processed/`), and the product catalog (`data/catalog.sqlite`).
- `notebooks/` — exploration notebooks, one per experiment.
- `docs/` — architecture and evaluation write-ups.

## Quickstart (pipeline)

```bash
cd pipeline
pip install -r requirements.txt
python -m ingest.build_catalog          # populate data/catalog.sqlite from data/raw/

# classical matching baseline (SIFT/AKAZE + RANSAC) on a confirmed-overlapping pair
python -m match.classical.demo ch2_iir_nri_20211221t0324126144_d_img_hw1 ch2_tmc_ncf_20240125t0622476078_d_img_d18 --out /tmp/match.png

# both tracks (classical SIFT/AKAZE + learned DISK/LightGlue) on one pair, side by side
python -m match.compare ch2_iir_nri_20211221t0324126144_d_img_hw1 ch2_tmc_ncf_20240125t0622476078_d_img_d18 --out-dir /tmp/compare

# native-resolution follow-up on the pair that failed at browse resolution (see docs/baseline_results.md)
python -m match.native_demo
```

Track B (learned) is DISK+LightGlue via `kornia`, not LoFTR as originally named in docs/architecture.md -- kornia's only pretrained LoFTR weights are hosted on a host this environment's egress policy blocks; DISK/LightGlue's GitHub-hosted weights aren't. First run downloads ~50MB of pretrained weights (needs network access to `raw.githubusercontent.com` / `github.com/cvg/LightGlue`).

See [`docs/baseline_results.md`](docs/baseline_results.md) for the real numbers: at browse resolution, the classical baseline finds real correspondences up to a 34.0° sun-angle gap and finds none on the highest-gap, cross-modality pair (34.7°, cross-instrument OHRC+TMC-2); the pretrained learned baseline (DISK+LightGlue), used zero-shot, ties classical inlier counts (4 inliers) on every pair that has any correspondences at all, once its keypoint budget is raised from 2048 to 4096 -- an early "DISK+LightGlue fails past 26.9°" result turned out to be partly a keypoint-starvation artifact on these low-texture crops, not pure domain gap (see "Track B keypoint-budget fix"). A native-resolution follow-up on the 34.7° pair (`match.native_demo`) recovers real correspondences from all three methods that browse resolution missed entirely (SIFT/AKAZE 4 inliers each, DISK+LightGlue 4 inliers at 80% inlier ratio -- the tightest geoloc agreement of the three). See docs/baseline_results.md's "Track B keypoint-budget fix" and "Native-resolution follow-up" sections for the full read.

## Quickstart (backend)

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Quickstart (frontend)

```bash
cd frontend
npm install
npm run dev          # expects the backend at http://localhost:8000; override with VITE_API_BASE
```

All 4 planned screens working end-to-end against a live backend: catalog browser (real catalog data, filterable by instrument), pair picker (genuinely-overlapping candidates from `/pairs/suggest`, sorted by sun-angle gap, all 3 methods selectable), results view (job submission + polling, inlier/keypoint metrics, correspondence overlay image), and a metrics dashboard (the full instrument-pair x sun-angle-gap x method matrix from `GET /metrics/matrix`, color-coded by whether real correspondences were found -- see docs/baseline_results.md for the reading). Uses a plain `<img>` for the results-view overlay rather than OpenSeadragon deep-zoom for now -- that needs a tile pyramid per product, which isn't built yet (see docs/architecture.md Sec. 7); swapping it in later doesn't require changing the job/result data shape.

The metrics dashboard's cells are clickable: selecting one expands an interactive correspondence viewer (`frontend/src/components/CorrespondenceViewer.jsx`) below the table showing the two real source crops (`GET /metrics/matrix/crop/{filename}`) with that cell's actual RANSAC-inlier points drawn as a hoverable, independently pannable/zoomable overlay on each side -- hovering one matched point highlights its partner on the other image and shows that specific correspondence's own geolocation-agreement distance, not just the row's aggregate median. DISK+LightGlue cells additionally carry a keypoint-budget toggle that swaps between the pre-fix (2048) and post-fix (4096) point sets -- real numbers from `pipeline/match/build_matrix.py` re-running the same crops at the old budget, not a mocked-up illustration (see docs/baseline_results.md's "Track B keypoint-budget fix").

Below the dashboard, a rotating 3D Moon (`frontend/src/components/MoonGlobe.jsx`, three.js) plots every product's real footprint at its actual lat/lon, on a base sphere textured with NASA's own real LROC global color mosaic (public domain, credit NASA's Scientific Visualization Studio) rather than a stylized placeholder. Wherever the raw imagery is actually staged (`has_raster`), the patch shows that product's own real Chandrayaan-2 photo (`GET /products/{id}/browse`), tinted by its own real solar-incidence angle -- the same number behind the dashboard's "incidence gap" column, now shown as an actual place on the Moon rather than just a table entry; the rest show that same color as a flat fill, since there's no real pixel data for them yet. Footprints are tiny at true scale (some under a degree wide, some 35-48deg-long-but-under-1deg-wide swaths), so each is exaggerated for visibility and subdivided into a curved grid so long swaths hug the sphere instead of rendering as a dashed line (see docs/baseline_results.md's "3D Moon" section for both fixes and their failure modes). Hovering a patch shows its product ID and incidence angle; clicking one syncs the catalog browser's selection and flies the camera in for a close look, and scrolling reaches true pixel-level zoom on the real imagery. Degrades to a plain-text notice on browsers without WebGL rather than breaking the page.

## Testing

`pipeline/`, `backend/`, and `frontend/` each have their own test suite, and all three run in CI on every push/PR (`.github/workflows/ci.yml`) against nothing but a fresh `git clone` -- no secrets, no downloading the raw PDS4 zips (those stay gitignored for size; the small real PDS4 `.xml` labels needed to build the catalog *are* committed, see `.gitignore`'s comment on that).

`pipeline/` and `backend/` run against real project data (not mocks) -- the same "verify against ground truth" discipline used throughout this build. Several tests are permanent regressions for real bugs found during development (corner-block ambiguity, the `overlap_crop` extrapolation blowup, the OHRC-2021/TMC-2-2024-01-25 near-miss, the DISK OOM crash, the SystemExit-vs-ValueError job-hang bug, the Track B keypoint-starvation fix).

```bash
cd pipeline
pip install -r requirements.txt
python -m ingest.build_catalog   # populate data/catalog.sqlite from the committed PDS4 labels (needed by backend tests too)
pytest                    # full suite, incl. slow DISK+LightGlue tests (downloads weights on first run)
pytest -m "not slow"      # fast subset only (~1min) -- skips anything needing torch/kornia
```

```bash
cd backend
pip install -r requirements.txt -r ../pipeline/requirements.txt
pytest                    # exercises the live FastAPI app via TestClient against data/catalog.sqlite
```

`frontend/` has Vitest + React Testing Library component tests for all 4 screens plus an `App.jsx` integration test that mocks only `api.js` and drives the real component tree (catalog load -> select -> suggest -> submit -> poll -> render result):

```bash
cd frontend
npm install
npm test        # component + integration tests (jsdom, no real backend needed)
npm run lint    # oxlint
npm run build   # production build
```

## Data

Raw PDS4 zips go under `data/raw/<instrument>/`. As of 2026-09-01 the team has downloaded 8 products from a verified equatorial overlap site (~lon -23.4 to -23.5°E, lat -2.6 to -3.4°S):

| Instrument | Date | Product ID |
|---|---|---|
| OHRC | 2021-04-05 | ch2_ohr_ncp_20210405T1606536730_d_img_d18 |
| OHRC | 2021-04-05 | ch2_ohr_ncp_20210405T1606537227_d_img_d18 |
| IIRS | 2021-12-21 | ch2_iir_nri_20211221T0324126144_d_img_hw1 |
| TMC-2 | 2024-01-25 | ch2_tmc_ncf_20240125T0622476078_d_img_d18 |
| TMC-2 | 2024-01-25 | ch2_tmc_nca_20240125T0622476111_d_img_d18 |
| TMC-2 | 2025-08-07 | ch2_tmc_ncf_20250807T1904346039_d_img_d18 |
| TMC-2 | 2025-08-07 | ch2_tmc_nca_20250807T1904346006_d_img_d18 |
| TMC-2 | 2025-08-07 | ch2_tmc_ncn_20250807T1904346006_d_img_d18 |

**Real sun-angle metadata** (from each product's own PDS4 label — `solar_incidence_deg`, no ephemeris computation needed):

| Product | Solar incidence |
|---|---|
| IIRS 2021-12-21 | 7.3° |
| TMC-2 2024-01-25 | 34.1° |
| TMC-2 2025-08-07 | 41.2° |
| OHRC 2021-04-05 | 75.9° |

**Real footprint-overlap check** (spherical point-in-quad on each product's corner coordinates, not the date gap): OHRC's 2021-04-05 footprint does **not** actually reach TMC-2's 2024-01-25 swath — that pair looked plausible by date but the geometry misses (confirmed genuine, not a bug: OHRC's western edge sits ~0.006° outside TMC-2024's strip at that latitude). Every other cross-instrument pair at this site does overlap. That gives two validated, geometry-checked combinations instead of the earlier date-based guess:

- **Bi-modal, low sun-angle gap**: IIRS 2021-12-21 + TMC-2 2024-01-25 — confirmed overlapping, incidence gap 26.9° (7.3° vs 34.1°). No OHRC in this one.
- **Tri-modal, high sun-angle gap**: OHRC 2021-04-05 + IIRS 2021-12-21 + TMC-2 2025-08-07 — all three confirmed mutually overlapping, incidence span 68.6° (7.3° to 75.9°).

A second, richer south-polar site (Chandrayaan-3 landing zone, 69.37°S 32.35°E — 17 OHRC + 2 IIRS + 3 TMC-2 verified overlapping scenes) is identified but not yet downloaded.
