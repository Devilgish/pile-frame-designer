"""Проверка однопролётной шарнирно опёртой балки по СП 16.13330.2017."""

from __future__ import annotations

from dataclasses import dataclass

from pile_frame.materials import STEEL_E_MPA, Steel
from pile_frame.sections import Section

#: Коэффициент условий работы γc (СП 16.13330.2017, таблица 1, примечание 5).
GAMMA_C = 1.0

#: Доля временной нагрузки в сочетании для прогиба (СП 20.13330.2016, таблица Д.1, п. 2а).
LIVE_SHARE_FOR_DEFLECTION = 0.35

#: Опорные точки таблицы Д.1, п. 2а: (пролёт, мм; знаменатель n в f_u = l/n).
_DEFLECTION_TABLE = ((1000, 120), (3000, 150), (6000, 200), (24000, 250), (36000, 300))


@dataclass(frozen=True)
class BeamLoad:
    """Равномерно распределённая нагрузка на балку, кН/м."""

    dead_normative: float
    dead_design: float
    live_normative: float
    live_design: float


@dataclass(frozen=True)
class BeamCheck:
    """Результат проверки балки."""

    strength_utilization: float
    deflection_mm: float
    deflection_limit_mm: float

    @property
    def strength_ok(self) -> bool:
        return self.strength_utilization <= 1.0

    @property
    def deflection_utilization(self) -> float:
        return self.deflection_mm / self.deflection_limit_mm

    @property
    def deflection_ok(self) -> bool:
        return self.deflection_utilization <= 1.0

    @property
    def passed(self) -> bool:
        return self.strength_ok and self.deflection_ok


def deflection_limit_mm(span_mm: float) -> float:
    """Предельный прогиб по таблице Д.1, п. 2а, с линейной интерполяцией f_u."""
    points = [(span, span / n) for span, n in _DEFLECTION_TABLE]
    first_span, first_n = _DEFLECTION_TABLE[0]
    last_span, last_n = _DEFLECTION_TABLE[-1]
    if span_mm <= first_span:
        return span_mm / first_n
    if span_mm >= last_span:
        return span_mm / last_n
    for (l0, f0), (l1, f1) in zip(points, points[1:], strict=False):
        if l0 <= span_mm <= l1:
            return f0 + (f1 - f0) * (span_mm - l0) / (l1 - l0)
    raise AssertionError("unreachable")


def check_beam(*, span_mm: float, section: Section, steel: Steel, load: BeamLoad) -> BeamCheck:
    """Проверить балку на прочность при изгибе и по прогибу."""
    # 1 кН/м = 1 Н/мм
    q_design = load.dead_design + load.live_design
    moment_n_mm = q_design * span_mm**2 / 8
    stress_mpa = moment_n_mm / (section.wx_cm3 * 1e3)

    q_deflection = load.dead_normative + LIVE_SHARE_FOR_DEFLECTION * load.live_normative
    deflection_mm = 5 * q_deflection * span_mm**4 / (384 * STEEL_E_MPA * section.ix_cm4 * 1e4)

    return BeamCheck(
        strength_utilization=stress_mpa / (steel.ry_mpa(section.thickness_mm) * GAMMA_C),
        deflection_mm=deflection_mm,
        deflection_limit_mm=deflection_limit_mm(span_mm),
    )
