"""Замечания к исходным данным: ошибка (расчёт невозможен) или предупреждение."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Severity = Literal["error", "warning"]


@dataclass(frozen=True)
class Issue:
    """Замечание к полю ввода. ``field`` совпадает с именем параметра."""

    field: str
    message: str
    severity: Severity = "error"


def errors(issues: list[Issue]) -> list[Issue]:
    return [i for i in issues if i.severity == "error"]
