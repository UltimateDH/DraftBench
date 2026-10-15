import os
import re
import ollama

def generate_educational_svg(description:str, filename_prefix:str,grade:int,lesson_topic:str="",iep_goal:str=""):
    system_prompt=prompt = f"""You are an SVG XML coder producing special-education visual aids in the style of PECS / Boardmaker picture symbols.

    CONTEXT:
    - Grade: {grade}
    - Lesson topic: {lesson_topic or "general"}
    - IEP goal (reference only): {iep_goal or "not specified"}
    - Icon to draw: {description}

    STRICT OUTPUT RULES:
    1. Output ONLY valid SVG XML. Start with <svg and end with </svg>.
    2. Do NOT wrap in markdown code fences. No ``` blocks.
    3. No comments, no explanation before or after the SVG.
    4. Root must include xmlns="http://www.w3.org/2000/svg" and viewBox="0 0 100 100".

    SPECIAL-EDUCATION DESIGN RULES (ASD / PECS style):
    1. LITERAL — depict exactly the object or action. No symbols, no abstraction, no metaphors.
    2. NO AMBIGUOUS FACES — if a person is shown, use a neutral simple face or plain silhouette. Never show emotions the learner must interpret.
    3. FLAT AND SIMPLE — no gradients, no shadows, no textures, no 3D effects, no transparency.
    4. HIGH CONTRAST — dark outline (stroke-width 3 to 4) on a white background. At most 4 solid colors. Prefer black line art on white.
    5. CLEAR SILHOUETTE — recognizable at 64x64 pixels.
    6. ONE SUBJECT — no background scenery, no extra props, no decoration.
    7. CONSISTENT STYLE — same stroke width and palette as every other icon in this lesson.
    8. CLOSED SHAPES — no open paths, no dashed strokes.
    9. NO TEXT LABELS — do not write words. Numerals allowed only if the icon itself represents a number.

    ACCESSIBILITY (required):
    - Include a <title> element with a short literal description.
    - Include a <desc> element with one plain sentence explaining the icon.

    EXAMPLE STRUCTURE (follow this shape, not the content):
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
    <title>Red circle with the number two</title>
    <desc>A red circle with the digit two in the middle.</desc>
    <circle cx="50" cy="50" r="35" fill="#e63946" stroke="#000000" stroke-width="3"/>
    <path d="..." fill="#000000"/>
    </svg>

    Output ONLY the SVG XML now."""

    response = ollama.chat(
        model="qwen2.5:7b-instruct",
        messages=[
            {"role": "system", "content": "You output only valid SVG XML. You never use markdown fences or add commentary."},
            {"role": "user", "content": prompt}
        ],
        options={
            "temperature": 0.2,
            "num_predict": 800,
            "top_p": 0.9
        }
    )

    raw=response["message"]["content"].strip()
    raw = re.sub(r'^```(?:svg|xml)?\s*', '', raw)
    raw = re.sub(r'\s*```$', '', raw)
    match = re.search(r'<svg[\s\S]*?</svg>', raw)
    if not match:
        print(f"[SVG] Model returned no valid <svg> block for: {description}")
        svg_code = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
            '<title>Icon unavailable</title>'
            '<desc>Visual could not be generated.</desc>'
            '<rect x="10" y="10" width="80" height="80" fill="none" '
            'stroke="#000" stroke-width="3"/>'
            '</svg>'
        )
    else:
        svg_code = match.group(0)

    os.makedirs("data/exports/images", exist_ok=True)
    clean_desc = re.sub(r'[^a-zA-Z0-9]', '_', description)[:20].lower()
    file_path = os.path.join("data/exports/images", f"{filename_prefix}_{clean_desc}.svg")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(svg_code)
    return file_path

