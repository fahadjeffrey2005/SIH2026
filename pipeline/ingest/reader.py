"""Load PDS4 image/cube data using `pdr`, paired with our own label parse.

We deliberately don't hardcode the pdr object key per instrument (e.g.
IIRS's cube currently surfaces as `SPECTRAL_QUBE_OBJECT`) because OHRC and
TMC-2 labels haven't been inspected yet and may use different object names.
Instead we pick the largest ndarray pdr hands back — robust to naming
differences, and correct as long as the label doesn't embed some other large
unrelated array (not expected for these single-image-object PDS4 products).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pdr

from .pds4_label import ProductLabel, parse_label


@dataclass
class Product:
    label: ProductLabel
    array: np.ndarray  # shape (lines, samples) for OHRC/TMC-2, (bands, lines, samples) for IIRS

    @property
    def is_cube(self) -> bool:
        return self.array.ndim == 3

    def band(self, index: int) -> np.ndarray:
        """A single 2D band. For a 2D product, `index` must be 0."""
        if self.is_cube:
            return self.array[index]
        if index != 0:
            raise IndexError(f"product {self.label.product_id} is not a cube; only band 0 exists")
        return self.array


def _largest_array(data: "pdr.Data") -> np.ndarray:
    best = None
    for key in data.keys():
        if key.lower() == "label":
            continue
        obj = data[key]
        if isinstance(obj, np.ndarray) and (best is None or obj.size > best.size):
            best = obj
    if best is None:
        raise ValueError("pdr did not return any ndarray image/cube object")
    return best


def load_product(xml_path: str | Path) -> Product:
    xml_path = Path(xml_path)
    label = parse_label(xml_path)
    data = pdr.read(str(xml_path))
    array = _largest_array(data)
    return Product(label=label, array=array)
