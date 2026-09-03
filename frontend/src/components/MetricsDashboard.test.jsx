import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import MetricsDashboard from "./MetricsDashboard";

const ROWS = [
  {
    product_a: "ch2_iir_nri_20211221t0324126144_d_img_hw1",
    instrument_a: "IIRS",
    product_b: "ch2_tmc_ncf_20240125t0622476078_d_img_d18",
    instrument_b: "TMC-2",
    incidence_gap_deg: 26.9,
    method: "sift",
    inliers: 7,
    raw_matches: 25,
    inlier_ratio: 0.28,
    geoloc_median_m: 186679.5,
  },
  {
    product_a: "ch2_iir_nri_20211221t0324126144_d_img_hw1",
    instrument_a: "IIRS",
    product_b: "ch2_tmc_ncf_20240125t0622476078_d_img_d18",
    instrument_b: "TMC-2",
    incidence_gap_deg: 26.9,
    method: "disk_lightglue",
    inliers: 0,
    raw_matches: 11,
    inlier_ratio: 0,
    geoloc_median_m: null,
  },
];

describe("MetricsDashboard", () => {
  it("shows a loading state", () => {
    render(<MetricsDashboard matrix={null} loading error={null} />);
    expect(screen.getByText(/loading comparison matrix/i)).toBeInTheDocument();
  });

  it("shows an error state instead of a stale table", () => {
    render(<MetricsDashboard matrix={null} loading={false} error="500 backend exploded" />);
    expect(screen.getByText("500 backend exploded")).toBeInTheDocument();
  });

  it("says when there's no matrix data yet rather than rendering an empty table", () => {
    render(<MetricsDashboard matrix={{ rows: [] }} loading={false} error={null} />);
    expect(screen.getByText(/no matrix data yet/i)).toBeInTheDocument();
  });

  it("renders one column per method and marks zero-inlier cells distinctly from hits", () => {
    render(<MetricsDashboard matrix={{ rows: ROWS }} loading={false} error={null} />);
    expect(screen.getByRole("columnheader", { name: "SIFT" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "DISK+LightGlue" })).toBeInTheDocument();

    const inlierCells = screen.getAllByText(/^(7|0)$/, { selector: ".cell-inliers" });
    expect(inlierCells).toHaveLength(2);
    expect(inlierCells[0].closest("td")).toHaveClass("cell-hit");
    expect(inlierCells[1].closest("td")).toHaveClass("cell-miss");
  });

  it("shows geoloc agreement only for cells that actually had inliers to measure", () => {
    render(<MetricsDashboard matrix={{ rows: ROWS }} loading={false} error={null} />);
    expect(screen.getByText(/186,680 m geoloc/)).toBeInTheDocument();
  });
});
