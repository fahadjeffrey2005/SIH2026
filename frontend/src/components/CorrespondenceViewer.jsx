// The interactive centerpiece of the metrics dashboard: instead of one
// flattened "here's a picture of the matches" PNG, this loads the two real
// source crops (GET /metrics/matrix/crop/{filename}) and draws each row's
// actual RANSAC-inlier points as a hoverable SVG overlay on top -- pan and
// zoom either image independently, and hovering one matched point
// highlights its partner on the OTHER image plus that specific
// correspondence's own geolocation-agreement distance (not just the row's
// aggregate median). For DISK+LightGlue rows, a toggle switches between the
// pre-fix (2048 keypoints) and post-fix (4096) point sets -- real numbers
// from pipeline/match/build_matrix.py re-running the same crops at the old
// budget, not a mocked-up illustration -- see docs/baseline_results.md's
// "Track B keypoint-budget fix".

import { useCallback, useRef, useState } from "react";

const MIN_SCALE = 0.2;
const MAX_SCALE = 8;
const ZOOM_STEP = 1.25;
const INITIAL_TRANSFORM = { scale: 1, x: 0, y: 0 };
// The initial fit-to-points framing (see onImgLoad) needs to be allowed to
// go well below MIN_SCALE for the most extreme pushbroom-strip crops --
// otherwise the "always fit every point on load" guarantee silently loses
// to the manual-zoom floor and points end up off-screen again, exactly the
// bug this framing exists to fix. MIN_SCALE stays the floor for manual
// zoom-out (below that, a single wheel tick would stop doing anything
// useful), but the initial fit is allowed its own, much lower floor.
const FIT_MIN_SCALE = 0.01;

// Point markers are drawn in the SVG's native (image-pixel) coordinate
// space, but that whole space gets visually scaled by the CSS transform
// applied to .zoom-pane-content -- so a fixed native-pixel radius would
// look tiny on a heavily-zoomed-out pane and huge on a heavily-zoomed-in
// one. Dividing the target apparent (screen-pixel) size by the current
// scale keeps markers a constant, comfortably clickable size on screen
// at any zoom level, the same way map-pin markers stay a fixed size
// while the map underneath zooms freely.
const POINT_SCREEN_R = 7;
const POINT_SCREEN_R_ACTIVE = 13;

function clamp(v, lo, hi) {
  return Math.min(hi, Math.max(lo, v));
}

function ZoomPane({ imageUrl, label, side, points, hoveredIndex, onHoverIndex }) {
  const [transform, setTransform] = useState(INITIAL_TRANSFORM);
  const [naturalSize, setNaturalSize] = useState(null);
  const [drag, setDrag] = useState(null);
  const viewportRef = useRef(null);
  // "Reset" returns to the fit-to-view framing computed on load (see
  // onImgLoad below), not necessarily 1:1 scale at the top-left corner --
  // for the large crops these viewers show, 1:1 mostly displays a black
  // corner with the matched points scrolled off-screen, which defeats the
  // whole point of an "interactive, impressive" viewer. Falls back to
  // INITIAL_TRANSFORM when a fit couldn't be computed (e.g. under jsdom in
  // tests, where the viewport never actually lays out).
  const initialTransformRef = useRef(INITIAL_TRANSFORM);

  const zoomBy = useCallback((factor) => {
    setTransform((t) => ({ ...t, scale: clamp(t.scale * factor, MIN_SCALE, MAX_SCALE) }));
  }, []);

  const resetView = useCallback(() => setTransform(initialTransformRef.current), []);

  const onImgLoad = useCallback((e) => {
    const w = e.target.naturalWidth;
    const h = e.target.naturalHeight;
    setNaturalSize({ w, h });

    const vp = viewportRef.current;
    const vw = vp?.clientWidth ?? 0;
    const vh = vp?.clientHeight ?? 0;
    if (w <= 0 || h <= 0 || vw <= 0 || vh <= 0) return;

    // These crops can be extreme pushbroom-swath strips (some over 30x
    // taller than wide), and the matched points on a given side aren't
    // necessarily clustered close together along that long axis either --
    // centering on their mean position isn't enough if the points
    // themselves are spread wider than one viewport's worth of height, as
    // they often are here. So: frame the view around the points' own
    // bounding box (with margin) rather than the whole image, and choose
    // whatever scale makes that box fit -- that's the one framing that
    // guarantees every matched point is actually on screen on load,
    // rather than technically present in the DOM but panned off to a
    // spot the user has no reason to go looking for.
    let fitScale, cx, cy;
    if (points.length > 0) {
      const xs = points.map((p) => p[0]);
      const ys = points.map((p) => p[1]);
      const minX = Math.min(...xs), maxX = Math.max(...xs);
      const minY = Math.min(...ys), maxY = Math.max(...ys);
      const MARGIN = 1.5; // multiplies the bbox span, so points sit well inside the edges, not flush against them
      const boxW = Math.max((maxX - minX) * MARGIN, 40);
      const boxH = Math.max((maxY - minY) * MARGIN, 40);
      fitScale = clamp(Math.min(vw / boxW, vh / boxH), FIT_MIN_SCALE, MAX_SCALE);
      cx = (minX + maxX) / 2;
      cy = (minY + maxY) / 2;
    } else {
      // No points for this side/variant (viewer-panes doesn't render at
      // all when there are none today, but stay correct if that changes):
      // fall back to fitting the image's width and centering vertically.
      fitScale = clamp(vw / w, FIT_MIN_SCALE, MAX_SCALE);
      cx = w / 2;
      cy = h / 2;
    }

    const contentW = w * fitScale;
    const contentH = h * fitScale;
    const x = contentW <= vw ? (vw - contentW) / 2 : clamp(vw / 2 - cx * fitScale, vw - contentW, 0);
    const y = contentH <= vh ? (vh - contentH) / 2 : clamp(vh / 2 - cy * fitScale, vh - contentH, 0);
    const fit = { scale: fitScale, x, y };
    initialTransformRef.current = fit;
    setTransform(fit);
  }, [points]);

  const onWheel = useCallback((e) => {
    e.preventDefault();
    zoomBy(e.deltaY < 0 ? ZOOM_STEP : 1 / ZOOM_STEP);
  }, [zoomBy]);

  const onPointerDown = useCallback((e) => {
    setDrag({ startX: e.clientX, startY: e.clientY, origX: transform.x, origY: transform.y });
  }, [transform.x, transform.y]);

  const onPointerMove = useCallback((e) => {
    if (!drag) return;
    setTransform((t) => ({ ...t, x: drag.origX + (e.clientX - drag.startX), y: drag.origY + (e.clientY - drag.startY) }));
  }, [drag]);

  const endDrag = useCallback(() => setDrag(null), []);

  return (
    <div className="zoom-pane">
      <div className="zoom-pane-toolbar">
        <span className="mono small">{label}</span>
        <div className="zoom-pane-controls">
          <button type="button" onClick={() => zoomBy(ZOOM_STEP)} aria-label="Zoom in">+</button>
          <button type="button" onClick={() => zoomBy(1 / ZOOM_STEP)} aria-label="Zoom out">&minus;</button>
          <button type="button" onClick={resetView} aria-label="Reset view">Reset</button>
        </div>
      </div>
      <div
        className="zoom-pane-viewport"
        ref={viewportRef}
        onWheel={onWheel}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerLeave={endDrag}
      >
        <div
          className="zoom-pane-content"
          style={{ transform: `translate(${transform.x}px, ${transform.y}px) scale(${transform.scale})` }}
        >
          <img
            src={imageUrl}
            alt={`${label} crop`}
            draggable={false}
            onLoad={onImgLoad}
          />
          {naturalSize && naturalSize.w > 0 && (
            <svg
              className="zoom-pane-points"
              viewBox={`0 0 ${naturalSize.w} ${naturalSize.h}`}
              width={naturalSize.w}
              height={naturalSize.h}
            >
              {points.map((p, i) => {
                const active = hoveredIndex === i;
                const r = clamp((active ? POINT_SCREEN_R_ACTIVE : POINT_SCREEN_R) / transform.scale, 1.5, 200);
                return (
                  <circle
                    key={i}
                    data-testid={`match-point-${side}-${i}`}
                    cx={p[0]}
                    cy={p[1]}
                    r={r}
                    className={active ? "match-point match-point-active" : "match-point"}
                    onMouseEnter={() => onHoverIndex(i)}
                    onMouseLeave={() => onHoverIndex(null)}
                  />
                );
              })}
            </svg>
          )}
        </div>
      </div>
    </div>
  );
}

export default function CorrespondenceViewer({ row, imageAUrl, imageBUrl }) {
  const [hoveredIndex, setHoveredIndex] = useState(null);
  const [variant, setVariant] = useState("new");

  const hasBudgetToggle = row.method === "disk_lightglue" && row.keypoint_budget_comparison != null;
  const active = hasBudgetToggle ? row.keypoint_budget_comparison[variant] : row;
  const pointsA = active.points_a || [];
  const pointsB = active.points_b || [];

  // Per-point geoloc errors are only saved for the row's own (== "new" for
  // disk_lightglue) points -- the "old" keypoint-budget variant only carries
  // its aggregate median, shown in the toggle bar itself.
  const errors = (!hasBudgetToggle || variant === "new") ? row.point_geoloc_errors_m : null;

  return (
    <div className="correspondence-viewer">
      {hasBudgetToggle && (
        <div className="budget-toggle">
          <span className="muted small">Keypoint budget:</span>
          <button
            type="button"
            className={variant === "old" ? "chip chip-active" : "chip"}
            onClick={() => setVariant("old")}
          >
            2048 (original)
          </button>
          <button
            type="button"
            className={variant === "new" ? "chip chip-active" : "chip"}
            onClick={() => setVariant("new")}
          >
            4096 (fixed)
          </button>
          <span className="muted small">
            {active.inliers} inliers, {(active.inlier_ratio * 100).toFixed(0)}% ratio
            {active.geoloc_median_m != null && `, ${Math.round(active.geoloc_median_m).toLocaleString()} m geoloc`}
          </span>
        </div>
      )}

      {pointsA.length === 0 ? (
        <p className="muted small">No inliers to show for this method/pair.</p>
      ) : (
        <div className="viewer-panes">
          <ZoomPane imageUrl={imageAUrl} label={row.product_a} side="a" points={pointsA} hoveredIndex={hoveredIndex} onHoverIndex={setHoveredIndex} />
          <ZoomPane imageUrl={imageBUrl} label={row.product_b} side="b" points={pointsB} hoveredIndex={hoveredIndex} onHoverIndex={setHoveredIndex} />
        </div>
      )}

      {hoveredIndex != null && errors && errors[hoveredIndex] != null && (
        <p className="muted small hover-readout">
          match #{hoveredIndex + 1}: {Math.round(errors[hoveredIndex]).toLocaleString()} m geolocation disagreement
          (independent accuracy check, not RANSAC)
        </p>
      )}
    </div>
  );
}
