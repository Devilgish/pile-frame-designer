"""Сортамент профилей: гнутые замкнутые сварные профили по ГОСТ 30245-2003."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from pile_frame.issues import Issue


@dataclass(frozen=True)
class Section:
    """Характеристики сечения относительно оси изгиба (большая сторона вертикально)."""

    name: str
    height_mm: float
    width_mm: float
    thickness_mm: float
    mass_kg_m: float
    area_cm2: float
    ix_cm4: float
    wx_cm3: float


TUBE_120x120x5 = Section("120×120×5", 120, 120, 5, 17.55, 22.36, 485.3, 80.88)
TUBE_120x60x4 = Section("120×60×4", 120, 60, 4, 10.48, 13.35, 240.7, 40.12)
TUBE_40x40x3 = Section("40×40×3", 40, 40, 3, 3.30, 4.21, 9.31, 4.65)

#: Профили ГОСТ 30245-2003, всегда присутствующие в справочнике.
GOST_SECTIONS = (TUBE_120x120x5, TUBE_120x60x4, TUBE_40x40x3)


_POSITIVE_FIELDS = {
    "height_mm": "Высота",
    "width_mm": "Ширина",
    "thickness_mm": "Толщина стенки",
    "mass_kg_m": "Масса",
    "area_cm2": "Площадь",
    "ix_cm4": "Момент инерции Ix",
    "wx_cm3": "Момент сопротивления Wx",
}


def validate_section(**fields: float | str) -> list[Issue]:
    """Проверить данные своего профиля. Возвращает ошибки, привязанные к полям."""
    issues = []
    if not str(fields.get("name", "")).strip():
        issues.append(Issue("name", "Укажите название профиля."))
    for field, label in _POSITIVE_FIELDS.items():
        if float(fields[field]) <= 0:
            issues.append(Issue(field, f"Значение «{label}» должно быть больше нуля."))
    if not any(i.field in ("height_mm", "width_mm", "thickness_mm") for i in issues):
        half = min(float(fields["height_mm"]), float(fields["width_mm"])) / 2
        if float(fields["thickness_mm"]) >= half:
            issues.append(
                Issue(
                    "thickness_mm",
                    f"Стенка должна быть меньше половины меньшей стороны ({half:g} мм).",
                )
            )
    return issues


class ProfileCatalog:
    """Справочник профилей: ГОСТ 30245-2003 (неизменяемые) и добавленные пользователем."""

    def __init__(self, custom: tuple[Section, ...] = ()) -> None:
        self._custom: list[Section] = list(custom)

    @property
    def sections(self) -> tuple[Section, ...]:
        return (*GOST_SECTIONS, *self._custom)

    def get(self, name: str) -> Section:
        for section in self.sections:
            if section.name == name:
                return section
        raise KeyError(name)

    def validate(self, **fields: float | str) -> list[Issue]:
        """Замечания к своему профилю с учётом уже имеющихся названий."""
        issues = validate_section(**fields)
        name = str(fields.get("name", "")).strip()
        if name and any(s.name == name for s in self.sections):
            issues.append(Issue("name", f"Профиль «{name}» уже есть в справочнике."))
        return issues

    def add(self, **fields: float | str) -> list[Issue]:
        """Добавить свой профиль. Если есть ошибки, профиль не добавляется."""
        issues = self.validate(**fields)
        name = str(fields.get("name", "")).strip()
        if not issues:
            numbers = {k: float(v) for k, v in fields.items() if k != "name"}
            self._custom.append(Section(name=name, **numbers))
        return issues

    def remove(self, name: str) -> None:
        if any(s.name == name for s in GOST_SECTIONS):
            raise ValueError(f"Профиль «{name}» из ГОСТ 30245-2003 удалить нельзя.")
        self._custom = [s for s in self._custom if s.name != name]

    def to_json(self) -> str:
        return json.dumps([asdict(s) for s in self._custom], ensure_ascii=False)

    @classmethod
    def from_json(cls, text: str) -> ProfileCatalog:
        catalog = cls()
        for fields in json.loads(text or "[]"):
            catalog.add(**fields)
        return catalog
