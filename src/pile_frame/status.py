"""Статус проверки элемента: текст и иконка, а не только цвет."""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pile_frame.design import Design

#: Загрузка, начиная с которой элемент проходит, но с запасом меньше 10 %.
WARNING_THRESHOLD = 0.9


class Status(Enum):
    """Статус с подписью и иконкой. Цвет берётся из темы по имени статуса."""

    OK = ("ok", "Проходит", "check")
    WARNING = ("warning", "Проходит, запас меньше 10 %", "alert")
    FAIL = ("fail", "Не проходит", "cross")

    def __init__(self, color_token: str, label: str, icon: str) -> None:
        self.color_token = color_token
        self.label = label
        self.icon = icon


def classify(utilization: float) -> Status:
    """Статус по коэффициенту использования (1,0 — ровно на пределе)."""
    if utilization > 1.0:
        return Status.FAIL
    if utilization >= WARNING_THRESHOLD:
        return Status.WARNING
    return Status.OK


#: Заголовок, когда всё проходит с запасом, но есть замечания (электрод, опирание листов).
REMARKS_LABEL = "Проходит, есть замечания"


def design_status(design: Design) -> tuple[Status, str, float]:
    """Итог проекта: статус, заголовок и наибольшая загрузка (элементы и листы ЦСП)."""
    board = max((cell.check.utilization for cell in design.board_cells), default=0.0)
    utilization = max(design.governing_check.utilization, board)
    boards_fail = any(not cell.check.passed for cell in design.board_cells)
    has_errors = bool(design.failing_members() or design.piles_outside or boards_fail)
    status = Status.FAIL if has_errors and utilization <= 1.0 else classify(utilization)
    if (design.electrode_issue or design.bearing_issues) and status is Status.OK:
        return Status.WARNING, REMARKS_LABEL, utilization
    return status, status.label, utilization
