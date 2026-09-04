"""FALLBACK generator for a procedural, stylized lunar diffuse texture.

`frontend/src/assets/moon_diffuse.jpg` is now NASA's own real LROC global
color mosaic (lroc_color_2k.jpg, NASA's Scientific Visualization Studio CGI
Moon Kit, svs.gsfc.nasa.gov/4720 -- public domain US government work), not
this generator's output -- see docs/baseline_results.md's "3D Moon" section.
This script is kept only as a network-free fallback: if that real asset is
ever missing (a fresh clone that hasn't fetched it, or working somewhere
with no way to obtain it), running this regenerates *something* plausible
to wrap the sphere in, entirely locally -- no network access, no license to
track, fully reproducible (fixed RNG seed). It was the default before the
real NASA texture was sourced.

Not photoreal, not claimed to be real satellite imagery anywhere in the UI
if it's ever back in use -- it's a backdrop the real, data-driven footprint
patches are drawn on top of.

Usage: python3 gen_moon_texture.py [out_path] [width]
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "frontend/src/assets/moon_diffuse.jpg"
W = int(sys.argv[2]) if len(sys.argv) > 2 else 2048
H = W // 2
rng = np.random.default_rng(1737400)  # seeded on the lunar radius constant used elsewhere in this project


def wrapped_paste_add(canvas: np.ndarray, sprite: np.ndarray, cx: int, cy: int):
    """Additively blends `sprite` (square, signed float) into `canvas` centered
    at (cx, cy), wrapping horizontally (the map is a full 360 deg equirect)
    and clipping at the poles (no wrap needed vertically for a backdrop)."""
    h, w = sprite.shape
    x0, y0 = cx - w // 2, cy - h // 2
    ys = np.arange(y0, y0 + h)
    xs = np.arange(x0, x0 + w)
    valid_y = (ys >= 0) & (ys < canvas.shape[0])
    if not valid_y.any():
        return
    xs_wrapped = xs % canvas.shape[1]
    canvas[np.ix_(ys[valid_y], xs_wrapped)] += sprite[valid_y]


def crater_sprite(radius: int) -> np.ndarray:
    """Radial profile: bright raised rim, darker floor, soft falloff outside --
    the classic lunar-crater look, as a small signed-brightness patch."""
    size = radius * 2 + 1
    yy, xx = np.mgrid[0:size, 0:size] - radius
    r = np.sqrt(xx ** 2 + yy ** 2) / max(radius, 1)
    floor = -0.35 * np.clip(1 - r / 0.75, 0, 1) ** 1.5
    rim = 0.45 * np.exp(-((r - 0.85) ** 2) / (2 * 0.09 ** 2))
    fade = np.clip(1 - r, 0, 1) ** 0.5
    return (floor + rim) * fade


# 1. Low-frequency albedo variation (maria vs highlands) via blurred noise.
base = rng.normal(0, 1, (H, W)).astype(np.float32)
base_img = Image.fromarray(((base - base.min()) / (np.ptp(base)) * 255).astype(np.uint8))
base_img = base_img.filter(ImageFilter.GaussianBlur(radius=W / 40))
low = np.asarray(base_img, dtype=np.float32) / 255.0
low = 0.62 + (low - low.mean()) * 0.5  # dimmer "maria" patches, brighter "highlands"

# 2. Fine grain (regolith texture) via lightly blurred higher-frequency noise.
grain = rng.normal(0, 1, (H, W)).astype(np.float32)
grain_img = Image.fromarray(((grain - grain.min()) / np.ptp(grain) * 255).astype(np.uint8))
grain_img = grain_img.filter(ImageFilter.GaussianBlur(radius=1.2))
grain = (np.asarray(grain_img, dtype=np.float32) / 255.0 - 0.5) * 0.05

canvas = low + grain

# 3. Craters at a range of sizes, denser at small sizes (matches real crater
# size-frequency distributions in spirit, not to scientific accuracy).
for radius, count in [(2, 6000), (4, 2500), (8, 900), (16, 260), (32, 70), (64, 18), (110, 6)]:
    sprite = crater_sprite(radius)
    cys = rng.integers(0, H, count)
    # Fewer craters land near the poles in equirect area terms; a plain
    # uniform y draw already under-samples poles visually enough for a
    # stylized backdrop, so no extra cos(lat) weighting needed here.
    cxs = rng.integers(0, W, count)
    for cy, cx in zip(cys, cxs):
        wrapped_paste_add(canvas, sprite, int(cx), int(cy))

canvas = np.clip(canvas, 0, 1)
out_img = Image.fromarray((canvas * 255).astype(np.uint8), mode="L").convert("RGB")
OUT.parent.mkdir(parents=True, exist_ok=True)
out_img.save(OUT, quality=90)
print(f"wrote {OUT} ({W}x{H})")
