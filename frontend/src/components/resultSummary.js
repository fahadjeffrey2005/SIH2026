// Pure, unit-testable wording helper for ResultsView.jsx's plain-language
// summary. Split out the same way moonGlobeMath.js is split from
// MoonGlobe.jsx: keeps the component file itself export-only (React fast
// refresh wants that) and makes the wording logic trivial to test on its
// own, independent of any rendering.
//
// summarizeResult turns the same real numbers already shown in the
// technical `dl.metrics` block into one or two plain-English sentences, for
// a viewer (a judge, a teammate from a different track) who doesn't know
// what an inlier ratio or RANSAC is -- the technical numbers stay put
// underneath in ResultsView for anyone who wants them.
export function summarizeResult(result) {
  const { inliers, raw_matches, inlier_ratio, geoloc_error_median_m } = result;
  if (inliers > 0) {
    const pct = Math.round(inlier_ratio * 100);
    let geoSentence = "";
    if (geoloc_error_median_m != null) {
      const km = geoloc_error_median_m / 1000;
      geoSentence =
        km < 10
          ? ` Their real ground positions also line up to within about ${km.toFixed(1)} km of each other -- an independent check that this is genuinely the same spot on the Moon, not a coincidence.`
          : ` Their real ground positions land roughly ${Math.round(km).toLocaleString()} km apart on that same independent check -- wider than ideal, but a known limitation of how these two products are geolocated (see the technical note below), not necessarily a sign the match itself is wrong.`;
    }
    return {
      tone: "good",
      headline: `Match found -- ${inliers} point${inliers === 1 ? " lines" : "s line"} up between the two images.`,
      body: `Out of ${raw_matches} candidate matches the algorithm proposed, ${inliers} survived a geometric consistency check -- about ${pct}% held up.${geoSentence}`,
    };
  }
  return {
    tone: "bad",
    headline: "No reliable match found.",
    body: "These two images were too different -- in lighting, sensor, or scale -- for this method to confidently link any points between them. That's a genuine, useful result, not an error: it shows exactly where this approach's limits are.",
  };
}
