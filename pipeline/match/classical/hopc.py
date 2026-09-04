"""Track A, third method: HOPC (Histogram of Oriented Phase Congruency).

Why this exists (see docs/architecture.md Sec.1 and docs/baseline_results.md):
SIFT and AKAZE both key off *intensity gradients* -- where the image gets
brighter or darker. Under a large sun-angle change, the exact same crater
rim can flip from a bright ridge (sun in front) to a black shadow edge (sun
behind) -- same physical feature, opposite gradient sign -- which is the
actual physical reason both classical detectors degrade past this
project's own baseline finding of ~34deg incidence gap.

Phase congruency (Kovesi 1999/2003) locates structure differently: instead
of gradient magnitude, it measures where the *local phase* of the image's
frequency components lines up across scales. A real edge or ridge has
Fourier components that are all in phase at that location, regardless of
whether the edge happens to be lit brightly or sit in shadow -- congruent
phase is a property of "there is a real structural edge here", not of which
way the light was coming from. HOPC (Ye, Shan et al.) then builds a
SIFT-shaped descriptor (a spatial grid of orientation histograms) on top of
per-orientation phase-congruency energy instead of raw gradients, and is
the standard literature answer for cross-modal, illumination-variant image
matching (SAR-optical, day/night, multispectral-panchromatic) -- exactly
this project's problem shape.

This is a real, working implementation of the core idea, not a byte-exact
port of any reference implementation -- two deliberate simplifications
vs. the literature, both called out where they happen below:
  1. Noise compensation uses a single-scale Rayleigh estimate rather than
     Kovesi's full multi-scale noise model (phase_congruency_energy).
  2. No per-keypoint dominant-orientation alignment, so this descriptor is
     NOT rotation-invariant (unlike SIFT) -- fine for this project, where
     every product pair is already geolocated into a shared, unrotated
     working frame (match.classical.demo.prep_crop) before matching ever
     runs, but worth knowing if this module is reused somewhere that isn't
     true (see test_hopc.py's rotation-sensitivity test, which documents
     this limitation as a passing assertion rather than a surprise).
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

# Kovesi's classic defaults (his 1999/2003 phasecong2/3 code and most open
# re-implementations use these same numbers) -- 4 scales an octave apart
# starting at a 3px wavelength, 8 orientations spanning 0..180deg (edge
# orientation is mod-180, not mod-360). 8 orientations also gives a tidy
# 16 cells x 8 orientations = 128-dim descriptor, the same length as SIFT's.
NSCALE = 4
NORIENT = 8
MIN_WAVELENGTH = 3.0
MULT = 2.1
SIGMA_ON_F = 0.55  # log-Gabor bandwidth (~0.55 -> a bit over 1 octave)
NOISE_K = 2.0  # noise-energy cutoff, in estimated-noise standard deviations
THETA_SIGMA_FACTOR = 1.2  # angular filter width, relative to the spacing between orientations

PATCH_SIZE = 16  # descriptor support region, pixels (must be a multiple of 4)
CELL = PATCH_SIZE // 4
MAX_KEYPOINTS = 4000
MIN_KEYPOINT_DISTANCE = 6
QUALITY_LEVEL = 0.01

_EPS = 1e-6


def _frequency_grids(rows: int, cols: int) -> tuple[np.ndarray, np.ndarray]:
    """Radius (cycles/pixel, matching np.fft.fft2's un-shifted layout) and
    angle (radians) at every point of the (rows, cols) frequency grid."""
    u = np.fft.fftfreq(cols)
    v = np.fft.fftfreq(rows)
    uu, vv = np.meshgrid(u, v)
    radius = np.sqrt(uu ** 2 + vv ** 2)
    radius[0, 0] = 1.0  # placeholder to avoid log(0) below; filter is zeroed at DC separately
    angle = np.arctan2(vv, uu)
    return radius, angle


def _log_gabor_radial(radius: np.ndarray, wavelength: float, sigma_on_f: float) -> np.ndarray:
    f0 = 1.0 / wavelength
    lg = np.exp(-(np.log(radius / f0) ** 2) / (2.0 * np.log(sigma_on_f) ** 2))
    lg[0, 0] = 0.0  # kill DC -- phase congruency is a bandpass measure
    return lg


def _angular_filter(angle: np.ndarray, orientation_rad: float, theta_sigma: float) -> np.ndarray:
    """A *one-sided* Gaussian lobe centered on `orientation_rad` -- deliberately
    NOT folded to also pass `orientation_rad + pi`. Because the input image is
    real, its FFT is Hermitian-symmetric (F(-u,-v) = conj(F(u,v))); multiplying
    by a filter that is large at angle theta_o but ~0 at theta_o+pi breaks that
    symmetry, so the inverse FFT of the product is genuinely complex rather than
    real. That complex response's real/imaginary parts are exactly the
    even/odd (quadrature) filter pair phase congruency needs, gotten "for
    free" from one filter instead of building two -- the standard log-Gabor
    phase-congruency trick (Kovesi)."""
    ds = np.sin(angle) * np.cos(orientation_rad) - np.cos(angle) * np.sin(orientation_rad)
    dc = np.cos(angle) * np.cos(orientation_rad) + np.sin(angle) * np.sin(orientation_rad)
    dtheta = np.abs(np.arctan2(ds, dc))  # signed wrap handled by atan2; abs keeps the single lobe one-sided
    return np.exp(-(dtheta ** 2) / (2.0 * theta_sigma ** 2))


def phase_congruency_energy(
    gray: np.ndarray,
    nscale: int = NSCALE,
    norient: int = NORIENT,
    min_wavelength: float = MIN_WAVELENGTH,
    mult: float = MULT,
    sigma_on_f: float = SIGMA_ON_F,
    k: float = NOISE_K,
    theta_sigma_factor: float = THETA_SIGMA_FACTOR,
) -> np.ndarray:
    """Per-orientation phase congruency, normalized to roughly [0, 1].

    Returns an (norient, H, W) float32 array: PC[o] is high wherever the
    image has real, illumination-independent structure oriented at
    `o * pi / norient` radians.
    """
    rows, cols = gray.shape
    radius, angle = _frequency_grids(rows, cols)
    img_fft = np.fft.fft2(gray.astype(np.float64))

    theta_sigma = (np.pi / norient) * theta_sigma_factor
    pc = np.empty((norient, rows, cols), dtype=np.float32)

    for o in range(norient):
        orientation_rad = o * np.pi / norient
        angular = _angular_filter(angle, orientation_rad, theta_sigma)

        sum_re = np.zeros((rows, cols))
        sum_im = np.zeros((rows, cols))
        sum_amp = np.zeros((rows, cols))
        scale_re = []
        scale_im = []
        first_scale_amp = None

        for s in range(nscale):
            wavelength = min_wavelength * (mult ** s)
            radial = _log_gabor_radial(radius, wavelength, sigma_on_f)
            resp = np.fft.ifft2(img_fft * radial * angular)
            re, im = resp.real, resp.imag
            amp = np.sqrt(re ** 2 + im ** 2)
            if s == 0:
                first_scale_amp = amp
            scale_re.append(re)
            scale_im.append(im)
            sum_re += re
            sum_im += im
            sum_amp += amp

        mean_mag = np.sqrt(sum_re ** 2 + sum_im ** 2) + _EPS
        cos_bar = sum_re / mean_mag
        sin_bar = sum_im / mean_mag

        energy = np.zeros((rows, cols))
        for re, im in zip(scale_re, scale_im):
            energy += re * cos_bar + im * sin_bar - np.abs(re * sin_bar - im * cos_bar)

        # Noise compensation: simplified single-scale Rayleigh estimate from
        # the smallest (highest-frequency, noisiest) scale's amplitude --
        # Kovesi's original combines all scales' noise statistics
        # analytically; this median-based estimate is the well-known
        # practical stand-in most open re-implementations use when skipping
        # that full derivation.
        median_amp = np.median(first_scale_amp)
        rayleigh_sigma = median_amp / np.sqrt(np.log(4.0)) + _EPS
        noise_mean = rayleigh_sigma * np.sqrt(np.pi / 2.0)
        noise_std = rayleigh_sigma * np.sqrt((4.0 - np.pi) / 2.0)
        noise_threshold = noise_mean + k * noise_std

        energy = np.maximum(energy - noise_threshold, 0.0)
        pc[o] = np.clip(energy / sum_amp.clip(min=_EPS), 0.0, 1.0)

    return pc


@dataclass
class _IntegralOrientationMaps:
    """Integral images (one per orientation) of the phase-congruency maps,
    so a keypoint's per-cell, per-orientation energy sum is an O(1) lookup
    instead of re-summing a slice for every keypoint -- matters once there
    are thousands of keypoints, each needing 16 cells x norient sums."""

    integrals: np.ndarray  # (norient, H+1, W+1)

    @classmethod
    def build(cls, pc: np.ndarray) -> "_IntegralOrientationMaps":
        integrals = np.stack([cv2.integral(o) for o in pc], axis=0)
        return cls(integrals)

    def box_sum(self, o: int, x0: int, y0: int, x1: int, y1: int) -> float:
        ii = self.integrals[o]
        return float(ii[y1, x1] - ii[y0, x1] - ii[y1, x0] + ii[y0, x0])


def detect_and_compute(
    gray: np.ndarray,
    max_keypoints: int = MAX_KEYPOINTS,
    patch_size: int = PATCH_SIZE,
    min_distance: int = MIN_KEYPOINT_DISTANCE,
    quality_level: float = QUALITY_LEVEL,
) -> tuple[list[cv2.KeyPoint], "np.ndarray | None"]:
    """Same shape of return value as cv2's own `detector.detectAndCompute`
    (a list of cv2.KeyPoint plus an NxD float32 descriptor array, or
    (kp, None) when nothing usable was found) -- match.classical.matcher's
    ratio-test/RANSAC code doesn't need to know HOPC isn't a cv2 built-in.

    Keypoints are Shi-Tomasi corners of the combined (max-across-
    orientations) phase-congruency map, rather than anything HOPC-specific
    -- the descriptor is where phase congruency actually earns its keep
    (illumination-independent structure), and reusing a standard, fast
    corner detector for localization keeps this from also having to
    reinvent scale-space extrema detection."""
    if gray.ndim != 2:
        raise ValueError(f"expected a single-channel grayscale image, got shape {gray.shape}")
    rows, cols = gray.shape
    half = patch_size // 2
    if rows <= patch_size or cols <= patch_size:
        return [], None

    normalized = gray.astype(np.float64) / 255.0
    pc = phase_congruency_energy(normalized)
    combined = pc.max(axis=0).astype(np.float32)

    corners = cv2.goodFeaturesToTrack(
        combined, maxCorners=max_keypoints, qualityLevel=quality_level, minDistance=min_distance
    )
    if corners is None:
        return [], None
    pts = corners.reshape(-1, 2)
    keep = (pts[:, 0] >= half) & (pts[:, 0] < cols - half) & (pts[:, 1] >= half) & (pts[:, 1] < rows - half)
    pts = pts[keep]
    if len(pts) == 0:
        return [], None

    integral_maps = _IntegralOrientationMaps.build(pc)
    norient = pc.shape[0]
    cell = patch_size // 4
    descriptors = np.empty((len(pts), 16 * norient), dtype=np.float32)
    keypoints = []
    for i, (x, y) in enumerate(pts):
        xi, yi = int(round(x)), int(round(y))
        idx = 0
        for cy in range(4):
            y0, y1 = yi - half + cy * cell, yi - half + (cy + 1) * cell
            for cx in range(4):
                x0, x1 = xi - half + cx * cell, xi - half + (cx + 1) * cell
                for o in range(norient):
                    descriptors[i, idx] = integral_maps.box_sum(o, x0, y0, x1, y1)
                    idx += 1
        keypoints.append(cv2.KeyPoint(float(xi), float(yi), float(patch_size)))

    # L2-normalize, then clip-and-renormalize (SIFT's own trick, reused
    # here for the same reason: caps how much a single unusually strong
    # orientation bin can dominate the match distance, which otherwise
    # makes the descriptor overly sensitive to exactly how much real
    # structure happened to fall in one cell).
    norms = np.linalg.norm(descriptors, axis=1, keepdims=True) + _EPS
    descriptors /= norms
    np.clip(descriptors, 0.0, 0.2, out=descriptors)
    norms = np.linalg.norm(descriptors, axis=1, keepdims=True) + _EPS
    descriptors /= norms

    return keypoints, descriptors
