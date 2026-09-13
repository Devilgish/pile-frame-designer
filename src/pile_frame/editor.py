"""Редактор плана: контур и сваи с историей отмены и повтора (без привязки к Qt)."""

from __future__ import annotations

from dataclasses import dataclass, replace

from pile_frame.contour import Contour, Point
from pile_frame.design import auto_piles


@dataclass(frozen=True)
class PlanState:
    """Снимок плана. Неизменяемый, поэтому история хранит снимки целиком."""

    contour: Contour | None = None
    piles: tuple[Point, ...] = ()


class PlanEditor:
    """Действия пользователя над планом. Каждое действие можно отменить и повторить."""

    def __init__(self, pile_step_mm: float) -> None:
        self.pile_step_mm = pile_step_mm
        self._undo: list[PlanState] = []
        self._redo: list[PlanState] = []
        self._state = PlanState()

    @property
    def contour(self) -> Contour | None:
        return self._state.contour

    @property
    def piles(self) -> tuple[Point, ...]:
        return self._state.piles

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def _commit(self, state: PlanState) -> None:
        if state == self._state:
            return
        self._undo.append(self._state)
        self._redo.clear()
        self._state = state

    def set_contour(self, contour: Contour) -> None:
        """Задать контур и расставить сваи автоматически."""
        piles = tuple(auto_piles(contour, self.pile_step_mm))
        self._commit(PlanState(contour, piles))

    def set_pile_step(self, step_mm: float) -> None:
        """Изменить шаг и заново расставить сваи в текущем контуре."""
        self.pile_step_mm = step_mm
        if self.contour is not None:
            self.set_contour(self.contour)

    def add_pile(self, point: Point) -> None:
        if point in self.piles:
            return
        self._commit(replace(self._state, piles=(*self.piles, point)))

    def move_pile(self, old: Point, new: Point) -> None:
        if old not in self.piles or new in self.piles:
            return
        piles = tuple(new if p == old else p for p in self.piles)
        self._commit(replace(self._state, piles=piles))

    def delete_pile(self, point: Point) -> None:
        if point not in self.piles:
            return
        self._commit(replace(self._state, piles=tuple(p for p in self.piles if p != point)))

    def undo(self) -> None:
        if self._undo:
            self._redo.append(self._state)
            self._state = self._undo.pop()

    def redo(self) -> None:
        if self._redo:
            self._undo.append(self._state)
            self._state = self._redo.pop()
