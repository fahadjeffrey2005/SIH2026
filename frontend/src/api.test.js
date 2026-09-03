// api.js is the only place the frontend talks to the FastAPI backend --
// worth pinning its URL-building and error-unwrapping behavior directly,
// since every component test below mocks this module rather than hitting
// a real backend.
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  getMatch,
  getMetricsMatrix,
  listProducts,
  overlayUrl,
  submitMatch,
  suggestPairs,
} from "./api";

afterEach(() => {
  vi.unstubAllGlobals();
});

function mockFetchOnce(response) {
  const fetchMock = vi.fn().mockResolvedValue(response);
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("api.js", () => {
  it("listProducts hits GET /products", async () => {
    const fetchMock = mockFetchOnce({ ok: true, json: async () => [{ product_id: "a" }] });
    const result = await listProducts();
    expect(fetchMock).toHaveBeenCalledWith("http://localhost:8000/products", undefined);
    expect(result).toEqual([{ product_id: "a" }]);
  });

  it("suggestPairs URL-encodes the product id", async () => {
    const fetchMock = mockFetchOnce({ ok: true, json: async () => [] });
    await suggestPairs("ch2_iir/weird id");
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/pairs/suggest?product_id=ch2_iir%2Fweird%20id",
      undefined,
    );
  });

  it("submitMatch POSTs a JSON body with the three fields", async () => {
    const fetchMock = mockFetchOnce({ ok: true, json: async () => ({ job_id: "j1" }) });
    await submitMatch("a", "b", "sift");
    expect(fetchMock).toHaveBeenCalledWith("http://localhost:8000/match", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ product_a: "a", product_b: "b", method: "sift" }),
    });
  });

  it("getMatch and getMetricsMatrix hit their expected paths", async () => {
    const fetchMock = mockFetchOnce({ ok: true, json: async () => ({}) });
    await getMatch("j1");
    expect(fetchMock).toHaveBeenCalledWith("http://localhost:8000/match/j1", undefined);

    await getMetricsMatrix();
    expect(fetchMock).toHaveBeenCalledWith("http://localhost:8000/metrics/matrix", undefined);
  });

  it("overlayUrl builds a plain URL without fetching", () => {
    expect(overlayUrl("j1")).toBe("http://localhost:8000/match/j1/overlay");
  });

  it("surfaces the backend's JSON `detail` field as the error message", async () => {
    mockFetchOnce({
      ok: false,
      status: 404,
      statusText: "Not Found",
      json: async () => ({ detail: "no such product" }),
    });
    await expect(listProducts()).rejects.toThrow("404 no such product");
  });

  it("falls back to statusText when the error body isn't JSON", async () => {
    mockFetchOnce({
      ok: false,
      status: 500,
      statusText: "Internal Server Error",
      json: async () => {
        throw new SyntaxError("not json");
      },
    });
    await expect(listProducts()).rejects.toThrow("500 Internal Server Error");
  });
});
