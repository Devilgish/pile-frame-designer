"""Расчётная записка в PDF: титул, содержание, нумерация, текст читается из файла."""

import datetime

import pytest
from pypdf import PdfReader

from pile_frame import assumptions
from pile_frame.design import Project, analyze
from pile_frame.pdf import write_pdf
from pile_frame.report import ReportMeta, build_report

META = ReportMeta(
    object_name="Заготовочный цех", author="Иванов И. И.", date=datetime.date(2026, 10, 3)
)


@pytest.fixture(scope="module")
def pages(tmp_path_factory):
    # 6400 × 2500, сваи через 3200, лист 24 мм: есть перемычки, швы и замечания по опиранию.
    project = Project(width_mm=6400, length_mm=2500, pile_step_mm=3200, live_load_kpa=4.0)
    path = tmp_path_factory.mktemp("pdf") / "записка.pdf"
    write_pdf(build_report(project, analyze(project), META), path)
    return [page.extract_text() for page in PdfReader(path).pages]


def _flat(text):
    return " ".join(text.split())


def test_title_page_names_the_object_author_and_date(pages):
    title = _flat(pages[0])

    assert "Заготовочный цех" in title
    assert "Иванов И. И." in title
    assert "Расчётная записка" in title
    assert "03.10.2026" in title
    assert "Предпроектная проработка" in title


def test_contents_list_numbered_sections_with_pages(pages):
    contents = _flat(pages[1])

    assert "Содержание" in contents
    assert "1. Итог" in contents
    assert "9. Что не проверяется и принятые упрощения" in contents


def test_every_page_is_numbered_out_of_the_total(pages):
    total = len(pages)

    assert total > 3
    for number, text in enumerate(pages, start=1):
        assert f"Лист {number} из {total}" in _flat(text)


def test_formulas_tables_and_disclaimer_are_in_the_text(pages):
    text = _flat(" ".join(pages))

    assert "264,6 / (96 · 4,50) = 0,612 ≤ 1" in text
    assert "Реакции свай" in text
    assert "С1" in text and "Б1" in text
    assert _flat(assumptions.DISCLAIMER) in text
