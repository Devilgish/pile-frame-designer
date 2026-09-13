"""Поля ввода исходных данных и окно справочника профилей."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from pile_frame.issues import Issue
from pile_frame.sections import GOST_SECTIONS, ProfileCatalog
from pile_frame.theme import LIGHT, Theme


def parse_number(text: str) -> float | None:
    """Число из строки: допускаются запятая и пробелы между разрядами."""
    try:
        return float(text.replace(" ", "").replace(" ", "").replace(",", "."))
    except ValueError:
        return None


def format_number(value: float) -> str:
    return f"{value:g}".replace(".", ",")


class NumberField(QWidget):
    """Числовое поле с единицами и строкой замечания под ним."""

    edited = Signal()

    def __init__(self, value: float, unit: str) -> None:
        super().__init__()
        self._theme = LIGHT
        self.editor = QLineEdit(format_number(value))
        self.editor.setAlignment(Qt.AlignmentFlag.AlignRight)
        unit_label = QLabel(unit)
        unit_label.setProperty("role", "muted")
        unit_label.setMinimumWidth(34)
        self.issue_label = QLabel()
        self.issue_label.setWordWrap(True)
        self.issue_label.hide()

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        row.addWidget(self.editor, stretch=1)
        row.addWidget(unit_label)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addLayout(row)
        layout.addWidget(self.issue_label)
        self.editor.editingFinished.connect(self.edited.emit)

    def value(self) -> float | None:
        return parse_number(self.editor.text())

    def set_value(self, value: float) -> None:
        self.editor.setText(format_number(value))

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme

    def show_issue(self, issue: Issue | None) -> None:
        """Показать ошибку или предупреждение под полем; ``None`` — скрыть."""
        if issue is None:
            self.issue_label.hide()
            self.issue_label.clear()
            return
        color = self._theme.fail if issue.severity == "error" else self._theme.warning
        prefix = "Ошибка: " if issue.severity == "error" else "Внимание: "
        self.issue_label.setText(prefix + issue.message)
        self.issue_label.setStyleSheet(f"color: {color}; font-size: 9pt;")
        self.issue_label.show()


PROFILE_FIELDS = (
    ("name", "Название", ""),
    ("height_mm", "Высота", "мм"),
    ("width_mm", "Ширина", "мм"),
    ("thickness_mm", "Стенка", "мм"),
    ("mass_kg_m", "Масса", "кг/м"),
    ("area_cm2", "Площадь", "см²"),
    ("ix_cm4", "Ix", "см⁴"),
    ("wx_cm3", "Wx", "см³"),
)


class ProfilesDialog(QDialog):
    """Справочник профилей: таблица и форма добавления своего профиля."""

    def __init__(
        self, catalog: ProfileCatalog, theme: Theme, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Справочник профилей")
        self.resize(900, 640)
        self.catalog = catalog
        self._theme = theme

        self.table = QTableWidget(0, len(PROFILE_FIELDS))
        self.table.setHorizontalHeaderLabels(
            [f"{label}, {unit}" if unit else label for _, label, unit in PROFILE_FIELDS]
        )
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setMinimumHeight(220)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        remove = QPushButton("Удалить выбранный")
        remove.clicked.connect(self._remove_selected)

        self.name = QLineEdit()
        self.name_issue = QLabel()
        self.name_issue.hide()
        self.fields: dict[str, NumberField] = {}
        form = QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(6)
        name_box = QVBoxLayout()
        name_box.setSpacing(2)
        name_box.addWidget(self.name)
        name_box.addWidget(self.name_issue)
        form.addWidget(QLabel("Название"), 0, 0)
        form.addLayout(name_box, 0, 1, 1, 3)
        # Поля в две колонки, чтобы таблица справочника оставалась крупной.
        for index, (key, label, unit) in enumerate(PROFILE_FIELDS[1:]):
            field = NumberField(0, unit)
            field.editor.clear()
            field.set_theme(theme)
            self.fields[key] = field
            row, col = 1 + index // 2, (index % 2) * 2
            form.addWidget(QLabel(label), row, col, Qt.AlignmentFlag.AlignTop)
            form.addWidget(field, row, col + 1)
        add = QPushButton("Добавить профиль")
        add.clicked.connect(self._add)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("Закрыть")
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.table, stretch=1)
        layout.addWidget(remove, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(QLabel("Свой профиль (характеристики из сортамента производителя)"))
        layout.addLayout(form)
        layout.addWidget(add, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(buttons)
        self._refresh()

    def _refresh(self) -> None:
        sections = self.catalog.sections
        self.table.setRowCount(len(sections))
        gost = {s.name for s in GOST_SECTIONS}
        for row, section in enumerate(sections):
            for col, (key, _, _) in enumerate(PROFILE_FIELDS):
                value = getattr(section, key)
                text = value if key == "name" else format_number(value)
                if key == "name" and section.name in gost:
                    text = f"{value} (ГОСТ 30245)"
                self.table.setItem(row, col, QTableWidgetItem(str(text)))

    def _add(self) -> None:
        values: dict[str, float | str] = {"name": self.name.text()}
        unreadable = [key for key, field in self.fields.items() if field.value() is None]
        for key, field in self.fields.items():
            values[key] = field.value() if key not in unreadable else 0.0
        if unreadable:
            issues = [Issue(key, "Введите число.") for key in unreadable]
            issues += [i for i in self.catalog.validate(**values) if i.field not in unreadable]
        else:
            issues = self.catalog.add(**values)
        by_field = {i.field: i for i in issues}
        self._show_name_issue(by_field.get("name"))
        for key, field in self.fields.items():
            field.show_issue(by_field.get(key))
        if not issues:
            self.name.clear()
            for field in self.fields.values():
                field.editor.clear()
            self._refresh()

    def _show_name_issue(self, issue: Issue | None) -> None:
        if issue is None:
            self.name_issue.hide()
            return
        self.name_issue.setText("Ошибка: " + issue.message)
        self.name_issue.setStyleSheet(f"color: {self._theme.fail}; font-size: 9pt;")
        self.name_issue.show()

    def _remove_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        name = self.catalog.sections[row].name
        try:
            self.catalog.remove(name)
        except ValueError as error:
            self._show_name_issue(Issue("name", str(error)))
            return
        self._refresh()
