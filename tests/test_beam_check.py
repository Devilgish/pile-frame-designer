"""Проверка однопролётной балки на прочность и прогиб.

Эталонные значения посчитаны вручную по СП 16.13330.2017 и СП 20.13330.2016,
а не повторно тем же кодом.
"""

import pytest

from pile_frame.beam import BeamLoad, check_beam
from pile_frame.materials import C245
from pile_frame.sections import TUBE_120x60x4

# Нагрузка на балку, кН/м: постоянная 0,8 (расчётная ×1,2 = 0,96),
# временная 8,0 (расчётная ×1,2 = 9,6).
LOAD = BeamLoad(dead_normative=0.8, dead_design=0.96, live_normative=8.0, live_design=9.6)


def test_beam_passes_strength_with_hand_calculated_utilization():
    # q = 10,56 кН/м; M = q·L²/8 = 10,56·2²/8 = 5,28 кН·м;
    # σ = 5,28e6 Н·мм / 40 120 мм³ = 131,6 Н/мм²; 131,6 / (240·1,0) = 0,548.
    result = check_beam(span_mm=2000, section=TUBE_120x60x4, steel=C245, load=LOAD)

    assert result.strength_utilization == pytest.approx(0.548, abs=0.001)
    assert result.strength_ok


def test_beam_deflection_uses_dead_plus_reduced_live_normative_load():
    # СП 20.13330, таблица Д.1: постоянная + 0,35 временной, нормативные значения.
    # q = 0,8 + 0,35·8,0 = 3,6 Н/мм; f = 5·q·L⁴/(384·E·I)
    #   = 5·3,6·2000⁴ / (384·2,06e5·240,7e4) = 1,513 мм.
    result = check_beam(span_mm=2000, section=TUBE_120x60x4, steel=C245, load=LOAD)

    assert result.deflection_mm == pytest.approx(1.513, abs=0.001)


@pytest.mark.parametrize(
    ("span_mm", "limit_mm"),
    [
        (500, 4.167),  # l ≤ 1 м: l/120
        (1000, 8.333),  # l/120
        (2000, 14.167),  # между 1 м (8,333) и 3 м (20,0)
        (3000, 20.0),  # l/150
        (4500, 25.0),  # между 3 м (20,0) и 6 м (30,0)
        (6000, 30.0),  # l/200
        (24000, 96.0),  # l/250
        (40000, 133.333),  # l ≥ 36 м: l/300
    ],
)
def test_deflection_limit_follows_table_d1_with_linear_interpolation(span_mm, limit_mm):
    # СП 20.13330.2016, таблица Д.1, п. 2а: для промежуточных пролётов предельный
    # прогиб определяется линейной интерполяцией.
    result = check_beam(span_mm=span_mm, section=TUBE_120x60x4, steel=C245, load=LOAD)

    assert result.deflection_limit_mm == pytest.approx(limit_mm, abs=0.001)


def test_overstressed_beam_does_not_pass():
    # L = 3 м: M = 10,56·3²/8 = 11,88 кН·м; σ = 11,88e6 / 40 120 = 296,1 Н/мм²;
    # 296,1 / 240 = 1,234.
    result = check_beam(span_mm=3000, section=TUBE_120x60x4, steel=C245, load=LOAD)

    assert result.strength_utilization == pytest.approx(1.234, abs=0.001)
    assert not result.passed


def test_beam_governed_by_deflection_does_not_pass():
    # Только постоянная нагрузка 1,0 кН/м (расчётная 1,05), L = 6 м.
    # Прочность: M = 1,05·6²/8 = 4,725 кН·м; σ = 117,8 Н/мм²; 117,8 / 240 = 0,491.
    # Прогиб: f = 5·1,0·6000⁴ / (384·2,06e5·240,7e4) = 34,03 мм > f_u = 30 мм.
    load = BeamLoad(dead_normative=1.0, dead_design=1.05, live_normative=0.0, live_design=0.0)

    result = check_beam(span_mm=6000, section=TUBE_120x60x4, steel=C245, load=load)

    assert result.strength_ok
    assert result.deflection_utilization == pytest.approx(1.134, abs=0.001)
    assert not result.passed
