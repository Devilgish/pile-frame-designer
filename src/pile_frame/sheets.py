"""Раскладка листов ЦСП по контуру ровной сеткой со сплошными стыками."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from shapely.geometry import box

from pile_frame.boards import BoardSpec
from pile_frame.contour import Contour

LongSide = Literal["x", "y"]

#: Если с каждой стороны листа срезается не больше этого, лист считается целым (подрезка кромки).
EDGE_TRIM_TOLERANCE_MM = 5.0


@dataclass(frozen=True)
class Sheet:
    """Лист в раскладке: номинальный прямоугольник и площадь куска внутри контура."""

    x0: float
    y0: float
    x1: float
    y1: float
    piece_area_mm2: float
    whole: bool


@dataclass(frozen=True)
class SheetLayout:
    sheets: list[Sheet]
    sheet_area_mm2: float
    #: Координаты сплошных стыков внутри контура: вертикальные (x) и горизонтальные (y), мм.
    joints_x: list[float]
    joints_y: list[float]

    @property
    def whole_count(self) -> int:
        return sum(1 for s in self.sheets if s.whole)

    @property
    def cut_count(self) -> int:
        return sum(1 for s in self.sheets if not s.whole)

    @property
    def offcut_m2(self) -> float:
        """Обрезки: каждый резаный кусок расходует целый лист."""
        cut = [s for s in self.sheets if not s.whole]
        return (len(cut) * self.sheet_area_mm2 - sum(s.piece_area_mm2 for s in cut)) / 1e6


def _starts(low: float, high: float, pitch: float, offset: float) -> list[float]:
    """Начала листов вдоль оси: сетка с шагом ``pitch``, сдвинутая на ``offset``."""
    first = low + offset % pitch
    if first > low:
        first -= pitch
    count = math.ceil((high - first) / pitch)
    return [first + i * pitch for i in range(count)]


def layout_sheets(
    contour: Contour,
    board: BoardSpec,
    *,
    long_side: LongSide = "x",
    offset_mm: tuple[float, float] = (0.0, 0.0),
    gap_mm: float = 3.0,
) -> SheetLayout:
    """Разложить листы по контуру. Сетка начинается от левого верхнего угла габарита."""
    size_x, size_y = (
        (board.length_mm, board.width_mm) if long_side == "x" else (board.width_mm, board.length_mm)
    )
    polygon = contour.polygon
    min_x, min_y, max_x, max_y = polygon.bounds
    xs = _starts(min_x, max_x, size_x + gap_mm, offset_mm[0])
    ys = _starts(min_y, max_y, size_y + gap_mm, offset_mm[1])

    sheets = []
    for y0 in ys:
        for x0 in xs:
            x1, y1 = x0 + size_x, y0 + size_y
            piece = polygon.intersection(box(x0, y0, x1, y1))
            if piece.area <= 0:
                continue
            t = EDGE_TRIM_TOLERANCE_MM
            inner = box(x0 + t, y0 + t, x1 - t, y1 - t)
            sheets.append(Sheet(x0, y0, x1, y1, piece.area, piece.buffer(1e-6).covers(inner)))

    joints_x = [x + size_x + gap_mm / 2 for x in xs[:-1]]
    joints_y = [y + size_y + gap_mm / 2 for y in ys[:-1]]
    return SheetLayout(
        sheets=sheets,
        sheet_area_mm2=size_x * size_y,
        joints_x=[x for x in joints_x if min_x < x < max_x],
        joints_y=[y for y in joints_y if min_y < y < max_y],
    )
