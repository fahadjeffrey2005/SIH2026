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
```

Track B (learned) is DISK+LightGlue via `kornia`, not LoFTR as originally named in docs/architecture.md -- kornia's only pretrained LoFTR weights are hosted on a host this environment's egress policy blocks; DISK/LightGlue's GitHub-hosted weights aren't. First run downloads ~50MB of pretrained weights (needs network access to `raw.githubusercontent.com` / `github.com/cvg/LightGlue`).

See [`docs/baseline_results.md`](docs/baseline_results.md) for the real numbers: the classical baseline finds real correspondences on the low-sun-angle-gap pair (26.9°) and finds *none* on the high-gap, cross-modality pair (34.7°); the pretrained learned baseline, used zero-shot, does *not* beat classical on the low-gap pair (0 inliers vs SIFT's 7) and also fails on the high-gap pair. That's a genuine result, sanity-checked against both tracks' self-match performance, not a bug.

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

3 screens working end-to-end against a live backend as of this writing: catalog browser (real catalog data, filterable by instrument), pair picker (genuinely-overlapping candidates from `/pairs/suggest`, sorted by sun-angle gap), results view (job submission + polling, inlier/keypoint metrics, correspondence overlay image) with all 3 methods selectable (SIFT, AKAZE, DISK+LightGlue). Uses a plain `<img>` for the overlay rather than OpenSeadragon deep-zoom for now -- that needs a tile pyramid per product, which isn't built yet (see docs/architecture.md Sec. 7); swapping it in later doesn't require changing the job/result data shape. The 4th screen (metrics dashboard crossing instrument-pair x sun-angle-bucket x method) is not built yet -- there are only 2 pairs' worth of real numbers so far (docs/baseline_results.md).

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
