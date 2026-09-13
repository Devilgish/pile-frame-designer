import os

# Окно в тестах не показывается на экране и работает в CI без дисплея.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
