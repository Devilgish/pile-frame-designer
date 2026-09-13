"""Проект каркаса: прямоугольный план на сваях → сваи, элементы каркаса, проверка."""

from __future__ import annotations

import math
from dataclasses import dataclass

from pile_frame.beam import BeamCheck, BeamLoad, check_beam
from pile_frame.materials import C245
from pile_frame.sections import TUBE_120x60x4, TUBE_120x120x5, Section

GRAVITY = 9.81  # м/с²

#: Коэффициенты надёжности по нагрузке (СП 20.13330.2016).
GAMMA_F_STEEL = 1.05  # металлические конструкции, таблица 7.1
GAMMA_F_BOARD = 1.2  # плиты заводского изготовления, таблица 7.1


def gamma_f_live(live_load_kpa: float) -> float:
    """γf для равномерной временной нагрузки: 1,3 при < 2,0 кПа, иначе 1,2 (п. 8.2.2)."""
    return 1.3 if live_load_kpa < 2.0 else 1.2


@dataclass(frozen=True)
class Project:
    """Исходные данные: размеры плана, мм; шаг свай, мм; временная нагрузка на пол, кПа."""

    width_mm: float
    length_mm: float
    pile_step_mm: float
    live_load_kpa: float
    board_thickness_mm: float = 24.0
    board_density_kg_m3: float = 1300.0

    @property
    def board_load_kpa(self) -> float:
        """Нормативная нагрузка от листов ЦСП, кПа."""
        return self.board_density_kg_m3 * GRAVITY * self.board_thickness_mm / 1e3 / 1e3


@dataclass(frozen=True)
class Member:
    """Элемент каркаса между двумя сваями, координаты в мм."""

    start: tuple[float, float]
    end: tuple[float, float]
    section: Section
    tributary_width_mm: float

    @property
    def length_mm(self) -> float:
        return math.dist(self.start, self.end)


@dataclass(frozen=True)
class Design:
    """Результат проектирования."""

    piles: list[tuple[float, float]]
    members: list[Member]
    governing_member: Member
    governing_check: BeamCheck


def _axis(size_mm: float, step_mm: float) -> list[float]:
    """Координаты рядов свай вдоль оси: равные пролёты, не больше заданного шага."""
    spans = max(1, math.ceil(size_mm / step_mm))
    return [size_mm * i / spans for i in range(spans + 1)]


def _tributary(coords: list[float], index: int) -> float:
    """Грузовая ширина ряда: половины соседних пролётов."""
    left = coords[index] - coords[index - 1] if index > 0 else 0.0
    right = coords[index + 1] - coords[index] if index < len(coords) - 1 else 0.0
    return (left + right) / 2


def _section_for_row(index: int, count: int) -> Section:
    """Крайние ряды — периметр 120×120, внутренние — 120×60."""
    return TUBE_120x120x5 if index in (0, count - 1) else TUBE_120x60x4


def _members(xs: list[float], ys: list[float]) -> list[Member]:
    """Балки по всем рядам свай в одной плоскости."""
    members = []
    for row, y in enumerate(ys):
        section, width = _section_for_row(row, len(ys)), _tributary(ys, row)
        members += [
            Member((x0, y), (x1, y), section, width) for x0, x1 in zip(xs, xs[1:], strict=False)
        ]
    for col, x in enumerate(xs):
        section, width = _section_for_row(col, len(xs)), _tributary(xs, col)
        members += [
            Member((x, y0), (x, y1), section, width) for y0, y1 in zip(ys, ys[1:], strict=False)
        ]
    return members


def _member_load(project: Project, member: Member) -> BeamLoad:
    """Нагрузка на балку с грузовой полосы, кН/м (упрощение #1: пол опирается на балку целиком)."""
    width_m = member.tributary_width_mm / 1e3
    board = project.board_load_kpa * width_m
    self_weight = member.section.mass_kg_m * GRAVITY / 1e3
    live = project.live_load_kpa * width_m
    return BeamLoad(
        dead_normative=board + self_weight,
        dead_design=board * GAMMA_F_BOARD + self_weight * GAMMA_F_STEEL,
        live_normative=live,
        live_design=live * gamma_f_live(project.live_load_kpa),
    )


def analyze(project: Project) -> Design:
    xs = _axis(project.width_mm, project.pile_step_mm)
    ys = _axis(project.length_mm, project.pile_step_mm)
    members = _members(xs, ys)
    checks = [
        (
            check_beam(
                span_mm=m.length_mm, section=m.section, steel=C245, load=_member_load(project, m)
            ),
            m,
        )
        for m in members
    ]
    check, member = max(
        checks, key=lambda cm: max(cm[0].strength_utilization, cm[0].deflection_utilization)
    )
    return Design(
        piles=[(x, y) for x in xs for y in ys],
        members=members,
        governing_member=member,
        governing_check=check,
    )
