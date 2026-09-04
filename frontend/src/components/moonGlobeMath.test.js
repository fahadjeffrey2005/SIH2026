import { describe, expect, it } from "vitest";

import {
  exaggerateCorners,
  footprintPatchGeometry,
  footprintPatchVertices,
  footprintQuadVertices,
  hasFullFootprint,
  incidenceColor,
  latLonToVector3,
} from "./moonGlobeMath";

function magnitude([x, y, z]) {
  return Math.sqrt(x * x + y * y + z * z);
}

describe("latLonToVector3", () => {
  it("places every point at exactly `radius` from the sphere's center", () => {
    const cases = [
      [0, 0], [45, 90], [-30, -120], [90, 0], [-90, 45], [12.3, -178.9],
    ];
    for (const [lat, lon] of cases) {
      expect(magnitude(latLonToVector3(lat, lon, 2.5))).toBeCloseTo(2.5, 6);
    }
  });

  it("puts the north and south poles on the +Y / -Y axis regardless of longitude", () => {
    const north = latLonToVector3(90, 137, 1);
    const south = latLonToVector3(-90, -42, 1);
    expect(north[0]).toBeCloseTo(0, 6);
    expect(north[1]).toBeCloseTo(1, 6);
    expect(north[2]).toBeCloseTo(0, 6);
    expect(south[1]).toBeCloseTo(-1, 6);
  });

  it("defaults to a unit sphere when no radius is given", () => {
    expect(magnitude(latLonToVector3(10, 20))).toBeCloseTo(1, 6);
  });
});

describe("incidenceColor", () => {
  it("returns the exact lightest ramp step at 0 degrees and darkest at 90", () => {
    expect(incidenceColor(0)).toBe("#cde2fb");
    expect(incidenceColor(90)).toBe("#0d366b");
  });

  it("clamps out-of-range angles to the same endpoints rather than extrapolating", () => {
    expect(incidenceColor(-5)).toBe(incidenceColor(0));
    expect(incidenceColor(200)).toBe(incidenceColor(90));
  });

  it("gets monotonically darker (lower red channel) as incidence increases", () => {
    const redChannel = (hex) => parseInt(hex.slice(1, 3), 16);
    const angles = [0, 15, 30, 45, 60, 75, 90];
    const reds = angles.map((a) => redChannel(incidenceColor(a)));
    for (let i = 1; i < reds.length; i++) {
      expect(reds[i]).toBeLessThanOrEqual(reds[i - 1]);
    }
    expect(reds[reds.length - 1]).toBeLessThan(reds[0]);
  });

  it("falls back to a neutral gray for missing/invalid data rather than a misleading color", () => {
    expect(incidenceColor(null)).toBe("#7a7a76");
    expect(incidenceColor(undefined)).toBe("#7a7a76");
    expect(incidenceColor(NaN)).toBe("#7a7a76");
  });
});

describe("hasFullFootprint", () => {
  it("is true only when all four corners are present", () => {
    expect(hasFullFootprint({ ul: [1, 2], ur: [1, 2], ll: [1, 2], lr: [1, 2] })).toBe(true);
  });

  it.each([
    [undefined],
    [null],
    [{}],
    [{ ul: [1, 2], ur: [1, 2], ll: [1, 2] }], // missing lr
  ])("is false for incomplete corners: %j", (corners) => {
    expect(hasFullFootprint(corners)).toBe(false);
  });
});

describe("exaggerateCorners", () => {
  const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
  const mid = (a, b) => [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
  // u = left->right side length, v = top->bottom side length (see source
  // docstring -- which one is "along-track" vs "cross-track" varies by
  // product and doesn't matter for these shape checks).
  const sides = (corners) => ({
    u: dist(mid(corners.ul, corners.ll), mid(corners.ur, corners.lr)),
    v: dist(mid(corners.ul, corners.ur), mid(corners.ll, corners.lr)),
  });
  const centroid = (corners) => {
    const keys = ["ul", "ur", "ll", "lr"];
    return [
      keys.reduce((s, k) => s + corners[k][0], 0) / 4,
      keys.reduce((s, k) => s + corners[k][1], 0) / 4,
    ];
  };

  it("widens a tiny real-world footprint (like OHRC's, under 1 degree across) on BOTH sides to clear the visibility floor", () => {
    // Real OHRC 2021-04-05 corners from the catalog -- a long, thin swath
    // (~0.84 deg along-track, ~0.10 deg cross-track).
    const ohrc = { ul: [-2.576048, -23.513766], ur: [-2.579083, -23.410545], ll: [-3.413866, -23.515354], lr: [-3.416904, -23.412227] };
    const before = sides(ohrc);
    expect(Math.min(before.u, before.v)).toBeLessThan(0.2);
    expect(Math.max(before.u, before.v)).toBeLessThan(1);

    const after = exaggerateCorners(ohrc);
    const afterSides = sides(after);
    // The wider side clears the 6 deg floor outright; the very narrow side
    // (~0.10 deg) hits EXAGGERATE_MAX_MULTIPLIER (35) before reaching 6 deg,
    // but that's still a >10x improvement -- a visible strip, not a sliver.
    expect(Math.max(afterSides.u, afterSides.v)).toBeCloseTo(6, 0);
    const narrowAfter = Math.min(afterSides.u, afterSides.v);
    const narrowBefore = Math.min(before.u, before.v);
    expect(narrowAfter).toBeCloseTo(narrowBefore * 35, 1);
    expect(narrowAfter).toBeGreaterThan(narrowBefore * 10);
  });

  it("widens a long IIRS-style swath's narrow cross-track side while leaving its already-visible along-track length alone", () => {
    // Same shape as a real ~15 deg-long, ~0.6 deg-wide IIRS swath.
    const iirs = { ul: [-15.529913, -23.454591], ur: [-15.527481, -22.843433], ll: [-0.239028, -23.515014], lr: [-0.236739, -22.945892] };
    const before = sides(iirs);
    const longBefore = Math.max(before.u, before.v);
    const shortBefore = Math.min(before.u, before.v);
    expect(shortBefore).toBeLessThan(1);
    expect(longBefore).toBeGreaterThan(15);

    const after = exaggerateCorners(iirs);
    const afterSides = sides(after);
    const longAfter = Math.max(afterSides.u, afterSides.v);
    const shortAfter = Math.min(afterSides.u, afterSides.v);
    expect(shortAfter).toBeCloseTo(6, 0); // narrow side pulled up to the floor
    expect(longAfter).toBeCloseTo(longBefore, 1); // long side left as-is, not further stretched
  });

  it("widens a TMC-2-style 35+ degree-long strip's narrow side without the long side capping the fix", () => {
    // A footprint this long used to prevent the narrow-side fix entirely
    // under a diagonal- or major-axis-capped approach; independent per-axis
    // scaling doesn't have that failure mode.
    const tmc = { ul: [-5, -20.5], ur: [-5, 14.2], ll: [-5.6, -20.5], lr: [-5.6, 14.2] };
    const after = exaggerateCorners(tmc);
    const afterSides = sides(after);
    expect(Math.min(afterSides.u, afterSides.v)).toBeGreaterThan(5.9);
    expect(Math.max(afterSides.u, afterSides.v)).toBeCloseTo(34.7, 0); // long side untouched
  });

  it("leaves a footprint alone when it's already wide enough on both sides", () => {
    const chunky = { ul: [0, 0], ur: [0, 10], ll: [-10, 0], lr: [-10, 10] };
    expect(exaggerateCorners(chunky)).toEqual(chunky);
  });

  it("preserves the footprint's centroid position", () => {
    const corners = { ul: [10, 10], ur: [10, 10.1], ll: [9.9, 10], lr: [9.9, 10.1] };
    const [clat, clon] = centroid(corners);
    const scaled = exaggerateCorners(corners);
    const [slat, slon] = centroid(scaled);
    expect(slat).toBeCloseTo(clat, 6);
    expect(slon).toBeCloseTo(clon, 6);
  });

  it("caps the multiplier for a near-degenerate (zero-span) footprint rather than dividing by zero", () => {
    const point = { ul: [5, 5], ur: [5, 5], ll: [5, 5], lr: [5, 5] };
    expect(() => exaggerateCorners(point)).not.toThrow();
    const scaled = exaggerateCorners(point);
    expect(scaled.ul).toEqual([5, 5]); // no spread to scale, all corners coincide with the centroid
  });
});

describe("footprintQuadVertices", () => {
  const corners = { ul: [10, 10], ur: [10, 20], lr: [0, 20], ll: [0, 10] };

  it("returns 6 vertices (two triangles) x 3 coordinates each, all on the sphere", () => {
    const verts = footprintQuadVertices(corners, 3);
    expect(verts).toHaveLength(18);
    for (let i = 0; i < 18; i += 3) {
      expect(magnitude(verts.slice(i, i + 3))).toBeCloseTo(3, 6);
    }
  });

  it("reuses the same projected corner for shared triangle vertices (ul and lr appear twice)", () => {
    const verts = footprintQuadVertices(corners, 1);
    const ul = verts.slice(0, 3);
    const ulAgain = verts.slice(9, 12); // second triangle's first vertex
    const lr = verts.slice(6, 9);
    const lrAgain = verts.slice(12, 15); // second triangle's second vertex
    expect(ulAgain).toEqual(ul);
    expect(lrAgain).toEqual(lr);
  });
});

describe("footprintPatchVertices", () => {
  it("matches footprintQuadVertices exactly for a small footprint (no subdivision needed)", () => {
    // Both sides well under MAX_PATCH_SEGMENT_DEG (5) -- a 1x1 grid, same as
    // the plain quad.
    const corners = { ul: [10, 10], ur: [10, 12], lr: [8, 12], ll: [8, 10] };
    expect(footprintPatchVertices(corners, 1)).toEqual(footprintQuadVertices(corners, 1));
  });

  it("subdivides a long swath into more than one quad's worth of vertices", () => {
    // ~35 deg long, well past the 5 deg-per-segment threshold.
    const tmc = { ul: [-5, -20.5], ur: [-5, 14.2], ll: [-5.6, -20.5], lr: [-5.6, 14.2] };
    const verts = footprintPatchVertices(tmc, 1);
    expect(verts.length).toBeGreaterThan(18); // more than one quad (6 vertices x 3 coords)
    expect(verts.length % 18).toBe(0); // still a whole number of triangle pairs
  });

  it("keeps every generated vertex exactly on the sphere", () => {
    const tmc = { ul: [-5, -20.5], ur: [-5, 14.2], ll: [-5.6, -20.5], lr: [-5.6, 14.2] };
    const verts = footprintPatchVertices(tmc, 2.5);
    for (let i = 0; i < verts.length; i += 3) {
      expect(magnitude(verts.slice(i, i + 3))).toBeCloseTo(2.5, 6);
    }
  });

  it("caps the segment count for an extremely long footprint rather than exploding the triangle count", () => {
    const huge = { ul: [-40, -90], ur: [-40, 90], ll: [-41, -90], lr: [-41, 90] };
    const verts = footprintPatchVertices(huge, 1);
    // MAX_PATCH_SEGMENTS_PER_AXIS (16) x 1 grid cells x 2 triangles x 3 verts x 3 coords
    expect(verts.length).toBeLessThanOrEqual(16 * 1 * 2 * 3 * 3);
  });
});

describe("footprintPatchGeometry", () => {
  const corners = { ul: [10, 10], ur: [10, 12], lr: [8, 12], ll: [8, 10] };

  it("returns positions identical to footprintPatchVertices, plus a matching UV per vertex", () => {
    const { positions, uvs } = footprintPatchGeometry(corners, 1);
    expect(positions).toEqual(footprintPatchVertices(corners, 1));
    expect(uvs).toHaveLength((positions.length / 3) * 2);
  });

  it("keeps every UV coordinate inside [0, 1]", () => {
    const tmc = { ul: [-5, -20.5], ur: [-5, 14.2], ll: [-5.6, -20.5], lr: [-5.6, 14.2] };
    const { uvs } = footprintPatchGeometry(tmc, 1);
    for (const c of uvs) {
      expect(c).toBeGreaterThanOrEqual(0);
      expect(c).toBeLessThanOrEqual(1);
    }
  });

  it("maps the ul/ur (top) edge to v=1 and the ll/lr (bottom) edge to v=0, matching three.js's default flipY", () => {
    // A footprint small enough to stay a single quad (no subdivision) --
    // the first triangle's 3 vertices are exactly ul, ur, lr in order (see
    // footprintQuadVertices' winding), so their UVs are easy to check directly.
    const { uvs } = footprintPatchGeometry(corners, 1);
    const ulUV = uvs.slice(0, 2);
    const urUV = uvs.slice(2, 4);
    const lrUV = uvs.slice(4, 6);
    expect(ulUV).toEqual([0, 1]);
    expect(urUV).toEqual([1, 1]);
    expect(lrUV).toEqual([1, 0]);
  });

  it("subdivides into the same number of cells as footprintPatchVertices for a long swath", () => {
    const tmc = { ul: [-5, -20.5], ur: [-5, 14.2], ll: [-5.6, -20.5], lr: [-5.6, 14.2] };
    const { positions, uvs } = footprintPatchGeometry(tmc, 1);
    expect(positions.length).toBeGreaterThan(18);
    expect(uvs.length).toBe((positions.length / 3) * 2);
  });
});
