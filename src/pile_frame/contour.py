"""Контур плана: замкнутый ортогональный многоугольник, координаты в мм."""

from __future__ import annotations

from dataclasses import dataclass

from shapely.geometry import Point as ShapelyPoint
from shapely.geometry import Polygon

Point = tuple[float, float]


class ContourError(ValueError):
    """Контур нельзя построить; текст исключения объясняет причину пользователю."""


@dataclass(frozen=True)
class Contour:
    """Контур из вершин по порядку обхода; последняя вершина соединяется с первой."""

    vertices: tuple[Point, ...]

    @classmethod
    def from_points(cls, points: list[Point]) -> Contour:
        """Построить контур, проверив, что он замкнутый, ортогональный и простой."""
        vertices = [(float(x), float(y)) for x, y in points]
        if len(vertices) > 1 and vertices[0] == vertices[-1]:
            vertices.pop()
        if len(vertices) < 4:
            raise ContourError("Контур должен иметь не меньше 4 вершин.")
        for start, end in zip(vertices, vertices[1:] + vertices[:1], strict=True):
            if start == end:
                raise ContourError("В контуре есть две одинаковые вершины подряд.")
            if start[0] != end[0] and start[1] != end[1]:
                raise ContourError(
                    "Каждая сторона контура должна быть горизонтальной или вертикальной."
                )
        if not Polygon(vertices).is_valid:
            raise ContourError("Контур пересекает сам себя.")
        return cls(tuple(vertices))

    @property
    def area_mm2(self) -> float:
        return self.polygon.area

    @property
    def polygon(self) -> Polygon:
        return Polygon(self.vertices)

    def covers(self, point: Point) -> bool:
        """Точка внутри контура или на его границе."""
        return bool(self.polygon.covers(ShapelyPoint(point)))
