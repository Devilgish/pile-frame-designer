"""Проверка листа ЦСП на изгиб между опорами.

Лист рассчитывается на пролёте, равном меньшей стороне ячейки между балками, как шарнирно
опёртая полоса (неразрезность и работа в двух направлениях не учитываются — в запас).
Расчётное сопротивление R = kmod·Rн/γm: Rн — предел прочности при изгибе по ГОСТ 26816-2016
(таблица 2), kmod и γm приняты по аналогии с EN 1995-1-1 для стружечной плиты P5.

Сосредоточенная нагрузка 1,5 кН на площадке 10×10 см (СП 20.13330.2016, п. 8.3.4) —
по решению Тимошенко для длинной шарнирно опёртой пластины с нагрузкой на малом круге.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from pile_frame.analysis import GAMMA_F_BOARD, GRAVITY, gamma_f_live
from pile_frame.beam import LIVE_SHARE_FOR_DEFLECTION, deflection_limit_mm
from pile_frame.boards import BoardSpec

#: Коэффициент надёжности по материалу γm (EN 1995-1-1, таблица 2.3, стружечные плиты).
GAMMA_M = 1.3
#: kmod (EN 1995-1-1, таблица 3.1, плита P5, класс эксплуатации 1): равномерная временная —
#: средней продолжительности, сосредоточенная — кратковременная.
KMOD_MEDIUM = 0.65
KMOD_SHORT = 0.85
#: Сосредоточенная нагрузка, Н, сторона площадки, мм, и γf (СП 20.13330.2016, п. 8.3.4, 8.3.5).
POINT_LOAD_N = 1500.0
POINT_PATCH_MM = 100.0
GAMMA_F_POINT = 1.2
#: Модуль упругости при изгибе ЦСП-1, МПа (ГОСТ 26816-2016, таблица А.1).
BOARD_E_MPA = 4500.0
#: kdef (EN 1995-1-1, таблица 3.2, плита P5, класс эксплуатации 1): ползучесть в прогибе.
KDEF = 2.25
#: Наименьший шаг перемычек 40×40, мм: чаще ставить нецелесообразно — нужен лист толще.
MIN_JUMPER_PITCH_MM = 150.0
#: Коэффициент Пуассона ЦСП: в ГОСТ не нормирован, принят в запас.
POISSON = 0.3


def bending_strength_mpa(thickness_mm: float) -> float:
    """Предел прочности при изгибе ЦСП-1, МПа (ГОСТ 26816-2016, таблица 2)."""
    if thickness_mm < 12:
        return 12.0
    if thickness_mm < 19:
        return 10.0
    return 9.0


def _point_moment(span_mm: float, thickness_mm: float, force_n: float) -> float:
    """Момент под сосредоточенной нагрузкой в пластине, Н·мм на 1 мм ширины."""
    radius = POINT_PATCH_MM / math.sqrt(math.pi)  # круг той же площади
    if radius < 1.724 * thickness_mm:
        # Поправка на толщину пластины (Тимошенко, «Пластинки и оболочки», § 19).
        radius = math.sqrt(1.6 * radius**2 + thickness_mm**2) - 0.675 * thickness_mm
    log = math.log(2 * span_mm / (math.pi * radius))
    return force_n / (4 * math.pi) * ((1 + POISSON) * log + 1)


@dataclass(frozen=True)
class BoardCheck:
    """Результат проверки листа на пролёте ``span_mm``."""

    span_mm: float
    uniform_utilization: float
    point_utilization: float
    deflection_mm: float
    deflection_limit_mm: float

    @property
    def deflection_utilization(self) -> float:
        return self.deflection_mm / self.deflection_limit_mm

    @property
    def utilization(self) -> float:
        return max(self.uniform_utilization, self.point_utilization, self.deflection_utilization)

    @property
    def passed(self) -> bool:
        return self.utilization <= 1.0


def check_board(board: BoardSpec, *, span_mm: float, live_load_kpa: float) -> BoardCheck:
    t = board.thickness_mm
    dead = board.density_kg_m3 * GRAVITY * t * 1e-9  # Н/мм²
    live = live_load_kpa * 1e-3
    section_modulus = t**2 / 6  # мм³ на 1 мм ширины
    strength = bending_strength_mpa(t) / GAMMA_M

    q = GAMMA_F_BOARD * dead + gamma_f_live(live_load_kpa) * live
    uniform = q * span_mm**2 / 8 / section_modulus / (KMOD_MEDIUM * strength)

    point_moment = _point_moment(span_mm, t, GAMMA_F_POINT * POINT_LOAD_N)
    point_moment += GAMMA_F_BOARD * dead * span_mm**2 / 8
    point = point_moment / section_modulus / (KMOD_SHORT * strength)
    q_long = dead + LIVE_SHARE_FOR_DEFLECTION * live
    stiffness = BOARD_E_MPA / (1 + KDEF) * t**3 / 12
    deflection = 5 * q_long * span_mm**4 / (384 * stiffness)
    return BoardCheck(
        span_mm=span_mm,
        uniform_utilization=uniform,
        point_utilization=point,
        deflection_mm=deflection,
        deflection_limit_mm=deflection_limit_mm(span_mm),
    )


def jumpers_needed(
    board: BoardSpec, *, short_mm: float, long_mm: float, live_load_kpa: float
) -> int | None:
    """Сколько перемычек поставить поперёк длинной стороны ячейки, чтобы лист прошёл.

    Перемычки перекрывают короткую сторону с равным шагом; пролёт листа — меньшее из короткой
    стороны и шага. ``None`` — лист не проходит даже при шаге перемычек ``MIN_JUMPER_PITCH_MM``.
    """
    count = 0
    while True:
        span = min(short_mm, long_mm / (count + 1))
        if span < MIN_JUMPER_PITCH_MM:
            return None
        if check_board(board, span_mm=span, live_load_kpa=live_load_kpa).passed:
            return count
        count += 1


#: Наименьшее расстояние от крепежа до кромки листа, мм: (толщина до, мм; a, мм).
#: Тамак, «Крепление ЦСП» (csp.tamak.ru); строки 16, 20 и 24 мм совпадают.
_EDGE_DISTANCE_MM = ((12, 20), (24, 25), (36, 40))


def edge_distance_mm(thickness_mm: float) -> float:
    """Отступ самореза от кромки листа; промежуточные толщины — по большей строке."""
    for limit, distance in _EDGE_DISTANCE_MM:
        if thickness_mm <= limit:
            return distance
    return _EDGE_DISTANCE_MM[-1][1]
