import os
import re
import uuid
import cairosvg
from agents.accessibility_tools import return_braille, get_nsl_gesture_description_for_single_word

IMAGE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "exports", "images")

def generate_educational_svg(vdescription: str, filename_prefix: str, grade: int, lesson_topic: str = "", iep_goal: str = "", language: str = "english") -> str:
    """
    Generates a professional PECS visual card using 100% native SVG text elements 
    (fully compatible with CairoSVG) for icons, Braille, and NSL gestures.
    """
    os.makedirs(IMAGE_DIR, exist_ok=True)
    
    clean_desc = re.sub(r'[^a-zA-Z0-9]', '_', vdescription).strip('_').lower()
    base_name = f"{filename_prefix}_{clean_desc[:15]}_{uuid.uuid4().hex[:6]}"
    svg_path = os.path.join(IMAGE_DIR, f"{base_name}.svg")
    png_path = os.path.join(IMAGE_DIR, f"{base_name}.png")

    desc_lower = vdescription.lower()
    
    # 1. Fetch Braille & NSL Gesture Text
    braille_code = return_braille(vdescription)
    try:
        nsl_gesture = get_nsl_gesture_description_for_single_word(vdescription, language=language)
    except Exception:
        nsl_gesture = f"Sign representation for {vdescription}"

    # Split long NSL text into 3 clean lines for native SVG rendering
    words = nsl_gesture.split()
    line1, line2, line3 = "", "", ""
    for word in words:
        if len(line1) < 38:
            line1 += word + " "
        elif len(line2) < 38:
            line2 += word + " "
        else:
            line3 += word + " "
    if line3 and len(words) > len((line1 + line2).split()):
        line3 = line3.strip() + "..."

    # 2. Smart Icon Selector
    icon_svg = """
      <circle cx="200" cy="125" r="30" fill="#6C5CE7" opacity="0.15"/>
      <circle cx="200" cy="125" r="18" fill="#6C5CE7"/>
      <path d="M192 125 L197 130 L208 118" stroke="#FFFFFF" stroke-width="3" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
    """
    
    if any(k in desc_lower for k in ["add", "plus", "sum", "math", "count", "number"]):
        icon_svg = """
          <rect x="170" y="90" width="60" height="60" rx="8" fill="#E8F0FE" stroke="#4A90E2" stroke-width="2"/>
          <text x="200" y="132" font-family="Arial" font-size="32" font-weight="bold" fill="#1A73E8" text-anchor="middle">+</text>
        """
    elif any(k in desc_lower for k in ["water", "liquid", "drink", "rain"]):
        icon_svg = """
          <path d="M200 80 C 200 80 178 110 178 122 C 178 134.15 187.85 144 200 144 C 212.15 144 222 134.15 222 122 C 222 110 200 80 200 80 Z" fill="#0984E3"/>
        """
    elif any(k in desc_lower for k in ["plant", "tree", "leaf", "nature", "flower"]):
        icon_svg = """
          <circle cx="200" cy="115" r="24" fill="#00B894"/>
          <rect x="196" y="132" width="8" height="24" fill="#636e72" rx="2"/>
        """

    # 3. High-Resolution Card Layout using Native SVG Text
    svg_code = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400" width="100%" height="100%">
  <defs>
    <style>
      .card-bg {{ fill: #FFFFFF; stroke: #2D3436; stroke-width: 4; rx: 20px; }}
      .header-bg {{ fill: #2D3436; }}
      .title-text {{ font-family: 'Arial', sans-serif; font-size: 16px; font-weight: bold; fill: #FFFFFF; text-anchor: middle; }}
      .frame-box {{ fill: #F8F9FA; stroke: #DFE6E9; stroke-width: 2; rx: 10px; }}
      .braille-text {{ font-family: 'Arial', sans-serif; font-size: 20px; fill: #2D3436; text-anchor: middle; letter-spacing: 2px; }}
      .nsl-box {{ fill: #F0F3FF; stroke: #A29BFE; stroke-width: 1.5; rx: 8px; }}
      .nsl-title {{ font-family: 'Arial', sans-serif; font-size: 10px; font-weight: bold; fill: #6C5CE7; }}
      .nsl-text {{ font-family: 'Arial', sans-serif; font-size: 10px; fill: #2D3436; }}
    </style>
  </defs>

  <!-- Card Border -->
  <rect x="10" y="10" width="380" height="380" class="card-bg" />

  <!-- Header Banner -->
  <rect x="10" y="10" width="380" height="40" class="header-bg" rx="16" />
  <rect x="10" y="35" width="380" height="15" class="header-bg" />
  <text x="200" y="35" class="title-text">{vdescription[:32].upper()}</text>

  <!-- Icon Visual Display Area -->
  <rect x="40" y="58" width="320" height="95" class="frame-box" />
  {icon_svg}

  <!-- Braille Translation Section -->
  <text x="200" y="182" class="braille-text">{braille_code}</text>
  <text x="200" y="195" font-family="Arial" font-size="8" fill="#B2BEC3" text-anchor="middle">BRAILLE PATTERN</text>

  <!-- Nepali Sign Language (NSL) Instruction Box (Using Native SVG Text) -->
  <rect x="30" y="208" width="340" height="170" class="nsl-box" />
  <text x="45" y="228" class="nsl-title">🤟 NEPALI SIGN LANGUAGE (NSL) GESTURE:</text>
  
  <text x="45" y="250" class="nsl-text"><tspan x="45" dy="0">{line1}</tspan><tspan x="45" dy="16">{line2}</tspan><tspan x="45" dy="16">{line3}</tspan></text>

  <title>{vdescription}</title>
  <desc>Accessible PECS card with Braille and NSL guidance for {vdescription}</desc>
</svg>
"""

    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(svg_code)

    png_ok = False
    try:
        cairosvg.svg2png(url=svg_path, write_to=png_path, output_width=320, output_height=320)
        png_ok = True
    except Exception as e:
        print(f"[SVG Agent] Warning: SVG to PNG conversion failed: {e}")

    if os.path.exists(svg_path):
        try:
            os.remove(svg_path)
        except Exception:
            pass

    return png_path if png_ok else None