"""Smoke-тест окна: нарисовал контур мышью → сваи, каркас и итог проверки."""

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from pile_frame.app import MainWindow
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


def test_choosing_heavier_internal_profile_recalculates_result(qtbot):
    window = _window_with_rectangle(qtbot)
    assert window.result_card.value("Прочность") == "54%"

    window.internal_profile.setCurrentText("120×120×5")

    assert window.result_card.value("Прочность") == "27%"


def test_zero_board_thickness_shows_error_next_to_field_and_keeps_last_result(qtbot):
    window = _window_with_rectangle(qtbot)
    field = window.board_fields["thickness_mm"]

    field.editor.clear()
    QTest.keyClicks(field.editor, "0")
    QTest.keyClick(field.editor, Qt.Key.Key_Return)

    assert field.issue_label.isVisibleTo(window)
    assert "больше нуля" in field.issue_label.text()
    assert window.result_card.value("Прочность") == "54%"
