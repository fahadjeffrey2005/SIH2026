# SIH26166 — Multi-Modal, Sun-Angle & Scale-Invariant Lunar Image Correspondence
## System Architecture & Execution Plan

*Chandrayaan-2 OHRC / TMC-2 / IIRS correspondence pipeline — v1 plan, 2026-09-01*

---

## 1. Problem restatement

Given two lunar images of overlapping ground area, taken by different instruments and/or under different illumination, find corresponding points between them. The three instruments differ enormously:

| Instrument | GSD | Swath | Type | Notes |
|---|---|---|---|---|
| OHRC | 0.25–0.28 m | ~3 km | Panchromatic | Extremely high res, sparse catalog |
| TMC-2 | 5 m | ~20 km | Panchromatic | ~20x coarser than OHRC |
| IIRS | 80 m | ~20 km | Hyperspectral (~250 bands) | ~320x coarser than OHRC |

Two compounding difficulties on top of ordinary image matching:
- **Scale gap**: up to ~320x GSD difference between OHRC and IIRS — far beyond what a single-scale detector handles.
- **Sun-angle gap**: the same crater rim looks like a bright ridge at one sun azimuth/elevation and a black shadow-edge at another. Classical intensity/gradient descriptors (SIFT, ORB) degrade badly under shadow inversion.
- **Modality gap**: IIRS is a hyperspectral cube, not a single-band panchromatic image — needs a band-selection or fusion step before it can be compared to OHRC/TMC-2 at all.
- **No labeled ground truth**: nobody has hand-annotated correspondences between these products. The only geometric truth available is each product's PDS4 corner geolocation (lat/lon), which is coarse and only good to the level of "these two footprints overlap here" — not pixel-accurate.

Our two acquired datasets are built exactly to stress-test this: an equatorial site with a low-sun-angle-gap pair and a high-sun-angle-gap pair, plus a richer south-polar (Chandrayaan-3 landing zone) site for later.

---

## 2. Repository layout

```
sih26166/
├── data/
│   ├── raw/                    # untouched PDS4 downloads, one folder per product
│   │   ├── ohrc/
│   │   ├── tmc2/
│   │   └── iirs/
│   ├── processed/               # decoded arrays + normalized metadata (parquet/json)
│   └── catalog.sqlite           # product index: id, instrument, date, footprint, paths
├── pipeline/                     # pure-python, no web framework — the ML/CV core
│   ├── ingest/                   # PDS4 label parsing, band/array extraction
│   ├── geo/                      # georeferencing, reprojection, footprint math
│   ├── preprocess/                # radiometric normalization, tiling, pyramids
│   ├── match/
│   │   ├── classical/            # SIFT/ORB/AKAZE + RANSAC baseline
│   │   └── learned/               # LoFTR / LightGlue wrappers
│   └── eval/                     # metrics, pseudo-ground-truth generation
├── backend/                       # FastAPI service wrapping pipeline/
│   ├── app/
│   │   ├── api/                  # routes
│   │   ├── jobs/                  # background task queue for matching runs
│   │   └── db/                    # ORM models, migrations
│   └── tests/
├── frontend/                      # React app for demo/judging
│   └── src/
├── notebooks/                     # exploration, one notebook per experiment
└── docs/
    ├── architecture.md            # this document
    └── eval_report.md             # filled in as results come in
```

Rationale: `pipeline/` has zero web-framework dependency so it can be unit-tested and run from notebooks independently of the backend — important given hackathon time pressure, you don't want ML iteration blocked on API plumbing.

---

## 3. Data layer

**Ingest.** Each PDS4 product ships as a `.zip` containing an image file (often `.img`/`.tif`/`.qub`) plus an XML label. Use the `pdr` (PlanetaryDataReader) library first — it understands PDS4 labels natively and returns a labeled xarray/numpy structure; fall back to manual XML parsing + `rasterio`/GDAL if `pdr` chokes on ISRO's specific label dialect (worth budgeting a few hours to check this early — PDS4 label schemas vary by mission and ISRO's may need a small custom reader).

**Check the PDS4 label itself for sun-angle metadata** before assuming it's unavailable — the ISSDC *catalog* (WFS `INC_ANGLE`/`EMI_ANGLE`/`PHA_ANGLE` fields) was unpopulated for every product we checked, but the per-product PDS4 XML label that ships *inside* the downloaded zip is a different, richer metadata source and planetary PDS4 labels commonly carry `img:Illumination_Direction`, `SUB_SOLAR_AZIMUTH`, `SUB_SOLAR_LATITUDE/LONGITUDE`, or incidence/emission/phase angles even when the map-browse catalog doesn't expose them. If present, this replaces the "date-gap as sun-angle-variance proxy" heuristic with an actual computed angle — check this first, it changes several downstream decisions (dataset labeling, evaluation bucketing).

**Georeferencing.** Each product's 4 corner lat/lon pairs (UL/UR/BL/BR) are known from the catalog. Build a per-product affine (or higher-order, since these are pushbroom sensors — a simple 4-corner affine is a first approximation, not exact) transform from pixel coordinates to selenographic lat/lon. This is what generates the pseudo-ground-truth correspondences for evaluation (Section 5).

**Preprocessing.**
- Radiometric: per-instrument normalization (OHRC/TMC-2 are reflectance-like DN, IIRS is a spectral cube — needs band selection/PCA before treating as an "image").
- Geometric: reproject the overlapping region of both images into a shared local reference frame (e.g., simple cylindrical or local orthographic centered on the AOI) at a common working resolution, rather than trying to match raw-pixel OHRC directly against raw-pixel IIRS.
- Tiling: OHRC/TMC-2 full scenes are large (we saw 300MB–800MB PDS4 zips) — tile into overlapping patches (e.g. 512x512 at working resolution) for both matching and any learned-model inference, with a manifest mapping tile → source scene → geolocation.
- Multi-resolution pyramid per product to bridge the scale gap explicitly rather than relying on a detector's built-in scale invariance alone.

---

## 4. ML / CV pipeline — two tracks in parallel

Given hackathon time constraints, run both tracks concurrently rather than sequentially — Track A gives you a working demo fast; Track B is the differentiator in judging.

### Track A — Classical baseline (build first, ~1–2 days)
- Detectors: start with SIFT (scale-invariant by construction, well understood); add AKAZE as a second baseline (nonlinear scale space, often more robust to illumination than SIFT).
- Illumination handling: don't feed raw DN into the detector. Apply CLAHE or a Laplacian-pyramid/high-pass filter first — shape/edge information survives sun-angle changes far better than raw intensity. If time allows, implement or borrow HOPC (Histogram of Oriented Phase Congruency) or a phase-congruency-based descriptor — this family is the standard answer in the remote-sensing literature specifically for cross-modal, illumination-variant image matching (SAR-optical, multispectral-panchromatic), and is a strong, explainable thing to cite in your report.
- Matching: ratio-test + mutual nearest neighbor, then RANSAC (homography for near-planar patches, fundamental matrix if you want to be rigorous about relief) to reject outliers and get a final inlier set + transform.
- This alone is a legitimate, presentable baseline — don't skip it even if Track B works, because judges will want the comparison.

### Track B — Learned matcher (the differentiator, ~2–4 days)
- Don't train from scratch under hackathon time pressure. Use pretrained detector-free matchers via `kornia` (has LoFTR built in) or the original repos for LightGlue / RoMa — these generalize far better across illumination than SIFT out of the box, because they're trained on wide-baseline, varied-lighting datasets.
- Multimodal gap (OHRC vs IIRS): pretrained matchers assume single-band optical images. For IIRS, first collapse the hyperspectral cube to a representative single-band or 3-band composite (e.g., PCA top components, or a band near IIRS's peak SNR) before feeding it into the matcher. Document this as a known simplification, not a solved problem — full cross-modal (spectral vs panchromatic) matching is itself open research territory, and being honest about this in your presentation is safer than overclaiming.
- If time allows: fine-tune the matcher's confidence threshold / re-rank matches using the pseudo-ground-truth from Section 5 as a weak validation signal — not full retraining, just calibration.
- Stretch goal: a lightweight learned re-ranker or modality-adapter (a shallow CNN that maps IIRS-band-composite features into the same embedding space as OHRC/TMC-2 features) — only attempt this if Tracks A and B are both solid and demoable first.

### Scale bridging (applies to both tracks)
Do coarse-to-fine matching explicitly rather than hoping scale-invariant descriptors alone bridge a 20–320x GSD gap: match at the coarsest common pyramid level first to get an approximate transform, then refine within the corresponding high-res crop. This is standard practice for cross-resolution remote sensing and will noticeably improve both tracks' results.

---

## 5. Evaluation strategy

The core honesty problem: there's no hand-labeled correspondence ground truth. Solution — build **pseudo-ground-truth** from geolocation, and be explicit in your report about its limits:

1. Using each product's corner-geolocation transform (Section 3), project a grid of points from image A's pixel space into selenographic coordinates, then back into image B's pixel space. This gives approximate corresponding pixel pairs — accurate to roughly the footprint metadata's own precision (almost certainly several pixels to tens of pixels at OHRC resolution, better at TMC-2/IIRS resolution). State this error bound explicitly rather than presenting it as exact truth.
2. Metrics to report, split by your two dataset conditions (low sun-angle-gap vs high sun-angle-gap, and separately by GSD-ratio pair):
   - Match count and inlier ratio after RANSAC
   - Reprojection error against the pseudo-ground-truth grid (median + 90th percentile)
   - Success rate: fraction of tile-pairs achieving ≥N inliers with reprojection error under threshold
3. Present results as a table crossed by (instrument pair) × (sun-angle-gap bucket) × (method: classical vs learned) — this directly showcases the "sun-angle and scale invariant" framing from the problem statement and is exactly the kind of structured result judges can evaluate at a glance.
4. If time allows, hand-verify a small number (10–20) of matched pairs visually per condition as a sanity spot-check — cheap and catches pipeline bugs the automated metric would miss.

---

## 6. Backend (FastAPI)

Purpose: turn the pipeline into something the frontend (and judges) can drive interactively, not just notebook output.

- **Stack**: FastAPI (Python-native, matches the pipeline directly — no serialization layer needed between ML code and API).
- **Storage**: SQLite is enough for a hackathon (Postgres if the team is already comfortable with it) for the product catalog + job records; images stay on disk, referenced by path.
- **Key endpoints**:
  - `GET /products` — list ingested products with instrument/date/footprint metadata
  - `GET /pairs/suggest?product_id=` — suggest candidate overlapping pairs from the catalog (reuses the point-in-polygon overlap logic already built during data acquisition)
  - `POST /match` — submit a matching job `{product_a, product_b, method: classical|learned}` → job id
  - `GET /match/{job_id}` — job status + result once done: matched keypoints, transform, inlier count, reprojection-error stats
  - `GET /match/{job_id}/overlay` — a rendered side-by-side image with correspondence lines, for direct display
- **Jobs**: matching on full-res tiles isn't instant — run as a background task (FastAPI `BackgroundTasks` is enough for hackathon scale; reach for Celery/RQ only if queueing becomes a real bottleneck) so the API responds immediately with a job id and the frontend polls.

---

## 7. Frontend (demo/judging surface)

Purpose: this is what judges actually see — invest proportionally.

- **Stack**: React + a tile-friendly image viewer (OpenSeadragon handles large-image pan/zoom well; skip building this yourself).
- **Screens**:
  1. **Catalog browser** — map or list view of downloaded products, filterable by instrument/date, showing footprints (you already have this geometry from the acquisition work).
  2. **Pair picker** — pick two products (or accept a suggested overlapping pair), choose method (classical/learned/both side-by-side).
  3. **Results view** — the two images side by side with drawn correspondence lines, inlier/outlier coloring, and the metric numbers from Section 5 displayed alongside. This single screen is your demo centerpiece.
  4. **Metrics dashboard** — the crossed table from Section 5.4, so judges can see the sun-angle-invariance claim substantiated with numbers, not just anecdote.

---

## 8. Phased plan

| Phase | Goal | Depends on |
|---|---|---|
| 0 | PDS4 ingest + georeferencing + tiling working end-to-end on the 8 downloaded equatorial products | none — start immediately |
| 1 | Classical baseline (Track A) producing matches + metrics on the equatorial pairs | Phase 0 |
| 2 | Learned matcher (Track B) integrated, same evaluation harness | Phase 0 |
| 3 | Backend API wrapping both tracks | Phase 1 (at least) |
| 4 | Frontend hitting the backend, results view working | Phase 3 |
| 5 | Pull curated landing-zone subset, re-run both tracks on the harder south-polar case | Phases 1–2 stable |
| 6 | Polish, full metrics dashboard, presentation/report | everything above |

Phase 0 is the critical path — nothing else can start meaningfully until PDS4 parsing and geolocation-based pseudo-ground-truth are working, so it's worth front-loading effort there even before deciding final matcher choices.

---

## 9. Open questions to resolve early

- Does the PDS4 label (inside the zip, not the ISSDC catalog) actually carry usable sun-angle metadata? Check this in the first hour of Phase 0 — it changes how you label/bucket the dataset for evaluation.
- What accuracy can the 4-corner georeferencing actually deliver? Worth a quick manual check (pick a recognizable crater visible in both an OHRC and TMC-2 scene, eyeball the corner-transform-predicted location against the real one) before trusting it as pseudo-ground-truth.
- IIRS band selection strategy (PCA vs fixed band vs learned) — pick one early, don't let this become a rabbit hole; a fixed reasonable band/PCA composite is fine for v1.
