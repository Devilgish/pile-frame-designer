"""Статус проверки элемента: текст и иконка, а не только цвет."""

from __future__ import annotations

from enum import Enum

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
