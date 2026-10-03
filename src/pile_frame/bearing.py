"""Опирание кромок листов ЦСП на верхние полки балок.

Кромка листа должна лежать на плоской части полки так, чтобы саморез, поставленный не ближе
допустимого расстояния от кромки (рекомендации производителя), попал на полку. Скругления
углов профиля в опору не входят: наружный радиус по ГОСТ 30245-2003, примечание 2 к табл. 1, 2.
Недостаток только показывается — каркас не исправляется.
"""

from __future__ import annotations

from dataclasses import dataclass

from shapely.geometry import box

from pile_frame.contour import Contour, Point
from pile_frame.sections import Section
from pile_frame.sheets import SheetLayout

TOLERANCE_MM = 0.5


@dataclass(frozen=True)
class BearingIssue:
    """Участок кромки листа, где плоской части полки меньше, чем нужно под саморез."""

    start: Point
    end: Point
    bearing_mm: float
    required_mm: float


def corner_radius_mm(thickness_mm: float) -> float:
    """Наружный радиус скругления угла гнутого профиля (ГОСТ 30245-2003)."""
    if thickness_mm < 6:
        return 2.0 * thickness_mm
    if thickness_mm <= 10:
        return 2.5 * thickness_mm
    return 3.0 * thickness_mm


def flat_width_mm(section: Section) -> float:
    """Ширина плоской части верхней полки, мм."""
    return section.width_mm - 2 * corner_radius_mm(section.thickness_mm)


def _edges(contour: Contour, layout: SheetLayout):
    """Кромки кусков листов: ось (0 — кромка вдоль X), координата, участок, сторона листа."""
    for sheet in layout.sheets:
        piece = contour.polygon.intersection(box(sheet.x0, sheet.y0, sheet.x1, sheet.y1))
        for part in getattr(piece, "geoms", [piece]):
            if part.geom_type != "Polygon":
                continue
            coords = list(part.exterior.coords)
            for (ax, ay), (bx, by) in zip(coords, coords[1:], strict=False):
                if abs(ay - by) <= TOLERANCE_MM:
                    axis, level, low, high = 0, ay, min(ax, bx), max(ax, bx)
                    probe = ((ax + bx) / 2, ay + 1)
                elif abs(ax - bx) <= TOLERANCE_MM:
                    axis, level, low, high = 1, ax, min(ay, by), max(ay, by)
                    probe = (ax + 1, (ay + by) / 2)
                else:
                    continue
                if high - low <= TOLERANCE_MM:
                    continue
                inward = 1 if part.buffer(1e-6).contains(box(*probe, *probe)) else -1
                yield axis, level, low, high, inward


def bearing_issues(
    contour: Contour,
    layout: SheetLayout,
    beams: list[tuple[Point, Point, Section]],
    required_mm: float,
) -> list[BearingIssue]:
    """Участки кромок листов, где опора на плоскую часть полки меньше ``required_mm``."""
    issues = []
    for axis, level, low, high, inward in _edges(contour, layout):
        along = 0 if axis == 0 else 1  # вдоль кромки меняется эта координата
        across = 1 - along
        supports = []
        for a, b, section in beams:
            if abs(a[across] - b[across]) > TOLERANCE_MM:
                continue  # не параллельна кромке
            centre = a[across]
            if abs(centre - level) > section.width_mm / 2:
                continue  # кромка не над полкой
            lo, hi = sorted((a[along], b[along]))
            if hi <= low or lo >= high:
                continue
            half = flat_width_mm(section) / 2
            # Плоская часть полки со стороны листа, считая от кромки.
            value = centre + half - level if inward > 0 else level - (centre - half)
            supports.append((lo, hi, max(0.0, value)))
        marks = sorted({low, high, *(t for s in supports for t in s[:2] if low < t < high)})
        deficient: list[tuple[float, float, float]] = []
        for t0, t1 in zip(marks, marks[1:], strict=False):
            mid = (t0 + t1) / 2
            value = max((v for lo, hi, v in supports if lo <= mid <= hi), default=0.0)
            if value >= required_mm:
                continue
            if deficient and abs(deficient[-1][1] - t0) <= TOLERANCE_MM:
                start, _, worst = deficient[-1]
                deficient[-1] = (start, t1, min(worst, value))
            else:
                deficient.append((t0, t1, value))
        for t0, t1, value in deficient:
            if axis == 0:
                start, end = (t0, level), (t1, level)
            else:
                start, end = (level, t0), (level, t1)
            issues.append(BearingIssue(start, end, value, required_mm))
    return issues
