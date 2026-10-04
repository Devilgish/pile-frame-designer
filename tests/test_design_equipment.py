"""Оборудование в расчёте: вес по пятну на балки, равновесие, лист под оборудованием."""

import pytest

from pile_frame.contour import Contour
from pile_frame.design import Project, analyze
from pile_frame.equipment import EquipmentType, place_equipment

RECT = Contour.from_points([(0, 0), (6000, 0), (6000, 4000), (0, 4000)])
MIXER = EquipmentType("Тестомес спиральный 60 л", 800, 450, own_kg=200, content_kg=50)
FRIDGE = EquipmentType("Шкаф холодильный 1400 л", 1400, 850, own_kg=200, content_kg=300)


def _grid(*equipment, **changes):
    params = {
        "contour": RECT,
        "pile_step_mm": 2000,
        "live_load_kpa": 1.5,
        "sheet_joints": False,
        "equipment": tuple(equipment),
    }
    return analyze(Project(**{**params, **changes}))


@pytest.mark.parametrize(
    "centre", [(1000, 1000), (2000, 1000)], ids=["посреди ячейки", "над балкой x = 2000"]
)
def test_reactions_grow_by_exactly_the_design_weight_of_the_equipment(centre):
    # (1,05·200 + 1,2·50)·9,81 = 2,6487 кН — где бы ни стоял тестомес, сваи берут его целиком.
    plain = sum(_grid().reactions_kn.values())
    design = _grid(place_equipment(RECT, MIXER, centre))

    assert sum(design.reactions_kn.values()) - plain == pytest.approx(2.6487, abs=1e-3)
    assert design.equipment_load_kn == pytest.approx(2.6487, abs=1e-4)


def test_equipment_raises_forces_only_around_itself():
    def moments(design):
        return {
            frozenset((m.start, m.end)): c.max_moment_knm
            for m, c in zip(design.members, design.checks, strict=True)
        }

    plain = moments(_grid())
    loaded = moments(_grid(place_equipment(RECT, FRIDGE, (1000, 600))))

    near = frozenset(((0.0, 0.0), (2000.0, 0.0)))
    far = frozenset(((4000.0, 4000.0), (6000.0, 4000.0)))
    assert loaded[near] > 1.2 * plain[near]
    assert loaded[far] == pytest.approx(plain[far], rel=0.03)


def test_board_under_heavy_equipment_counts_its_pressure():
    # 6400 × 2500, листы 3200 × 1250, 4 кПа: без оборудования по 4 перемычки на ячейку.
    # Стеллаж 600 кг продуктов на 1200 × 500: (20 + 600)·9,81/0,6 м² = 10,1 кПа сверх 4 кПа —
    # в его ячейке перемычек больше, в остальных столько же.
    rack = EquipmentType("Стеллаж 4 полки 1200×500", 1200, 500, own_kg=20, content_kg=600)
    contour = Contour.from_points([(0, 0), (6400, 0), (6400, 2500), (0, 2500)])
    design = analyze(
        Project(
            contour=contour,
            pile_step_mm=3200,
            live_load_kpa=4.0,
            equipment=(place_equipment(contour, rack, (1600, 600)),),
        )
    )

    by_cell = {
        round(c.bounds[0]) // 3200 * 10 + round(c.bounds[1]) // 1250: c for c in design.board_cells
    }
    under = by_cell[0]  # ячейка 0…3200 × 0…1251,5
    others = [c for key, c in by_cell.items() if key != 0]
    assert under.jumpers > 4
    assert all(c.jumpers == 4 for c in others)
    assert under.check.passed


def test_equipment_weight_counts_fully_in_the_deflection():
    # Вес стационарного оборудования — длительная нагрузка: в прогиб идёт целиком.
    def deflection(design):
        key = frozenset(((0.0, 0.0), (2000.0, 0.0)))
        return next(
            c.deflection_mm
            for m, c in zip(design.members, design.checks, strict=True)
            if frozenset((m.start, m.end)) == key
        )

    assert deflection(_grid(place_equipment(RECT, FRIDGE, (1000, 600)))) > 1.2 * deflection(_grid())
