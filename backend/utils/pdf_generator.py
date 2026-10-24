import os
import sys

# Ensure root level modules like labels.py can be imported
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import re
from xml.sax.saxutils import escape
from utils.labels import get_labels

# Font path configured explicitly for utils/assets/fonts/
FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "fonts")
REGULAR_FONT_PATH = os.path.join(FONT_DIR, "NotoSansDevanagari-Regular.ttf")
BOLD_FONT_PATH = os.path.join(FONT_DIR, "NotoSansDevanagari-Bold.ttf")

if os.path.exists(REGULAR_FONT_PATH):
    pdfmetrics.registerFont(TTFont('NotoSansDevanagari', REGULAR_FONT_PATH))
    DEFAULT_FONT = 'NotoSansDevanagari'
else:
    DEFAULT_FONT = 'Helvetica'

if os.path.exists(BOLD_FONT_PATH):
    pdfmetrics.registerFont(TTFont('NotoSansDevanagari-Bold', BOLD_FONT_PATH))
    BOLD_FONT = 'NotoSansDevanagari-Bold'
else:
    BOLD_FONT = DEFAULT_FONT

# Lets <b> / <i> tags work with the custom font (otherwise ReportLab raises an error)
if DEFAULT_FONT != 'Helvetica':
    pdfmetrics.registerFontFamily(DEFAULT_FONT, normal=DEFAULT_FONT, bold=BOLD_FONT,
                                  italic=DEFAULT_FONT, boldItalic=BOLD_FONT)

_IMG_RE = re.compile(r"^!\[(.*?)\]\((.+)\)$")


def _fmt(text: str) -> str:
    """Escape XML characters, then turn **bold** and *italic* markdown into ReportLab tags."""
    t = escape(text)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<!\w)\*(.+?)\*(?!\w)", r"<i>\1</i>", t)
    return t


def generate_styled_pdf(content: str, output_path: str, image_paths: list = None, intent: str = "document", language: str = "english", grade: int = 7, subject: str = "Mathematics"):
    doc = SimpleDocTemplate(output_path, pagesize=letter, rightMargin=45, leftMargin=45, topMargin=45, bottomMargin=45)
    story = []
    styles = getSampleStyleSheet()
    L = get_labels(language)

    # High-contrast, ASD-friendly color palette
    PRIMARY = colors.HexColor("#1E3A8A")     # Deep Blue
    SECONDARY = colors.HexColor("#2563EB")   # Clear Accent Blue
    TEXT = colors.HexColor("#1F2937")        # Dark Charcoal Text
    BG = colors.HexColor("#F8FAFC")          # Off-White Low-Glare Background

    title_style = ParagraphStyle('T1', fontName=BOLD_FONT, fontSize=16, leading=20, textColor=PRIMARY, spaceAfter=4)
    sub_style = ParagraphStyle('T2', fontName=DEFAULT_FONT, fontSize=9.5, leading=13, textColor=SECONDARY, spaceAfter=12)
    h2_style = ParagraphStyle('H2', fontName=BOLD_FONT, fontSize=11.5, leading=15, textColor=PRIMARY, spaceBefore=10, spaceAfter=4)
    body_style = ParagraphStyle('B1', fontName=DEFAULT_FONT, fontSize=10, leading=14, textColor=TEXT, spaceAfter=6)
    h3_style = ParagraphStyle('H3', fontName=BOLD_FONT, fontSize=10.5, leading=14, textColor=SECONDARY, spaceBefore=8, spaceAfter=3)

    is_quiz = (intent == "quiz")

    # Quiz Layout Header
    if is_quiz:
        story.append(Paragraph(f"<b>{L['quiz_header']}</b>", title_style))
        story.append(Paragraph(f"<b>{L['subject']}:</b> {subject} | <b>{L['grade']}:</b> {grade}", sub_style))
        
        # High-contrast Student Assessment Table
        header_data = [
            [
                Paragraph(f"<b>{L['student_name']}:</b> ________________________", body_style), 
                Paragraph(f"<b>{L['date_label']}:</b> _____________", body_style),
                Paragraph(f"<b>{L['score_label']}:</b> _______", body_style)
            ]
        ]
        header_table = Table(header_data, colWidths=[240, 150, 110])
        header_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), BG),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor("#94A3B8")),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 10))
        story.append(Paragraph(f"<i>{L['quiz_instructions']}</i>", body_style))
        story.append(Spacer(1, 10))
    else:
        story.append(Paragraph("DraftBench — Special Education Resource", title_style))
        story.append(Paragraph("Curriculum Aligned &amp; Autism Support Framework", sub_style))

    # Visual PECS/PNG Icons Rendering Block
    has_inline = any(_IMG_RE.match(x.strip()) for x in content.split('\n'))
    if image_paths and not has_inline:
        img_elements = []
        for path in image_paths[:3]:
            if path and os.path.exists(path):
                try:
                    img = Image(path, width=70, height=70)
                    img_elements.append(img)
                except Exception:
                    pass
        if img_elements:
            img_table = Table([img_elements], colWidths=[80] * len(img_elements))
            img_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), BG),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ]))
            story.append(img_table)
            story.append(Spacer(1, 12))

    # Parse and add structured markdown content
    for line in content.split('\n'):
        l = line.strip()
        if not l:
            continue
        m = _IMG_RE.match(l)
        if m:  # inline slide icon
            p = m.group(2).strip().strip("<>")
            if os.path.exists(p):
                try:
                    from PIL import Image as PILImage
                    with PILImage.open(p) as pim:
                        iw, ih = pim.size
                    ratio = min(260 / iw, 170 / ih)
                    story.append(Image(p, width=iw * ratio, height=ih * ratio))
                    story.append(Spacer(1, 4))
                except Exception:
                    pass
            continue
        if l.startswith('### '):
            story.append(Paragraph(_fmt(l[4:]), h3_style))
        elif l.startswith('## '):
            story.append(Spacer(1, 4))
            story.append(Paragraph(_fmt(l[3:]), h2_style))
        elif l.startswith('# '):
            story.append(Spacer(1, 6))
            story.append(Paragraph(_fmt(l[2:]), h2_style))
        elif l.startswith('- '):
            story.append(Paragraph(f"• {_fmt(l[2:])}", body_style))
            if is_quiz:
                story.append(Spacer(1, 14))  # response space for the student
        else:
            story.append(Paragraph(_fmt(l), body_style))

    def add_footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(DEFAULT_FONT, 8)
        canvas.setFillColor(colors.HexColor("#64748B"))
        canvas.drawString(45, 25, "DraftBench Offline AI • Special Education Toolkit")
        canvas.drawRightString(letter[0] - 45, 25, f"{L['page']} {doc.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=add_footer, onLaterPages=add_footer)
    return output_path