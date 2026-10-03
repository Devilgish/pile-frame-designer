"""Расчётная записка: содержание без оформления.

Записка собирается из результата расчёта в виде разделов с абзацами, формулами и таблицами.
Оформление (PDF) — отдельно, в ``pdf.py``. Подробно, с формулой и подставленными числами,
расписывается самый загруженный элемент каждого типа; остальные — таблицами.
"""

from __future__ import annotations

import datetime
import math
from collections.abc import Iterator
from dataclasses import dataclass, field

from pile_frame import assumptions, tables
from pile_frame.analysis import (
    GAMMA_F_BOARD,
    GAMMA_F_POINT,
    GAMMA_F_STEEL,
    GRAVITY,
    POINT_LOAD_N,
    SHEAR_RATIO,
    gamma_f_live,
    static_moment_mm3,
)
from pile_frame.beam import GAMMA_C, LIVE_SHARE_FOR_DEFLECTION
from pile_frame.board_check import (
    BOARD_E_MPA,
    GAMMA_M,
    KDEF,
    KMOD_MEDIUM,
    KMOD_SHORT,
    POISSON,
    bending_strength_mpa,
    load_radius_mm,
)
from pile_frame.design import Design, Member, Project
from pile_frame.materials import STEEL_E_MPA
from pile_frame.stability import WEB_SLENDERNESS_LIMIT
from pile_frame.status import design_status
from pile_frame.welds import BETA_F, BETA_Z
from pile_frame.zones import PRESETS

#: Типы элементов каркаса в порядке изложения.
KIND_TITLES = {"perimeter": "Балка периметра", "beam": "Балка", "jumper": "Перемычка"}


def num(value: float, digits: int = 3) -> str:
    """Число с запятой: 1,813."""
    return f"{value:.{digits}f}".replace(".", ",")


def grouped(value: float) -> str:
    """Целое с разделением разрядов: 49 625."""
    return f"{value:,.0f}".replace(",", " ")


def short(value: float) -> str:
    """Число без лишних нулей: 80,88; 240."""
    return f"{value:g}".replace(".", ",")


def verdict(utilization: float) -> str:
    """Итог проверки после коэффициента: «0,093 ≤ 1» или «1,196 > 1 — не проходит»."""
    if utilization <= 1:
        return f"{num(utilization)} ≤ 1"
    return f"{num(utilization)} > 1 — не проходит"


@dataclass(frozen=True)
class ReportMeta:
    object_name: str
    author: str
    date: datetime.date


@dataclass(frozen=True)
class Paragraph:
    text: str


@dataclass(frozen=True)
class Heading:
    """Подзаголовок внутри раздела."""

    text: str


@dataclass(frozen=True)
class Formula:
    """Проверка: название с пунктом норм, строки расчёта, итоговый коэффициент использования."""

    title: str
    lines: tuple[str, ...]
    utilization: float


@dataclass(frozen=True)
class Table:
    title: str
    headers: tuple[str, ...]
    rows: list[tuple[str, ...]]


@dataclass(frozen=True)
class PlanMember:
    start: tuple[float, float]
    end: tuple[float, float]
    kind: str
    label: str
    failing: bool


@dataclass(frozen=True)
class PlanFigure:
    """Схема плана: контур, элементы с марками, сваи с марками, кромки без опоры."""

    contour: tuple[tuple[float, float], ...]
    members: tuple[PlanMember, ...]
    piles: tuple[tuple[tuple[float, float], str], ...]
    bearing: tuple[tuple[tuple[float, float], tuple[float, float]], ...]
    #: Зоны: прямоугольник, подпись «назначение, нагрузка», нужна ли пометка-предупреждение.
    zones: tuple[tuple[tuple[float, float, float, float], str, bool], ...] = ()


@dataclass
class Section:
    title: str
    blocks: list = field(default_factory=list)


@dataclass
class Report:
    meta: ReportMeta
    sections: list[Section]

    def _blocks(self, kind: type):
        for section in self.sections:
            for block in section.blocks:
                if isinstance(block, kind):
                    yield block

    def formulas(self) -> Iterator[Formula]:
        yield from self._blocks(Formula)

    def tables(self) -> Iterator[Table]:
        yield from self._blocks(Table)

    def summary(self) -> str:
        """Текст раздела «Итог»."""
        return "\n".join(b.text for b in self.sections[0].blocks if isinstance(b, Paragraph))


def _bending(member: Member, check, project: Project) -> Formula:
    section = member.section
    ry = project.steel.ry_mpa(section.thickness_mm)
    u = check.strength_utilization
    return Formula(
        "Прочность при изгибе (СП 16.13330.2017, формула 41)",
        (
            "M / (Wx·Ry·γc) ≤ 1",
            f"{num(check.max_moment_knm)}·10⁶ / ({short(section.wx_cm3)}·10³ · {short(ry)} · "
            f"{short(GAMMA_C)}) = {verdict(u)}",
        ),
        u,
    )


def _shear(member: Member, check, project: Project) -> Formula:
    section = member.section
    ry = project.steel.ry_mpa(section.thickness_mm)
    rs = SHEAR_RATIO * ry
    tw = 2 * section.thickness_mm
    u = check.shear_utilization
    return Formula(
        "Прочность при срезе по двум стенкам (СП 16.13330.2017, формула 42)",
        (
            "Q·S / (Ix·tw·Rs·γc) ≤ 1",
            f"Rs = {short(SHEAR_RATIO)}·Ry = {short(SHEAR_RATIO)}·{short(ry)} = {short(rs)} Н/мм²",
            f"{num(check.max_shear_kn)}·10³ · {grouped(static_moment_mm3(section))} / "
            f"({short(section.ix_cm4)}·10⁴ · {short(tw)} · {short(rs)} · {short(GAMMA_C)}) "
            f"= {verdict(u)}",
        ),
        u,
    )


def _deflection(check) -> Formula:
    f, fu, u = check.deflection_mm, check.deflection_limit_mm, check.deflection_utilization
    return Formula(
        "Прогиб (СП 20.13330.2016, таблица Д.1, п. 2а)",
        (
            "f ≤ fu; f — от постоянной и 0,35 временной нормативной нагрузки",
            f"fu для l = {check.deflection_span_mm:.0f} мм: {num(fu, 2)} мм",
            f"f / fu = {num(f, 2)} / {num(fu, 2)} = {verdict(u)}",
        ),
        u,
    )


def _slenderness(section, ry: float, side: float) -> tuple[float, str]:
    """Условная гибкость пластинки шириной side − 2t и её запись с подставленными числами."""
    t = section.thickness_mm
    value = (side - 2 * t) / t * math.sqrt(ry / STEEL_E_MPA)
    text = (
        f"({short(side)} − 2·{short(t)}) / {short(t)} · √({short(ry)} / {grouped(STEEL_E_MPA)}) "
        f"= {num(value)}"
    )
    return value, text


def _web(member: Member, check, project: Project) -> Formula:
    section = member.section
    ry = project.steel.ry_mpa(section.thickness_mm)
    value, text = _slenderness(section, ry, section.height_mm)
    limit = short(WEB_SLENDERNESS_LIMIT)
    u = check.web_utilization
    return Formula(
        "Местная устойчивость стенки (СП 16.13330.2017, п. 8.5.1)",
        (
            f"λw = (h − 2t) / t · √(Ry / E) ≤ {limit}",
            f"λw = {text}",
            f"λw / {limit} = {num(value)} / {limit} = {verdict(u)}",
        ),
        u,
    )


def _flange(member: Member, check, project: Project) -> Formula:
    section = member.section
    ry = project.steel.ry_mpa(section.thickness_mm)
    value, text = _slenderness(section, ry, section.width_mm)
    sigma = check.max_moment_knm * 1e6 / (section.wx_cm3 * 1e3 * GAMMA_C)
    u = check.flange_utilization
    return Formula(
        "Местная устойчивость поясного листа (СП 16.13330.2017, формула 98)",
        (
            "λf = (b − 2t) / t · √(Ry / E) ≤ 1,5·√(Ry / σc), σc не больше Ry",
            f"σc = M / Wx = {num(check.max_moment_knm)}·10⁶ / {short(section.wx_cm3)}·10³ "
            f"= {num(sigma, 2)} Н/мм²",
            f"λf = {text}",
            f"λf / (1,5·√(Ry / σc)) = {num(value)} / (1,5·√({short(ry)} / "
            f"{num(min(sigma, ry), 2)})) = {verdict(u)}",
        ),
        u,
    )


def _members_section(project: Project, design: Design) -> Section:
    section = Section("Проверки элементов каркаса")
    for kind, title in KIND_TITLES.items():
        indexed = [
            (i, m, c)
            for i, (m, c) in enumerate(zip(design.members, design.checks, strict=True))
            if m.kind == kind
        ]
        if not indexed:
            continue
        index, member, check = max(indexed, key=lambda imc: imc[2].utilization)
        section.blocks.append(
            Heading(
                f"{title} {tables.member_label(index)}: {member.section.name}, "
                f"длина {member.length_mm:.0f} мм"
            )
        )
        section.blocks.append(_bending(member, check, project))
        section.blocks.append(_shear(member, check, project))
        section.blocks.append(_deflection(check))
        section.blocks.append(_web(member, check, project))
        section.blocks.append(_flange(member, check, project))
    unsupported = {id(m) for m in design.unsupported_members}
    rows = [
        _texts(tables.member_row(i, m, c, id(m) in unsupported))
        for i, (m, c) in enumerate(zip(design.members, design.checks, strict=True))
    ]
    section.blocks.append(Table("Элементы каркаса", tables.MEMBER_COLUMNS, rows))
    return section


def _texts(row: list[tables.Cell]) -> tuple[str, ...]:
    return tuple(text for text, _ in row)


SP20 = "СП 20.13330.2016"


def _board_formulas(project: Project, check) -> list[Formula]:
    board, live = project.board, project.live_load_kpa
    t, span = board.thickness_mm, check.span_mm
    g = project.board_load_kpa
    rn = bending_strength_mpa(t)
    w = short(check.section_modulus)

    def resistance(kmod: float, value: float) -> str:
        return (
            f"R = kmod·Rн / γm = {short(kmod)}·{short(rn)} / {short(GAMMA_M)} "
            f"= {num(value, 2)} Н/мм²"
        )

    u = check.uniform_utilization
    uniform = Formula(
        "Лист ЦСП: равномерная нагрузка (ГОСТ 26816-2016, таблица 2)",
        (
            "M / (W·R) ≤ 1; полоса шириной 1 мм на пролёте l — меньшей стороне ячейки",
            f"q = {short(GAMMA_F_BOARD)}·g + γf·p = {short(GAMMA_F_BOARD)}·{num(g)} + "
            f"{short(gamma_f_live(live))}·{num(live, 2)} = {num(check.design_load * 1e3)} кПа",
            f"M = q·l² / 8 = {num(check.design_load * 1e3)}·10⁻³ · {span:.0f}² / 8 "
            f"= {num(check.uniform_moment, 1)} Н·мм/мм",
            resistance(KMOD_MEDIUM, check.strength_medium),
            f"M / (W·R) = {num(check.uniform_moment, 1)} / ({w} · "
            f"{num(check.strength_medium, 2)}) = {verdict(u)}",
        ),
        u,
    )
    force = GAMMA_F_POINT * POINT_LOAD_N
    dead_moment = GAMMA_F_BOARD * g * 1e-3 * span**2 / 8
    u = check.point_utilization
    point = Formula(
        "Лист ЦСП: сосредоточенная нагрузка (СП 20.13330.2016, п. 8.3.4; Тимошенко, пластина)",
        (
            f"M = P / (4π)·[(1 + ν)·ln(2l / (πc)) + 1] + {short(GAMMA_F_BOARD)}·g·l² / 8; "
            f"P = {short(GAMMA_F_POINT)}·{short(POINT_LOAD_N)} Н, ν = {short(POISSON)}",
            f"c = {num(load_radius_mm(t), 1)} мм — радиус круга той же площади, что 10×10 см",
            f"M = {short(force)} / (4π)·[{short(1 + POISSON)}·ln(2·{span:.0f} / "
            f"(π·{num(load_radius_mm(t), 1)})) + 1] + {num(dead_moment, 1)} "
            f"= {num(check.point_moment, 1)} Н·мм/мм",
            resistance(KMOD_SHORT, check.strength_short),
            f"M / (W·R) = {num(check.point_moment, 1)} / ({w} · "
            f"{num(check.strength_short, 2)}) = {verdict(u)}",
        ),
        u,
    )
    u = check.deflection_utilization
    deflection = Formula(
        "Лист ЦСП: прогиб (СП 20.13330.2016, таблица Д.1)",
        (
            f"f = 5·q·l⁴ / (384·E·I); E = {short(BOARD_E_MPA)} / (1 + kdef), kdef = {short(KDEF)}",
            f"q = g + {short(LIVE_SHARE_FOR_DEFLECTION)}·p = {num(g)} + "
            f"{short(LIVE_SHARE_FOR_DEFLECTION)}·{num(live, 2)} = "
            f"{num(check.long_term_load * 1e3)} кПа",
            f"E·I = {short(BOARD_E_MPA)} / {short(1 + KDEF)} · {short(t)}³ / 12 "
            f"= {num(check.stiffness / 1e6)}·10⁶ Н·мм²/мм",
            f"fu для l = {span:.0f} мм: {num(check.deflection_limit_mm, 2)} мм",
            f"f / fu = {num(check.deflection_mm, 2)} / {num(check.deflection_limit_mm, 2)} "
            f"= {verdict(u)}",
        ),
        u,
    )
    return [uniform, point, deflection]


def _boards_section(project: Project, design: Design) -> Section | None:
    if not design.board_cells:
        return None
    section = Section("Лист ЦСП и перемычки")
    cell = max(design.board_cells, key=lambda c: c.check.utilization)
    x0, y0, x1, y1 = cell.bounds
    jumpers = (
        "лист не проходит даже с перемычками"
        if cell.jumpers is None
        else (f"перемычек {cell.jumpers}")
    )
    section.blocks.append(
        Paragraph(
            f"Самая загруженная ячейка {x1 - x0:.0f} × {y1 - y0:.0f} мм, {jumpers}, "
            f"пролёт листа {cell.check.span_mm:.0f} мм."
        )
    )
    section.blocks += _board_formulas(project, cell.check)
    rows = [_texts(tables.board_row(c)) for c in design.board_cells]
    section.blocks.append(Table("Ячейки листов ЦСП", tables.BOARD_COLUMNS, rows))
    if design.bearing_issues:
        section.blocks.append(
            Paragraph(
                "Кромка листа должна лежать на плоской части полки (без скруглений R = 2t, "
                "ГОСТ 30245-2003) не меньше, чем отступ самореза от кромки по рекомендациям "
                "производителя. Недостаток не исправляется автоматически."
            )
        )
        rows = [
            (
                f"({i.start[0]:.0f}; {i.start[1]:.0f}) — ({i.end[0]:.0f}; {i.end[1]:.0f})",
                f"{math.dist(i.start, i.end):.0f}",
                tables.fmt(i.bearing_mm),
                short(i.required_mm),
            )
            for i in design.bearing_issues
        ]
        headers = ("Кромка, мм", "Длина, мм", "Опора, мм", "Нужно, мм")
        section.blocks.append(Table("Кромки листов без места под саморез", headers, rows))
    return section


def _loads_section(project: Project, design: Design) -> Section:
    board, live = project.board, project.live_load_kpa
    live_gamma = gamma_f_live(live)
    rows = [
        (
            f"Лист ЦСП {short(board.thickness_mm)} мм, {short(board.density_kg_m3)} кг/м³",
            f"{num(project.board_load_kpa)} кПа",
            short(GAMMA_F_BOARD),
            f"{num(project.board_load_kpa * GAMMA_F_BOARD)} кПа",
            f"{SP20}, таблица 7.1",
        ),
        (
            "Временная на пол вне зон" if project.zones else "Временная на пол",
            f"{num(live, 2)} кПа",
            short(live_gamma),
            f"{num(live * live_gamma, 2)} кПа",
            f"{SP20}, п. 8.2.7",
        ),
    ]
    for zone in project.zones:
        x0, y0, x1, y1 = zone.rect
        p = zone.live_load_kpa
        rows.append(
            (
                f"Зона «{zone.title}» {x1 - x0:.0f} × {y1 - y0:.0f} мм",
                f"{num(p, 2)} кПа",
                short(gamma_f_live(p)),
                f"{num(p * gamma_f_live(p), 2)} кПа",
                PRESETS[zone.kind].source,
            )
        )
    sections = []
    for kind in KIND_TITLES:
        for member in design.members:
            if member.kind == kind and member.section not in sections:
                sections.append(member.section)
    for section in sections:
        weight = section.mass_kg_m * GRAVITY / 1e3
        rows.append(
            (
                f"Профиль {section.name}, {short(section.mass_kg_m)} кг/м",
                f"{num(weight)} кН/м",
                short(GAMMA_F_STEEL),
                f"{num(weight * GAMMA_F_STEEL)} кН/м",
                f"{SP20}, таблица 7.1",
            )
        )
    point = POINT_LOAD_N / 1e3
    rows.append(
        (
            "Сосредоточенная на площадке 10×10 см",
            f"{num(point, 2)} кН",
            short(GAMMA_F_POINT),
            f"{num(point * GAMMA_F_POINT, 2)} кН",
            f"{SP20}, п. 8.3.4, 8.3.5",
        )
    )
    headers = ("Нагрузка", "Нормативная", "γf", "Расчётная", "Основание")
    return Section("Нагрузки", [Table("Нагрузки", headers, rows)])


#: «Расчёт по …» для критерия шва.
_DATIVE = {"металл шва": "металлу шва", "граница сплавления": "металлу границы сплавления"}


def _weld_formula(weld) -> Formula:
    check = weld.check
    x, y = weld.point
    bf_rwf, bz_rwz = BETA_F * check.rwf_mpa, BETA_Z * check.rwz_mpa
    by_metal = check.governing == "металл шва"
    sign = "≤" if by_metal else ">"
    beta, rw, symbol = (
        (BETA_F, check.rwf_mpa, "βf·kf·lw·Rwf·γc")
        if by_metal
        else (BETA_Z, check.rwz_mpa, "βz·kf·lw·Rwz·γc")
    )
    u = check.utilization
    return Formula(
        f"Сварной шов в узле ({x:.0f}; {y:.0f}) (СП 16.13330.2017, формулы 176, 177)",
        (
            "Два угловых шва по стенкам примыкающей балки, ручная сварка",
            f"βf·Rwf = {short(BETA_F)}·{short(check.rwf_mpa)} = {short(bf_rwf)} {sign} βz·Rwz = "
            f"{short(BETA_Z)}·{short(check.rwz_mpa)} = {short(bz_rwz)} "
            f"— по {_DATIVE[check.governing]}",
            f"N / ({symbol}) = {num(check.force_kn, 2)}·10³ / ({short(beta)} · {check.leg_mm} · "
            f"{check.length_mm:.0f} · {short(rw)} · {short(GAMMA_C)}) = {verdict(u)}",
        ),
        u,
    )


def _welds_section(design: Design) -> Section | None:
    if not design.welds:
        return None
    weld = max(design.welds, key=lambda w: w.check.utilization)
    rows = [_texts(tables.weld_row(w)) for w in design.welds]
    return Section(
        "Сварные швы", [_weld_formula(weld), Table("Сварные швы", tables.WELD_COLUMNS, rows)]
    )


def _reactions_section(design: Design) -> Section:
    rows = [
        _texts(tables.pile_row(i, pile, reaction))
        for i, (pile, reaction) in enumerate(design.reactions_kn.items())
    ]
    total = sum(design.reactions_kn.values())
    return Section(
        "Реакции свай",
        [
            Paragraph(
                f"Расчётные вертикальные реакции, кН. Сумма {tables.fmt(total, 2)} кН равна полной "
                "расчётной нагрузке на каркас. Несущая способность свай не проверяется."
            ),
            Table("Реакции свай", tables.PILE_COLUMNS, rows),
        ],
    )


_LONG_SIDE = {"x": "длинной стороной вдоль X", "y": "длинной стороной вдоль Y"}


def _input_section(project: Project, design: Design) -> Section:
    contour = project.outline
    xs = [x for x, _ in contour.vertices]
    ys = [y for _, y in contour.vertices]
    board = project.board
    jumper = next((m.section.name for m in design.members if m.kind == "jumper"), "не нужны")
    offset = project.sheet_offset_mm
    rows = [
        ("Габариты плана", f"{max(xs) - min(xs):.0f} × {max(ys) - min(ys):.0f} мм"),
        ("Площадь", f"{tables.fmt(contour.area_mm2 / 1e6)} м²"),
        ("Вершин контура", str(len(contour.vertices))),
        ("Свай", str(len(design.piles))),
        ("Профиль периметра", f"{project.perimeter_section.name}, ГОСТ 30245-2003"),
        ("Внутренние балки", f"{project.internal_section.name}, ГОСТ 30245-2003"),
        ("Перемычки", jumper),
        ("Сталь", f"{project.steel.name}, Ry по СП 16.13330.2017, таблица В.3"),
        ("Электрод", f"{project.electrode}, ручная сварка"),
        (
            "Лист ЦСП",
            f"{short(board.length_mm)} × {short(board.width_mm)} × {short(board.thickness_mm)} мм, "
            f"{short(board.density_kg_m3)} кг/м³, ГОСТ 26816-2016",
        ),
        (
            "Раскладка листов",
            f"{_LONG_SIDE[project.sheet_long_side]}, смещение {short(offset[0])}; "
            f"{short(offset[1])} мм, зазор {short(project.sheet_gap_mm)} мм",
        ),
        (
            "Временная нагрузка вне зон" if project.zones else "Временная нагрузка",
            f"{num(project.live_load_kpa, 2)} кПа",
        ),
    ]
    if project.zones:
        rows.append(("Зон помещений", str(len(project.zones))))
    return Section("Исходные данные", [Table("Исходные данные", ("Параметр", "Значение"), rows)])


def plan_figure(design: Design, contour, zones=()) -> PlanFigure:
    failing = {id(m) for m in design.failing_members()}
    members = tuple(
        PlanMember(m.start, m.end, m.kind, tables.member_label(i), id(m) in failing)
        for i, m in enumerate(design.members)
    )
    piles = tuple((p, tables.pile_label(i)) for i, p in enumerate(design.reactions_kn))
    bearing = tuple((i.start, i.end) for i in design.bearing_issues)
    labelled = tuple(
        (z.rect, f"{z.title}, {num(z.live_load_kpa, 2)} кПа", z.cold_on_board) for z in zones
    )
    return PlanFigure(tuple(contour.vertices), members, piles, bearing, labelled)


def _scheme_section(project: Project, design: Design) -> Section:
    return Section(
        "Расчётная схема",
        [
            Paragraph(assumptions.SIMPLIFICATIONS[0]),
            Paragraph(assumptions.SIMPLIFICATIONS[1]),
            Paragraph(assumptions.SIMPLIFICATIONS[2]),
            plan_figure(design, project.outline, project.zones),
            Paragraph(
                "Марки элементов (Б…) и свай (С…) совпадают с таблицами записки и программы. "
                "Перемычки показаны тонкими линиями, непроходящие элементы — пунктиром, "
                "кромки листов без опоры под саморез — штрихом."
            ),
        ],
    )


def _limitations_section() -> Section:
    blocks: list = [Heading("Не проверяется")]
    blocks += [Paragraph(f"• {item}") for item in assumptions.NOT_CHECKED]
    blocks.append(Heading("Принятые упрощения"))
    blocks += [Paragraph(f"• {item}") for item in assumptions.SIMPLIFICATIONS]
    blocks.append(Paragraph(assumptions.DISCLAIMER))
    return Section("Что не проверяется и принятые упрощения", blocks)


def _summary_section(design: Design) -> Section:
    status, label, utilization = design_status(design)
    member = design.governing_member
    failing = len(design.failing_members())
    lines = [
        f"Итог: {label}.",
        f"Наибольшая загрузка {utilization:.0%}; самый загруженный элемент каркаса — "
        f"{KIND_TITLES[member.kind].lower()} {member.section.name}, "
        f"{design.governing_check.utilization:.0%}.",
        f"Не проходят элементов: {failing} из {len(design.members)}.",
    ]
    if design.bearing_issues:
        lines.append(
            f"Опирание листов: у {len(design.bearing_issues)} кромок не хватает плоской части "
            "полки под саморез (см. раздел «Лист ЦСП и перемычки»)."
        )
    if design.electrode_issue:
        lines.append(design.electrode_issue)
    lines += design.remarks
    return Section("Итог", [Paragraph(line) for line in lines])


def build_report(project: Project, design: Design, meta: ReportMeta) -> Report:
    sections = [
        _summary_section(design),
        _input_section(project, design),
        _loads_section(project, design),
        _scheme_section(project, design),
        _members_section(project, design),
        _boards_section(project, design),
        _welds_section(design),
        _reactions_section(design),
        _limitations_section(),
    ]
    return Report(meta, [s for s in sections if s is not None])
