import math
import os
import sys

# Ensure project root is available for imports
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt
from lxml import etree

from utils.labels import get_labels

# Palette (matches the Draft Bench app)
PRIMARY, DEEP, SOFT, BORDER = "6D28D9", "2E1065", "F3EEFF", "E2D8F8"
TEXT, MUTED, WHITE, LAVENDER = "1E1033", "6B5E85", "FFFFFF", "DDD0FA"

SLIDE_W, SLIDE_H = 13.333, 7.5


def _rgb(hex_str: str) -> RGBColor:
    return RGBColor.from_string(hex_str)


def _fit_size(paragraphs, w_in, h_in, max_pt, min_pt, deva=False, gap=0.35):
    """Largest font size (pt) at which the paragraphs should fit the box. python-pptx can't measure text."""
    char_w = 0.62 if deva else 0.5
    usable_w = max((w_in - 0.3) * 72, 20)
    size = max_pt
    while size > min_pt:
        per_line = max(int(usable_w / (size * char_w)), 4)
        lines = sum(max(1, math.ceil(len(p) / per_line)) for p in paragraphs if p) or 1
        height = lines * size * 1.2 + max(len(paragraphs) - 1, 0) * size * gap
        if height <= (h_in - 0.2) * 72:
            break
        size -= 1
    return size


def _est_height(paragraphs, w_in, size, deva=False, gap=0.35):
    """Estimated height (inches) the paragraphs need at a given size."""
    char_w = 0.62 if deva else 0.5
    per_line = max(int(max((w_in - 0.3) * 72, 20) / (size * char_w)), 4)
    lines = sum(max(1, math.ceil(len(p) / per_line)) for p in paragraphs if p) or 1
    return (lines * size * 1.2 + max(len(paragraphs) - 1, 0) * size * gap) / 72 + 0.25


def _set_font(run, size, color, bold=False, italic=False, deva=False):
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = _rgb(color)
    rPr = run._r.get_or_add_rPr()
    if deva:  # complex-script font so Devanagari renders with a proper font
        cs = etree.SubElement(rPr, qn("a:cs"))
        cs.set("typeface", "Nirmala UI")


def _bullet(paragraph, color):
    pPr = paragraph._p.get_or_add_pPr()
    pPr.set("marL", "342900")
    pPr.set("indent", "-342900")
    bu_clr = etree.SubElement(pPr, qn("a:buClr"))
    etree.SubElement(bu_clr, qn("a:srgbClr")).set("val", color)
    etree.SubElement(pPr, qn("a:buChar")).set("char", "•")


def _rect(slide, x, y, w, h, fill=None, line=None, line_w=1.0, rounded=True, radius=0.08, alpha=None, shape=None):
    kind = shape or (MSO_SHAPE.ROUNDED_RECTANGLE if rounded else MSO_SHAPE.RECTANGLE)
    shp = slide.shapes.add_shape(kind, Inches(x), Inches(y), Inches(w), Inches(h))
    if kind == MSO_SHAPE.ROUNDED_RECTANGLE:
        shp.adjustments[0] = radius
    if fill:
        shp.fill.solid()
        shp.fill.fore_color.rgb = _rgb(fill)
        if alpha is not None:
            clr = shp.fill._xPr.find(qn("a:solidFill")).find(qn("a:srgbClr"))
            etree.SubElement(clr, qn("a:alpha")).set("val", str(int(alpha * 1000)))
    else:
        shp.fill.background()
    if line:
        shp.line.color.rgb = _rgb(line)
        shp.line.width = Pt(line_w)
    else:
        shp.line.fill.background()
    shp.shadow.inherit = False
    style = shp._element.find(qn("p:style"))  # drop the theme shadow in every viewer
    if style is not None:
        style.find(qn("a:effectRef")).set("idx", "0")
    return shp


def _text(slide, x, y, w, h, paragraphs, size, color=TEXT, bold=False, italic=False, align=PP_ALIGN.LEFT,
          anchor=MSO_ANCHOR.TOP, deva=False, bullets=False, bullet_color=PRIMARY, space_after=0.0):
    """Add a text box. paragraphs is a list of strings or of lists of (text, {bold, color, size}) runs."""
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.NONE
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Inches(0.08)
    tf.margin_top = tf.margin_bottom = Inches(0.04)
    for i, para in enumerate(paragraphs):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        if space_after:
            p.space_after = Pt(space_after)
        runs = para if isinstance(para, list) else [(para, {})]
        for txt, opt in runs:
            r = p.add_run()
            r.text = txt
            _set_font(r, opt.get("size", size), opt.get("color", color), opt.get("bold", bold), italic, deva)
        if bullets:
            _bullet(p, bullet_color)
    return tb


def _bg(slide, color):
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = _rgb(color)


def _picture_in_frame(slide, img_path, x, y, w, h):
    """Place a picture centred inside a white rounded frame, keeping its proportions."""
    from PIL import Image
    _rect(slide, x, y, w, h, fill=WHITE, line=BORDER, line_w=1.5, radius=0.04)
    try:
        with Image.open(img_path) as im:
            iw, ih = im.size
        pad = 0.15
        bw, bh = w - 2 * pad, h - 2 * pad
        ratio = min(bw / iw, bh / ih)
        pw, ph = iw * ratio, ih * ratio
        slide.shapes.add_picture(img_path, Inches(x + (w - pw) / 2), Inches(y + (h - ph) / 2), Inches(pw), Inches(ph))
        return True
    except Exception as e:
        print(f"Warning: PPTX image embed failed: {e}")
        return False


def _notes(slide, info, L):
    parts = []
    if info.get("teacher_script"):
        parts.append(f"{L['teacher_script']}: {info['teacher_script']}")
    if info.get("communication_support"):
        parts.append(f"{L['communication']}: {info['communication_support']}")
    if info.get("sensory_note"):
        parts.append(f"{L['sensory_note']}: {info['sensory_note']}")
    if parts:
        slide.notes_slide.notes_text_frame.text = "\n\n".join(parts)


def _footer(slide, idx, total, deva):
    _text(slide, SLIDE_W - 1.7, SLIDE_H - 0.5, 1.2, 0.35, [f"{idx} / {total}"], 11, color=MUTED, align=PP_ALIGN.RIGHT)
    _text(slide, 0.6, SLIDE_H - 0.5, 3, 0.35, ["Draft Bench"], 11, color=MUTED)


def _title_slide(prs, title, subtitle, meta_line, deva):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    _bg(s, PRIMARY)
    _rect(s, 8.6, -2.2, 6.6, 6.6, fill=WHITE, alpha=9, shape=MSO_SHAPE.OVAL)
    _rect(s, -1.6, 4.6, 4.6, 4.6, fill=WHITE, alpha=7, shape=MSO_SHAPE.OVAL)
    logo = _rect(s, 0.9, 0.8, 0.9, 0.9, fill=WHITE, radius=0.22)
    _text(s, 0.9, 0.8, 0.9, 0.9, ["DB"], 26, color=PRIMARY, bold=True, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    size = _fit_size([title], 10.5, 2.6, 54, 30, deva, gap=0)
    _text(s, 0.9, 2.5, 10.5, 2.6, [title], size, color=WHITE, bold=True, anchor=MSO_ANCHOR.MIDDLE, deva=deva)
    _text(s, 0.9, 5.2, 10.5, 0.6, [subtitle], 24, color=LAVENDER, deva=deva)
    if meta_line:
        _text(s, 0.9, 5.85, 10.5, 0.5, [meta_line], 16, color=LAVENDER, deva=deva)
    return s


def _schedule_slide(prs, schedule, heading, L, idx, total, deva):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    _bg(s, WHITE)
    _rect(s, 0.6, 0.45, 0.12, 0.8, fill=PRIMARY, rounded=False)
    _text(s, 0.85, 0.4, 11, 0.9, [heading], 34, color=DEEP, bold=True, anchor=MSO_ANCHOR.MIDDLE, deva=deva)
    steps = schedule[:4]
    n = max(len(steps), 1)
    gap = 0.3
    cw = (SLIDE_W - 1.2 - gap * (n - 1)) / n
    for i, st in enumerate(steps):
        x = 0.6 + i * (cw + gap)
        _rect(s, x, 1.9, cw, 4.2, fill=SOFT, line=BORDER, radius=0.06)
        _rect(s, x + 0.25, 2.15, 0.7, 0.7, fill=PRIMARY, shape=MSO_SHAPE.OVAL)
        _text(s, x + 0.25, 2.15, 0.7, 0.7, [str(i + 1)], 24, color=WHITE, bold=True, align=PP_ALIGN.CENTER,
              anchor=MSO_ANCHOR.MIDDLE)
        _text(s, x + 0.15, 3.05, cw - 0.3, 0.7, [str(st.get("label") or "")], 28, color=DEEP, bold=True, deva=deva)
        desc = str(st.get("icon_desc") or "")
        sz = _fit_size([desc], cw - 0.3, 1.6, 20, 14, deva)
        _text(s, x + 0.15, 3.8, cw - 0.3, 1.6, [desc], sz, color=TEXT, deva=deva)
        mins = st.get("duration_min")
        if mins:
            _text(s, x + 0.15, 5.4, cw - 0.3, 0.5, [f"{mins} {L['minutes']}"], 16, color=PRIMARY, bold=True, deva=deva)
    _footer(s, idx, total, deva)
    return s


def _content_slide(prs, info, idx, total, L, deva):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    _bg(s, WHITE)
    title = str(info.get("title") or f"{L['slide']} {idx}")
    key_idea = str(info.get("key_idea") or "").strip()
    bullets = [str(b) for b in (info.get("bullets") or []) if b][:3]
    explanation = str(info.get("explanation") or "").strip()
    example = str(info.get("example") or "").strip()
    terms = [t for t in (info.get("key_terms") or []) if isinstance(t, dict) and t.get("term")][:2]
    img = info.get("image_path") or info.get("icon_path")
    has_img = bool(img and os.path.exists(img))

    # Title
    _rect(s, 0.6, 0.4, 0.12, 0.8, fill=PRIMARY, rounded=False)
    tsize = _fit_size([title], 11.6, 0.9, 34, 24, deva, gap=0)
    _text(s, 0.85, 0.35, 11.9, 0.9, [title], tsize, color=DEEP, bold=True, anchor=MSO_ANCHOR.MIDDLE, deva=deva)

    LX, LW = 0.6, 7.4          # left column
    RX, RW = 8.4, 4.35         # right column

    # Key idea callout
    y = 1.5
    if key_idea:
        _rect(s, LX, y, LW, 1.05, fill=SOFT, line=BORDER, radius=0.1)
        _rect(s, LX, y + 0.12, 0.09, 0.81, fill=PRIMARY, rounded=False)
        ksz = _fit_size([key_idea], LW - 0.3, 1.05, 24, 16, deva, gap=0)
        _text(s, LX + 0.2, y, LW - 0.3, 1.05, [key_idea], ksz, color=DEEP, bold=True, anchor=MSO_ANCHOR.MIDDLE, deva=deva)
        y += 1.25

    # Bullets
    if bullets:
        bmax = 2.6 if explanation else 3.6
        bsz = _fit_size(bullets, LW, bmax, 22, 15, deva, gap=0.45)
        bh = min(bmax, _est_height(bullets, LW, bsz, deva, 0.45) + 0.1)
        _text(s, LX, y, LW, bh, bullets, bsz, color=TEXT, bullets=True, deva=deva, space_after=bsz * 0.45)
        y += bh + 0.2

    # Explanation
    if explanation:
        eh = max(SLIDE_H - 0.75 - y, 1.2)
        _rect(s, LX, y, LW, eh, fill=WHITE, line=BORDER, radius=0.06)
        esz = _fit_size([explanation], LW - 0.3, eh - 0.1, 20, 13, deva, gap=0)
        _text(s, LX + 0.15, y + 0.05, LW - 0.3, eh - 0.1, [explanation], esz, color=TEXT, anchor=MSO_ANCHOR.MIDDLE, deva=deva)

    # Right column: picture (if any), key terms, example
    ry = 1.5
    if has_img:
        fh = 3.35
        if _picture_in_frame(s, img, RX, ry, RW, fh):
            if info.get("image_path"):
                cap = L.get("from_material", "From your material") + (f" · {L['page']} {info['image_page']}" if info.get("image_page") else "")
                _text(s, RX, ry + fh + 0.02, RW, 0.35, [cap], 11, color=MUTED, deva=deva)
            ry += fh + 0.45
    if terms:
        paras = [[(str(t["term"]) + ": ", {"bold": True, "color": PRIMARY}), (str(t.get("meaning") or ""), {})] for t in terms]
        flat = [str(t["term"]) + ": " + str(t.get("meaning") or "") for t in terms]
        tmax = 2.0 if has_img else 3.0
        tsz = _fit_size([L.get("key_terms", "Key words")] + flat, RW - 0.2, tmax, 20, 13, deva, gap=0.3)
        th = min(tmax, _est_height([L.get("key_terms", "Key words")] + flat, RW - 0.2, tsz, deva, 0.3) + 0.2)
        _rect(s, RX, ry, RW, th, fill=SOFT, line=BORDER, radius=0.08)
        _text(s, RX + 0.1, ry + 0.08, RW - 0.2, th - 0.16, [[(L.get("key_terms", "Key words"), {"bold": True, "color": DEEP, "size": tsz})]] + paras,
              tsz, color=TEXT, deva=deva, space_after=tsz * 0.3)
        ry += th + 0.2
    if example:
        eh = max(SLIDE_H - 0.75 - ry, 1.1)
        _rect(s, RX, ry, RW, eh, fill=PRIMARY, radius=0.08)
        xsz = _fit_size([example], RW - 0.3, eh - 0.55, 20, 12, deva, gap=0)
        _text(s, RX + 0.15, ry + 0.08, RW - 0.3, 0.4, [L.get("example", "Example")], 13, color=LAVENDER, bold=True, deva=deva)
        _text(s, RX + 0.15, ry + 0.45, RW - 0.3, eh - 0.55, [example], xsz, color=WHITE, anchor=MSO_ANCHOR.MIDDLE, deva=deva)

    _footer(s, idx, total, deva)
    _notes(s, info, L)
    return s


def generate_styled_pptx(
    slides_data: list,
    output_path: str,
    grade: int,
    subject: str,
    image_paths: list = None,
    language: str = "english",
    lesson_title: str = None,
    visual_schedule: list = None,
    cdc_outcome: str = None,
):
    L = get_labels(language)
    deva = (language or "").lower() == "nepali"
    prs = Presentation()
    prs.slide_width = Inches(SLIDE_W)
    prs.slide_height = Inches(SLIDE_H)

    # Backward compatible: an aligned list of pictures, used only where a slide has no image of its own
    for i, info in enumerate(slides_data):
        if not info.get("image_path") and image_paths and i < len(image_paths) and image_paths[i]:
            info["image_path"] = image_paths[i]

    schedule = [st for st in (visual_schedule or []) if isinstance(st, dict) and st.get("label")]
    total = 1 + (1 if schedule else 0) + len(slides_data)

    _title_slide(
        prs,
        lesson_title or f"{subject}",
        f"{L['grade']} {grade} • {subject}",
        cdc_outcome or "",
        deva,
    )
    idx = 2
    if schedule:
        _schedule_slide(prs, schedule, L["visual_schedule"], L, idx, total, deva)
        idx += 1
    for info in slides_data:
        _content_slide(prs, info, idx, total, L, deva)
        idx += 1

    prs.save(output_path)
    return output_path