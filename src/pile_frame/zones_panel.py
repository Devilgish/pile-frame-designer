"""Панель зон: назначение новой зоны, список зон с нагрузкой и вариантом холодильной камеры."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QLabel,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from pile_frame.editor import PlanEditor
from pile_frame.zones import PRESETS, Zone

NOTE = (
    "Нагрузки зон приняты по аналогии с СП 20.13330.2016 и СНиП 2.01.07-85 — "
    "уточнить у технолога. Источник — в подсказке к полю."
)


def _kind_combo() -> QComboBox:
    combo = QComboBox()
    for kind, preset in PRESETS.items():
        combo.addItem(preset.title, kind)
    return combo


@dataclass
class ZoneRow:
    kind: QComboBox
    load: QDoubleSpinBox
    on_board: QCheckBox
    remove: QToolButton


class ZonesPanel(QWidget):
    """Правки зон идут в редактор плана; ``edited`` сообщает окну, что пора пересчитать."""

    edited = Signal()

    def __init__(self, editor: PlanEditor) -> None:
        super().__init__()
        self._editor = editor
        self.new_kind = _kind_combo()
        self.new_kind.setToolTip("Назначение зоны, которую вы нарисуете инструментом «Зоны».")
        self.note = QLabel(NOTE)
        self.note.setWordWrap(True)
        self.note.setProperty("role", "muted")
        self._empty = QLabel("Зон нет: выберите инструмент «Зоны» и протяните прямоугольник.")
        self._empty.setWordWrap(True)
        self._empty.setProperty("role", "muted")
        self._grid = QGridLayout()
        self._grid.setHorizontalSpacing(8)
        self._grid.setVerticalSpacing(4)
        self.rows: list[ZoneRow] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        new = QGridLayout()
        new.addWidget(QLabel("Новая зона"), 0, 0)
        new.addWidget(self.new_kind, 0, 1)
        new.setColumnStretch(1, 1)
        layout.addLayout(new)
        layout.addWidget(self._empty)
        layout.addLayout(self._grid)
        layout.addWidget(self.note)
        # Не сжимать строки зон: если панели мало места, прокручивается вся колонка.
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)

    def refresh(self, zones: tuple[Zone, ...]) -> None:
        """Показать зоны редактора; строки обновляются на месте, если число зон то же."""
        if len(zones) != len(self.rows):
            self._rebuild(len(zones))
        for row, zone in zip(self.rows, zones, strict=True):
            for widget in (row.kind, row.load, row.on_board):
                widget.blockSignals(True)
            row.kind.setCurrentIndex(row.kind.findData(zone.kind))
            row.kind.setToolTip(PRESETS[zone.kind].source)
            row.load.setValue(zone.live_load_kpa)
            row.load.setToolTip(PRESETS[zone.kind].source)
            row.on_board.setChecked(zone.cold_on_board)
            row.on_board.setVisible(zone.kind == "cold")
            for widget in (row.kind, row.load, row.on_board):
                widget.blockSignals(False)
        self._empty.setVisible(not zones)

    def _rebuild(self, count: int) -> None:
        for row in self.rows:
            for widget in (row.kind, row.load, row.on_board, row.remove):
                self._grid.removeWidget(widget)
                widget.hide()  # до удаления в цикле событий виджет не должен мелькать
                widget.deleteLater()
        self.rows = []
        for index in range(count):
            kind = _kind_combo()
            load = QDoubleSpinBox(minimum=0.0, maximum=50.0, singleStep=0.5, suffix=" кПа")
            load.setDecimals(2)
            on_board = QCheckBox("Стоит на ЦСП (не сборный пол)")
            remove = QToolButton()
            remove.setText("✕")
            remove.setToolTip("Удалить зону")
            remove.setAccessibleName("Удалить зону")
            load.setFixedWidth(112)
            kind.currentIndexChanged.connect(
                lambda _=0, i=index, w=kind: self._apply(
                    self._editor.set_zone_kind, i, w.currentData()
                )
            )
            load.valueChanged.connect(
                lambda value, i=index: self._apply(self._editor.set_zone_load, i, value)
            )
            on_board.toggled.connect(
                lambda value, i=index: self._apply(self._editor.set_zone_cold_on_board, i, value)
            )
            remove.clicked.connect(
                lambda _=False, i=index: self._apply(self._editor.remove_zone, i)
            )
            base = 2 * index
            self._grid.addWidget(kind, base, 0)
            self._grid.addWidget(load, base, 1)
            self._grid.addWidget(remove, base, 2)
            self._grid.addWidget(on_board, base + 1, 0, 1, 3)
            self.rows.append(ZoneRow(kind, load, on_board, remove))
        self._grid.setColumnStretch(0, 1)

    def _apply(self, action, *args) -> None:
        action(*args)
        self.refresh(self._editor.zones)
        self.edited.emit()
