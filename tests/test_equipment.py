"""Оборудование: библиотека, вес с коэффициентами по СП 20, установка на плане."""

import pytest

from pile_frame.contour import Contour
from pile_frame.equipment import (
    CATALOG,
    EquipmentError,
    EquipmentLibrary,
    EquipmentType,
    place_equipment,
    turned,
)

RECT = Contour.from_points([(0, 0), (6000, 0), (6000, 4000), (0, 4000)])
MIXER = EquipmentType("Тестомес спиральный 60 л", 800, 450, own_kg=200, content_kg=50)


def test_catalog_has_typical_kitchen_items_marked_to_check_by_passport():
    names = [item.name for item in CATALOG]

    assert len(names) >= 8 and len(set(names)) == len(names)
    assert any("Пароконвектомат" in n for n in names)
    assert any("Стеллаж" in n for n in names)
    for item in CATALOG:
        assert item.length_mm > 0 and item.width_mm > 0 and item.own_kg > 0
        assert "паспорт" in item.note


def test_design_weight_uses_factors_for_stationary_equipment_and_its_contents():
    # СП 20.13330.2016, табл. 8.2: стационарное оборудование 1,05; загрузка — как складируемые
    # материалы 1,2. (1,05·200 + 1,2·50)·9,81 = 2648,7 Н; нормативный (200 + 50)·9,81 = 2452,5 Н.
    assert MIXER.design_weight_kn == pytest.approx(2.6487, abs=1e-4)
    assert MIXER.normative_weight_kn == pytest.approx(2.4525, abs=1e-4)


def test_equipment_footprint_follows_its_centre_and_quarter_turns():
    placed = place_equipment(RECT, MIXER, (1000, 1000))
    turned = place_equipment(RECT, MIXER, (1000, 1000), rotated=True)

    assert placed.rect == (600, 775, 1400, 1225)  # длина 800 вдоль X
    assert turned.rect == (775, 600, 1225, 1400)  # повёрнут на 90°


@pytest.mark.parametrize(
    "centre", [(200, 1000), (7000, 1000), (3000, 3900)], ids=["за левым краем", "вне", "у края"]
)
def test_equipment_must_stand_entirely_inside_the_contour(centre):
    with pytest.raises(EquipmentError, match="внутри контура"):
        place_equipment(RECT, MIXER, centre)


def test_own_equipment_is_validated_and_kept_in_the_library():
    library = EquipmentLibrary()

    issues = library.add(name="", length_mm=0, width_mm=500, own_kg=-1, content_kg=0)
    assert {i.field for i in issues} == {"name", "length_mm", "own_kg"}
    assert library.add(name="Печь подовая", length_mm=1200, width_mm=1000, own_kg=400) == []
    assert library.add(name="Печь подовая", length_mm=1, width_mm=1, own_kg=1)[0].field == "name"

    restored = EquipmentLibrary.from_json(library.to_json())
    assert restored.get("Печь подовая").own_kg == 400
    assert restored.get("Стеллаж 4 полки 1200×500").content_kg > 0  # типовые всегда есть


def test_quarter_turn_is_refused_when_the_item_would_leave_the_contour():
    # Тестораскатка 2000 × 800 у нижней стены: развёрнутая, она вылезла бы на 600 мм.
    sheeter = EquipmentType("Тестораскаточная машина", 2000, 800, own_kg=220)
    item = place_equipment(RECT, sheeter, (3000, 400))

    with pytest.raises(EquipmentError):
        turned(RECT, item)
    assert turned(RECT, place_equipment(RECT, sheeter, (3000, 2000))).rect == (
        2600,
        1000,
        3400,
        3000,
    )
