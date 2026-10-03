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
