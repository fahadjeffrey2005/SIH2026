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
    <>
      {/* Landing: the 3D Moon fills the entire first viewport (own black
          background, edge to edge -- not squeezed into a bordered card like
          the sections below), with just the team name + one-line project
          description overlaid on top of it and the overlay toggles as a
          floating glass control in the bottom-right corner. Rendered as a
          sibling of `.app` (not inside it) so it isn't constrained by that
          container's max-width/padding. */}
      <section className="hero-3d">
        <div className="hero-3d-globe">
          <MoonGlobe
            products={products}
            selectedId={selectedId}
            onSelect={setSelectedId}
            pairIds={job ? [job.product_a, job.product_b] : undefined}
            showOverlay={showOverlay}
            visibleInstruments={visibleInstruments}
          />
        </div>

        <div className="hero-3d-overlay">
          <h1 className="hero-3d-title">
            BADR <span className="hero-3d-title-sep">&mdash;</span> SIH26166
          </h1>
          <p className="hero-3d-subtitle">
            Multi-modal, sun-angle- and scale-invariant image correspondence using Chandrayaan-2
            optical images (OHRC, TMC-2, and IIRS)
          </p>
        </div>

        <div className="hero-3d-toggles glass-panel">
          <span className="hero-3d-toggles-label">Overlay</span>
          <button
            type="button"
            className={showOverlay ? "glass-toggle glass-toggle-active" : "glass-toggle"}
            aria-pressed={showOverlay}
            onClick={() => setShowOverlay((v) => !v)}
          >
            <span>Footprints</span>
            <span className="glass-toggle-dot" />
          </button>
          <span className="hero-3d-toggles-label">Instruments</span>
          <div className="hero-3d-toggles-row">
            {["OHRC", "TMC-2", "IIRS"].map((instrument) => (
              <button
                key={instrument}
                type="button"
                disabled={!showOverlay}
                className={
                  visibleInstruments.has(instrument) ? "glass-toggle glass-toggle-active" : "glass-toggle"
                }
                aria-pressed={visibleInstruments.has(instrument)}
                onClick={() => toggleInstrument(instrument)}
              >
                <span>{instrument}</span>
                <span className="glass-toggle-dot" />
              </button>
            ))}
          </div>
        </div>
      </section>

      {/* Short black-to-white fade so scrolling out of the hero isn't an
          abrupt cut -- purely decorative, no content. */}
      <div className="hero-3d-fade" aria-hidden="true" />

      <div className="app">
        <p className="app-intro muted small">
          Every product's real footprint is plotted at its actual lat/lon on the globe above.
          Wherever the actual Chandrayaan-2 image is available (OHRC/TMC-2/IIRS raster staged --
          "Raster: available" in the catalog below), that real photo is draped onto the patch,
          tinted by its own real solar-incidence angle (lighter = sun closer to overhead, darker =
          grazing light) -- the same number behind the metrics dashboard's "incidence gap" column.
          Drag to rotate, scroll to zoom, click a patch to select that product below; use the
          toggles in the globe's corner to hide the footprint overlay entirely, or instrument by
          instrument.
        </p>

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

        {/* Full width rather than squeezed into the 2-up grid above: the
            overlay image and the metrics were unreadably small crammed into
            a narrow column, and there was nowhere to put a plain-language
            summary that wasn't even tighter. Matches the same full-width
            treatment used for the metrics dashboard below. */}
        <div className="app-grid-wide">
          <ResultsView job={job} error={jobError} />
        </div>

        <div className="app-grid-wide">
          <MetricsDashboard matrix={matrix} loading={matrixLoading} error={matrixError} />
        </div>
      </div>
    </>
  );
}
