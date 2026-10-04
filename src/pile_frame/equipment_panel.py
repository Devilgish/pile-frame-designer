"""Панель оборудования: выбор позиции для установки, список на плане, библиотека."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from pile_frame.editor import PlanEditor
from pile_frame.equipment import Equipment, EquipmentError, EquipmentLibrary
from pile_frame.tables import fmt

NOTE = (
    "Клик инструментом «Оборудование» ставит выбранную позицию, перетаскивание двигает, "
    "R — поворот на 90°, правый клик или Delete — удалить. Оборудование стоит целиком внутри "
    "контура. На границе зон его вес от зон не зависит, лист под ним считается по более "
    "тяжёлой зоне. Массы типовые — уточнить по паспорту."
)


@dataclass
class EquipmentRow:
    name: QLabel
    rotate: QToolButton
    remove: QToolButton


class EquipmentPanel(QWidget):
    """Правки оборудования идут в редактор плана; ``edited`` просит окно пересчитать."""

    edited = Signal()
    message = Signal(str)

    def __init__(self, editor: PlanEditor, library: EquipmentLibrary) -> None:
        super().__init__()
        self._editor = editor
        self._library = library
        self.new_type = QComboBox()
        # Длинные названия не распирают колонку шириной 340 px.
        self.new_type.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.new_type.setMinimumContentsLength(14)
        self.library_button = QPushButton("Библиотека…")
        self.total = QLabel()
        self.total.setProperty("role", "muted")
        self.note = QLabel(NOTE)
        self.note.setWordWrap(True)
        self.note.setProperty("role", "muted")
        self._grid = QGridLayout()
        self._grid.setHorizontalSpacing(6)
        self._grid.setVerticalSpacing(2)
        self.rows: list[EquipmentRow] = []
        choose = QHBoxLayout()
        choose.addWidget(self.new_type, stretch=1)
        choose.addWidget(self.library_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addLayout(choose)
        layout.addLayout(self._grid)
        layout.addWidget(self.total)
        layout.addWidget(self.note)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self.refresh_library()

    @property
    def selected_type(self):
        return self._library.get(self.new_type.currentText())

    def refresh_library(self) -> None:
        current = self.new_type.currentText()
        self.new_type.blockSignals(True)
        self.new_type.clear()
        for item in self._library.items:
            self.new_type.addItem(item.name)
            self.new_type.setItemData(
                self.new_type.count() - 1,
                f"{item.length_mm:g} × {item.width_mm:g} мм, {item.own_kg:g} + "
                f"{item.content_kg:g} кг — {item.note}",
            )
        if current:
            self.new_type.setCurrentText(current)
        self.new_type.blockSignals(False)

    def refresh(self, equipment: tuple[Equipment, ...]) -> None:
        if len(equipment) != len(self.rows):
            self._rebuild(len(equipment))
        for row, item in zip(self.rows, equipment, strict=True):
            mass = item.type.own_kg + item.type.content_kg
            row.name.setText(f"{item.type.name}, {mass:g} кг")
            row.name.setToolTip(item.type.note)
        normative = sum(e.type.normative_weight_kn for e in equipment)
        design = sum(e.type.design_weight_kn for e in equipment)
        self.total.setText(
            f"Итого {len(equipment)} шт.: нормативная {fmt(normative, 2)} кН, "
            f"расчётная {fmt(design, 2)} кН"
            if equipment
            else "Оборудования на плане нет."
        )

    def _rebuild(self, count: int) -> None:
        for row in self.rows:
            for widget in (row.name, row.rotate, row.remove):
                self._grid.removeWidget(widget)
                widget.hide()
                widget.deleteLater()
        self.rows = []
        for index in range(count):
            name = QLabel()
            name.setWordWrap(True)
            rotate = QToolButton()
            rotate.setText("⟳")
            rotate.setToolTip("Повернуть на 90°")
            rotate.setAccessibleName("Повернуть на 90°")
            remove = QToolButton()
            remove.setText("✕")
            remove.setToolTip("Удалить оборудование")
            remove.setAccessibleName("Удалить оборудование")
            rotate.clicked.connect(
                lambda _=False, i=index: self._apply(self._editor.rotate_equipment, i)
            )
            remove.clicked.connect(
                lambda _=False, i=index: self._apply(self._editor.remove_equipment, i)
            )
            self._grid.addWidget(name, index, 0)
            self._grid.addWidget(rotate, index, 1)
            self._grid.addWidget(remove, index, 2)
            self.rows.append(EquipmentRow(name, rotate, remove))
        self._grid.setColumnStretch(0, 1)

    def _apply(self, action, *args) -> None:
        try:
            action(*args)
        except EquipmentError as error:
            self.message.emit(str(error))
            return
        self.refresh(self._editor.equipment)
        self.edited.emit()


_NUMBER_FIELDS = (
    ("length_mm", "Длина (вдоль X)", " мм", 10, 10000),
    ("width_mm", "Ширина", " мм", 10, 10000),
    ("own_kg", "Собственная масса", " кг", 0, 20000),
    ("content_kg", "Загрузка (продукты, вода)", " кг", 0, 20000),
)


class LibraryDialog(QDialog):
    """Добавить своё оборудование в библиотеку; ``on_change`` сохраняет библиотеку."""

    def __init__(
        self, library: EquipmentLibrary, on_change: Callable[[], None] | None = None, parent=None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Библиотека оборудования")
        self._library = library
        self._on_change = on_change
        self.fields: dict[str, QLineEdit | QDoubleSpinBox] = {"name": QLineEdit()}
        form = QFormLayout()
        form.addRow("Название", self.fields["name"])
        for key, label, suffix, low, high in _NUMBER_FIELDS:
            spin = QDoubleSpinBox(minimum=low, maximum=high, suffix=suffix)
            spin.setDecimals(0)
            self.fields[key] = spin
            form.addRow(label, spin)
        self.issues = QLabel()
        self.issues.setWordWrap(True)
        self.add_button = QPushButton("Добавить")
        self.add_button.clicked.connect(self._add)
        self.items = QLabel()
        self.items.setWordWrap(True)
        self.items.setProperty("role", "muted")
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.issues)
        layout.addWidget(self.add_button)
        layout.addWidget(self.items)
        self._show_items()

    def _show_items(self) -> None:
        own = [i for i in self._library.items if i.note == "своя позиция" or "из файла" in i.name]
        names = ", ".join(i.name for i in own) or "своих позиций пока нет"
        self.items.setText(f"Свои позиции: {names}.")

    def _add(self) -> None:
        values = {"name": self.fields["name"].text()}
        values |= {key: self.fields[key].value() for key, *_ in _NUMBER_FIELDS}
        issues = self._library.add(**values)
        if issues:
            self.issues.setText("\n".join(issue.message for issue in issues))
            return
        self.issues.setText(f"«{values['name'].strip()}» добавлено.")
        if self._on_change is not None:
            self._on_change()
        self._show_items()
