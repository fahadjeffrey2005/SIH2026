# Track A vs Track B — first real results

Ran both matching tracks on the two geometry-confirmed overlapping pairs
from the equatorial site, cropped to their true overlap via
`geo.overlap_crop` and normalized with CLAHE. Working resolution is the
coarser instrument's native GSD in each pair (see `NOMINAL_GSD_M` in
`match/classical/demo.py`).

- **Track A (classical)**: SIFT and AKAZE, ratio test + RANSAC homography.
- **Track B (learned)**: DISK + LightGlue via `kornia`, used zero-shot
  (pretrained on terrestrial photo datasets, no lunar-imagery fine-tuning),
  RANSAC homography on top for a fair comparison to Track A. LoFTR (the
  other candidate named in docs/architecture.md Sec. 5) isn't runnable here
  -- kornia's only pretrained LoFTR weights are hosted on
  cmp.felk.cvut.cz, which this environment's egress policy blocks. DISK's
  and LightGlue's weights are both GitHub release/raw assets, which are
  reachable.

| Pair (incidence gap) | Method | Keypoints | Raw/ratio-test matches | Inliers | Inlier % |
|---|---|---|---|---|---|
| IIRS 2021-12-21 + TMC-2 2024-01-25 (26.9°) | SIFT | 8000/4207 | 25 | 7 | 28% |
| | AKAZE | 1945/614 | 10 | 4 | 40% |
| | DISK+LightGlue | 2048/2048 | 23 | **0** | 0% |
| OHRC 2021-04-05 + TMC-2 2025-08-07 (34.7°) | SIFT | 100/57 | 0 | 0 | 0% |
| | AKAZE | 1/0 | 0 | 0 | 0% |
| | DISK+LightGlue | 449/994 | 1 | 0 | 0% |

Reproduce (runs all 3 methods on one pair and saves an overlay PNG per method):

```bash
cd pipeline
python -m match.compare ch2_iir_nri_20211221t0324126144_d_img_hw1 ch2_tmc_ncf_20240125t0622476078_d_img_d18 --out-dir /tmp/compare
python -m match.compare ch2_ohr_ncp_20210405t1606536730_d_img_d18 ch2_tmc_ncf_20250807t1904346039_d_img_d18 --out-dir /tmp/compare
```

## Reading

This is a small, low-resolution, browse-quality first pass (IIRS/TMC-2
crops here are still hundreds of km long at 80m/px; OHRC/TMC-2 crops are
only a few hundred pixels since OHRC's browse is a 20x finer GSD than
TMC-2's and the true overlap is small), so absolute inlier counts aren't
meaningful on their own. Two things are, though:

1. **The high-gap pair beats every method tried.** Classical and learned
   both produce zero inliers on OHRC vs TMC-2 2025-08-07 (34.7° incidence
   gap, cross-modality, ~20x GSD difference). Sanity-checked that this
   isn't a broken pipeline on either track: a rotated self-match (8°, same
   image) gets 434/435 SIFT inliers and 1229/1235 DISK+LightGlue inliers,
   so both tracks demonstrably work when there's real content to match --
   they just find nothing shared between these two crops at this
   resolution. That's the actual hard case this project is about.

2. **Zero-shot DISK+LightGlue does not obviously beat classical SIFT/AKAZE
   here -- if anything it's worse on the one pair that has a real signal**
   (0 inliers vs SIFT's 7 and AKAZE's 4 on the low-gap pair, despite
   finding plenty of keypoints and even more raw candidate matches than
   AKAZE). This is a genuine, slightly humbling result, not a bug -- same
   self-match sanity check confirms the DISK+LightGlue pipeline itself
   works. The likely explanation is domain gap: DISK and LightGlue were
   both trained on MegaDepth-style terrestrial outdoor photos, and neither
   has seen lunar panchromatic/hyperspectral imagery. This is a known
   failure mode in planetary remote sensing (see docs/architecture.md's
   framing of why this problem is hard) and a legitimate finding to report
   as-is: "off-the-shelf learned matchers don't transparently transfer to
   this domain" is itself evidence for why the actual project (an
   evaluation harness that measures this rather than assuming a learned
   method wins) is worth building.

## Known caveats in this pass

- OHRC/TMC-2 imagery here is the 1/10-downsampled browse PNG, not the
  native raster (native files are 300-800MB each and not yet staged into
  the pipeline environment -- see `match/classical/demo.py` docstring).
  Native resolution should only help both tracks, not explain away the
  zero-match result at browse scale, but it hasn't been tried yet.
- IIRS is represented by a single VNIR band (index 40), not a fused/PCA
  composite.
- `geo.overlap_crop`'s margin (15%), CLAHE's clip limit (2.5), and DISK's
  keypoint cap (2048) are untuned defaults, not swept.
- DISK+LightGlue tried both the "depth" and "epipolar" DISK checkpoints on
  the high-gap pair; "epipolar" found more keypoints (1035 vs 994 on one
  side) but LightGlue still matched none of them across images.
- No fine-tuning or domain adaptation attempted for Track B yet -- that's
  the natural next step suggested by finding #2 above, not just running the
  pretrained model harder.
