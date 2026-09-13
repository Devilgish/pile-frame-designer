"""Главное окно: план с сеткой, исходные данные и карточка результата."""

from __future__ import annotations

import sys

from PySide6.QtCore import QPointF, QRectF, QSettings, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QBrush,
    QColor,
    QMouseEvent,
    QPen,
    QPixmap,
    QResizeEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGraphicsScene,
    QGraphicsView,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from pile_frame.design import Design, Project, analyze
from pile_frame.qt_theme import THEME_MODES, apply_theme, resolve_theme, status_icon
from pile_frame.status import Status, classify
from pile_frame.theme import LIGHT, Theme

GRID_STEP_MM = 250
GRID_MAJOR_MM = 1000
PLAN_MARGIN_MM = 500
PLAN_SCALE = 0.05  # пикселей на миллиметр
PILE_DIAMETER_MM = 108

SETTINGS_ORG = "pile-frame-designer"
SETTINGS_APP = "pile-frame-designer"
THEME_LABELS = {"system": "Как в системе", "light": "Светлая", "dark": "Тёмная"}


def snap(value_mm: float, step_mm: float = GRID_STEP_MM) -> float:
    """Привязать координату к сетке."""
    return round(value_mm / step_mm) * step_mm


def _fmt(value: float, digits: int = 1) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


def _settings() -> QSettings:
    return QSettings(
        QSettings.Format.IniFormat, QSettings.Scope.UserScope, SETTINGS_ORG, SETTINGS_APP
    )


class PlanView(QGraphicsView):
    """План в миллиметрах: контур рисуется протягиванием мыши с привязкой к сетке."""

    contour_drawn = Signal(float, float)
    cursor_moved = Signal(float, float)

    def __init__(self) -> None:
        super().__init__()
        self._area = QRectF(-PLAN_MARGIN_MM, -PLAN_MARGIN_MM, 13000, 10000)
        self._scene = QGraphicsScene(self._area)
        self.setScene(self._scene)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setRenderHint(self.renderHints().Antialiasing)
        self.setMouseTracking(True)
        self.scale(PLAN_SCALE, PLAN_SCALE)
        self._theme = LIGHT
        self._drag_start: QPointF | None = None
        self._contour: QRectF | None = None
        self._design: Design | None = None
        self._pile_count = 0
        self._redraw()

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._redraw()

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Сетка заполняет весь видимый план при любом размере окна."""
        super().resizeEvent(event)
        size = self.viewport().size()
        self._area = QRectF(
            -PLAN_MARGIN_MM, -PLAN_MARGIN_MM, size.width() / PLAN_SCALE, size.height() / PLAN_SCALE
        )
        self._scene.setSceneRect(self._area)
        self._redraw()

    def _redraw(self) -> None:
        """Перерисовать сетку, контур и каркас в цветах текущей темы."""
        self._scene.clear()
        self._scene.setBackgroundBrush(QColor(self._theme.plan_background))
        self._draw_grid()
        if self._contour is not None:
            pen = QPen(QColor(self._theme.outline), 0, Qt.PenStyle.DashLine)
            self._scene.addRect(self._contour, pen)
        if self._design is not None and self._contour is not None:
            self._draw_design(self._design, self._contour.topLeft())

    def _draw_grid(self) -> None:
        t = self._theme
        minor, major = QPen(QColor(t.grid_minor), 0), QPen(QColor(t.grid_major), 0)
        area = self._area
        x = area.left()
        while x <= area.right():
            pen = major if x % GRID_MAJOR_MM == 0 else minor
            self._scene.addLine(x, area.top(), x, area.bottom(), pen)
            x += GRID_STEP_MM
        y = area.top()
        while y <= area.bottom():
            pen = major if y % GRID_MAJOR_MM == 0 else minor
            self._scene.addLine(area.left(), y, area.right(), y, pen)
            y += GRID_STEP_MM

    def _draw_design(self, design: Design, origin: QPointF) -> None:
        t = self._theme
        ox, oy = origin.x(), origin.y()
        failing = {id(m) for m in design.failing_members()}
        for member in design.members:
            is_perimeter = member.section.width_mm == member.section.height_mm
            if id(member) in failing:
                # Не только цвет: перегруженная балка рисуется пунктиром.
                pen = QPen(QColor(t.fail), member.section.width_mm, Qt.PenStyle.DashLine)
            else:
                color = t.member_perimeter if is_perimeter else t.member_internal
                pen = QPen(QColor(color), member.section.width_mm)
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            (x0, y0), (x1, y1) = member.start, member.end
            self._scene.addLine(ox + x0, oy + y0, ox + x1, oy + y1, pen)
        r = PILE_DIAMETER_MM / 2
        brush = QBrush(QColor(t.pile))
        for x, y in design.piles:
            self._scene.addEllipse(ox + x - r, oy + y - r, 2 * r, 2 * r, Qt.PenStyle.NoPen, brush)

    def _snapped(self, event: QMouseEvent) -> QPointF:
        point = self.mapToScene(event.position().toPoint())
        return QPointF(snap(point.x()), snap(point.y()))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = self._snapped(event)
            self._design = None
            self._contour = QRectF(self._drag_start, self._drag_start)
            self._redraw()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        point = self._snapped(event)
        self.cursor_moved.emit(point.x(), point.y())
        if self._drag_start is not None:
            self._contour = QRectF(self._drag_start, point).normalized()
            self._redraw()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._drag_start is None or event.button() != Qt.MouseButton.LeftButton:
            return
        rect = QRectF(self._drag_start, self._snapped(event)).normalized()
        self._drag_start = None
        self._contour = rect
        self._redraw()
        if rect.width() > 0 and rect.height() > 0:
            self.contour_drawn.emit(rect.width(), rect.height())

    def show_design(self, design: Design) -> None:
        """Нарисовать сваи и балки поверх контура."""
        self._design = design
        self._pile_count = len(design.piles)
        self._redraw()

    def pile_count(self) -> int:
        return self._pile_count


class ResultCard(QFrame):
    """Карточка результата: статус (иконка + текст) и ключевые числа."""

    ROWS = ("План", "Свай", "Не проходят", "Балка", "Прочность", "Прогиб")

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("card")
        self._theme = LIGHT
        self._status: Status | None = None
        self._icon = QLabel()
        self._icon.setFixedSize(20, 20)
        self._icon.hide()
        self._title = QLabel("Протяните мышью прямоугольник на плане, чтобы задать контур.")
        self._title.setWordWrap(True)
        self._title.setProperty("role", "muted")

        header = QHBoxLayout()
        header.setSpacing(8)
        header.addWidget(self._icon)
        header.addWidget(self._title, stretch=1)

        rows = QGridLayout()
        rows.setHorizontalSpacing(12)
        rows.setVerticalSpacing(4)
        self._values: dict[str, QLabel] = {}
        for i, key in enumerate(self.ROWS):
            name = QLabel(key)
            name.setProperty("role", "muted")
            value = QLabel("—")
            value.setAlignment(Qt.AlignmentFlag.AlignRight)
            rows.addWidget(name, i, 0)
            rows.addWidget(value, i, 1)
            self._values[key] = value

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)
        layout.addLayout(header)
        layout.addLayout(rows)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._refresh_status_style()

    def show_design(self, width: float, length: float, design: Design) -> None:
        check, member = design.governing_check, design.governing_member
        utilization = max(check.strength_utilization, check.deflection_utilization)
        self._status = classify(utilization)
        v = self._values
        v["План"].setText(f"{width:.0f} × {length:.0f} мм")
        v["Свай"].setText(str(len(design.piles)))
        v["Не проходят"].setText(f"{len(design.failing_members())} из {len(design.members)}")
        v["Балка"].setText(f"{member.section.name}, {member.length_mm:.0f} мм")
        v["Прочность"].setText(f"{check.strength_utilization:.0%}")
        v["Прогиб"].setText(
            f"{_fmt(check.deflection_mm)} из {_fmt(check.deflection_limit_mm)} мм "
            f"({check.deflection_utilization:.0%})"
        )
        self._refresh_status_style()

    def _refresh_status_style(self) -> None:
        if self._status is None:
            return
        color = getattr(self._theme, self._status.color_token)
        self._icon.show()
        self._title.setText(self._status.label)
        self._title.setStyleSheet(f"font-weight: 600; font-size: 11pt; color: {color};")
        self._icon.setPixmap(status_icon(self._status, self._theme))

    def status(self) -> Status | None:
        return self._status

    def status_text(self) -> str:
        return self._title.text()

    def icon_pixmap(self) -> QPixmap:
        return self._icon.pixmap()

    def text(self) -> str:
        details = "\n".join(f"{k}: {v.text()}" for k, v in self._values.items())
        return f"{self._title.text()}\n{details}"


def _section(title: str) -> QLabel:
    label = QLabel(title.upper())
    label.setProperty("role", "section")
    return label


class MainWindow(QMainWindow):
    """Окно «Каркас на сваях»."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Каркас на сваях")
        self.resize(1180, 760)

        self.plan = PlanView()
        self.pile_step = QSpinBox(
            minimum=500, maximum=6000, singleStep=250, value=2000, suffix=" мм"
        )
        self.live_load = QDoubleSpinBox(
            minimum=0.0, maximum=50.0, singleStep=0.5, value=4.0, suffix=" кПа"
        )
        self.result_card = ResultCard()

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)
        form.addRow("Шаг свай", self.pile_step)
        form.addRow("Временная нагрузка", self.live_load)

        panel = QWidget()
        panel.setObjectName("panel")
        panel.setFixedWidth(320)
        side = QVBoxLayout(panel)
        side.setContentsMargins(0, 0, 0, 0)
        side.setSpacing(8)
        side.addWidget(_section("Исходные данные"))
        side.addLayout(form)
        side.addWidget(_section("Результат"))
        side.addWidget(self.result_card)
        side.addStretch(1)

        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        layout.addWidget(self.plan, stretch=1)
        layout.addWidget(panel)
        self.setCentralWidget(root)

        self._coords = QLabel()
        self.statusBar().addWidget(self._coords)
        self.statusBar().addPermanentWidget(QLabel(f"Сетка {GRID_STEP_MM} мм"))
        self._build_menu()

        self._size: tuple[float, float] | None = None
        self.plan.contour_drawn.connect(self._on_contour)
        self.plan.cursor_moved.connect(self._show_cursor)
        self.pile_step.valueChanged.connect(self._recalculate)
        self.live_load.valueChanged.connect(self._recalculate)

        self._theme_mode = "system"
        self.set_theme_mode(str(_settings().value("theme", "system")))

    def _build_menu(self) -> None:
        view = self.menuBar().addMenu("Вид")
        theme_menu = view.addMenu("Тема")
        self._theme_actions = QActionGroup(self)
        for mode in THEME_MODES:
            action = QAction(THEME_LABELS[mode], self, checkable=True)
            action.setData(mode)
            action.triggered.connect(self._on_theme_action)
            self._theme_actions.addAction(action)
            theme_menu.addAction(action)

    def _on_theme_action(self) -> None:
        action = self._theme_actions.checkedAction()
        if action is not None:
            self.set_theme_mode(str(action.data()))

    def _show_cursor(self, x: float, y: float) -> None:
        self._coords.setText(f"X {x:.0f} мм   Y {y:.0f} мм")

    def set_theme_mode(self, mode: str) -> None:
        """Переключить тему: «system», «light» или «dark». Выбор запоминается."""
        if mode not in THEME_MODES:
            mode = "system"
        self._theme_mode = mode
        theme = resolve_theme(mode)
        apply_theme(self, theme)
        self.plan.set_theme(theme)
        self.result_card.set_theme(theme)
        for action in self._theme_actions.actions():
            action.setChecked(action.data() == mode)
        _settings().setValue("theme", mode)

    def theme_mode(self) -> str:
        return self._theme_mode

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
        self.result_card.show_design(width, length, design)

    def result_text(self) -> str:
        return self.result_card.text()


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
