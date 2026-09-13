"""Местная устойчивость стенок и поясных листов замкнутых профилей (СП 16.13330.2017, 8.5)."""

import pytest

from pile_frame.sections import Section, TUBE_120x60x4
from pile_frame.stability import check_local_stability


def _tube(height, width, thickness):
    # Для устойчивости важны только размеры; остальные характеристики условные.
    return Section(f"{height}×{width}×{thickness}", height, width, thickness, 1.0, 1.0, 100.0, 50.0)


def test_gost_profile_web_slenderness_is_far_below_the_limit():
    # hef = 120 − 2·4 = 112; λw = (112/4)·√(240/206 000) = 28·0,034132 = 0,956; предел 3,5.
    result = check_local_stability(TUBE_120x60x4, ry_mpa=240, sigma_c_mpa=240)

    assert result.web_slenderness == pytest.approx(0.956, abs=1e-3)
    assert result.web_utilization == pytest.approx(0.956 / 3.5, abs=1e-3)


@pytest.mark.parametrize(
    ("section", "slenderness", "ok"),
    [
        (_tube(200, 100, 2), 3.345, True),  # (196/2)·0,034132
        (_tube(250, 100, 2), 4.198, False),  # (246/2)·0,034132
    ],
)
def test_thin_custom_web_passes_or_fails_against_limit_3_5(section, slenderness, ok):
    result = check_local_stability(section, ry_mpa=240, sigma_c_mpa=240)

    assert result.web_slenderness == pytest.approx(slenderness, abs=1e-3)
    assert (result.web_utilization <= 1.0) is ok


@pytest.mark.parametrize(
    ("sigma_c", "limit", "ok"),
    [
        (240, 1.5, False),  # σc = Ry → 1,5·√1
        (240 / 9, 4.5, True),  # σc = Ry/9 → 1,5·√9
    ],
)
def test_box_flange_limit_follows_formula_98(sigma_c, limit, ok):
    # Поясной лист 200 мм, стенка 2 мм: bf = 196; λf1 = 98·0,034132 = 3,345.
    result = check_local_stability(_tube(120, 200, 2), ry_mpa=240, sigma_c_mpa=sigma_c)

    assert result.flange_slenderness == pytest.approx(3.345, abs=1e-3)
    assert result.flange_limit == pytest.approx(limit)
    assert (result.flange_utilization <= 1.0) is ok
