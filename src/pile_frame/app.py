"""Главное окно: план с инструментами, исходные данные и карточка результата."""

from __future__ import annotations

import math
import sys

from PySide6.QtCore import QPointF, QRectF, QSettings, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QBrush,
    QColor,
    QKeyEvent,
    QKeySequence,
    QMouseEvent,
    QPen,
    QPixmap,
    QPolygonF,
    QResizeEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
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
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from pile_frame.contour import Contour, ContourError, Point
from pile_frame.design import Design, Project, analyze
from pile_frame.editor import PlanEditor
from pile_frame.qt_theme import THEME_MODES, apply_theme, resolve_theme, status_icon
from pile_frame.status import Status, classify
from pile_frame.theme import LIGHT, Theme

GRID_STEPS_MM = (50, 100, 250, 500)
DEFAULT_GRID_STEP_MM = 250
GRID_MAJOR_MM = 1000
PLAN_MARGIN_MM = 500
PLAN_SCALE = 0.05  # пикселей на миллиметр
PILE_DIAMETER_MM = 108
PILE_HIT_RADIUS_MM = 250

SETTINGS_ORG = "pile-frame-designer"
SETTINGS_APP = "pile-frame-designer"
THEME_LABELS = {"system": "Как в системе", "light": "Светлая", "dark": "Тёмная"}
TOOL_LABELS = {"contour": "Контур", "piles": "Сваи"}


def snap(value_mm: float, step_mm: float = DEFAULT_GRID_STEP_MM) -> float:
    """Привязать координату к сетке."""
    return round(value_mm / step_mm) * step_mm


def orthogonal(previous: Point, point: Point) -> Point:
    """Сделать отрезок от предыдущей вершины горизонтальным или вертикальным."""
    dx, dy = point[0] - previous[0], point[1] - previous[1]
    return (point[0], previous[1]) if abs(dx) >= abs(dy) else (previous[0], point[1])


def _fmt(value: float, digits: int = 1) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


def _settings() -> QSettings:
    return QSettings(
        QSettings.Format.IniFormat, QSettings.Scope.UserScope, SETTINGS_ORG, SETTINGS_APP
    )


class PlanView(QGraphicsView):
    """План в миллиметрах. Инструмент «Контур» рисует контур, «Сваи» правит сваи."""

    edited = Signal()
    message = Signal(str)
    cursor_moved = Signal(float, float)

    def __init__(self, editor: PlanEditor) -> None:
        super().__init__()
        self.editor = editor
        self.grid_step_mm = DEFAULT_GRID_STEP_MM
        self.tool = "contour"
        self._area = QRectF(-PLAN_MARGIN_MM, -PLAN_MARGIN_MM, 13000, 10000)
        self._scene = QGraphicsScene(self._area)
        self.setScene(self._scene)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setRenderHint(self.renderHints().Antialiasing)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.scale(PLAN_SCALE, PLAN_SCALE)
        self._theme = LIGHT
        self._design: Design | None = None
        self._press: Point | None = None  # точка нажатия (с привязкой)
        self._cursor: Point | None = None
        self._rectangle = False  # идёт протягивание прямоугольника
        self._vertices: list[Point] = []  # вершины рисуемого контура
        self._dragged_pile: Point | None = None
        self._redraw()

    # --- состояние и отрисовка -------------------------------------------------------

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._redraw()

    def set_tool(self, tool: str) -> None:
        self.tool = tool
        self._vertices.clear()
        self._redraw()

    def set_grid_step(self, step_mm: int) -> None:
        self.grid_step_mm = step_mm
        self._redraw()

    def show_design(self, design: Design | None) -> None:
        self._design = design
        self._redraw()

    def pile_count(self) -> int:
        return len(self.editor.piles)

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
        self._scene.clear()
        self._scene.setBackgroundBrush(QColor(self._theme.plan_background))
        self._draw_grid()
        if self.editor.contour is not None:
            polygon = QPolygonF([QPointF(x, y) for x, y in self.editor.contour.vertices])
            self._scene.addPolygon(polygon, QPen(QColor(self._theme.outline), 0))
        if self._design is not None:
            self._draw_members(self._design)
        self._draw_piles()
        self._draw_preview()

    def _draw_grid(self) -> None:
        t, area, step = self._theme, self._area, self.grid_step_mm
        minor, major = QPen(QColor(t.grid_minor), 0), QPen(QColor(t.grid_major), 0)
        x = math.floor(area.left() / step) * step
        while x <= area.right():
            pen = major if x % GRID_MAJOR_MM == 0 else minor
            self._scene.addLine(x, area.top(), x, area.bottom(), pen)
            x += step
        y = math.floor(area.top() / step) * step
        while y <= area.bottom():
            pen = major if y % GRID_MAJOR_MM == 0 else minor
            self._scene.addLine(area.left(), y, area.right(), y, pen)
            y += step

    def _draw_members(self, design: Design) -> None:
        t = self._theme
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
            self._scene.addLine(x0, y0, x1, y1, pen)

    def _draw_piles(self) -> None:
        t, r = self._theme, PILE_DIAMETER_MM / 2
        outside = set(self._design.piles_outside) if self._design else set()
        for pile in self.editor.piles:
            x, y = self._cursor if pile == self._dragged_pile and self._cursor else pile
            if pile in outside:
                # Свая вне контура: крупное кольцо цвета ошибки вокруг сваи.
                ring = QPen(QColor(t.fail), 40)
                self._scene.addEllipse(x - 3 * r, y - 3 * r, 6 * r, 6 * r, ring)
            brush = QBrush(QColor(t.fail if pile in outside else t.pile))
            self._scene.addEllipse(x - r, y - r, 2 * r, 2 * r, Qt.PenStyle.NoPen, brush)
        if self._design is not None:
            ring = QPen(QColor(t.warning), 40, Qt.PenStyle.DashLine)
            for x, y in self._design.corners_without_piles:
                self._scene.addEllipse(x - 3 * r, y - 3 * r, 6 * r, 6 * r, ring)

    def _draw_preview(self) -> None:
        pen = QPen(QColor(self._theme.focus), 0, Qt.PenStyle.DashLine)
        if self._rectangle and self._press and self._cursor:
            self._scene.addRect(
                QRectF(QPointF(*self._press), QPointF(*self._cursor)).normalized(), pen
            )
        if self._vertices:
            points = list(self._vertices)
            if self._cursor is not None:
                points.append(orthogonal(points[-1], self._cursor))
            for a, b in zip(points, points[1:], strict=False):
                self._scene.addLine(a[0], a[1], b[0], b[1], pen)

    # --- мышь и клавиатура -----------------------------------------------------------

    def _snapped(self, event: QMouseEvent) -> Point:
        point = self.mapToScene(event.position().toPoint())
        step = self.grid_step_mm
        return (snap(point.x(), step), snap(point.y(), step))

    def _pile_at(self, event: QMouseEvent) -> Point | None:
        point = self.mapToScene(event.position().toPoint())
        nearest = min(
            self.editor.piles, key=lambda p: math.dist(p, (point.x(), point.y())), default=None
        )
        if nearest is not None and math.dist(nearest, (point.x(), point.y())) <= PILE_HIT_RADIUS_MM:
            return nearest
        return None

    def mousePressEvent(self, event: QMouseEvent) -> None:
        point = self._snapped(event)
        if self.tool == "piles" and event.button() == Qt.MouseButton.RightButton:
            pile = self._pile_at(event)
            if pile is not None:
                self.editor.delete_pile(pile)
                self.edited.emit()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._press, self._cursor = point, point
        if self.tool == "piles":
            self._dragged_pile = self._pile_at(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        point = self._snapped(event)
        self._cursor = point
        self.cursor_moved.emit(*point)
        if self.tool == "contour" and self._press is not None and point != self._press:
            self._rectangle = not self._vertices
        self._redraw()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self._press is None:
            return
        point, press = self._snapped(event), self._press
        self._press = None
        if self.tool == "contour":
            self._release_contour(press, point)
        else:
            self._release_piles(point)
        self._redraw()

    def _release_contour(self, press: Point, point: Point) -> None:
        if self._rectangle:
            self._rectangle = False
            if press[0] != point[0] and press[1] != point[1]:
                (x0, x1), (y0, y1) = sorted((press[0], point[0])), sorted((press[1], point[1]))
                self._apply_contour([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])
            return
        if self._vertices:
            point = orthogonal(self._vertices[-1], point)
        if len(self._vertices) >= 3 and point == self._vertices[0]:
            vertices, self._vertices = self._vertices, []
            self._apply_contour(vertices)
        elif not self._vertices or point != self._vertices[-1]:
            self._vertices.append(point)
            self.message.emit("Кликайте по вершинам; клик в первую вершину замыкает контур.")

    def _apply_contour(self, vertices: list[Point]) -> None:
        try:
            contour = Contour.from_points(vertices)
        except ContourError as error:
            self.message.emit(str(error))
            return
        self.editor.set_contour(contour)
        self.message.emit("")
        self.edited.emit()

    def _release_piles(self, point: Point) -> None:
        dragged, self._dragged_pile = self._dragged_pile, None
        if dragged is not None:
            if point != dragged:
                self.editor.move_pile(dragged, point)
                self.edited.emit()
        elif point not in self.editor.piles:
            self.editor.add_pile(point)
            self.edited.emit()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape and self._vertices:
            self._vertices.clear()
            self._redraw()
            return
        if event.key() == Qt.Key.Key_Delete and self.tool == "piles" and self._cursor:
            near = [
                p for p in self.editor.piles if math.dist(p, self._cursor) <= PILE_HIT_RADIUS_MM
            ]
            if near:
                self.editor.delete_pile(near[0])
                self.edited.emit()
            return
        super().keyPressEvent(event)


class ResultCard(QFrame):
    """Карточка результата: статус (иконка + текст) и ключевые числа."""

    ROWS = (
        "Габариты",
        "Площадь",
        "Свай",
        "Не проходят",
        "Балка",
        "Прочность",
        "Прогиб",
        "Замечания",
    )

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("card")
        self._theme = LIGHT
        self._status: Status | None = None
        self._icon = QLabel()
        self._icon.setFixedSize(20, 20)
        self._icon.hide()
        self._title = QLabel("Нарисуйте контур: протяните прямоугольник или кликайте по вершинам.")
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
            value.setWordWrap(True)
            rows.addWidget(name, i, 0, Qt.AlignmentFlag.AlignTop)
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

    def show_design(self, contour: Contour, design: Design) -> None:
        check, member = design.governing_check, design.governing_member
        utilization = max(check.strength_utilization, check.deflection_utilization)
        has_errors = bool(design.failing_members() or design.piles_outside)
        self._status = Status.FAIL if has_errors and utilization <= 1.0 else classify(utilization)
        v = self._values
        xs = [x for x, _ in contour.vertices]
        ys = [y for _, y in contour.vertices]
        v["Габариты"].setText(f"{max(xs) - min(xs):.0f} × {max(ys) - min(ys):.0f} мм")
        v["Площадь"].setText(f"{_fmt(contour.area_mm2 / 1e6)} м²")
        v["Свай"].setText(str(len(design.piles)))
        v["Не проходят"].setText(f"{len(design.failing_members())} из {len(design.members)}")
        v["Балка"].setText(f"{member.section.name}, {member.length_mm:.0f} мм")
        v["Прочность"].setText(f"{check.strength_utilization:.0%}")
        v["Прогиб"].setText(
            f"{_fmt(check.deflection_mm)} из {_fmt(check.deflection_limit_mm)} мм "
            f"({check.deflection_utilization:.0%})"
        )
        notes = []
        if design.piles_outside:
            notes.append(f"свай вне контура: {len(design.piles_outside)}")
        if design.corners_without_piles:
            notes.append(f"углов без свай: {len(design.corners_without_piles)}")
        v["Замечания"].setText(", ".join(notes) if notes else "нет")
        self._refresh_status_style()

    def clear(self) -> None:
        self._status = None
        self._icon.hide()
        self._title.setText("Нарисуйте контур: протяните прямоугольник или кликайте по вершинам.")
        self._title.setStyleSheet("")
        for value in self._values.values():
            value.setText("—")

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

        self.pile_step = QSpinBox(
            minimum=500, maximum=6000, singleStep=250, value=2000, suffix=" мм"
        )
        self.live_load = QDoubleSpinBox(
            minimum=0.0, maximum=50.0, singleStep=0.5, value=4.0, suffix=" кПа"
        )
        self.editor = PlanEditor(pile_step_mm=self.pile_step.value())
        self.plan = PlanView(self.editor)
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
        self._message = QLabel()
        self.statusBar().addWidget(self._coords)
        self.statusBar().addWidget(self._message, stretch=1)
        self._build_toolbar()
        self._build_menu()

        self.plan.edited.connect(self._recalculate)
        self.plan.message.connect(self._message.setText)
        self.plan.cursor_moved.connect(self._show_cursor)
        self.pile_step.valueChanged.connect(self._on_pile_step)
        self.live_load.valueChanged.connect(self._recalculate)

        self._theme_mode = "system"
        self.set_theme_mode(str(_settings().value("theme", "system")))
        self.set_tool("contour")

    # --- панели и меню ---------------------------------------------------------------

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Инструменты")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        self._tool_actions = QActionGroup(self)
        for tool, label in TOOL_LABELS.items():
            action = QAction(label, self, checkable=True)
            action.setData(tool)
            action.triggered.connect(self._on_tool_action)
            self._tool_actions.addAction(action)
            toolbar.addAction(action)
        toolbar.addSeparator()
        self.undo_action = QAction("Отменить", self, shortcut=QKeySequence.StandardKey.Undo)
        self.redo_action = QAction("Повторить", self)
        self.redo_action.setShortcuts([QKeySequence("Ctrl+Y"), QKeySequence("Ctrl+Shift+Z")])
        self.undo_action.triggered.connect(self._undo)
        self.redo_action.triggered.connect(self._redo)
        toolbar.addAction(self.undo_action)
        toolbar.addAction(self.redo_action)
        toolbar.addSeparator()
        toolbar.addWidget(QLabel(" Сетка "))
        self.grid_step = QComboBox()
        for step in GRID_STEPS_MM:
            self.grid_step.addItem(f"{step} мм", step)
        self.grid_step.setCurrentIndex(GRID_STEPS_MM.index(DEFAULT_GRID_STEP_MM))
        self.grid_step.currentIndexChanged.connect(
            lambda _: self.plan.set_grid_step(self.grid_step.currentData())
        )
        toolbar.addWidget(self.grid_step)

    def _build_menu(self) -> None:
        edit = self.menuBar().addMenu("Правка")
        edit.addAction(self.undo_action)
        edit.addAction(self.redo_action)
        view = self.menuBar().addMenu("Вид")
        theme_menu = view.addMenu("Тема")
        self._theme_actions = QActionGroup(self)
        for mode in THEME_MODES:
            action = QAction(THEME_LABELS[mode], self, checkable=True)
            action.setData(mode)
            action.triggered.connect(self._on_theme_action)
            self._theme_actions.addAction(action)
            theme_menu.addAction(action)

    def set_tool(self, tool: str) -> None:
        """Выбрать инструмент: «contour» или «piles»."""
        self.plan.set_tool(tool)
        for action in self._tool_actions.actions():
            action.setChecked(action.data() == tool)
        hints = {
            "contour": "Протяните прямоугольник или кликайте по вершинам контура.",
            "piles": "Клик — добавить сваю, перетащить — сдвинуть, "
            "правый клик или Delete — удалить.",
        }
        self._message.setText(hints[tool])

    def _on_tool_action(self) -> None:
        action = self._tool_actions.checkedAction()
        if action is not None:
            self.set_tool(str(action.data()))

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

    # --- правка и расчёт -------------------------------------------------------------

    def _undo(self) -> None:
        self.editor.undo()
        self._recalculate()

    def _redo(self) -> None:
        self.editor.redo()
        self._recalculate()

    def _on_pile_step(self, step_mm: int) -> None:
        self.editor.set_pile_step(step_mm)
        self._recalculate()

    def _recalculate(self) -> None:
        self.undo_action.setEnabled(self.editor.can_undo)
        self.redo_action.setEnabled(self.editor.can_redo)
        contour = self.editor.contour
        if contour is None or not self.editor.piles:
            self.plan.show_design(None)
            self.result_card.clear()
            return
        design = analyze(
            Project(
                contour=contour,
                piles=self.editor.piles,
                pile_step_mm=self.pile_step.value(),
                live_load_kpa=self.live_load.value(),
            )
        )
        self.plan.show_design(design)
        self.result_card.show_design(contour, design)

    def result_text(self) -> str:
        return self.result_card.text()


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
