"""Редактор плана: действия со сваями и контуром, отмена и повтор."""

import pytest

from pile_frame.contour import Contour
from pile_frame.editor import PlanEditor
from pile_frame.equipment import EquipmentError, EquipmentType
from pile_frame.zones import Zone, ZoneError

SQUARE = Contour.from_points([(0, 0), (4000, 0), (4000, 4000), (0, 4000)])
AUTO = {(x, y) for x in (0, 2000, 4000) for y in (0, 2000, 4000)}  # шаг 2000 → 3 × 3


def test_undo_and_redo_restore_exact_states_after_pile_edits():
    editor = PlanEditor(pile_step_mm=2000)
    editor.set_contour(SQUARE)
    assert set(editor.piles) == AUTO

    editor.add_pile((1000, 1000))
    editor.move_pile((1000, 1000), (1000, 3000))
    editor.delete_pile((2000, 2000))
    final = set(editor.piles)

    for _ in range(3):
        editor.undo()
    assert set(editor.piles) == AUTO

    for _ in range(3):
        editor.redo()
    assert set(editor.piles) == final
    assert not editor.can_redo


def test_new_action_after_undo_discards_redo_branch():
    editor = PlanEditor(pile_step_mm=2000)
    editor.set_contour(SQUARE)
    editor.add_pile((1000, 1000))
    editor.undo()

    editor.delete_pile((0, 0))

    assert not editor.can_redo
    assert (1000, 1000) not in editor.piles


def test_first_undo_returns_to_empty_plan():
    editor = PlanEditor(pile_step_mm=2000)
    editor.set_contour(SQUARE)

    editor.undo()

    assert editor.contour is None
    assert editor.piles == ()
    assert not editor.can_undo


def test_zones_are_drawn_edited_and_undone_like_other_plan_actions():
    editor = PlanEditor(pile_step_mm=2000)
    editor.set_contour(SQUARE)

    editor.add_zone((0, 0, 2000, 4000), "prep")
    editor.set_zone_kind(0, "storage")  # смена назначения — пресет нагрузки
    assert (editor.zones[0].kind, editor.zones[0].live_load_kpa) == ("storage", 5.0)
    editor.set_zone_load(0, 7.5)  # своя нагрузка, назначение то же
    editor.set_zone_cold_on_board(0, True)
    assert editor.zones[0] == Zone("storage", (0, 0, 2000, 4000), 7.5, cold_on_board=True)

    editor.remove_zone(0)
    assert editor.zones == ()
    for _ in range(4):
        editor.undo()
    assert editor.zones[0] == Zone("prep", (0, 0, 2000, 4000), 2.0)


def test_zone_that_cannot_be_placed_leaves_the_plan_unchanged():
    editor = PlanEditor(pile_step_mm=2000)
    editor.set_contour(SQUARE)
    editor.add_zone((0, 0, 2000, 2000), "prep")

    with pytest.raises(ZoneError):
        editor.add_zone((1000, 1000, 3000, 3000), "storage")
    assert len(editor.zones) == 1
    editor.undo()
    assert editor.zones == ()


def test_smaller_contour_keeps_zones_that_still_fit_and_trims_the_rest():
    # Новый контур 4000 × 2000: зона снизу остаётся, зона сверху исчезает,
    # зона через границу обрезается.
    editor = PlanEditor(pile_step_mm=2000)
    editor.set_contour(SQUARE)
    editor.add_zone((0, 0, 1000, 1000), "prep")
    editor.add_zone((0, 3000, 1000, 4000), "storage")
    editor.add_zone((2000, 1000, 4000, 3000), "aisle")

    editor.set_contour(Contour.from_points([(0, 0), (4000, 0), (4000, 2000), (0, 2000)]))

    assert [z.rect for z in editor.zones] == [(0, 0, 1000, 1000), (2000, 1000, 4000, 2000)]


MIXER = EquipmentType("Тестомес спиральный 60 л", 800, 450, own_kg=200, content_kg=50)


def test_equipment_is_placed_moved_turned_and_removed_with_undo():
    editor = PlanEditor(pile_step_mm=2000)
    editor.set_contour(SQUARE)

    editor.add_equipment(MIXER, (1000, 1000))
    editor.move_equipment(0, (3000, 3000))
    editor.rotate_equipment(0)
    assert editor.equipment[0].rect == (2775.0, 2600.0, 3225.0, 3400.0)

    editor.remove_equipment(0)
    assert editor.equipment == ()
    editor.undo()  # удаление
    editor.undo()  # поворот
    assert editor.equipment[0].centre == (3000.0, 3000.0) and not editor.equipment[0].rotated


def test_equipment_that_does_not_fit_leaves_the_plan_unchanged():
    editor = PlanEditor(pile_step_mm=2000)
    editor.set_contour(SQUARE)
    editor.add_equipment(MIXER, (1000, 1000))

    with pytest.raises(EquipmentError):
        editor.move_equipment(0, (3900, 1000))
    with pytest.raises(EquipmentError):
        editor.add_equipment(MIXER, (-500, 1000))
    assert editor.equipment[0].centre == (1000.0, 1000.0)
    assert len(editor.equipment) == 1


def test_smaller_contour_drops_equipment_left_outside():
    editor = PlanEditor(pile_step_mm=2000)
    editor.set_contour(SQUARE)
    editor.add_equipment(MIXER, (1000, 1000))
    editor.add_equipment(MIXER, (1000, 3000))

    editor.set_contour(Contour.from_points([(0, 0), (4000, 0), (4000, 2000), (0, 2000)]))

    assert [e.centre for e in editor.equipment] == [(1000.0, 1000.0)]
