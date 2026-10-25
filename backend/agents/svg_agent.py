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
    include_accessibility: bool = False,
    is_sign: bool = False
) -> str:
    """
    Uses local Ollama (qwen2.5:7b-instruct) to generate clean vector illustration SVGs.
    Automatically switches between general educational slide diagrams and schematic NSL hand signs.
    """
    os.makedirs(IMAGE_DIR, exist_ok=True)

    clean_desc = re.sub(r'[^a-zA-Z0-9]', '_', vdescription).strip('_').lower()
    base_name = f"{filename_prefix}_{clean_desc[:15]}_{uuid.uuid4().hex[:6]}"
    svg_path = os.path.join(IMAGE_DIR, f"{base_name}.svg")
    png_path = os.path.join(IMAGE_DIR, f"{base_name}.png")

    # Detect if this is a sign language gesture or general concept diagram
    is_sign_context = is_sign or any(kw in vdescription.lower() for kw in ["sign", "gesture", "hand", "finger", "palm", "tap", "wave", "motion"])

    if is_sign_context:
        system_prompt = """You are an expert SVG icon illustrator for sign language and educational gestures.
Output ONLY valid raw SVG XML inside an ```xml ... ``` block. No conversational text.

STRICT RULES FOR HAND SIGNS & GESTURES:
1. CANVAS: Use viewBox="0 0 500 340" with width="100%" height="100%".
2. CONTAINER: Outer card shape <rect width="500" height="340" rx="14" fill="#FFFFFF" stroke="#1E293B" stroke-width="3"/>
3. FRAME: Inner canvas area <rect x="25" y="25" width="450" height="260" rx="10" fill="#F8FAFC" stroke="#E2E8F0" stroke-width="2"/>
4. SCHEMATIC HAND & MOVEMENT: Do NOT attempt complex realistic hand anatomy. Instead, draw a clear schematic hand symbol using a rounded rectangle for the palm (e.g., <rect x="210" y="130" width="80" height="100" rx="15" fill="#93C5FD" stroke="#1E3A8A" stroke-width="3"/>), lines for fingers, and prominent curved/straight arrows (stroke="#EF4444" stroke-width="5" fill="none") to clearly show hand movement, tapping, or direction based on the description.
5. CLEAN & SIMPLE: Use high-contrast colors (Blue #3B82F6 for hands, Red #EF4444 for movement arrows). Add a short 2-3 word uppercase label at the bottom describing the action.
"""
    else:
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
            options={"temperature": 0.2, "num_predict": 600}
        )

        content = response["message"]["content"]
        match = re.search(r'<svg[\s\S]*?</svg>', content)
        if match:
            svg_code = match.group(0)
    except Exception as e:
        print(f"[SVG Agent] LLM Error: {e}")

    # Fallback clean vector if LLM fails
    if not svg_code or "<svg" not in svg_code:
        if is_sign_context:
            svg_code = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 340" width="100%" height="100%">
              <rect width="500" height="340" rx="14" fill="#FFFFFF" stroke="#1E293B" stroke-width="3"/>
              <rect x="25" y="25" width="450" height="260" rx="10" fill="#F8FAFC" stroke="#E2E8F0" stroke-width="2"/>
              <rect x="210" y="130" width="80" height="100" rx="15" fill="#93C5FD" stroke="#1E3A8A" stroke-width="3"/>
              <line x1="230" y1="130" x2="230" y2="100" stroke="#1E3A8A" stroke-width="4" stroke-linecap="round"/>
              <line x1="250" y1="130" x2="250" y2="95" stroke="#1E3A8A" stroke-width="4" stroke-linecap="round"/>
              <line x1="270" y1="130" x2="270" y2="100" stroke="#1E3A8A" stroke-width="4" stroke-linecap="round"/>
              <path d="M 310 160 Q 340 160 340 190 Q 340 220 310 220" stroke="#EF4444" stroke-width="5" fill="none" stroke-linecap="round"/>
              <polygon points="305,215 315,225 305,235" fill="#EF4444"/>
              <text x="250" y="312" font-family="Arial" font-size="11" fill="#475569" text-anchor="middle" font-weight="bold">NSL GESTURE ILLUSTRATION</text>
            </svg>"""
        else:
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
        import cairosvg
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


def generate_hand_sign_instruction_and_illustration(term: str, meaning: str, language: str = "english", lesson_topic: str = "") -> dict:
    """
    Generates text instructions for how to perform the hand sign, and simultaneously 
    generates the corresponding schematic illustration via SVG.
    """
    model = os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct")
    lang_name = "Nepali (Devanagari script)" if language == "nepali" else "English"
    
    prompt = f"""You are a Sign Language linguistics expert. Provide a concise physical instruction on how to sign the term '{term}' (meaning: {meaning}) in sign language.
Language: {lang_name}.
Describe hand configuration, starting position, and movement in 1-2 short sentences.
Return ONLY valid JSON:
{{"instruction": "..."}}"""

    instruction = f"Perform sign gesture for {term}."
    try:
        resp = ollama.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.2}
        )
        data = re.search(r'\{.*\}', resp["message"]["content"], re.DOTALL)
        if data:
            import json
            parsed = json.loads(data.group(0))
            instruction = parsed.get("instruction", instruction)
    except Exception as e:
        print(f"[SVG Agent] Instruction generation error: {e}")

    # Generate the SVG/PNG illustration based on the generated instruction
    png_path = generate_educational_svg(
        vdescription=instruction,
        filename_prefix="nsl_hand_sign",
        grade=7,
        lesson_topic=lesson_topic,
        language=language,
        is_sign=True
    )

    return {
        "term": term,
        "instruction": instruction,
        "sign_illustration": png_path or ""
    }


def add_nsl_svg_illustrations(items: list, topic: str = "", language: str = "english", say=None) -> list:
    """
    Batch processor for NSL items: populates both text instructions and visual sign illustrations.
    """
    say = say or (lambda m: None)
    for n, it in enumerate(items, 1):
        term = it.get("term") or it.get("term_en") or "sign"
        meaning = it.get("meaning") or ""
        say(f"Generating hand sign instructions & icon for '{term}' ({n} of {len(items)})...")
        
        result = generate_hand_sign_instruction_and_illustration(
            term=term, meaning=meaning, language=language, lesson_topic=topic
        )
        
        it["description"] = result["instruction"]
        it["sign_illustration"] = result["sign_illustration"]
        if it.get("status") in ("fingerspell", "missing"):
            it["status"] = "suggested"
            
    return items