// jsdom never actually decodes <img> sources, so naturalWidth/naturalHeight
// stay 0 until we stub them and fire a real 'load' event -- the same
// pattern any image-dependent component needs under jsdom. Production
// behavior (a real browser firing onLoad with the real decoded size) needs
// no such stub; this is purely a test-environment gap, not a component
// design compromise.
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import CorrespondenceViewer from "./CorrespondenceViewer";

function loadImages(container, { width = 400, height = 300 } = {}) {
  for (const img of container.querySelectorAll("img")) {
    Object.defineProperty(img, "naturalWidth", { value: width, configurable: true });
    Object.defineProperty(img, "naturalHeight", { value: height, configurable: true });
    fireEvent.load(img);
  }
}

const SIFT_ROW = {
  method: "sift",
  product_a: "ch2_iir_nri_20211221t0324126144_d_img_hw1",
  product_b: "ch2_tmc_ncf_20240125t0622476078_d_img_d18",
  points_a: [[10, 20], [30, 40]],
  points_b: [[15, 25], [35, 45]],
  point_geoloc_errors_m: [1234.5, 6789.1],
};

const DISK_ROW = {
  method: "disk_lightglue",
  product_a: "ch2_iir_nri_20211221t0324126144_d_img_hw1",
  product_b: "ch2_tmc_ncf_20240125t0622476078_d_img_d18",
  points_a: [],
  points_b: [],
  point_geoloc_errors_m: [],
  keypoint_budget_comparison: {
    old: { max_keypoints: 2048, raw_matches: 23, inliers: 0, inlier_ratio: 0, geoloc_median_m: null, points_a: [], points_b: [] },
    new: { max_keypoints: 4096, raw_matches: 11, inliers: 4, inlier_ratio: 0.36, geoloc_median_m: 230124.4, points_a: [[1, 2], [3, 4], [5, 6], [7, 8]], points_b: [[2, 3], [4, 5], [6, 7], [8, 9]] },
  },
};

describe("CorrespondenceViewer", () => {
  it("draws one point per inlier on each side once the images load", () => {
    const { container } = render(<CorrespondenceViewer row={SIFT_ROW} imageAUrl="a.png" imageBUrl="b.png" />);
    loadImages(container);
    expect(screen.getByTestId("match-point-a-0")).toBeInTheDocument();
    expect(screen.getByTestId("match-point-a-1")).toBeInTheDocument();
    expect(screen.getByTestId("match-point-b-0")).toBeInTheDocument();
    expect(screen.getByTestId("match-point-b-1")).toBeInTheDocument();
  });

  it("hovering a point on one side highlights the same index on both sides and shows its own geoloc distance", () => {
    const { container } = render(<CorrespondenceViewer row={SIFT_ROW} imageAUrl="a.png" imageBUrl="b.png" />);
    loadImages(container);

    fireEvent.mouseEnter(screen.getByTestId("match-point-a-1"));

    expect(screen.getByTestId("match-point-a-1")).toHaveClass("match-point-active");
    expect(screen.getByTestId("match-point-b-1")).toHaveClass("match-point-active");
    expect(screen.getByTestId("match-point-a-0")).not.toHaveClass("match-point-active");
    expect(screen.getByText(/6,789 m geolocation disagreement/)).toBeInTheDocument();

    fireEvent.mouseLeave(screen.getByTestId("match-point-a-1"));
    expect(screen.queryByText(/geolocation disagreement/)).not.toBeInTheDocument();
  });

  it("says plainly when there are no inliers to show, instead of an empty viewer", () => {
    render(<CorrespondenceViewer row={{ ...SIFT_ROW, points_a: [], points_b: [] }} imageAUrl="a.png" imageBUrl="b.png" />);
    expect(screen.getByText(/no inliers to show/i)).toBeInTheDocument();
  });

  it("shows a keypoint-budget toggle only for disk_lightglue rows, defaulting to the fixed (4096) variant", () => {
    render(<CorrespondenceViewer row={DISK_ROW} imageAUrl="a.png" imageBUrl="b.png" />);
    expect(screen.getByText("4096 (fixed)")).toBeInTheDocument();
    expect(screen.getByText("2048 (original)")).toBeInTheDocument();
    // Defaults to "new" (4096), which has 4 real inliers -- not the empty top-level row.
    expect(screen.getByText(/4 inliers, 36% ratio/)).toBeInTheDocument();
  });

  it("switching the toggle to the original budget redraws the real pre-fix (zero-inlier) result", () => {
    const { container } = render(<CorrespondenceViewer row={DISK_ROW} imageAUrl="a.png" imageBUrl="b.png" />);
    loadImages(container);
    expect(screen.getByTestId("match-point-a-0")).toBeInTheDocument();

    fireEvent.click(screen.getByText("2048 (original)"));

    expect(screen.getByText(/0 inliers/)).toBeInTheDocument();
    expect(screen.getByText(/no inliers to show/i)).toBeInTheDocument();
    expect(screen.queryByTestId("match-point-a-0")).not.toBeInTheDocument();
  });

  it("does not show a keypoint-budget toggle for classical methods", () => {
    render(<CorrespondenceViewer row={SIFT_ROW} imageAUrl="a.png" imageBUrl="b.png" />);
    expect(screen.queryByText(/keypoint budget/i)).not.toBeInTheDocument();
  });

  it("zoom controls change the pane's transform scale", () => {
    const { container } = render(<CorrespondenceViewer row={SIFT_ROW} imageAUrl="a.png" imageBUrl="b.png" />);
    loadImages(container);
    const zoomInButtons = screen.getAllByLabelText("Zoom in");
    const content = container.querySelectorAll(".zoom-pane-content")[0];
    expect(content.style.transform).toContain("scale(1)");

    fireEvent.click(zoomInButtons[0]);
    expect(content.style.transform).toContain("scale(1.25)");
  });
});
