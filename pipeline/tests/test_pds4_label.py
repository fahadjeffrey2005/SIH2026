"""ingest.pds4_label: regression test for the corner-block-ambiguity bug.

OHRC/TMC-2 labels carry BOTH a System_Level_Coordinates block (onboard/
predicted attitude, less accurate) and a Refined_Corner_Coordinates block
(post-processed, more accurate) using identical leaf tag names. The first
implementation read the flat tag index and silently took the *first*
occurrence -- System_Level -- for every product. Fixed by walking the
actual element tree and explicitly preferring Refined. This test builds a
minimal synthetic label with deliberately different values in each block so
a regression can't hide behind "both blocks happen to agree" the way real
data might.
"""

from pathlib import Path

import pytest

from ingest.pds4_label import parse_label

LABEL_WITH_BOTH_BLOCKS = """<?xml version="1.0" encoding="UTF-8"?>
<Product_Observational xmlns="http://pds.nasa.gov/pds4/pds/v1"
                        xmlns:isda="https://isda.issdc.gov.in/pds4/isda/v1">
  <Identification_Area>
    <logical_identifier>urn:isro:isda:ch2_ohr.ohr:ch2_ohr_ncp_20210405t1606536730_d_img_d18</logical_identifier>
  </Identification_Area>
  <Observation_Area>
    <isda:Geometry_Orbit_Parameters>
      <isda:Coordinates>
        <isda:System_Level_Coordinates>
          <isda:upper_left_latitude>-2.600000</isda:upper_left_latitude>
          <isda:upper_left_longitude>336.400000</isda:upper_left_longitude>
          <isda:upper_right_latitude>-2.600000</isda:upper_right_latitude>
          <isda:upper_right_longitude>336.500000</isda:upper_right_longitude>
          <isda:lower_left_latitude>-3.400000</isda:lower_left_latitude>
          <isda:lower_left_longitude>336.400000</isda:lower_left_longitude>
          <isda:lower_right_latitude>-3.400000</isda:lower_right_latitude>
          <isda:lower_right_longitude>336.500000</isda:lower_right_longitude>
        </isda:System_Level_Coordinates>
        <isda:Refined_Corner_Coordinates>
          <isda:upper_left_latitude>-2.576048</isda:upper_left_latitude>
          <isda:upper_left_longitude>336.486234</isda:upper_left_longitude>
          <isda:upper_right_latitude>-2.579083</isda:upper_right_latitude>
          <isda:upper_right_longitude>336.589455</isda:upper_right_longitude>
          <isda:lower_left_latitude>-3.413866</isda:lower_left_latitude>
          <isda:lower_left_longitude>336.484646</isda:lower_left_longitude>
          <isda:lower_right_latitude>-3.416904</isda:lower_right_latitude>
          <isda:lower_right_longitude>336.587773</isda:lower_right_longitude>
        </isda:Refined_Corner_Coordinates>
      </isda:Coordinates>
    </isda:Geometry_Orbit_Parameters>
  </Observation_Area>
</Product_Observational>
"""

LABEL_SYSTEM_LEVEL_ONLY = LABEL_WITH_BOTH_BLOCKS.replace(
    "<isda:Refined_Corner_Coordinates>", "<isda:_Disabled_Refined>",
).replace(
    "</isda:Refined_Corner_Coordinates>", "</isda:_Disabled_Refined>",
)


def test_prefers_refined_over_system_level(tmp_path: Path):
    xml_path = tmp_path / "ch2_ohr_ncp_20210405T1606536730_d_img_d18.xml"
    xml_path.write_text(LABEL_WITH_BOTH_BLOCKS)

    label = parse_label(xml_path)

    assert label.corner_source == "refined"
    # The refined UL corner (336.486234 -> -23.513766 after -180..180 normalization),
    # not the system-level one (336.4 -> -23.6).
    assert label.corners["ul"] == pytest.approx((-2.576048, -23.513766))


def test_falls_back_to_system_level_when_no_refined_block(tmp_path: Path):
    xml_path = tmp_path / "ch2_iir_no_refined.xml"
    xml_path.write_text(LABEL_SYSTEM_LEVEL_ONLY)

    label = parse_label(xml_path)

    assert label.corner_source == "system_level"
    assert label.corners["ul"] == pytest.approx((-2.6, -23.6))


def test_instrument_inferred_from_product_id(tmp_path: Path):
    xml_path = tmp_path / "ch2_ohr_ncp_20210405T1606536730_d_img_d18.xml"
    xml_path.write_text(LABEL_WITH_BOTH_BLOCKS)

    label = parse_label(xml_path)

    assert label.instrument == "OHRC"
    assert label.product_id == "ch2_ohr_ncp_20210405t1606536730_d_img_d18"
