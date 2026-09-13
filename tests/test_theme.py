"""Темы оформления: контраст цветов по WCAG 2.2."""

import pytest

from pile_frame.theme import DARK, LIGHT, contrast_ratio


@pytest.mark.parametrize(
    ("foreground", "background", "ratio"),
    [
        ("#000000", "#FFFFFF", 21.0),  # максимальный контраст
        ("#FFFFFF", "#FFFFFF", 1.0),  # минимальный
        ("#767676", "#FFFFFF", 4.54),  # самый светлый серый, проходящий AA на белом
        ("#FFFFFF", "#767676", 4.54),  # порядок цветов не важен
    ],
)
def test_contrast_ratio_matches_wcag_reference_values(foreground, background, ratio):
    assert contrast_ratio(foreground, background) == pytest.approx(ratio, abs=0.01)


TEXT_PAIRS = [
    ("text", "background"),
    ("text", "surface"),
    ("text", "surface_alt"),
    ("text_muted", "background"),
    ("text_muted", "surface"),
    ("ok", "surface"),
    ("warning", "surface"),
    ("fail", "surface"),
    ("on_primary", "primary"),
]

# Нетекстовые элементы интерфейса и графика плана: WCAG 1.4.11, не ниже 3:1.
NON_TEXT_PAIRS = [
    ("focus", "surface"),
    ("focus", "background"),
    ("member_perimeter", "plan_background"),
    ("member_internal", "plan_background"),
    ("pile", "plan_background"),
    ("fail", "plan_background"),
    ("outline", "plan_background"),
]


@pytest.mark.parametrize("theme", [LIGHT, DARK], ids=lambda t: t.name)
@pytest.mark.parametrize(("foreground", "background"), TEXT_PAIRS)
def test_text_colors_meet_wcag_aa(theme, foreground, background):
    ratio = contrast_ratio(getattr(theme, foreground), getattr(theme, background))
    assert ratio >= 4.5, f"{theme.name}: {foreground} на {background} = {ratio:.2f}"


@pytest.mark.parametrize("theme", [LIGHT, DARK], ids=lambda t: t.name)
@pytest.mark.parametrize(("foreground", "background"), NON_TEXT_PAIRS)
def test_graphics_and_focus_colors_meet_non_text_contrast(theme, foreground, background):
    ratio = contrast_ratio(getattr(theme, foreground), getattr(theme, background))
    assert ratio >= 3.0, f"{theme.name}: {foreground} на {background} = {ratio:.2f}"
