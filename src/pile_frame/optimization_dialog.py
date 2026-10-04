"""Диалог оптимизации: перебор в фоне с прогрессом и отменой, сравнение и применение варианта."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from pile_frame.design import Design, Project
from pile_frame.optimizer import OptimizationResult, Variant, explain, optimize
from pile_frame.sections import Section
from pile_frame.tables import fmt

COLUMNS = (
    "Масса, кг",
    "Легче текущего, кг",
    "Листы",
    "Отходы ЦСП, м²",
    "Опирание, кромок",
    "Что изменено",
)


class _Worker(QObject):
    """Перебор в отдельном потоке; отмена — флаг, который читает оптимизатор."""

    progressed = Signal(int, int)
    finished = Signal(object)

    def __init__(self, project: Project, sections: tuple[Section, ...], step_mm: float) -> None:
        super().__init__()
        self._project, self._sections, self._step = project, sections, step_mm
        self.stop = False

    def run(self) -> None:
        result = optimize(
            self._project,
            self._sections,
            step_mm=self._step,
            progress=lambda done, total: self.progressed.emit(done, total),
            cancelled=lambda: self.stop,
        )
        self.finished.emit(result)


class OptimizationDialog(QDialog):
    """``apply`` получает выбранный вариант; окно применяет его и умеет отменить."""

    def __init__(
        self,
        project: Project,
        current: Design,
        sections: tuple[Section, ...],
        apply: Callable[[Variant], None],
        *,
        step_mm: float = 250.0,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Оптимизация по массе металла")
        self.resize(900, 560)
        self._project, self._current, self._sections = project, current, sections
        self._apply, self._step = apply, step_mm
        self.variants: list[Variant] = []
        self.done = False
        self.cancelled = False
        self._thread: QThread | None = None
        self._worker: _Worker | None = None

        self.status = QLabel(
            "Перебираются ориентация и смещение листов, профили периметра и внутренних балок "
            "(той же высоты) и точечные усиления. В выдаче только варианты, проходящие все "
            "проверки. Отходы ЦСП показаны, но в цель не входят."
        )
        self.status.setWordWrap(True)
        self.progress = QProgressBar()
        self.cancel_button = QPushButton("Отмена")
        self.cancel_button.clicked.connect(self.cancel)
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(list(COLUMNS))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._show_explanation)
        self.explanation = QPlainTextEdit()
        self.explanation.setReadOnly(True)
        self.apply_button = QPushButton("Применить вариант")
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(self._apply_selected)
        close = QPushButton("Закрыть")
        close.clicked.connect(self.reject)

        top = QHBoxLayout()
        top.addWidget(self.progress, stretch=1)
        top.addWidget(self.cancel_button)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.apply_button)
        buttons.addWidget(close)
        layout = QVBoxLayout(self)
        layout.addWidget(self.status)
        layout.addLayout(top)
        layout.addWidget(self.table, stretch=2)
        layout.addWidget(QLabel("Почему этот вариант легче"))
        layout.addWidget(self.explanation, stretch=1)
        layout.addLayout(buttons)

    def start(self) -> None:
        self._thread = QThread(self)
        self._worker = _Worker(self._project, self._sections, self._step)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progressed.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.finished.connect(self._thread.quit)
        self._thread.start()

    def cancel(self) -> None:
        if self._worker is not None:
            self._worker.stop = True
        self.cancel_button.setEnabled(False)

    def _on_progress(self, done: int, total: int) -> None:
        self.progress.setMaximum(max(total, 1))
        self.progress.setValue(done)

    def _on_finished(self, result: OptimizationResult) -> None:
        self.variants = result.variants
        self.cancelled = result.cancelled
        self.cancel_button.setEnabled(False)
        if result.cancelled:
            self.status.setText(
                f"Остановлено: просчитано {result.analysed} вариантов, показаны лучшие из них."
            )
        else:
            self.progress.setValue(self.progress.maximum())
            self.status.setText(
                f"Готово: {result.total} вариантов раскладки и профилей, полностью просчитано "
                f"{result.analysed} (остальные заведомо тяжелее)."
            )
        self._fill()
        self.done = True

    def _fill(self) -> None:
        self.table.setRowCount(len(self.variants))
        base = self._current.steel_mass_kg
        for row, variant in enumerate(self.variants):
            layout = variant.design.sheet_layout
            values = (
                fmt(variant.mass_kg),
                fmt(base - variant.mass_kg),
                f"{layout.whole_count} целых, {layout.cut_count} резаных",
                fmt(layout.offcut_m2),
                str(len(variant.design.bearing_issues)),
                ", ".join(variant.changes),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)  # длинный перечень изменений виден целиком
                if column < 5:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                self.table.setItem(row, column, item)
        if self.variants:
            self.table.selectRow(0)
        else:
            self.explanation.setPlainText("Проходящих вариантов не найдено.")

    def _selected(self) -> int | None:
        rows = self.table.selectionModel().selectedRows()
        return rows[0].row() if rows else None

    def _show_explanation(self) -> None:
        row = self._selected()
        self.apply_button.setEnabled(row is not None)
        if row is None:
            return
        variant = self.variants[row]
        others = [v for i, v in enumerate(self.variants) if i > row]
        self.explanation.setPlainText("\n".join(explain(variant, self._current, others)))

    def _apply_selected(self) -> None:
        row = self._selected()
        if row is not None:
            self._apply(self.variants[row])

    def closeEvent(self, event) -> None:  # noqa: N802 — имя метода Qt
        self.cancel()
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
        super().closeEvent(event)

    def reject(self) -> None:
        self.cancel()
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
        super().reject()
