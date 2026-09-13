"""Передача нагрузки с пола на балки методом «конверта».

Пол делится балками на ячейки. В прямоугольной ячейке линии под 45° из углов делят площадь:
на короткие стороны приходятся треугольники, на длинные — трапеции. Сумма равна площади ячейки,
поэтому нагрузка не считается дважды. Непрямоугольные ячейки (редкие, у выреза контура)
распределяются равномерно по периметру.

Нагрузка на балку описывается «глубиной» грузовой площади d(s), мм: погонная нагрузка равна
давлению на пол, умноженному на d(s). Профиль задаётся кусочно-линейно: (s0, s1, d0, d1),
где s отсчитывается от начала балки (меньшей координаты).
"""

from __future__ import annotations

from shapely.geometry import LineString
from shapely.ops import polygonize, unary_union

from pile_frame.contour import Contour, Point

Profile = list[tuple[float, float, float, float]]
TOLERANCE_MM = 0.5


def loaded_area_mm2(profile: Profile) -> float:
    """Грузовая площадь по профилю глубины, мм²."""
    return sum((s1 - s0) * (d0 + d1) / 2 for s0, s1, d0, d1 in profile)


def _ordered(segment: tuple[Point, Point]) -> tuple[Point, Point, int]:
    """Начало и конец отрезка по возрастанию координаты и ось (0 — вдоль X, 1 — вдоль Y)."""
    a, b = segment
    axis = 0 if abs(a[1] - b[1]) <= TOLERANCE_MM else 1
    return (a, b, axis) if a[axis] <= b[axis] else (b, a, axis)


def _edge_profile(length: float, depth: float) -> list[tuple[float, float]]:
    """Точки профиля d(t) = min(t, length − t, depth) вдоль стороны ячейки."""
    ramp = min(depth, length / 2)
    points = [(0.0, 0.0), (ramp, ramp)]
    if length - ramp > ramp:
        points.append((length - ramp, ramp))
    points.append((length, 0.0))
    return points


def _clip(points: list[tuple[float, float]], start: float, end: float) -> Profile:
    """Кусочно-линейный профиль на участке [start, end] в координатах стороны."""

    def value(t: float) -> float:
        for (t0, d0), (t1, d1) in zip(points, points[1:], strict=False):
            if t0 <= t <= t1:
                return d0 if t1 == t0 else d0 + (d1 - d0) * (t - t0) / (t1 - t0)
        return 0.0

    marks = sorted({start, end, *(t for t, _ in points if start < t < end)})
    return [(t0, t1, value(t0), value(t1)) for t0, t1 in zip(marks, marks[1:], strict=False)]


def distribute_floor(contour: Contour, segments: list[tuple[Point, Point]]) -> dict[int, Profile]:
    """Профили грузовой площади для каждой балки (по индексу в ``segments``)."""
    lines = [LineString(s) for s in segments] + [contour.polygon.boundary]
    cells = [
        cell
        for cell in polygonize(unary_union(lines))
        if contour.polygon.buffer(TOLERANCE_MM).contains(cell.representative_point())
    ]
    ordered = [_ordered(s) for s in segments]
    loads: dict[int, Profile] = {i: [] for i in range(len(segments))}

    for cell in cells:
        min_x, min_y, max_x, max_y = cell.bounds
        width, height = max_x - min_x, max_y - min_y
        rectangular = abs(cell.area - width * height) <= TOLERANCE_MM * (width + height)
        if rectangular:
            depth = min(width, height) / 2
            edges = [
                ((min_x, min_y), (max_x, min_y), 0),
                ((min_x, max_y), (max_x, max_y), 0),
                ((min_x, min_y), (min_x, max_y), 1),
                ((max_x, min_y), (max_x, max_y), 1),
            ]
        else:
            depth = cell.area / cell.length  # равномерно по периметру
            coords = list(cell.exterior.coords)
            edges = [_ordered((a, b)) for a, b in zip(coords, coords[1:], strict=False)]
        for start, end, axis in edges:
            length = end[axis] - start[axis]
            if length <= TOLERANCE_MM:
                continue
            across = 1 - axis
            points = (
                _edge_profile(length, depth) if rectangular else [(0.0, depth), (length, depth)]
            )
            for index, (a, b, seg_axis) in enumerate(ordered):
                if seg_axis != axis or abs(a[across] - start[across]) > TOLERANCE_MM:
                    continue
                low, high = max(a[axis], start[axis]), min(b[axis], end[axis])
                if high - low <= TOLERANCE_MM:
                    continue
                for t0, t1, d0, d1 in _clip(points, low - start[axis], high - start[axis]):
                    offset = start[axis] - a[axis]
                    loads[index].append((t0 + offset, t1 + offset, d0, d1))
    return loads
