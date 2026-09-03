// Integration test for the wiring in App.jsx itself -- the four components
// are unit-tested on their own (see components/*.test.jsx); this test mocks
// only api.js and drives the real App to catch bugs in how the pieces are
// glued together (state flow, polling, effect dependencies) rather than
// anything already covered at the unit level.
import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import * as api from "./api";

vi.mock("./api");

const PRODUCT = {
  product_id: "ch2_iir_nri_20211221t0324126144_d_img_hw1",
  instrument: "IIRS",
  start_time: "2021-12-21T03:24:12Z",
  solar_incidence_deg: 7.3,
  has_raster: true,
};

const SUGGESTION = {
  product_id: "ch2_tmc_ncf_20240125t0622476078_d_img_d18",
  instrument: "TMC-2",
  incidence_gap_deg: 26.9,
  has_raster: true,
};

beforeEach(() => {
  api.listProducts.mockResolvedValue([PRODUCT]);
  api.getMetricsMatrix.mockResolvedValue({ rows: [] });
  api.suggestPairs.mockResolvedValue([SUGGESTION]);
  api.overlayUrl.mockImplementation((jobId) => `http://localhost:8000/match/${jobId}/overlay`);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("App", () => {
  it("loads the catalog and metrics matrix on mount", async () => {
    render(<App />);
    expect(await screen.findByText(PRODUCT.product_id)).toBeInTheDocument();
    expect(api.listProducts).toHaveBeenCalledTimes(1);
    expect(api.getMetricsMatrix).toHaveBeenCalledTimes(1);
  });

  it("selecting a catalog row fetches its overlap suggestions", async () => {
    render(<App />);
    const row = await screen.findByText(PRODUCT.product_id);
    await act(async () => row.click());

    expect(api.suggestPairs).toHaveBeenCalledWith(PRODUCT.product_id);
    expect(await screen.findByText(SUGGESTION.product_id)).toBeInTheDocument();
  });

  it("running a match submits the job, polls until done, and renders the result", async () => {
    api.submitMatch.mockResolvedValue({
      job_id: "job-1",
      product_a: PRODUCT.product_id,
      product_b: SUGGESTION.product_id,
      method: "sift",
      status: "running",
    });
    api.getMatch.mockResolvedValue({
      job_id: "job-1",
      product_a: PRODUCT.product_id,
      product_b: SUGGESTION.product_id,
      method: "sift",
      status: "done",
      result: {
        keypoints_a: 8000,
        keypoints_b: 4207,
        raw_matches: 25,
        inliers: 7,
        inlier_ratio: 0.28,
        working_gsd_m: 50,
        geoloc_error_median_m: 186679.5,
        geoloc_error_n: 7,
      },
    });

    render(<App />);
    const row = await screen.findByText(PRODUCT.product_id);
    await act(async () => row.click());
    const matchButton = await screen.findByRole("button", { name: "Match" });

    await act(async () => matchButton.click());
    expect(api.submitMatch).toHaveBeenCalledWith(PRODUCT.product_id, SUGGESTION.product_id, "sift");

    // App polls getMatch on a 1.5s interval until status is a terminal one --
    // wait for real time to pass rather than faking timers, since jsdom +
    // vitest fake timers and React's own scheduling don't always interleave
    // predictably with `act`.
    await waitFor(() => expect(api.getMatch).toHaveBeenCalledWith("job-1"), { timeout: 3000 });
    expect(await screen.findByText("done")).toBeInTheDocument();
    expect(screen.getByText("7")).toBeInTheDocument();
  });

  it("shows the products error state when the catalog fails to load", async () => {
    api.listProducts.mockRejectedValue(new Error("500 backend exploded"));
    render(<App />);
    expect(await screen.findByText(/failed to load catalog: 500 backend exploded/i)).toBeInTheDocument();
  });
});
