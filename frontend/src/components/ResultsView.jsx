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
        <>
          {(() => {
            const summary = summarizeResult(job.result);
            return (
              <div className={`result-summary result-summary-${summary.tone}`}>
                <p className="result-summary-headline">{summary.headline}</p>
                <p className="result-summary-body">{summary.body}</p>
              </div>
            );
          })()}
          <h3 className="results-subhead">Technical detail</h3>
          <dl className="metrics">
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
              Independent accuracy check: how far apart each matched pixel pair's own PDS4 corner
              geolocation places them on the lunar surface -- not derived from RANSAC, which only
              checks internal (homography) self-consistency. See docs/baseline_results.md's
              "geolocation agreement" section: this is a pseudo-ground-truth check (single bilinear
              quad per product), most trustworthy for smaller footprints -- large pushbroom swaths
              (TMC-2, IIRS) can show tens-to-hundreds of km of model error unrelated to matching
              quality.
            </p>
          )}
          {job.result.inliers === 0 && (
            <p className="muted small">
              Zero inliers is itself a real, reportable result here -- see docs/baseline_results.md.
              Both tracks (classical and learned) fail on the high-sun-angle-gap pair; that's the
              actual hard case this project is about.
            </p>
          )}
          <p className="muted small">
            Below: the two real images side by side, with a line drawn between every matched point
            that survived the consistency check above -- scroll/zoom in the box to inspect them.
          </p>
          <div className="overlay-scroll">
            <img className="overlay-img" src={job.overlayUrl} alt="match overlay" />
          </div>
        </>
      )}
    </section>
  );
}
