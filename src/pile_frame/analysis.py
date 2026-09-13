"""Расчёт каркаса как перекрёстной системы балок по СП 16.13330.2017 и СП 20.13330.2016.

Схема: все линии балок неразрезные, в пересечениях общий прогиб, сваи — шарнирные опоры,
кручение труб не учитывается (в запас). Нагрузка с пола передаётся методом «конверта».
Проверки: прочность при изгибе (формула 41), срез (формула 42), прогиб (таблица Д.1).
"""

from __future__ import annotations

import bisect
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from pile_frame.beam import GAMMA_C, LIVE_SHARE_FOR_DEFLECTION, deflection_limit_mm
from pile_frame.contour import Contour, Point
from pile_frame.floor_load import Profile, distribute_floor
from pile_frame.grillage import Grillage
from pile_frame.materials import STEEL_E_MPA
from pile_frame.sections import Section
from pile_frame.stability import check_local_stability
from pile_frame.welds import WeldCheck, check_weld

if TYPE_CHECKING:
    from pile_frame.design import Member, Project

GRAVITY = 9.81  # м/с²
#: Коэффициенты надёжности по нагрузке (СП 20.13330.2016, таблица 7.1).
GAMMA_F_STEEL = 1.05  # металлические конструкции
GAMMA_F_BOARD = 1.2  # плиты заводского изготовления
#: Расчётное сопротивление срезу Rs = 0,58·Ry (СП 16.13330.2017, таблица 2).
SHEAR_RATIO = 0.58
#: На сколько конечных элементов делится каждая балка (прогибы считаются в узлах).
SUBDIVISIONS = 4
NODE_TOLERANCE_MM = 0.5


def gamma_f_live(live_load_kpa: float) -> float:
    """γf для равномерной временной нагрузки: 1,3 при < 2,0 кПа, иначе 1,2 (п. 8.2.2)."""
    return 1.3 if live_load_kpa < 2.0 else 1.2


def static_moment_mm3(section: Section) -> float:
    """Статический момент половины замкнутого профиля относительно нейтральной оси, мм³.

    Радиусы скругления углов не учитываются (небольшой запас).
    """
    b, h, t = section.width_mm, section.height_mm, section.thickness_mm
    flange = b * t * (h - t) / 2
    webs = 2 * t * (h / 2 - t) ** 2 / 2
    return flange + webs


@dataclass(frozen=True)
class MemberCheck:
    """Результат проверок элемента."""

    strength_utilization: float
    shear_utilization: float
    deflection_mm: float
    deflection_limit_mm: float
    max_moment_knm: float
    max_shear_kn: float
    web_utilization: float = 0.0
    flange_utilization: float = 0.0

    @property
    def deflection_utilization(self) -> float:
        return self.deflection_mm / self.deflection_limit_mm

    @property
    def utilization(self) -> float:
        return max(
            self.strength_utilization,
            self.shear_utilization,
            self.deflection_utilization,
            self.web_utilization,
            self.flange_utilization,
        )

    @property
    def strength_ok(self) -> bool:
        return self.strength_utilization <= 1.0

    @property
    def shear_ok(self) -> bool:
        return self.shear_utilization <= 1.0

    @property
    def deflection_ok(self) -> bool:
        return self.deflection_utilization <= 1.0

    @property
    def passed(self) -> bool:
        return self.utilization <= 1.0


@dataclass(frozen=True)
class NodeWeld:
    """Сварное примыкание в узле пересечения балок."""

    point: Point
    check: WeldCheck


class AnalysisError(RuntimeError):
    """Схема геометрически изменяема (например, нет свай): расчёт невозможен."""


def _bay(coords: list[float], value: float) -> float:
    """Ширина ячейки свай вдоль оси для точки: расстояние между соседними осями свай."""
    if len(coords) < 2:
        return math.inf
    index = bisect.bisect_left(coords, value - NODE_TOLERANCE_MM)
    on_axis = index < len(coords) and abs(coords[index] - value) <= NODE_TOLERANCE_MM
    if on_axis:
        spans = []
        if index > 0:
            spans.append(coords[index] - coords[index - 1])
        if index < len(coords) - 1:
            spans.append(coords[index + 1] - coords[index])
        return min(spans)
    if 0 < index < len(coords):
        return coords[index] - coords[index - 1]
    return math.inf


def _clip_profile(profile: Profile, start: float, end: float) -> Profile:
    """Часть профиля нагрузки на участке [start, end] в координатах этого участка."""
    parts = []
    for s0, s1, d0, d1 in profile:
        low, high = max(s0, start), min(s1, end)
        if high - low <= 1e-9:
            continue

        def depth(s: float, s0=s0, s1=s1, d0=d0, d1=d1) -> float:
            return d0 + (d1 - d0) * (s - s0) / (s1 - s0)

        parts.append((low - start, high - start, depth(low), depth(high)))
    return parts


def analyze_frame(
    project: Project, contour: Contour, supports: list[Point], members: list[Member]
) -> tuple[list[MemberCheck], dict[Point, float], list[NodeWeld]]:
    """Проверки элементов, реакции свай (кН) и сварные примыкания в узлах."""
    profiles = distribute_floor(contour, [(m.start, m.end) for m in members])
    live_gamma = gamma_f_live(project.live_load_kpa)
    # Давление на пол, Н/мм² (1 кПа = 1e-3 Н/мм²), и коэффициент к весу металла.
    design_combo = (
        (project.board_load_kpa * GAMMA_F_BOARD + project.live_load_kpa * live_gamma) * 1e-3,
        GAMMA_F_STEEL,
    )
    deflection_combo = (
        (project.board_load_kpa + LIVE_SHARE_FOR_DEFLECTION * project.live_load_kpa) * 1e-3,
        1.0,
    )

    design, sub_design, nodes_design = _solve(members, profiles, supports, *design_combo)
    deflection, _, nodes_deflection = _solve(members, profiles, supports, *deflection_combo)

    pile_xs = sorted({p[0] for p in supports})
    pile_ys = sorted({p[1] for p in supports})
    checks = []
    for index, member in enumerate(members):
        section = member.section
        subs = sub_design[index]
        moments, shears = [], []
        for beam in subs:
            length = design.beam_length(beam)
            for s in (0.0, length / 2, length):
                moments.append(abs(design.moment_at(beam, s)))
            shears.append(abs(design.shear_at(beam, 0.0)))
            shears.append(abs(design.shear_at(beam, length)))
        max_moment, max_shear = max(moments), max(shears)
        ry = project.steel.ry_mpa(section.thickness_mm)
        strength = max_moment / (section.wx_cm3 * 1e3 * ry * GAMMA_C)
        tau = (
            max_shear
            * static_moment_mm3(section)
            / (section.ix_cm4 * 1e4 * 2 * section.thickness_mm)
        )
        shear = tau / (SHEAR_RATIO * ry * GAMMA_C)
        stability = check_local_stability(
            section, ry_mpa=ry, sigma_c_mpa=max_moment / (section.wx_cm3 * 1e3 * GAMMA_C)
        )

        worst: tuple[float, float] | None = None  # прогиб и предел в худшей точке
        for node, point in nodes_deflection[index]:
            span = min(_bay(pile_xs, point[0]), _bay(pile_ys, point[1]))
            if math.isinf(span):
                span = member.length_mm
            limit = deflection_limit_mm(span)
            value = abs(deflection.deflection(node))
            if worst is None or value / limit > worst[0] / worst[1]:
                worst = (value, limit)
        checks.append(
            MemberCheck(
                strength_utilization=strength,
                shear_utilization=shear,
                deflection_mm=worst[0],
                deflection_limit_mm=worst[1],
                max_moment_knm=max_moment / 1e6,
                max_shear_kn=max_shear / 1e3,
                web_utilization=stability.web_utilization,
                flange_utilization=stability.flange_utilization,
            )
        )

    reactions = {}
    for pile in supports:
        node = design.node_at(pile)
        reactions[pile] = design.reaction(node) / 1e3 if node is not None else 0.0
    welds = _welds(project, members, design, nodes_design, supports)
    return checks, reactions, welds


def _welds(project, members, design, nodes, supports) -> list[NodeWeld]:
    """Швы в узлах, где балки одного направления опираются на балки другого (кроме свай)."""
    support_keys = {_key(p) for p in supports}
    touching: dict[tuple[int, int], tuple[int, Point, list[Section]]] = {}
    for index, member in enumerate(members):
        for node, point in (nodes[index][0], nodes[index][-1]):
            key = _key(point)
            if key in support_keys:
                continue
            entry = touching.setdefault(key, (node, point, []))
            entry[2].append(member.section)
    welds = []
    for node, point, sections in touching.values():
        force = design.result.transfer_force(node)
        if force <= 0:
            continue
        thinnest = min(sections, key=lambda s: s.thickness_mm)
        welds.append(NodeWeld(point, check_weld(force, thinnest, project.steel, project.electrode)))
    return sorted(welds, key=lambda w: (w.point[1], w.point[0]))


class _Solved:
    """Решённый грильяж с поиском узлов по координатам."""

    def __init__(self, model: Grillage, keys: dict[tuple[int, int], int]) -> None:
        self.model = model
        self.keys = keys
        try:
            self.result = model.solve()
        except np.linalg.LinAlgError as error:
            raise AnalysisError("Каркас не закреплён: проверьте расстановку свай.") from error

    def beam_length(self, beam: int) -> float:
        return self.model.beams[beam].length(self.model.nodes)

    def moment_at(self, beam: int, s: float) -> float:
        return self.result.moment_at(beam, s)

    def shear_at(self, beam: int, s: float) -> float:
        return self.result.shear_at(beam, s)

    def deflection(self, node: int) -> float:
        return self.result.deflection(node)

    def reaction(self, node: int) -> float:
        return self.result.reaction(node)

    def node_at(self, point: Point) -> int | None:
        return self.keys.get(_key(point))


def _key(point: Point) -> tuple[int, int]:
    return (round(point[0] / NODE_TOLERANCE_MM), round(point[1] / NODE_TOLERANCE_MM))


def _solve(members, profiles, supports, pressure, steel_gamma):
    model = Grillage()
    keys: dict[tuple[int, int], int] = {}
    support_keys = {_key(p) for p in supports}

    def node(point: Point) -> int:
        key = _key(point)
        if key not in keys:
            keys[key] = model.node(*point, support=key in support_keys)
        return keys[key]

    sub_beams: list[list[int]] = []
    member_nodes: list[list[tuple[int, Point]]] = []
    for index, member in enumerate(members):
        (ax, ay), (bx, by) = member.start, member.end
        if (ax, ay) > (bx, by):
            (ax, ay), (bx, by) = (bx, by), (ax, ay)
        length = member.length_mm
        ei = STEEL_E_MPA * member.section.ix_cm4 * 1e4
        self_weight = member.section.mass_kg_m * GRAVITY / 1e3 * steel_gamma  # Н/мм
        # Профиль нагрузки задан от меньшей координаты — как и порядок узлов здесь.
        points = [
            (ax + (bx - ax) * k / SUBDIVISIONS, ay + (by - ay) * k / SUBDIVISIONS)
            for k in range(SUBDIVISIONS + 1)
        ]
        ids = [node(p) for p in points]
        beams = []
        for k in range(SUBDIVISIONS):
            beam = model.beam(ids[k], ids[k + 1], ei)
            start, end = length * k / SUBDIVISIONS, length * (k + 1) / SUBDIVISIONS
            model.line_load(beam, self_weight)
            for s0, s1, d0, d1 in _clip_profile(profiles[index], start, end):
                model.line_load(beam, pressure * d0, pressure * d1, s0, s1)
            beams.append(beam)
        sub_beams.append(beams)
        member_nodes.append(list(zip(ids, points, strict=True)))
    return _Solved(model, keys), sub_beams, member_nodes
