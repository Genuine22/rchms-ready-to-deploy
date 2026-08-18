"""
PDF builders for the Starlink Installation module (Phase 7).

Two kinds of documents:
  - Record PDFs (survey_pdf, installation_report_pdf): a single site
    survey or installation report, formatted as a hand-off document -
    something you could print and leave with a school, clinic, or
    business after the visit.
  - Table PDFs (table_report_pdf): the four aggregate reports (Daily
    Installations, Monthly Installations, Technician Performance,
    Revenue) - all built from one shared function since they're all
    "a title, some summary lines, then a table."

Every function here returns raw PDF bytes; the Flask routes in
app/routes/installation.py wrap those bytes in a Response with the
right mimetype and filename.
"""

import io
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
)

GOLD = colors.HexColor("#B08D45")
INK = colors.HexColor("#1A1A1A")
MUTED = colors.HexColor("#6B6B6B")
LINE = colors.HexColor("#E2DED4")

_styles = getSampleStyleSheet()
_title_style = ParagraphStyle(
    "RCHMSTitle", parent=_styles["Title"], textColor=INK, fontSize=18, spaceAfter=2,
)
_subtitle_style = ParagraphStyle(
    "RCHMSSubtitle", parent=_styles["Normal"], textColor=MUTED, fontSize=10, spaceAfter=10,
)
_label_style = ParagraphStyle(
    "RCHMSLabel", parent=_styles["Normal"], textColor=MUTED, fontSize=9,
)
_value_style = ParagraphStyle(
    "RCHMSValue", parent=_styles["Normal"], textColor=INK, fontSize=10.5,
)
_h2_style = ParagraphStyle(
    "RCHMSH2", parent=_styles["Heading2"], textColor=INK, fontSize=12, spaceBefore=14, spaceAfter=6,
)


def _letterhead(title, subtitle):
    return [
        Paragraph("RuralConnect Hub", _title_style),
        Paragraph(f"{title} &middot; {subtitle}", _subtitle_style),
        HRFlowable(width="100%", thickness=1, color=LINE, spaceAfter=12),
    ]


def _kv_table(pairs):
    """A simple label/value table for detail sheets."""
    rows = [[Paragraph(label, _label_style), Paragraph(str(value), _value_style)] for label, value in pairs]
    t = Table(rows, colWidths=[45 * mm, 120 * mm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
    ]))
    return t


def _fmt_money(value):
    return f"GHS {value:,.2f}" if value is not None else "—"


def _fmt_date(value, fmt="%d %b %Y"):
    return value.strftime(fmt) if value else "—"


# ============================================================
# RECORD PDFs
# ============================================================

def survey_pdf(survey):
    """One site survey, as a printable hand-off sheet."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=20 * mm, bottomMargin=20 * mm)
    story = []
    story += _letterhead("Site Survey Report", survey.subscriber.full_name)

    story.append(_kv_table([
        ("Member", survey.subscriber.full_name),
        ("Phone", survey.subscriber.phone_number),
        ("Location", survey.subscriber.location or "—"),
    ]))
    story.append(Paragraph("Survey Details", _h2_style))
    story.append(_kv_table([
        ("Survey Date", _fmt_date(survey.survey_date)),
        ("Surveyor", survey.surveyor.full_name if survey.surveyor else "Not assigned"),
        ("Status", survey.status.title()),
        ("GPS Location", survey.gps_location or "—"),
        ("Roof Type", survey.roof_type or "—"),
        ("Mount Type", survey.mount_type or "—"),
        ("Obstruction Level", survey.obstruction_level.title()),
        ("Estimated Cable Length",
         f"{survey.estimated_cable_length} m" if survey.estimated_cable_length is not None else "—"),
        ("Estimated Cost", _fmt_money(survey.estimated_cost)),
        ("Remarks", survey.remarks or "—"),
    ]))

    doc.build(story)
    return buf.getvalue()


def installation_report_pdf(job):
    """One installation's completion report, as a printable hand-off sheet."""
    report = job.report
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=20 * mm, bottomMargin=20 * mm)
    story = []
    story += _letterhead("Installation Report", job.subscriber.full_name)

    story.append(_kv_table([
        ("Member", job.subscriber.full_name),
        ("Phone", job.subscriber.phone_number),
        ("Location", job.subscriber.location or "—"),
    ]))

    story.append(Paragraph("Installation", _h2_style))
    story.append(_kv_table([
        ("Technician", job.technician.full_name if job.technician else "Not assigned"),
        ("Installation Date", _fmt_date(job.installation_date)),
        ("Status", job.status.replace("_", " ").title()),
    ]))

    if job.equipment:
        latest_kit = sorted(job.equipment, key=lambda e: e.assigned_date, reverse=True)[0]
        story.append(Paragraph("Equipment", _h2_style))
        story.append(_kv_table([
            ("Dish Serial", latest_kit.dish_serial or "—"),
            ("Router Serial", latest_kit.router_serial or "—"),
            ("Cable Length", f"{latest_kit.cable_length} m" if latest_kit.cable_length is not None else "—"),
            ("Mount Type", latest_kit.mount_type or "—"),
        ]))

    if report:
        story.append(Paragraph("Completion & Speed Test", _h2_style))
        story.append(_kv_table([
            ("Completion Date", _fmt_date(report.completion_date)),
            ("Download Speed", f"{report.download_speed} Mbps" if report.download_speed is not None else "—"),
            ("Upload Speed", f"{report.upload_speed} Mbps" if report.upload_speed is not None else "—"),
            ("Latency", f"{report.latency} ms" if report.latency is not None else "—"),
            ("Signed Off By", report.customer_name or "—"),
            ("Installer Notes", report.installer_notes or "—"),
        ]))
    else:
        story.append(Paragraph("No completion report has been filed for this job yet.", _value_style))

    doc.build(story)
    return buf.getvalue()


# ============================================================
# TABLE PDFs (Daily / Monthly / Technician / Revenue)
# ============================================================

def table_report_pdf(title, subtitle, columns, rows, summary_lines=None):
    """
    Shared builder for the four aggregate reports. `rows` is a list
    of tuples matching `columns`; `summary_lines` is an optional list
    of short strings shown above the table (e.g. totals).
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=20 * mm, bottomMargin=20 * mm)
    story = []
    story += _letterhead(title, subtitle)

    if summary_lines:
        for line in summary_lines:
            story.append(Paragraph(line, _value_style))
        story.append(Spacer(1, 10))

    table_data = [columns] + [list(r) for r in rows]
    col_count = len(columns)
    available_width = 170 * mm
    col_width = available_width / col_count
    t = Table(table_data, colWidths=[col_width] * col_count, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F5F1E8")),
        ("TEXTCOLOR", (0, 0), (-1, 0), INK),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, 0), 1, GOLD),
        ("LINEBELOW", (0, 1), (-1, -2), 0.5, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    if not rows:
        story.append(Paragraph("No records found for this range.", _value_style))
    else:
        story.append(t)

    doc.build(story)
    return buf.getvalue()
