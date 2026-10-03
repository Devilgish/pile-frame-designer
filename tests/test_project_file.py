"""Файл проекта: сохранил → открыл → тот же проект и тот же расчёт; ошибки и версии формата."""

import json
import pathlib

import pytest

from pile_frame.boards import BoardSpec
from pile_frame.contour import Contour
from pile_frame.design import Project, analyze, auto_piles
from pile_frame.materials import STEELS
from pile_frame.project_file import ProjectFileError, load_text, save_text, summary_note
from pile_frame.sections import ProfileCatalog, Section, TUBE_120x60x4

L_SHAPE = Contour.from_points(
    [(0, 0), (6000, 0), (6000, 2000), (3000, 2000), (3000, 4000), (0, 4000)]
)


def _project(**changes):
    piles = auto_piles(L_SHAPE, 2000)
    piles[1] = (1750.0, 0.0)  # свая сдвинута вручную
    params = {
        "contour": L_SHAPE,
        "piles": tuple(piles),
        "pile_step_mm": 2000,
        "live_load_kpa": 2.5,
        "perimeter_section": TUBE_120x60x4,
        "steel": STEELS["С255"],
        "electrode": "Э50",
        "board": BoardSpec(length_mm=3600, width_mm=1200, thickness_mm=28, density_kg_m3=1250),
        "sheet_long_side": "y",
        "sheet_offset_mm": (300.0, 150.0),
        "sheet_gap_mm": 4.0,
    }
    return Project(**{**params, **changes})


def test_saved_project_opens_with_the_same_inputs_and_the_same_results():
    project = _project()
    design = analyze(project)

    loaded = load_text(save_text(project, "Кондитерский цех", design), ProfileCatalog())

    assert loaded.project == project
    assert loaded.object_name == "Кондитерский цех"
    reopened = analyze(loaded.project)
    assert reopened.members == design.members
    assert reopened.checks == design.checks
    assert reopened.reactions_kn == design.reactions_kn
    assert reopened.board_cells == design.board_cells
    assert loaded.notes == []


def _saved(**changes):
    """Текст сохранённого проекта с изменёнными полями JSON (вложенность через «__»)."""
    data = json.loads(save_text(_project(), "Цех"))
    for path, value in changes.items():
        target = data
        *parents, last = path.split("__")
        for key in parents:
            target = target[key]
        if value is DELETE:
            del target[last]
        else:
            target[last] = value
    return json.dumps(data, ensure_ascii=False)


DELETE = object()


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("это не JSON", "не является файлом проекта"),
        ('{"name": "чужой файл"}', "не является файлом проекта"),
        ("[1, 2, 3]", "не является файлом проекта"),
        (lambda: _saved(format_version=2), "создан более новой версией программы"),
        (lambda: _saved(board=DELETE), "повреждён"),
        (lambda: _saved(plan__piles="abc"), "повреждён"),
        (lambda: _saved(frame__steel="С999"), "сталь «С999»"),
        (lambda: _saved(plan__contour=[[0, 0], [100, 100], [0, 100]]), "контур"),
        (lambda: _saved(format_version=DELETE), "версия формата"),
        (lambda: _saved(frame__electrode="Э99"), "электрод «Э99»"),
        (lambda: _saved(sheets__long_side="z"), "повреждён"),
        (lambda: _saved(board__thickness_mm=0), "Толщина листа"),
        (lambda: _saved(plan__pile_step_mm=0), "повреждён"),
        (lambda: _saved(loads__live_load_kpa=-1), "повреждён"),
    ],
    ids=[
        "не JSON",
        "чужой JSON",
        "не объект",
        "новее программы",
        "нет раздела",
        "неверный тип",
        "неизвестная сталь",
        "неверный контур",
        "нет версии",
        "неизвестный электрод",
        "неверная ориентация",
        "нулевая толщина",
        "нулевой шаг свай",
        "отрицательная нагрузка",
    ],
)
def test_broken_or_foreign_file_gives_a_clear_message(text, message):
    text = text() if callable(text) else text

    with pytest.raises(ProjectFileError, match=message):
        load_text(text, ProfileCatalog())


DATA = pathlib.Path(__file__).with_name("data")


def test_project_saved_by_format_version_1_still_opens():
    # Файл сохранён программой с форматом 1 и лежит в репозитории: если формат изменится,
    # этот тест требует миграцию, а не молчаливую поломку старых проектов.
    text = (DATA / "project_v1.karkas").read_text(encoding="utf-8")

    loaded = load_text(text, ProfileCatalog())

    assert json.loads(text)["format_version"] == 1
    assert loaded.project == _project()


def test_old_format_is_upgraded_step_by_step(monkeypatch):
    # Формат 1 → 2: нагрузка переименована; 2 → 3: нагрузка задаётся в Па.
    def to_2(data):
        data["loads"] = {"live_kpa": data["loads"]["live_load_kpa"]}
        return data

    def to_3(data):
        data["loads"] = {"live_load_kpa": data["loads"]["live_kpa"]}
        data["loads"]["live_load_kpa"] *= 2  # условная правка, видимая в результате
        return data

    text = save_text(_project(live_load_kpa=1.5), "Цех")
    monkeypatch.setattr("pile_frame.project_file.FORMAT_VERSION", 3)
    monkeypatch.setattr("pile_frame.project_file.MIGRATIONS", {1: to_2, 2: to_3})

    assert load_text(text, ProfileCatalog()).project.live_load_kpa == 3.0


CUSTOM = {
    "name": "Труба 100×50×3",
    "height_mm": 100,
    "width_mm": 50,
    "thickness_mm": 3,
    "mass_kg_m": 6.6,
    "area_cm2": 8.41,
    "ix_cm4": 107.0,
    "wx_cm3": 21.4,
}


def _custom_section(**changes):
    return Section(**{**CUSTOM, **changes})


def test_custom_profile_travels_with_the_file_and_joins_the_catalog():
    text = save_text(_project(internal_section=_custom_section()), "Цех")
    catalog = ProfileCatalog()  # на другом компьютере своего профиля нет

    loaded = load_text(text, catalog)

    assert loaded.project.internal_section == _custom_section()
    assert catalog.get("Труба 100×50×3") == _custom_section()
    assert loaded.notes == ["Профиль «Труба 100×50×3» добавлен в справочник из файла."]


def test_same_custom_profile_in_the_catalog_gives_no_remark():
    catalog = ProfileCatalog((_custom_section(),))

    loaded = load_text(save_text(_project(internal_section=_custom_section()), "Цех"), catalog)

    assert loaded.project.internal_section == _custom_section()
    assert loaded.notes == []


def test_conflicting_profile_name_keeps_the_file_data_under_a_new_name():
    # В справочнике тот же «Труба 100×50×3», но с другой массой: данные файла не теряются.
    catalog = ProfileCatalog((_custom_section(mass_kg_m=7.0),))

    loaded = load_text(save_text(_project(internal_section=_custom_section()), "Цех"), catalog)

    renamed = _custom_section(name="Труба 100×50×3 (из файла)")
    assert loaded.project.internal_section == renamed
    assert catalog.get("Труба 100×50×3 (из файла)") == renamed
    assert catalog.get("Труба 100×50×3").mass_kg_m == 7.0
    assert "из файла" in loaded.notes[0] and "отличается" in loaded.notes[0]


def test_reopened_project_reproduces_the_saved_result_summary():
    project = _project()
    loaded = load_text(save_text(project, "Цех", analyze(project)), ProfileCatalog())

    assert loaded.summary is not None
    assert summary_note(loaded.summary, analyze(loaded.project)) is None


def test_changed_result_after_reopening_is_reported():
    # Сводку в файле «испортили»: так выглядит проект, посчитанный старой версией программы.
    project = _project()
    design = analyze(project)
    data = json.loads(save_text(project, "Цех", design))
    data["summary"]["max_utilization"] = 0.5
    data["summary"]["total_reaction_kn"] += 10
    data["summary"]["members"] += 1

    loaded = load_text(json.dumps(data, ensure_ascii=False), ProfileCatalog())
    note = summary_note(loaded.summary, analyze(loaded.project))

    assert note.startswith("Результаты расчёта отличаются от сохранённых")
    assert "наибольшая загрузка 50%" in note
    assert "сумма реакций свай" in note
    assert "элементов" in note


def test_frame_on_piles_only_mode_is_kept():
    project = _project(sheet_joints=False)

    assert load_text(save_text(project, "Цех"), ProfileCatalog()).project == project
