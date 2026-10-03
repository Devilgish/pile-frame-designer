"""Зоны помещений: пресеты нагрузок с источниками, размещение на плане."""

import pytest

from pile_frame.contour import Contour
from pile_frame.zones import PRESETS, ZoneError, place_zone

RECT = Contour.from_points([(0, 0), (6000, 0), (6000, 4000), (0, 4000)])
L_SHAPE = Contour.from_points(
    [(0, 0), (6000, 0), (6000, 2000), (3000, 2000), (3000, 4000), (0, 4000)]
)


def test_presets_cite_a_source_and_ask_to_check_with_the_technologist():
    # СП 20.13330.2016, табл. 8.3: п. 3 «кухни общественных зданий» 2,0; п. 12а коридоры 3,0;
    # склад и камера — по аналогии с книгохранилищами, СНиП 2.01.07-85, табл. 3, п. 5: 5,0.
    loads = {kind: preset.load_kpa for kind, preset in PRESETS.items()}

    assert loads == {"prep": 2.0, "pastry": 2.0, "aisle": 3.0, "storage": 5.0, "cold": 5.0}
    for preset in PRESETS.values():
        assert "по аналогии" in preset.source and "технолог" in preset.source


def test_zone_drawn_inside_the_contour_gets_the_preset_load():
    zone = place_zone(RECT, [], (3000, 2500, 1000, 500), "pastry")  # протянута справа налево

    assert zone.rect == (1000, 500, 3000, 2500)
    assert zone.kind == "pastry"
    assert zone.live_load_kpa == 2.0


def test_zone_hanging_over_a_straight_edge_is_trimmed_to_the_contour():
    zone = place_zone(RECT, [], (5000, -500, 7000, 1000), "storage")

    assert zone.rect == (5000, 0, 6000, 1000)


@pytest.mark.parametrize(
    ("contour", "rect", "message"),
    [
        (RECT, (7000, 0, 8000, 1000), "вне контура"),
        (RECT, (1000, 1000, 1000, 2000), "вне контура"),  # нулевая ширина
        (L_SHAPE, (2000, 1000, 4000, 3000), "прямоугольн"),  # после обрезки — Г-образная
        (RECT, (2500, 2000, 4000, 3000), "пересекается"),
    ],
    ids=["вне контура", "нулевая ширина", "через внутренний угол", "наложение"],
)
def test_zone_that_cannot_be_placed_is_explained(contour, rect, message):
    existing = [place_zone(RECT, [], (1000, 500, 3000, 2500), "prep")]

    with pytest.raises(ZoneError, match=message):
        place_zone(contour, existing, rect, "storage")


def test_zones_may_touch_along_an_edge():
    first = place_zone(RECT, [], (0, 0, 3000, 4000), "prep")

    second = place_zone(RECT, [first], (3000, 0, 6000, 4000), "aisle")

    assert second.rect == (3000, 0, 6000, 4000)
