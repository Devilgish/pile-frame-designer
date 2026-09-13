"""Угловые сварные швы примыканий балок по СП 16.13330.2017.

Примыкающая балка приваривается двумя вертикальными угловыми швами по своим стенкам.
Сварка ручная: βf = 0,7, βz = 1,0 (таблица 39). Расчётная длина шва — полная длина минус 1 см
на каждый непрерывный участок (п. 14.1.16).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from pile_frame.beam import GAMMA_C
from pile_frame.materials import Steel
from pile_frame.sections import Section

#: Rwf металла шва, Н/мм² (таблица Г.2).
ELECTRODES = {"Э42": 180.0, "Э46": 200.0, "Э50": 215.0}
DEFAULT_ELECTRODE = "Э46"
BETA_F = 0.7
BETA_Z = 1.0
#: Катет по умолчанию, мм; не больше 1,2·t более тонкого элемента.
DEFAULT_LEG_MM = 4


@dataclass(frozen=True)
class WeldCheck:
    force_kn: float
    leg_mm: int
    length_mm: float
    governing: str  # «металл шва» или «граница сплавления»
    utilization: float


def fillet_leg_mm(section: Section) -> int:
    return min(DEFAULT_LEG_MM, math.floor(1.2 * section.thickness_mm))


def weld_length_mm(section: Section) -> float:
    """Два вертикальных шва по стенкам, каждый короче высоты на 1 см."""
    return 2 * (section.height_mm - 10)


def _rwz(steel: Steel, thickness_mm: float) -> float:
    """Rwz = 0,45·Run (таблица 4)."""
    return 0.45 * steel.run_mpa(thickness_mm)


def electrode_issue(steel: Steel, electrode: str, *, thickness_mm: float) -> str | None:
    """Условие п. 14.1.8 для ручной сварки: 1,1·Rwz ≤ Rwf ≤ Rwz·βz/βf."""
    rwf, rwz = ELECTRODES[electrode], _rwz(steel, thickness_mm)
    low, high = 1.1 * rwz, rwz * BETA_Z / BETA_F
    if low <= rwf <= high:
        return None
    return (
        f"Электрод {electrode} (Rwf = {rwf:g} Н/мм²) не подходит для стали {steel.name}: "
        f"по п. 14.1.8 СП 16.13330.2017 нужно {low:.0f} ≤ Rwf ≤ {high:.0f} Н/мм²."
    )


def check_weld(force_n: float, section: Section, steel: Steel, electrode: str) -> WeldCheck:
    """Проверка шва на силу, передаваемую в узле, по формулам (176) или (177)."""
    leg, length = fillet_leg_mm(section), weld_length_mm(section)
    rwf, rwz = ELECTRODES[electrode], _rwz(steel, section.thickness_mm)
    if BETA_F * rwf / (BETA_Z * rwz) <= 1:
        governing, capacity = "металл шва", BETA_F * leg * length * rwf * GAMMA_C
    else:
        governing, capacity = "граница сплавления", BETA_Z * leg * length * rwz * GAMMA_C
    return WeldCheck(abs(force_n) / 1e3, leg, length, governing, abs(force_n) / capacity)
