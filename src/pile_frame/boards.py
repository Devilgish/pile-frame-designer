"""Листы пола: цементно-стружечные плиты по ГОСТ 26816-2016."""

from __future__ import annotations

from dataclasses import dataclass

from pile_frame.issues import Issue

#: Номинальные длины и ширины, мм (таблица 1).
GOST_LENGTHS_MM = (3200, 3600)
GOST_WIDTHS_MM = (1200, 1250)
#: Форматы листов по ГОСТ: длина × ширина.
GOST_FORMATS_MM = tuple((length, width) for length in GOST_LENGTHS_MM for width in GOST_WIDTHS_MM)
#: Плотность, кг/м³ (таблица 2).
GOST_DENSITY_RANGE = (1100, 1400)
#: Градация по толщине — шаг 2 мм (таблица 1, примечание 1).
THICKNESS_STEP_MM = 2
#: Толщины для выбора в интерфейсе, мм.
THICKNESS_CHOICES_MM = tuple(range(8, 42, THICKNESS_STEP_MM))


@dataclass(frozen=True)
class BoardSpec:
    """Лист ЦСП: размеры, мм; плотность, кг/м³."""

    length_mm: float = 3200
    width_mm: float = 1250
    thickness_mm: float = 24
    density_kg_m3: float = 1300


_LABELS = {
    "length_mm": "Длина листа",
    "width_mm": "Ширина листа",
    "thickness_mm": "Толщина листа",
    "density_kg_m3": "Плотность",
}


def validate_board(board: BoardSpec) -> list[Issue]:
    """Ошибки — значения, с которыми расчёт невозможен; предупреждения — отступления от ГОСТ."""
    issues = [
        Issue(field, f"Значение «{label}» должно быть больше нуля.")
        for field, label in _LABELS.items()
        if getattr(board, field) <= 0
    ]
    bad = {i.field for i in issues}
    note = "не по ГОСТ 26816-2016"
    if "length_mm" not in bad and board.length_mm not in GOST_LENGTHS_MM:
        issues.append(
            Issue("length_mm", f"Длина {board.length_mm:g} мм {note} (3200 или 3600).", "warning")
        )
    if "width_mm" not in bad and board.width_mm not in GOST_WIDTHS_MM:
        issues.append(
            Issue("width_mm", f"Ширина {board.width_mm:g} мм {note} (1200 или 1250).", "warning")
        )
    if "thickness_mm" not in bad and board.thickness_mm % THICKNESS_STEP_MM:
        issues.append(
            Issue(
                "thickness_mm", f"Толщина {board.thickness_mm:g} мм {note} (шаг 2 мм).", "warning"
            )
        )
    low, high = GOST_DENSITY_RANGE
    if "density_kg_m3" not in bad and not low <= board.density_kg_m3 <= high:
        issues.append(
            Issue(
                "density_kg_m3",
                f"Плотность {board.density_kg_m3:g} кг/м³ {note} ({low}–{high}).",
                "warning",
            )
        )
    return issues
