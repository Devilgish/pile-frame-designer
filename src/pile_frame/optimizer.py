"""Оптимизация каркаса по массе металла.

Перебираются ориентация листов, смещение их сетки (шаг ``step_mm`` и положения, при которых
стык ложится на ось свай), профили периметра и внутренних балок. Перемычки ставятся
автоматически, а непроходящие балки точечно заменяются более тяжёлым профилем той же высоты.

Ветви и границы: масса геометрии считается без расчёта и не больше итоговой (усиления только
добавляют металл). Варианты проверяются по возрастанию этой оценки; как только оценка не
меньше массы худшего из ``keep`` найденных, остальные заведомо тяжелее. Поэтому результат
совпадает с полным перебором того же набора вариантов.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, replace

from pile_frame.design import (
    AnalysisError,
    Design,
    Frame,
    Project,
    analyze,
    frame,
    member_key,
)
from pile_frame.sections import Section

#: Сколько раз подряд усиливать непроходящие балки, прежде чем отказаться от варианта.
MAX_UPGRADE_ROUNDS = 6
#: Массы, отличающиеся меньше этого, считаются равными, кг.
MASS_TOLERANCE_KG = 0.05
#: Варианты с той же ориентацией и профилями, чьи массы различаются меньше этой доли,
#: показываются как один (это одна раскладка, сдвинутая на миллиметры).
BUCKET_SHARE = 0.005
LONG_SIDES = ("x", "y")


@dataclass(frozen=True)
class Variant:
    """Проходящий все проверки вариант и что в нём изменено против исходного проекта."""

    project: Project
    design: Design
    changes: tuple[str, ...]

    @property
    def mass_kg(self) -> float:
        return self.design.steel_mass_kg


@dataclass(frozen=True)
class OptimizationResult:
    variants: list[Variant]
    #: Сколько вариантов просчитано полностью (с грильяжем) и сколько было геометрий.
    analysed: int
    total: int
    cancelled: bool = False


def _axis_offsets(
    low: float, axes: list[float], size: float, gap: float, step: float
) -> list[float]:
    """Смещения сетки листов вдоль оси: шаг ``step`` и стыки на осях свай."""
    pitch = size + gap
    values = {round(i * step, 1) for i in range(math.ceil(pitch / step))}
    values |= {round((a - low - size - gap / 2) % pitch, 1) for a in axes}
    return sorted(v for v in values if v < pitch - 0.05)


def _layouts(project: Project, step_mm: float) -> list[tuple[str, tuple[float, float]]]:
    if not project.sheet_joints:
        return [(project.sheet_long_side, project.sheet_offset_mm)]
    contour = project.outline
    min_x, min_y, _, _ = contour.polygon.bounds
    piles = frame(project).supports
    xs = sorted({p[0] for p in piles})
    ys = sorted({p[1] for p in piles})
    board, gap = project.board, project.sheet_gap_mm
    layouts = []
    for side in LONG_SIDES:
        size_x, size_y = (
            (board.length_mm, board.width_mm) if side == "x" else (board.width_mm, board.length_mm)
        )
        for ox in _axis_offsets(min_x, xs, size_x, gap, step_mm):
            for oy in _axis_offsets(min_y, ys, size_y, gap, step_mm):
                layouts.append((side, (ox, oy)))
    return layouts


def _feasible_geometry(built: Frame) -> bool:
    """Отбросить без расчёта: лист не проходит даже с перемычками, балки без опоры."""
    return not built.unsupported and all(c.check.passed for c in built.board_cells)


def _heavier(section: Section, sections: list[Section]) -> Section | None:
    for candidate in sections:
        if candidate.mass_kg_m > section.mass_kg_m:
            return candidate
    return None


def _passes(design: Design) -> bool:
    return (
        not design.failing_members()
        and all(c.check.passed for c in design.board_cells)
        and all(w.check.utilization <= 1 for w in design.welds)
    )


def _evaluate(project: Project, sections: list[Section]) -> Design | None:
    """Расчёт с точечными усилениями; ``None`` — вариант не удаётся сделать проходящим."""
    upgrades = dict(project.upgrades)
    for _ in range(MAX_UPGRADE_ROUNDS):
        try:
            design = analyze(replace(project, upgrades=tuple(upgrades.items())))
        except AnalysisError:
            return None
        if _passes(design):
            return design
        if design.unsupported_members or any(w.check.utilization > 1 for w in design.welds):
            return None
        for member in design.failing_members():
            stronger = _heavier(member.section, sections)
            if stronger is None or member.kind == "jumper":
                return None
            upgrades[member_key(member)] = stronger
    return None


def _n(value: float, digits: int = 1) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


def _g(value: float) -> str:
    return f"{value:g}".replace(".", ",")


def _changes(base: Project, variant: Project) -> tuple[str, ...]:
    changes = []
    if variant.sheet_long_side != base.sheet_long_side:
        side = "вдоль X" if variant.sheet_long_side == "x" else "вдоль Y"
        changes.append(f"листы длинной стороной {side}")
    if variant.sheet_offset_mm != base.sheet_offset_mm:
        ox, oy = variant.sheet_offset_mm
        changes.append(f"смещение листов {_g(ox)}; {_g(oy)} мм")
    if variant.perimeter_section != base.perimeter_section:
        changes.append(f"периметр {variant.perimeter_section.name}")
    if variant.internal_section != base.internal_section:
        changes.append(f"внутренние балки {variant.internal_section.name}")
    if variant.upgrades:
        changes.append(f"усилено балок: {len(variant.upgrades)}")
    return tuple(changes) or ("без изменений",)


def optimize(
    project: Project,
    sections: tuple[Section, ...] | list[Section],
    *,
    step_mm: float = 250.0,
    keep: int = 5,
    prune: bool = True,
    progress: Callable[[int, int], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> OptimizationResult:
    """Лучшие ``keep`` вариантов по массе металла, все проходят проверки.

    ``sections`` — профили для периметра, внутренних балок и усилений; берутся те, что одной
    высоты с внутренними балками проекта (верх каркаса в одной плоскости).
    """
    height = project.internal_section.height_mm
    family = sorted({s for s in sections if s.height_mm == height}, key=lambda s: s.mass_kg_m)
    family = family or [project.internal_section]
    base = replace(project, upgrades=())

    # 1. Геометрии (дёшево). Профиль влияет на геометрию только шириной внутренней балки
    #    (допуск «стык рядом с балкой»), поэтому каркас строится один раз на раскладку и ширину,
    #    а масса для каждого сочетания профилей считается по длинам. Из вариантов с одинаковой
    #    массой, ориентацией и профилями остаётся один — с наименьшими отходами ЦСП.
    found: list[tuple[float, float, int, Project]] = []
    order = 0
    for side, offset in _layouts(base, step_mm):
        laid = replace(base, sheet_long_side=side, sheet_offset_mm=offset)
        built_by_width: dict[float, Frame] = {}
        for internal in family:
            if internal.width_mm not in built_by_width:
                built_by_width[internal.width_mm] = frame(
                    replace(laid, perimeter_section=family[0], internal_section=internal)
                )
            built = built_by_width[internal.width_mm]
            if not _feasible_geometry(built):
                continue
            lengths = {"perimeter": 0.0, "beam": 0.0}
            jumpers = 0.0
            for m in built.members:
                if m.kind == "jumper":
                    jumpers += m.mass_kg
                else:
                    lengths[m.kind] += m.length_mm / 1e3
            for perimeter in family:
                mass = (
                    lengths["perimeter"] * perimeter.mass_kg_m
                    + lengths["beam"] * internal.mass_kg_m
                    + jumpers
                )
                variant = replace(laid, perimeter_section=perimeter, internal_section=internal)
                found.append((mass, built.layout.offcut_m2, order, variant))
                order += 1
    # Почти одинаковые варианты (та же ориентация и профили, масса в пределах BUCKET_SHARE)
    # — это одна раскладка, сдвинутая на миллиметры: остаётся самый лёгкий.
    bucket = max(1.0, BUCKET_SHARE * min((f[0] for f in found), default=0.0))
    chosen: dict[tuple, tuple[float, float, int, Project]] = {}
    for item in sorted(found, key=lambda f: (f[0], f[1], f[2])):
        mass, _, _, variant = item
        key = (
            math.floor(mass / bucket),
            variant.sheet_long_side,
            variant.perimeter_section.name,
            variant.internal_section.name,
        )
        chosen.setdefault(key, item)
    candidates = sorted(chosen.values(), key=lambda c: (c[0], c[1], c[2]))

    # 2. Расчёт по возрастанию нижней оценки массы с отсечением.
    best: list[Variant] = []
    analysed = 0
    total = len(candidates)
    for done, (lower_bound, _, _, variant) in enumerate(candidates, start=1):
        if cancelled is not None and cancelled():
            return OptimizationResult(best, analysed, total, cancelled=True)
        # Строго тяжелее худшего из лучших (с запасом на округление) — дальше смотреть незачем.
        if prune and len(best) >= keep and lower_bound > best[-1].mass_kg + MASS_TOLERANCE_KG:
            if progress is not None:
                progress(total, total)
            break
        design = _evaluate(variant, family)
        analysed += 1
        if design is not None:
            final = replace(variant, upgrades=_upgrades_of(design, variant))
            best.append(Variant(final, design, _changes(project, final)))
            best.sort(key=lambda v: v.mass_kg)
            del best[keep:]
        if progress is not None:
            progress(done, total)
    return OptimizationResult(best, analysed, total)


def _upgrades_of(design: Design, variant: Project) -> tuple:
    """Усиления, которые понадобились варианту: балки с профилем тяжелее назначенного."""
    planned = {"perimeter": variant.perimeter_section, "beam": variant.internal_section}
    return tuple(
        (member_key(m), m.section)
        for m in design.members
        if m.kind in planned and m.section != planned[m.kind]
    )


def _by_kind(design: Design) -> dict[str, dict[str, tuple[float, int]]]:
    """Тип элемента → профиль → (длина, м; число элементов)."""
    totals: dict[str, dict[str, tuple[float, int]]] = {}
    for m in design.members:
        sections = totals.setdefault(m.kind, {})
        length, count = sections.get(m.section.name, (0.0, 0))
        sections[m.section.name] = (length + m.length_mm / 1e3, count + 1)
    return totals


_KINDS = {"perimeter": "Периметр", "beam": "Балки", "jumper": "Перемычки"}


def _describe(sections: dict[str, tuple[float, int]]) -> str:
    if not sections:
        return "нет"
    return ", ".join(
        f"{name} {_n(length)} м ({count} шт.)" for name, (length, count) in sorted(sections.items())
    )


def _compare(variant: Design, other: Design) -> list[str]:
    a, b = _by_kind(variant), _by_kind(other)
    lines = []
    for kind, title in _KINDS.items():
        mine, theirs = a.get(kind, {}), b.get(kind, {})
        same = mine.keys() == theirs.keys() and all(
            abs(mine[k][0] - theirs[k][0]) < 0.01 for k in mine
        )
        if not same:
            lines.append(f"{title}: {_describe(mine)} вместо {_describe(theirs)}")
    return lines


def explain(variant: Variant, current: Design, others: list[Variant]) -> list[str]:
    """Почему вариант легче: сравнение с текущим проектом и со следующим по массе вариантом."""
    diff = current.steel_mass_kg - variant.mass_kg
    if abs(diff) < MASS_TOLERANCE_KG:
        lines = [f"Масса совпадает с текущим проектом: {_n(variant.mass_kg)} кг."]
    else:
        word = "легче" if diff > 0 else "тяжелее"
        share = abs(diff) / current.steel_mass_kg if current.steel_mass_kg else 0.0
        lines = [
            f"{_n(variant.mass_kg)} кг — {word} текущего проекта на {_n(abs(diff))} кг "
            f"({share:.0%})."
        ]
    if not _passes(current):
        lines.append("Текущий проект не проходит проверки, вариант проходит все.")
    lines += _compare(variant.design, current)
    if variant.project.upgrades:
        lines.append(
            f"Точечно усилено балок: {len(variant.project.upgrades)} — дешевле, чем утяжелять "
            "все балки этого типа."
        )
    if others:
        nxt = others[0]
        lines.append(
            f"Следующий вариант тяжелее на {_n(nxt.mass_kg - variant.mass_kg)} кг "
            f"({', '.join(nxt.changes)}):"
        )
        lines += [f"  {line}" for line in _compare(variant.design, nxt.design)]
    return lines
