"""Проект целиком: прямоугольный контур и шаг свай → сваи, каркас, проверка."""

import pytest

from pile_frame.design import Project, analyze
from pile_frame.sections import TUBE_120x60x4, TUBE_120x120x5


def test_piles_are_placed_on_a_grid_with_the_given_step():
    design = analyze(Project(width_mm=6000, length_mm=4000, pile_step_mm=2000, live_load_kpa=4.0))

    assert sorted(design.piles) == sorted(
        (x, y) for x in (0, 2000, 4000, 6000) for y in (0, 2000, 4000)
    )


def test_frame_has_heavy_perimeter_and_light_internal_beams_between_pile_rows():
    # 6500 / 2000 → 4 равных пролёта по 1625; 4000 / 2000 → 2 пролёта по 2000.
    design = analyze(Project(width_mm=6500, length_mm=4000, pile_step_mm=2000, live_load_kpa=4.0))

    perimeter = sorted(m.length_mm for m in design.members if m.section == TUBE_120x120x5)
    internal = sorted(m.length_mm for m in design.members if m.section == TUBE_120x60x4)

    assert perimeter == pytest.approx([1625] * 8 + [2000] * 4)
    assert internal == pytest.approx([1625] * 4 + [2000] * 6)


def test_most_loaded_internal_beam_is_checked_with_floor_and_self_weight_loads():
    # Внутренняя балка 120×60, пролёт 2 м, грузовая ширина 2 м.
    # ЦСП 24 мм, 1300 кг/м³: 0,3061 кПа · 2 = 0,6121 кН/м (γf 1,2 → 0,7346);
    # собственный вес 10,48 кг/м · 9,81 = 0,1028 кН/м (γf 1,05 → 0,1080);
    # временная 4,0 кПа · 2 = 8,0 кН/м (γf 1,2 → 9,6).
    # q = 10,4425 кН/м; M = 5,2213 кН·м; σ = 130,14 Н/мм²; 130,14 / 240 = 0,542.
    design = analyze(Project(width_mm=6000, length_mm=4000, pile_step_mm=2000, live_load_kpa=4.0))

    assert design.governing_member.section == TUBE_120x60x4
    assert design.governing_member.length_mm == pytest.approx(2000)
    assert design.governing_check.strength_utilization == pytest.approx(0.542, abs=0.001)
    assert design.governing_check.passed


def test_light_live_load_uses_higher_load_factor():
    # СП 20.13330, п. 8.2.2: γf = 1,3 при нормативной нагрузке < 2,0 кПа.
    # q = 0,8425 + 1,5·2·1,3 = 4,7425 кН/м; M = 2,3713 кН·м; σ = 59,10 Н/мм²; 0,246.
    # (С γf = 1,2 было бы 0,231.)
    design = analyze(Project(width_mm=6000, length_mm=4000, pile_step_mm=2000, live_load_kpa=1.5))

    assert design.governing_check.strength_utilization == pytest.approx(0.246, abs=0.001)


def test_plan_without_internal_rows_checks_perimeter_with_half_span_tributary():
    # Только периметр 120×120×5, пролёт 2 м, грузовая ширина 1 м.
    # q = 0,3061·1,2 + 0,1722·1,05 + 4,0·1,2 = 5,348 кН/м; M = 2,674 кН·м;
    # σ = 2,674e6 / 80 880 = 33,06 Н/мм²; 33,06 / 240 = 0,138.
    design = analyze(Project(width_mm=2000, length_mm=2000, pile_step_mm=2000, live_load_kpa=4.0))

    assert design.governing_member.section == TUBE_120x120x5
    assert design.governing_check.strength_utilization == pytest.approx(0.138, abs=0.001)


def test_every_overstressed_member_is_reported_not_only_the_governing_one():
    # 9000 × 6000, шаг 3000, 4,0 кПа.
    # Внутренние 120×60 (грузовая ширина 3 м): использование ≈ 1,82 — не проходят, их 3 + 2·2 = 7.
    # Периметр 120×120 (грузовая ширина 1,5 м): q ≈ 7,93 кН/м, σ ≈ 110 Н/мм², ≈ 0,46 — проходит.
    design = analyze(Project(width_mm=9000, length_mm=6000, pile_step_mm=3000, live_load_kpa=4.0))

    failing = design.failing_members()

    assert len(failing) == 7
    assert {m.section for m in failing} == {TUBE_120x60x4}
