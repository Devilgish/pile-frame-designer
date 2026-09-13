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
