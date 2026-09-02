"""Reference/reproduction script for native-resolution matching -- this
does NOT run as part of the normal pipeline/backend/frontend flow, and
deliberately has no import on the pipeline package (numpy + opencv only).

Why it exists and where it actually runs: OHRC/TMC-2's native rasters are
300MB-2.2GB *uncompressed* each (see the byte math in this file's crop
constants -- e.g. OHRC's is 93693 x 12000 x 1 byte = 1,124,316,000 bytes
exactly, matching its PDS4 label's Axis_Array element counts and the zip's
own uncompressed size), which is both too big to keep staged in the ML
pipeline environment and unnecessary to move there in full: only a small
crop around each pair's true geometric overlap is ever needed for matching.
This script is meant to run wherever the raw PDS4 zips actually live (the
project's external drive, via a local Python -- it only needs numpy +
opencv, both of which are commonly available without the rest of the
pipeline's dependency stack): it memmaps the already-unzipped .img file
(no need to load the whole file into RAM), slices out just the needed
row/col window, downsamples if that side needs to match the pair's working
GSD, and writes a small PNG -- typically a few MB, versus a multi-hundred-
MB to multi-GB source raster. That PNG is what actually gets moved (staged)
into the pipeline environment for match.classical.matcher / match.learned.
matcher / match.evaluate to run on, exactly like the pre-baked browse PNGs
match.classical.demo.py already uses, just at a much less lossy resolution.

The crop window and downsample factor for the one pair this script
currently encodes (OHRC 2021-04-05 vs TMC-2 2025-08-07 -- the 34.7 deg
sun-incidence-gap pair that found zero matches at 1/10-browse resolution,
see docs/baseline_results.md's "Native-resolution follow-up" section) were
derived once, offline, from each product's own PDS4 corner geolocation via
geo.overlap_crop -- see pipeline/match/native_demo.py's docstring for that
derivation and for how to reproduce/rerun the actual matching once this
script's output PNGs exist. Extending this to another pair means computing
a new crop window the same way and adding another block below; this is a
one-off reproduction aid, not a generalized tool, given how much native
rasters vary in size across this catalog (OHRC's 2021-04-05 frame happens
to be small enough that its whole footprint is the "crop"; a longer OHRC
strip would need real crop bounds instead of near-full-frame ones).

Usage (on the machine holding the unzipped PDS4 data, e.g. via the
project's external drive):
    python3 extract_native_crop.py <base_dir>
where <base_dir> contains ohrc_20210405/data/calibrated/20210405/*.img and
tmc2_20250807/data/calibrated/20250807/*.img (i.e. the two products' zips,
unzipped in place -- unzip -o <zip> <img-path> <xml-path> -d <base_dir>/<name>).
Writes <base_dir>/ohrc_native5m_crop.png and <base_dir>/tmc2_native5m_crop.png.
"""
import numpy as np
import cv2
import sys


def to_uint8(img):
    if img.dtype == np.uint8:
        return img
    img = img.astype(np.float32)
    lo, hi = np.percentile(img, [1.0, 99.0])
    if hi <= lo:
        hi = lo + 1.0
    img = np.clip((img - lo) / (hi - lo), 0.0, 1.0)
    return (img * 255).astype(np.uint8)

def main():
    base = sys.argv[1]

    # --- OHRC: 93693 x 12000, uint8, crop (0:93692, 0:11999), downsample 20x (0.25m -> 5m GSD) ---
    ohrc_path = f"{base}/ohrc_20210405/data/calibrated/20210405/ch2_ohr_ncp_20210405T1606536730_d_img_d18.img"
    ohrc = np.memmap(ohrc_path, dtype=np.uint8, mode="r", shape=(93693, 12000))
    ohrc_crop = np.array(ohrc[0:93692, 0:11999])  # copy out of memmap
    scale = 0.25 / 5.0
    new_w = max(8, int(round(ohrc_crop.shape[1] * scale)))
    new_h = max(8, int(round(ohrc_crop.shape[0] * scale)))
    ohrc_small = cv2.resize(ohrc_crop, (new_w, new_h), interpolation=cv2.INTER_AREA)
    cv2.imwrite(f"{base}/ohrc_native5m_crop.png", ohrc_small)
    print("OHRC crop:", ohrc_crop.shape, "-> downsampled:", ohrc_small.shape, "scale=", scale)

    # --- TMC-2: 295234 x 4000, uint16 LE, crop (279899:286631, 2451:3322), native 5m, no resize ---
    tmc2_path = f"{base}/tmc2_20250807/data/calibrated/20250807/ch2_tmc_ncf_20250807T1904346039_d_img_d18.img"
    tmc2 = np.memmap(tmc2_path, dtype="<u2", mode="r", shape=(295234, 4000))
    tmc2_crop = np.array(tmc2[279899:286631, 2451:3322])
    tmc2_u8 = to_uint8(tmc2_crop)
    cv2.imwrite(f"{base}/tmc2_native5m_crop.png", tmc2_u8)
    print("TMC-2 crop:", tmc2_crop.shape, "dtype", tmc2_crop.dtype, "-> uint8", tmc2_u8.shape)

if __name__ == "__main__":
    main()
