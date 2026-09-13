"""Редактор плана: действия со сваями и контуром, отмена и повтор."""

from pile_frame.contour import Contour
from pile_frame.editor import PlanEditor

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
