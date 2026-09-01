// Screen 1 (docs/architecture.md Sec. 7): list the ingested catalog,
// filterable by instrument, showing each product's real sun-angle metadata
// and whether pixel data is currently loadable for matching.

const INSTRUMENTS = ["all", "OHRC", "TMC-2", "IIRS"];

export default function CatalogBrowser({ products, loading, error, instrumentFilter, onFilterChange, onSelect, selectedId }) {
  const filtered = instrumentFilter === "all"
    ? products
    : products.filter((p) => p.instrument === instrumentFilter);

  return (
    <section className="panel">
      <h2>Catalog</h2>
      <div className="filter-row">
        {INSTRUMENTS.map((inst) => (
          <button
            key={inst}
            className={inst === instrumentFilter ? "chip chip-active" : "chip"}
            onClick={() => onFilterChange(inst)}
          >
            {inst}
          </button>
        ))}
      </div>

      {loading && <p className="muted">Loading catalog...</p>}
      {error && <p className="error">Failed to load catalog: {error}</p>}

      {!loading && !error && (
        <table className="catalog-table">
          <thead>
            <tr>
              <th>Product</th>
              <th>Instrument</th>
              <th>Date</th>
              <th>Solar incidence</th>
              <th>Raster</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((p) => (
              <tr
                key={p.product_id}
                className={p.product_id === selectedId ? "row-selected" : ""}
                onClick={() => onSelect(p.product_id)}
              >
                <td className="mono">{p.product_id}</td>
                <td>{p.instrument}</td>
                <td>{p.start_time ? p.start_time.slice(0, 10) : "-"}</td>
                <td>{p.solar_incidence_deg != null ? `${p.solar_incidence_deg.toFixed(1)}°` : "-"}</td>
                <td>{p.has_raster ? <span className="badge-yes">available</span> : <span className="badge-no">not staged</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {!loading && !error && filtered.length === 0 && <p className="muted">No products match this filter.</p>}
    </section>
  );
}
