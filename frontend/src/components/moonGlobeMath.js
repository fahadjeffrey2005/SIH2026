// Pure, unit-testable geometry/color helpers for Feature 2 (the 3D Moon
// globe, frontend/src/components/MoonGlobe.jsx). Kept separate from the
// three.js rendering code so this logic can be tested without a WebGL
// context (jsdom has none) -- MoonGlobe.jsx imports these rather than
// duplicating the math inline.

/** Standard lat/lon -> unit-sphere-surface Cartesian conversion (the same
 * convention used by common three.js globe visualizations). This isn't just
 * self-consistent across footprint corners -- it's also, by construction,
 * the exact inverse of three.js's default `SphereGeometry` UV unwrap (u =
 * (lon+180)/360, v = (90+lat)/180, matching that geometry's own vertex
 * formula with phi_azimuth=(lon+180) and theta_polar=(90-lat)). That match
 * matters now that MoonGlobe.jsx's base sphere is a real NASA LROC
 * equirectangular map (moon_diffuse.jpg) rather than a stylized backdrop --
 * a standard planetary equirectangular map already puts north at the image
 * top and lon=-180 at the left edge, so this formula places a footprint on
 * its actual real terrain with no extra rotation/offset needed. (Before
 * that swap, when the texture was scripts/gen_moon_texture.py's procedural
 * placeholder, this alignment was true but incidental -- the placeholder
 * didn't depict any real longitude, so it wouldn't have shown a
 * misalignment either way.) */
export function latLonToVector3(latDeg, lonDeg, radius = 1) {
  const phi = ((90 - latDeg) * Math.PI) / 180;
  const theta = ((lonDeg + 180) * Math.PI) / 180;
  return [
    -radius * Math.sin(phi) * Math.cos(theta),
    radius * Math.cos(phi),
    radius * Math.sin(phi) * Math.sin(theta),
  ];
}

// dataviz skill's validated default sequential ramp (single hue, blue,
// light->dark; references/palette.md's "Sequential hue" table) -- reused
// as-is per the skill's own guidance, not re-derived. Low solar-incidence
// (sun near-overhead, "easy" lighting) reads as the lightest step; high
// incidence (grazing light, the hard-to-match cases this project's whole
// baseline is about) reads as the darkest.
const SEQUENTIAL_BLUE_STEPS = [
  "#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef",
  "#6da7ec", "#5598e7", "#3987e5", "#2a78d6",
  "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b",
];

function hexToRgb(hex) {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function rgbToHex([r, g, b]) {
  const c = (v) => Math.round(v).toString(16).padStart(2, "0");
  return `#${c(r)}${c(g)}${c(b)}`;
}

/** Maps a solar-incidence angle (degrees, physically bounded 0-90) onto the
 * sequential blue ramp. Domain is the full physical 0-90 range rather than
 * this catalog's actual min/max, so the encoding stays meaningful if/when
 * products outside today's ~7-76 deg range are added. */
export function incidenceColor(deg) {
  if (deg == null || Number.isNaN(deg)) return "#7a7a76"; // neutral gray for "unknown"
  const t = Math.min(1, Math.max(0, deg / 90));
  const steps = SEQUENTIAL_BLUE_STEPS;
  const pos = t * (steps.length - 1);
  const i0 = Math.floor(pos);
  const i1 = Math.min(steps.length - 1, i0 + 1);
  const frac = pos - i0;
  const a = hexToRgb(steps[i0]);
  const b = hexToRgb(steps[i1]);
  const mixed = a.map((av, i) => av + (b[i] - av) * frac);
  return rgbToHex(mixed);
}

/** True when a product's `corners` dict (as served by GET /products, e.g.
 * {ul: [lat, lon], ur: [...], ll: [...], lr: [...]}) has all four corners
 * needed to draw a footprint patch. Some products only have partial corner
 * data (see corner_source in the catalog). */
export function hasFullFootprint(corners) {
  return !!(corners && corners.ul && corners.ur && corners.ll && corners.lr);
}

const EXAGGERATE_MIN_SPAN_DEG = 6; // smallest on-screen angular size EACH side (along-track and cross-track) is stretched up to
const EXAGGERATE_MAX_MULTIPLIER = 35; // caps the stretch for near-degenerate (~0 width) footprints

/** Real lunar footprints are tiny next to the whole Moon -- OHRC's is under
 * 1 degree across, versus 360 for the full sphere -- so plotted at true
 * angular scale, most patches are sub-pixel. Most of these footprints are
 * also long, thin swaths (e.g. OHRC is ~0.84 deg along-track but only
 * ~0.10 deg cross-track; a TMC-2 strip can run 35-48 deg long but only
 * ~0.6-1 deg wide), so a single uniform stretch can't fix both problems at
 * once: scale by the long side and the short side stays sub-pixel; scale by
 * the short side (or the diagonal, which is dominated by the long side) and
 * an already-plenty-visible long side balloons absurdly.
 *
 * `exaggerateCorners` instead stretches the two sides of the footprint
 * INDEPENDENTLY: whichever side is under `targetMinSpanDeg` gets scaled up
 * to it (capped at `maxMultiplier` for a near-zero-width side), and a side
 * already at or above the target is left alone (multiplier floors at 1,
 * never shrinks). In practice that means a long thin swath gets *wider*
 * (its cross-track side grows to the visibility floor) while keeping its
 * *original* along-track length -- it reads as a clearly-visible ribbon
 * along its true ground track, not a sliver and not a wildly oversized
 * blob. Position (centroid) and orientation are preserved exactly; only
 * the two side lengths change, independently.
 *
 * Corners are treated as a parallelogram (center +/- half of each side
 * vector) when reconstructing, which is a very close approximation for
 * these near-rectangular satellite footprints even when not stretched
 * (real footprints are subtly trapezoidal, not perfect parallelograms) --
 * an accepted, tiny shape approximation in exchange for a simple,
 * dependable stretch. This is a display convention (like drawing planets
 * oversized on an orrery), not a claim about true size -- callers should
 * caption it as such.
 *
 * Note: assumes a footprint's own corners don't straddle the +-180 deg
 * antimeridian (true for every product in this catalog); a footprint that
 * did would need longitude unwrapping before averaging. */
export function exaggerateCorners(corners, targetSpanDeg = EXAGGERATE_MIN_SPAN_DEG, maxMultiplier = EXAGGERATE_MAX_MULTIPLIER) {
  const { ul, ur, ll, lr } = corners;
  const mid = (a, b) => [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
  const midTop = mid(ul, ur);
  const midBottom = mid(ll, lr);
  const midLeft = mid(ul, ll);
  const midRight = mid(ur, lr);
  const center = [(ul[0] + ur[0] + ll[0] + lr[0]) / 4, (ul[1] + ur[1] + ll[1] + lr[1]) / 4];

  // Full side vectors: u runs left->right (the "width"), v runs top->bottom
  // (the "height") -- whichever is physically along-track vs. cross-track
  // depends on the product, and it doesn't matter here since both are
  // handled the same way.
  const uVec = [midRight[0] - midLeft[0], midRight[1] - midLeft[1]];
  const vVec = [midBottom[0] - midTop[0], midBottom[1] - midTop[1]];
  const uLen = Math.hypot(...uVec);
  const vLen = Math.hypot(...vVec);

  const axisMultiplier = (len) => (len > 0 ? Math.min(maxMultiplier, Math.max(1, targetSpanDeg / len)) : maxMultiplier);
  const uMul = axisMultiplier(uLen);
  const vMul = axisMultiplier(vLen);
  if (uMul === 1 && vMul === 1) return corners; // both sides already big enough -- untouched, no float roundoff

  const halfU = [(uVec[0] * uMul) / 2, (uVec[1] * uMul) / 2];
  const halfV = [(vVec[0] * vMul) / 2, (vVec[1] * vMul) / 2];
  return {
    ul: [center[0] - halfU[0] - halfV[0], center[1] - halfU[1] - halfV[1]],
    ur: [center[0] + halfU[0] - halfV[0], center[1] + halfU[1] - halfV[1]],
    ll: [center[0] - halfU[0] + halfV[0], center[1] - halfU[1] + halfV[1]],
    lr: [center[0] + halfU[0] + halfV[0], center[1] + halfU[1] + halfV[1]],
  };
}

/** Builds the two-triangle vertex list (a flat Float32Array-ready number
 * array, 3 floats per vertex, 6 vertices) for one footprint quad, each
 * corner projected onto a sphere of the given radius. Winding order
 * (ul, ur, lr) + (ul, lr, ll) gives outward-facing normals for the
 * standard lat/lon convention above. */
export function footprintQuadVertices(corners, radius) {
  const ul = latLonToVector3(corners.ul[0], corners.ul[1], radius);
  const ur = latLonToVector3(corners.ur[0], corners.ur[1], radius);
  const ll = latLonToVector3(corners.ll[0], corners.ll[1], radius);
  const lr = latLonToVector3(corners.lr[0], corners.lr[1], radius);
  return [...ul, ...ur, ...lr, ...ul, ...lr, ...ll];
}

const MAX_PATCH_SEGMENT_DEG = 5; // finer grid steps than this stop being visibly different against sphere curvature
const MAX_PATCH_SEGMENTS_PER_AXIS = 16; // bounds triangle count for very long swaths

// Shared by footprintPatchVertices and footprintPatchGeometry below -- both
// need the exact same NxM grid, one just also wants each grid point's UV
// coordinate (for draping a product's own real image on top, see
// footprintPatchGeometry's docstring) alongside its 3D position.
function footprintPatchGrid(corners, radius) {
  const { ul, ur, ll, lr } = corners;
  const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
  const uSpan = (dist(ul, ur) + dist(ll, lr)) / 2;
  const vSpan = (dist(ul, ll) + dist(ur, lr)) / 2;
  const segmentsFor = (span) => Math.min(MAX_PATCH_SEGMENTS_PER_AXIS, Math.max(1, Math.ceil(span / MAX_PATCH_SEGMENT_DEG)));
  const segU = segmentsFor(uSpan);
  const segV = segmentsFor(vSpan);

  const lerp = (a, b, t) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
  // s: 0 at the ul/ll edge -> 1 at the ur/lr edge (matches image column 0 -> last column).
  // t: 0 at the ul/ur edge (top) -> 1 at the ll/lr edge (matches image row 0 -> last row) --
  // this mirrors the same row/column-to-corner convention pipeline/geo's
  // BilinearGeoTransform already uses to project real pixels to lat/lon, so
  // a UV built from (s, t) lines up with that same source image.
  const gridPoint = (i, j) => {
    const s = i / segU;
    const t = j / segV;
    const top = lerp(ul, ur, s);
    const bottom = lerp(ll, lr, s);
    const latLon = lerp(top, bottom, t);
    return { pos: latLonToVector3(latLon[0], latLon[1], radius), s, t };
  };

  const cells = [];
  for (let j = 0; j < segV; j++) {
    for (let i = 0; i < segU; i++) {
      cells.push([gridPoint(i, j), gridPoint(i + 1, j), gridPoint(i + 1, j + 1), gridPoint(i, j), gridPoint(i + 1, j + 1), gridPoint(i, j + 1)]);
    }
  }
  return cells;
}

/** Builds the two-triangle-per-cell vertex list (a flat Float32Array-ready
 * number array, 3 floats per vertex) for one footprint quad, each corner
 * projected onto a sphere of the given radius. Real footprints are tiny
 * next to the whole Moon -- OHRC's is under 1 degree across, versus 360 for
 * the full sphere -- so plotted at true angular scale, most patches are
 * sub-pixel. Segment counts scale with the footprint's angular span so
 * small footprints stay cheap (a footprint under `MAX_PATCH_SEGMENT_DEG` on
 * both axes is still just one quad, two triangles, identical output to
 * `footprintQuadVertices`) while long swaths get enough segments to hug the
 * curve -- see `footprintPatchGeometry`'s docstring for why that curve
 * matters. */
export function footprintPatchVertices(corners, radius) {
  const verts = [];
  for (const cell of footprintPatchGrid(corners, radius)) {
    for (const { pos } of cell) verts.push(...pos);
  }
  return verts;
}

/** Same NxM curved grid as `footprintPatchVertices`, but also returns a
 * matching flat UV array (2 floats per vertex, u/v both in 0..1) so a
 * product's own real browse image (GET /products/{id}/browse) can be
 * draped onto its footprint patch instead of a flat color fill. u runs
 * along the ul/ll -> ur/lr edge (image column 0 -> last column); v is
 * flipped (1 - row fraction) to match three.js's default `flipY` texture
 * convention, so v=1 lands on the ul/ur (image row 0, "top") edge the way
 * an unflipped image would read.
 *
 * A flat two-triangle quad doesn't follow the sphere's curvature over a
 * long swath's span (a 35-48 deg TMC-2 strip after exaggerateCorners), so
 * most of it sits inside or floating outside the true curved Moon mesh, and
 * depth-testing against that real surface then only lets slivers near the
 * corners show through -- a solid ribbon breaks into a dashed line. This
 * (and footprintPatchVertices) fix that by subdividing into a grid, each
 * point independently projected onto the sphere, so the mesh -- and
 * whatever image is draped on it -- hugs the curve as one continuous
 * surface. */
export function footprintPatchGeometry(corners, radius) {
  const positions = [];
  const uvs = [];
  for (const cell of footprintPatchGrid(corners, radius)) {
    for (const { pos, s, t } of cell) {
      positions.push(...pos);
      uvs.push(s, 1 - t);
    }
  }
  return { positions, uvs };
}
