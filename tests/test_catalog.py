"""Справочники: профили ГОСТ 30245-2003, стали СП 16.13330.2017, плиты ГОСТ 26816-2016."""

import pytest

from pile_frame.boards import BoardSpec, validate_board
from pile_frame.materials import STEELS
from pile_frame.sections import GOST_SECTIONS, ProfileCatalog, validate_section


@pytest.mark.parametrize(
    ("name", "mass_kg_m", "area_cm2", "ix_cm4", "wx_cm3"),
    [
        ("120×120×5", 17.55, 22.36, 485.3, 80.88),
        ("120×60×4", 10.48, 13.35, 240.7, 40.12),
        ("40×40×3", 3.30, 4.21, 9.31, 4.65),
    ],
)
def test_gost_30245_profiles_are_in_the_catalog(name, mass_kg_m, area_cm2, ix_cm4, wx_cm3):
    section = {s.name: s for s in GOST_SECTIONS}[name]

    assert (section.mass_kg_m, section.area_cm2, section.ix_cm4, section.wx_cm3) == (
        mass_kg_m,
        area_cm2,
        ix_cm4,
        wx_cm3,
    )


@pytest.mark.parametrize(
    ("steel", "thickness_mm", "ry_mpa"),
    [
        ("С245", 5.0, 240),  # от 2,0 до 20 включ.
        ("С255", 3.9, 250),  # от 2,0 до 3,9 включ.
        ("С255", 4.0, 240),  # от 4,0 до 10 включ.
        ("С255", 12.0, 240),  # св. 10 до 20 включ.
        ("С355", 4.0, 350),  # от 2,0 до 16 включ.
        ("С235", 3.0, 230),  # от 2,0 до 4,0 включ.
    ],
)
def test_design_resistance_follows_sp16_table_b3_by_thickness(steel, thickness_mm, ry_mpa):
    assert STEELS[steel].ry_mpa(thickness_mm) == ry_mpa


def test_steel_outside_its_thickness_range_is_rejected_with_reason():
    # С235 в таблице В.3 приведена только до 4,0 мм.
    with pytest.raises(ValueError, match="С235.*5"):
        STEELS["С235"].ry_mpa(5.0)


VALID_PROFILE = {
    "name": "100×100×4",
    "height_mm": 100,
    "width_mm": 100,
    "thickness_mm": 4,
    "mass_kg_m": 11.73,
    "area_cm2": 14.95,
    "ix_cm4": 226.0,
    "wx_cm3": 45.2,
}


def test_valid_custom_profile_has_no_issues():
    assert validate_section(**VALID_PROFILE) == []


@pytest.mark.parametrize(
    ("changes", "field", "text"),
    [
        ({"height_mm": 0}, "height_mm", "больше нуля"),
        ({"wx_cm3": -5}, "wx_cm3", "больше нуля"),
        ({"name": "  "}, "name", "название"),
        # Стенка должна быть тоньше половины меньшей стороны: 60 / 2 = 30 мм.
        ({"width_mm": 60, "thickness_mm": 30}, "thickness_mm", "меньше половины"),
    ],
)
def test_invalid_custom_profile_reports_error_on_the_field(changes, field, text):
    issues = validate_section(**{**VALID_PROFILE, **changes})

    assert [(i.field, i.severity) for i in issues] == [(field, "error")]
    assert text in issues[0].message


def test_default_board_follows_gost_26816_without_issues():
    board = BoardSpec()

    assert (board.length_mm, board.width_mm, board.thickness_mm, board.density_kg_m3) == (
        3200,
        1250,
        24,
        1300,
    )
    assert validate_board(board) == []


@pytest.mark.parametrize(
    ("changes", "field", "severity"),
    [
        ({"thickness_mm": 0}, "thickness_mm", "error"),
        ({"density_kg_m3": -1}, "density_kg_m3", "error"),
        ({"density_kg_m3": 1500}, "density_kg_m3", "warning"),  # ГОСТ: 1100–1400
        ({"length_mm": 2700}, "length_mm", "warning"),  # ГОСТ: 3200 или 3600
        ({"width_mm": 1220}, "width_mm", "warning"),  # ГОСТ: 1200 или 1250
        ({"thickness_mm": 25}, "thickness_mm", "warning"),  # градация с шагом 2 мм
    ],
)
def test_board_issues_separate_errors_from_non_gost_warnings(changes, field, severity):
    issues = validate_board(BoardSpec(**changes))

    assert [(i.field, i.severity) for i in issues] == [(field, severity)]
    if severity == "warning":
        assert "ГОСТ 26816" in issues[0].message


def test_catalog_keeps_gost_profiles_and_round_trips_custom_ones_through_json():
    catalog = ProfileCatalog()
    assert catalog.add(**VALID_PROFILE) == []

    restored = ProfileCatalog.from_json(catalog.to_json())

    assert [s.name for s in restored.sections] == ["120×120×5", "120×60×4", "40×40×3", "100×100×4"]
    assert restored.get("100×100×4").wx_cm3 == 45.2


def test_catalog_rejects_duplicate_name_and_protects_gost_profiles():
    catalog = ProfileCatalog()

    issues = catalog.add(**{**VALID_PROFILE, "name": "120×60×4"})

    assert [(i.field, i.severity) for i in issues] == [("name", "error")]
    with pytest.raises(ValueError, match="ГОСТ"):
        catalog.remove("120×60×4")
