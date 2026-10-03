"""Лист ЦСП на изгиб между опорами: равномерная и сосредоточенная нагрузки, прогиб."""

import pytest

from pile_frame.board_check import check_board, edge_distance_mm, jumpers_needed
from pile_frame.boards import BoardSpec

BOARD_24 = BoardSpec(thickness_mm=24, density_kg_m3=1300)


def test_uniform_load_bending_of_a_strip_between_two_supports():
    # Лист 24 мм, 1300 кг/м³: g = 1300·9,81·0,024 = 306,07 Па = 3,0607e-4 Н/мм².
    # q = 1,2·3,0607e-4 + 1,2·4e-3 = 5,1673e-3 Н/мм² (временная 4 кПа ≥ 2 → γf 1,2).
    # Полоса 1 мм, пролёт 600: M = q·l²/8 = 232,53 Н·мм; W = 24²/6 = 96 мм³ → σ = 2,4222 МПа.
    # R = kmod·Rн/γm = 0,65·9/1,3 = 4,5 МПа (толщина > 19 мм → 9 МПа) → 0,5383.
    check = check_board(BOARD_24, span_mm=600, live_load_kpa=4.0)

    assert check.uniform_utilization == pytest.approx(0.5383, abs=1e-4)


@pytest.mark.parametrize(
    ("thickness", "expected"),
    [
        # 12 мм: «от 12,0 включ.» → Rн = 10, R = 0,65·10/1,3 = 5,0 МПа.
        # g = 1300·9,81·0,012 = 1,5304e-4; q = 1,2·g + 4,8e-3 = 4,9836e-3 Н/мм².
        # M = q·300²/8 = 56,066; W = 12²/6 = 24 → σ = 2,3361 → 0,4672.
        (12, 0.4672),
        # 18 мм: «св. 15 до 19» → Rн = 10. g = 2,2955e-4; q = 5,0755e-3;
        # M = 57,099; W = 54 → σ = 1,0574 → 0,2115.
        (18, 0.2115),
    ],
)
def test_bending_strength_follows_the_gost_thickness_grades(thickness, expected):
    board = BoardSpec(thickness_mm=thickness, density_kg_m3=1300)

    check = check_board(board, span_mm=300, live_load_kpa=4.0)

    assert check.uniform_utilization == pytest.approx(expected, abs=1e-4)


def test_concentrated_load_on_a_small_square_bends_the_board_as_a_plate():
    # P = 1,2·1,5 кН = 1800 Н на площадке 100×100 → круг той же площади c = 100/√π = 56,42 мм
    # (c ≥ 1,724·t = 41,4 — поправка на толщину не нужна).
    # Тимошенко, длинная шарнирная пластина: M = P/(4π)·[(1+ν)·ln(2l/(πc)) + 1], ν = 0,3.
    # ln(1200/(π·56,42)) = ln 6,7703 = 1,9125 → M = 143,24·(1,3·1,9125 + 1) = 499,38 Н·мм/мм.
    # Собственный вес: 1,2·3,0607e-4·600²/8 = 16,53 → M = 515,90; σ = 515,90/96 = 5,3740 МПа.
    # Кратковременная нагрузка: R = 0,85·9/1,3 = 5,8846 МПа → 0,9132.
    check = check_board(BOARD_24, span_mm=600, live_load_kpa=4.0)

    assert check.point_utilization == pytest.approx(0.9132, abs=1e-4)


def test_long_term_deflection_includes_creep_and_is_limited_by_table_d1():
    # q = g + 0,35·p = 3,0607e-4 + 1,4e-3 = 1,7061e-3 Н/мм²; I = 24³/12 = 1152 мм⁴/мм.
    # Ползучесть: E = 4500/(1 + 2,25) = 1384,6 МПа.
    # f = 5·q·l⁴/(384·E·I) = 5·1,7061e-3·600⁴/(384·1384,6·1152) = 1,805 мм.
    # Пролёт ≤ 1 м → fu = l/120 = 5,0 мм (СП 20.13330.2016, таблица Д.1, п. 2а).
    check = check_board(BOARD_24, span_mm=600, live_load_kpa=4.0)

    assert check.deflection_mm == pytest.approx(1.805, abs=1e-3)
    assert check.deflection_limit_mm == pytest.approx(5.0)


def test_thick_board_uses_the_equivalent_load_radius():
    # 36 мм: c = 56,42 < 1,724·36 = 62,06 → c' = √(1,6·c² + h²) − 0,675·h = 55,63 мм.
    # ln(2000/(π·55,63)) = 2,4374 → M = 143,24·(1,3·2,4374 + 1) = 597,12 Н·мм/мм.
    # Вес: 1,2·1300·9,81·36e-9·1000²/8 = 68,87 → M = 665,98; W = 36²/6 = 216 → σ = 3,0833.
    # R = 0,85·9/1,3 = 5,8846 → 0,5240 (без поправки было бы 0,5219).
    board = BoardSpec(thickness_mm=36, density_kg_m3=1300)

    check = check_board(board, span_mm=1000, live_load_kpa=4.0)

    assert check.point_utilization == pytest.approx(0.5240, abs=1e-4)


def test_jumpers_split_the_long_side_until_the_board_passes():
    # Ячейка 1250 × 3200, лист 24 мм, 4 кПа. Без перемычек пролёт 1250: сосредоточенная 1,253.
    # 3 перемычки → пролёт 3200/4 = 800: сосредоточенная 1,031 (M = 582,3 Н·мм/мм) — мало.
    # 4 перемычки → 3200/5 = 640: сосредоточенная 0,939, равномерная 0,612, прогиб 2,34/5,33.
    assert jumpers_needed(BOARD_24, short_mm=1250, long_mm=3200, live_load_kpa=4.0) == 4


def test_no_jumpers_when_the_board_spans_the_cell_on_its_own():
    # Ячейка 600 × 1250: пролёт 600 → 0,913 (см. тест сосредоточенной нагрузки).
    assert jumpers_needed(BOARD_24, short_mm=600, long_mm=1250, live_load_kpa=4.0) == 0


def test_thin_board_cannot_be_rescued_by_jumpers():
    # Лист 8 мм при шаге 150 мм: ln(300/(π·56,42)) = 0,5262 → M = 143,24·1,684 = 241,2 Н·мм/мм;
    # W = 8²/6 = 10,67 → σ = 22,6 МПа при R = 0,85·12/1,3 = 7,85 → 2,88. Нужен лист толще.
    board = BoardSpec(thickness_mm=8, density_kg_m3=1300)

    assert jumpers_needed(board, short_mm=1250, long_mm=3200, live_load_kpa=4.0) is None


def test_board_fails_when_only_the_deflection_is_exceeded():
    # 36 мм, пролёт 2000, без временной: g = 4,591e-4 Н/мм²; E·I = 1384,6·36³/12 = 5,383e6.
    # f = 5·4,591e-4·2000⁴/(384·5,383e6) = 17,77 мм; fu(2 м) = 8,33 + (20 − 8,33)/2 = 14,17 мм.
    # Прочность проходит: равномерная 0,283, сосредоточенная 0,788.
    board = BoardSpec(thickness_mm=36, density_kg_m3=1300)

    check = check_board(board, span_mm=2000, live_load_kpa=0.0)

    assert check.point_utilization < 1 and check.uniform_utilization < 1
    assert check.deflection_mm == pytest.approx(17.77, abs=0.01)
    assert not check.passed


@pytest.mark.parametrize(
    ("thickness", "expected"),
    # Тамак, «Крепление ЦСП»: a = 20 мм для 8–12, 25 для 16, 20, 24, 40 для 36.
    # Промежуточные толщины — по ближайшей большей строке таблицы (в запас).
    [(8, 20), (12, 20), (14, 25), (24, 25), (26, 40), (36, 40)],
)
def test_screw_edge_distance_follows_the_manufacturer_table(thickness, expected):
    assert edge_distance_mm(thickness) == expected
