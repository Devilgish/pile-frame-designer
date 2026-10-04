"""Точечные усиления: отдельные балки получают более тяжёлый профиль; масса металла."""

import pytest

from pile_frame.design import Project, analyze, member_key
from pile_frame.sections import TUBE_120x120x5


def _heavy(**changes):
    # 8000 × 4000, сваи через 3000, 8 кПа, каркас только по сваям: три внутренние балки
    # 120×60×4 длиной 2667 мм не проходят по изгибу (1,144).
    params = {
        "width_mm": 8000,
        "length_mm": 4000,
        "pile_step_mm": 3000,
        "live_load_kpa": 8.0,
        "sheet_joints": False,
    }
    return Project(**{**params, **changes})


def test_steel_mass_is_the_sum_of_lengths_times_linear_mass():
    # Квадрат 2000 × 2000, только периметр 120×120×5: 8 м · 17,55 кг/м = 140,4 кг.
    design = analyze(
        Project(
            width_mm=2000, length_mm=2000, pile_step_mm=2000, live_load_kpa=4.0, sheet_joints=False
        )
    )

    assert design.steel_mass_kg == pytest.approx(140.4)


def test_upgraded_beams_get_the_heavier_profile_and_pass():
    plain = analyze(_heavy())
    failing = [m for m in plain.members if m in plain.failing_members()]
    assert len(failing) == 3

    upgrades = tuple((member_key(m), TUBE_120x120x5) for m in failing)
    upgraded = analyze(_heavy(upgrades=upgrades))

    assert upgraded.failing_members() == []
    heavy = [m for m in upgraded.members if m.section == TUBE_120x120x5 and m.kind == "beam"]
    assert len(heavy) == 3
    # 3 · 2,6667 м · (17,55 − 10,48) кг/м = 56,56 кг.
    assert upgraded.steel_mass_kg - plain.steel_mass_kg == pytest.approx(56.56, abs=0.01)
