"""Зоны помещений с пресетами временной нагрузки.

Зона — прямоугольник на плане внутри контура. Пресеты взяты из норм по аналогии: нагрузки на
производственные и складские помещения по СП 20.13330.2016 (таблица 8.3, примечание 4)
задаются технологом, поэтому каждый пресет помечен «уточнить у технолога».
"""

from __future__ import annotations

from dataclasses import dataclass

from shapely.geometry import box

from pile_frame.contour import Contour

Rect = tuple[float, float, float, float]  # x0, y0, x1, y1, мм
AREA_TOLERANCE_MM2 = 1.0

_CHECK = "принято по аналогии, уточнить у технолога"


@dataclass(frozen=True)
class Preset:
    title: str
    load_kpa: float
    source: str


PRESETS = {
    "prep": Preset(
        "Заготовочный цех",
        2.0,
        f"СП 20.13330.2016, табл. 8.3, п. 3 «кухни общественных зданий»; {_CHECK}",
    ),
    "pastry": Preset(
        "Кондитерский цех",
        2.0,
        f"СП 20.13330.2016, табл. 8.3, п. 3 «кухни общественных зданий»; {_CHECK}",
    ),
    "aisle": Preset(
        "Проход",
        3.0,
        f"СП 20.13330.2016, табл. 8.3, п. 12а «коридоры при помещениях п. 3»; {_CHECK}",
    ),
    "storage": Preset(
        "Склад", 5.0, f"СНиП 2.01.07-85, табл. 3, п. 5 «книгохранилища, архивы»; {_CHECK}"
    ),
    "cold": Preset(
        "Холодильная камера",
        5.0,
        f"как склад: СНиП 2.01.07-85, табл. 3, п. 5 «книгохранилища, архивы»; {_CHECK}",
    ),
}


class ZoneError(ValueError):
    """Зону нельзя поставить; текст объясняет причину пользователю."""


@dataclass(frozen=True)
class Zone:
    kind: str
    rect: Rect
    live_load_kpa: float
    #: Только для холодильной камеры: стоит прямо на ЦСП, а не на своём сборном полу.
    cold_on_board: bool = False

    @property
    def title(self) -> str:
        return PRESETS[self.kind].title


def place_zone(contour: Contour, zones: list[Zone], rect: Rect, kind: str) -> Zone:
    """Новая зона по протянутому прямоугольнику: обрезана по контуру, без наложений."""
    piece = contour.polygon.intersection(box(*rect))  # box сам упорядочивает углы
    if piece.area <= AREA_TOLERANCE_MM2:
        raise ZoneError("Зона вне контура: протяните прямоугольник внутри плана.")
    bx0, by0, bx1, by1 = piece.bounds
    if abs(piece.area - (bx1 - bx0) * (by1 - by0)) > AREA_TOLERANCE_MM2:
        raise ZoneError("Внутри контура зона должна остаться прямоугольной: не заходите за угол.")
    for other in zones:
        if box(*other.rect).intersection(box(bx0, by0, bx1, by1)).area > AREA_TOLERANCE_MM2:
            raise ZoneError(f"Зона пересекается с зоной «{other.title}».")
    return Zone(kind, (bx0, by0, bx1, by1), PRESETS[kind].load_kpa)


COLD_ON_BOARD_REMARK = (
    "Холодильная камера стоит прямо на ЦСП: возможны промерзание пола и конденсат под камерой. "
    "Нужны утеплённый пол камеры с пароизоляцией и проветриваемое подполье — уточнить у "
    "поставщика камеры."
)


def zone_remarks(zones: tuple[Zone, ...]) -> list[str]:
    """Замечания по зонам, которые расчёт каркаса не проверяет."""
    if any(z.kind == "cold" and z.cold_on_board for z in zones):
        return [COLD_ON_BOARD_REMARK]
    return []
