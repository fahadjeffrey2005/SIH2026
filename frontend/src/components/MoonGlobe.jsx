// Feature 2 (stretch goal, added after Feature 1): a small rotating 3D Moon
// that plots every real product's footprint quad at its true lat/lon
// (straight from the PDS4-derived corner coordinates GET /products already
// serves) and colors each patch by that product's own real solar-incidence
// angle -- the same number driving the "incidence gap" story in the metrics
// dashboard. The point isn't decoration: it's showing *where on the Moon*
// two overlapping footprints sit and *how differently lit* they were, which
// is the physical reason matching gets harder as the gap grows.
//
// Selecting a product in the catalog (or running/viewing a match) highlights
// the corresponding footprint(s) here too, via the `selectedId`/`pairIds`
// props -- this view and the rest of the app stay in sync.
//
// `showOverlay` (master on/off) and `visibleInstruments` (a Set of
// instrument names) let App.jsx's sidebar toggles hide the footprint layer
// entirely or by instrument, independent of the real base-map sphere --
// see the effect below that builds/tears down patch meshes.
//
// has_raster patches carry their own real, single-band Chandrayaan-2 image
// (buildPatchMesh) and normally show it tinted by solar-incidence angle for
// the zoomed-out overview; selecting/focusing one (the highlight effect
// below) drops the tint to true white so the actual grayscale pixels read
// correctly once you've zoomed in close enough to judge them.
//
// Honesty note (see the in-panel caption too): the sphere's own shading
// comes from one fixed decorative light, not each product's actual
// sun-elevation/azimuth -- reconstructing a true per-product illumination
// direction on the globe was scoped out as a stretch-on-a-stretch (see the
// project chat log). The colored patches are the real, data-driven part;
// the base surface (see moon_diffuse.jpg below) is real too, just not real
// *lighting* -- the lit-sphere look is decorative shading on top of a real map.
//
// moon_diffuse.jpg is NASA's own LROC (Lunar Reconnaissance Orbiter Camera)
// global color mosaic (2048x1024 equirectangular, "lroc_color_2k.jpg" from
// NASA's Scientific Visualization Studio CGI Moon Kit, svs.gsfc.nasa.gov/4720
// -- US government work, public domain, credit: NASA's Scientific
// Visualization Studio), not a procedural placeholder -- swap it for a
// higher-resolution version from the same kit (4k/8k/16k TIFFs are
// available there) by replacing this one file; nothing else needs to
// change, since latLonToVector3's phi/theta convention already matches
// three.js's default SphereGeometry UV unwrap (north pole at v=1/image
// top, lon=-180 at u=0/image left edge -- the standard convention for this
// kind of map, see moonGlobeMath.js's docstring).

import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

import { productBrowseUrl } from "../api";
import moonTextureUrl from "../assets/moon_diffuse.jpg";
import { exaggerateCorners, footprintPatchGeometry, footprintPatchVertices, hasFullFootprint, incidenceColor } from "./moonGlobeMath";

const MOON_RADIUS = 1;
const PATCH_RADIUS = MOON_RADIUS * 1.004; // lifted slightly off the surface to avoid z-fighting
const INSTRUMENT_LABEL = { OHRC: "OHRC", "TMC-2": "TMC-2", IIRS: "IIRS" };

// How close the camera can get / where a click-to-focus flight ends up.
// MIN_CAMERA_DISTANCE is deliberately just above PATCH_RADIUS -- close
// enough that a real-image patch fills most of the frame for pixel-level
// inspection (the whole point of draping real Chandrayaan-2 photos on).
// FOCUS_DISTANCE is a little further out than that floor, so clicking a
// patch gives an immediately-readable close-up with the rest of the globe
// still for context, and scrolling in further reaches true max zoom.
const MIN_CAMERA_DISTANCE = 1.03;
const MAX_CAMERA_DISTANCE = 5;
const FOCUS_DISTANCE = 1.12;
const FLIGHT_DURATION_MS = 650;
const easeInOutQuad = (t) => (t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2);

function buildPatchMesh(product, maxAnisotropy) {
  // Real footprints are tiny next to the whole Moon (some under 1 degree
  // across) -- exaggerate for visibility, same idea as an orrery drawing
  // planets oversized. See moonGlobeMath.js's exaggerateCorners docstring.
  const exaggerated = exaggerateCorners(product.corners);
  const geometry = new THREE.BufferGeometry();

  // has_raster products get their own real Chandrayaan-2 image draped onto
  // the patch (GET /products/{id}/browse) rather than a flat color fill --
  // footprintPatchGeometry (not the plain-positions footprintPatchVertices)
  // also emits the matching UV per vertex for this. The other 4 products'
  // raw zips aren't unpacked past their PDS4 labels yet, so there's no real
  // pixel data to show for them -- they keep the flat color fill.
  let texture = null;
  if (product.has_raster) {
    const { positions, uvs } = footprintPatchGeometry(exaggerated, PATCH_RADIUS);
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
    geometry.setAttribute("uv", new THREE.Float32BufferAttribute(uvs, 2));
    texture = new THREE.TextureLoader().load(productBrowseUrl(product.product_id));
    texture.colorSpace = THREE.SRGBColorSpace;
    // These patches are long, thin, near-grazing-angle swaths (a TMC-2
    // strip can be 35-48deg long but under 1deg wide) -- viewed obliquely
    // on the curved globe, plain bilinear filtering blurs them far more
    // than a straight-on texture would, on top of whatever detail the
    // backend's own long-side resize already gave up (see
    // backend/app/routers/products.py's _GLOBE_TEXTURE_MAX_SIDE comment).
    // Anisotropic filtering samples along the view-angle-stretched axis
    // instead of averaging it away, which is exactly this case.
    if (maxAnisotropy) texture.anisotropy = maxAnisotropy;
  } else {
    const verts = footprintPatchVertices(exaggerated, PATCH_RADIUS);
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(verts, 3));
  }
  geometry.computeVertexNormals();

  // Every one of these source images is a single-band panchromatic (or
  // grayscale IIRS browse) frame, not a color photo -- so multiplying it by
  // the incidence-angle tint (MeshBasicMaterial multiplies `map` by `color`)
  // doesn't read as "a real photo with a colored cast," it reads as "a
  // washed-out gradient," especially once you're zoomed in close enough to
  // actually judge real detail. Keep the tint for the at-a-glance,
  // zoomed-out overview (it's genuinely useful there -- see the legend), but
  // the highlight effect below switches it to white (no tint) the moment a
  // has_raster patch is selected/focused, so inspecting real pixels shows
  // the real grayscale image, not a colorized one. tintColor is stashed on
  // the mesh so that effect can restore it on deselect.
  const tintColor = incidenceColor(product.solar_incidence_deg);
  const material = new THREE.MeshBasicMaterial({
    color: tintColor,
    map: texture,
    side: THREE.DoubleSide,
    transparent: true,
    opacity: 0.82,
    depthWrite: false,
  });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.renderOrder = 1;
  mesh.userData.productId = product.product_id;
  mesh.userData.tintColor = tintColor;
  mesh.userData.hasTexture = !!texture;

  // A subdivided (curved) patch has internal grid-cell edges that aren't
  // perfectly coplanar with their neighbors -- EdgesGeometry's default 1deg
  // threshold treats those as "creases" too, drawing the whole internal
  // grid instead of just the patch's true outer boundary. A high threshold
  // keeps only genuine boundary edges (always included regardless of
  // angle, since they belong to a single triangle) plus any real crease.
  const outlineGeom = new THREE.EdgesGeometry(geometry, 89);
  const outline = new THREE.LineSegments(
    outlineGeom,
    new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0 })
  );
  outline.renderOrder = 2;
  mesh.add(outline);
  mesh.userData.outline = outline;

  return mesh;
}

export default function MoonGlobe({ products, selectedId, onSelect, pairIds, showOverlay = true, visibleInstruments }) {
  const containerRef = useRef(null);
  const stateRef = useRef(null); // holds all mutable three.js objects across renders
  const [hovered, setHovered] = useState(null); // { product, x, y }
  // WebGL isn't universal (older browsers, some locked-down corporate
  // machines, and -- relevantly for this codebase -- jsdom in the frontend
  // test suite all lack it). Rather than let a WebGLRenderer construction
  // error take the whole page down, degrade to a plain-text notice: the
  // rest of the app (catalog, matching, metrics dashboard) works fine
  // without this panel.
  const [unavailable, setUnavailable] = useState(false);

  // --- one-time scene setup -------------------------------------------------
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return undefined;

    let renderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true });
    } catch {
      setUnavailable(true);
      return undefined;
    }

    const scene = new THREE.Scene();
    // near=0.1 would clip the sphere's own surface once the camera gets
    // close to MIN_CAMERA_DISTANCE (1.03, only ~0.026 units above the
    // radius-1 surface): anything directly ahead nearer than the near
    // plane simply isn't rendered, which at that distance is the very
    // thing the user zoomed in to see.
    const camera = new THREE.PerspectiveCamera(45, 1, 0.01, 100);
    camera.position.set(0, 0.6, 2.6);

    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.minDistance = MIN_CAMERA_DISTANCE;
    controls.maxDistance = MAX_CAMERA_DISTANCE;
    controls.enablePan = false;
    controls.autoRotate = true;
    controls.autoRotateSpeed = 0.5;
    // Auto-rotate is a nice idle state, but actively fighting a user who's
    // zoomed in to inspect a patch is not -- stop it for good the moment
    // they touch the view (rotate, zoom, or a click-to-focus flight below).
    controls.addEventListener("start", () => {
      controls.autoRotate = false;
    });

    scene.add(new THREE.AmbientLight(0xffffff, 0.55));
    const sun = new THREE.DirectionalLight(0xfff4e0, 1.1);
    sun.position.set(4, 2, 3);
    scene.add(sun);

    const texture = new THREE.TextureLoader().load(moonTextureUrl);
    texture.colorSpace = THREE.SRGBColorSpace;
    const moon = new THREE.Mesh(
      new THREE.SphereGeometry(MOON_RADIUS, 64, 48),
      new THREE.MeshStandardMaterial({ map: texture, roughness: 1, metalness: 0 })
    );
    scene.add(moon);

    const stars = new THREE.Points(
      new THREE.BufferGeometry().setAttribute(
        "position",
        new THREE.Float32BufferAttribute(
          Array.from({ length: 600 * 3 }, () => (Math.random() - 0.5) * 40),
          3
        )
      ),
      new THREE.PointsMaterial({ color: 0xffffff, size: 0.02, sizeAttenuation: true })
    );
    scene.add(stars);

    const raycaster = new THREE.Raycaster();
    const pointerNdc = new THREE.Vector2();
    const meshes = new Map();

    const state = { scene, camera, renderer, controls, meshes, raycaster, pointerNdc, container, flight: null };
    stateRef.current = state;

    let frameId;
    const animate = () => {
      frameId = requestAnimationFrame(animate);
      if (state.flight) {
        const t = Math.min(1, (performance.now() - state.flight.start) / FLIGHT_DURATION_MS);
        const eased = easeInOutQuad(t);
        camera.position.lerpVectors(state.flight.from, state.flight.to, eased);
        camera.lookAt(0, 0, 0);
        if (t >= 1) state.flight = null;
      }
      controls.update();
      renderer.render(scene, camera);
    };
    animate();

    const resize = () => {
      const { clientWidth: w, clientHeight: h } = container;
      if (w === 0 || h === 0) return;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    };
    resize();
    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(container);

    const onPointerMove = (e) => {
      const rect = renderer.domElement.getBoundingClientRect();
      pointerNdc.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      pointerNdc.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(pointerNdc, camera);
      const hits = raycaster.intersectObjects([...meshes.values()], false);
      if (hits.length > 0) {
        const productId = hits[0].object.userData.productId;
        setHovered({ productId, x: e.clientX, y: e.clientY });
      } else {
        setHovered(null);
      }
    };
    const onPointerLeave = () => setHovered(null);
    const onClick = () => {
      const hits = raycaster.intersectObjects([...meshes.values()], false);
      if (hits.length === 0) return;
      onSelect?.(hits[0].object.userData.productId);
      // Fly the camera in toward exactly where the click landed on the
      // patch (not just "some point on this product"), so a long swath
      // clicked near one end focuses there rather than jumping to its
      // centroid. Keeps looking at the Moon's center throughout -- only
      // the camera's distance and angle change.
      const direction = hits[0].point.clone().normalize();
      state.flight = {
        from: camera.position.clone(),
        to: direction.multiplyScalar(FOCUS_DISTANCE),
        start: performance.now(),
      };
    };
    renderer.domElement.addEventListener("pointermove", onPointerMove);
    renderer.domElement.addEventListener("pointerleave", onPointerLeave);
    renderer.domElement.addEventListener("click", onClick);

    return () => {
      cancelAnimationFrame(frameId);
      resizeObserver.disconnect();
      renderer.domElement.removeEventListener("pointermove", onPointerMove);
      renderer.domElement.removeEventListener("pointerleave", onPointerLeave);
      renderer.domElement.removeEventListener("click", onClick);
      controls.dispose();
      scene.traverse((obj) => {
        obj.geometry?.dispose();
        if (obj.material) {
          (Array.isArray(obj.material) ? obj.material : [obj.material]).forEach((m) => {
            m.map?.dispose(); // each has_raster patch's own real-image texture (buildPatchMesh)
            m.dispose();
          });
        }
      });
      texture.dispose();
      renderer.dispose();
      container.removeChild(renderer.domElement);
      stateRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // scene is built once; product/selection changes are handled below without a rebuild

  // --- keep footprint meshes in sync with the `products` prop ---------------
  // Also honors the sidebar's overlay toggles (App.jsx): `showOverlay` hides
  // every patch at once (master switch), `visibleInstruments` (a Set of
  // instrument names, e.g. {"OHRC","TMC-2"}) hides patches instrument by
  // instrument -- both work by simply shrinking the "wanted" set below, so
  // toggling either off disposes the now-unwanted meshes exactly the way
  // removing a product from `products` already did, and toggling back on
  // rebuilds them fresh (re-fetching a has_raster product's real photo, a
  // deliberate simplicity/cache-freshness tradeoff over keeping hidden
  // meshes around).
  useEffect(() => {
    const s = stateRef.current;
    if (!s) return;
    const wanted = new Set();
    if (showOverlay) {
      for (const product of products || []) {
        if (!hasFullFootprint(product.corners)) continue;
        if (visibleInstruments && !visibleInstruments.has(product.instrument)) continue;
        wanted.add(product.product_id);
        if (!s.meshes.has(product.product_id)) {
          const mesh = buildPatchMesh(product, s.renderer.capabilities.getMaxAnisotropy());
          s.scene.add(mesh);
          s.meshes.set(product.product_id, mesh);
        }
      }
    }
    for (const [id, mesh] of [...s.meshes.entries()]) {
      if (!wanted.has(id)) {
        s.scene.remove(mesh);
        mesh.geometry.dispose();
        mesh.material.map?.dispose();
        mesh.material.dispose();
        s.meshes.delete(id);
      }
    }
  }, [products, showOverlay, visibleInstruments]);

  // --- highlight styling: selected product / an active pair -----------------
  useEffect(() => {
    const s = stateRef.current;
    if (!s) return;
    const pairSet = new Set(pairIds || []);
    for (const [id, mesh] of s.meshes.entries()) {
      const inPair = pairSet.has(id);
      const isSelected = id === selectedId;
      const outline = mesh.userData.outline;
      if (inPair || isSelected) {
        mesh.material.opacity = 1;
        // Drop the incidence-color tint the moment a has_raster patch is
        // focused -- see buildPatchMesh's comment: this is the "zoomed in
        // to actually look at the pixels" moment, and the real (grayscale)
        // image should show true, not multiplied by a blue wash.
        if (mesh.userData.hasTexture) mesh.material.color.set(0xffffff);
        outline.material.color.set(inPair ? 0xff7a18 : 0xffffff);
        outline.material.opacity = 1;
        outline.material.linewidth = 2;
      } else {
        mesh.material.opacity = 0.82;
        if (mesh.userData.hasTexture) mesh.material.color.set(mesh.userData.tintColor);
        outline.material.opacity = 0;
      }
    }
  }, [selectedId, pairIds, products]);

  const hoveredProduct = hovered && (products || []).find((p) => p.product_id === hovered.productId);

  if (unavailable) {
    return (
      <div className="moon-globe-wrap">
        <p className="muted small">
          3D view unavailable -- this browser (or environment) doesn't support WebGL. The rest of
          the app works normally without it.
        </p>
      </div>
    );
  }

  return (
    <div className="moon-globe-wrap">
      <div className="moon-globe-canvas" ref={containerRef} />
      <div className="moon-globe-legend">
        <span className="muted small">Sun-incidence angle</span>
        <div className="moon-globe-legend-bar" />
        <div className="moon-globe-legend-labels muted small">
          <span>0&deg; (overhead)</span>
          <span>90&deg; (grazing)</span>
        </div>
      </div>
      {hoveredProduct && (
        <div
          className="moon-globe-tooltip"
          style={{ left: hovered.x + 14, top: hovered.y + 14 }}
        >
          <div className="mono small">{hoveredProduct.product_id}</div>
          <div className="small">{INSTRUMENT_LABEL[hoveredProduct.instrument] || hoveredProduct.instrument}</div>
          {hoveredProduct.solar_incidence_deg != null && (
            <div className="small">incidence {hoveredProduct.solar_incidence_deg.toFixed(1)}&deg;</div>
          )}
          <div className="muted small">click to select</div>
        </div>
      )}
    </div>
  );
}
