"""Parse ISRO Chandrayaan-2 PDS4 XML labels (OHRC / TMC-2 / IIRS).

ISSDC's PDS4 labels use a mix of the standard PDS4 namespace and an
ISRO-specific `isda:` extension namespace for mission fields (sun angles,
orbit numbers, footprint corners, ...). Different instruments' labels are
not guaranteed to use identical tag sets, so this parser is deliberately
permissive: it indexes every leaf element by its *local* tag name (namespace
stripped) into a dict-of-lists, then exposes the handful of fields we know
we need as convenience properties on top of that raw index. Anything not
covered by a convenience property is still reachable via `label.raw`.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from lxml import etree

INSTRUMENT_BY_PREFIX = {
    "ohr": "OHRC",
    "tmc": "TMC-2",
    "iir": "IIRS",
    "hys": "IIRS",  # Chandrayaan-1 HySI, same family
    "sar": "SAR",
}


def _local(tag: str) -> str:
    """Strip a `{namespace}tag` clark-notation tag down to its local name."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _text(el) -> Optional[str]:
    if el.text is None:
        return None
    t = el.text.strip()
    return t or None


def _as_float(v: Optional[str]) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except ValueError:
        return None


@dataclass
class AxisInfo:
    axis_name: str
    elements: int
    sequence_number: int


@dataclass
class ProductLabel:
    xml_path: Path
    product_id: str
    instrument: str
    raw: dict = field(repr=False, default_factory=dict)

    # ---- convenience accessors over `raw` ------------------------------

    def _get(self, name: str) -> Optional[str]:
        vals = self.raw.get(name)
        return vals[0] if vals else None

    def _get_float(self, name: str) -> Optional[float]:
        return _as_float(self._get(name))

    @property
    def start_time(self) -> Optional[str]:
        return self._get("start_date_time")

    @property
    def stop_time(self) -> Optional[str]:
        return self._get("stop_date_time")

    @property
    def orbit_number(self) -> Optional[int]:
        v = self._get("imaging_orbit_number") or self._get("orbit_number")
        return int(v) if v is not None else None

    @property
    def spacecraft_altitude_km(self) -> Optional[float]:
        return self._get_float("spacecraft_altitude")

    # Sun / illumination geometry — the key fields for this project.
    # NOTE: these live in the PDS4 label itself and are populated even though
    # the ISSDC map-browse catalog's WFS fields (INC_ANGLE/EMI_ANGLE/PHA_ANGLE)
    # are not. Always prefer these over any catalog-level angle field.
    @property
    def sun_azimuth_deg(self) -> Optional[float]:
        return self._get_float("sun_azimuth")

    @property
    def sun_elevation_deg(self) -> Optional[float]:
        return self._get_float("sun_elevation")

    @property
    def solar_incidence_deg(self) -> Optional[float]:
        return self._get_float("solar_incidence") or self._get_float("incidence_angle")

    @property
    def emission_angle_deg(self) -> Optional[float]:
        return self._get_float("emission_angle")

    @property
    def phase_angle_deg(self) -> Optional[float]:
        return self._get_float("phase_angle")

    @property
    def has_sun_angle_metadata(self) -> bool:
        return any(
            v is not None
            for v in (self.sun_azimuth_deg, self.sun_elevation_deg, self.solar_incidence_deg)
        )

    # Footprint corners (degrees, lon normalized to -180..180). Computed once
    # in `parse_label` (see `_extract_corners`) and stored in these fields,
    # because OHRC/TMC-2 labels carry TWO corner blocks --
    # `System_Level_Coordinates` (onboard/predicted attitude) and
    # `Refined_Corner_Coordinates` (post-processed, more accurate) -- using
    # identical leaf tag names, so the flat `raw` index alone can't
    # distinguish them. `_extract_corners` resolves this by walking the
    # actual element tree and preferring Refined over System-Level.
    corners: dict = field(default_factory=dict)
    corner_source: Optional[str] = None  # 'refined' | 'system_level' | 'flat' | None

    @property
    def axes(self) -> list[AxisInfo]:
        """Axis_Array entries in document order (band/line/sample dimensions)."""
        names = self.raw.get("axis_name", [])
        elements = self.raw.get("elements", [])
        seqs = self.raw.get("sequence_number", [])
        out = []
        for n, e, s in zip(names, elements, seqs):
            try:
                out.append(AxisInfo(axis_name=n, elements=int(e), sequence_number=int(s)))
            except (TypeError, ValueError):
                continue
        return out


def normalize_lon(lon_deg: float) -> float:
    """PDS4 labels use 0-360 East longitude; normalize to -180..180."""
    lon = lon_deg % 360.0
    return lon - 360.0 if lon > 180.0 else lon


_CORNER_KEYS = {
    "ul": ("upper_left_latitude", "upper_left_longitude"),
    "ur": ("upper_right_latitude", "upper_right_longitude"),
    "ll": ("lower_left_latitude", "lower_left_longitude"),
    "lr": ("lower_right_latitude", "lower_right_longitude"),
}


def _read_corner_block(container_el) -> Optional[dict]:
    """Read the 8 corner lat/lon leaves directly under one container element."""
    vals: dict[str, float] = {}
    for el in container_el:
        name = _local(el.tag)
        f = _as_float(_text(el))
        if f is not None:
            vals[name] = f
    if not any(k in vals for pair in _CORNER_KEYS.values() for k in pair):
        return None
    out = {}
    for corner, (lat_key, lon_key) in _CORNER_KEYS.items():
        if lat_key in vals and lon_key in vals:
            out[corner] = (vals[lat_key], normalize_lon(vals[lon_key]))
    return out or None


def _extract_corners(root) -> tuple[dict, Optional[str]]:
    """Prefer Refined_Corner_Coordinates, then System_Level_Coordinates, then
    any single unlabeled corner block (IIRS labels only have one)."""
    refined = system_level = generic = None
    for el in root.iter():
        local = _local(el.tag)
        if local == "Refined_Corner_Coordinates" and refined is None:
            refined = _read_corner_block(el)
        elif local == "System_Level_Coordinates" and system_level is None:
            system_level = _read_corner_block(el)
        elif local in ("Geometry_Parameters", "Geometry") and generic is None:
            block = _read_corner_block(el)
            if block:
                generic = block
    if refined:
        return refined, "refined"
    if system_level:
        return system_level, "system_level"
    if generic:
        return generic, "flat"
    return {}, None


def infer_instrument(product_id: str) -> str:
    parts = product_id.lower().split("_")
    mid_prefix = parts[1] if len(parts) > 1 else ""
    return INSTRUMENT_BY_PREFIX.get(mid_prefix, "UNKNOWN")


def parse_label(xml_path: str | Path) -> ProductLabel:
    xml_path = Path(xml_path)
    tree = etree.parse(str(xml_path))
    root = tree.getroot()

    raw: dict[str, list[str]] = defaultdict(list)
    for el in root.iter():
        if len(el) > 0:
            continue  # skip container elements, we only want leaves
        text = _text(el)
        if text is not None:
            raw[_local(el.tag)].append(text)

    # product_id: prefer the logical_identifier's final path segment, fall back
    # to the filename stem.
    lid = raw.get("logical_identifier", [None])[0]
    if lid:
        product_id = lid.rsplit(":", 1)[-1]
    else:
        product_id = xml_path.stem

    corners, corner_source = _extract_corners(root)

    return ProductLabel(
        xml_path=xml_path,
        product_id=product_id,
        instrument=infer_instrument(product_id),
        raw=dict(raw),
        corners=corners,
        corner_source=corner_source,
    )
