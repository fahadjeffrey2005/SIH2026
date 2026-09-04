// Screen 2 (docs/architecture.md Sec. 7): given a product selected in the
// catalog, fetch genuinely-overlapping candidates from GET /pairs/suggest
// (real quads_overlap geometry -- not a date or bounding-box guess) and let
// the user pick one plus a matching method to run.

export default function PairPicker({ selectedId, anchorHasRaster, suggestions, loading, error, method, onMethodChange, onRunMatch, running }) {
  if (!selectedId) {
    return (
      <section className="panel">
        <h2>Pair picker</h2>
        <p className="muted">Select a product from the catalog to see its confirmed overlaps.</p>
      </section>
    );
  }

  return (
    <section className="panel">
      <h2>Pair picker</h2>
      <p className="mono small">anchor: {selectedId}</p>
      {!anchorHasRaster && (
        <p className="error small">
          This product's pixel data isn't staged into the pipeline yet, so it can't be matched
          (its metadata is real, from the catalog -- only the raster is missing).
        </p>
      )}

      {loading && <p className="muted">Checking overlap geometry...</p>}
      {error && <p className="error">{error}</p>}

      {!loading && !error && suggestions.length === 0 && (
        <p className="muted">No other catalog product genuinely overlaps this one.</p>
      )}

      {!loading && !error && suggestions.length > 0 && (
        <>
          <div className="method-row">
            <label>
              <input type="radio" name="method" value="sift" checked={method === "sift"} onChange={() => onMethodChange("sift")} />
              SIFT
            </label>
            <label>
              <input type="radio" name="method" value="akaze" checked={method === "akaze"} onChange={() => onMethodChange("akaze")} />
              AKAZE
            </label>
            <label title="Illumination-invariant descriptor -- matches on real edge/ridge structure regardless of sun angle, instead of raw brightness gradients">
              <input type="radio" name="method" value="hopc" checked={method === "hopc"} onChange={() => onMethodChange("hopc")} />
              HOPC
            </label>
            <label>
              <input type="radio" name="method" value="disk_lightglue" checked={method === "disk_lightglue"} onChange={() => onMethodChange("disk_lightglue")} />
              DISK+LightGlue (learned)
            </label>
          </div>

          <ul className="suggestion-list">
            {suggestions.map((s) => (
              <li key={s.product_id} className="suggestion-row">
                <div>
                  <div className="mono">{s.product_id}</div>
                  <div className="muted small">
                    {s.instrument} · incidence gap {s.incidence_gap_deg != null ? `${s.incidence_gap_deg.toFixed(1)}°` : "unknown"}
                    {!s.has_raster && " · raster not staged"}
                  </div>
                </div>
                <button
                  disabled={!s.has_raster || !anchorHasRaster || running}
                  title={!s.has_raster ? "Pixel data for this product isn't loaded into the pipeline yet" : undefined}
                  onClick={() => onRunMatch(selectedId, s.product_id, method)}
                >
                  {running ? "Running..." : "Match"}
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
