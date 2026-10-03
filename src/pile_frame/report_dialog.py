"""Диалог перед выводом расчётной записки: объект и исполнитель для титула."""

from __future__ import annotations

import datetime

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QWidget

from pile_frame.report import ReportMeta

DEFAULT_OBJECT = "Заготовочное производство"


class ReportDialog(QDialog):
    """Поля титула: объект из проекта, исполнитель запоминается между запусками."""

    def __init__(
        self, parent: QWidget | None, settings: QSettings, object_name: str = DEFAULT_OBJECT
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Расчётная записка")
        self.object_name = QLineEdit(object_name)
        self.author = QLineEdit(str(settings.value("report/author", "")))
        self.author.setPlaceholderText("Фамилия И. О.")
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form = QFormLayout(self)
        form.addRow("Объект", self.object_name)
        form.addRow("Исполнитель", self.author)
        form.addRow(buttons)

    def meta(self) -> ReportMeta:
        return ReportMeta(
            object_name=self.object_name.text().strip() or DEFAULT_OBJECT,
            author=self.author.text().strip() or "—",
            date=datetime.date.today(),
        )

    @staticmethod
    def ask(parent: QWidget | None, settings: QSettings, object_name: str) -> ReportMeta | None:
        """Показать диалог; ``None`` — пользователь отказался.

        Объект хранится в проекте, исполнитель — в настройках программы.
        """
        dialog = ReportDialog(parent, settings, object_name)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        settings.setValue("report/author", dialog.author.text().strip())
        return dialog.meta()
