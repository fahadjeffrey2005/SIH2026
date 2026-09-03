// Thin fetch wrapper for the FastAPI backend (backend/app, docs/architecture.md
// Sec. 6). No client-side env-var setup required for the hackathon demo:
// point this at wherever `uvicorn app.main:app` is actually running.
const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

async function request(path, options) {
  const res = await fetch(`${API_BASE}${path}`, options);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      // response body wasn't JSON -- keep statusText
    }
    throw new Error(`${res.status} ${detail}`);
  }
  return res.json();
}

export function listProducts() {
  return request("/products");
}

export function suggestPairs(productId) {
  return request(`/pairs/suggest?product_id=${encodeURIComponent(productId)}`);
}

export function submitMatch(productA, productB, method) {
  return request("/match", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ product_a: productA, product_b: productB, method }),
  });
}

export function getMatch(jobId) {
  return request(`/match/${jobId}`);
}

export function overlayUrl(jobId) {
  return `${API_BASE}/match/${jobId}/overlay`;
}

export function getMetricsMatrix() {
  return request("/metrics/matrix");
}

export function matrixCropUrl(filename) {
  return `${API_BASE}/metrics/matrix/crop/${filename}`;
}
