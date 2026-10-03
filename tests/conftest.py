import os

import pytest
from PySide6.QtCore import QSettings

# Окно в тестах не показывается на экране и работает в CI без дисплея.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path):
    """Настройки приложения пишутся во временную папку, а не в профиль пользователя."""
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    yield


@pytest.fixture(autouse=True)
def no_modal_dialogs(monkeypatch):
    """Модальные сообщения в тестах не показываются: отвечать на них некому.

    При закрытии окна с несохранёнными правками по умолчанию выбирается «Не сохранять».
    Тесты, которым важен ответ или текст сообщения, подменяют эти функции сами.
    """
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Discard
    )
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
