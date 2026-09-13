"""Контур плана: ортогональный многоугольник."""

import pytest

from pile_frame.contour import Contour, ContourError

# Г-образный план: прямоугольник 6000 × 4000 без выреза 3000 × 2000 в углу.
L_SHAPE = [(0, 0), (6000, 0), (6000, 2000), (3000, 2000), (3000, 4000), (0, 4000)]


def test_l_shaped_contour_area_is_rectangle_minus_notch():
    # 6000·4000 − 3000·2000 = 24 − 6 = 18 м².
    contour = Contour.from_points(L_SHAPE)

    assert contour.area_mm2 == pytest.approx(18e6)


@pytest.mark.parametrize(
    ("points", "reason"),
    [
        ([(0, 0), (4000, 0), (3000, 3000), (0, 3000)], "горизонтальной или вертикальной"),
        # Сторона x = 1000 идёт от y = 2000 до y = −1000 и пересекает сторону y = 0.
        (
            [(0, 0), (3000, 0), (3000, 2000), (1000, 2000), (1000, -1000), (0, -1000)],
            "пересекает сам себя",
        ),
        ([(0, 0), (4000, 0), (4000, 3000)], "не меньше 4 вершин"),
    ],
    ids=["скошенная сторона", "самопересечение", "мало вершин"],
)
def test_invalid_contour_is_rejected_with_a_readable_reason(points, reason):
    with pytest.raises(ContourError, match=reason):
        Contour.from_points(points)


@pytest.mark.parametrize(
    ("point", "inside"),
    [
        ((1000, 1000), True),
        ((4500, 2000), True),  # на стороне выреза — граница считается контуром
        ((0, 4000), True),  # вершина
        ((4500, 3000), False),  # в вырезе
        ((-1, 0), False),
    ],
)
def test_point_on_boundary_counts_as_inside_and_notch_is_outside(point, inside):
    assert Contour.from_points(L_SHAPE).covers(point) is inside
