"""Зоны в расчёте: своя временная нагрузка на своей площади, остальной пол — общая."""

import pytest

from pile_frame.design import Project, analyze
from pile_frame.status import REMARKS_LABEL, Status, design_status
from pile_frame.zones import Zone


def _grid(*zones, **changes):
    # 6000 × 4000 на сваях через 2000, каркас только по сваям; вне зон 1,5 кПа.
    params = {
        "width_mm": 6000,
        "length_mm": 4000,
        "pile_step_mm": 2000,
        "live_load_kpa": 1.5,
        "sheet_joints": False,
    }
    return analyze(Project(zones=tuple(zones), **{**params, **changes}))


STORAGE = Zone("storage", (0, 0, 2000, 2000), 5.0)


def _moments(design):
    return {
        frozenset((m.start, m.end)): c.max_moment_knm
        for m, c in zip(design.members, design.checks, strict=True)
    }


def test_heavy_zone_raises_forces_under_it_and_leaves_far_beams_alone():
    plain = _moments(_grid())
    zoned = _moments(_grid(STORAGE))

    # Периметр под складом нагружен только зоной; балка x = 2000 делит её с соседней ячейкой
    # без зоны и неразрезна через узел y = 2000, поэтому растёт меньше.
    only_zone = frozenset(((0.0, 0.0), (2000.0, 0.0)))
    shared = frozenset(((2000.0, 0.0), (2000.0, 2000.0)))
    assert zoned[only_zone] > 1.5 * plain[only_zone]
    assert zoned[shared] > 1.3 * plain[shared]
    far = [
        frozenset(((4000.0, 4000.0), (6000.0, 4000.0))),
        frozenset(((6000.0, 2000.0), (6000.0, 4000.0))),
    ]
    for key in far:
        assert zoned[key] == pytest.approx(plain[key], rel=0.03), key


def test_reactions_carry_the_zone_load_with_its_own_load_factor():
    # Пол 24 м²: (0,3061·1,2 + 1,5·1,3) = 2,3173 кПа → 55,615 кН (1,5 < 2,0 → γf 1,3).
    # Склад 4 м²: 5,0·1,2 − 1,5·1,3 = 4,05 кПа сверх общей → 16,2 кН (5,0 ≥ 2,0 → γf 1,2).
    # Металл: 20 м · 17,55 + 14 м · 10,48 кг/м · 9,81 · 1,05 = 5,127 кН. Всего 76,942 кН.
    design = _grid(STORAGE)

    assert sum(design.reactions_kn.values()) == pytest.approx(76.942, abs=1e-2)


def test_heavy_zone_increases_deflection_under_it():
    # Прогиб считается от постоянной и 0,35 временной — в зоне от её собственной нагрузки.
    def deflection(design):
        key = frozenset(((0.0, 0.0), (2000.0, 0.0)))
        return next(
            c.deflection_mm
            for m, c in zip(design.members, design.checks, strict=True)
            if frozenset((m.start, m.end)) == key
        )

    assert deflection(_grid(STORAGE)) > 1.3 * deflection(_grid())


def test_board_in_a_heavy_zone_gets_more_jumpers():
    # 6400 × 2500, листы 3200 × 1250: вне зон 4 кПа → по 4 перемычки на ячейку (пролёт 640).
    # Зона 10 кПа слева: q = 1,2·0,306 + 1,2·10 = 12,37 кПа, на пролёте 640 изгиб 1,47 —
    # перемычек слева больше, справа столько же, сколько без зоны.
    heavy = Zone("storage", (0, 0, 3200, 2500), 10.0)
    design = analyze(
        Project(width_mm=6400, length_mm=2500, pile_step_mm=3200, live_load_kpa=4.0, zones=(heavy,))
    )

    left = [c.jumpers for c in design.board_cells if c.bounds[2] <= 3200 + 1]
    right = [c.jumpers for c in design.board_cells if c.bounds[0] >= 3200 - 1]
    assert right == [4, 4]
    assert all(j > 4 for j in left)
    assert all(c.check.passed for c in design.board_cells)


def test_cold_room_standing_on_the_board_is_warned_about_freezing_and_condensate():
    prefab = Zone("cold", (0, 0, 2000, 2000), 5.0)
    on_board = Zone("cold", (0, 0, 2000, 2000), 5.0, cold_on_board=True)

    assert _grid(prefab).remarks == []
    remarks = _grid(on_board).remarks
    assert len(remarks) == 1
    assert "промерзан" in remarks[0] and "конденсат" in remarks[0]
    status, label, _ = design_status(_grid(on_board))
    assert status is Status.WARNING and label == REMARKS_LABEL
