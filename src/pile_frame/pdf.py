"""Оформление расчётной записки в PDF (reportlab).

Шрифт DejaVu Sans встроен в пакет: кириллица, греческие буквы и математические знаки
выглядят одинаково на любом компьютере.
"""

from __future__ import annotations

import math
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.graphics.shapes import Circle, Drawing, Line, PolyLine, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

from pile_frame import report as rp

FONT, FONT_BOLD = "DejaVuSans", "DejaVuSans-Bold"
_FONTS = Path(__file__).with_name("fonts")
MARGIN = 20 * mm
FRAME_WIDTH = A4[0] - 2 * MARGIN

INK = colors.HexColor("#0F172A")
MUTED = colors.HexColor("#475569")
RULE = colors.HexColor("#CBD5E1")
HEADER_FILL = colors.HexColor("#F1F5F9")
FAIL = colors.HexColor("#B91C1C")
WARNING = colors.HexColor("#B45309")
JUMPER = colors.HexColor("#0F766E")
ZONE = colors.HexColor("#7C3AED")
ZONE_FILL = colors.Color(0.486, 0.227, 0.929, alpha=0.08)


def _register_fonts() -> None:
    if FONT not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(FONT, str(_FONTS / "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont(FONT_BOLD, str(_FONTS / "DejaVuSans-Bold.ttf")))
        pdfmetrics.registerFontFamily(FONT, normal=FONT, bold=FONT_BOLD)


def _styles() -> dict[str, ParagraphStyle]:
    base = ParagraphStyle("base", fontName=FONT, fontSize=9.5, leading=13, textColor=INK)
    return {
        "body": base,
        "muted": ParagraphStyle("muted", base, textColor=MUTED, fontSize=8.5, leading=11),
        "h1": ParagraphStyle(
            "h1", base, fontName=FONT_BOLD, fontSize=13, leading=17, spaceBefore=10, spaceAfter=6
        ),
        "h2": ParagraphStyle(
            "h2",
            base,
            fontName=FONT_BOLD,
            fontSize=10.5,
            leading=14,
            spaceBefore=10,
            spaceAfter=2,
            textColor=MUTED,
        ),
        "formula_title": ParagraphStyle(
            "formula_title", base, fontName=FONT_BOLD, spaceBefore=6, spaceAfter=2
        ),
        "formula": ParagraphStyle("formula", base, leftIndent=6 * mm, leading=12.5),
        "cell": ParagraphStyle("cell", base, fontSize=6.8, leading=8.2),
        "head": ParagraphStyle("head", base, fontName=FONT_BOLD, fontSize=6.8, leading=8.2),
        "title": ParagraphStyle(
            "title", base, fontName=FONT_BOLD, fontSize=20, leading=26, alignment=TA_CENTER
        ),
        "subtitle": ParagraphStyle(
            "subtitle", base, fontSize=13, leading=18, alignment=TA_CENTER, textColor=MUTED
        ),
        "center": ParagraphStyle("center", base, alignment=TA_CENTER),
        "note": ParagraphStyle(
            "note", base, alignment=TA_CENTER, textColor=MUTED, fontSize=8.5, leading=11
        ),
        "toc": ParagraphStyle("toc", base, fontSize=10.5, leading=16),
    }


def _p(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(text), style)


class _Document(SimpleDocTemplate):
    """Документ с оглавлением: заголовки разделов попадают в содержание."""

    def afterFlowable(self, flowable) -> None:  # noqa: N802 — имя метода reportlab
        if getattr(flowable, "toc_text", None):
            self.notify("TOCEntry", (0, flowable.toc_text, self.page))


def _numbered_canvas(footer: str):
    """Холст, который после вёрстки подписывает каждую страницу «Лист N из M»."""

    class NumberedCanvas(Canvas):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            self._pages: list[dict] = []

        def showPage(self) -> None:  # noqa: N802
            self._pages.append(dict(self.__dict__))
            self._startPage()

        def save(self) -> None:
            total = len(self._pages)
            for state in self._pages:
                self.__dict__.update(state)
                self.setFont(FONT, 7.5)
                self.setFillColor(MUTED)
                self.setStrokeColor(RULE)
                self.line(MARGIN, 14 * mm, A4[0] - MARGIN, 14 * mm)
                self.drawString(MARGIN, 10 * mm, footer)
                self.drawRightString(A4[0] - MARGIN, 10 * mm, f"Лист {self._pageNumber} из {total}")
                super().showPage()
            super().save()

    return NumberedCanvas


def _title_page(meta: rp.ReportMeta, styles) -> list:
    return [
        Spacer(1, 45 * mm),
        _p(meta.object_name, styles["subtitle"]),
        Spacer(1, 8 * mm),
        _p("Металлокаркас пола на сваях", styles["title"]),
        _p("под листы ЦСП", styles["subtitle"]),
        Spacer(1, 4 * mm),
        _p("Расчётная записка", styles["title"]),
        Spacer(1, 8 * mm),
        _p("Предпроектная проработка", styles["subtitle"]),
        Spacer(1, 70 * mm),
        _p(f"Исполнитель: {meta.author}", styles["center"]),
        _p(f"Дата: {meta.date:%d.%m.%Y}", styles["center"]),
        Spacer(1, 10 * mm),
        _p(
            "Документ не заменяет проект. Решения необходимо подтвердить расчётом проектировщика.",
            styles["note"],
        ),
        PageBreak(),
    ]


def _table(table: rp.Table, styles) -> Table:
    data = [[_p(h, styles["head"]) for h in table.headers]]
    data += [[_p(cell, styles["cell"]) for cell in row] for row in table.rows]
    widths = _column_widths(table)
    result = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    result.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), HEADER_FILL),
                ("LINEBELOW", (0, 0), (-1, -1), 0.3, RULE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 1.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
                ("LEFTPADDING", (0, 0), (-1, -1), 2.5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2.5),
            ]
        )
    )
    return result


CELL_PADDING = 5.0  # левый и правый отступ ячейки вместе, pt


def _column_widths(table: rp.Table, size: float = 6.8) -> list[float]:
    """Ширина колонок по самому длинному значению и самому длинному слову заголовка.

    Если колонки не помещаются, сжимаются только те, что шире своего заголовка: длинный
    текст переносится по словам, а числа и слова заголовка не разрываются.
    """
    need, floor = [], []
    for i, header in enumerate(table.headers):
        words = max(pdfmetrics.stringWidth(w, FONT_BOLD, size) for w in header.split())
        values = [pdfmetrics.stringWidth(row[i], FONT, size) for row in table.rows]
        # Слово из ячейки тоже не рвётся: «1,05» не должно переноситься по символам.
        cell_words = [
            pdfmetrics.stringWidth(w, FONT, size) for row in table.rows for w in row[i].split()
        ]
        longest = max(values, default=0.0)
        need.append(max(words, longest) + CELL_PADDING)
        floor.append(max(words, *cell_words, 0.0) + CELL_PADDING)
    total = sum(need)
    if total <= FRAME_WIDTH:
        spare = (FRAME_WIDTH - total) / len(need)
        return [w + spare for w in need]
    stretch = sum(n - f for n, f in zip(need, floor, strict=True))
    shrink = min(1.0, (total - FRAME_WIDTH) / stretch) if stretch else 1.0
    return [n - (n - f) * shrink for n, f in zip(need, floor, strict=True)]


def _plan(figure: rp.PlanFigure, styles) -> Drawing:
    """Схема плана в масштабе по ширине страницы, ось Y вниз — как на экране."""
    xs = [x for x, _ in figure.contour]
    ys = [y for _, y in figure.contour]
    min_x, max_x, min_y, max_y = min(xs), max(xs), min(ys), max(ys)
    pad = 12 * mm
    scale = min((FRAME_WIDTH - 2 * pad) / (max_x - min_x), (150 * mm) / (max_y - min_y))
    width = FRAME_WIDTH
    height = (max_y - min_y) * scale + 2 * pad

    def at(point):
        x, y = point
        return pad + (x - min_x) * scale, height - pad - (y - min_y) * scale

    drawing = Drawing(width, height)
    for rect, _, warn in figure.zones:
        (x0, y0), (x1, y1) = at(rect[:2]), at(rect[2:])
        zone = Rect(
            min(x0, x1),
            min(y0, y1),
            abs(x1 - x0),
            abs(y1 - y0),
            fillColor=ZONE_FILL,
            strokeColor=WARNING if warn else ZONE,
            strokeWidth=0.6,
        )
        if warn:
            zone.strokeDashArray = [2, 1.5]
        drawing.add(zone)
    outline = [c for p in [*figure.contour, figure.contour[0]] for c in at(p)]
    drawing.add(PolyLine(outline, strokeColor=RULE, strokeWidth=0.6))
    stroke = {"perimeter": 1.6, "beam": 1.0, "jumper": 0.5}
    font = max(3.2, min(6.0, 1.5 * mm * math.sqrt(len(figure.members)) / 5))
    for member in figure.members:
        (x0, y0), (x1, y1) = at(member.start), at(member.end)
        color = FAIL if member.failing else JUMPER if member.kind == "jumper" else INK
        line = Line(x0, y0, x1, y1, strokeColor=color, strokeWidth=stroke[member.kind])
        if member.failing:
            line.strokeDashArray = [2, 1.5]
        drawing.add(line)
        drawing.add(
            String(
                (x0 + x1) / 2 + 0.8,
                (y0 + y1) / 2 + 0.8,
                member.label,
                fontName=FONT,
                fontSize=font,
                fillColor=MUTED,
            )
        )
    for start, end in figure.bearing:
        (x0, y0), (x1, y1) = at(start), at(end)
        line = Line(x0, y0, x1, y1, strokeColor=WARNING, strokeWidth=1.2)
        line.strokeDashArray = [1.5, 1.5]
        drawing.add(line)
    for point, label in figure.piles:
        x, y = at(point)
        drawing.add(Circle(x, y, 1.6, fillColor=WARNING, strokeColor=None))
        drawing.add(String(x + 2, y - font - 1.5, label, fontName=FONT_BOLD, fontSize=font + 0.6))
    # Подписи зон — поверх балок и свай, на белой подложке.
    for rect, label, _ in figure.zones:
        (x0, y0), (x1, y1) = at(rect[:2]), at(rect[2:])
        text_width = pdfmetrics.stringWidth(label, FONT, 6)
        drawing.add(
            Rect(
                (x0 + x1) / 2 - text_width / 2 - 1.5,
                (y0 + y1) / 2 - 2,
                text_width + 3,
                8,
                fillColor=colors.white,
                strokeColor=None,
            )
        )
        drawing.add(
            String(
                (x0 + x1) / 2,
                (y0 + y1) / 2,
                label,
                fontName=FONT,
                fontSize=6,
                fillColor=ZONE,
                textAnchor="middle",
            )
        )
    # Габаритные размеры над и слева от плана.
    top = height - pad + 5
    drawing.add(Line(pad, top, pad + (max_x - min_x) * scale, top, strokeColor=MUTED))
    drawing.add(
        String(
            pad + (max_x - min_x) * scale / 2,
            top + 2,
            f"{max_x - min_x:.0f}",
            fontName=FONT,
            fontSize=7,
            textAnchor="middle",
        )
    )
    left = pad - 5
    drawing.add(Line(left, pad, left, height - pad, strokeColor=MUTED))
    drawing.add(
        String(
            left - 2,
            height / 2,
            f"{max_y - min_y:.0f}",
            fontName=FONT,
            fontSize=7,
            textAnchor="end",
        )
    )
    return drawing


def _section(number: int, section: rp.Section, styles) -> list:
    heading = _p(f"{number}. {section.title}", styles["h1"])
    heading.toc_text = f"{number}. {section.title}"
    story: list = [heading]
    for block in section.blocks:
        if isinstance(block, rp.Heading):
            story.append(_p(block.text, styles["h2"]))
        elif isinstance(block, rp.Paragraph):
            story.append(_p(block.text, styles["body"]))
            story.append(Spacer(1, 2))
        elif isinstance(block, rp.Formula):
            lines = [_p(block.title, styles["formula_title"])]
            lines += [_p(line, styles["formula"]) for line in block.lines]
            story.append(KeepTogether(lines))
        elif isinstance(block, rp.Table):
            story.append(Spacer(1, 4))
            story.append(_table(block, styles))
            story.append(Spacer(1, 6))
        elif isinstance(block, rp.PlanFigure):
            story.append(Spacer(1, 4))
            story.append(_plan(block, styles))
            story.append(Spacer(1, 4))
    return story


def write_pdf(report: rp.Report, path: str | Path) -> None:
    """Сверстать записку и сохранить в ``path``."""
    _register_fonts()
    styles = _styles()
    meta = report.meta
    document = _Document(
        str(path),
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
        title=f"Расчётная записка — {meta.object_name}",
        author=meta.author,
    )
    contents = TableOfContents()
    contents.levelStyles = [styles["toc"]]
    story = _title_page(meta, styles)
    story += [_p("Содержание", styles["h1"]), contents, PageBreak()]
    for number, section in enumerate(report.sections, start=1):
        story += _section(number, section, styles)
    footer = f"Каркас на сваях · {meta.object_name} · расчётная записка"
    document.multiBuild(story, canvasmaker=_numbered_canvas(footer))
