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
          ? ` Ground positions agree to within ~${km.toFixed(1)} km -- not a coincidence.`
          : ` Ground positions land ~${Math.round(km).toLocaleString()} km apart -- a known limitation, not a bad match.`;
    }
    return {
      tone: "good",
      headline: `Match found -- ${inliers} point${inliers === 1 ? " lines" : "s line"} up between the two images.`,
      body: `Out of ${raw_matches} candidate matches, ${inliers} survived (${pct}%).${geoSentence}`,
    };
  }
  return {
    tone: "bad",
    headline: "No reliable match found.",
    body: "Too different in lighting, sensor, or scale to link any points -- a real result, not an error.",
  };
}
