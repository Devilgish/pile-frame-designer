"""Редактор плана: контур и сваи с историей отмены и повтора (без привязки к Qt)."""

from __future__ import annotations

from dataclasses import dataclass, replace

from pile_frame.contour import Contour, Point
from pile_frame.design import auto_piles
from pile_frame.zones import PRESETS, Rect, Zone, ZoneError, place_zone


@dataclass(frozen=True)
class PlanState:
    """Снимок плана. Неизменяемый, поэтому история хранит снимки целиком."""

    contour: Contour | None = None
    piles: tuple[Point, ...] = ()
    zones: tuple[Zone, ...] = ()


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
    def zones(self) -> tuple[Zone, ...]:
        return self._state.zones

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

    def load(
        self, contour: Contour | None, piles: tuple[Point, ...], zones: tuple[Zone, ...] = ()
    ) -> None:
        """Открыть план целиком (из файла или пустой): история отмены начинается заново."""
        self._undo.clear()
        self._redo.clear()
        self._state = PlanState(contour, tuple(piles), tuple(zones))

    def set_contour(self, contour: Contour) -> None:
        """Задать контур и расставить сваи автоматически; зоны обрезаются по новому контуру."""
        piles = tuple(auto_piles(contour, self.pile_step_mm))
        self._commit(PlanState(contour, piles, _fit_zones(contour, self.zones)))

    def add_zone(self, rect: Rect, kind: str) -> None:
        """Нарисовать зону. ``ZoneError`` — зону поставить нельзя, план не меняется."""
        if self.contour is None:
            raise ZoneError("Сначала нарисуйте контур плана.")
        zone = place_zone(self.contour, list(self.zones), rect, kind)
        self._commit(replace(self._state, zones=(*self.zones, zone)))

    def _change_zone(self, index: int, **changes) -> None:
        zones = list(self.zones)
        zones[index] = replace(zones[index], **changes)
        self._commit(replace(self._state, zones=tuple(zones)))

    def set_zone_kind(self, index: int, kind: str) -> None:
        """Сменить назначение: нагрузка становится пресетом нового назначения."""
        self._change_zone(index, kind=kind, live_load_kpa=PRESETS[kind].load_kpa)

    def set_zone_load(self, index: int, load_kpa: float) -> None:
        self._change_zone(index, live_load_kpa=load_kpa)

    def set_zone_cold_on_board(self, index: int, on_board: bool) -> None:
        self._change_zone(index, cold_on_board=on_board)

    def remove_zone(self, index: int) -> None:
        zones = [z for i, z in enumerate(self.zones) if i != index]
        self._commit(replace(self._state, zones=tuple(zones)))

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


def _fit_zones(contour: Contour, zones: tuple[Zone, ...]) -> tuple[Zone, ...]:
    """Зоны, которые помещаются в новый контур (обрезанные); остальные отбрасываются."""
    fitted: list[Zone] = []
    for zone in zones:
        try:
            placed = place_zone(contour, fitted, zone.rect, zone.kind)
        except ZoneError:
            continue
        fitted.append(replace(zone, rect=placed.rect))
    return tuple(fitted)
