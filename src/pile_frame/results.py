"""Результаты: проверки балок, реакции свай, сварные швы и допущения."""

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

from pile_frame import assumptions
from pile_frame.design import Design
from pile_frame.status import classify

SORT_ROLE = Qt.ItemDataRole.UserRole + 1
MEMBER_ROLE = Qt.ItemDataRole.UserRole + 2


def _item(text: str, sort_value: float | str, member: int | None = None) -> QStandardItem:
    item = QStandardItem(text)
    item.setData(sort_value, SORT_ROLE)
    item.setEditable(False)
    if member is not None:
        item.setData(member, MEMBER_ROLE)
    if isinstance(sort_value, (int, float)):
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return item


def _fmt(value: float, digits: int = 1) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


def member_label(index: int) -> str:
    return f"Б{index + 1}"


def pile_label(index: int) -> str:
    return f"С{index + 1}"


def _table() -> QTableView:
    view = QTableView()
    view.setSortingEnabled(True)
    view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    view.verticalHeader().setVisible(False)
    view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    view.horizontalHeader().setStretchLastSection(True)
    return view


class ResultsPanel(QTabWidget):
    """Вкладки «Балки», «Сваи и реакции», «Швы», «Допущения». Выбор балки сообщает её индекс."""

    member_selected = Signal(int)

    MEMBER_COLUMNS = (
        "Элемент",
        "Профиль",
        "Длина, мм",
        "M, кН·м",
        "Q, кН",
        "Изгиб, %",
        "Срез, %",
        "Прогиб, мм",
        "Прогиб, %",
        "Стенка, %",
        "Пояс, %",
        "Использование, %",
        "Итог",
    )
    UTILIZATION_COLUMN = MEMBER_COLUMNS.index("Использование, %")

    def __init__(self) -> None:
        super().__init__()
        self._member_model = QStandardItemModel(0, len(self.MEMBER_COLUMNS))
        self._member_model.setHorizontalHeaderLabels(list(self.MEMBER_COLUMNS))
        self._member_proxy = QSortFilterProxyModel()
        self._member_proxy.setSourceModel(self._member_model)
        self._member_proxy.setSortRole(SORT_ROLE)
        self.members = _table()
        self.members.setModel(self._member_proxy)
        self.members.selectionModel().currentRowChanged.connect(self._on_row)

        self._pile_model = QStandardItemModel(0, 4)
        self._pile_model.setHorizontalHeaderLabels(["Свая", "X, мм", "Y, мм", "Реакция, кН"])
        pile_proxy = QSortFilterProxyModel()
        pile_proxy.setSourceModel(self._pile_model)
        pile_proxy.setSortRole(SORT_ROLE)
        self.piles = _table()
        self.piles.setModel(pile_proxy)

        self._weld_model = QStandardItemModel(0, 7)
        self._weld_model.setHorizontalHeaderLabels(
            [
                "X, мм",
                "Y, мм",
                "Сила, кН",
                "Катет, мм",
                "Длина, мм",
                "Расчёт по",
                "Использование, %",
            ]
        )
        weld_proxy = QSortFilterProxyModel()
        weld_proxy.setSourceModel(self._weld_model)
        weld_proxy.setSortRole(SORT_ROLE)
        self.welds = _table()
        self.welds.setModel(weld_proxy)

        self.assumptions = QPlainTextEdit(assumptions.as_text())
        self.assumptions.setReadOnly(True)

        self.addTab(self.members, "Балки")
        self.addTab(self.piles, "Сваи и реакции")
        self.addTab(self.welds, "Швы")
        self.addTab(self.assumptions, "Допущения")

    def show_design(self, design: Design | None) -> None:
        self._member_model.setRowCount(0)
        self._pile_model.setRowCount(0)
        self._weld_model.setRowCount(0)
        if design is None:
            return
        unsupported = {id(m) for m in design.unsupported_members}
        for index, (member, check) in enumerate(zip(design.members, design.checks, strict=True)):
            status = classify(check.utilization)
            verdict = "нет опоры" if id(member) in unsupported else status.label
            row = [
                _item(member_label(index), index, index),
                _item(member.section.name, member.section.name),
                _item(f"{member.length_mm:.0f}", member.length_mm),
                _item(_fmt(check.max_moment_knm, 2), check.max_moment_knm),
                _item(_fmt(check.max_shear_kn, 2), check.max_shear_kn),
                _item(f"{check.strength_utilization:.0%}", check.strength_utilization),
                _item(f"{check.shear_utilization:.0%}", check.shear_utilization),
                _item(_fmt(check.deflection_mm), check.deflection_mm),
                _item(f"{check.deflection_utilization:.0%}", check.deflection_utilization),
                _item(f"{check.web_utilization:.0%}", check.web_utilization),
                _item(f"{check.flange_utilization:.0%}", check.flange_utilization),
                _item(f"{check.utilization:.0%}", check.utilization),
                _item(verdict, check.utilization),
            ]
            self._member_model.appendRow(row)
        for index, (pile, reaction) in enumerate(design.reactions_kn.items()):
            self._pile_model.appendRow(
                [
                    _item(pile_label(index), index),
                    _item(f"{pile[0]:.0f}", pile[0]),
                    _item(f"{pile[1]:.0f}", pile[1]),
                    _item(_fmt(reaction, 2), reaction),
                ]
            )

        for weld in design.welds:
            check = weld.check
            self._weld_model.appendRow(
                [
                    _item(f"{weld.point[0]:.0f}", weld.point[0]),
                    _item(f"{weld.point[1]:.0f}", weld.point[1]),
                    _item(_fmt(check.force_kn, 2), check.force_kn),
                    _item(str(check.leg_mm), check.leg_mm),
                    _item(f"{check.length_mm:.0f}", check.length_mm),
                    _item(check.governing, check.governing),
                    _item(f"{check.utilization:.0%}", check.utilization),
                ]
            )

    def assumptions_text(self) -> str:
        return self.assumptions.toPlainText()

    def member_index_at(self, row: int) -> int:
        """Индекс элемента в проекте для строки таблицы с учётом сортировки."""
        return int(self._member_proxy.index(row, 0).data(MEMBER_ROLE))

    def _on_row(self, current, _previous) -> None:
        if current.isValid():
            self.member_selected.emit(self.member_index_at(current.row()))
