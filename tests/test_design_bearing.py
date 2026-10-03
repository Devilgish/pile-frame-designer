"""Опирание листа ЦСП на верхнюю полку балки: хватает ли места под саморез."""

import pytest

from pile_frame.boards import BoardSpec
from pile_frame.contour import Contour
from pile_frame.design import Project, analyze


def _design(thickness, offset=(0.0, 0.0)):
    # 6400 × 2500, сваи через 3200, листы 3200 × 1250 с зазором 3: стыки x = 3201,5 (над балкой
    # по сваям x = 3200) и y = 1251,5 (своя балка 120×60×4). Плоская часть полки
    # 60 − 2·R = 60 − 2·2·4 = 44 мм (ГОСТ 30245-2003: R = 2t при t < 6 мм).
    contour = Contour.from_points([(0, 0), (6400, 0), (6400, 2500), (0, 2500)])
    return analyze(
        Project(
            contour=contour,
            pile_step_mm=3200,
            live_load_kpa=4.0,
            board=BoardSpec(thickness_mm=thickness),
            sheet_offset_mm=offset,
        )
    )


def test_offset_joint_leaves_too_little_flange_for_the_screw():
    # Лист 12 мм: саморез не ближе a = 20 мм к кромке (Тамак).
    # Стык y: кромки 1250 и 1253 над осью 1251,5 → по 22 − 1,5 = 20,5 ≥ 20 — хватает.
    # Стык x: кромка 3200 над осью 3200 → 22; кромка 3203 → 3200 + 22 − 3203 = 19 < 20.
    design = _design(12)

    assert design.bearing_issues
    for issue in design.bearing_issues:
        (x0, _), (x1, _) = issue.start, issue.end
        assert x0 == pytest.approx(3203) and x1 == pytest.approx(3203)
        assert issue.bearing_mm == pytest.approx(19)
        assert issue.required_mm == 20
    covered = sum(abs(i.end[1] - i.start[1]) for i in design.bearing_issues)
    assert covered == pytest.approx(2500 - 3)  # обе кромки правого ряда листов, кроме зазора


def test_thick_board_needs_more_than_a_60_mm_flange_gives_and_perimeter_is_enough():
    # Лист 24 мм: a = 25 мм. Внутренние кромки: 22 (x = 3200), 19 (x = 3203), 20,5 (y = 1250
    # и 1253) — все меньше 25. Периметр 120×120×5: плоская часть 120 − 2·2·5 = 100, у кромки
    # над осью 50 ≥ 25 — замечаний нет.
    design = _design(24)

    found = sorted(
        {
            (round(i.bearing_mm, 1), round(i.start[0]) == round(i.end[0]))
            for i in design.bearing_issues
        }
    )
    assert found == [(19.0, True), (20.5, False), (22.0, True)]
    # По одному замечанию на кромку листа (2 листа × 4 внутренние кромки), хотя балка под стыком
    # разрезана концами перемычек на много элементов.
    assert len(design.bearing_issues) == 8
    on_perimeter = [
        i
        for i in design.bearing_issues
        if {i.start[0], i.end[0]} <= {0, 6400} or {i.start[1], i.end[1]} <= {0, 2500}
    ]
    assert on_perimeter == []


@pytest.mark.parametrize(
    ("offset", "edge"),
    [
        # Стык x = 27,5 + 3201,5 = 3229 в 29 мм от балки по сваям x = 3200 — своя балка не
        # ставится (ближе 30 мм). Кромка 3230,5 в 30,5 мм от оси — за краем полки 120×60.
        (27.5, 3230.5),
        # Стык 3225: кромка 3226,5 в 26,5 мм от оси — на скруглении (плоская часть до 22 мм).
        (23.5, 3226.5),
    ],
    ids=["за полкой", "на скруглении"],
)
def test_edge_off_the_flat_part_of_the_flange_has_no_bearing(offset, edge):
    design = _design(12, offset=(offset, 0.0))

    assert design.bearing_issues
    assert all(i.start[0] == pytest.approx(edge) for i in design.bearing_issues)
    assert all(i.bearing_mm == 0 for i in design.bearing_issues)
