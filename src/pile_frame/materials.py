"""Стали по СП 16.13330.2017."""

from __future__ import annotations

from dataclasses import dataclass

#: Модуль упругости прокатной стали, Н/мм² (СП 16.13330.2017, таблица Г.10).
STEEL_E_MPA = 2.06e5


@dataclass(frozen=True)
class Steel:
    """Сталь с расчётным сопротивлением по пределу текучести Ry, Н/мм²."""

    name: str
    ry_mpa: float


#: С245, толщина 2–20 мм: Ry = 240 Н/мм² (таблица В.3; для гнутых профилей по п. 6.2).
C245 = Steel("С245", ry_mpa=240.0)
