"""Строки таблиц результатов: одни и те же для окна и для расчётной записки.

Каждая ячейка — пара (текст, значение для сортировки).
"""

from __future__ import annotations

from pile_frame.analysis import MemberCheck, NodeWeld
from pile_frame.contour import Point
from pile_frame.design import BoardCell, Member
from pile_frame.status import classify

Cell = tuple[str, float | str]

MEMBER_COLUMNS = (
    "Элемент",
    "Профиль",
    "Длина, мм",
    "M, кН·м",
    "Q, кН",
    "Изгиб, %",
    "Срез, %",
    "Прогиб, мм",
    "Прогиб, %",
    "Стенка, %",
    "Пояс, %",
    "Использование, %",
    "Итог",
)
BOARD_COLUMNS = (
    "Ячейка, мм",
    "Перемычки",
    "Пролёт листа, мм",
    "Равномерная, %",
    "Сосредоточенная, %",
    "Прогиб, мм",
    "Прогиб, %",
    "Итог",
)
PILE_COLUMNS = ("Свая", "X, мм", "Y, мм", "Реакция, кН")
WELD_COLUMNS = (
    "X, мм",
    "Y, мм",
    "Сила, кН",
    "Катет, мм",
    "Длина, мм",
    "Расчёт по",
    "Использование, %",
)


def fmt(value: float, digits: int = 1) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


def percent(value: float) -> Cell:
    return f"{value:.0%}", value


def member_label(index: int) -> str:
    return f"Б{index + 1}"


def pile_label(index: int) -> str:
    return f"С{index + 1}"


def member_row(index: int, member: Member, check: MemberCheck, unsupported: bool) -> list[Cell]:
    verdict = "нет опоры" if unsupported else classify(check.utilization).label
    return [
        (member_label(index), index),
        (member.section.name, member.section.name),
        (f"{member.length_mm:.0f}", member.length_mm),
        (fmt(check.max_moment_knm, 2), check.max_moment_knm),
        (fmt(check.max_shear_kn, 2), check.max_shear_kn),
        percent(check.strength_utilization),
        percent(check.shear_utilization),
        (fmt(check.deflection_mm), check.deflection_mm),
        percent(check.deflection_utilization),
        percent(check.web_utilization),
        percent(check.flange_utilization),
        percent(check.utilization),
        (verdict, check.utilization),
    ]


def board_row(cell: BoardCell) -> list[Cell]:
    x0, y0, x1, y1 = cell.bounds
    check = cell.check
    if cell.jumpers is None:
        jumpers, verdict = "не помогают", "нужен лист толще"
    else:
        jumpers, verdict = str(cell.jumpers), classify(check.utilization).label
    return [
        (f"{x1 - x0:.0f} × {y1 - y0:.0f}", (x1 - x0) * (y1 - y0)),
        (jumpers, -1 if cell.jumpers is None else cell.jumpers),
        (f"{check.span_mm:.0f}", check.span_mm),
        percent(check.uniform_utilization),
        percent(check.point_utilization),
        (fmt(check.deflection_mm), check.deflection_mm),
        percent(check.deflection_utilization),
        (verdict, check.utilization),
    ]


def pile_row(index: int, pile: Point, reaction_kn: float) -> list[Cell]:
    return [
        (pile_label(index), index),
        (f"{pile[0]:.0f}", pile[0]),
        (f"{pile[1]:.0f}", pile[1]),
        (fmt(reaction_kn, 2), reaction_kn),
    ]


def weld_row(weld: NodeWeld) -> list[Cell]:
    check = weld.check
    return [
        (f"{weld.point[0]:.0f}", weld.point[0]),
        (f"{weld.point[1]:.0f}", weld.point[1]),
        (fmt(check.force_kn, 2), check.force_kn),
        (str(check.leg_mm), check.leg_mm),
        (f"{check.length_mm:.0f}", check.length_mm),
        (check.governing, check.governing),
        percent(check.utilization),
    ]
