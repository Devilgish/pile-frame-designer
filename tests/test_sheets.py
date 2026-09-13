"""Раскладка листов ЦСП по контуру: целые и резаные листы, обрезки, линии стыков."""

import pytest

from pile_frame.boards import BoardSpec
from pile_frame.contour import Contour
from pile_frame.sheets import layout_sheets

BOARD = BoardSpec()  # 3200 × 1250 × 24


def _rectangle(width, length):
    return Contour.from_points([(0, 0), (width, 0), (width, length), (0, length)])


def test_rectangle_of_two_by_two_sheets_is_laid_with_whole_sheets_only():
    # Шаг раскладки с зазором 3 мм: 3203 × 1253. Крайние листы подрезаются на 3 мм (≤ 5) — целые.
    layout = layout_sheets(_rectangle(6400, 2500), BOARD, gap_mm=3)

    assert (layout.whole_count, layout.cut_count) == (4, 0)
    assert layout.offcut_m2 == pytest.approx(0)
    assert layout.joints_x == pytest.approx([3201.5])
    assert layout.joints_y == pytest.approx([1251.5])


def test_cut_sheets_at_contour_edges_count_offcuts_as_consumed_sheets():
    # 7000 × 3000: столбцы с 0, 3203, 6406 (кусок 594); ряды с 0, 1253, 2506 (кусок 494).
    # Целые 2 × 2 = 4; резаные 5. Куски: 594·1250·2 + 3200·494·2 + 594·494 = 4 940 036 мм².
    # Обрезки: 5 · 4 000 000 − 4 940 036 = 15 059 964 мм² ≈ 15,06 м².
    layout = layout_sheets(_rectangle(7000, 3000), BOARD, gap_mm=3)

    assert (layout.whole_count, layout.cut_count) == (4, 5)
    assert layout.offcut_m2 == pytest.approx(15.06, abs=0.01)


def test_l_shape_layout_cuts_sheets_around_the_notch():
    # Вырез x ∈ [3000, 6000], y ∈ [2000, 4000]. Целый только лист (0..3200, 0..1250).
    # Резаные куски: 2797·1250; 747·3200 + 503·3000; 747·2797; 3000·1250; 3000·241
    #   = 13 958 009 мм²; обрезки 5 · 4 000 000 − 13 958 009 ≈ 6,04 м².
    l_shape = Contour.from_points(
        [(0, 0), (6000, 0), (6000, 2000), (3000, 2000), (3000, 4000), (0, 4000)]
    )
    layout = layout_sheets(l_shape, BOARD, gap_mm=3)

    assert (layout.whole_count, layout.cut_count) == (1, 5)
    assert layout.offcut_m2 == pytest.approx(6.04, abs=0.01)


def test_rotating_sheets_changes_the_layout():
    # Вдоль Y лист 1250 × 3200: 6 столбцов по 1253 мм, один ряд; 3200 > 3000 — все резаные.
    layout = layout_sheets(_rectangle(7000, 3000), BOARD, long_side="y", gap_mm=3)

    assert (layout.whole_count, layout.cut_count) == (0, 6)
    assert len(layout.joints_x) == 5
    assert layout.joints_y == []
