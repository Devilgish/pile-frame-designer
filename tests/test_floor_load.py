"""Нагрузка с пола на балки методом «конверта»: линии под 45° в каждой ячейке."""

import pytest

from pile_frame.contour import Contour
from pile_frame.floor_load import distribute_floor, loaded_area_mm2, zone_profiles


def _rectangle(width, length):
    return Contour.from_points([(0, 0), (width, 0), (width, length), (0, length)])


def _perimeter(width, length):
    return [
        ((0, 0), (width, 0)),
        ((width, 0), (width, length)),
        ((0, length), (width, length)),
        ((0, 0), (0, length)),
    ]


def test_single_cell_sends_triangles_to_short_edges_and_trapezoids_to_long_edges():
    # 2000 × 3000: короткие стороны — треугольники 2000²/4 = 1 м²;
    # длинные — трапеции 3000·1000 − 1000² = 2 м². Сумма 6 м².
    segments = _perimeter(2000, 3000)

    loads = distribute_floor(_rectangle(2000, 3000), segments)

    areas = [loaded_area_mm2(loads[i]) / 1e6 for i in range(4)]
    assert areas == pytest.approx([1.0, 2.0, 1.0, 2.0])


def test_internal_beam_collects_load_from_both_neighbouring_cells_without_double_count():
    # 4000 × 3000, балка y = 1000. Ячейки 4000×1000 и 4000×2000.
    # Внутренняя балка: 4·0,5 − 0,5² = 1,75 м² и 4·1 − 1² = 3 м² → 4,75 м². Всего 12 м².
    segments = [*_perimeter(4000, 3000), ((0, 1000), (4000, 1000))]

    loads = distribute_floor(_rectangle(4000, 3000), segments)

    assert loaded_area_mm2(loads[4]) / 1e6 == pytest.approx(4.75)
    total = sum(loaded_area_mm2(profile) for profile in loads.values())
    assert total / 1e6 == pytest.approx(12.0)


def test_zone_strip_along_one_edge_loads_the_nearest_beams_by_the_envelope():
    # Ячейка 2000 × 2000, зона — полоса y ≤ 500 вдоль нижней стороны.
    # Нижняя балка: часть треугольника «конверта» ниже 500 — трапеция 2000·500 − 500² = 0,75 м²,
    # глубина min(s, 2000 − s, 500). Левая и правая: треугольники 500²/2 = 0,125 м². Верхняя: 0.
    segments = _perimeter(2000, 2000)

    zones = zone_profiles(_rectangle(2000, 2000), segments, [(0, 0, 2000, 500)])

    areas = [loaded_area_mm2(zones[i][0]) / 1e6 for i in range(4)]
    assert areas == pytest.approx([0.75, 0.125, 0.0, 0.125])
    bottom = zones[0][0]
    assert max(d for _, _, d0, d1 in bottom for d in (d0, d1)) == pytest.approx(500)


def test_zone_loads_add_up_to_the_zone_area_on_a_beam_grid():
    # 6000 × 4000, балки по сетке 2000: зона 1500…4500 × 500…3000 режет несколько ячеек.
    # Вся её площадь 3000·2500 = 7,5 м² уходит на балки, ничего не теряется и не удваивается.
    segments = list(_perimeter(6000, 4000))
    segments += [((x, 0), (x, 4000)) for x in (2000, 4000)]
    segments += [((0, 2000), (6000, 2000))]

    zones = zone_profiles(_rectangle(6000, 4000), segments, [(1500, 500, 4500, 3000)])

    total = sum(loaded_area_mm2(zones[i][0]) for i in range(len(segments)))
    assert total / 1e6 == pytest.approx(7.5)


def test_zone_over_the_whole_floor_repeats_the_ordinary_envelope_for_every_beam():
    segments = list(_perimeter(6000, 4000))
    segments += [((x, 0), (x, 4000)) for x in (2000, 4000)]
    segments += [((0, 1250), (6000, 1250))]
    contour = _rectangle(6000, 4000)

    full = distribute_floor(contour, segments)
    zones = zone_profiles(contour, segments, [(0, 0, 6000, 4000)])

    for i in range(len(segments)):
        assert loaded_area_mm2(zones[i][0]) == pytest.approx(loaded_area_mm2(full[i]), rel=1e-6)
