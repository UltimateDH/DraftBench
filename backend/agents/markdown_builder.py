"""Builds the lesson-plan / IEP document text (markdown subset read by utils/pdf_generator.py).

Layout: 1) lesson content (what the topic is about), 2) teacher support, 3) schedule, 4) IEP, 5) supports, 6) sources.
Only '# ', '## ', '### ', '- ', '**bold**' and '![alt](path)' lines are used, so nothing leaks as raw symbols.
"""
import os

from utils.labels import get_labels

_NULLS = {"", "null", "none", "n/a", "na", "-"}


def _c(v) -> str:
    s = str(v if v is not None else "").strip()
    return "" if s.lower() in _NULLS else s


def _list(v) -> list:
    if isinstance(v, str):
        v = [v]
    return [_c(x) for x in (v or []) if _c(x)]


def build_lesson_markdown(plan: dict, subject: str, grade: int, language: str = "english", sources=None) -> str:
    L = get_labels(language)
    g = lambda k, d: L.get(k, d)
    meta = plan.get("lesson_meta") or {}
    out = []

    title = _c(meta.get("title")) or g("untitled", "Untitled Lesson Plan")
    head = f"**{g('subject', 'Subject')}:** {subject} | **{g('grade', 'Grade')}:** {grade}"
    if meta.get("duration_minutes"):
        head += f" | **{g('duration', 'Duration')}:** {meta['duration_minutes']} {g('minutes', 'mins')}"
    out += [f"# {title}", head, ""]

    slides = plan.get("slides") or []
    if not slides:
        return "\n".join(out + [g("no_plan", "No plan data available.")])

    # ---- 1. Lesson content: what the topic is about ----
    out.append(f"## {g('lesson_content', 'Lesson content')}")
    for s in slides:
        out.append(f"### {s.get('slide_number', '')}. {_c(s.get('title'))}")
        img = s.get("image_path")
        if img and os.path.exists(img):
            out.append(f"![{_c(s.get('title'))}]({img})")
        if _c(s.get("key_idea")):
            out.append(f"**{g('key_idea', 'Key idea')}:** {_c(s['key_idea'])}")
        if _c(s.get("explanation")):
            out.append(f"**{g('explanation', 'Explanation')}:** {_c(s['explanation'])}")
        for b in _list(s.get("bullets")):
            out.append(f"- {b}")
        if _c(s.get("example")):
            out.append(f"**{g('example', 'Example')}:** {_c(s['example'])}")
        terms = [t for t in (s.get("key_terms") or []) if isinstance(t, dict) and _c(t.get("term"))]
        if terms:
            out.append(f"**{g('key_terms', 'Key words')}:**")
            for t in terms:
                out.append(f"- **{_c(t['term'])}:** {_c(t.get('meaning'))}")
        out.append("")

    # ---- 2. Teacher support (never shown on slides) ----
    out.append(f"## {g('teacher_support', 'Teacher support')}")
    for s in slides:
        rows = [(g("teacher_script", "Teacher Script"), s.get("teacher_script")),
                (g("communication", "Communication Access"), s.get("communication_support")),
                (g("sensory_note", "Sensory Note"), s.get("sensory_note"))]
        rows = [(lab, _c(val)) for lab, val in rows if _c(val)]
        if rows:
            out.append(f"### {s.get('slide_number', '')}. {_c(s.get('title'))}")
            out += [f"**{lab}:** {val}" for lab, val in rows]
    out.append("")

    # ---- 3. Visual schedule ----
    sched = [x for x in (plan.get("visual_schedule") or []) if isinstance(x, dict) and _c(x.get("label"))]
    if sched:
        out.append(f"## {g('visual_schedule', 'Visual Schedule')}")
        for st in sched:
            dur = f" ({st['duration_min']} {g('minutes', 'mins')})" if st.get("duration_min") else ""
            out.append(f"- **{_c(st['label'])}:** {_c(st.get('icon_desc'))}{dur}")
        out.append("")

    # ---- 4. IEP ----
    iep = plan.get("iep_goal") or {}
    if iep:
        out.append(f"## {g('iep_target', 'IEP Target')}")
        for key, lab in (("goal_statement_english", g("goal_english", "English Goal")),
                         ("goal_statement_nepali", g("goal_nepali", "Nepali Goal")),
                         ("baseline_probe", g("baseline", "Baseline Probe")),
                         ("measurable_criteria", g("criteria", "Measurable Criteria")),
                         ("progress_monitoring", g("monitoring", "Progress Monitoring"))):
            if _c(iep.get(key)):
                out.append(f"**{lab}:** {_c(iep[key])}")
        out.append("")

    # ---- 5. Supports ----
    def block(heading, items):
        items = _list(items)
        if items:
            out.append(f"## {heading}")
            out.extend(f"- {i}" for i in items)
            out.append("")

    block(g("accommodations", "Accommodations"), plan.get("accommodations"))
    block(g("modifications", "Modifications"), plan.get("modifications"))
    block(g("prompt_hierarchy", "Prompt Hierarchy"), plan.get("prompt_hierarchy"))
    rp = plan.get("reinforcement_plan") or {}
    rows = [(g("preferred_reinforcer", "Preferred Reinforcer"), rp.get("preferred_reinforcer")),
            (g("schedule", "Schedule"), rp.get("schedule")),
            (g("first_then", "First–Then"), rp.get("first_then_statement"))]
    rows = [(a, _c(b)) for a, b in rows if _c(b)]
    if rows:
        out.append(f"## {g('reinforcement', 'Reinforcement Plan')}")
        out += [f"**{a}:** {b}" for a, b in rows]
        out.append("")
    block(g("sensory", "Sensory Accommodations"), plan.get("sensory_accommodations"))
    if _c(plan.get("calm_down_strategy")):
        out += [f"## {g('calm_down', 'Calm-Down Strategy')}", _c(plan["calm_down_strategy"]), ""]
    block(g("local_context", "Local Context Used"), plan.get("local_context_used"))

    # ---- 6. Sources (only when there are relevant ones) ----
    srcs = _list(sources)
    if srcs:
        out.append(f"## {g('sources', 'Curriculum Sources')}")
        out.extend(f"- {x}" for x in srcs)

    return "\n".join(out)
