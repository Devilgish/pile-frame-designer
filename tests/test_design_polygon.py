"""Проект на ортогональном многоугольнике: сваи, балки, ошибки и предупреждения."""

import pytest

from pile_frame.contour import Contour
from pile_frame.design import Project, analyze
from pile_frame.sections import TUBE_120x60x4, TUBE_120x120x5

# Г-образный план: 6000 × 4000 без выреза x ∈ [3000, 6000], y ∈ [2000, 4000].
L_SHAPE = Contour.from_points(
    [(0, 0), (6000, 0), (6000, 2000), (3000, 2000), (3000, 4000), (0, 4000)]
)


def _project(contour, piles=None):
    # Каркас только по сваям: здесь проверяется логика балок по сваям и контуру.
    return Project(
        contour=contour, pile_step_mm=2000, live_load_kpa=4.0, piles=piles, sheet_joints=False
    )


def test_auto_piles_fill_l_shape_on_axes_through_every_corner():
    # Оси X: вершины 0, 3000, 6000; отрезки по 3000 делятся на 2 → 0, 1500, 3000, 4500, 6000.
    # Оси Y: 0, 2000, 4000. Из 15 узлов два (4500 и 6000 при y = 4000) в вырезе → 13 свай.
    design = analyze(_project(L_SHAPE))

    expected = [(x, y) for y in (0, 2000) for x in (0, 1500, 3000, 4500, 6000)]
    expected += [(0, 4000), (1500, 4000), (3000, 4000)]
    assert sorted(design.piles) == sorted(expected)


def test_l_shape_frame_follows_contour_edges_with_heavy_perimeter():
    # Периметр: низ 4×1500; сторона выреза y = 2000 — 2×1500; верх 2×1500;
    #   x = 0 — 2×2000; x = 3000 над вырезом — 1×2000; x = 6000 — 1×2000.
    #   Итого 8×1500 + 4×2000 = 20 000 мм = 2·(6000 + 4000).
    # Внутренние: y = 2000 левее выреза 2×1500; x = 1500 — 2×2000; x = 3000 и x = 4500 ниже
    #   выреза — по 1×2000.
    design = analyze(_project(L_SHAPE))

    perimeter = sorted(m.length_mm for m in design.members if m.section == TUBE_120x120x5)
    internal = sorted(m.length_mm for m in design.members if m.section == TUBE_120x60x4)

    assert perimeter == pytest.approx([1500] * 8 + [2000] * 4)
    assert internal == pytest.approx([1500] * 2 + [2000] * 4)


def test_no_beam_bridges_the_notch_of_a_u_shape():
    # П-образный план: вырез x ∈ [2000, 4000], y ∈ [2000, 4000]. Сваи (2000, 4000) и (4000, 4000)
    # стоят на одной линии, но между ними пустота — балки быть не должно.
    u_shape = Contour.from_points(
        [
            (0, 0),
            (6000, 0),
            (6000, 4000),
            (4000, 4000),
            (4000, 2000),
            (2000, 2000),
            (2000, 4000),
            (0, 4000),
        ]
    )
    design = analyze(_project(u_shape))

    spans = {frozenset((m.start, m.end)) for m in design.members}
    assert frozenset(((2000, 4000), (4000, 4000))) not in spans
    assert len(design.piles) == 12


def _auto(contour):
    return list(analyze(_project(contour)).piles)


def _spans(design):
    return {frozenset((m.start, m.end)): m for m in design.members}


def test_moved_pile_reconnects_beams_along_its_new_lines():
    piles = _auto(L_SHAPE)
    piles[piles.index((1500, 2000))] = (1500, 2500)

    spans = _spans(analyze(_project(L_SHAPE, piles=tuple(piles))))

    # На линии y = 2000 средней сваи больше нет — одна балка через 3000 мм.
    assert spans[frozenset(((0, 2000), (3000, 2000)))].length_mm == pytest.approx(3000)
    # На вертикали x = 1500 балки 2500 и 1500.
    assert spans[frozenset(((1500, 0), (1500, 2500)))].length_mm == pytest.approx(2500)
    assert spans[frozenset(((1500, 2500), (1500, 4000)))].length_mm == pytest.approx(1500)
    assert not any((1500, 2000) in pair for pair in spans)


def test_pile_outside_contour_is_reported_and_not_connected():
    piles = [*_auto(L_SHAPE), (4500, 3000)]  # в вырезе Г-формы

    design = analyze(_project(L_SHAPE, piles=tuple(piles)))

    assert design.piles_outside == [(4500, 3000)]
    assert not any((4500, 3000) in pair for pair in _spans(design))


def test_corner_without_pile_is_warned_and_its_perimeter_beams_have_no_support():
    piles = [p for p in _auto(L_SHAPE) if p != (6000, 0)]

    design = analyze(_project(L_SHAPE, piles=tuple(piles)))

    assert design.corners_without_piles == [(6000, 0)]
    unsupported = {frozenset((m.start, m.end)) for m in design.unsupported_members}
    assert unsupported == {
        frozenset(((4500, 0), (6000, 0))),
        frozenset(((6000, 0), (6000, 2000))),
    }
    failing = {frozenset((m.start, m.end)) for m in design.failing_members()}
    assert unsupported <= failing


def test_removed_mid_edge_pile_merges_perimeter_into_a_longer_span():
    piles = [p for p in _auto(L_SHAPE) if p != (1500, 0)]

    spans = _spans(analyze(_project(L_SHAPE, piles=tuple(piles))))

    assert spans[frozenset(((0, 0), (3000, 0)))].length_mm == pytest.approx(3000)
