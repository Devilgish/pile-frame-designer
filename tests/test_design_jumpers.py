"""Перемычки 40×40 там, где лист ЦСП не проходит между балками."""

import pytest

from pile_frame.boards import BoardSpec
from pile_frame.contour import Contour
from pile_frame.design import Project, analyze
from pile_frame.sections import TUBE_40x40x3


def _rectangle(width, length):
    return Contour.from_points([(0, 0), (width, 0), (width, length), (0, length)])


def _jumpers(design):
    return [m for m in design.members if m.kind == "jumper"]


def test_wide_cells_get_jumpers_across_their_long_side():
    # 6400 × 2500, сваи через 3200: балки x = 0, 3200, 6400 и под стыком y = 1251,5.
    # Четыре ячейки ≈ 3200 × 1250, лист 24 мм, 4 кПа: по 4 перемычки с шагом 3200/5 = 640
    # (пролёт 800 при трёх перемычках не проходит — см. test_board_check).
    design = analyze(
        Project(
            contour=_rectangle(6400, 2500),
            pile_step_mm=3200,
            live_load_kpa=4.0,
            board=BoardSpec(thickness_mm=24),
        )
    )
    jumpers = _jumpers(design)

    assert len(jumpers) == 16
    assert all(m.section == TUBE_40x40x3 for m in jumpers)
    assert all(m.start[0] == m.end[0] for m in jumpers)  # поперёк длинной стороны — вдоль Y
    xs = sorted({m.start[0] for m in jumpers})
    assert xs == pytest.approx([640, 1280, 1920, 2560, 3840, 4480, 5120, 5760])
    assert sorted(m.length_mm for m in jumpers) == pytest.approx([1248.5] * 8 + [1251.5] * 8)
    assert [c.jumpers for c in design.board_cells] == [4, 4, 4, 4]
    assert all(c.check.span_mm == pytest.approx(640) for c in design.board_cells)
    assert all(c.check.passed for c in design.board_cells)


def test_close_beams_need_no_jumpers():
    # 2400 × 2500, сваи через 600: ячейки не больше 600 × 500, лист 24 мм проходит на 600
    # (сосредоточенная 0,913) — перемычки не нужны, все ячейки проверены и проходят.
    design = analyze(
        Project(
            contour=_rectangle(2400, 2500),
            pile_step_mm=600,
            live_load_kpa=4.0,
            board=BoardSpec(thickness_mm=24),
        )
    )

    assert _jumpers(design) == []
    assert design.board_cells
    assert all(cell.jumpers == 0 and cell.check.passed for cell in design.board_cells)


def _wide_cells_design():
    return analyze(
        Project(
            contour=_rectangle(6400, 2500),
            pile_step_mm=3200,
            live_load_kpa=4.0,
            board=BoardSpec(thickness_mm=24),
        )
    )


def _jumper_check(design, length):
    return next(
        c
        for m, c in zip(design.members, design.checks, strict=True)
        if m.kind == "jumper" and m.length_mm == pytest.approx(length)
    )


def test_jumper_is_checked_for_the_concentrated_load_at_midspan():
    # Перемычка 1251,5 мм, соседние ячейки по 640: две трапеции «конверта» глубиной 320,
    # средняя глубина 2·(1251,5 + 611,5)/2·320/1251,5 = 476,4 мм.
    # Постоянная: 1,2·3,0607e-4·476,4 + 1,05·3,30·9,81e-3 = 0,2090 Н/мм.
    # M = 1800·1251,5/4 + 0,2090·1251,5²/8 = 604 084 Н·мм; σ = M/4650 = 129,9 → 129,9/240 = 0,541
    # (от равномерной временной ≈ 0,44 — сосредоточенная определяет).
    check = _jumper_check(_wide_cells_design(), 1251.5)

    assert check.strength_utilization == pytest.approx(0.5413, abs=1e-3)
    # Срез у опоры: V = 1800 + 0,2090·1251,5/2 = 1930,8 Н; S = 40·3·37/2 + 2·3·17²/2 = 3087 мм³;
    # τ = V·S/(I·2t) = 1930,8·3087/(9,31e4·6) = 10,67 МПа; Rs = 0,58·240 = 139,2 → 0,0767.
    assert check.shear_utilization == pytest.approx(0.0767, abs=1e-3)


def test_jumper_deflection_is_limited_by_its_own_span():
    # fu по таблице Д.1 для l = 1,2515 м: 8,333 + (20 − 8,333)·0,2515/2 = 9,80 мм
    # (не по ячейке свай 3200 × 2500, как у балок каркаса).
    check = _jumper_check(_wide_cells_design(), 1251.5)

    assert check.deflection_limit_mm == pytest.approx(9.80, abs=0.01)
