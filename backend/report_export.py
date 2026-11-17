from __future__ import annotations

import re
from io import BytesIO

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt


def _plain(text: str) -> str:
    text = re.sub(r"!\[([^]]*)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[([^]]+)\]\(([^)]+)\)", r"\1（\2）", text)
    text = re.sub(r"\*\*([^*]+)\*\*|__([^_]+)__", lambda match: match.group(1) or match.group(2), text)
    return text.replace("`", "").strip()


def _clear_paragraph(paragraph) -> None:
    for child in list(paragraph._p):
        paragraph._p.remove(child)


def _set_keep_with_next(paragraph) -> None:
    properties = paragraph._p.get_or_add_pPr()
    properties.append(OxmlElement("w:keepNext"))


def _remove_paragraph_border(paragraph_or_style) -> None:
    properties = paragraph_or_style._element.get_or_add_pPr()
    border = properties.find(qn("w:pBdr"))
    if border is not None:
        properties.remove(border)


def _add_page_number(paragraph) -> None:
    _clear_paragraph(paragraph)
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run()
    _font(run, "宋体", 9)
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instruction = OxmlElement("w:instrText")
    instruction.set(qn("xml:space"), "preserve")
    instruction.text = " PAGE "
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    display = OxmlElement("w:t")
    display.text = "1"
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    for element in (begin, instruction, separate, display, end):
        run._r.append(element)


def _add_inline(paragraph, text: str, size: float = 12) -> None:
    """Write basic Markdown inline emphasis without exposing Markdown symbols."""
    cursor = 0
    for match in re.finditer(r"\*\*([^*]+)\*\*|__([^_]+)__|`([^`]+)`", text):
        if match.start() > cursor:
            _font(paragraph.add_run(_plain(text[cursor:match.start()])), "宋体", size)
        content = match.group(1) or match.group(2) or match.group(3) or ""
        run = paragraph.add_run(content)
        _font(run, "宋体", size, match.group(3) is None)
        cursor = match.end()
    if cursor < len(text):
        _font(paragraph.add_run(_plain(text[cursor:])), "宋体", size)


def _font(run, name: str = "宋体", size: float = 12, bold: bool | None = None) -> None:
    run.font.name = name
    run._element.rPr.rFonts.set(qn("w:eastAsia"), name)
    run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold


def _configure(document: Document) -> None:
    section = document.sections[0]
    section.page_width = Cm(21)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.54)
    section.bottom_margin = Cm(2.54)
    section.left_margin = Cm(3.0)
    section.right_margin = Cm(2.6)
    section.header_distance = Cm(0)
    section.footer_distance = Cm(1.2)
    section.different_first_page_header_footer = False
    for container in (section.header, section.footer, section.first_page_header, section.first_page_footer):
        for paragraph in container.paragraphs:
            _clear_paragraph(paragraph)
    _add_page_number(section.footer.paragraphs[0])
    styles = document.styles
    normal = styles["Normal"]
    normal.font.name = "宋体"
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
    normal.font.size = Pt(12)
    normal.paragraph_format.line_spacing = 1.5
    normal.paragraph_format.space_after = Pt(0)
    for style_name, size in (("Title", 22), ("Heading 1", 16), ("Heading 2", 15), ("Heading 3", 14)):
        style = styles[style_name]
        style.font.name = "黑体"
        style._element.rPr.rFonts.set(qn("w:eastAsia"), "黑体")
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = None
        style.paragraph_format.space_before = Pt(12)
        style.paragraph_format.space_after = Pt(6)
    styles["Title"].paragraph_format.space_before = Pt(0)
    styles["Title"].paragraph_format.space_after = Pt(18)
    _remove_paragraph_border(styles["Title"])


def _add_table(document: Document, lines: list[str]) -> None:
    rows = [[_plain(cell) for cell in line.strip().strip("|").split("|")] for line in lines]
    if len(rows) > 1 and all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in rows[1]):
        rows.pop(1)
    if not rows:
        return
    width = max(len(row) for row in rows)
    table = document.add_table(rows=len(rows), cols=width)
    table.style = "Table Grid"
    for row_index, values in enumerate(rows):
        for column_index in range(width):
            cell = table.cell(row_index, column_index)
            cell.text = values[column_index] if column_index < len(values) else ""
            for paragraph in cell.paragraphs:
                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER if row_index == 0 else WD_ALIGN_PARAGRAPH.LEFT
                for run in paragraph.runs:
                    _font(run, "黑体" if row_index == 0 else "宋体", 10.5, row_index == 0)


def build_report_docx(markdown: str, fallback_title: str) -> bytes:
    """Convert the final report Markdown only into a clean, editable Word report."""
    document = Document()
    _configure(document)
    lines = markdown.replace("\r\n", "\n").splitlines()
    title = next((_plain(line[2:]) for line in lines if line.startswith("# ")), fallback_title.strip()[:80] or "研究报告")
    title_paragraph = document.add_paragraph(style="Title")
    title_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _remove_paragraph_border(title_paragraph)
    _font(title_paragraph.add_run(title), "黑体", 22, True)
    title_paragraph.paragraph_format.line_spacing = 1.25
    title_paragraph.paragraph_format.space_after = Pt(18)

    index = 0
    in_code = False
    while index < len(lines):
        raw = lines[index].rstrip()
        stripped = raw.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            index += 1
            continue
        if not stripped or stripped in {"---", "***"} or stripped.startswith("# "):
            index += 1
            continue
        if stripped.startswith("|") and stripped.endswith("|"):
            table_lines = []
            while index < len(lines) and lines[index].strip().startswith("|") and lines[index].strip().endswith("|"):
                table_lines.append(lines[index].strip())
                index += 1
            _add_table(document, table_lines)
            continue
        heading = re.match(r"^(#{2,4})\s+(.+)$", stripped)
        if heading:
            level = min(len(heading.group(1)) - 1, 3)
            heading_text = _plain(heading.group(2))
            paragraph = document.add_paragraph(style=f"Heading {level}")
            if heading_text in {"摘要", "摘 要"}:
                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _set_keep_with_next(paragraph)
            _font(paragraph.add_run(heading_text), "黑体", {1: 16, 2: 15, 3: 14}[level], True)
            index += 1
            continue
        bullet = re.match(r"^[-*+]\s+(.+)$", stripped)
        numbered = re.match(r"^\d+[.)、]\s*(.+)$", stripped)
        bracketed_reference = re.match(r"^\[(\d+)\]\s*(.+)$", stripped)
        if bracketed_reference:
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.left_indent = Cm(0.85)
            paragraph.paragraph_format.first_line_indent = Cm(-0.85)
            paragraph.paragraph_format.line_spacing = 1.5
            paragraph.paragraph_format.space_after = Pt(0)
            _add_inline(paragraph, f"[{bracketed_reference.group(1)}] {bracketed_reference.group(2)}", 12)
            index += 1
            continue
        if bullet or numbered:
            paragraph = document.add_paragraph(style="List Bullet" if bullet else "List Number")
            paragraph.paragraph_format.line_spacing = 1.5
            paragraph.paragraph_format.space_after = Pt(0)
            _add_inline(paragraph, (bullet or numbered).group(1), 12)
            index += 1
            continue
        paragraph = document.add_paragraph()
        if in_code:
            _font(paragraph.add_run(raw), "等线", 10.5)
        else:
            content = stripped.lstrip("> ")
            is_keywords = bool(re.match(r"^(?:\*\*)?关键词(?:\*\*)?[：:]", content))
            is_abstract_label = content in {"摘要", "**摘要**", "摘要：", "摘要:"}
            paragraph.paragraph_format.line_spacing = 1.5
            paragraph.paragraph_format.space_after = Pt(0)
            paragraph.paragraph_format.first_line_indent = Cm(0) if is_keywords or is_abstract_label else Cm(0.85)
            if is_abstract_label:
                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                _font(paragraph.add_run("摘要"), "黑体", 15, True)
                _set_keep_with_next(paragraph)
            else:
                _add_inline(paragraph, content, 12)
        index += 1

    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()
