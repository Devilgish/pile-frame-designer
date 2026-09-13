"""Темы оформления и проверка контраста цветов по WCAG 2.2."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    """Токены цвета. Компоненты берут цвета только отсюда, без «сырых» hex в коде."""

    name: str
    # Интерфейс
    background: str
    surface: str
    surface_alt: str
    border: str
    text: str
    text_muted: str
    primary: str
    on_primary: str
    focus: str
    # Статусы проверок (цвет текста и иконки)
    ok: str
    warning: str
    fail: str
    # План
    plan_background: str
    grid_minor: str
    grid_major: str
    member_perimeter: str
    member_internal: str
    pile: str
    sheet_fill: str
    sheet_cut: str
    outline: str


LIGHT = Theme(
    name="light",
    background="#F8FAFC",
    surface="#FFFFFF",
    surface_alt="#F1F5F9",
    border="#E2E8F0",
    text="#0F172A",
    text_muted="#475569",
    primary="#1E3A5F",
    on_primary="#FFFFFF",
    focus="#2563EB",
    ok="#047857",
    warning="#B45309",
    fail="#B91C1C",
    plan_background="#FFFFFF",
    grid_minor="#EEF2F6",
    grid_major="#D5DCE5",
    member_perimeter="#1E3A5F",
    member_internal="#475569",
    pile="#C2410C",
    sheet_fill="#E6EDF6",
    sheet_cut="#94A3B8",
    outline="#2563EB",
)

DARK = Theme(
    name="dark",
    background="#0F172A",
    surface="#1E293B",
    surface_alt="#273449",
    border="#334155",
    text="#F1F5F9",
    text_muted="#94A3B8",
    primary="#93C5FD",
    on_primary="#0F172A",
    focus="#60A5FA",
    ok="#34D399",
    warning="#FBBF24",
    fail="#F87171",
    plan_background="#111827",
    grid_minor="#1F2937",
    grid_major="#374151",
    member_perimeter="#CBD5E1",
    member_internal="#94A3B8",
    pile="#FB923C",
    sheet_fill="#1B2940",
    sheet_cut="#52627A",
    outline="#60A5FA",
)


def _relative_luminance(hex_color: str) -> float:
    """Относительная яркость цвета sRGB по WCAG 2.2."""
    value = hex_color.lstrip("#")
    channels = [int(value[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    r, g, b = linear
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(foreground: str, background: str) -> float:
    """Коэффициент контраста двух цветов, от 1 до 21."""
    lighter, darker = sorted(
        (_relative_luminance(foreground), _relative_luminance(background)), reverse=True
    )
    return (lighter + 0.05) / (darker + 0.05)
