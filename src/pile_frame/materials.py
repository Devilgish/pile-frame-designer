"""Стали по СП 16.13330.2017."""

from __future__ import annotations

from dataclasses import dataclass

#: Модуль упругости прокатной стали, Н/мм² (СП 16.13330.2017, таблица Г.10).
STEEL_E_MPA = 2.06e5


@dataclass(frozen=True)
class Steel:
    """Сталь с расчётным сопротивлением Ry по толщине проката.

    ``ranges`` — строки таблицы: (толщина от, толщина до включительно, Ry), мм и Н/мм².
    Для гнутых профилей Ry принимается как для листового проката (п. 6.2), таблица В.3.
    """

    name: str
    ranges: tuple[tuple[float, float, float], ...]

    def ry_mpa(self, thickness_mm: float) -> float:
        for low, high, ry in self.ranges:
            if low <= thickness_mm <= high:
                return ry
        raise ValueError(
            f"Для стали {self.name} толщина {thickness_mm:g} мм не приведена в таблице В.3 "
            "СП 16.13330.2017."
        )


# Таблица В.3. «Св. 10 до 20» у С255 записано как верхняя граница 20 после строки «до 10».
C235 = Steel("С235", ((2.0, 4.0, 230),))
C245 = Steel("С245", ((2.0, 20.0, 240),))
C255 = Steel("С255", ((2.0, 3.9, 250), (4.0, 10.0, 240), (10.0, 20.0, 240), (20.0, 40.0, 230)))
C355 = Steel("С355", ((2.0, 16.0, 350), (16.0, 40.0, 340)))

#: Стали, доступные для выбора.
STEELS = {steel.name: steel for steel in (C235, C245, C255, C355)}
