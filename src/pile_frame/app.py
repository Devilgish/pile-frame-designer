"""Главное окно: план с сеткой, параметры и результат проверки."""

from __future__ import annotations

import sys

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QMouseEvent, QPen
from PySide6.QtWidgets import (
    QApplication,
    QDoubleSpinBox,
    QFormLayout,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QSpinBox,
    QWidget,
)

from pile_frame.design import Design, Project, analyze

GRID_STEP_MM = 250
GRID_MAJOR_MM = 1000
PLAN_AREA_MM = QRectF(-500, -500, 13000, 10000)
PILE_DIAMETER_MM = 108


def snap(value_mm: float, step_mm: float = GRID_STEP_MM) -> float:
    """Привязать координату к сетке."""
    return round(value_mm / step_mm) * step_mm


def _fmt(value: float, digits: int = 1) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


class PlanView(QGraphicsView):
    """План в миллиметрах: контур рисуется протягиванием мыши с привязкой к сетке."""

    contour_drawn = Signal(float, float)

    def __init__(self) -> None:
        super().__init__()
        self._scene = QGraphicsScene(PLAN_AREA_MM)
        self.setScene(self._scene)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.setRenderHint(self.renderHints().Antialiasing)
        self.scale(0.05, 0.05)
        self._draw_grid()
        self._drag_start: QPointF | None = None
        self._outline = None
        self._frame_items: list = []
        self._pile_count = 0

    def _draw_grid(self) -> None:
        minor, major = QPen(QColor("#e3e7ee"), 0), QPen(QColor("#c5ccd8"), 0)
        area = PLAN_AREA_MM
        x = area.left()
        while x <= area.right():
            self._scene.addLine(
                x, area.top(), x, area.bottom(), major if x % GRID_MAJOR_MM == 0 else minor
            )
            x += GRID_STEP_MM
        y = area.top()
        while y <= area.bottom():
            self._scene.addLine(
                area.left(), y, area.right(), y, major if y % GRID_MAJOR_MM == 0 else minor
            )
            y += GRID_STEP_MM

    def _snapped(self, event: QMouseEvent) -> QPointF:
        point = self.mapToScene(event.position().toPoint())
        return QPointF(snap(point.x()), snap(point.y()))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = self._snapped(event)
            if self._outline is None:
                self._outline = self._scene.addRect(
                    QRectF(), QPen(QColor("#1f4e9a"), 0, Qt.PenStyle.DashLine)
                )
            self._outline.setRect(QRectF(self._drag_start, self._drag_start))

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_start is not None and self._outline is not None:
            self._outline.setRect(QRectF(self._drag_start, self._snapped(event)).normalized())

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._drag_start is None or event.button() != Qt.MouseButton.LeftButton:
            return
        rect = QRectF(self._drag_start, self._snapped(event)).normalized()
        self._drag_start = None
        if self._outline is not None:
            self._outline.setRect(rect)
        if rect.width() > 0 and rect.height() > 0:
            self._origin = rect.topLeft()
            self.contour_drawn.emit(rect.width(), rect.height())

    def show_design(self, design: Design) -> None:
        """Нарисовать сваи и балки поверх контура."""
        for item in self._frame_items:
            self._scene.removeItem(item)
        self._frame_items.clear()
        ox, oy = self._origin.x(), self._origin.y()
        failing = {id(m) for m in design.failing_members()}
        for member in design.members:
            color = QColor("#c0392b") if id(member) in failing else QColor("#34495e")
            pen = QPen(color, member.section.width_mm)
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            (x0, y0), (x1, y1) = member.start, member.end
            self._frame_items.append(self._scene.addLine(ox + x0, oy + y0, ox + x1, oy + y1, pen))
        r = PILE_DIAMETER_MM / 2
        for x, y in design.piles:
            pile = self._scene.addEllipse(
                ox + x - r,
                oy + y - r,
                2 * r,
                2 * r,
                QPen(Qt.PenStyle.NoPen),
                QBrush(QColor("#e67e22")),
            )
            self._frame_items.append(pile)
        self._pile_count = len(design.piles)

    def pile_count(self) -> int:
        return self._pile_count


class MainWindow(QMainWindow):
    """Окно «Каркас на сваях»."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Каркас на сваях")
        self.resize(1100, 720)

        self.plan = PlanView()
        self.pile_step = QSpinBox(
            minimum=500, maximum=6000, singleStep=250, value=2000, suffix=" мм"
        )
        self.live_load = QDoubleSpinBox(
            minimum=0.0, maximum=50.0, singleStep=0.5, value=4.0, suffix=" кПа"
        )
        self._result = QLabel("Протяните мышью прямоугольник на плане, чтобы задать контур.")
        self._result.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Шаг свай", self.pile_step)
        form.addRow("Временная нагрузка", self.live_load)
        form.addRow(self._result)
        panel = QWidget()
        panel.setLayout(form)
        panel.setFixedWidth(300)

        root = QWidget()
        layout = QHBoxLayout(root)
        layout.addWidget(self.plan, stretch=1)
        layout.addWidget(panel)
        self.setCentralWidget(root)

        self._size: tuple[float, float] | None = None
        self.plan.contour_drawn.connect(self._on_contour)
        self.pile_step.valueChanged.connect(self._recalculate)
        self.live_load.valueChanged.connect(self._recalculate)

    def _on_contour(self, width_mm: float, length_mm: float) -> None:
        self._size = (width_mm, length_mm)
        self._recalculate()

    def _recalculate(self) -> None:
        if self._size is None:
            return
        width, length = self._size
        design = analyze(
            Project(
                width_mm=width,
                length_mm=length,
                pile_step_mm=self.pile_step.value(),
                live_load_kpa=self.live_load.value(),
            )
        )
        self.plan.show_design(design)
        self._result.setText(self._describe(width, length, design))

    @staticmethod
    def _describe(width: float, length: float, design: Design) -> str:
        check, member = design.governing_check, design.governing_member
        failing = len(design.failing_members())
        verdict = "Проходит" if check.passed else "Не проходит"
        return (
            f"<b>{verdict}</b><br>"
            f"План {width:.0f} × {length:.0f} мм, свай: {len(design.piles)}<br>"
            f"Не проходят элементов: {failing} из {len(design.members)}<br><br>"
            f"Самая нагруженная балка: {member.section.name}, пролёт {member.length_mm:.0f} мм<br>"
            f"Прочность: {check.strength_utilization:.0%}<br>"
            f"Прогиб: {_fmt(check.deflection_mm)} из {_fmt(check.deflection_limit_mm)} мм "
            f"({check.deflection_utilization:.0%})"
        )

    def result_text(self) -> str:
        return self._result.text()


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
