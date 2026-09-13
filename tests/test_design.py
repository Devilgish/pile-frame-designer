"""Проект целиком: контур и сваи → каркас, нагрузки, расчёт грильяжа, проверки, реакции.

Эталоны нагрузок и материалов считаются вручную на простой схеме: квадрат 2000 × 2000 мм на
четырёх угловых сваях, только периметр. Каждая сторона — однопролётная балка (кручение не
учитывается), нагрузка с пола по «конверту» — треугольник с пиком w = p·1 м посередине.
Тогда M = w·L²/12 + g·L²/8, реакция каждой сваи — четверть полной нагрузки.
"""

import pytest

from pile_frame.boards import BoardSpec
from pile_frame.design import Project, analyze
from pile_frame.materials import STEELS
from pile_frame.sections import TUBE_120x60x4, TUBE_120x120x5

# ЦСП 24 мм, 1300 кг/м³: 1300·9,81·0,024 = 0,306072 кПа.
BOARD_KPA = 0.306072


def _square(**changes):
    params = {
        "width_mm": 2000,
        "length_mm": 2000,
        "pile_step_mm": 2000,
        "live_load_kpa": 4.0,
        "sheet_joints": False,
    }
    return analyze(Project(**{**params, **changes}))


def test_piles_are_placed_on_a_grid_with_the_given_step():
    design = analyze(
        Project(
            width_mm=6000, length_mm=4000, pile_step_mm=2000, live_load_kpa=4.0, sheet_joints=False
        )
    )

    assert sorted(design.piles) == sorted(
        (x, y) for x in (0, 2000, 4000, 6000) for y in (0, 2000, 4000)
    )


def test_frame_has_heavy_perimeter_and_light_internal_beams_between_pile_rows():
    # 6500 / 2000 → 4 равных пролёта по 1625; 4000 / 2000 → 2 пролёта по 2000.
    design = analyze(
        Project(
            width_mm=6500, length_mm=4000, pile_step_mm=2000, live_load_kpa=4.0, sheet_joints=False
        )
    )

    perimeter = sorted(m.length_mm for m in design.members if m.section == TUBE_120x120x5)
    internal = sorted(m.length_mm for m in design.members if m.section == TUBE_120x60x4)

    assert perimeter == pytest.approx([1625] * 8 + [2000] * 4)
    assert internal == pytest.approx([1625] * 4 + [2000] * 6)


def test_pile_reactions_add_up_to_the_full_design_load():
    # Пол 4 м²: (0,306072·1,2 + 4,0·1,2)·4 = 20,6691 кН.
    # Периметр 8 м · 17,55 кг/м · 9,81 · 1,05 = 1,4462 кН. Всего 22,1153 кН, по 5,5288 кН на сваю.
    design = _square()

    reactions = design.reactions_kn
    assert sum(reactions.values()) == pytest.approx(22.1153, abs=1e-3)
    assert all(r == pytest.approx(5.5288, abs=1e-3) for r in reactions.values())


def test_square_perimeter_beam_matches_hand_calculated_triangular_load():
    # w = (0,306072·1,2 + 4,0·1,2)·1 м = 5,16729 кН/м; g = 0,17217·1,05 = 0,18077 кН/м.
    # M = 5,16729·2²/12 + 0,18077·2²/8 = 1,72243 + 0,09039 = 1,81282 кН·м.
    # σ = 1,81282e6 / 80 880 = 22,41 Н/мм²; 22,41 / 240 = 0,0934.
    check = _square().governing_check

    assert check.max_moment_knm == pytest.approx(1.8128, abs=1e-3)
    assert check.strength_utilization == pytest.approx(0.0934, abs=5e-4)


def test_shear_follows_formula_42_with_both_webs():
    # Q = w·L/4 + g·L/2 = 5,16729·0,5 + 0,18077·1 = 2,76442 кН.
    # 120×120×5 без скруглений: S = 120·5·57,5 + 2·5·55·27,5 = 49 625 мм³;
    # I = 485,3 см⁴; tw = 2·5 = 10 мм; Rs = 0,58·240 = 139,2 Н/мм².
    # τ = 2 764,42·49 625 / (4 853 000·10) = 2,827 Н/мм²; 2,827 / 139,2 = 0,0203.
    check = _square().governing_check

    assert check.max_shear_kn == pytest.approx(2.7644, abs=1e-3)
    assert check.shear_utilization == pytest.approx(0.0203, abs=2e-4)


def test_light_live_load_uses_higher_load_factor():
    # Временная 1,5 кПа < 2,0 → γf = 1,3. Пол: (0,367286 + 1,5·1,3)·4 = 9,26914 кН; периметр 1,4462.
    # Сумма реакций 10,7153 кН (с γf = 1,2 было бы 10,1153).
    reactions = _square(live_load_kpa=1.5).reactions_kn

    assert sum(reactions.values()) == pytest.approx(10.7153, abs=1e-3)


def test_lighter_perimeter_profile_changes_self_weight_and_resistance():
    # 120×60×4: g = 10,48·9,81·1,05 = 0,10795 кН/м; M = 1,72243 + 0,10795·4/8 = 1,77641 кН·м;
    # σ = 1,77641e6 / 40 120 = 44,28 Н/мм²; 44,28 / 240 = 0,1845.
    check = _square(perimeter_section=TUBE_120x60x4).governing_check

    assert check.strength_utilization == pytest.approx(0.1845, abs=5e-4)


def test_stronger_steel_uses_its_design_resistance():
    # С355, стенка 5 мм: Ry = 350. σ = 22,41 Н/мм² → 22,41 / 350 = 0,0640.
    check = _square(steel=STEELS["С355"]).governing_check

    assert check.strength_utilization == pytest.approx(0.0640, abs=5e-4)


def test_thicker_board_adds_floor_load():
    # ЦСП 36 мм: 0,459108·1,2 = 0,55093 кПа; w = 5,35093 кН/м;
    # M = 5,35093·4/12 + 0,09039 = 1,87403 кН·м; σ = 23,17 Н/мм²; 23,17 / 240 = 0,0965.
    check = _square(board=BoardSpec(thickness_mm=36)).governing_check

    assert check.strength_utilization == pytest.approx(0.0965, abs=5e-4)


def test_every_overstressed_member_is_reported_not_only_the_governing_one():
    # 2000 × 6000 на угловых сваях (шаг 6000). Длинные стороны — трапеция с подъёмом 1 м:
    # M = w·(3L² − 4a²)/24 + g·L²/8 = 5,16729·(108 − 4)/24 + 0,18077·36/8
    #   = 22,39 + 0,81 = 23,21 кН·м;
    # σ = 287,0 Н/мм² > 240 — не проходят. Короткие: M = 1,81 кН·м, 0,093 — проходят.
    design = analyze(
        Project(
            width_mm=2000, length_mm=6000, pile_step_mm=6000, live_load_kpa=4.0, sheet_joints=False
        )
    )

    failing = design.failing_members()

    assert len(failing) == 2
    assert all(m.length_mm == pytest.approx(6000) for m in failing)
