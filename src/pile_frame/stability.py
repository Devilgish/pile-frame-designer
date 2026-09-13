"""Местная устойчивость стенок и поясных листов замкнутых профилей (СП 16.13330.2017, 8.5).

Расчётная высота стенки и ширина поясного листа берутся без радиусов скругления:
hef = h − 2t, bf = b − 2t. Это чуть строже реального профиля (в запас).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from pile_frame.materials import STEEL_E_MPA
from pile_frame.sections import Section

#: Предельная условная гибкость стенки без местного напряжения (п. 8.5.1).
WEB_SLENDERNESS_LIMIT = 3.5


@dataclass(frozen=True)
class LocalStability:
    web_slenderness: float
    flange_slenderness: float
    flange_limit: float

    @property
    def web_utilization(self) -> float:
        return self.web_slenderness / WEB_SLENDERNESS_LIMIT

    @property
    def flange_utilization(self) -> float:
        return self.flange_slenderness / self.flange_limit


def check_local_stability(section: Section, *, ry_mpa: float, sigma_c_mpa: float) -> LocalStability:
    """Условные гибкости стенки (п. 8.5.1) и сжатого поясного листа (формула 98)."""
    root = math.sqrt(ry_mpa / STEEL_E_MPA)
    t = section.thickness_mm
    web = (section.height_mm - 2 * t) / t * root
    flange = (section.width_mm - 2 * t) / t * root
    # σc не больше Ry (п. 8.5.18); при σc → 0 пояс не сжат и предел не ограничивает.
    sigma = min(sigma_c_mpa, ry_mpa)
    limit = 1.5 * math.sqrt(ry_mpa / sigma) if sigma > 0 else math.inf
    return LocalStability(web_slenderness=web, flange_slenderness=flange, flange_limit=limit)
