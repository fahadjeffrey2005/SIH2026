// Screen 3 (docs/architecture.md Sec. 7) -- the demo centerpiece: the two
// crops side by side with drawn correspondence lines, plus the actual
// inlier/keypoint numbers behind them.
//
// Uses a plain <img> against GET /match/{id}/overlay rather than
// OpenSeadragon deep-zoom for now: that needs a tile pyramid generated per
// product, which isn't built yet (native OHRC/TMC-2 rasters aren't even
// staged into the pipeline -- see README.md). Swapping this <img> for an
// OpenSeadragon viewer once tiling exists is a self-contained follow-up;
// nothing about the job/result data shape needs to change for it.
//
// Rendered full-width (see App.jsx) rather than squeezed into the 3-up
// grid it used to share with the catalog browser and pair picker -- that
// left the overlay image and the metrics list too small to actually read.
//
// The plain-language summary shown above the technical metrics (for a
// viewer who doesn't know what an inlier ratio or RANSAC is) is built by
// resultSummary.js's summarizeResult -- split out the same way
// moonGlobeMath.js is split from MoonGlobe.jsx, so the wording logic is
// unit-testable on its own.
import { summarizeResult } from "./resultSummary";

export default function ResultsView({ job, error }) {
  if (error) {
    return (
      <section className="panel">
        <h2>Results</h2>
        <p className="error">{error}</p>
      </section>
    );
  }

  if (!job) {
    return (
      <section className="panel">
        <h2>Results</h2>
        <p className="muted">Run a match from the pair picker to see results here.</p>
      </section>
    );
  }

  return (
    <section className="panel">
      <h2>Results</h2>
      <p className="mono small">{job.product_a} &harr; {job.product_b} ({job.method})</p>
      <p>
        status: <span className={`status status-${job.status}`}>{job.status}</span>
      </p>

      {(job.status === "running" || job.status === "queued") && (
        <p className="muted">Comparing the two images now -- this usually takes a few seconds.</p>
      )}

      {job.status === "failed" && <p className="error">{job.error}</p>}

      {job.status === "done" && job.result && (
        // Laid out as a horizontally-scrolling row of cards (summary,
        // technical detail, match image) rather than one long vertically
        // stacked block -- each card is independently readable, and the
        // row only needs to scroll sideways once it doesn't fit, per
        // explicit request.
        <div className="results-row">
          <div className="result-card">
            {(() => {
              const summary = summarizeResult(job.result);
              return (
                <div className={`result-summary result-summary-${summary.tone}`}>
                  <p className="result-summary-headline">{summary.headline}</p>
                  <p className="result-summary-body">{summary.body}</p>
                </div>
              );
            })()}
          </div>

          <div className="result-card">
            <h3 className="results-subhead">Technical detail</h3>
            <dl className="metrics metrics-stacked">
              <div><dt>Keypoints</dt><dd>{job.result.keypoints_a} / {job.result.keypoints_b}</dd></div>
              <div><dt>Candidate matches</dt><dd>{job.result.raw_matches}</dd></div>
              <div><dt>RANSAC inliers</dt><dd>{job.result.inliers}</dd></div>
              <div><dt>Inlier ratio</dt><dd>{(job.result.inlier_ratio * 100).toFixed(0)}%</dd></div>
              <div><dt>Working resolution</dt><dd>{job.result.working_gsd_m} m/px</dd></div>
              <div>
                <dt>Geolocation agreement</dt>
                <dd>
                  {job.result.geoloc_error_median_m != null
                    ? `${Math.round(job.result.geoloc_error_median_m).toLocaleString()} m median (n=${job.result.geoloc_error_n})`
                    : "n/a (no inliers)"}
                </dd>
              </div>
            </dl>
            {job.result.geoloc_error_median_m != null && (
              <p className="muted small">
                Independent check via each image's own geolocation, not RANSAC -- large swaths
                (TMC-2, IIRS) can show big model error unrelated to match quality.
              </p>
            )}
            {job.result.inliers === 0 && (
              <p className="muted small">
                Zero inliers is itself a real, reportable result -- this method's real limit, not a
                bug.
              </p>
            )}
          </div>

          <div className="result-card result-card-image">
            <h3 className="results-subhead">Match image</h3>
            <p className="muted small">Lines connect matched points -- scroll to explore.</p>
            <div className="overlay-scroll">
              <img className="overlay-img" src={job.overlayUrl} alt="match overlay" />
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
