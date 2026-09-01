# Classical matching baseline (Track A) — first real results

Ran `pipeline/match/classical/demo.py` (SIFT and AKAZE, ratio test + RANSAC
homography) on the two geometry-confirmed overlapping pairs from the
equatorial site, cropped to their true overlap via `geo.overlap_crop` and
normalized with CLAHE. Working resolution is the coarser instrument's native
GSD in each pair (see `NOMINAL_GSD_M` in demo.py).

| Pair | Solar incidence gap | SIFT inliers | AKAZE inliers |
|---|---|---|---|
| IIRS 2021-12-21 + TMC-2 2024-01-25 | 26.9° (7.3° vs 34.1°) | 7 / 25 (28%) | 4 / 10 (40%) |
| OHRC 2021-04-05 + TMC-2 2025-08-07 | 34.7° (75.9° vs 41.2°) | 0 / 0 | 0 keypoints matched at all |

Reproduce:

```bash
cd pipeline
python -m match.classical.demo ch2_iir_nri_20211221t0324126144_d_img_hw1 ch2_tmc_ncf_20240125t0622476078_d_img_d18 --out /tmp/a.png
python -m match.classical.demo ch2_ohr_ncp_20210405t1606536730_d_img_d18 ch2_tmc_ncf_20250807t1904346039_d_img_d18 --out /tmp/b.png
```

## Reading

This is a small, low-resolution, browse-quality first pass (IIRS/TMC-2
crops here are still hundreds of km long at 80m/px; OHRC/TMC-2 crops are
only a few hundred pixels since OHRC's browse is a 20x finer GSD than
TMC-2's and the true overlap is small), so absolute inlier counts aren't
meaningful on their own. What *is* meaningful, and lines up with this
project's actual premise: the low-incidence-gap pair produces real,
visually-plausible correspondences (see `docs/baseline_results.md`'s
sibling image dump); the high-gap, cross-modality pair (OHRC panchromatic
vs TMC-2 panchromatic, 34.7° incidence gap, ~20x GSD difference) produces
*none* — SIFT finds keypoints on both sides but not one survives the ratio
test, and AKAZE barely finds keypoints at all on a crop this small.

That's the actual failure mode Track B (LoFTR/LightGlue, learned features)
needs to fix, and now there's a concrete, reproducible classical baseline
number to beat instead of an assumption. Next step per docs/architecture.md
Sec. 5: stage OHRC/TMC-2 at native (not browse) resolution for a fairer
comparison, then run the same pair through a pretrained LoFTR/LightGlue via
`kornia`.

## Known caveats in this first pass

- OHRC/TMC-2 imagery here is the 1/10-downsampled browse PNG, not the native
  raster (native files are 300-800MB each and not yet staged into the
  pipeline environment -- see `pipeline/match/classical/demo.py` docstring).
  Native resolution should only help the high-gap pair, not explain away its
  zero-match result at browse scale, but it hasn't been tried yet.
- IIRS is represented by a single VNIR band (index 40), not a fused/PCA
  composite -- an easy next tweak if band choice turns out to matter.
- `geo.overlap_crop`'s margin (15%) and CLAHE's clip limit (2.5) are
  untuned defaults, not swept.
