import os
import re
import uuid
import cairosvg

IMAGE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "exports", "images")

def generate_educational_svg(vdescription: str, filename_prefix: str, grade: int, lesson_topic: str = "", iep_goal: str = "") -> str:
    """
    Deterministically generates a clean, high-contrast, professional PECS-style 
    educational visual card in SVG and converts it to PNG via CairoSVG.
    Completely eliminates broken LLM-generated XML/empty squares.
    """
    os.makedirs(IMAGE_DIR, exist_ok=True)
    
    clean_desc = re.sub(r'[^a-zA-Z0-9]', '_', vdescription).strip('_').lower()
    base_name = f"{filename_prefix}_{clean_desc[:15]}_{uuid.uuid4().hex[:6]}"
    svg_path = os.path.join(IMAGE_DIR, f"{base_name}.svg")
    png_path = os.path.join(IMAGE_DIR, f"{base_name}.png")

    desc_lower = vdescription.lower()
    
    # Smart Icon Selector based on concept keywords
    icon_svg = """
      <!-- Default Educational Icon Symbol -->
      <circle cx="200" cy="140" r="45" fill="#6C5CE7" opacity="0.15"/>
      <circle cx="200" cy="140" r="30" fill="#6C5CE7"/>
      <path d="M185 140 L195 150 L215 130" stroke="#FFFFFF" stroke-width="6" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
    """
    
    if any(k in desc_lower for k in ["add", "plus", "sum", "math", "count", "number"]):
        icon_svg = """
          <!-- Math / Count Icon -->
          <rect x="160" y="100" width="80" height="80" rx="12" fill="#E8F0FE" stroke="#4A90E2" stroke-width="3"/>
          <text x="200" y="152" font-family="Arial, sans-serif" font-size="42" font-weight="bold" fill="#1A73E8" text-anchor="middle">+</text>
        """
    elif any(k in desc_lower for k in ["water", "liquid", "drink", "rain"]):
        icon_svg = """
          <!-- Water / Nature Icon -->
          <path d="M200 95 C 200 95 170 130 170 150 C 170 166.569 183.431 180 200 180 C 216.569 180 230 166.569 230 150 C 230 130 200 95 200 95 Z" fill="#0984E3"/>
        """
    elif any(k in desc_lower for k in ["plant", "tree", "leaf", "nature", "flower"]):
        icon_svg = """
          <!-- Plant / Nature Icon -->
          <circle cx="200" cy="130" r="35" fill="#00B894"/>
          <rect x="193" y="150" width="14" height="35" fill="#636e72" rx="4"/>
        """
    elif any(k in desc_lower for k in ["book", "read", "study", "learn", "text"]):
        icon_svg = """
          <!-- Book / Reading Icon -->
          <path d="M165 110 C 180 100 200 110 200 110 C 200 110 220 100 235 110 L 235 170 C 220 160 200 170 200 170 C 200 170 180 160 165 170 Z" fill="#D63031"/>
          <path d="M200 110 L 200 170" stroke="#FFFFFF" stroke-width="3"/>
        """

    # Professional PECS Card Template (400x400 High-Res ViewBox)
    svg_code = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400" width="100%" height="100%">
  <defs>
    <style>
      .card-bg {{ fill: #FFFFFF; stroke: #2D3436; stroke-width: 5; rx: 24px; }}
      .header-bg {{ fill: #2D3436; }}
      .title-text {{ font-family: 'Arial', sans-serif; font-size: 22px; font-weight: bold; fill: #FFFFFF; text-anchor: middle; }}
      .sub-text {{ font-family: 'Arial', sans-serif; font-size: 14px; fill: #636E72; text-anchor: middle; }}
      .frame-box {{ fill: #F8F9FA; stroke: #DFE6E9; stroke-width: 3; rx: 16px; }}
    </style>
  </defs>

  <!-- Outer PECS Card Background -->
  <rect x="10" y="10" width="380" height="380" class="card-bg" />

  <!-- Top Header Banner -->
  <rect x="10" y="10" width="380" height="60" class="header-bg" rx="20" />
  <rect x="10" y="50" width="380" height="20" class="header-bg" />
  <text x="200" y="47" class="title-text">Grade {grade} | {lesson_topic[:20] if lesson_topic else "Learning Card"}</text>

  <!-- Central Image / Icon Frame -->
  <rect x="40" y="85" width="320" height="210" class="frame-box" />
  
  {icon_svg}

  <!-- Bottom Label Description -->
  <text x="200" y="335" font-family="Arial, sans-serif" font-size="18px" font-weight="bold" fill="#2D3436" text-anchor="middle">{vdescription[:35]}</text>
  <text x="200" y="360" class="sub-text">Special Education Visual Aid</text>
  
  <title>{vdescription}</title>
  <desc>Visual PECS card for Grade {grade} representing {vdescription}</desc>
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