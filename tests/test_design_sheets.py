"""Каркас под листы: промежуточные балки под стыками, каждый край листа на балке."""

import pytest
from shapely.geometry import LineString, box

from pile_frame.contour import Contour
from pile_frame.design import Project, analyze

L_SHAPE = Contour.from_points(
    [(0, 0), (6000, 0), (6000, 2000), (3000, 2000), (3000, 4000), (0, 4000)]
)


def _rectangle(width, length):
    return Contour.from_points([(0, 0), (width, 0), (width, length), (0, length)])


def test_secondary_beams_are_added_only_under_joints_without_a_pile_line_beam():
    # 6400 × 2500, сваи через 3200: балка по сваям x = 3200.
    # Стык x = 3201,5 — в 1,5 мм от неё: отдельная балка не нужна.
    # Стык y = 1251,5 — балки нет: две промежуточные 0…3200 и 3200…6400.
    design = analyze(Project(contour=_rectangle(6400, 2500), pile_step_mm=3200, live_load_kpa=4.0))

    under_y_joint = [m for m in design.members if m.start[1] == pytest.approx(1251.5) == m.end[1]]
    near_x_joint = [
        m
        for m in design.members
        if abs(m.start[0] - 3201.5) < 30 and m.start[0] == m.end[0] and m.start[0] != 3200
    ]

    assert sorted(m.length_mm for m in under_y_joint) == pytest.approx([3200, 3200])
    assert near_x_joint == []


@pytest.mark.parametrize(
    ("contour", "long_side", "offset"),
    [
        (L_SHAPE, "x", (0, 0)),
        (L_SHAPE, "y", (400, 700)),
        (_rectangle(7000, 3000), "x", (1000, 300)),
    ],
    ids=["Г-контур", "Г-контур поперёк со сдвигом", "прямоугольник со сдвигом"],
)
def test_every_sheet_edge_inside_the_contour_rests_on_a_beam(contour, long_side, offset):
    design = analyze(
        Project(
            contour=contour,
            pile_step_mm=2000,
            live_load_kpa=4.0,
            sheet_long_side=long_side,
            sheet_offset_mm=offset,
        )
    )
    beams = [LineString([m.start, m.end]) for m in design.members]
    boundary = contour.polygon.boundary

    unsupported = []
    for sheet in design.sheet_layout.sheets:
        rect = box(sheet.x0, sheet.y0, sheet.x1, sheet.y1)
        edges = contour.polygon.intersection(rect).boundary
        length = edges.length
        # Точки вдоль краёв куска через каждые 100 мм, кроме лежащих на контуре (там периметр).
        for i in range(int(length // 100) + 1):
            point = edges.interpolate(i * 100)
            if boundary.distance(point) < 1:
                continue
            if min(beam.distance(point) for beam in beams) > 30:
                unsupported.append((round(point.x), round(point.y)))

    assert unsupported == []


@pytest.mark.parametrize(
    "project",
    [
        # Балки под стыками делят Г-контур на прямоугольные ячейки.
        Project(contour=L_SHAPE, pile_step_mm=2000, live_load_kpa=4.0),
        # Сваи только в шести углах, без внутренних балок: одна Г-образная (непрямоугольная) ячейка.
        Project(
            contour=L_SHAPE,
            pile_step_mm=2000,
            live_load_kpa=4.0,
            piles=L_SHAPE.vertices,
            sheet_joints=False,
        ),
    ],
    ids=["ячейки прямоугольные", "одна Г-образная ячейка"],
)
def test_reactions_balance_floor_and_steel_weight_on_an_l_shape(project):
    # Полная расчётная нагрузка = площадь пола · (ЦСП·1,2 + временная·1,2) + вес металла · 1,05.
    design = analyze(project)

    floor = 18.0 * (0.306072 * 1.2 + 4.0 * 1.2)  # кН, площадь Г-контура 18 м²
    steel = sum(m.length_mm / 1e3 * m.section.mass_kg_m * 9.81e-3 * 1.05 for m in design.members)

    assert sum(design.reactions_kn.values()) == pytest.approx(floor + steel, rel=1e-6)
