// jsdom has no real <canvas>/WebGL implementation, so these tests can only
// exercise MoonGlobe's no-WebGL fallback path -- the actual three.js scene
// (footprint placement, hover/click raycasting, highlight styling) is
// verified live against a real browser instead (see the project chat log
// for the Playwright screenshots taken during development). This test
// documents and pins the fallback behavior itself: the component must
// degrade gracefully rather than crash the page when WebGLRenderer
// construction throws, which is exactly what happens under jsdom.
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import MoonGlobe from "./MoonGlobe";

const PRODUCTS = [
  {
    product_id: "ch2_iir_nri_20211221t0324126144_d_img_hw1",
    instrument: "IIRS",
    solar_incidence_deg: 7.3,
    corners: { ul: [-15.5, -23.5], ur: [-15.5, -22.8], ll: [-0.2, -23.5], lr: [-0.2, -22.9] },
  },
];

describe("MoonGlobe", () => {
  it("degrades to a plain-text notice instead of crashing when WebGL is unavailable", () => {
    render(<MoonGlobe products={PRODUCTS} selectedId={null} onSelect={() => {}} />);
    expect(screen.getByText(/3D view unavailable/i)).toBeInTheDocument();
  });

  it("doesn't render the legend or canvas once it's fallen back", () => {
    const { container } = render(<MoonGlobe products={PRODUCTS} selectedId={null} onSelect={() => {}} />);
    expect(container.querySelector(".moon-globe-canvas")).not.toBeInTheDocument();
    expect(container.querySelector(".moon-globe-legend")).not.toBeInTheDocument();
  });

  it("handles an empty product list without throwing", () => {
    expect(() => render(<MoonGlobe products={[]} selectedId={null} onSelect={() => {}} />)).not.toThrow();
  });
});
