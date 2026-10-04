"""Оборудование на плане: библиотека позиций и установка.

Вес оборудования — собственная масса (стационарное оборудование, γf 1,05) и наибольшая
загрузка продуктами, тестом или водой (как складируемые материалы, γf 1,2), СП 20.13330.2016,
таблица 8.2. На каркас вес передаётся равномерно по габариту в плане (п. 8.1.1 допускает
эквивалентную равномерную нагрузку).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from shapely.geometry import box

from pile_frame.analysis import GRAVITY
from pile_frame.contour import Contour, Point
from pile_frame.issues import Issue

#: Коэффициенты надёжности по нагрузке (СП 20.13330.2016, таблица 8.2).
GAMMA_F_EQUIPMENT = 1.05
GAMMA_F_CONTENT = 1.2
PASSPORT = "типовое значение, уточнить по паспорту оборудования"


@dataclass(frozen=True)
class EquipmentType:
    """Позиция библиотеки: габарит в плане (длина вдоль X), мм; массы, кг."""

    name: str
    length_mm: float
    width_mm: float
    own_kg: float
    content_kg: float = 0.0
    note: str = ""

    @property
    def normative_weight_kn(self) -> float:
        return (self.own_kg + self.content_kg) * GRAVITY / 1e3

    @property
    def design_weight_kn(self) -> float:
        return (GAMMA_F_EQUIPMENT * self.own_kg + GAMMA_F_CONTENT * self.content_kg) * GRAVITY / 1e3


def _typical(name: str, length: float, width: float, own: float, content: float):
    return EquipmentType(name, length, width, own, content, PASSPORT)


#: Типовые позиции заготовочного производства: собственная масса и рабочая загрузка.
CATALOG = (
    _typical("Пароконвектомат 10 GN 1/1 на подставке", 900, 800, 150, 30),
    _typical("Печь конвекционная с расстойкой", 900, 900, 180, 20),
    _typical("Плита электрическая 4 конфорки", 800, 900, 130, 40),
    _typical("Тестомес спиральный 60 л", 800, 450, 200, 50),
    _typical("Миксер планетарный 40 л", 800, 600, 230, 30),
    _typical("Тестораскаточная машина", 2000, 800, 220, 10),
    _typical("Шкаф холодильный 1400 л", 1400, 850, 200, 300),
    _typical("Шкаф шоковой заморозки 10 GN", 800, 800, 150, 40),
    _typical("Стеллаж 4 полки 1200×500", 1200, 500, 20, 600),
    _typical("Стол производственный 1500×700", 1500, 700, 40, 100),
    _typical("Ванна моечная двухсекционная", 1200, 600, 40, 200),
)


class EquipmentError(ValueError):
    """Оборудование нельзя поставить; текст объясняет причину пользователю."""


@dataclass(frozen=True)
class Equipment:
    """Оборудование на плане: позиция, центр габарита, поворот на 90°."""

    type: EquipmentType
    centre: Point
    rotated: bool = False

    @property
    def rect(self) -> tuple[float, float, float, float]:
        length, width = self.type.length_mm, self.type.width_mm
        if self.rotated:
            length, width = width, length
        x, y = self.centre
        return (x - length / 2, y - width / 2, x + length / 2, y + width / 2)


AREA_TOLERANCE_MM2 = 1.0


def place_equipment(
    contour: Contour, kind: EquipmentType, centre: Point, *, rotated: bool = False
) -> Equipment:
    """Оборудование в точке; ``EquipmentError``, если габарит выходит за контур."""
    item = Equipment(kind, (float(centre[0]), float(centre[1])), rotated)
    footprint = box(*item.rect)
    if footprint.difference(contour.polygon).area > AREA_TOLERANCE_MM2:
        raise EquipmentError(
            f"«{kind.name}» должно стоять целиком внутри контура: сдвиньте или поверните."
        )
    return item


def turned(contour: Contour, item: Equipment) -> Equipment:
    """Повернуть на 90° вокруг центра; ``EquipmentError``, если не помещается."""
    return place_equipment(contour, item.type, item.centre, rotated=not item.rotated)


_FIELDS = {
    "length_mm": "Длина",
    "width_mm": "Ширина",
    "own_kg": "Собственная масса",
}


def validate_equipment(**fields) -> list[Issue]:
    issues = []
    if not str(fields.get("name", "")).strip():
        issues.append(Issue("name", "Укажите название оборудования."))
    for field, label in _FIELDS.items():
        if float(fields.get(field, 0)) <= 0:
            issues.append(Issue(field, f"Значение «{label}» должно быть больше нуля."))
    if float(fields.get("content_kg", 0)) < 0:
        issues.append(Issue("content_kg", "Загрузка не может быть отрицательной."))
    return issues


class EquipmentLibrary:
    """Типовые позиции (неизменяемые) и добавленные пользователем."""

    def __init__(self, custom: tuple[EquipmentType, ...] = ()) -> None:
        self._custom = list(custom)

    @property
    def items(self) -> tuple[EquipmentType, ...]:
        return (*CATALOG, *self._custom)

    def get(self, name: str) -> EquipmentType:
        for item in self.items:
            if item.name == name:
                return item
        raise KeyError(name)

    def add(self, **fields) -> list[Issue]:
        """Добавить своё оборудование. Если есть ошибки, позиция не добавляется."""
        issues = validate_equipment(**fields)
        name = str(fields.get("name", "")).strip()
        if name and any(item.name == name for item in self.items):
            issues.append(Issue("name", f"«{name}» уже есть в библиотеке."))
        if not issues:
            numbers = {k: float(v) for k, v in fields.items() if k not in ("name", "note")}
            note = str(fields.get("note", "")) or "своя позиция"
            self._custom.append(EquipmentType(name=name, note=note, **numbers))
        return issues

    def add_type(self, item: EquipmentType) -> list[Issue]:
        return self.add(**asdict(item))

    def to_json(self) -> str:
        return json.dumps([asdict(item) for item in self._custom], ensure_ascii=False)

    @classmethod
    def from_json(cls, text: str) -> EquipmentLibrary:
        library = cls()
        for fields in json.loads(text or "[]"):
            library.add(**fields)
        return library
