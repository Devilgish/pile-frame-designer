"""Файл проекта «.karkas»: исходные данные в JSON с версией формата и сводкой результата.

Результаты расчёта не хранятся целиком: при открытии проект пересчитывается, а короткая
сводка из файла позволяет заметить, что результат изменился (например, после обновления
программы). Свои профили вшиваются в файл, чтобы проект открывался на другом компьютере.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

from pile_frame.boards import BoardSpec, validate_board
from pile_frame.contour import Contour, ContourError
from pile_frame.design import Design, Project
from pile_frame.issues import errors
from pile_frame.materials import STEELS
from pile_frame.sections import ProfileCatalog, Section
from pile_frame.status import design_status
from pile_frame.tables import fmt
from pile_frame.welds import ELECTRODES
from pile_frame.zones import PRESETS, Zone, ZoneError, place_zone

APP_ID = "pile-frame-designer"
#: 1 — исходный формат; 2 — добавлены зоны помещений.
FORMAT_VERSION = 2
EXTENSION = ".karkas"


#: Обновление данных файла с версии N до N + 1. Старые файлы проходят цепочку до текущей.
def _v1_to_v2(data: dict[str, Any]) -> dict[str, Any]:
    """В формате 1 зон не было: проект без зон."""
    data["zones"] = []
    return data


MIGRATIONS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {1: _v1_to_v2}


class ProjectFileError(ValueError):
    """Файл нельзя открыть; текст исключения объясняет причину пользователю."""


@dataclass(frozen=True)
class LoadedProject:
    project: Project
    object_name: str
    summary: dict[str, Any] | None
    #: Замечания при открытии: профили из файла, изменившийся результат.
    notes: list[str] = field(default_factory=list)


def _section(section: Section) -> dict[str, Any]:
    return asdict(section)


def summarize(design: Design) -> dict[str, Any]:
    """Короткая сводка результата для сверки после открытия."""
    _, label, utilization = design_status(design)
    return {
        "status": label,
        "max_utilization": round(utilization, 4),
        "members": len(design.members),
        "total_reaction_kn": round(sum(design.reactions_kn.values()), 3),
    }


def summary_note(saved: dict[str, Any] | None, design: Design) -> str | None:
    """Замечание, если пересчитанный результат не совпал со сводкой из файла."""
    if not saved:
        return None
    now = summarize(design)
    changes = []
    if abs(now["max_utilization"] - saved.get("max_utilization", 0)) > 5e-4:
        changes.append(
            f"наибольшая загрузка {saved.get('max_utilization', 0):.0%} → "
            f"{now['max_utilization']:.0%}"
        )
    if now["members"] != saved.get("members"):
        changes.append(f"элементов {saved.get('members')} → {now['members']}")
    if abs(now["total_reaction_kn"] - saved.get("total_reaction_kn", 0)) > 5e-3:
        changes.append(
            f"сумма реакций свай {fmt(saved.get('total_reaction_kn', 0), 2)} → "
            f"{fmt(now['total_reaction_kn'], 2)} кН"
        )
    if not changes:
        return None
    return (
        "Результаты расчёта отличаются от сохранённых (возможно, проект считался другой "
        "версией программы): " + "; ".join(changes) + "."
    )


def _one_line(match: re.Match[str]) -> str:
    return "[" + ", ".join(v.strip() for v in match.group(1).split(",")) + "]"


def save_text(project: Project, object_name: str, design: Design | None = None) -> str:
    """Проект в текст файла."""
    board = project.board
    data = {
        "app": APP_ID,
        "format_version": FORMAT_VERSION,
        "object_name": object_name,
        "plan": {
            "contour": [list(v) for v in project.outline.vertices],
            "piles": None if project.piles is None else [list(p) for p in project.piles],
            "pile_step_mm": project.pile_step_mm,
        },
        "loads": {"live_load_kpa": project.live_load_kpa},
        "frame": {
            "perimeter": _section(project.perimeter_section),
            "internal": _section(project.internal_section),
            "jumper": _section(project.jumper_section),
            "steel": project.steel.name,
            "electrode": project.electrode,
        },
        "board": asdict(board),
        "sheets": {
            "long_side": project.sheet_long_side,
            "offset_mm": list(project.sheet_offset_mm),
            "gap_mm": project.sheet_gap_mm,
            "joints": project.sheet_joints,
        },
        "zones": [
            {
                "kind": z.kind,
                "rect": list(z.rect),
                "live_load_kpa": z.live_load_kpa,
                "cold_on_board": z.cold_on_board,
            }
            for z in project.zones
        ],
        "summary": None if design is None else summarize(design),
    }
    text = json.dumps(data, ensure_ascii=False, indent=2)
    # Числовые массивы (координаты, прямоугольники зон) — в одну строку: [1250.0, 0.0].
    return re.sub(r"\[\s*(-?[\d.e+-]+(?:,\s*-?[\d.e+-]+)*)\s*\]", _one_line, text)


def _points(raw) -> tuple[tuple[float, float], ...]:
    return tuple((float(x), float(y)) for x, y in raw)


NOT_A_PROJECT = "Файл не является файлом проекта «Каркас на сваях»."


def _parse(text: str) -> dict[str, Any]:
    """JSON проекта текущей версии формата."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise ProjectFileError(NOT_A_PROJECT) from error
    if not isinstance(data, dict) or data.get("app") != APP_ID:
        raise ProjectFileError(NOT_A_PROJECT)
    version = data.get("format_version")
    if not isinstance(version, int):
        raise ProjectFileError("Файл проекта повреждён: не указана версия формата.")
    if version > FORMAT_VERSION:
        raise ProjectFileError(
            f"Файл создан более новой версией программы (формат {version}, "
            f"эта версия читает до {FORMAT_VERSION}). Обновите программу."
        )
    for step in range(version, FORMAT_VERSION):
        data = MIGRATIONS[step](data)
    return data


FROM_FILE = " (из файла)"


def _profile(raw: dict[str, Any], catalog: ProfileCatalog, notes: list[str]) -> Section:
    """Профиль из файла: тот же в справочнике, добавленный в справочник или переименованный."""
    section = Section(**raw)
    names = {s.name: s for s in catalog.sections}
    if names.get(section.name) == section:
        return section
    if section.name in names:
        renamed = Section(**{**raw, "name": section.name + FROM_FILE})
        if names.get(renamed.name) != renamed:
            _add(catalog, renamed)
        notes.append(
            f"Профиль «{section.name}» в справочнике отличается от сохранённого в проекте: "
            f"данные из файла добавлены как «{renamed.name}»."
        )
        return renamed
    _add(catalog, section)
    notes.append(f"Профиль «{section.name}» добавлен в справочник из файла.")
    return section


def _add(catalog: ProfileCatalog, section: Section) -> None:
    issues = catalog.add(**asdict(section))
    if issues:
        raise ProjectFileError(f"В файле неверный профиль «{section.name}»: {issues[0].message}")


def load_text(text: str, catalog: ProfileCatalog) -> LoadedProject:
    """Текст файла в проект. Ошибки — ``ProjectFileError`` с понятным сообщением."""
    data = _parse(text)
    try:
        plan, frame, sheets = data["plan"], data["frame"], data["sheets"]
        try:
            contour = Contour.from_points(_points(plan["contour"]))
        except ContourError as error:
            raise ProjectFileError(f"В файле неверный контур: {error}") from error
        steel_name, electrode = frame["steel"], frame["electrode"]
        if steel_name not in STEELS:
            raise ProjectFileError(f"В файле неизвестная сталь «{steel_name}».")
        if electrode not in ELECTRODES:
            raise ProjectFileError(f"В файле неизвестный электрод «{electrode}».")
        if sheets["long_side"] not in ("x", "y"):
            raise ValueError(sheets["long_side"])
        step, live, gap = (
            float(plan["pile_step_mm"]),
            float(data["loads"]["live_load_kpa"]),
            float(sheets["gap_mm"]),
        )
        if step <= 0 or live < 0 or gap < 0:
            raise ValueError("отрицательное или нулевое значение")
        board = BoardSpec(**{k: float(v) for k, v in data["board"].items()})
        board_errors = errors(validate_board(board))
        if board_errors:
            raise ProjectFileError("В файле неверный лист: " + board_errors[0].message)
        zones = _zones(data["zones"], contour)
        notes: list[str] = []
        sections = {
            key: _profile(frame[key], catalog, notes) for key in ("perimeter", "internal", "jumper")
        }
        project = Project(
            contour=contour,
            piles=None if plan["piles"] is None else _points(plan["piles"]),
            pile_step_mm=step,
            live_load_kpa=live,
            perimeter_section=sections["perimeter"],
            internal_section=sections["internal"],
            jumper_section=sections["jumper"],
            steel=STEELS[steel_name],
            electrode=electrode,
            board=board,
            sheet_long_side=sheets["long_side"],
            sheet_offset_mm=tuple(float(v) for v in sheets["offset_mm"]),
            sheet_gap_mm=gap,
            sheet_joints=bool(sheets["joints"]),
            zones=zones,
        )
        return LoadedProject(project, str(data["object_name"]), data["summary"], notes)
    except ProjectFileError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise ProjectFileError(f"Файл проекта повреждён: {_describe(error)}.") from error


def _zones(raw: list[dict[str, Any]], contour: Contour) -> tuple[Zone, ...]:
    """Зоны из файла с теми же проверками, что при рисовании: внутри контура, без наложений."""
    zones: list[Zone] = []
    for item in raw:
        kind = item["kind"]
        if kind not in PRESETS:
            raise ProjectFileError(f"В файле неизвестное назначение зоны «{kind}».")
        load = float(item["live_load_kpa"])
        if load < 0:
            raise ValueError("отрицательная нагрузка зоны")
        try:
            placed = place_zone(contour, zones, tuple(float(v) for v in item["rect"]), kind)
        except ZoneError as error:
            raise ProjectFileError(f"В файле неверная зона: {error}") from error
        zones.append(Zone(kind, placed.rect, load, bool(item.get("cold_on_board", False))))
    return tuple(zones)


def _describe(error: Exception) -> str:
    if isinstance(error, KeyError):
        return f"нет поля «{error.args[0]}»"
    return "неверное значение в данных"
