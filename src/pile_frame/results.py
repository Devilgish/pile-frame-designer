"""Результаты: проверки балок, листов ЦСП, реакции свай, сварные швы и допущения."""

from __future__ import annotations

from PySide6.QtCore import QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QPlainTextEdit,
    QTableView,
    QTabWidget,
)

from pile_frame import assumptions, tables
from pile_frame.design import Design

SORT_ROLE = Qt.ItemDataRole.UserRole + 1
MEMBER_ROLE = Qt.ItemDataRole.UserRole + 2


def _item(cell: tables.Cell, member: int | None = None) -> QStandardItem:
    text, sort_value = cell
    item = QStandardItem(text)
    item.setData(sort_value, SORT_ROLE)
    item.setEditable(False)
    if member is not None:
        item.setData(member, MEMBER_ROLE)
    if isinstance(sort_value, (int, float)):
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return item


def _table(columns: tuple[str, ...]) -> tuple[QTableView, QStandardItemModel]:
    model = QStandardItemModel(0, len(columns))
    model.setHorizontalHeaderLabels(list(columns))
    proxy = QSortFilterProxyModel()
    proxy.setSourceModel(model)
    proxy.setSortRole(SORT_ROLE)
    view = QTableView()
    view.setModel(proxy)
    view.setSortingEnabled(True)
    view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    view.verticalHeader().setVisible(False)
    view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    view.horizontalHeader().setStretchLastSection(True)
    return view, model


class ResultsPanel(QTabWidget):
    """Вкладки «Балки», «Листы ЦСП», «Сваи и реакции», «Швы», «Допущения».

    Выбор балки сообщает её индекс.
    """

    member_selected = Signal(int)

    MEMBER_COLUMNS = tables.MEMBER_COLUMNS
    UTILIZATION_COLUMN = MEMBER_COLUMNS.index("Использование, %")

    def __init__(self) -> None:
        super().__init__()
        self.members, self._member_model = _table(tables.MEMBER_COLUMNS)
        self._member_proxy = self.members.model()
        self.members.selectionModel().currentRowChanged.connect(self._on_row)
        self.boards, self._board_model = _table(tables.BOARD_COLUMNS)
        self.piles, self._pile_model = _table(tables.PILE_COLUMNS)
        self.welds, self._weld_model = _table(tables.WELD_COLUMNS)

        self.assumptions = QPlainTextEdit(assumptions.as_text())
        self.assumptions.setReadOnly(True)

        self.addTab(self.members, "Балки")
        self.addTab(self.boards, "Листы ЦСП")
        self.addTab(self.piles, "Сваи и реакции")
        self.addTab(self.welds, "Швы")
        self.addTab(self.assumptions, "Допущения")

    def show_design(self, design: Design | None) -> None:
        for model in (self._member_model, self._board_model, self._pile_model, self._weld_model):
            model.setRowCount(0)
        if design is None:
            return
        unsupported = {id(m) for m in design.unsupported_members}
        for index, (member, check) in enumerate(zip(design.members, design.checks, strict=True)):
            row = tables.member_row(index, member, check, id(member) in unsupported)
            self._member_model.appendRow([_item(row[0], index)] + [_item(c) for c in row[1:]])
        for cell in design.board_cells:
            self._board_model.appendRow([_item(c) for c in tables.board_row(cell)])
        for index, (pile, reaction) in enumerate(design.reactions_kn.items()):
            self._pile_model.appendRow([_item(c) for c in tables.pile_row(index, pile, reaction)])
        for weld in design.welds:
            self._weld_model.appendRow([_item(c) for c in tables.weld_row(weld)])

    def assumptions_text(self) -> str:
        return self.assumptions.toPlainText()

    def member_index_at(self, row: int) -> int:
        """Индекс элемента в проекте для строки таблицы с учётом сортировки."""
        return int(self._member_proxy.index(row, 0).data(MEMBER_ROLE))

    def _on_row(self, current, _previous) -> None:
        if current.isValid():
            self.member_selected.emit(self.member_index_at(current.row()))
