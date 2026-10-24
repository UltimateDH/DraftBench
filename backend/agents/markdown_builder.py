from typing import Any
from utils.labels import get_labels
import os


def _h1(text: str) -> str:
    return f"# {text}\n\n"


def _h2(text: str) -> str:
    return f"\n## {text}\n\n"


def _h3(text: str) -> str:
    return f"\n### {text}\n\n"


def _bullet(text: str) -> str:
    return f"- {text}\n"


def _kv(label: str, value: Any) -> str:
    """Bold label : value. Skips if value is None/empty/empty-list."""
    if value is None or value == "" or value == []:
        return ""
    return f"- **{label}:** {value}\n"


def _safe(value: Any, fallback: Any = "") -> Any:
    if value is None or value == "":
        return fallback
    return value


def _join_list(items: list) -> str:
    """Join a list of strings with commas. Skips falsy entries."""
    return ", ".join(str(i) for i in items if i)


def _normalize_image_path(path: str) -> str:
    """
    Normalize an image path for Markdown.

    - Converts backslashes to forward slashes (Windows -> Markdown).
    - Wraps in angle brackets if the path contains spaces or parentheses
      (Markdown needs <> to parse those correctly).
    """
    if not path:
        return ""
    p = path.replace("\\", "/")
    if any(ch in p for ch in (" ", "(", ")")):
        return f"<{p}>"
    return p


def _get_slide_png(slide: dict) -> str:
    """
    Return the PNG path for a slide, or "".

    Only looks at slide["png_path"]. If the file doesn't exist on disk,
    the path is still returned — a PDF renderer running from a different
    working directory may still resolve it.
    """
    val = slide.get("image_path") or slide.get("png_path")
    if not val or not isinstance(val, str):
        return ""
    return val


def _build_header(plan: dict, subject: str, grade: int, language: str, L: dict) -> str:
    meta = plan.get("lesson_meta", {}) or {}
    title = _safe(meta.get("title"), L["untitled"])
    duration = _safe(meta.get("duration_minutes"), 30)
    cdc_ref = meta.get("cdc_outcome_ref")

    out = _h1(title)
    out += (
        f"**{L['subject']}:** {subject} | "
        f"**{L['grade']}:** {grade} | "
        f"**{L['language']}:** {language.upper()} | "
        f"**{L['duration']}:** {duration} {L['minutes']}\n\n"
    )
    if cdc_ref:
        out += f"**{L['cdc_outcome']}:** {cdc_ref}\n\n"
    return out


def _build_visual_schedule(plan: dict, L: dict) -> str:
    schedule = plan.get("visual_schedule") or []
    if not schedule:
        return ""
    out = _h2(L["visual_schedule"])
    for step in schedule:
        label = _safe(step.get("label"), "Step")
        dur = _safe(step.get("duration_min"), "?")
        icon = _safe(step.get("icon_desc"), "—")
        out += _bullet(f"**{label}** ({dur} {L['minutes']}): {icon}")
    return out


def _build_slides(plan: dict, L: dict) -> str:
    """
    Render all slides. For each slide:
      - PNG icon appears FIRST (fixed, predictable position)
      - Then the slide heading
      - Then up to 3 bullets
      - Then optional teacher script / communication / sensory notes
    """
    slides = plan.get("slides") or []
    if not slides:
        return ""

    out = _h2(L["lesson_slides"])
    for s in slides:
        num = _safe(s.get("slide_number"), "?")
        title = _safe(s.get("title"), L["untitled"])

        # --- PNG icon FIRST (predictable position: top of every slide) ---
        png_path = _get_slide_png(s)
        if png_path:
            rel = _normalize_image_path(png_path)
            alt = _safe(s.get("visual_desc"), L["icon_alt"])
            # Escape chars that break Markdown alt text
            alt = alt.replace("|", "/").replace("[", "(").replace("]", ")")
            out += f"\n![{alt}]({rel})\n\n"

        # --- Heading ---
        out += _h3(f"{L['slide']} {num}: {title}")

        # --- Bullets (hard cap at 3 for ASD-friendly cognitive load) ---
        bullets = (s.get("bullets") or [])[:3]
        for b in bullets:
            out += _bullet(b)
        if s.get("explanation"):
            out += f"\n{s['explanation']}\n"
        if s.get("example"):
            out += f"\n**{L.get('example', 'Example')}:** {s['example']}\n"
        terms = [t for t in (s.get("key_terms") or []) if isinstance(t, dict) and t.get("term")]
        if terms:
            out += f"\n**{L.get('key_terms', 'Key words')}:** " + "; ".join(
                f"{t['term']}: {t.get('meaning', '')}" for t in terms) + "\n"

        # --- Optional inline notes ---
        if s.get("teacher_script"):
            out += f"\n*{L['teacher_script']}:* \"{s['teacher_script']}\"\n"
        if s.get("communication_support"):
            out += f"*{L['communication']}:* {s['communication_support']}\n"
        if s.get("sensory_note"):
            out += f"*{L['sensory_note']}:* {s['sensory_note']}\n"

    return out


def _build_present_levels(plan: dict, L: dict) -> str:
    """PLAAFP — Present Levels of Academic Achievement & Functional Performance."""
    pl = plan.get("present_levels") or {}
    if not pl:
        return ""
    out = _h2(L["present_levels"])
    if pl.get("narrative"):
        out += pl["narrative"] + "\n\n"
    if pl.get("strengths"):
        out += f"**{L['strengths']}:** {_join_list(pl['strengths'])}\n\n"
    if pl.get("areas_of_need"):
        out += f"**{L['areas_of_need']}:** {_join_list(pl['areas_of_need'])}\n\n"
    return out


def _build_iep_goals(plan: dict, L: dict) -> str:
    """
    Supports both schemas:
      - New: plan["iep_goals"] = [ {domain, goal_statement_english, ...}, ... ]
      - Old: plan["iep_goal"]  = { goal_statement_english, ... }  (single)
    """
    goals = plan.get("iep_goals")
    if not goals:
        single = plan.get("iep_goal")
        goals = [single] if single else []

    if not goals:
        return ""

    out = _h2(L["iep_target"])
    for i, g in enumerate(goals, 1):
        if not isinstance(g, dict):
            continue
        domain = g.get("domain")
        if domain:
            out += _h3(f"{L['goal']} {i} — {domain.title()}")
        else:
            out += _h3(f"{L['goal']} {i}")

        out += _kv(L["goal_english"], g.get("goal_statement_english"))
        out += _kv(L["goal_nepali"], g.get("goal_statement_nepali"))
        out += _kv(L["baseline"], g.get("baseline_probe"))
        out += _kv(L["criteria"], g.get("measurable_criteria"))
        out += _kv(L["monitoring"], g.get("progress_monitoring"))

        objectives = g.get("short_term_objectives") or []
        if objectives:
            out += f"\n**{L['objectives']}:**\n"
            for obj in objectives[:5]:
                out += _bullet(obj)
    return out


def _build_services(plan: dict, L: dict) -> str:
    services = plan.get("services") or {}
    if not services:
        return ""
    out = _h2(L["services"])
    out += _kv(L["sped_service"], services.get("special_education"))
    if services.get("related_services"):
        out += f"- **{L['related_services']}:** {_join_list(services['related_services'])}\n"
    out += _kv(L["lre"], services.get("lre_statement"))
    return out


def _build_list_section(title: str, items: list) -> str:
    if not items:
        return ""
    out = _h2(title)
    for item in items[:5]:
        if item:
            out += _bullet(item)
    return out


def _build_prompt_hierarchy(plan: dict, L: dict) -> str:
    hierarchy = plan.get("prompt_hierarchy") or []
    if not hierarchy:
        return ""
    return _h2(L["prompt_hierarchy"]) + " → ".join(hierarchy) + "\n"


def _build_reinforcement_plan(plan: dict, L: dict) -> str:
    rp = plan.get("reinforcement_plan") or {}
    if not rp:
        return ""
    out = _h2(L["reinforcement"])
    out += _kv(L["preferred_reinforcer"], rp.get("preferred_reinforcer"))
    out += _kv(L["schedule"], rp.get("schedule"))
    out += _kv(L["first_then"], rp.get("first_then_statement"))
    return out


def _build_calm_down(plan: dict, L: dict) -> str:
    text = plan.get("calm_down_strategy")
    if not text:
        return ""
    return _h2(L["calm_down"]) + f"{text}\n"


def _build_sources(sources: list, L: dict) -> str:
    out = _h2(L["sources"])
    if sources:
        for i, src in enumerate(sources, 1):
            out += f"{i}. {src}\n"
    else:
        out += f"_{L['no_sources']}_\n"
    return out

def build_lesson_markdown(plan: dict, subject: str, grade: int, language: str = "english", sources: list = None) -> str:
    """
    Builds structured, predictable, autism-friendly educational content for PDFs and presentations.
    Organizes material into clear visual blocks: Core Concept, Key Points, Real-World Examples, 
    and Communication Supports, avoiding cognitive overload.
    """
    meta = plan.get("lesson_meta", {})
    title = meta.get("title", "Structured Lesson Plan")
    slides = plan.get("slides", [])

    md_lines = []
    
    # Document Header (Predictable layout)
    md_lines.append(f"# {title}")
    md_lines.append(f"**Subject:** {subject} | **Target Grade:** {grade}")
    md_lines.append("\n--- \n")
    md_lines.append("### 🧠 Autism-Friendly Learning Framework")
    md_lines.append("* *Predictable pacing: One core concept per section.*")
    md_lines.append("* *Literal, concrete language with real-world grounding.*")
    md_lines.append("\n---\n")

    for idx, slide in enumerate(slides, 1):
        s_title = slide.get("title", f"Concept {idx}")
        key_idea = slide.get("key_idea", "").strip()
        explanation = slide.get("explanation", "").strip()
        bullets = slide.get("bullets", [])
        example = slide.get("example", "").strip()
        comm_support = slide.get("communication_support", "Point, say, or use AAC to respond.")
        key_terms = slide.get("key_terms", [])

        md_lines.append(f"## Step {idx}: {s_title}\n")
        
        if key_idea:
            md_lines.append(f"🎯 **Core Concept:** {key_idea}\n")
        
        if explanation:
            md_lines.append(f"📖 **Explanation:** {explanation}\n")

        if bullets and isinstance(bullets, list):
            md_lines.append("📌 **Key Takeaways:**")
            for b in bullets:
                if str(b).strip():
                    md_lines.append(f"- {str(b).strip()}")
            md_lines.append("")

        if example:
            md_lines.append(f"🌍 **Real-World Example:** {example}\n")

        if comm_support:
            md_lines.append(f"🗣️ **Communication Support:** {comm_support}\n")

        if key_terms and isinstance(key_terms, list):
            md_lines.append("📖 **Vocabulary Builder:**")
            for kt in key_terms:
                if isinstance(kt, dict):
                    term = kt.get("term", "").strip()
                    meaning = kt.get("meaning", "").strip()
                    if term:
                        md_lines.append(f"- **{term}:** {meaning}")
            md_lines.append("")

        md_lines.append("\n---\n")

    # Curriculum Sources Appendix
    if sources and isinstance(sources, list):
        md_lines.append("### 📚 Curriculum Reference Standards")
        for src in sources:
            md_lines.append(f"- {src}")

    return "\n".join(md_lines)