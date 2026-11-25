from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from xml.sax.saxutils import escape


def render(rx, valid_until, license_number):
    """Build the prescription PDF (page compression off so the text can be checked in tests)."""
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
                            title=f"Prescription {rx.id}", author="Zahanati Digital", pageCompression=0)
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], fontSize=18, spaceAfter=2)
    small = ParagraphStyle("small", parent=ss["Normal"], fontSize=8, textColor=colors.grey)
    body = ss["Normal"]
    e = lambda v: escape(str(v)) if v is not None else "-"
    d, p = rx.doctor, rx.patient
    story = [Paragraph("Zahanati Digital", h1), Paragraph("Electronic Prescription / Agizo la Dawa", ss["Heading3"]),
             Paragraph(f"Prescription ID: {rx.id}", small)]
    if rx.status == "cancelled":
        story += [Spacer(1, 4), Paragraph(f'<font color="red"><b>CANCELLED / IMEFUTWA</b> - {e(rx.cancel_reason)}</font>', body)]
    story += [Spacer(1, 8)]
    info = [["Issued / Tarehe", e(rx.issued_date.isoformat()), "Valid until / Halali hadi", e(valid_until.isoformat())],
            ["Doctor / Daktari", e(f"Dr. {d.first_name} {d.last_name}"), "Licence / Leseni", e(license_number)],
            ["Council / Baraza", e(d.council.capitalize()), "Status", "Verified doctor" if d.can_practice else "Not currently verified"],
            ["Patient / Mgonjwa", e(f"{p.first_name} {p.last_name}"), "Date of birth", e(p.date_of_birth.isoformat() if p.date_of_birth else None)]]
    t = Table(info, colWidths=[34 * mm, 52 * mm, 38 * mm, 48 * mm])
    t.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 9), ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
                           ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke), ("BACKGROUND", (2, 0), (2, -1), colors.whitesmoke)]))
    story += [t, Spacer(1, 10)]
    rows = [["#", "Medicine / Dawa", "Dosage", "Frequency", "Days", "Instructions"]]
    cell = ParagraphStyle("cell", parent=body, fontSize=9)
    for n, i in enumerate(rx.items, 1):
        rows.append([str(n), Paragraph(e(i.medicine_name), cell), Paragraph(e(i.dosage), cell), Paragraph(e(i.frequency), cell),
                     str(i.duration_days), Paragraph(e(i.instructions), cell)])
    mt = Table(rows, colWidths=[8 * mm, 52 * mm, 25 * mm, 30 * mm, 12 * mm, 45 * mm], repeatRows=1)
    mt.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, 0), 9), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8f1ee")),
                            ("GRID", (0, 0), (-1, -1), 0.3, colors.grey), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [mt]
    if rx.notes:
        story += [Spacer(1, 8), Paragraph(f"<b>Notes / Maelezo:</b> {e(rx.notes)}", body)]
    story += [Spacer(1, 16), Paragraph("Issued electronically through Zahanati Digital. A prescription that is cancelled or past its "
                                       "validity date must not be dispensed. This document is not an emergency service - call 112.", small)]
    doc.build(story)
    return buf.getvalue()
