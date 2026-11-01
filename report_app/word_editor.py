from io import BytesIO

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_ROW_HEIGHT_RULE
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Mm, Pt, RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn


BLUE = "28599C"
BLACK = "111111"
SIGNERS = (
    ("ENTREGA – UNIVERSIDAD DE LIMA", "signature_delivered", "delivered_by", "delivered_dni", "delivered_position", "delivered_signed_on"),
    ("VALIDA - VDC", "signature_verified", "verified_by", "verified_dni", "verified_position", "verified_signed_on"),
    ("RECIBE / VALIDA - COSAPI", "signature_received", "received_by", "received_dni", "received_position", "received_signed_on"),
)


def _shade_cell(cell, color):
    properties = cell._tc.get_or_add_tcPr()
    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), color)
    properties.append(shading)


def _set_cell_margins(cell, top=60, start=70, bottom=60, end=70):
    properties = cell._tc.get_or_add_tcPr()
    margins = OxmlElement("w:tcMar")
    for side, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        margin = OxmlElement(f"w:{side}")
        margin.set(qn("w:w"), str(value))
        margin.set(qn("w:type"), "dxa")
        margins.append(margin)
    properties.append(margins)


def _set_cell_borders(cell, color=BLACK, size="6"):
    properties = cell._tc.get_or_add_tcPr()
    borders = OxmlElement("w:tcBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        border = OxmlElement(f"w:{edge}")
        border.set(qn("w:val"), "single")
        border.set(qn("w:sz"), size)
        border.set(qn("w:color"), color)
        borders.append(border)
    properties.append(borders)


def _format_run(run, size=8, bold=False, color=BLACK):
    run.font.name = "Arial"
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = RGBColor.from_string(color)


def _write_cell(cell, text, *, size=8, bold=False, color=BLACK, align=WD_ALIGN_PARAGRAPH.LEFT):
    cell.text = ""
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    _set_cell_margins(cell)
    _set_cell_borders(cell)
    paragraph = cell.paragraphs[0]
    paragraph.alignment = align
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.line_spacing = 1.0
    run = paragraph.add_run(str(text or ""))
    _format_run(run, size=size, bold=bold, color=color)


def _add_file_image(cell, file_field, width, height=None):
    if not file_field:
        return
    with file_field.open("rb") as source:
        image_bytes = BytesIO(source.read())
    paragraph = cell.paragraphs[0]
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.add_run().add_picture(image_bytes, width=Mm(width), height=Mm(height) if height else None)


def _format_document(document):
    section = document.sections[0]
    section.page_width = Mm(210)
    section.page_height = Mm(297)
    section.top_margin = Mm(9)
    section.bottom_margin = Mm(9)
    section.left_margin = Mm(9)
    section.right_margin = Mm(9)
    normal = document.styles["Normal"]
    normal.font.name = "Arial"
    normal.font.size = Pt(8)
    normal.paragraph_format.space_after = Pt(0)
    normal.paragraph_format.space_before = Pt(0)


def build_material_receipt_docx(receipt):
    report = receipt.report
    project = report.project
    document = Document()
    _format_document(document)

    header = document.add_table(rows=1, cols=3)
    header.autofit = False
    for cell, width in zip(header.rows[0].cells, (Mm(35), Mm(119), Mm(38))):
        cell.width = width
    logo_cell, title_cell, meta_cell = header.rows[0].cells
    _write_cell(logo_cell, "UNIVERSIDAD\nDE LIMA", size=8, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
    if receipt.company_logo:
        logo_cell.text = ""
        _add_file_image(logo_cell, receipt.company_logo, 27, 15)
    _write_cell(title_cell, "FORMATO – ACTA DE ENTREGA DE MATERIALES", size=9, bold=True, color="FFFFFF", align=WD_ALIGN_PARAGRAPH.CENTER)
    _shade_cell(title_cell, BLUE)
    title_cell.add_paragraph("CONTROL DE ENTREGA Y RECEPCIÓN")
    title_cell.add_paragraph("ÁREA DE ALMACÉN / LOGÍSTICA / PROYECTO")
    for paragraph in title_cell.paragraphs[1:]:
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.paragraph_format.space_after = Pt(0)
        for run in paragraph.runs:
            _format_run(run, size=7)
    receipt_date = receipt.receipt_date.strftime("%d/%m/%Y") if receipt.receipt_date else "—"
    _write_cell(
        meta_cell,
        f"Código: {receipt.act_number or '—'}\nVersión: 01\nFecha: {receipt_date}\nPágina: 1",
        size=7,
    )

    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.space_before = Pt(8)
    paragraph.paragraph_format.space_after = Pt(4)
    _format_run(paragraph.add_run("ACTA DE ENTREGA DE MATERIALES"), size=12, bold=True, color=BLUE)

    details = document.add_table(rows=2, cols=2)
    detail_values = (
        ("Proyecto", project.project_name),
        ("Ubicación", project.project_location),
        ("Proveedor", receipt.supplier),
        ("Guía de remisión", receipt.delivery_note),
    )
    for cell, (label, value) in zip(
        (cell for row in details.rows for cell in row.cells),
        detail_values,
    ):
        _write_cell(cell, f"{label}: {value or '—'}", size=7)

    intro = document.add_paragraph(
        f"Por medio de la presente, se deja constancia de la entrega y recepción de los materiales que se detallan a continuación, realizada en fecha {receipt_date}, en {project.project_location or '________________________________________'}."
    )
    intro.paragraph_format.space_after = Pt(6)

    heading = document.add_paragraph()
    heading.paragraph_format.space_after = Pt(3)
    _format_run(heading.add_run("DETALLE DE LOS MATERIALES ENTREGADOS"), size=8, bold=True, color=BLUE)

    entries = list(report.entries.all().order_by("id"))
    table = document.add_table(rows=1, cols=5)
    table.autofit = False
    widths = (Mm(10), Mm(86), Mm(19), Mm(20), Mm(57))
    for cell, text, width in zip(table.rows[0].cells, ("N.°", "DESCRIPCIÓN DEL MATERIAL", "UNIDAD", "CANTIDAD", "OBSERVACIONES"), widths):
        cell.width = width
        _write_cell(cell, text, size=6, bold=True, color="FFFFFF", align=WD_ALIGN_PARAGRAPH.CENTER)
        _shade_cell(cell, BLUE)

    rows = max(6, len(entries))
    for index in range(rows):
        entry = entries[index] if index < len(entries) else None
        values = (
            str(index + 1),
            entry.item_name if entry else "",
            entry.unit if entry else "",
            str(entry.quantity or 1) if entry else "",
            entry.description if entry else "",
        )
        cells = table.add_row().cells
        table.rows[-1].height = Mm(9)
        table.rows[-1].height_rule = WD_ROW_HEIGHT_RULE.AT_LEAST
        for cell, value, width in zip(cells, values, widths):
            cell.width = width
            _write_cell(cell, value, size=7, align=WD_ALIGN_PARAGRAPH.CENTER if cell is cells[0] else WD_ALIGN_PARAGRAPH.LEFT)

    closing = document.add_paragraph()
    closing.paragraph_format.space_before = Pt(7)
    closing.paragraph_format.space_after = Pt(3)
    _format_run(closing.add_run("CONFORMIDAD DE RECEPCIÓN"), size=8, bold=True, color=BLUE)
    conformity = {
        "conforme": "Recibido conforme",
        "observado": "Recibido con observaciones",
        "parcial": "Entrega parcial",
    }.get(receipt.conformity, "Sin especificar")
    document.add_paragraph(
        f"La persona que recibe declara haber verificado los materiales y las cantidades detalladas. Resultado: {conformity}."
    )
    observation = document.add_paragraph()
    _format_run(observation.add_run("Observaciones (faltantes, daños, diferencias u otros): "), bold=True)
    observation.add_run(receipt.observations or "—")

    signatures_title = document.add_paragraph()
    signatures_title.paragraph_format.space_before = Pt(6)
    signatures_title.paragraph_format.space_after = Pt(3)
    _format_run(signatures_title.add_run("FIRMAS DE RESPONSABILIDAD"), size=8, bold=True, color=BLUE)
    signatures = document.add_table(rows=5, cols=3)
    signatures.autofit = False
    for column, signer in enumerate(SIGNERS):
        label, signature_field, name_field, dni_field, position_field, signed_on_field = signer
        for row in signatures.rows:
            row.cells[column].width = Mm(64)
        heading_cell = signatures.cell(0, column)
        _write_cell(heading_cell, label, size=7, bold=True, color=BLUE, align=WD_ALIGN_PARAGRAPH.CENTER)
        _shade_cell(heading_cell, "E7EDF5")
        signature_cell = signatures.cell(1, column)
        _write_cell(signature_cell, "", size=7, align=WD_ALIGN_PARAGRAPH.CENTER)
        _add_file_image(signature_cell, getattr(receipt, signature_field), 40, 18)
        _write_cell(signatures.cell(2, column), f"Nombre: {getattr(receipt, name_field) or '—'}", size=7)
        _write_cell(
            signatures.cell(3, column),
            f"DNI: {getattr(receipt, dni_field) or '—'}   Cargo: {getattr(receipt, position_field) or '—'}",
            size=6,
        )
        signed_on = getattr(receipt, signed_on_field)
        _write_cell(signatures.cell(4, column), f"Fecha: {signed_on.strftime('%d/%m/%Y') if signed_on else '—'}", size=7)

    output = BytesIO()
    document.save(output)
    return output.getvalue()
