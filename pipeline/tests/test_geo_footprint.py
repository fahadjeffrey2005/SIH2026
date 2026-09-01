"""geo.footprint: spherical point-in-quad overlap geometry.

The two "real data" tests below pin down an actual finding from this
project's data-acquisition phase: OHRC's 2021-04-05 scene does NOT overlap
TMC-2's 2024-01-25 scene, even though every other cross-instrument pair at
this site does. That was originally mistaken for a bug (see git history /
docs/baseline_results.md) -- confirmed genuine via a boundary-nudge check.
These tests encode that check permanently so a future change to the overlap
math can't silently reintroduce either failure mode (falsely calling this
pair "overlapping", or breaking the pairs that genuinely do overlap).
"""

from geo.footprint import Footprint, bbox_overlap, quads_overlap, spherical_point_in_quad

# Real corner coordinates from data/catalog.sqlite (PDS4 label Refined_Corner_Coordinates).
OHRC_2021 = Footprint("ohrc_2021", {
    "ul": (-2.576048, -23.513766),
    "ur": (-2.579083, -23.410545),
    "ll": (-3.413866, -23.515354),
    "lr": (-3.416904, -23.412227),
})
TMC2_2024 = Footprint("tmc2_2024", {
    "ul": (-20.275705, -23.112805),
    "ur": (-20.287889, -23.753295),
    "ll": (14.461747, -23.910689),
    "lr": (14.450336, -24.513836),
})
TMC2_2025 = Footprint("tmc2_2025", {
    "ul": (43.095893, -20.838351),
    "ur": (43.131132, -22.015005),
    "ll": (-4.962184, -22.957478),
    "lr": (-4.93821, -23.761254),
})
IIRS_2021 = Footprint("iirs_2021", {
    "ul": (-15.529913, -23.454591),
    "ur": (-15.527481, -22.843433),
    "ll": (-0.239028, -23.515014),
    "lr": (-0.236739, -22.945892),
})


def test_ohrc_2021_does_not_overlap_tmc2_2024():
    """The genuine near-miss: bboxes overlap, but OHRC's footprint sits
    entirely east of TMC-2 2024's actual swath at that latitude."""
    assert bbox_overlap(OHRC_2021, TMC2_2024) is True
    assert quads_overlap(OHRC_2021, TMC2_2024) is False


def test_ohrc_2021_overlaps_tmc2_2025():
    """Same OHRC scene, different TMC-2 date -- this pair genuinely does
    overlap. Guards against a fix for the case above becoming so
    conservative it breaks real overlaps too."""
    assert quads_overlap(OHRC_2021, TMC2_2025) is True


def test_iirs_overlaps_all_others_at_this_site():
    assert quads_overlap(IIRS_2021, OHRC_2021) is True
    assert quads_overlap(IIRS_2021, TMC2_2024) is True
    assert quads_overlap(IIRS_2021, TMC2_2025) is True


def test_boundary_nudge_flips_containment():
    """Sanity check on spherical_point_in_quad itself: a point clearly on
    the far (west) side of a quad's near edge is contained, a point clearly
    on the near (east) side is not. This is the same manual check used to
    confirm the near-miss above is real geometry and not a bug in this
    function -- TMC-2 2024's strip, evaluated at OHRC's latitude, has its
    near edge at ~lon -23.53 (scanned by hand; see docs/baseline_results.md
    / project history), so +/-0.1 deg gives a safe margin either side.
    """
    probe_lat = OHRC_2021.corners["ul"][0]
    quad = TMC2_2024.ordered_quad
    just_inside = (probe_lat, -23.65)  # west of the edge -> inside TMC-2's swath
    just_outside = (probe_lat, -23.40)  # east of the edge -> outside (OHRC's own side)
    assert spherical_point_in_quad(just_inside, quad) is True
    assert spherical_point_in_quad(just_outside, quad) is False


def test_bbox_overlap_disjoint():
    a = Footprint("a", {"ul": (10, 10), "ur": (10, 11), "ll": (9, 10), "lr": (9, 11)})
    b = Footprint("b", {"ul": (-10, -10), "ur": (-10, -9), "ll": (-11, -10), "lr": (-11, -9)})
    assert bbox_overlap(a, b) is False
    assert quads_overlap(a, b) is False


def test_quads_overlap_nested():
    """A small quad entirely inside a larger one overlaps."""
    outer = Footprint("outer", {"ul": (10, -10), "ur": (10, 10), "ll": (-10, -10), "lr": (-10, 10)})
    inner = Footprint("inner", {"ul": (1, -1), "ur": (1, 1), "ll": (-1, -1), "lr": (-1, 1)})
    assert quads_overlap(outer, inner) is True
    assert quads_overlap(inner, outer) is True
