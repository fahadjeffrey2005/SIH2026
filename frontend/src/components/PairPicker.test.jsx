import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import PairPicker from "./PairPicker";

const SUGGESTION = {
  product_id: "ch2_tmc_ncf_20240125t0622476078_d_img_d18",
  instrument: "TMC-2",
  incidence_gap_deg: 26.9,
  has_raster: true,
};

const baseProps = {
  selectedId: "ch2_iir_nri_20211221t0324126144_d_img_hw1",
  anchorHasRaster: true,
  suggestions: [SUGGESTION],
  loading: false,
  error: null,
  method: "sift",
  onMethodChange: () => {},
  onRunMatch: () => {},
  running: false,
};

describe("PairPicker", () => {
  it("prompts for a selection before anything is picked in the catalog", () => {
    render(<PairPicker {...baseProps} selectedId={null} suggestions={[]} />);
    expect(screen.getByText(/select a product from the catalog/i)).toBeInTheDocument();
  });

  it("warns when the anchor product has no staged raster, using the real reason not a generic error", () => {
    render(<PairPicker {...baseProps} anchorHasRaster={false} />);
    expect(screen.getByText(/pixel data isn't staged/i)).toBeInTheDocument();
  });

  it("shows real incidence-gap geometry for each suggestion, not a date guess", () => {
    render(<PairPicker {...baseProps} />);
    expect(screen.getByText(SUGGESTION.product_id)).toBeInTheDocument();
    expect(screen.getByText(/incidence gap 26.9°/)).toBeInTheDocument();
  });

  it("says when a catalog product genuinely has no confirmed overlap", () => {
    render(<PairPicker {...baseProps} suggestions={[]} />);
    expect(screen.getByText(/no other catalog product genuinely overlaps/i)).toBeInTheDocument();
  });

  it("lets the user pick a method, including the learned track", () => {
    const onMethodChange = vi.fn();
    render(<PairPicker {...baseProps} onMethodChange={onMethodChange} />);
    fireEvent.click(screen.getByLabelText(/disk\+lightglue/i));
    expect(onMethodChange).toHaveBeenCalledWith("disk_lightglue");
  });

  it("submits the anchor, the chosen suggestion, and the current method when Match is clicked", () => {
    const onRunMatch = vi.fn();
    render(<PairPicker {...baseProps} method="akaze" onRunMatch={onRunMatch} />);
    fireEvent.click(screen.getByRole("button", { name: "Match" }));
    expect(onRunMatch).toHaveBeenCalledWith(baseProps.selectedId, SUGGESTION.product_id, "akaze");
  });

  it("disables the Match button when the suggestion has no staged raster", () => {
    render(<PairPicker {...baseProps} suggestions={[{ ...SUGGESTION, has_raster: false }]} />);
    expect(screen.getByRole("button", { name: "Match" })).toBeDisabled();
  });

  it("disables the Match button and relabels it while a job is running", () => {
    render(<PairPicker {...baseProps} running />);
    const button = screen.getByRole("button", { name: "Running..." });
    expect(button).toBeDisabled();
  });
});
