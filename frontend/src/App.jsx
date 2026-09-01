import { useEffect, useState, useCallback, useRef } from "react";
import CatalogBrowser from "./components/CatalogBrowser";
import PairPicker from "./components/PairPicker";
import ResultsView from "./components/ResultsView";
import { listProducts, suggestPairs, submitMatch, getMatch, overlayUrl } from "./api";
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

  useEffect(() => {
    listProducts()
      .then((data) => setProducts(data))
      .catch((err) => setProductsError(err.message))
      .finally(() => setProductsLoading(false));
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
        <ResultsView job={job} error={jobError} />
      </main>
    </div>
  );
}
