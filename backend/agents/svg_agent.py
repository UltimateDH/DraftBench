import os
import re
import uuid
import ollama

IMAGE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "exports", "images")

def generate_educational_svg(
    vdescription: str,
    filename_prefix: str,
    grade: int,
    lesson_topic: str = "",
    iep_goal: str = "",
    language: str = "english",
    include_accessibility: bool = False
) -> str:
    """
    Uses local Ollama (qwen2.5:7b-instruct) to generate clean vector illustration SVGs
    focusing on geometric shapes and visual diagrams, avoiding text hallucinations.
    """
    os.makedirs(IMAGE_DIR, exist_ok=True)

    clean_desc = re.sub(r'[^a-zA-Z0-9]', '_', vdescription).strip('_').lower()
    base_name = f"{filename_prefix}_{clean_desc[:15]}_{uuid.uuid4().hex[:6]}"
    svg_path = os.path.join(IMAGE_DIR, f"{base_name}.svg")
    png_path = os.path.join(IMAGE_DIR, f"{base_name}.png")

    system_prompt = """You are an expert SVG diagram illustrator for school educational materials.
Output ONLY valid raw SVG XML inside an ```xml ... ``` block. No conversational text.

STRICT RULES:
1. CANVAS: Use viewBox="0 0 500 340" with width="100%" height="100%".
2. CONTAINER: Outer card shape <rect width="500" height="340" rx="14" fill="#FFFFFF" stroke="#1E293B" stroke-width="3"/>
3. FRAME: Inner canvas area <rect x="25" y="25" width="450" height="260" rx="10" fill="#F8FAFC" stroke="#E2E8F0" stroke-width="2"/>
4. VECTOR GRAPHICS ONLY: Draw clear visual objects (circles, rectangles, paths, connection lines, arrows) representing the description using vibrant colors (Blue #3B82F6, Red #EF4444, Green #10B981, Amber #F59E0B).
5. NO LONG TEXT: Do NOT write long paragraphs of text inside the SVG. You may include a single short 2-3 word uppercase label max. Focus entirely on drawing the visual concept clearly.
"""

    user_prompt = f"Topic: {lesson_topic} | Visual Concept to Illustrate: {vdescription}"

    svg_code = ""
    try:
        response = ollama.chat(
            model="qwen2.5:7b-instruct",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            options={"temperature": 0.2, "num_predict": 500}
        )

        content = response["message"]["content"]
        match = re.search(r'<svg[\s\S]*?</svg>', content)
        if match:
            svg_code = match.group(0)
    except Exception as e:
        print(f"[SVG Agent] LLM Error: {e}")

    # Fallback clean vector if LLM fails
    if not svg_code or "<svg" not in svg_code:
        svg_code = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 340" width="100%" height="100%">
          <rect width="500" height="340" rx="14" fill="#FFFFFF" stroke="#1E293B" stroke-width="3"/>
          <rect x="25" y="25" width="450" height="260" rx="10" fill="#F8FAFC" stroke="#E2E8F0" stroke-width="2"/>
          <circle cx="250" cy="155" r="50" fill="#3B82F6" opacity="0.2"/>
          <path d="M225 155 L242 172 L275 138" stroke="#1D4ED8" stroke-width="5" stroke-linecap="round" fill="none"/>
          <text x="250" y="312" font-family="Arial" font-size="11" fill="#475569" text-anchor="middle" font-weight="bold">DRAFTBENCH VISUAL ASSET</text>
        </svg>"""

    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(svg_code)

    png_ok = False
    try:
        import cairosvg  # loaded only when an icon is drawn, so a missing Cairo library cannot break other sections
        cairosvg.svg2png(url=svg_path, write_to=png_path, output_width=600, output_height=408)
        png_ok = True
    except Exception as err:
        print(f"[SVG Agent] CairoSVG conversion error: {err}")

    if os.path.exists(svg_path):
        try:
            os.remove(svg_path)
        except Exception:
            pass

    return png_path if png_ok else None