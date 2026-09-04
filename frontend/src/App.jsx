import { useEffect, useState, useCallback, useRef } from "react";
import CatalogBrowser from "./components/CatalogBrowser";
import PairPicker from "./components/PairPicker";
import ResultsView from "./components/ResultsView";
import MetricsDashboard from "./components/MetricsDashboard";
import MoonGlobe from "./components/MoonGlobe";
import { listProducts, suggestPairs, submitMatch, getMatch, overlayUrl, getMetricsMatrix } from "./api";
import "./App.css";

const POLL_INTERVAL_MS = 1500;

export default function App() {
  const [products, setProducts] = useState([]);
  const [productsLoading, setProductsLoading] = useState(true);
  const [productsError, setProductsError] = useState(null);

  const [instrumentFilter, setInstrumentFilter] = useState("all");
  const [selectedId, setSelectedId] = useState(null);

  const [suggestions, setSuggestions] = useState([]);
  const [suggestionsLoading, setSuggestionsLoading] = useState(false);
  const [suggestionsError, setSuggestionsError] = useState(null);

  const [method, setMethod] = useState("sift");
  const [job, setJob] = useState(null);
  const [jobError, setJobError] = useState(null);
  const [running, setRunning] = useState(false);
  const pollRef = useRef(null);

  const [matrix, setMatrix] = useState(null);
  const [matrixLoading, setMatrixLoading] = useState(true);
  const [matrixError, setMatrixError] = useState(null);

  // 3D Moon overlay toggles (moon-globe-sidebar below): a master on/off for
  // the whole footprint layer, plus per-instrument show/hide -- both are
  // plain client-side filters over the same `products` list, MoonGlobe.jsx
  // just skips building a mesh for anything filtered out.
  const [showOverlay, setShowOverlay] = useState(true);
  const [visibleInstruments, setVisibleInstruments] = useState(() => new Set(["OHRC", "TMC-2", "IIRS"]));
  const toggleInstrument = useCallback((instrument) => {
    setVisibleInstruments((prev) => {
      const next = new Set(prev);
      if (next.has(instrument)) next.delete(instrument);
      else next.add(instrument);
      return next;
    });
  }, []);

  useEffect(() => {
    listProducts()
      .then((data) => setProducts(data))
      .catch((err) => setProductsError(err.message))
      .finally(() => setProductsLoading(false));
  }, []);

  useEffect(() => {
    getMetricsMatrix()
      .then((data) => setMatrix(data))
      .catch((err) => setMatrixError(err.message))
      .finally(() => setMatrixLoading(false));
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    setSuggestionsLoading(true);
    setSuggestionsError(null);
    suggestPairs(selectedId)
      .then((data) => setSuggestions(data))
      .catch((err) => setSuggestionsError(err.message))
      .finally(() => setSuggestionsLoading(false));
  }, [selectedId]);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  useEffect(() => () => stopPolling(), [stopPolling]);

  const handleRunMatch = useCallback((productA, productB, matchMethod) => {
    setRunning(true);
    setJobError(null);
    setJob(null);
    stopPolling();

    submitMatch(productA, productB, matchMethod)
      .then((initial) => {
        setJob({ ...initial, overlayUrl: overlayUrl(initial.job_id) });
        pollRef.current = setInterval(() => {
          getMatch(initial.job_id)
            .then((updated) => {
              setJob({ ...updated, overlayUrl: overlayUrl(updated.job_id) });
              if (updated.status === "done" || updated.status === "failed") {
                stopPolling();
                setRunning(false);
              }
            })
            .catch((err) => {
              setJobError(err.message);
              stopPolling();
              setRunning(false);
            });
        }, POLL_INTERVAL_MS);
      })
      .catch((err) => {
        setJobError(err.message);
        setRunning(false);
      });
  }, [stopPolling]);

  const anchorProduct = products.find((p) => p.product_id === selectedId);

  return (
    <div className="app">
      <header className="app-header">
        <h1>SIH26166 — Lunar Image Correspondence</h1>
        <p className="muted">Chandrayaan-2 OHRC / TMC-2 / IIRS, sun-angle &amp; scale-invariant matching demo</p>
      </header>

      <main className="app-grid">
        <CatalogBrowser
          products={products}
          loading={productsLoading}
          error={productsError}
          instrumentFilter={instrumentFilter}
          onFilterChange={setInstrumentFilter}
          onSelect={setSelectedId}
          selectedId={selectedId}
        />
        <PairPicker
          selectedId={selectedId}
          anchorHasRaster={anchorProduct ? anchorProduct.has_raster : false}
          suggestions={suggestions}
          loading={suggestionsLoading}
          error={suggestionsError}
          method={method}
          onMethodChange={setMethod}
          onRunMatch={handleRunMatch}
          running={running}
        />
      </main>

      {/* Full width rather than squeezed into the 3-up grid above: the
          overlay image and the metrics were unreadably small crammed into a
          ~1/3-width column, and there was nowhere to put a plain-language
          summary that wasn't even tighter. Matches the same full-width
          treatment already used for the metrics dashboard and 3D Moon below. */}
      <div className="app-grid-wide">
        <ResultsView job={job} error={jobError} />
      </div>

      <div className="app-grid-wide">
        <MetricsDashboard matrix={matrix} loading={matrixLoading} error={matrixError} />
      </div>

      <div className="app-grid-wide">
        <section className="panel panel-wide">
          <h2>3D Moon</h2>
          <p className="muted small">
            Every product's real footprint, plotted at its actual lat/lon on a rotating globe.
            Wherever the actual Chandrayaan-2 image is available (OHRC/TMC-2/IIRS raster staged --
            "Raster: available" in the catalog above), that real photo is draped onto the patch,
            tinted by its own real solar-incidence angle (lighter = sun closer to overhead, darker =
            grazing light) -- the same number behind the metrics dashboard's "incidence gap" column;
            the remaining products (raster not staged) show that same color as a flat fill instead.
            Drag to rotate, scroll to zoom, click a patch to select that product above. Footprint
            sizes are exaggerated for visibility (a real one can be under a degree wide, and some are
            long, thin swaths only a fraction of a degree across) -- true positions and orientation
            are real, but each side is independently stretched up to a visible minimum, so a very
            narrow swath reads wider relative to its length than the true footprint. The globe's own
            base surface is also real -- NASA's public-domain LROC global color mosaic -- though its
            shading is decorative lighting, not each product's true illumination direction. Click a
            patch to fly the camera in on it; scroll to zoom all the way in on the real pixels. Use
            the toggles alongside the globe to hide the footprint overlay entirely, or instrument by
            instrument, to see the bare base map underneath.
          </p>
          <div className="moon-globe-layout">
            <MoonGlobe
              products={products}
              selectedId={selectedId}
              onSelect={setSelectedId}
              pairIds={job ? [job.product_a, job.product_b] : undefined}
              showOverlay={showOverlay}
              visibleInstruments={visibleInstruments}
            />
            <div className="moon-globe-sidebar">
              <span className="moon-globe-sidebar-label">Overlay</span>
              <button
                type="button"
                className={showOverlay ? "moon-globe-sidebar-toggle moon-globe-sidebar-toggle-active" : "moon-globe-sidebar-toggle"}
                aria-pressed={showOverlay}
                onClick={() => setShowOverlay((v) => !v)}
              >
                <span>Footprints</span>
                <span className="moon-globe-sidebar-dot" />
              </button>
              <span className="moon-globe-sidebar-label">Instruments</span>
              {["OHRC", "TMC-2", "IIRS"].map((instrument) => (
                <button
                  key={instrument}
                  type="button"
                  disabled={!showOverlay}
                  className={
                    visibleInstruments.has(instrument)
                      ? "moon-globe-sidebar-toggle moon-globe-sidebar-toggle-active"
                      : "moon-globe-sidebar-toggle"
                  }
                  aria-pressed={visibleInstruments.has(instrument)}
                  onClick={() => toggleInstrument(instrument)}
                >
                  <span>{instrument}</span>
                  <span className="moon-globe-sidebar-dot" />
                </button>
              ))}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
