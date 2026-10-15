import os
import sys

# Ensure project root is available for imports
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from labels import get_labels


def generate_styled_pptx(
    slides_data: list,
    output_path: str,
    grade: int,
    subject: str,
    image_paths: list = None,
    language: str = "english"
):
    L = get_labels(language)
    prs = Presentation()
    prs.slide_width = Inches(13.33)
    prs.slide_height = Inches(7.5)

    CHARCOAL = RGBColor(31, 41, 55)

    # Localized Title Slide
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    slide.shapes.title.text = f"DraftBench: {subject}"
    slide.placeholders[1].text = (
        f"{L['grade']} {grade} | {L['language']}: {language.upper()}"
    )

    # Localized & Autism-Optimized Content Slides
    for idx, slide_info in enumerate(slides_data):
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        slide_title = slide_info.get("title") or f"{L['slide']} {idx + 1}"
        slide.shapes.title.text = slide_title

        tf = slide.placeholders[1].text_frame
        tf.text = ""

        bullets = slide_info.get("bullets", [])[:3]
        for point in bullets:
            p = tf.add_paragraph()
            p.text = str(point)
            p.font.size = Pt(18)
            p.font.color.rgb = CHARCOAL
            p.space_after = Pt(12)

        # Optional Teacher Script Footer on Slide
        if slide_info.get("teacher_script"):
            p_script = tf.add_paragraph()
            p_script.text = f"{L['teacher_script']}: \"{slide_info['teacher_script']}\""
            p_script.font.size = Pt(14)
            p_script.font.italic = True
            p_script.font.color.rgb = RGBColor(75, 85, 99)
            p_script.space_before = Pt(16)

        # High-contrast PNG icon placement
        if image_paths and idx < len(image_paths):
            img_path = image_paths[idx]
            if img_path and os.path.exists(img_path):
                try:
                    slide.shapes.add_picture(
                        img_path, Inches(9.8), Inches(2.0), width=Inches(2.8)
                    )
                except Exception as e:
                    print(f"Warning: PPTX image embed failed: {e}")

    prs.save(output_path)
    return output_path