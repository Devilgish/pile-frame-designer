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

from shapely.geometry import LineString, Polygon, box
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
    """Кусочно-линейный профиль на участке [start, end] в координатах стороны.

    Точки (t, d) по возрастанию t; повтор t с другим d — скачок глубины.
    """
    pieces = [(a, b) for a, b in zip(points, points[1:], strict=False) if b[0] > a[0]]

    def piece_at(t: float):
        for a, b in pieces:
            if a[0] <= t <= b[0]:
                return a, b
        return None

    marks = sorted({start, end, *(t for t, _ in points if start < t < end)})
    profile = []
    for t0, t1 in zip(marks, marks[1:], strict=False):
        piece = piece_at((t0 + t1) / 2)
        if piece is None:
            continue
        (a, da), (b, db) = piece

        def depth(t: float, a=a, b=b, da=da, db=db) -> float:
            return da + (db - da) * (t - a) / (b - a)

        profile.append((t0, t1, depth(t0), depth(t1)))
    return profile


def floor_cells(contour: Contour, segments: list[tuple[Point, Point]]) -> list[Polygon]:
    """Ячейки пола внутри контура, на которые его делят балки."""
    lines = [LineString(s) for s in segments] + [contour.polygon.boundary]
    return [
        cell
        for cell in polygonize(unary_union(lines))
        if contour.polygon.buffer(TOLERANCE_MM).contains(cell.representative_point())
    ]


def is_rectangular(cell: Polygon) -> bool:
    """Ячейка совпадает со своим габаритом (с допуском)."""
    min_x, min_y, max_x, max_y = cell.bounds
    width, height = max_x - min_x, max_y - min_y
    return abs(cell.area - width * height) <= TOLERANCE_MM * (width + height)


def _rect_edges(cell: Polygon):
    """Стороны прямоугольной ячейки с их грузовыми фигурами «конверта» (линии под 45°)."""
    x0, y0, x1, y1 = cell.bounds
    d = min(x1 - x0, y1 - y0) / 2
    return [
        ((x0, y0), (x1, y0), 0, [(x0, y0), (x1, y0), (x1 - d, y0 + d), (x0 + d, y0 + d)]),
        ((x0, y1), (x1, y1), 0, [(x0, y1), (x1, y1), (x1 - d, y1 - d), (x0 + d, y1 - d)]),
        ((x0, y0), (x0, y1), 1, [(x0, y0), (x0, y1), (x0 + d, y1 - d), (x0 + d, y0 + d)]),
        ((x1, y0), (x1, y1), 1, [(x1, y0), (x1, y1), (x1 - d, y1 - d), (x1 - d, y0 + d)]),
    ]


def _distribute(contour, segments, edge_points) -> dict[int, Profile]:
    """Раздать профили глубины сторон ячеек балкам, лежащим на этих сторонах.

    ``edge_points(cell, start, end, axis, tributary)`` — точки (t, d) профиля вдоль стороны;
    ``tributary`` — грузовая фигура стороны (для непрямоугольной ячейки ``None``).
    """
    ordered = [_ordered(s) for s in segments]
    loads: dict[int, Profile] = {i: [] for i in range(len(segments))}
    for cell in floor_cells(contour, segments):
        if is_rectangular(cell):
            edges = _rect_edges(cell)
        else:
            coords = list(cell.exterior.coords)
            edges = [(*_ordered((a, b)), None) for a, b in zip(coords, coords[1:], strict=False)]
        for start, end, axis, tributary in edges:
            length = end[axis] - start[axis]
            if length <= TOLERANCE_MM:
                continue
            points = edge_points(cell, start, end, axis, tributary)
            across = 1 - axis
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


def distribute_floor(contour: Contour, segments: list[tuple[Point, Point]]) -> dict[int, Profile]:
    """Профили грузовой площади для каждой балки (по индексу в ``segments``)."""

    def full(cell, start, end, axis, tributary):
        length = end[axis] - start[axis]
        if tributary is None:
            depth = cell.area / cell.length  # равномерно по периметру
            return [(0.0, depth), (length, depth)]
        x0, y0, x1, y1 = cell.bounds
        return _edge_profile(length, min(x1 - x0, y1 - y0) / 2)

    return _distribute(contour, segments, full)


def _section_length(polygon: Polygon, axis: int, at: float) -> float:
    """Длина сечения фигуры поперёк стороны (ось ``axis``) в координате ``at``."""
    x0, y0, x1, y1 = polygon.bounds
    if axis == 0:
        line = LineString([(at, y0 - 1), (at, y1 + 1)])
    else:
        line = LineString([(x0 - 1, at), (x1 + 1, at)])
    return polygon.intersection(line).length


def _zone_points(piece: Polygon, start: Point, end: Point, axis: int) -> list[tuple[float, float]]:
    """Профиль глубины части грузовой фигуры, попавшей в зону, вдоль стороны ячейки.

    Сечение выпуклой фигуры меняется линейно между вершинами; значения на концах участка
    берутся чуть внутри него (на 0,01 мм), поэтому скачки на краях зоны не размываются.
    """
    if piece.is_empty or piece.area <= 0:
        return [(0.0, 0.0), (end[axis] - start[axis], 0.0)]
    coords = sorted({round(c[axis], 6) for c in piece.exterior.coords})
    marks = sorted({start[axis], end[axis], *(c for c in coords if start[axis] < c < end[axis])})
    points = []
    for a, b in zip(marks, marks[1:], strict=False):
        delta = min(1e-3 * (b - a), 0.01)
        va = _section_length(piece, axis, a + delta)
        vb = _section_length(piece, axis, b - delta)
        points += [(a - start[axis], va), (b - start[axis], vb)]
    return points


def zone_profiles(
    contour: Contour, segments: list[tuple[Point, Point]], rects: list[tuple[float, ...]]
) -> dict[int, list[Profile]]:
    """Профили грузовой площади в пределах каждой зоны: балка → [профиль зоны 0, зоны 1, …].

    В прямоугольной ячейке берётся часть грузовой фигуры «конверта», попавшая в зону;
    в непрямоугольной — доля площади зоны в ячейке, равномерно по периметру.
    """
    result: dict[int, list[Profile]] = {i: [] for i in range(len(segments))}
    for rect in rects:
        zone = box(*rect)

        def inside(cell, start, end, axis, tributary, zone=zone):
            length = end[axis] - start[axis]
            if tributary is None:
                depth = cell.area / cell.length * cell.intersection(zone).area / cell.area
                return [(0.0, depth), (length, depth)]
            return _zone_points(Polygon(tributary).intersection(zone), start, end, axis)

        for index, profile in _distribute(contour, segments, inside).items():
            result[index].append(profile)
    return result
