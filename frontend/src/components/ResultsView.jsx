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

      {job.status === "failed" && <p className="error">{job.error}</p>}

      {job.status === "done" && job.result && (
        <>
          <dl className="metrics">
            <div><dt>Keypoints</dt><dd>{job.result.keypoints_a} / {job.result.keypoints_b}</dd></div>
            <div><dt>Ratio-test matches</dt><dd>{job.result.ratio_test_matches}</dd></div>
            <div><dt>RANSAC inliers</dt><dd>{job.result.inliers}</dd></div>
            <div><dt>Inlier ratio</dt><dd>{(job.result.inlier_ratio * 100).toFixed(0)}%</dd></div>
            <div><dt>Working resolution</dt><dd>{job.result.working_gsd_m} m/px</dd></div>
          </dl>
          {job.result.inliers === 0 && (
            <p className="muted small">
              Zero inliers is itself a real, reportable result here -- see docs/baseline_results.md.
              It's the classical-baseline failure mode this project's learned track (Track B) is meant to fix.
            </p>
          )}
          <div className="overlay-scroll">
            <img className="overlay-img" src={job.overlayUrl} alt="match overlay" />
          </div>
        </>
      )}
    </section>
  );
}
