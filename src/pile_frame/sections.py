"""Сортамент профилей: гнутые замкнутые сварные профили по ГОСТ 30245-2003."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Section:
    """Геометрические характеристики сечения относительно оси изгиба (стенка вертикально)."""

    name: str
    height_mm: float
    width_mm: float
    thickness_mm: float
    mass_kg_m: float
    ix_cm4: float
    wx_cm3: float


TUBE_120x120x5 = Section("120×120×5", 120, 120, 5, mass_kg_m=17.55, ix_cm4=485.3, wx_cm3=80.88)
TUBE_120x60x4 = Section("120×60×4", 120, 60, 4, mass_kg_m=10.48, ix_cm4=240.7, wx_cm3=40.12)
