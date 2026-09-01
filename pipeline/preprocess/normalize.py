"""Illumination-normalization shared by both matching tracks.

A sun-angle gap between two products shows up mainly as different shadow
length/direction and different overall brightness/contrast -- not a simple
photometric offset -- so a single global histogram equalization just
re-globalizes those differences instead of removing them. CLAHE (localized,
contrast-limited equalization) is the standard remote-sensing answer: it
flattens *local* contrast without inventing structure that isn't there,
which is what both the classical detectors and any learned matcher actually
need to key on.
"""

from __future__ import annotations

import cv2
import numpy as np


def to_uint8(img: np.ndarray) -> np.ndarray:
    """Percentile-stretch anything that isn't already 8-bit (IIRS bands,
    16-bit OHRC/TMC-2 rasters) into uint8. 1st/99th percentile clipping
    avoids a few hot/dead pixels blowing out the whole stretch."""
    if img.dtype == np.uint8:
        return img
    img = img.astype(np.float32)
    lo, hi = np.percentile(img, [1.0, 99.0])
    if hi <= lo:
        hi = lo + 1.0
    img = np.clip((img - lo) / (hi - lo), 0.0, 1.0)
    return (img * 255).astype(np.uint8)


def clahe_normalize(img: np.ndarray, clip_limit: float = 2.5, tile_grid: int = 8) -> np.ndarray:
    img8 = to_uint8(img)
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(tile_grid, tile_grid))
    return clahe.apply(img8)
