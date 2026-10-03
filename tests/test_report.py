"""Расчётная записка: формулы с подставленными числами, нагрузки, таблицы."""

import datetime

import pytest

from pile_frame import assumptions
from pile_frame.design import Project, analyze
from pile_frame.report import Heading, PlanFigure, ReportMeta, build_report
from pile_frame.zones import Zone

META = ReportMeta(object_name="Цех", author="Исполнитель", date=datetime.date(2026, 10, 3))


def _square_report():
    # Квадрат 2000 × 2000 на угловых сваях, только периметр 120×120×5 (см. test_design):
    # M = 1,8128 кН·м, Q = 2,7644 кН.
    project = Project(
        width_mm=2000, length_mm=2000, pile_step_mm=2000, live_load_kpa=4.0, sheet_joints=False
    )
    return build_report(project, analyze(project), META)


def _formula(report, title):
    found = [f for f in report.formulas() if f.title.startswith(title)]
    assert len(found) == 1, [f.title for f in report.formulas()]
    return found[0]


def test_bending_check_shows_formula_41_with_substituted_values():
    # M / (Wx·Ry·γc) = 1,813·10⁶ / (80,88·10³ · 240 · 1) = 0,093.
    formula = _formula(_square_report(), "Прочность при изгибе")

    assert "формула 41" in formula.title
    assert "1,813·10⁶ / (80,88·10³ · 240 · 1) = 0,093 ≤ 1" in formula.lines
    assert formula.utilization == pytest.approx(0.0934, abs=5e-4)


def test_shear_check_shows_formula_42_with_both_webs():
    # S = 120·5·57,5 + 2·5·55·27,5 = 49 625 мм³, tw = 2·5 = 10 мм, Rs = 0,58·240 = 139,2.
    # Q·S / (Ix·tw·Rs·γc) = 2,764·10³ · 49 625 / (485,3·10⁴ · 10 · 139,2 · 1) = 0,020.
    formula = _formula(_square_report(), "Прочность при срезе")

    assert "формула 42" in formula.title
    assert "Rs = 0,58·Ry = 0,58·240 = 139,2 Н/мм²" in formula.lines
    assert "2,764·10³ · 49 625 / (485,3·10⁴ · 10 · 139,2 · 1) = 0,020 ≤ 1" in formula.lines
    assert formula.utilization == pytest.approx(0.0203, abs=2e-4)


def test_deflection_check_names_the_span_used_for_the_limit():
    # Нормативные: треугольник w = (0,306 + 0,35·4)·1 м = 1,706 кН/м, вес g = 0,1722 кН/м.
    # f = w·L⁴/(120·EI) + 5·g·L⁴/(384·EI) = 0,228 + 0,036 = 0,263 мм, EI = 2,06e5·485,3e4.
    # Ячейка свай 2000 → fu = 8,33 + (20 − 8,33)·0,5 = 14,17 мм (таблица Д.1).
    formula = _formula(_square_report(), "Прогиб")

    assert "Д.1" in formula.title
    assert "fu для l = 2000 мм: 14,17 мм" in formula.lines
    assert "f / fu = 0,26 / 14,17 = 0,019 ≤ 1" in formula.lines


def test_web_and_flange_stability_show_slenderness_with_substituted_values():
    # λ = (120 − 2·5)/5 · √(240 / 206 000) = 22 · 0,03413 = 0,751.
    # Стенка: предел 3,5 → 0,215. Пояс: σc = 1,8128e6 / 80 880 = 22,41 Н/мм²,
    # предел 1,5·√(240 / 22,41) = 4,908 → 0,153.
    report = _square_report()
    web = _formula(report, "Местная устойчивость стенки")
    flange = _formula(report, "Местная устойчивость поясного листа")

    assert "λw = (120 − 2·5) / 5 · √(240 / 206 000) = 0,751" in web.lines
    assert "λw / 3,5 = 0,751 / 3,5 = 0,215 ≤ 1" in web.lines
    assert "σc = M / Wx = 1,813·10⁶ / 80,88·10³ = 22,41 Н/мм²" in flange.lines
    assert "λf / (1,5·√(Ry / σc)) = 0,751 / (1,5·√(240 / 22,41)) = 0,153 ≤ 1" in flange.lines


def test_failing_check_is_written_as_exceeding_the_limit():
    # 2000 × 6000 на угловых сваях (test_design): M = 5,16729·104/24 + 0,18077·36/8 = 23,205 кН·м;
    # σ = 23,205e6 / 80 880 = 286,9 > 240 → 1,195.
    project = Project(
        width_mm=2000, length_mm=6000, pile_step_mm=6000, live_load_kpa=4.0, sheet_joints=False
    )
    formula = _formula(build_report(project, analyze(project), META), "Прочность при изгибе")

    assert formula.lines[-1].endswith("= 1,195 > 1 — не проходит")


def _table(report, title):
    found = [t for t in report.tables() if t.title == title]
    assert len(found) == 1, [t.title for t in report.tables()]
    return found[0]


def test_loads_table_gives_normative_and_design_values_with_clauses():
    # ЦСП 24 мм, 1300 кг/м³: 0,306 кПа · 1,2 = 0,367; временная 4 кПа ≥ 2 → γf 1,2 → 4,80;
    # профиль 120×120×5: 17,55·9,81 = 0,172 кН/м · 1,05 = 0,181; сосредоточенная 1,5 · 1,2 = 1,8.
    rows = _table(_square_report(), "Нагрузки").rows

    assert (
        "Лист ЦСП 24 мм, 1300 кг/м³",
        "0,306 кПа",
        "1,2",
        "0,367 кПа",
        "СП 20.13330.2016, таблица 7.1",
    ) in rows
    assert ("Временная на пол", "4,00 кПа", "1,2", "4,80 кПа", "СП 20.13330.2016, п. 8.2.7") in rows
    assert (
        "Профиль 120×120×5, 17,55 кг/м",
        "0,172 кН/м",
        "1,05",
        "0,181 кН/м",
        "СП 20.13330.2016, таблица 7.1",
    ) in rows
    assert (
        "Сосредоточенная на площадке 10×10 см",
        "1,50 кН",
        "1,2",
        "1,80 кН",
        "СП 20.13330.2016, п. 8.3.4, 8.3.5",
    ) in rows


def test_light_live_load_gets_the_higher_factor_in_the_loads_table():
    project = Project(
        width_mm=2000, length_mm=2000, pile_step_mm=2000, live_load_kpa=1.5, sheet_joints=False
    )
    rows = _table(build_report(project, analyze(project), META), "Нагрузки").rows

    assert ("Временная на пол", "1,50 кПа", "1,3", "1,95 кПа", "СП 20.13330.2016, п. 8.2.7") in rows


def _wide_cells_report():
    # 6400 × 2500, сваи через 3200, лист 24 мм: по 4 перемычки, пролёт листа 640
    # (см. test_design_jumpers).
    project = Project(width_mm=6400, length_mm=2500, pile_step_mm=3200, live_load_kpa=4.0)
    return build_report(project, analyze(project), META)


def test_board_checks_are_written_out_for_the_governing_cell():
    # Равномерная: q = 1,2·0,306 + 1,2·4,00 = 5,167 кПа; M = 5,167e-3·640²/8 = 264,6 Н·мм/мм;
    # R = 0,65·9/1,3 = 4,50; 264,6 / (96·4,50) = 0,612.
    # Сосредоточенная: c = 100/√π = 56,4; M = 1800/(4π)·[1,3·ln(1280/(π·56,4)) + 1] + 18,8
    # = 143,24·3,570 + 18,8 = 530,2; R = 0,85·9/1,3 = 5,88; 530,2 / (96·5,88) = 0,939.
    # Прогиб: EI = 4500/3,25·24³/12 = 1,595·10⁶; f = 2,34 мм; fu = 640/120 = 5,33 → 0,438.
    report = _wide_cells_report()
    uniform = _formula(report, "Лист ЦСП: равномерная нагрузка")
    point = _formula(report, "Лист ЦСП: сосредоточенная нагрузка")
    deflection = _formula(report, "Лист ЦСП: прогиб")

    assert "M = q·l² / 8 = 5,167·10⁻³ · 640² / 8 = 264,6 Н·мм/мм" in uniform.lines
    assert "R = kmod·Rн / γm = 0,65·9 / 1,3 = 4,50 Н/мм²" in uniform.lines
    assert "M / (W·R) = 264,6 / (96 · 4,50) = 0,612 ≤ 1" in uniform.lines
    assert "M / (W·R) = 530,2 / (96 · 5,88) = 0,939 ≤ 1" in point.lines
    assert "f / fu = 2,34 / 5,33 = 0,438 ≤ 1" in deflection.lines


def test_governing_weld_is_written_out_with_formula_176():
    # Узел (3200; 1251,5): балка 120×60×4 под стыком на балке по сваям. kf = 4, lw = 2·(120 − 10)
    # = 220 мм, Rwf = 200 (Э46), Rwz = 0,45·370 = 166,5 (С245). βf·Rwf = 140 ≤ βz·Rwz = 166,5 →
    # по металлу шва (176). Сила N — из расчёта грильяжа, 21,62 кН: 21 624 / 123 200 = 0,176.
    formula = _formula(_wide_cells_report(), "Сварной шов")

    assert "(3200; 1252)" in formula.title
    assert "βf·Rwf = 0,7·200 = 140 ≤ βz·Rwz = 1·166,5 = 166,5 — по металлу шва" in formula.lines
    assert "N / (βf·kf·lw·Rwf·γc) = 21,62·10³ / (0,7 · 4 · 220 · 200 · 1) = 0,176 ≤ 1" in (
        formula.lines
    )


def test_report_has_all_sections_and_ends_with_what_is_not_checked():
    report = _wide_cells_report()

    assert [s.title for s in report.sections] == [
        "Итог",
        "Исходные данные",
        "Нагрузки",
        "Расчётная схема",
        "Проверки элементов каркаса",
        "Лист ЦСП и перемычки",
        "Сварные швы",
        "Реакции свай",
        "Что не проверяется и принятые упрощения",
    ]
    last = "\n".join(b.text for b in report.sections[-1].blocks if hasattr(b, "text"))
    for item in assumptions.NOT_CHECKED:
        assert item in last
    assert assumptions.DISCLAIMER in last


def test_plan_figure_labels_members_and_piles_like_the_tables():
    report = _wide_cells_report()
    figure = next(b for s in report.sections for b in s.blocks if isinstance(b, PlanFigure))
    members = _table(report, "Элементы каркаса").rows
    piles = _table(report, "Реакции свай").rows

    assert [m.label for m in figure.members] == [row[0] for row in members]
    assert [label for _, label in figure.piles] == [row[0] for row in piles]
    assert any(m.kind == "jumper" for m in figure.members)


def test_sheet_edges_without_screw_room_are_listed():
    # Лист 24 мм на 120×60: 8 кромок с опорой 19–22 мм при нужных 25 (test_design_bearing).
    report = _wide_cells_report()
    rows = _table(report, "Кромки листов без места под саморез").rows

    assert len(rows) == 8
    assert {row[-1] for row in rows} == {"25"}
    assert {row[-2] for row in rows} == {"19,0", "20,5", "22,0"}


def test_each_governing_element_gets_a_heading_with_its_mark_and_length():
    # Квадрат: четыре одинаковые стороны периметра 2000 мм, самая загруженная — первая (Б1).
    headings = [
        b.text for s in _square_report().sections for b in s.blocks if isinstance(b, Heading)
    ]

    assert "Балка периметра Б1: 120×120×5, длина 2000 мм" in headings


def test_summary_repeats_the_electrode_remark():
    # Э42 для С245 не выполняет п. 14.1.8 (см. test_welds).
    project = Project(
        width_mm=6400, length_mm=2500, pile_step_mm=3200, live_load_kpa=4.0, electrode="Э42"
    )

    assert "14.1.8" in build_report(project, analyze(project), META).summary()


def _zoned_report():
    project = Project(
        width_mm=6000,
        length_mm=4000,
        pile_step_mm=2000,
        live_load_kpa=1.5,
        zones=(
            Zone("storage", (0.0, 0.0, 2000.0, 2000.0), 5.0),
            Zone("cold", (2000.0, 0.0, 4000.0, 2000.0), 5.0, cold_on_board=True),
        ),
    )
    return build_report(project, analyze(project), META)


def test_zones_are_listed_in_the_loads_table_with_their_sources():
    # Вне зон 1,5 кПа · 1,3 = 1,95; склад 5,0 · 1,2 = 6,00.
    rows = _table(_zoned_report(), "Нагрузки").rows

    assert (
        "Временная на пол вне зон",
        "1,50 кПа",
        "1,3",
        "1,95 кПа",
        "СП 20.13330.2016, п. 8.2.7",
    ) in rows
    storage = next(r for r in rows if r[0].startswith("Зона «Склад»"))
    assert storage[1:4] == ("5,00 кПа", "1,2", "6,00 кПа")
    assert "СНиП 2.01.07-85" in storage[4] and "уточнить у технолога" in storage[4]


def test_cold_room_on_the_board_is_in_the_summary_and_zones_are_on_the_plan():
    report = _zoned_report()
    figure = next(b for s in report.sections for b in s.blocks if isinstance(b, PlanFigure))

    assert "промерзание" in report.summary()
    assert [label for _, label, _ in figure.zones] == [
        "Склад, 5,00 кПа",
        "Холодильная камера, 5,00 кПа",
    ]
    assert [warn for _, _, warn in figure.zones] == [False, True]


def test_input_data_name_the_live_load_outside_zones_and_count_the_zones():
    rows = dict(_table(_zoned_report(), "Исходные данные").rows)

    assert rows["Временная нагрузка вне зон"] == "1,50 кПа"
    assert rows["Зон помещений"] == "2"
