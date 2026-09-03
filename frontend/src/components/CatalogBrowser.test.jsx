import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import CatalogBrowser from "./CatalogBrowser";

const PRODUCTS = [
  {
    product_id: "ch2_iir_nri_20211221t0324126144_d_img_hw1",
    instrument: "IIRS",
    start_time: "2021-12-21T03:24:12Z",
    solar_incidence_deg: 7.3,
    has_raster: true,
  },
  {
    product_id: "ch2_tmc_ncf_20240125t0622476078_d_img_d18",
    instrument: "TMC-2",
    start_time: "2024-01-25T06:22:47Z",
    solar_incidence_deg: 34.1,
    has_raster: false,
  },
];

describe("CatalogBrowser", () => {
  it("shows a loading state and nothing else", () => {
    render(<CatalogBrowser products={[]} loading error={null} instrumentFilter="all" onFilterChange={() => {}} onSelect={() => {}} selectedId={null} />);
    expect(screen.getByText(/loading catalog/i)).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("shows an error state instead of the table", () => {
    render(<CatalogBrowser products={[]} loading={false} error="backend unreachable" instrumentFilter="all" onFilterChange={() => {}} onSelect={() => {}} selectedId={null} />);
    expect(screen.getByText(/failed to load catalog: backend unreachable/i)).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("renders one row per product with real metadata, not placeholders", () => {
    render(<CatalogBrowser products={PRODUCTS} loading={false} error={null} instrumentFilter="all" onFilterChange={() => {}} onSelect={() => {}} selectedId={null} />);
    expect(screen.getByText("ch2_iir_nri_20211221t0324126144_d_img_hw1")).toBeInTheDocument();
    expect(screen.getByText("7.3°")).toBeInTheDocument();
    expect(screen.getByText("available")).toBeInTheDocument();
    expect(screen.getByText("not staged")).toBeInTheDocument();
  });

  it("filters rows down to the selected instrument", () => {
    render(<CatalogBrowser products={PRODUCTS} loading={false} error={null} instrumentFilter="TMC-2" onFilterChange={() => {}} onSelect={() => {}} selectedId={null} />);
    expect(screen.queryByText("ch2_iir_nri_20211221t0324126144_d_img_hw1")).not.toBeInTheDocument();
    expect(screen.getByText("ch2_tmc_ncf_20240125t0622476078_d_img_d18")).toBeInTheDocument();
  });

  it("calls onFilterChange when an instrument chip is clicked", () => {
    const onFilterChange = vi.fn();
    render(<CatalogBrowser products={PRODUCTS} loading={false} error={null} instrumentFilter="all" onFilterChange={onFilterChange} onSelect={() => {}} selectedId={null} />);
    fireEvent.click(screen.getByRole("button", { name: "OHRC" }));
    expect(onFilterChange).toHaveBeenCalledWith("OHRC");
  });

  it("calls onSelect with the product id when a row is clicked", () => {
    const onSelect = vi.fn();
    render(<CatalogBrowser products={PRODUCTS} loading={false} error={null} instrumentFilter="all" onFilterChange={() => {}} onSelect={onSelect} selectedId={null} />);
    fireEvent.click(screen.getByText("ch2_tmc_ncf_20240125t0622476078_d_img_d18"));
    expect(onSelect).toHaveBeenCalledWith("ch2_tmc_ncf_20240125t0622476078_d_img_d18");
  });

  it("marks the selected row so the user can see which product is active", () => {
    render(<CatalogBrowser products={PRODUCTS} loading={false} error={null} instrumentFilter="all" onFilterChange={() => {}} onSelect={() => {}} selectedId={PRODUCTS[0].product_id} />);
    const row = screen.getByText(PRODUCTS[0].product_id).closest("tr");
    expect(row).toHaveClass("row-selected");
  });

  it("shows an empty-filter message rather than a blank table", () => {
    render(<CatalogBrowser products={PRODUCTS} loading={false} error={null} instrumentFilter="OHRC" onFilterChange={() => {}} onSelect={() => {}} selectedId={null} />);
    expect(screen.getByText(/no products match this filter/i)).toBeInTheDocument();
  });
});
