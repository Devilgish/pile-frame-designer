"""Угловые сварные швы примыканий балок (СП 16.13330.2017, 14.1.8, 14.1.16)."""

import pytest

from pile_frame.materials import STEELS
from pile_frame.sections import TUBE_40x40x3, TUBE_120x60x4
from pile_frame.welds import check_weld, electrode_issue, fillet_leg_mm


def test_weld_by_weld_metal_matches_hand_calculation():
    # Катет 4 мм, lw = 2·(120 − 10) = 220 мм, Э46: Rwf = 200, βf = 0,7.
    # βf·Rwf / (βz·Rwz) = 140 / (1,0·0,45·370) = 0,84 ≤ 1 → по металлу шва (176):
    # 17 240 / (0,7·4·220·200·1) = 0,140.
    weld = check_weld(17_240, TUBE_120x60x4, STEELS["С245"], "Э46")

    assert (weld.leg_mm, weld.length_mm) == (4, 220)
    assert weld.governing == "металл шва"
    assert weld.utilization == pytest.approx(0.140, abs=1e-3)


def test_fillet_leg_is_limited_by_thin_wall():
    # Катет не больше 1,2·t: для стенки 3 мм — 3 мм.
    assert fillet_leg_mm(TUBE_40x40x3) == 3
    assert fillet_leg_mm(TUBE_120x60x4) == 4


@pytest.mark.parametrize(
    ("electrode", "steel", "problem"),
    [
        ("Э42", "С245", True),  # 1,1·166,5 = 183,2 > 180
        ("Э46", "С245", False),  # 183,2 ≤ 200 ≤ 166,5 / 0,7 = 237,9
    ],
)
def test_electrode_must_satisfy_clause_14_1_8_for_manual_welding(electrode, steel, problem):
    issue = electrode_issue(STEELS[steel], electrode, thickness_mm=4)

    assert (issue is not None) is problem
    if problem:
        assert "14.1.8" in issue
