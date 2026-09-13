"""Проект каркаса: план на сваях → сваи, элементы каркаса, расчёт и проверки."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from shapely.geometry import LineString

from pile_frame.analysis import (
    GRAVITY,
    AnalysisError,
    MemberCheck,
    analyze_frame,
    gamma_f_live,
)
from pile_frame.boards import BoardSpec
from pile_frame.contour import Contour, Point
from pile_frame.materials import C245, Steel
from pile_frame.sections import Section, TUBE_120x60x4, TUBE_120x120x5
from pile_frame.sheets import LongSide, SheetLayout, layout_sheets

__all__ = ["GRAVITY", "AnalysisError", "gamma_f_live"]


@dataclass(frozen=True, kw_only=True)
class Project:
    """Исходные данные проекта.

    План задаётся контуром или, для прямоугольника, шириной и длиной, мм. Сваи можно
    передать явно; если их нет, они расставляются автоматически с шагом ``pile_step_mm``.
    """

    pile_step_mm: float
    live_load_kpa: float
    width_mm: float | None = None
    length_mm: float | None = None
    contour: Contour | None = None
    piles: tuple[Point, ...] | None = None
    perimeter_section: Section = TUBE_120x120x5
    internal_section: Section = TUBE_120x60x4
    steel: Steel = C245
    board: BoardSpec = field(default_factory=BoardSpec)
    sheet_long_side: LongSide = "x"
    sheet_offset_mm: tuple[float, float] = (0.0, 0.0)
    sheet_gap_mm: float = 3.0
    #: Ставить балки под стыками листов. Выключается, чтобы рассмотреть каркас только по сваям.
    sheet_joints: bool = True

    @property
    def outline(self) -> Contour:
        """Контур плана."""
        if self.contour is not None:
            return self.contour
        if self.width_mm is None or self.length_mm is None:
            raise ValueError("Задайте контур или ширину и длину плана.")
        w, length = self.width_mm, self.length_mm
        return Contour.from_points([(0, 0), (w, 0), (w, length), (0, length)])

    @property
    def board_load_kpa(self) -> float:
        """Нормативная нагрузка от листов ЦСП, кПа."""
        return self.board.density_kg_m3 * GRAVITY * self.board.thickness_mm / 1e3 / 1e3


@dataclass(frozen=True)
class Member:
    """Элемент каркаса между двумя узлами (сваи, пересечения балок), координаты в мм."""

    start: tuple[float, float]
    end: tuple[float, float]
    section: Section

    @property
    def length_mm(self) -> float:
        return math.dist(self.start, self.end)


@dataclass(frozen=True)
class Design:
    """Результат проектирования."""

    piles: list[tuple[float, float]]
    members: list[Member]
    checks: list[MemberCheck]
    governing_member: Member
    governing_check: MemberCheck
    reactions_kn: dict[Point, float] = field(default_factory=dict)
    piles_outside: list[Point] = field(default_factory=list)
    corners_without_piles: list[Point] = field(default_factory=list)
    unsupported_members: list[Member] = field(default_factory=list)
    sheet_layout: SheetLayout | None = None

    def failing_members(self) -> list[Member]:
        """Элементы, не прошедшие проверку, и балки без опоры на одном из концов."""
        unsupported = {id(m) for m in self.unsupported_members}
        return [
            m
            for m, c in zip(self.members, self.checks, strict=True)
            if not c.passed or id(m) in unsupported
        ]


def _axis(breakpoints: list[float], step_mm: float) -> list[float]:
    """Оси свай: через каждую вершину контура, отрезки между ними — равными пролётами ≤ шага."""
    marks = sorted(set(breakpoints))
    axis = [marks[0]]
    for start, end in zip(marks, marks[1:], strict=False):
        spans = max(1, math.ceil((end - start) / step_mm))
        axis += [start + (end - start) * i / spans for i in range(1, spans + 1)]
    return axis


def auto_piles(contour: Contour, step_mm: float) -> list[Point]:
    """Сваи в узлах осей, попавших внутрь контура или на его границу."""
    xs = _axis([x for x, _ in contour.vertices], step_mm)
    ys = _axis([y for _, y in contour.vertices], step_mm)
    return [(x, y) for y in ys for x in xs if contour.covers((x, y))]


#: Допуск, мм: сваи ближе этого к одной линии считаются стоящими на ней.
LINE_TOLERANCE_MM = 1.0


def _on_segment(point: Point, a: Point, b: Point) -> bool:
    """Точка лежит на горизонтальном или вертикальном отрезке (с допуском)."""
    (x, y), (ax, ay), (bx, by) = point, a, b
    if abs(ax - bx) <= LINE_TOLERANCE_MM:
        return abs(x - ax) <= LINE_TOLERANCE_MM and min(ay, by) <= y <= max(ay, by)
    return abs(y - ay) <= LINE_TOLERANCE_MM and min(ax, bx) <= x <= max(ax, bx)


def _perimeter_members(contour: Contour, piles: list[Point]) -> list[tuple[Point, Point]]:
    """Периметр: по каждой стороне контура от узла к узлу (вершины и сваи на стороне)."""
    segments = []
    vertices = list(contour.vertices)
    for a, b in zip(vertices, vertices[1:] + vertices[:1], strict=True):
        nodes = {a, b} | {p for p in piles if _on_segment(p, a, b)}
        ordered = sorted(nodes, key=lambda n: math.dist(a, n))
        segments += list(zip(ordered, ordered[1:], strict=False))
    return segments


def _internal_members(contour: Contour, piles: list[Point]) -> list[tuple[Point, Point]]:
    """Внутренние балки: между соседними сваями на одной линии, только внутри контура."""
    polygon, boundary = contour.polygon, contour.polygon.boundary
    segments = []
    for axis in (0, 1):
        lines: dict[int, list[Point]] = {}
        for pile in piles:
            lines.setdefault(round(pile[1 - axis]), []).append(pile)
        for line in lines.values():
            ordered = sorted(line, key=lambda p: p[axis])
            for a, b in zip(ordered, ordered[1:], strict=False):
                segment = LineString([a, b])
                if polygon.covers(segment) and not boundary.covers(segment):
                    segments.append((a, b))
    return segments


def _parts(geometry) -> list[LineString]:
    """Отрезки линии внутри многоугольника (пересечение может распасться на части)."""
    parts = getattr(geometry, "geoms", [geometry])
    return [g for g in parts if isinstance(g, LineString) and g.length > 0]


def _joint_members(
    contour: Contour,
    joints: tuple[list[float], list[float]],
    existing: list[tuple[Point, Point]],
    cover_mm: float,
) -> list[tuple[Point, Point]]:
    """Промежуточные балки под стыками листов, где рядом нет балки по сваям.

    Балка идёт по линии стыка внутри контура и делится на пролёты перпендикулярными
    балками и стыками. Отрезок не нужен, если параллельная балка ближе ``cover_mm``.
    """
    polygon = contour.polygon
    min_x, min_y, max_x, max_y = polygon.bounds
    joints_x, joints_y = joints
    segments: list[tuple[Point, Point]] = []
    for axis, positions, crossing in ((0, joints_x, joints_y), (1, joints_y, joints_x)):
        along = 1 - axis  # вдоль линии стыка меняется эта координата
        for c in positions:
            if axis == 0:
                line = LineString([(c, min_y - 1), (c, max_y + 1)])
            else:
                line = LineString([(min_x - 1, c), (max_x + 1, c)])
            for part in _parts(polygon.intersection(line)):
                ends = sorted(p[along] for p in part.coords)
                low, high = ends[0], ends[-1]
                cuts = {low, high}
                for a, b in existing:
                    if abs(a[along] - b[along]) > LINE_TOLERANCE_MM:
                        continue  # не перпендикулярна линии стыка
                    lo, hi = sorted((a[axis], b[axis]))
                    if lo <= c <= hi and low < a[along] < high:
                        cuts.add(a[along])
                beams_across = set(cuts)
                # Стык режет балку, только если рядом нет перпендикулярной балки (она уже опора).
                cuts |= {
                    t
                    for t in crossing
                    if low < t < high and all(abs(t - b) > cover_mm for b in beams_across)
                }
                points = sorted(cuts)
                for t0, t1 in zip(points, points[1:], strict=False):
                    mid = (t0 + t1) / 2
                    covered = False
                    for a, b in existing:
                        if abs(a[axis] - b[axis]) > LINE_TOLERANCE_MM:
                            continue  # не параллельна
                        lo, hi = sorted((a[along], b[along]))
                        if abs(a[axis] - c) <= cover_mm and lo <= mid <= hi:
                            covered = True
                            break
                    if covered:
                        continue
                    if axis == 0:
                        segments.append(((c, t0), (c, t1)))
                    else:
                        segments.append(((t0, c), (t1, c)))
    return segments


def _members(
    contour: Contour,
    piles: list[Point],
    perimeter_section: Section,
    internal_section: Section,
    layout: SheetLayout | None = None,
) -> list[Member]:
    """Балки каркаса в одной плоскости: периметр, балки по сваям и под стыками листов."""
    perimeter = _perimeter_members(contour, piles)
    internal = _internal_members(contour, piles)
    if layout is not None:
        internal += _joint_members(
            contour,
            (layout.joints_x, layout.joints_y),
            perimeter + internal,
            internal_section.width_mm / 2,
        )
    typed = [(seg, perimeter_section) for seg in perimeter]
    typed += [(seg, internal_section) for seg in internal]
    return [Member(a, b, section) for (a, b), section in _split_at_nodes(typed)]


def _split_at_nodes(typed: list[tuple[tuple[Point, Point], Section]]):
    """Разрезать балки в узлах, где к ним примыкают другие балки (Т-образные примыкания)."""
    ends = {p for (a, b), _ in typed for p in (a, b)}
    result = []
    for (a, b), section in typed:
        inner = [
            p
            for p in ends
            if p not in (a, b)
            and _on_segment(p, a, b)
            and LINE_TOLERANCE_MM < math.dist(a, p) < math.dist(a, b) - LINE_TOLERANCE_MM
        ]
        points = [a, *sorted(inner, key=lambda p: math.dist(a, p)), b]
        result += [((p, q), section) for p, q in zip(points, points[1:], strict=False)]
    return result


def analyze(project: Project) -> Design:
    contour = project.outline
    piles = (
        list(project.piles)
        if project.piles is not None
        else auto_piles(contour, project.pile_step_mm)
    )
    outside = [p for p in piles if not contour.covers(p)]
    supports = [p for p in piles if contour.covers(p)]
    layout = layout_sheets(
        contour,
        project.board,
        long_side=project.sheet_long_side,
        offset_mm=project.sheet_offset_mm,
        gap_mm=project.sheet_gap_mm,
    )
    members = _members(
        contour,
        supports,
        project.perimeter_section,
        project.internal_section,
        layout if project.sheet_joints else None,
    )
    corners = [
        v
        for v in contour.vertices
        if not any(math.dist(v, p) <= LINE_TOLERANCE_MM for p in supports)
    ]
    unsupported = [m for m in members if m.start in corners or m.end in corners]
    checks, reactions = analyze_frame(project, contour, supports, members)
    check, member = max(zip(checks, members, strict=True), key=lambda cm: cm[0].utilization)
    return Design(
        piles=piles,
        members=members,
        checks=checks,
        governing_member=member,
        governing_check=check,
        reactions_kn=reactions,
        piles_outside=outside,
        corners_without_piles=corners,
        unsupported_members=unsupported,
        sheet_layout=layout,
    )
