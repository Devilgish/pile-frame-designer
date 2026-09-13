"""Нагрузка с пола на балки методом «конверта»: линии под 45° в каждой ячейке."""

import pytest

from pile_frame.contour import Contour
from pile_frame.floor_load import distribute_floor, loaded_area_mm2


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
