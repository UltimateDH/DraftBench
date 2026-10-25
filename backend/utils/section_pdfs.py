"""PDF builders for the Quiz, Braille-card and Sign-language-card sections."""
import re
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (Flowable, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

from agents.accessibility_tools import BLANK, UNVERIFIED_SIGNS, legend_entries, translate
from utils.labels import get_labels
from utils.pdf_generator import BOLD_FONT, DEFAULT_FONT

PRIMARY = colors.HexColor("#6D28D9")
DEEP = colors.HexColor("#2E1065")
SOFT = colors.HexColor("#F3EEFF")
BORDER = colors.HexColor("#D9CCF5")
INK = colors.HexColor("#1E1033")
MUTED = colors.HexColor("#6B5E85")
GREEN = colors.HexColor("#15803D")
AMBER = colors.HexColor("#B45309")
WIDTH = letter[0] - 90  # usable width with 45pt margins

_EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F]")


def _t(text) -> str:
    """Escape for ReportLab and drop emoji, which the PDF fonts cannot draw."""
    return _EMOJI.sub("", escape(str(text or "")))


def _styles():
    def st(name, **kw):
        base = dict(fontName=DEFAULT_FONT, fontSize=12, leading=17, textColor=INK)
        base.update(kw)
        return ParagraphStyle(name, **base)
    return {
        "title": st("t", fontName=BOLD_FONT, fontSize=22, leading=27, textColor=DEEP, spaceAfter=4),
        "sub": st("s", fontSize=11, textColor=MUTED, spaceAfter=10),
        "part": st("p", fontName=BOLD_FONT, fontSize=15, leading=20, textColor=PRIMARY, spaceBefore=10, spaceAfter=2),
        "hint": st("h", fontSize=11, textColor=MUTED, spaceAfter=8),
        "q": st("q", fontSize=15, leading=21, spaceAfter=6),
        "opt": st("o", fontSize=14, leading=19),
        "body": st("b"),
        "small": st("sm", fontSize=10, leading=14, textColor=MUTED),
        "label": st("l", fontName=BOLD_FONT, fontSize=10, textColor=PRIMARY),
        "print": st("pr", fontName=BOLD_FONT, fontSize=17, leading=23),
        "term": st("tm", fontName=BOLD_FONT, fontSize=19, leading=24, textColor=DEEP),
    }


def _doc(path, footer_text, language):
    L = get_labels(language)

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(DEFAULT_FONT, 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(45, 25, f"Draft Bench • {footer_text}")
        canvas.drawRightString(letter[0] - 45, 25, f"{L.get('page', 'Page')} {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(path, pagesize=letter, rightMargin=45, leftMargin=45, topMargin=45, bottomMargin=45)
    return doc, footer


class TickBox(Flowable):
    def __init__(self, size=20):
        super().__init__()
        self.size = size
        self.width = self.height = size

    def draw(self):
        c = self.canv
        c.setStrokeColor(INK)
        c.setLineWidth(1.6)
        c.roundRect(1, 1, self.size - 2, self.size - 2, 3, stroke=1, fill=0)


# ============================================================ QUIZ
def _question_block(q, n, S, g):
    items = [Paragraph(f"<b>{n}.</b> {_t(q['question']).replace('___', '__________')}", S["q"])]
    if q["type"] == "mcq":
        for i, opt in enumerate(q["options"]):
            row = Table([[TickBox(), Paragraph(f"<b>{'ABC'[i]}.</b> {_t(opt)}", S["opt"])]], colWidths=[34, WIDTH - 40])
            row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 5),
                                     ("BOTTOMPADDING", (0, 0), (-1, -1), 5), ("LEFTPADDING", (0, 0), (-1, -1), 6)]))
            items.append(row)
    elif q["type"] == "true_false":
        row = Table([[TickBox(26), Paragraph(f"<b>{_t(g('true_label', 'True'))}</b>", S["opt"]), "",
                      TickBox(26), Paragraph(f"<b>{_t(g('false_label', 'False'))}</b>", S["opt"])]],
                    colWidths=[36, 130, 30, 36, 130])
        row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 6),
                                 ("LEFTPADDING", (0, 0), (-1, -1), 6)]))
        items.append(row)
    else:
        bank = "      ".join(f"<b>{_t(w)}</b>" for w in q["word_bank"])
        box = Table([[Paragraph(f"{_t(g('word_bank', 'Word bank'))}:   {bank}", S["opt"])]], colWidths=[WIDTH - 10])
        box.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), SOFT), ("BOX", (0, 0), (-1, -1), 1, BORDER),
                                 ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
                                 ("LEFTPADDING", (0, 0), (-1, -1), 12)]))
        items.append(box)
    items.append(Spacer(1, 16))
    return items


def generate_quiz_pdf(quiz: dict, output_path: str, grade: int, subject: str, language: str = "english"):
    L = get_labels(language)
    g = lambda k, d: L.get(k, d)
    S = _styles()
    doc, footer = _doc(output_path, g("quiz_header", "Assessment Sheet"), language)
    story = [Paragraph(_t(quiz.get("title") or g("quiz_header", "Assessment Sheet")), S["title"]),
             Paragraph(f"{_t(subject)} • {_t(g('grade', 'Grade'))} {grade}", S["sub"])]

    head = Table([[Paragraph(f"<b>{_t(g('student_name', 'Student Name'))}:</b> ______________", S["body"]),
                   Paragraph(f"<b>{_t(g('date_label', 'Date'))}:</b> __________", S["body"]),
                   Paragraph(f"<b>{_t(g('score_label', 'Score'))}:</b> ____ / {len(quiz['questions'])}", S["body"])]],
                 colWidths=[WIDTH * 0.5, WIDTH * 0.26, WIDTH * 0.24])
    head.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), SOFT), ("BOX", (0, 0), (-1, -1), 1, BORDER),
                              ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 9)]))
    story += [head, Spacer(1, 8), Paragraph(_t(g("quiz_instructions", "")), S["hint"])]

    parts = [("mcq", g("quiz_part_mcq", "Choose the right answer"), g("tick_one", "Tick one box.")),
             ("true_false", g("quiz_part_tf", "True or false"), g("tick_tf", "Tick True or False.")),
             ("fill_blank", g("quiz_part_fill", "Fill in the blank"), g("use_bank", "Choose a word from the word bank."))]
    letter_i = 0
    for ptype, heading, hint in parts:
        qs = [q for q in quiz["questions"] if q["type"] == ptype]
        if not qs:
            continue
        story.append(Paragraph(f"{_t(g('part', 'Part'))} {'ABC'[letter_i]}: {_t(heading)}", S["part"]))
        story.append(Paragraph(_t(hint), S["hint"]))
        letter_i += 1
        for q in qs:
            story.append(KeepTogether(_question_block(q, q["number"], S, g)))

    story += [PageBreak(), Paragraph(_t(g("answer_key", "Answer Key")), S["title"]),
              Paragraph(f"{_t(g('teacher_copy', 'Teacher copy'))} • {_t(quiz.get('title') or '')}", S["sub"])]
    for q in quiz["questions"]:
        if q["type"] == "mcq":
            ans = f"{'ABC'[q['answer_index']]}. {q['options'][q['answer_index']]}"
        elif q["type"] == "true_false":
            ans = g("true_label", "True") if q["answer_bool"] else g("false_label", "False")
        else:
            ans = q["answer_text"]
        line = f"<b>{q['number']}.</b> {_t(ans)}"
        if q.get("explanation"):
            line += f"  <font color='#6B5E85'>— {_t(q['explanation'])}</font>"
        story.append(Paragraph(line, S["body"]))
        story.append(Spacer(1, 4))

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return output_path


# ============================================================ BRAILLE
class BrailleLines(Flowable):
    """Draws braille as real 6-dot cells, wrapped on word boundaries. No special font is needed."""
    ADV, DX, DY, R, LINE_H = 26, 10, 10, 3.1, 42

    def __init__(self, cells: str):
        super().__init__()
        self.cells = cells
        self.lines = []

    def wrap(self, aw, ah):
        cap = max(int(aw // self.ADV), 4)
        lines, cur = [], ""
        for word in [w for w in self.cells.split(BLANK) if w]:
            while len(word) > cap:
                if cur:
                    lines.append(cur)
                    cur = ""
                lines.append(word[:cap])
                word = word[cap:]
            if cur and len(cur) + 1 + len(word) > cap:
                lines.append(cur)
                cur = ""
            cur = (cur + BLANK + word) if cur else word
        if cur:
            lines.append(cur)
        self.lines = lines or [""]
        self.width, self.height = aw, len(self.lines) * self.LINE_H
        return self.width, self.height

    def draw(self):
        c = self.canv
        for li, line in enumerate(self.lines):
            top = self.height - li * self.LINE_H - 8
            for ci, ch in enumerate(line):
                if ch == BLANK:
                    continue
                bits = ord(ch) - 0x2800
                x0 = ci * self.ADV + 6
                for dot in range(1, 7):
                    col, row = (0 if dot <= 3 else 1), (dot - 1) % 3
                    cx, cy = x0 + col * self.DX, top - self.R - row * self.DY
                    if bits & (1 << (dot - 1)):
                        c.setFillColor(INK)
                        c.circle(cx, cy, self.R, stroke=0, fill=1)
                    else:
                        c.setFillColor(colors.HexColor("#D8D2E6"))
                        c.circle(cx, cy, 1.1, stroke=0, fill=1)


def _braille_card(label, text, S, sub_text=None):
    cells, unknown, _ = translate(text)
    flow = [Paragraph(_t(label), S["label"]), Paragraph(_t(text), S["print"]), Spacer(1, 4), BrailleLines(cells)]
    if sub_text:
        sub_cells = translate(sub_text)[0]
        flow += [Spacer(1, 4), Paragraph(_t(sub_text), S["body"]), Spacer(1, 4), BrailleLines(sub_cells)]
    card = Table([[flow]], colWidths=[WIDTH])
    card.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 1, BORDER), ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                              ("LEFTPADDING", (0, 0), (-1, -1), 14), ("TOPPADDING", (0, 0), (-1, -1), 10),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 10)]))
    return card, unknown


def generate_braille_pdf(content: dict, output_path: str, grade: int, subject: str, language: str = "english"):
    L = get_labels(language)
    g = lambda k, d: L.get(k, d)
    S = _styles()
    doc, footer = _doc(output_path, g("braille_title", "Braille Cards"), language)
    story = [Paragraph(_t(content.get("title") or g("braille_title", "Braille Cards")), S["title"]),
             Paragraph(f"{_t(g('braille_title', 'Braille Cards'))} • {_t(subject)} • {_t(g('grade', 'Grade'))} {grade}", S["sub"]),
             Paragraph(_t(g("braille_note", "")), S["small"]), Spacer(1, 10)]

    all_texts, all_unknown = [], set()

    def add(label, text, sub=None):
        card, unk = _braille_card(label, text, S, sub)
        all_unknown.update(unk)
        all_texts.extend([text] + ([sub] if sub else []))
        story.append(card)
        story.append(Spacer(1, 10))

    if content.get("title"):
        add(g("title_label", "Title"), content["title"])
    for i, p in enumerate(content.get("key_points") or [], 1):
        add(f"{g('braille_point', 'Key point')} {i}", p)
    for i, t in enumerate(content.get("key_terms") or [], 1):
        add(f"{g('braille_word', 'Key word')} {i}", t["term"], t.get("meaning") or None)

    joined = "".join(all_texts)
    if any(ch in joined for ch in UNVERIFIED_SIGNS):
        story.append(Paragraph(f"<font color='#B45309'>{_t(g('braille_unverified', ''))}</font>", S["small"]))
    if all_unknown:
        story.append(Paragraph(f"<font color='#B45309'>{_t(g('braille_unknown', ''))} {_t(' '.join(sorted(all_unknown)))}</font>", S["small"]))

    entries = legend_entries(all_texts)
    if entries:
        story += [PageBreak(), Paragraph(_t(g("braille_cells", "Cells used in this lesson")), S["part"]), Spacer(1, 6)]
        rows, row = [], []
        for ch, cells in entries:
            row += [Paragraph(f"<b>{_t(ch)}</b>", S["print"]), BrailleLines(cells)]
            if len(row) == 6:
                rows.append(row)
                row = []
        if row:
            rows.append(row + [""] * (6 - len(row)))
        legend = Table(rows, colWidths=[30, 86] * 3)
        legend.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 4),
                                    ("LINEBELOW", (0, 0), (-1, -1), 0.5, BORDER)]))
        story.append(legend)

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return output_path


# ============================================================ SIGN LANGUAGE
def generate_nsl_pdf(content: dict, items: list, output_path: str, grade: int, subject: str, language: str = "english"):
    L = get_labels(language)
    g = lambda k, d: L.get(k, d)
    S = _styles()
    doc, footer = _doc(output_path, g("nsl_title", "Sign Language Cards"), language)
    story = [Paragraph(_t(content.get("title") or g("nsl_title", "Sign Language Cards")), S["title"]),
             Paragraph(f"{_t(g('nsl_title', 'Sign Language Cards'))} • {_t(subject)} • {_t(g('grade', 'Grade'))} {grade}", S["sub"]),
             Paragraph(_t(g("nsl_note", "")), S["small"]), Spacer(1, 12)]

    badge = {"verified": (g("nsl_verified", "Verified sign"), "#15803D"),
             "suggested": (g("nsl_suggested", "Suggested: please check"), "#B45309"),
             "missing": (g("nsl_missing", "No suggestion yet"), "#6B5E85")}
    for it in items:
        text, color = badge.get(it["status"], badge["missing"])
        desc = it["description"] or g("nsl_missing_hint", "")
        src = f" <font color='#6B5E85'>({_t(it['source'])})</font>" if it.get("source") else ""
        rows = [
            [Paragraph(_t(it["term"]), S["term"]), Paragraph(f"<font color='{color}'><b>{_t(text)}</b></font>", S["small"])],
            [Paragraph(_t(it.get("meaning") or ""), S["body"]), ""],
            [Paragraph(f"<b>{_t(g('nsl_gesture', 'Gesture'))}:</b> {_t(desc)}{src}", S["opt"]), ""],
            [Paragraph(f"<font color='#6B5E85'>{_t(g('nsl_photo', ''))}</font>", S["small"]), ""],
        ]
        card = Table(rows, colWidths=[WIDTH * 0.62, WIDTH * 0.38], rowHeights=[None, None, None, 70])
        card.setStyle(TableStyle([
            ("SPAN", (0, 1), (1, 1)), ("SPAN", (0, 2), (1, 2)), ("SPAN", (0, 3), (1, 3)),
            ("BOX", (0, 0), (-1, -1), 1, BORDER), ("BACKGROUND", (0, 0), (-1, 0), SOFT),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("BOX", (0, 3), (-1, 3), 0.8, colors.HexColor("#CBD5E1"), None, (3, 3)),
        ]))
        story += [KeepTogether([card]), Spacer(1, 12)]

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return output_path
