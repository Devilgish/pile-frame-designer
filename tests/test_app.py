"""Smoke-тест окна: нарисовал контур мышью → сваи, каркас и итог проверки."""

from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest

from pile_frame.app import MainWindow


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
