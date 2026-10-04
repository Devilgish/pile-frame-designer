"""Smoke-тест окна: нарисовал контур мышью → сваи, каркас и итог проверки."""

import datetime
import json
import pathlib

import pytest
from pypdf import PdfReader
from PySide6.QtCore import QPointF, QSettings, Qt
from PySide6.QtGui import QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from pile_frame.app import MainWindow, _settings
from pile_frame.report import ReportMeta
from pile_frame.report_dialog import ReportDialog
from pile_frame.status import Status
from pile_frame.theme import DARK
from pile_frame.zones import Zone


def _drag(view, start_mm, end_mm):
    viewport = view.viewport()
    start = view.mapFromScene(QPointF(*start_mm))
    end = view.mapFromScene(QPointF(*end_mm))
    QTest.mousePress(viewport, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(viewport, end)
    QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, pos=end)


def test_drawing_a_rectangle_builds_frame_and_shows_check_result(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()

    # Контур чуть мимо сетки: привязка округляет до 6000 × 4000 мм.
    _drag(window.plan, (0, 0), (6040, 3980))

    assert window.plan.pile_count() == 12
    assert "Проходит" in window.result_text()


def test_switching_to_dark_theme_repaints_window_and_is_remembered(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    window.set_theme_mode("dark")

    assert window.palette().color(QPalette.ColorRole.Window).name().upper() == DARK.background
    reopened = MainWindow()
    qtbot.addWidget(reopened)
    assert reopened.theme_mode() == "dark"


def test_result_card_shows_status_as_text_and_icon(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    # Полка 120 мм: кромкам листов хватает места под саморез — замечаний нет.
    # Лист 28 мм загружен на 76 % — запас больше 10 %.
    window.internal_profile.setCurrentText("120×120×5")
    window.board_fields["thickness_mm"].set_value(28)

    _drag(window.plan, (0, 0), (6000, 4000))

    card = window.result_card
    assert card.status() is Status.OK
    assert card.status_text() == Status.OK.label
    assert not card.icon_pixmap().isNull()


L_POINTS = [(0, 0), (6000, 0), (6000, 2000), (3000, 2000), (3000, 4000), (0, 4000)]


def _click(view, point_mm):
    QTest.mouseClick(
        view.viewport(), Qt.MouseButton.LeftButton, pos=view.mapFromScene(QPointF(*point_mm))
    )


def test_clicking_vertices_draws_l_shaped_contour_with_auto_piles(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    window.set_tool("contour")

    for point in [*L_POINTS, L_POINTS[0]]:  # клик в первую вершину замыкает контур
        _click(window.plan, point)

    assert window.plan.pile_count() == 13


def test_dragging_a_pile_moves_it_and_ctrl_z_puts_it_back(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    _drag(window.plan, (0, 0), (4000, 4000))
    window.set_tool("piles")

    _drag(window.plan, (2000, 2000), (2000, 2500))
    assert (2000, 2500) in window.editor.piles

    window.activateWindow()
    qtbot.waitUntil(lambda: QApplication.activeWindow() is window, timeout=1000)
    QTest.keyClick(window.plan, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert (2000, 2000) in window.editor.piles
    assert (2000, 2500) not in window.editor.piles


def _window_with_rectangle(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    _drag(window.plan, (0, 0), (6000, 4000))
    return window


def _worst_beam(design) -> float:
    """Наибольшая загрузка балок по сваям и под стыками (без периметра и перемычек)."""
    return max(
        c.strength_utilization
        for m, c in zip(design.members, design.checks, strict=True)
        if m.kind == "beam"
    )


def test_choosing_heavier_internal_profile_recalculates_result(qtbot):
    window = _window_with_rectangle(qtbot)
    before = _worst_beam(window.last_design)

    window.internal_profile.setCurrentText("120×120×5")

    assert _worst_beam(window.last_design) < before


def test_zero_board_thickness_shows_error_next_to_field_and_keeps_last_result(qtbot):
    window = _window_with_rectangle(qtbot)
    field = window.board_fields["thickness_mm"]
    before = window.result_text()

    field.editor.clear()
    QTest.keyClicks(field.editor, "0")
    QTest.keyClick(field.editor, Qt.Key.Key_Return)

    assert field.issue_label.isVisibleTo(window)
    assert "больше нуля" in field.issue_label.text()
    assert window.result_text() == before


def test_rotating_sheets_changes_layout_and_rebuilds_frame(qtbot):
    # 6000 × 4000, листы 3200 × 1250 с зазором 3 мм.
    # Вдоль X: 2 столбца (кусок 2797) × 4 ряда (кусок 241) → 3 целых, 5 резаных.
    # Вдоль Y: 5 столбцов (кусок 988) × 2 ряда (кусок 797) → 4 целых, 6 резаных.
    window = _window_with_rectangle(qtbot)
    assert window.result_card.value("Листы") == "3 целых, 5 резаных"
    members_before = window.result_card.value("Не проходят").split(" из ")[1]

    window.sheet_long_side.setCurrentIndex(1)

    assert window.result_card.value("Листы") == "4 целых, 6 резаных"
    assert window.result_card.value("Не проходят").split(" из ")[1] != members_before


def test_results_table_sorts_by_utilization_and_row_click_selects_member(qtbot):
    window = _window_with_rectangle(qtbot)
    table = window.results.members
    design = window.last_design
    assert table.model().rowCount() == len(design.members)

    table.sortByColumn(window.results.UTILIZATION_COLUMN, Qt.SortOrder.DescendingOrder)
    top_member = window.results.member_index_at(0)
    assert design.checks[top_member].utilization == max(c.utilization for c in design.checks)

    row_rect = table.visualRect(table.model().index(2, 0))
    QTest.mouseClick(table.viewport(), Qt.MouseButton.LeftButton, pos=row_rect.center())

    assert window.plan.selected_member() == window.results.member_index_at(2)


def test_welds_and_assumptions_tabs_are_filled(qtbot):
    window = _window_with_rectangle(qtbot)

    assert window.results.welds.model().rowCount() == len(window.last_design.welds) > 0
    assert "кручени" in window.results.assumptions_text().lower()


def test_board_check_jumpers_and_bearing_are_shown(qtbot):
    # Лист 24 мм на полках 120×60: перемычки в ячейках, кромкам не хватает полки под саморез.
    window = _window_with_rectangle(qtbot)
    design = window.last_design
    jumpers = sum(1 for m in design.members if m.kind == "jumper")
    assert jumpers > 0 and design.bearing_issues

    card = window.result_card
    assert card.status() is Status.WARNING
    assert f"перемычек {jumpers}" in card.value("Лист ЦСП")
    assert card.value("Балка").startswith("перемычка 40×40×3")  # определяет перемычка
    assert f"опирание листов: {len(design.bearing_issues)}" in card.value("Замечания")
    assert window.results.boards.model().rowCount() == len(design.board_cells)
    assert "ЦСП" in window.results.assumptions_text()


def test_remarks_without_overload_are_titled_as_remarks_not_as_low_margin(qtbot):
    # Лист 28 мм, 4 кПа: наибольшая загрузка 76 % (лист), но кромкам 120×60 не хватает полки.
    window = _window_with_rectangle(qtbot)
    field = window.board_fields["thickness_mm"]
    field.editor.clear()
    QTest.keyClicks(field.editor, "28")
    QTest.keyClick(field.editor, Qt.Key.Key_Return)

    card = window.result_card
    assert window.last_design.bearing_issues
    assert card.status() is Status.WARNING
    assert card.status_text() == "Проходит, есть замечания"


def test_board_utilization_counts_in_the_card_status(qtbot):
    # Лист 24 мм на полках 120 мм (замечаний по опиранию нет): элементы каркаса загружены
    # меньше чем на 60 %, лист — на 95 % → запас меньше 10 %.
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    window.internal_profile.setCurrentText("120×120×5")
    _drag(window.plan, (0, 0), (6000, 4000))

    assert not window.last_design.bearing_issues
    assert window.result_card.status_text() == Status.WARNING.label


def _rows(view):
    model = view.model()
    return sorted(
        tuple(model.index(r, c).data() for c in range(model.columnCount()))
        for r in range(model.rowCount())
    )


def test_report_repeats_the_numbers_shown_in_the_window(qtbot):
    window = _window_with_rectangle(qtbot)
    meta = ReportMeta(object_name="Цех", author="Исполнитель", date=datetime.date(2026, 10, 3))

    report = window.build_report(meta)

    tables = {t.title: t for t in report.tables()}
    results = window.results
    for view, title in (
        (results.members, "Элементы каркаса"),
        (results.boards, "Ячейки листов ЦСП"),
        (results.piles, "Реакции свай"),
        (results.welds, "Сварные швы"),
    ):
        assert sorted(tables[title].rows) == _rows(view), title
    assert window.result_card.status_text() in report.summary()


def test_report_is_exported_to_pdf_from_the_menu(qtbot, tmp_path, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    assert not window.report_action.isEnabled()  # нечего выводить, пока нет контура

    _drag(window.plan, (0, 0), (6000, 4000))
    meta = ReportMeta(
        object_name="Кондитерский цех", author="Петров П. П.", date=datetime.date(2026, 10, 3)
    )
    target = tmp_path / "записка.pdf"
    monkeypatch.setattr("pile_frame.app.ReportDialog.ask", lambda *args: meta)
    monkeypatch.setattr(
        "pile_frame.app.QFileDialog.getSaveFileName", lambda *args, **kwargs: (str(target), "")
    )
    window.report_action.trigger()

    first_page = PdfReader(target).pages[0].extract_text()
    assert "Кондитерский цех" in first_page
    assert str(target) in window.status_message()


def test_report_dialog_fills_the_title_and_falls_back_to_defaults(qtbot, tmp_path):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    dialog = ReportDialog(None, settings)
    qtbot.addWidget(dialog)

    dialog.object_name.clear()
    dialog.author.setText("Сидоров С. С.")
    meta = dialog.meta()

    assert meta.object_name == "Заготовочное производство"
    assert meta.author == "Сидоров С. С."
    assert meta.date == datetime.date.today()


def _configured_window(qtbot):
    """Окно с Г-образным контуром и нестандартными исходными данными."""
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    for point in L_POINTS:
        _click(window.plan, point)
    _click(window.plan, L_POINTS[0])
    window.live_load.setValue(2.5)
    window.steel.setCurrentText("С255")
    window.sheet_long_side.setCurrentIndex(1)
    return window


def test_saved_project_reopens_with_the_same_result(qtbot, tmp_path):
    window = _configured_window(qtbot)
    before = window.result_text()
    path = tmp_path / "цех.karkas"

    window.save_to(path)
    window.new_project()
    assert window.last_design is None
    window.open_file(path)

    assert window.result_text() == before
    assert window.live_load.value() == 2.5
    assert window.steel.currentText() == "С255"
    assert window.windowTitle().startswith("цех")
    assert not window.isWindowModified()


def test_title_marks_unsaved_changes_until_saved_or_undone(qtbot, tmp_path):
    window = _configured_window(qtbot)
    assert window.isWindowModified()

    window.save_to(tmp_path / "план.karkas")
    assert not window.isWindowModified()

    window.live_load.setValue(3.0)
    assert window.isWindowModified()
    window.live_load.setValue(2.5)  # вернули как было — изменений нет
    assert not window.isWindowModified()


def test_file_actions_have_standard_shortcuts_and_save_as_adds_the_extension(
    qtbot, tmp_path, monkeypatch
):
    window = _configured_window(qtbot)
    shortcuts = {
        window.new_action: "Ctrl+N",
        window.open_action: "Ctrl+O",
        window.save_action: "Ctrl+S",
        window.save_as_action: "Ctrl+Shift+S",
    }
    for action, keys in shortcuts.items():
        assert action.shortcut().toString() == keys
    asked = []

    def save_dialog(*args, **kwargs):
        asked.append(args)
        return str(tmp_path / "цех"), ""

    monkeypatch.setattr("pile_frame.app.QFileDialog.getSaveFileName", save_dialog)
    window.save_action.trigger()  # файла ещё нет — спрашивает имя
    window.live_load.setValue(3.0)
    window.save_action.trigger()  # теперь сохраняет молча в тот же файл

    assert len(asked) == 1
    assert window.current_file == tmp_path / "цех.karkas"
    assert '"live_load_kpa": 3.0' in (tmp_path / "цех.karkas").read_text(encoding="utf-8")


def test_closing_with_unsaved_changes_asks_and_can_be_cancelled(qtbot, tmp_path, monkeypatch):
    window = _configured_window(qtbot)
    buttons = QMessageBox.StandardButton
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: buttons.Cancel)

    window.close()
    assert window.isVisible()  # передумал — окно осталось

    target = tmp_path / "перед выходом.karkas"
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: buttons.Save)
    monkeypatch.setattr(
        "pile_frame.app.QFileDialog.getSaveFileName", lambda *args, **kwargs: (str(target), "")
    )
    window.close()
    assert not window.isVisible()
    assert target.exists()


def test_broken_file_shows_a_message_and_keeps_the_current_project(qtbot, tmp_path, monkeypatch):
    window = _configured_window(qtbot)
    before = window.result_text()
    broken = tmp_path / "сломан.karkas"
    broken.write_text('{"app": "pile-frame-designer", "format_version": 1}', encoding="utf-8")
    messages = []
    monkeypatch.setattr(QMessageBox, "warning", lambda parent, title, text: messages.append(text))

    assert not window.open_file(broken)

    assert "повреждён" in messages[0]
    assert window.result_text() == before
    assert window.current_file is None


def test_recent_files_menu_reopens_a_saved_project(qtbot, tmp_path):
    window = _configured_window(qtbot)
    path = tmp_path / "недавний.karkas"
    window.save_to(path)
    window.new_project()

    actions = window.recent_menu.actions()
    assert [a.text() for a in actions] == ["недавний.karkas"]
    actions[0].trigger()

    assert window.current_file == path
    assert window.live_load.value() == 2.5


def test_opening_a_project_reports_a_changed_result(qtbot, tmp_path, monkeypatch):
    window = _configured_window(qtbot)
    path = tmp_path / "старый.karkas"
    window.save_to(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["summary"]["max_utilization"] = 0.1  # так выглядит проект из старой версии
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda parent, title, text: shown.append(text))

    window.open_file(path)

    assert "отличаются от сохранённых" in shown[0]


def test_opened_pile_step_is_used_for_the_next_contour(qtbot, tmp_path):
    # Проект с шагом свай 3000. После открытия новый контур 6000 × 4000 получает сваи
    # по осям x 0/3000/6000 и y 0/2000/4000 — 9 штук (при шаге 2000 было бы 12).
    saved = _configured_window(qtbot)
    saved.pile_step.setValue(3000)
    path = tmp_path / "шаг.karkas"
    saved.save_to(path)
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()

    window.open_file(path)
    _drag(window.plan, (0, 0), (6000, 4000))

    assert window.pile_step.value() == 3000
    assert window.plan.pile_count() == 9


def test_open_action_asks_for_a_file(qtbot, tmp_path, monkeypatch):
    window = _configured_window(qtbot)
    path = tmp_path / "через меню.karkas"
    window.save_to(path)
    window.new_project()
    monkeypatch.setattr(
        "pile_frame.app.QFileDialog.getOpenFileName", lambda *args, **kwargs: (str(path), "")
    )

    window.open_action.trigger()

    assert window.current_file == path


@pytest.mark.parametrize("content", [None, b"\xff\xfe\x00binary"], ids=["нет файла", "не текст"])
def test_unreadable_file_shows_a_message(qtbot, tmp_path, monkeypatch, content):
    window = MainWindow()
    qtbot.addWidget(window)
    path = tmp_path / "файл.karkas"
    if content is not None:
        path.write_bytes(content)
    messages = []
    monkeypatch.setattr(QMessageBox, "warning", lambda parent, title, text: messages.append(text))

    assert not window.open_file(path)
    assert str(path) in messages[0]


def test_recent_file_that_was_deleted_is_reported_and_removed(qtbot, tmp_path, monkeypatch):
    window = _configured_window(qtbot)
    path = tmp_path / "удалённый.karkas"
    window.save_to(path)
    path.unlink()
    messages = []
    monkeypatch.setattr(QMessageBox, "warning", lambda parent, title, text: messages.append(text))

    window.recent_menu.actions()[0].trigger()

    assert "перемещён или удалён" in messages[0]
    assert window.recent_menu.actions() == []


def test_saving_to_a_folder_shows_a_message(qtbot, tmp_path, monkeypatch):
    window = _configured_window(qtbot)
    messages = []
    monkeypatch.setattr(QMessageBox, "warning", lambda parent, title, text: messages.append(text))

    assert not window.save_to(tmp_path)  # папка вместо файла
    assert window.isWindowModified()
    assert messages


def test_opened_gost_board_format_is_selected_in_the_list(qtbot):
    # В эталонном проекте лист 3600 × 1200 — формат по ГОСТ, а не «свой размер».
    window = MainWindow()
    qtbot.addWidget(window)

    window.open_file(pathlib.Path(__file__).with_name("data") / "project_v1.karkas")

    assert window.board_format.currentText() == "3600 × 1200 мм"
    assert not window.board_fields["length_mm"].editor.isEnabled()


def _window_with_zone(qtbot, kind="storage", rect=((0, 0), (2000, 2000))):
    window = _window_with_rectangle(qtbot)
    window.set_tool("zones")
    window.zones_panel.new_kind.setCurrentIndex(window.zones_panel.new_kind.findData(kind))
    _drag(window.plan, *rect)
    return window


def test_zone_tool_draws_a_zone_with_its_preset_and_recalculates(qtbot):
    window = _window_with_rectangle(qtbot)
    before = max(window.last_design.reactions_kn.values())

    window.set_tool("zones")
    window.zones_panel.new_kind.setCurrentIndex(window.zones_panel.new_kind.findData("storage"))
    _drag(window.plan, (0, 0), (2000, 2000))

    assert window.last_project.zones == (Zone("storage", (0.0, 0.0, 2000.0, 2000.0), 5.0),)
    assert max(window.last_design.reactions_kn.values()) > before
    note = window.zones_panel.note.text()
    assert "по аналогии" in note and "технолог" in note


def test_zone_kind_load_and_cold_room_option_are_edited_in_the_panel(qtbot):
    window = _window_with_zone(qtbot)
    row = window.zones_panel.rows[0]
    assert not row.on_board.isVisibleTo(window)  # вариант камеры — только у камеры

    row.kind.setCurrentIndex(row.kind.findData("cold"))
    row = window.zones_panel.rows[0]
    assert row.on_board.isVisibleTo(window)
    row.load.setValue(6.5)
    window.zones_panel.rows[0].on_board.setChecked(True)

    assert window.last_project.zones[0] == Zone(
        "cold", (0.0, 0.0, 2000.0, 2000.0), 6.5, cold_on_board=True
    )
    assert "камера на ЦСП" in window.result_card.value("Замечания")


def test_overlapping_zone_is_refused_with_an_explanation(qtbot):
    window = _window_with_zone(qtbot)

    _drag(window.plan, (1000, 1000), (3000, 3000))

    assert len(window.last_project.zones) == 1
    assert "пересекается" in window.status_message()


def test_zone_is_removed_from_the_panel(qtbot):
    window = _window_with_zone(qtbot)

    window.zones_panel.rows[0].remove.click()

    assert window.last_project.zones == ()
    assert window.zones_panel.rows == []


def test_zones_are_saved_and_reopened(qtbot, tmp_path):
    window = _window_with_zone(qtbot, "pastry", ((2000, 0), (4000, 2000)))
    path = tmp_path / "зоны.karkas"
    window.save_to(path)
    window.new_project()

    window.open_file(path)

    assert window.last_project.zones == (Zone("pastry", (2000.0, 0.0, 4000.0, 2000.0), 2.0),)
    assert len(window.zones_panel.rows) == 1


def _select_equipment(window, name):
    combo = window.equipment_panel.new_type
    combo.setCurrentIndex(combo.findText(name))


def _window_with_mixer(qtbot):
    window = _window_with_rectangle(qtbot)
    window.set_tool("equipment")
    _select_equipment(window, "Тестомес спиральный 60 л")
    _click(window.plan, (1000, 1000))
    return window


def test_equipment_tool_places_the_chosen_item_and_shows_its_load_separately(qtbot):
    window = _window_with_mixer(qtbot)

    (item,) = window.last_project.equipment
    assert item.type.name == "Тестомес спиральный 60 л" and item.centre == (1000.0, 1000.0)
    # (1,05·200 + 1,2·50)·9,81 = 2,65 кН — отдельной строкой в карточке.
    assert window.result_card.value("Оборудование") == "1 шт., расчётная 2,65 кН"
    note = window.equipment_panel.note.text()
    assert "внутри контура" in note and "зон" in note


def test_equipment_is_dragged_turned_with_r_and_removed_with_right_click(qtbot):
    window = _window_with_mixer(qtbot)

    _drag(window.plan, (1000, 1000), (3000, 2000))
    assert window.last_project.equipment[0].centre == (3000.0, 2000.0)
    QTest.keyClick(window.plan, Qt.Key.Key_R)
    assert window.last_project.equipment[0].rotated
    QTest.mouseClick(
        window.plan.viewport(),
        Qt.MouseButton.RightButton,
        pos=window.plan.mapFromScene(QPointF(3000, 2000)),
    )
    assert window.last_project.equipment == ()


def test_equipment_outside_the_contour_is_refused_with_a_reason(qtbot):
    window = _window_with_mixer(qtbot)

    _click(window.plan, (5900, 2000))

    assert len(window.last_project.equipment) == 1
    assert "внутри контура" in window.status_message()


def test_equipment_panel_turns_and_removes_items(qtbot):
    window = _window_with_mixer(qtbot)
    row = window.equipment_panel.rows[0]

    row.rotate.click()
    assert window.last_project.equipment[0].rotated
    window.equipment_panel.rows[0].remove.click()
    assert window.last_project.equipment == ()


def test_own_equipment_is_added_to_the_library_and_remembered(qtbot):
    window = _window_with_rectangle(qtbot)
    dialog = window.make_library_dialog()
    qtbot.addWidget(dialog)

    dialog.fields["name"].setText("Печь подовая")
    for key, value in (
        ("length_mm", 1200),
        ("width_mm", 1000),
        ("own_kg", 400),
        ("content_kg", 60),
    ):
        dialog.fields[key].setValue(value)
    dialog.add_button.click()

    assert window.equipment_library.get("Печь подовая").own_kg == 400
    window.equipment_panel.refresh_library()
    assert window.equipment_panel.new_type.findText("Печь подовая") >= 0
    assert "Печь подовая" in str(_settings().value("equipment"))


def test_equipment_is_saved_and_reopened(qtbot, tmp_path):
    window = _window_with_mixer(qtbot)
    path = tmp_path / "оборудование.karkas"
    window.save_to(path)
    window.new_project()

    window.open_file(path)

    assert window.last_project.equipment[0].centre == (1000.0, 1000.0)
    assert len(window.equipment_panel.rows) == 1


def test_turn_that_does_not_fit_is_explained_and_library_errors_are_shown(qtbot):
    window = _window_with_rectangle(qtbot)
    window.set_tool("equipment")
    _select_equipment(window, "Тестораскаточная машина")
    _click(window.plan, (3000, 500))  # 2000 × 800 у нижней стены — развернуть некуда

    window.equipment_panel.rows[0].rotate.click()

    assert not window.last_project.equipment[0].rotated
    assert "внутри контура" in window.status_message()
    dialog = window.make_library_dialog()
    qtbot.addWidget(dialog)
    dialog.add_button.click()  # пустая форма
    assert "название" in dialog.issues.text()
