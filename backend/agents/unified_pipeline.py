import os
import sys
import json
import re
import ollama

# Ensure project root is in python path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from utils.labels import get_labels
from rag import query_curriculum_rag
from agents.svg_agent import generate_educational_svg
from agents.markdown_builder import build_lesson_markdown
from utils.pdf_generator import generate_styled_pdf
from utils.pptx_generator import generate_styled_pptx

MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct")
# AI-drawn SVG pictures from a small model are rarely useful. Off by default; set DRAFTBENCH_AI_SVG=1 to try them.
USE_AI_SVG = os.getenv("DRAFTBENCH_AI_SVG", "0") == "1"

# Global in-memory session store for state persistence across turns
SESSION_STORE = {}
EXPORT_DIR = os.path.join(PROJECT_ROOT, "data", "exports")

_NULLS = {"", "null", "none", "n/a", "na", "-"}
# Slide text must describe the TOPIC. These patterns catch instructions / teacher-talk that leaked into slides.
IMPERATIVE = re.compile(
    r"^\s*(draw|label|point|look|say|ask|tell|show|have|let'?s|let us|imagine|think|remember|try|use|write|"
    r"students?|teacher|we will|you will)\b", re.I)
META = re.compile(r"\b(the teacher|the student|students will|teacher will|let'?s learn|in this lesson we)\b", re.I)


# ----------------------------------------------------------------------------- helpers
def get_or_update_session(session_id: str, current_params: dict) -> dict:
    """Retrieve or update in-memory session parameters across chat turns."""
    if session_id not in SESSION_STORE:
        SESSION_STORE[session_id] = {"grade": 7, "subject": "Mathematics", "language": "english", "topic": None}
    session = SESSION_STORE[session_id]
    for key in ["grade", "subject", "language", "topic"]:
        if current_params.get(key):
            session[key] = current_params[key]
    return session


def _s(v) -> str:
    s = str(v if v is not None else "").strip()
    return "" if s.lower() in _NULLS else s


def _sentences(text: str) -> list:
    return [x for x in re.split(r"(?<=[.!?।])\s+", text or "") if x.strip()]


def clean_meta_text(text: str) -> str:
    """Strips meta-instructions, rubric headers and internal prompt tags so they don't leak onto slides."""
    if not isinstance(text, str):
        return text
    cleaned = text.strip()
    for pattern in (r"^learning goal[s]?:?\s*", r"^iep goal[s]?:?\s*", r"^cdc outcome:?\s*",
                    r"^prompt instruction:?\s*", r"^teacher script:?\s*"):
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


_ABOUT = re.compile(r"^\s*(?:please\s+)?(?:create|make|write|generate|prepare|build|draft)\b.*?\b(?:about|on|covering)\s+", re.I | re.S)
_FOR = re.compile(r"^\s*(?:please\s+)?(?:create|make|write|generate|prepare|build|draft)\b.*?\bfor\s+(?:a\s+|an\s+|the\s+)?", re.I | re.S)


def derive_topic(user_prompt: str) -> str:
    """'Create a lesson plan with an IEP goal about Rutherford's atomic model' -> "Rutherford's atomic model"."""
    p = (user_prompt or "").strip()
    for rx in (_ABOUT, _FOR):
        t = rx.sub("", p, count=1).strip().rstrip(".")
        if t and t != p:
            return t
    return p


def _kw(text: str) -> set:
    t = re.sub(r"'s\b", "", (text or "").lower())
    out = set()
    for w in re.findall(r"[a-z\u0900-\u097F]{4,}", t):
        out.add(w[:-1] if w.endswith("s") and len(w) > 4 else w)
    return out


_GENERIC = {"lesson", "plan", "presentation", "about", "grade", "class", "introduction", "short", "quiz", "cards", "slides"}


def filter_curriculum(cdc_context: str, sources: list, topic: str):
    """Drop retrieved curriculum text that has nothing to do with the topic (e.g. 'electric field' for atoms)."""
    tk = _kw(topic) - _GENERIC
    if not tk:
        return cdc_context, sources
    if not (tk & _kw(cdc_context)):
        return "No curriculum context available.", []
    keep = []
    for src in sources:
        text = " ".join(str(v) for v in src.values()) if isinstance(src, dict) else str(src)
        if tk & _kw(text):
            keep.append(src)
    return cdc_context, keep


def _lang_instruction(language: str) -> str:
    if language == "nepali":
        return """LANGUAGE POLICY: 100% PURE NEPALI (नेपाली).
- Write everything strictly in pure Nepali using Devanagari script.
- ABSOLUTELY PROHIBITED HINDI WORDS: 'और', 'दशक', 'मूल्य ज्ञात करना', 'सैकड़ा', 'ज्ञात कीजिए', 'अंतर'.
- MANDATORY NEPALI TERMS: Use 'र', 'दहाइ', 'मान पत्ता लगाउने', 'सय', 'पत्ता लगाउनुहोस्', 'फरक'.
"""
    return """LANGUAGE POLICY: 100% PROFESSIONAL ENGLISH.
- Write all content in clean, professional English. Do not use Nepali script.
"""


def _material_block(material_text: str) -> str:
    if not material_text:
        return ""
    return ("\nTEACHER'S UPLOADED MATERIAL (base the lesson on this content; do not invent facts beyond it):\n"
            + material_text + "\n\n")


def _chat_json(prompt: str, num_predict: int, temperature: float = 0.3) -> dict:
    resp = ollama.chat(
        model=MODEL,
        messages=[{"role": "system", "content": "You output only valid JSON. You never add markdown or commentary."},
                  {"role": "user", "content": prompt}],
        format="json",
        options={"temperature": temperature, "num_predict": num_predict, "num_ctx": 12288},
    )
    raw = resp["message"]["content"]
    return json.loads(re.search(r"\{.*\}", raw, re.DOTALL).group(0))


# ----------------------------------------------------------------------------- stage A: slide content
def normalize_plan(plan: dict) -> dict:
    """Repair small mistakes in model JSON so later steps can rely on its shape."""
    slides = plan.get("slides")
    if not isinstance(slides, list):
        plan["slides"] = []
        return plan
    clean = []
    for n, s in enumerate(slides, 1):
        if not isinstance(s, dict):
            continue
        for k in ("title", "key_idea", "explanation", "example", "visual_desc"):
            s[k] = clean_meta_text(_s(s.get(k)))
        b = s.get("bullets")
        if isinstance(b, str):
            b = _sentences(b)
        s["bullets"] = [clean_meta_text(str(x)) for x in (b or []) if _s(x)]
        terms = s.get("key_terms")
        s["key_terms"] = [
            {"term": clean_meta_text(_s(t.get("term"))), "meaning": clean_meta_text(_s(t.get("meaning")))}
            for t in terms if isinstance(t, dict) and _s(t.get("term"))
        ] if isinstance(terms, list) else []
        if s.get("slide_type") not in ("intro", "concept", "example", "review"):
            s["slide_type"] = "concept"
        s["slide_number"] = n
        # teacher-only fields are filled in by stage B, never by the content writer
        for k in ("teacher_script", "communication_support", "sensory_note"):
            s[k] = ""
        s["braille_text"], s["nsl_gestures"] = {}, []
        clean.append(s)
    plan["slides"] = clean
    return plan


def evaluate_content_plan(plan: dict, language: str, topic: str = "") -> tuple:
    """Checks that slides TEACH the topic: no instructions, no fragments, no repeats, topic-relevant."""
    feedback, score = [], 10
    slides = plan.get("slides", [])
    if not 5 <= len(slides) <= 7:
        score -= 2
        feedback.append(f"Produce between 5 and 7 slides (got {len(slides)}).")

    seen, tk = set(), _kw(topic) - _GENERIC
    on_topic = 0
    for idx, s in enumerate(slides, 1):
        penalty = 0
        bullets = s.get("bullets", [])
        if not 2 <= len(bullets) <= 3:
            penalty += 1
            feedback.append(f"Slide {idx} must have 2 or 3 bullets (got {len(bullets)}).")
        for b in bullets + [s.get("key_idea", "")]:
            if not b:
                continue
            if IMPERATIVE.match(b) or META.search(b):
                penalty += 1
                feedback.append(f"Slide {idx} text '{b}' is an instruction or teacher talk. Write a FACT about the topic.")
            key = re.sub(r"\W+", " ", b.lower()).strip()
            if key in seen:
                penalty += 1
                feedback.append(f"Slide {idx} repeats '{b}'. Every slide needs new content.")
            seen.add(key)
        for b in bullets:
            n = len(b.split())
            if n < 5:
                penalty += 1
                feedback.append(f"Slide {idx} bullet '{b}' is a fragment. Write a full factual sentence of 6 to 14 words.")
            elif n > 16:
                penalty += 1
                feedback.append(f"Slide {idx} bullet '{b}' is longer than 16 words.")
        ki = (s.get("key_idea") or "").strip()
        if not ki:
            penalty += 1
            feedback.append(f"Slide {idx} has no key_idea sentence.")
        elif not 6 <= len(ki.split()) <= 26:
            penalty += 1
            feedback.append(f"Slide {idx} key_idea must be one factual sentence of 6 to 26 words.")
        expl = (s.get("explanation") or "").strip()
        if not expl or len(expl.split()) < 8:
            penalty += 1
            feedback.append(f"Slide {idx} needs an explanation of 2 to 3 sentences about the topic.")
        elif any(len(x.split()) > 20 for x in _sentences(expl)):
            penalty += 1
            feedback.append(f"Slide {idx} explanation has a sentence over 20 words.")
        if not (s.get("example") or "").strip():
            penalty += 1
            feedback.append(f"Slide {idx} has no example.")
        score -= min(penalty, 2)

        blob = " ".join([s.get("title", ""), ki, expl] + bullets + [t["term"] for t in s.get("key_terms", [])])
        if not tk or (tk & _kw(blob)):
            on_topic += 1

    examples = [(s.get("example") or "").strip().lower() for s in slides if (s.get("example") or "").strip()]
    if examples and len(set(examples)) < len(examples) - 1:
        score -= 2
        feedback.append("Examples repeat across slides. Give each slide its own different example.")
    if slides and on_topic < max(1, round(len(slides) * 0.4)):
        score -= 2
        feedback.append(f"Slides drift away from the topic '{topic}'. Every slide must teach part of it.")

    if language == "nepali":
        raw_str = json.dumps(plan, ensure_ascii=False)
        found = [w for w in ['और', 'दशक', 'मूल्य ज्ञात करना', 'सैकड़ा', 'ज्ञात कीजिए', 'अंतर'] if w in raw_str]
        if found:
            score -= 3
            feedback.append(f"Replace Hindi terms {found} with pure Nepali terms ('र', 'दहाइ', etc.).")
    return score, feedback


evaluate_asd_plan = evaluate_content_plan  # old name kept so other imports do not break


def plan_slide_content(topic, grade, subject, language, cdc_context, material_text, user_prompt, say) -> dict:
    best, best_score, feedback = {}, -99, []
    for attempt in range(1, 4):
        say(f"Writing the lesson content (attempt {attempt} of 3)...")
        fb = ""
        if feedback:
            fb = "\nCORRECTIONS REQUIRED (fix all of these):\n" + "".join(f"- {x}\n" for x in feedback[:12]) + "\n"
        prompt = f"""You write the SLIDES a teacher will show to students about: {topic}  (Grade {grade}, {subject}).

{_lang_instruction(language)}
CURRICULUM CONTEXT (use only if it is about this topic):
{cdc_context}

TEACHER REQUEST: {user_prompt}
{_material_block(material_text)}{fb}
The slides TEACH THE TOPIC. Every line is a statement of fact about the subject matter.
Slides NEVER contain instructions to the teacher or the student, and never mention "the teacher", "students", lesson activities or drawing tasks.

GOOD bullet: "Chlorophyll in the leaf absorbs light from the sun."
BAD bullet:  "Draw the leaf" / "Label the parts" / "Experiment shows" / "Point to the diagram"

RULES:
1. Literal language: no idioms or metaphors. Level: Grade {grade} (not simpler than that).
2. 5 to 7 slides, in this order: what it is (intro) -> 3 or 4 slides with one idea each -> evidence, worked example or application -> summary (review).
3. Each slide teaches something the others do not. No repeated bullets, no repeated examples.
4. key_idea: ONE factual sentence, 10 to 22 words.
5. bullets: 2 or 3 full factual sentences, 6 to 14 words each, each with a subject and a verb.
6. explanation: 2 to 3 short sentences (max 20 words each) that explain the idea.
7. example: a concrete example specific to THIS slide. Use a Nepali everyday example only where it truly fits the science.
8. key_terms: 1 to 2 important words with simple meanings.
9. visual_desc: what a diagram for THIS slide would show, with its labels (e.g. "alpha particles hitting thin gold foil, most pass through, a few bounce back").
10. Use the teacher's material for facts when it is given.

Return STRICT JSON:
{{
  "lesson_meta": {{"title": "short literal topic title", "duration_minutes": 30}},
  "slides": [
    {{"slide_type": "intro | concept | example | review",
      "title": "2 to 5 word topic heading",
      "key_idea": "...", "bullets": ["...", "..."], "explanation": "...", "example": "...",
      "key_terms": [{{"term": "...", "meaning": "..."}}], "visual_desc": "..."}}
  ]
}}
Output ONLY valid JSON."""
        try:
            plan = normalize_plan(_chat_json(prompt, num_predict=5000))
            score, feedback = evaluate_content_plan(plan, language, topic)
            print(f"  [Content Evaluator] pass {attempt}: {score}/10")
            if plan["slides"] and score > best_score:
                best, best_score = plan, score
            if score >= 8:
                break
        except Exception as e:
            print(f"[Pipeline] Content writer error on pass {attempt}: {e}")
            feedback = [f"Previous answer was not valid JSON ({e}). Return only the JSON object."]
    return best


# ----------------------------------------------------------------------------- stage B: teacher support + IEP
def plan_teacher_support(plan, topic, grade, subject, language, say) -> dict:
    summary = "\n".join(f'{s["slide_number"]}. {s["title"]}: {s["key_idea"]}' for s in plan["slides"])
    feedback, support = "", {}
    for attempt in range(1, 3):
        say(f"Writing teacher support and the IEP goal (attempt {attempt} of 2)...")
        prompt = f"""You are a special education specialist for autistic learners (ASD) in Nepal's CDC curriculum.
{_lang_instruction(language)}
The lesson slides are already written (they teach the topic). Write ONLY the TEACHER-SIDE support.
TOPIC: {topic} | GRADE: {grade} | SUBJECT: {subject}
SLIDES:
{summary}
{feedback}
Rules:
- teacher_script: 1 or 2 short literal sentences the teacher says to introduce THAT slide, then one simple question. Do not copy the slide text word for word.
- communication_support: how the student can answer THAT slide's question (point to a card, say a word, use AAC, nod). Be specific to the slide.
- sensory_note: only a real, specific sensory consideration for that slide, otherwise null.
- iep_goal must be SMART, about THIS topic, include a number (%, trials or minutes), and a baseline probe.
- local_context_used: Nepali examples only where they genuinely help; an empty list is fine.
- Literal language only, no idioms.

Return STRICT JSON:
{{
  "slides": [{{"slide_number": 1, "teacher_script": "...", "communication_support": "...", "sensory_note": null}}],
  "visual_schedule": [
    {{"step": 1, "label": "First", "icon_desc": "...", "duration_min": 5}},
    {{"step": 2, "label": "Then", "icon_desc": "...", "duration_min": 10}},
    {{"step": 3, "label": "Last", "icon_desc": "...", "duration_min": 10}},
    {{"step": 4, "label": "Done", "icon_desc": "...", "duration_min": 5}}
  ],
  "iep_goal": {{"goal_statement_nepali": "SMART goal in Devanagari", "goal_statement_english": "SMART goal in English",
                "baseline_probe": "...", "measurable_criteria": "e.g. 80% accuracy across 5 consecutive sessions",
                "progress_monitoring": "..."}},
  "accommodations": ["..."], "modifications": ["..."],
  "prompt_hierarchy": ["independent", "verbal", "visual", "gestural", "physical"],
  "reinforcement_plan": {{"preferred_reinforcer": "...", "schedule": "...", "first_then_statement": "First [task], then [reinforcer]"}},
  "sensory_accommodations": ["..."], "calm_down_strategy": "...", "local_context_used": ["..."]
}}
Output ONLY valid JSON."""
        try:
            support = _chat_json(prompt, num_predict=3500)
            iep = support.get("iep_goal") or {}
            problems = []
            if not _s(iep.get("baseline_probe")):
                problems.append("iep_goal.baseline_probe is missing.")
            if not re.search(r"\d", _s(iep.get("measurable_criteria"))):
                problems.append("iep_goal.measurable_criteria needs a number (%, trials or minutes).")
            if not problems:
                break
            feedback = "\nCORRECTIONS REQUIRED:\n" + "".join(f"- {p}\n" for p in problems)
        except Exception as e:
            print(f"[Pipeline] Support writer error on pass {attempt}: {e}")
            feedback = "\nPrevious answer was not valid JSON. Return only the JSON object.\n"
    return support if isinstance(support, dict) else {}


def merge_support(plan: dict, support: dict, topic: str) -> dict:
    by_num = {}
    for x in support.get("slides") or []:
        if isinstance(x, dict):
            try:
                by_num[int(x.get("slide_number"))] = x
            except (TypeError, ValueError):
                pass
    for s in plan["slides"]:
        x = by_num.get(s["slide_number"], {})
        s["teacher_script"] = _s(x.get("teacher_script"))
        s["communication_support"] = _s(x.get("communication_support"))
        s["sensory_note"] = _s(x.get("sensory_note"))
    iep = support.get("iep_goal") if isinstance(support.get("iep_goal"), dict) else {}
    iep.setdefault("baseline_probe", f"Ask 5 questions about {topic} and record how many the student answers correctly.")
    iep.setdefault("measurable_criteria", "80% correct across 3 consecutive sessions")
    plan["iep_goal"] = iep
    for k in ("visual_schedule", "accommodations", "modifications", "prompt_hierarchy", "reinforcement_plan",
              "sensory_accommodations", "calm_down_strategy", "local_context_used"):
        if support.get(k):
            plan[k] = support[k]
    return plan


# ----------------------------------------------------------------------------- intent
def classify_intent_and_extract_params(user_prompt: str) -> dict:
    """Classifies user intent and extracts educational metadata from prompt."""
    system_prompt = """You are the Master Intent Classifier for DraftBench.
Analyze the user prompt and return a strict JSON object with:
{
  "intent": "chat" | "presentation" | "document" | "quiz" | "braille" | "nsl",
  "topic": string or null,
  "grade": integer (1 to 12, default 7 if unspecified),
  "subject": string (e.g. "Mathematics", "Science", "English", "Nepali", "Social Studies"),
  "language": "nepali" | "english",
  "needs_autism_adaptations": boolean
}
CRITICAL RULES:
- Set "intent" to "braille" if the user specifically requests Braille translations or Tactile learning materials.
- Set "intent" to "nsl" if the user specifically requests Nepali Sign Language or Deaf-accessible materials.
- Set "language" to "nepali" if the prompt is written in Nepali/Devanagari script, otherwise set it to "english".
- Output ONLY valid JSON.
"""
    response = ollama.chat(
        model=MODEL,
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        options={"temperature": 0.0},
    )
    try:
        raw = response["message"]["content"]
        return json.loads(re.search(r'\{.*\}', raw, re.DOTALL).group(0))
    except Exception:
        has_devanagari = bool(re.search(r'[\u0900-\u097F]', user_prompt))
        return {"intent": "document", "grade": 7, "subject": "Mathematics",
                "language": "nepali" if has_devanagari else "english", "needs_autism_adaptations": True}


# ----------------------------------------------------------------------------- main
def run_unified_pipeline(
    user_prompt: str,
    session_id: str = "default_session",
    forced_intent: str = None,
    forced_grade: int = None,
    forced_subject: str = None,
    forced_language: str = None,
    material_text: str = "",
    material_images: list = None,
    file_tag: str = "",
    num_questions: int = 8,
    on_progress=None,
) -> dict:
    """Executes the DraftBench pipeline: slides and lesson plan/IEP here; quiz, braille and NSL in special_outputs."""
    say = on_progress or (lambda msg: None)
    say("Understanding your request...")
    print("Step[1]...Resolving settings & session state...")
    if forced_intent and forced_grade and forced_subject and forced_language:
        extracted_params = {"intent": forced_intent, "grade": forced_grade, "subject": forced_subject,
                            "language": forced_language, "topic": None}
    else:
        extracted_params = classify_intent_and_extract_params(user_prompt)
        for key, val in (("intent", forced_intent), ("grade", forced_grade),
                         ("subject", forced_subject), ("language", forced_language)):
            if val:
                extracted_params[key] = val

    topic = extracted_params.get("topic") or derive_topic(user_prompt)
    extracted_params["topic"] = topic
    session = get_or_update_session(session_id, extracted_params)

    intent = extracted_params.get("intent", "document")
    language, grade, subject = session["language"], session["grade"], session["subject"]
    print(f"[Pipeline] Intent: {intent.upper()} | Language: {language.upper()} | Grade: {grade} | Subject: {subject} | Topic: {topic}")

    # --- Step 2: curriculum retrieval, searched with the TOPIC and filtered for relevance ---
    print("Step[2]...Retrieving CDC Curriculum Context via RAG...")
    say("Looking up the curriculum...")
    try:
        cdc_context, sources = query_curriculum_rag(user_query=topic, grade_filter=grade, subject_filter=subject, top_k=3)
        cdc_context, sources = filter_curriculum(cdc_context, sources, topic)
    except Exception as e:
        print(f"[Pipeline] RAG unavailable: {e}")
        cdc_context, sources = "No curriculum context available.", []

    sources = [
        f"{m.get('subject', '')} Grade {m.get('grade', '')} {m.get('topic', '')} ({m.get('source_file', '')})"
        if isinstance(m, dict) else str(m)
        for m in sources
    ]

    # --- Separate sections: quiz, braille cards and sign-language cards skip the lesson planner ---
    if intent in ("quiz", "braille", "nsl"):
        from agents.special_outputs import run_special_output
        return run_special_output(
            intent=intent, user_prompt=user_prompt, grade=grade, subject=subject, language=language,
            topic=topic, cdc_context=cdc_context, sources=sources, material_text=material_text,
            num_questions=num_questions, say=say, export_dir=EXPORT_DIR, file_tag=file_tag,
        )

    # --- Step 3: slide CONTENT (about the topic), then TEACHER SUPPORT (about teaching it) ---
    print("Step[3]...Writing lesson content, then teacher support...")
    plan = plan_slide_content(topic, grade, subject, language, cdc_context, material_text, user_prompt, say)
    if not plan or not plan.get("slides"):
        return {"error": "planner_failed", "message": "The AI couldn't write the lesson content. Try again or simplify the request."}
    support = plan_teacher_support(plan, topic, grade, subject, language, say)
    plan = merge_support(plan, support, topic)

    # --- Step 3c: pictures from the teacher's files, matched by content; no match = no picture ---
    matched = 0
    if material_images:
        say("Choosing pictures from your files...")
        try:
            from agents.image_matcher import assign_images
            matched = assign_images(plan.get("slides", []), material_images, material_text)
        except Exception as e:
            print(f"[Pipeline] Picture matching failed: {e}")
    print(f"[Pipeline] Pictures matched from uploaded files: {matched}")

    # --- Step 4: optional AI-drawn pictures (off by default) ---
    png_paths = []
    if USE_AI_SVG:
        lesson_topic_str = plan.get("lesson_meta", {}).get("title", topic)
        for n, slide in enumerate(plan.get("slides", []), 1):
            if slide.get("image_path"):
                continue
            say(f"Drawing picture symbols ({n} of {len(plan['slides'])})...")
            try:
                path = generate_educational_svg(
                    vdescription=slide.get("visual_desc") or f"{subject} concept icon",
                    filename_prefix=f"G{grade}", grade=grade, lesson_topic=lesson_topic_str,
                    iep_goal=plan.get("iep_goal", {}).get("goal_statement_english", ""), language=language)
                slide["png_path"] = path
                if path:
                    png_paths.append(path)
            except Exception as err:
                print(f"[Pipeline] Error generating PNG: {err}")

    # --- Step 5: build the file ---
    print(f"Step[5]...Routing Execution for Intent: [{intent.upper()}]...")
    say("Building your file...")
    os.makedirs(EXPORT_DIR, exist_ok=True)
    stem = f"DraftBench_G{grade}_{subject.replace(' ', '_')}_{language.capitalize()}"

    master_text = build_lesson_markdown(plan=plan, subject=subject, grade=grade, language=language, sources=sources)
    result = {"session_id": session_id, "intent": intent, "grade": grade, "subject": subject, "language": language,
              "sources": sources, "plan_json": plan, "image_assets": png_paths, "files": {}}

    if intent == "chat":
        result["response_text"] = master_text
    elif intent == "presentation":
        pptx_path = os.path.join(EXPORT_DIR, f"{stem}_Presentation{file_tag}.pptx")
        slides_for_deck = [dict(s, bullets=(s.get("bullets") or [])[:3], icon_path=s.get("png_path"))
                           for s in plan.get("slides", [])]
        generate_styled_pptx(
            slides_data=slides_for_deck, output_path=pptx_path, grade=grade, subject=subject, image_paths=None,
            language=language, lesson_title=plan.get("lesson_meta", {}).get("title"),
            visual_schedule=None, cdc_outcome=None,
        )
        result["response_text"] = "Presentation generated successfully."
        result["files"] = {"pptx": pptx_path}
    else:  # document: lesson plan + IEP
        pdf_path = os.path.join(EXPORT_DIR, f"{stem}_Report{file_tag}.pdf")
        generate_styled_pdf(master_text, pdf_path, None, intent="document", language=language, grade=grade, subject=subject)
        result["response_text"] = "Lesson plan and IEP generated successfully."
        result["files"] = {"pdf": pdf_path}
    return result
