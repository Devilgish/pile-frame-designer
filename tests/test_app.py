"""Smoke-тест окна: нарисовал контур мышью → сваи, каркас и итог проверки."""

import datetime

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from pile_frame.app import MainWindow
from pile_frame.report import ReportMeta
from pile_frame.status import Status
from pile_frame.theme import DARK


def _drag(view, start_mm, end_mm):
    viewport = view.viewport()
    start = view.mapFromScene(QPointF(*start_mm))
    end = view.mapFromScene(QPointF(*end_mm))
    QTest.mousePress(viewport, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(viewport, end)
    QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, pos=end)


def test_drawing_a_rectangle_builds_frame_and_shows_check_result(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()

    # Контур чуть мимо сетки: привязка округляет до 6000 × 4000 мм.
    _drag(window.plan, (0, 0), (6040, 3980))

    assert window.plan.pile_count() == 12
    assert "Проходит" in window.result_text()


def test_switching_to_dark_theme_repaints_window_and_is_remembered(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    window.set_theme_mode("dark")

    assert window.palette().color(QPalette.ColorRole.Window).name().upper() == DARK.background
    reopened = MainWindow()
    qtbot.addWidget(reopened)
    assert reopened.theme_mode() == "dark"


def test_result_card_shows_status_as_text_and_icon(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    # Полка 120 мм: кромкам листов хватает места под саморез — замечаний нет.
    # Лист 28 мм загружен на 76 % — запас больше 10 %.
    window.internal_profile.setCurrentText("120×120×5")
    window.board_fields["thickness_mm"].set_value(28)

    _drag(window.plan, (0, 0), (6000, 4000))

    card = window.result_card
    assert card.status() is Status.OK
    assert card.status_text() == Status.OK.label
    assert not card.icon_pixmap().isNull()


L_POINTS = [(0, 0), (6000, 0), (6000, 2000), (3000, 2000), (3000, 4000), (0, 4000)]


def _click(view, point_mm):
    QTest.mouseClick(
        view.viewport(), Qt.MouseButton.LeftButton, pos=view.mapFromScene(QPointF(*point_mm))
    )


def test_clicking_vertices_draws_l_shaped_contour_with_auto_piles(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    window.set_tool("contour")

    for point in [*L_POINTS, L_POINTS[0]]:  # клик в первую вершину замыкает контур
        _click(window.plan, point)

    assert window.plan.pile_count() == 13


def test_dragging_a_pile_moves_it_and_ctrl_z_puts_it_back(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    _drag(window.plan, (0, 0), (4000, 4000))
    window.set_tool("piles")

    _drag(window.plan, (2000, 2000), (2000, 2500))
    assert (2000, 2500) in window.editor.piles

    window.activateWindow()
    qtbot.waitUntil(lambda: QApplication.activeWindow() is window, timeout=1000)
    QTest.keyClick(window.plan, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert (2000, 2000) in window.editor.piles
    assert (2000, 2500) not in window.editor.piles


def _window_with_rectangle(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    _drag(window.plan, (0, 0), (6000, 4000))
    return window


def _worst_beam(design) -> float:
    """Наибольшая загрузка балок по сваям и под стыками (без периметра и перемычек)."""
    return max(
        c.strength_utilization
        for m, c in zip(design.members, design.checks, strict=True)
        if m.kind == "beam"
    )


def test_choosing_heavier_internal_profile_recalculates_result(qtbot):
    window = _window_with_rectangle(qtbot)
    before = _worst_beam(window.last_design)

    window.internal_profile.setCurrentText("120×120×5")

    assert _worst_beam(window.last_design) < before


def test_zero_board_thickness_shows_error_next_to_field_and_keeps_last_result(qtbot):
    window = _window_with_rectangle(qtbot)
    field = window.board_fields["thickness_mm"]
    before = window.result_text()

    field.editor.clear()
    QTest.keyClicks(field.editor, "0")
    QTest.keyClick(field.editor, Qt.Key.Key_Return)

    assert field.issue_label.isVisibleTo(window)
    assert "больше нуля" in field.issue_label.text()
    assert window.result_text() == before


def test_rotating_sheets_changes_layout_and_rebuilds_frame(qtbot):
    # 6000 × 4000, листы 3200 × 1250 с зазором 3 мм.
    # Вдоль X: 2 столбца (кусок 2797) × 4 ряда (кусок 241) → 3 целых, 5 резаных.
    # Вдоль Y: 5 столбцов (кусок 988) × 2 ряда (кусок 797) → 4 целых, 6 резаных.
    window = _window_with_rectangle(qtbot)
    assert window.result_card.value("Листы") == "3 целых, 5 резаных"
    members_before = window.result_card.value("Не проходят").split(" из ")[1]

    window.sheet_long_side.setCurrentIndex(1)

    assert window.result_card.value("Листы") == "4 целых, 6 резаных"
    assert window.result_card.value("Не проходят").split(" из ")[1] != members_before


def test_results_table_sorts_by_utilization_and_row_click_selects_member(qtbot):
    window = _window_with_rectangle(qtbot)
    table = window.results.members
    design = window.last_design
    assert table.model().rowCount() == len(design.members)

    table.sortByColumn(window.results.UTILIZATION_COLUMN, Qt.SortOrder.DescendingOrder)
    top_member = window.results.member_index_at(0)
    assert design.checks[top_member].utilization == max(c.utilization for c in design.checks)

    row_rect = table.visualRect(table.model().index(2, 0))
    QTest.mouseClick(table.viewport(), Qt.MouseButton.LeftButton, pos=row_rect.center())

    assert window.plan.selected_member() == window.results.member_index_at(2)


def test_welds_and_assumptions_tabs_are_filled(qtbot):
    window = _window_with_rectangle(qtbot)

    assert window.results.welds.model().rowCount() == len(window.last_design.welds) > 0
    assert "кручени" in window.results.assumptions_text().lower()


def test_board_check_jumpers_and_bearing_are_shown(qtbot):
    # Лист 24 мм на полках 120×60: перемычки в ячейках, кромкам не хватает полки под саморез.
    window = _window_with_rectangle(qtbot)
    design = window.last_design
    jumpers = sum(1 for m in design.members if m.kind == "jumper")
    assert jumpers > 0 and design.bearing_issues

    card = window.result_card
    assert card.status() is Status.WARNING
    assert f"перемычек {jumpers}" in card.value("Лист ЦСП")
    assert card.value("Балка").startswith("перемычка 40×40×3")  # определяет перемычка
    assert f"опирание листов: {len(design.bearing_issues)}" in card.value("Замечания")
    assert window.results.boards.model().rowCount() == len(design.board_cells)
    assert "ЦСП" in window.results.assumptions_text()


def test_remarks_without_overload_are_titled_as_remarks_not_as_low_margin(qtbot):
    # Лист 28 мм, 4 кПа: наибольшая загрузка 76 % (лист), но кромкам 120×60 не хватает полки.
    window = _window_with_rectangle(qtbot)
    field = window.board_fields["thickness_mm"]
    field.editor.clear()
    QTest.keyClicks(field.editor, "28")
    QTest.keyClick(field.editor, Qt.Key.Key_Return)

    card = window.result_card
    assert window.last_design.bearing_issues
    assert card.status() is Status.WARNING
    assert card.status_text() == "Проходит, есть замечания"


def test_board_utilization_counts_in_the_card_status(qtbot):
    # Лист 24 мм на полках 120 мм (замечаний по опиранию нет): элементы каркаса загружены
    # меньше чем на 60 %, лист — на 95 % → запас меньше 10 %.
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    window.internal_profile.setCurrentText("120×120×5")
    _drag(window.plan, (0, 0), (6000, 4000))

    assert not window.last_design.bearing_issues
    assert window.result_card.status_text() == Status.WARNING.label


def _rows(view):
    model = view.model()
    return sorted(
        tuple(model.index(r, c).data() for c in range(model.columnCount()))
        for r in range(model.rowCount())
    )


def test_report_repeats_the_numbers_shown_in_the_window(qtbot):
    window = _window_with_rectangle(qtbot)
    meta = ReportMeta(object_name="Цех", author="Исполнитель", date=datetime.date(2026, 10, 3))

    report = window.build_report(meta)

    tables = {t.title: t for t in report.tables()}
    results = window.results
    for view, title in (
        (results.members, "Элементы каркаса"),
        (results.boards, "Ячейки листов ЦСП"),
        (results.piles, "Реакции свай"),
        (results.welds, "Сварные швы"),
    ):
        assert sorted(tables[title].rows) == _rows(view), title
    assert window.result_card.status_text() in report.summary()
