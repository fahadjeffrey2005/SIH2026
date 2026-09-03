import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import ResultsView from "./ResultsView";

const DONE_JOB = {
  product_a: "ch2_iir_nri_20211221t0324126144_d_img_hw1",
  product_b: "ch2_tmc_ncf_20240125t0622476078_d_img_d18",
  method: "sift",
  status: "done",
  overlayUrl: "http://localhost:8000/match/j1/overlay",
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
};

describe("ResultsView", () => {
  it("prompts to run a match before any job exists", () => {
    render(<ResultsView job={null} error={null} />);
    expect(screen.getByText(/run a match from the pair picker/i)).toBeInTheDocument();
  });

  it("surfaces a submission error instead of a stale/blank panel", () => {
    render(<ResultsView job={null} error="500 backend exploded" />);
    expect(screen.getByText("500 backend exploded")).toBeInTheDocument();
  });

  it("shows the job's status while it's still running, with no result section yet", () => {
    render(<ResultsView job={{ product_a: "a", product_b: "b", method: "sift", status: "running" }} error={null} />);
    expect(screen.getByText("running")).toBeInTheDocument();
    expect(screen.queryByText(/ransac inliers/i)).not.toBeInTheDocument();
  });

  it("shows the job's own error message on failure, not a generic one", () => {
    render(<ResultsView job={{ product_a: "a", product_b: "b", method: "sift", status: "failed", error: "no overlap found" }} error={null} />);
    expect(screen.getByText("no overlap found")).toBeInTheDocument();
  });

  it("renders real metrics and the geolocation-agreement figure once a job is done", () => {
    render(<ResultsView job={DONE_JOB} error={null} />);
    expect(screen.getByText("8000 / 4207")).toBeInTheDocument();
    expect(screen.getByText("7")).toBeInTheDocument();
    expect(screen.getByText("28%")).toBeInTheDocument();
    expect(screen.getByText(/186,680 m median \(n=7\)/)).toBeInTheDocument();
    expect(screen.getByAltText("match overlay")).toHaveAttribute("src", DONE_JOB.overlayUrl);
  });

  it("reports a zero-inlier result as a real finding, not a hidden failure", () => {
    const job = { ...DONE_JOB, result: { ...DONE_JOB.result, inliers: 0, inlier_ratio: 0, geoloc_error_median_m: null, geoloc_error_n: 0 } };
    render(<ResultsView job={job} error={null} />);
    expect(screen.getByText(/zero inliers is itself a real, reportable result/i)).toBeInTheDocument();
    expect(screen.getByText(/n\/a \(no inliers\)/)).toBeInTheDocument();
  });
});
