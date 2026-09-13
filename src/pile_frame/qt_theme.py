"""Применение темы к Qt: палитра, таблица стилей и иконки статусов."""

from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPalette, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QWidget

from pile_frame.status import Status
from pile_frame.theme import DARK, LIGHT, Theme

THEME_MODES = ("system", "light", "dark")
BASE_FONT = "Segoe UI"
BASE_POINT_SIZE = 10


def resolve_theme(mode: str) -> Theme:
    """Тема для режима «system» / «light» / «dark»."""
    if mode == "light":
        return LIGHT
    if mode == "dark":
        return DARK
    hints = QGuiApplication.styleHints()
    return DARK if hints.colorScheme() == Qt.ColorScheme.Dark else LIGHT


def build_palette(theme: Theme) -> QPalette:
    palette = QPalette()
    c = QColor
    palette.setColor(QPalette.ColorRole.Window, c(theme.background))
    palette.setColor(QPalette.ColorRole.WindowText, c(theme.text))
    palette.setColor(QPalette.ColorRole.Base, c(theme.surface))
    palette.setColor(QPalette.ColorRole.AlternateBase, c(theme.surface_alt))
    palette.setColor(QPalette.ColorRole.Text, c(theme.text))
    palette.setColor(QPalette.ColorRole.PlaceholderText, c(theme.text_muted))
    palette.setColor(QPalette.ColorRole.Button, c(theme.surface))
    palette.setColor(QPalette.ColorRole.ButtonText, c(theme.text))
    palette.setColor(QPalette.ColorRole.Highlight, c(theme.focus))
    palette.setColor(QPalette.ColorRole.HighlightedText, c(theme.surface))
    palette.setColor(QPalette.ColorRole.ToolTipBase, c(theme.surface))
    palette.setColor(QPalette.ColorRole.ToolTipText, c(theme.text))
    return palette


_ICON_DIR = Path(tempfile.gettempdir()) / "pile-frame-designer-icons"


def _chevron(theme: Theme, direction: str) -> str:
    """SVG-стрелка для полей ввода в цвете темы; возвращает путь для таблицы стилей."""
    points = "2,7 5,4 8,7" if direction == "up" else "2,3 5,6 8,3"
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 10 10">'
        f'<polyline points="{points}" fill="none" stroke="{theme.text_muted}" '
        'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>'
    )
    _ICON_DIR.mkdir(parents=True, exist_ok=True)
    path = _ICON_DIR / f"chevron-{direction}-{theme.name}.svg"
    path.write_text(svg, encoding="utf-8")
    return path.as_posix()


def build_stylesheet(theme: Theme) -> str:
    t = theme
    up, down = _chevron(theme, "up"), _chevron(theme, "down")
    return f"""
    QMainWindow, QWidget#panel {{ background: {t.background}; }}
    QWidget#panel QLabel {{ color: {t.text}; }}
    QLabel[role="section"] {{
        color: {t.text_muted}; font-size: 8pt; font-weight: 600;
        letter-spacing: 0.5px; padding-top: 12px;
    }}
    QLabel[role="muted"] {{ color: {t.text_muted}; }}
    QFrame#card {{
        background: {t.surface}; border: 1px solid {t.border}; border-radius: 6px;
    }}
    QAbstractSpinBox {{
        background: {t.surface}; color: {t.text}; border: 1px solid {t.border};
        border-radius: 4px; padding: 4px 26px 4px 6px; min-height: 22px;
    }}
    QAbstractSpinBox:focus {{ border: 2px solid {t.focus}; padding: 3px 25px 3px 5px; }}
    QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{
        subcontrol-origin: border; width: 20px; border: none;
        border-left: 1px solid {t.border}; background: {t.surface_alt};
    }}
    QAbstractSpinBox::up-button {{
        subcontrol-position: top right; border-top-right-radius: 4px;
    }}
    QAbstractSpinBox::down-button {{
        subcontrol-position: bottom right; border-bottom-right-radius: 4px;
    }}
    QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover {{
        background: {t.border};
    }}
    QAbstractSpinBox::up-arrow {{ image: url({up}); width: 10px; height: 10px; }}
    QAbstractSpinBox::down-arrow {{ image: url({down}); width: 10px; height: 10px; }}
    QGraphicsView {{
        border: 1px solid {t.border}; border-radius: 6px; background: {t.plan_background};
    }}
    QMenuBar {{
        background: {t.surface}; color: {t.text}; border-bottom: 1px solid {t.border};
    }}
    QMenuBar::item:selected, QMenu::item:selected {{
        background: {t.surface_alt}; color: {t.text};
    }}
    QMenu {{ background: {t.surface}; color: {t.text}; border: 1px solid {t.border}; }}
    QStatusBar {{
        background: {t.surface}; color: {t.text_muted}; border-top: 1px solid {t.border};
    }}
    """


def apply_theme(window: QWidget, theme: Theme) -> None:
    """Применить тему к приложению и окну."""
    app = QApplication.instance()
    palette = build_palette(theme)
    if isinstance(app, QApplication):
        app.setStyle("Fusion")
        app.setPalette(palette)
        font = QFont(BASE_FONT, BASE_POINT_SIZE)
        app.setFont(font)
    window.setPalette(palette)
    window.setStyleSheet(build_stylesheet(theme))


def status_icon(status: Status, theme: Theme, size: int = 20, dpr: float = 2.0) -> QPixmap:
    """Иконка статуса: круг цвета статуса со знаком ✓ / ! / ✕."""
    pixmap = QPixmap(int(size * dpr), int(size * dpr))
    pixmap.setDevicePixelRatio(dpr)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(getattr(theme, status.color_token)))
    painter.drawEllipse(QRectF(0, 0, size, size))
    pen = QPen(QColor(theme.surface), size * 0.12)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    s = size
    if status.icon == "check":
        painter.drawPolyline(
            [QPointF(s * 0.28, s * 0.52), QPointF(s * 0.44, s * 0.68), QPointF(s * 0.72, s * 0.36)]
        )
    elif status.icon == "alert":
        painter.drawLine(QPointF(s * 0.5, s * 0.27), QPointF(s * 0.5, s * 0.56))
        painter.drawPoint(QPointF(s * 0.5, s * 0.73))
    else:
        painter.drawLine(QPointF(s * 0.33, s * 0.33), QPointF(s * 0.67, s * 0.67))
        painter.drawLine(QPointF(s * 0.67, s * 0.33), QPointF(s * 0.33, s * 0.67))
    painter.end()
    return pixmap
