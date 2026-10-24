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

# Import Accessibility Tools
from agents.accessibility_tools import (
    return_braille,
    get_nsl_gesture_description_for_single_textblock,
    get_nsl_gesture_description_for_single_word
)

# Global in-memory session store for state persistence across turns
SESSION_STORE = {}
EXPORT_DIR = os.path.join(PROJECT_ROOT, "data", "exports")


def get_or_update_session(session_id: str, current_params: dict) -> dict:
    """Retrieve or update in-memory session parameters across chat turns."""
    if session_id not in SESSION_STORE:
        SESSION_STORE[session_id] = {
            "grade": 7,
            "subject": "Mathematics",
            "language": "english",
            "topic": None
        }

    session = SESSION_STORE[session_id]
    for key in ["grade", "subject", "language", "topic"]:
        if current_params.get(key):
            session[key] = current_params[key]

    return session


def _sentences(text: str) -> list:
    return [x for x in re.split(r"(?<=[.!?।])\s+", text or "") if x.strip()]


def normalize_plan(plan: dict) -> dict:
    """Repair the usual small mistakes in the model's JSON so later steps can rely on its shape."""
    slides = plan.get("slides")
    if not isinstance(slides, list):
        plan["slides"] = []
        return plan
    clean = []
    for n, s in enumerate(slides, 1):
        if not isinstance(s, dict):
            continue
        b = s.get("bullets")
        if isinstance(b, str):
            b = _sentences(b)
        s["bullets"] = [str(x).strip() for x in (b or []) if str(x).strip()]
        terms = s.get("key_terms")
        s["key_terms"] = [t for t in terms if isinstance(t, dict) and t.get("term")] if isinstance(terms, list) else []
        sp = s.get("source_page")
        s["source_page"] = int(sp) if (isinstance(sp, (int, float)) and not isinstance(sp, bool)) or (isinstance(sp, str) and sp.strip().isdigit()) else None
        if s.get("slide_type") not in ("intro", "concept", "example", "review"):
            s["slide_type"] = "concept"
        s["slide_number"] = n
        
        # Ensure accessibility fields exist
        if "braille_text" not in s:
            s["braille_text"] = {}
        if "nsl_gestures" not in s or not isinstance(s["nsl_gestures"], list):
            s["nsl_gestures"] = []

        clean.append(s)
    plan["slides"] = clean
    return plan


def evaluate_asd_plan(plan: dict, language: str) -> tuple[int, list]:
    """
    Evaluator Agent: reviews the generated plan against the ASD rubric, checks that slides actually
    teach (not just list keywords), and enforces the language policy (pure Nepali vs English).
    """
    feedback = []
    score = 10

    slides = plan.get("slides", [])
    if not 5 <= len(slides) <= 7:
        score -= 2
        feedback.append(f"Produce between 5 and 7 slides (got {len(slides)}).")

    for idx, slide in enumerate(slides, 1):
        penalty = 0
        bullets = slide.get("bullets", [])
        if len(bullets) > 3:
            penalty += 2
            feedback.append(f"Slide {idx} has {len(bullets)} bullets (max 3 allowed).")
        for b in bullets:
            n = len(b.split())
            if n < 3:
                penalty += 1
                feedback.append(f"Slide {idx} bullet '{b}' is too short. Write a full phrase of 4 to 12 words.")
            elif n > 12:
                penalty += 1
                feedback.append(f"Slide {idx} bullet '{b}' is longer than 12 words.")
        if not (slide.get("key_idea") or "").strip():
            penalty += 1
            feedback.append(f"Slide {idx} has no key_idea sentence.")
        expl = (slide.get("explanation") or "").strip()
        if not expl:
            penalty += 2
            feedback.append(f"Slide {idx} has no explanation. Write 2 to 4 short sentences that explain the idea.")
        elif any(len(sen.split()) > 18 for sen in _sentences(expl)):
            penalty += 1
            feedback.append(f"Slide {idx} explanation has a sentence over 18 words. Use shorter sentences.")
        score -= min(penalty, 2)

    # Measurable IEP goal validation
    iep = plan.get("iep_goal", {})
    if not iep.get("baseline_probe") or not iep.get("measurable_criteria"):
        score -= 2
        feedback.append("IEP Goal is missing measurable criteria or baseline probe.")

    # Pure Nepali policy enforcement (prohibit Hindi loanwords)
    if language == "nepali":
        raw_str = json.dumps(plan, ensure_ascii=False)
        prohibited = ['और', 'दशक', 'मूल्य ज्ञात करना', 'सैकड़ा', 'ज्ञात कीजिए', 'अंतर']
        found = [w for w in prohibited if w in raw_str]
        if found:
            score -= 3
            feedback.append(f"Replace Hindi terms {found} with pure Nepali terms ('र', 'दहाइ', etc.).")

    return score, feedback


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
        model="qwen2.5:7b-instruct",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        options={"temperature": 0.0}
    )

    try:
        raw = response["message"]["content"]
        clean_json = re.search(r'\{.*\}', raw, re.DOTALL).group(0)
        return json.loads(clean_json)
    except Exception:
        has_devanagari = bool(re.search(r'[\u0900-\u097F]', user_prompt))
        return {
            "intent": "document",
            "grade": 7,
            "subject": "Mathematics",
            "language": "nepali" if has_devanagari else "english",
            "needs_autism_adaptations": True
        }


def enrich_slides_with_accessibility(plan: dict, language: str, say_func=None) -> dict:
    """Enriches each slide in the plan with Braille translations and NSL gesture descriptions."""
    say = say_func or (lambda msg: None)
    slides = plan.get("slides", [])
    total = len(slides)

    for i, slide in enumerate(slides, 1):
        say(f"Generating Braille and NSL gestures ({i} of {total})...")
        print(f"  [Accessibility] Processing Slide {i}/{total}...")

        # 1. Generate Braille patterns for Title, Key Idea, and Bullets
        slide["braille_text"] = {
            "title_braille": return_braille(slide.get("title", "")),
            "key_idea_braille": return_braille(slide.get("key_idea", "")),
            "bullets_braille": [return_braille(b) for b in slide.get("bullets", [])]
        }

        # 2. Extract key concepts and build NSL Gesture Descriptions
        combined_text = f"{slide.get('title', '')}. {slide.get('key_idea', '')}. {' '.join(slide.get('bullets', []))}"
        nsl_items = get_nsl_gesture_description_for_single_textblock(combined_text, language=language)
        
        slide["nsl_gestures"] = nsl_items

    return plan


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
    on_progress=None,
) -> dict:
    """Executes the complete DraftBench pipeline with self-correction and multi-format exporting."""
    # --- Step 1: Intent Classification & Session State Synchronization ---
    say = on_progress or (lambda msg: None)
    say("Understanding your request...")
    print("Step[1]...Resolving settings & session state...")
    if forced_intent and forced_grade and forced_subject and forced_language:
        extracted_params = {
            "intent": forced_intent,
            "grade": forced_grade,
            "subject": forced_subject,
            "language": forced_language,
            "topic": None
        }
    else:
        extracted_params = classify_intent_and_extract_params(user_prompt)
        for key, val in (("intent", forced_intent), ("grade", forced_grade),
                         ("subject", forced_subject), ("language", forced_language)):
            if val:
                extracted_params[key] = val
    session = get_or_update_session(session_id, extracted_params)

    intent = extracted_params.get("intent", "document")
    language = session["language"]
    grade = session["grade"]
    subject = session["subject"]
    topic = extracted_params.get("topic") or session["topic"] or user_prompt

    print(f"[Pipeline] Intent: {intent.upper()} | Language: {language.upper()} | Grade: {grade} | Subject: {subject}")

    # --- Step 2: RAG Context Retrieval ---
    print("Step[2]...Retrieving CDC Curriculum Context via RAG...")
    say("Looking up the curriculum...")
    try:
        cdc_context, sources = query_curriculum_rag(
            user_query=user_prompt,
            grade_filter=grade,
            subject_filter=subject,
            top_k=3
        )
    except Exception as e:
        print(f"[Pipeline] RAG unavailable: {e}")
        cdc_context, sources = "No curriculum context available.", []

    sources = [
        f"{m.get('subject', '')} Grade {m.get('grade', '')} {m.get('topic', '')} ({m.get('source_file', '')})"
        if isinstance(m, dict) else str(m)
        for m in sources
    ]

    # --- Step 3: CoIEP Writer-Evaluator Loop ---
    print("Step[3]...Planning content with CoIEP Evaluator Loop...")

    if language == "nepali":
        lang_instruction = """LANGUAGE POLICY: 100% PURE NEPALI (नेपाली).
- Write all titles, slides, bullets, teacher scripts, and IEP goals strictly in pure Nepali using Devanagari script.
- ABSOLUTELY PROHIBITED HINDI WORDS: 'और', 'दशक', 'मूल्य ज्ञात करना', 'सैकड़ा', 'ज्ञात कीजिए', 'अंतर'.
- MANDATORY NEPALI TERMS: Use 'र', 'दहाइ', 'मान पत्ता लगाउने', 'सय', 'पत्ता लगाउनुहोस्', 'फरक'.
"""
    else:
        lang_instruction = """LANGUAGE POLICY: 100% PROFESSIONAL ENGLISH.
- Write all content in clean, professional English. Do not use Nepali script.
"""

    material_block = ""
    if material_text:
        material_block = (
            "\nTEACHER'S UPLOADED MATERIAL (base the lesson on this content; do not invent facts beyond it):\n"
            + material_text + "\n\n"
        )

    evaluator_feedback = []
    attempt = 0
    max_attempts = 3
    plan = {}

    while attempt < max_attempts:
        attempt += 1
        print(f"  [CoIEP Loop] Planner Pass {attempt}/{max_attempts}...")
        say(f"Writing the lesson plan (attempt {attempt} of {max_attempts})...")

        feedback_str = ""
        if evaluator_feedback:
            feedback_str = (
                "\nCRITICAL CORRECTIONS REQUIRED FROM EVALUATOR:\n"
                + "\n".join(f"- {item}" for item in evaluator_feedback)
                + "\n"
            )

        planner_prompt = f"""You are an expert special education content designer for Autism Spectrum Disorder (ASD), grounded in Nepal's CDC curriculum.

{lang_instruction}

CDC CONTEXT (from RAG):
{cdc_context}

TEACHER REQUEST: {user_prompt}
{material_block}TOPIC: {topic} | GRADE: {grade} | SUBJECT: {subject}
{feedback_str}
DESIGN RULES (evidence-based ASD practices):
1. LITERAL LANGUAGE ONLY — no idioms, metaphors, or sarcasm. Every sentence <= 15 words. Never write a bullet that is a single word or half a sentence.
2. ONE CONCEPT PER SLIDE — maximum 3 bullets per slide. Each bullet is a complete phrase of 4 to 12 words.
3. VISUAL-FIRST — every abstract concept gets a simple, literal icon description.
4. SENSORY SAFETY — flag any potential trigger (loud video, bright colors, strong smell).
5. PREDICTABILITY — include a visual schedule using First / Then / Last / Done.
6. COMMUNICATION ACCESS — for each slide, state how the student can respond (point, gesture, say, use AAC).
7. STRENGTHS-BASED — connect content to concrete everyday interests.
8. LOCAL CONTEXT — use Nepali examples (rupees, festivals, native plants) at least twice.
9. MEASURABLE IEP GOAL — must include a number (%, trials, or time) and a baseline probe.
10. EXPLAIN PROPERLY — every slide teaches. Give a key_idea (one sentence), an explanation (2 to 4 short sentences that really explain the idea) and one concrete example. When TEACHER'S UPLOADED MATERIAL is provided, take the facts, terms and examples from it, in your own simple words.
11. SOURCE PAGE — when the uploaded material has [Page N] markers, set source_page to the page the slide is based on, otherwise null.

Return STRICT JSON in this exact schema:
{{
  "lesson_meta": {{
    "title": "short literal title",
    "duration_minutes": 30,
    "cdc_outcome_ref": "the CDC standard addressed"
  }},
  "visual_schedule": [
    {{"step": 1, "label": "First", "icon_desc": "simple icon", "duration_min": 5}},
    {{"step": 2, "label": "Then",  "icon_desc": "simple icon", "duration_min": 10}},
    {{"step": 3, "label": "Last",  "icon_desc": "simple icon", "duration_min": 10}},
    {{"step": 4, "label": "Done",  "icon_desc": "simple icon", "duration_min": 5}}
  ],
  "slides": [
    {{
      "slide_number": 1,
      "slide_type": "intro | concept | example | review",
      "title": "short literal title",
      "key_idea": "one sentence that states the main idea",
      "bullets": ["3 key points", "each a full phrase of 4 to 12 words", "never a single word"],
      "explanation": "2 to 4 short sentences that explain the idea simply",
      "example": "one concrete everyday example",
      "key_terms": [{{"term": "important word", "meaning": "simple meaning"}}],
      "source_page": 1,
      "visual_desc": "what picture would help show this idea",
      "sensory_note": "any sensory consideration or null",
      "communication_support": "how student responds (point / say / gesture / AAC)",
      "teacher_script": "exact short literal words the teacher can say"
    }}
  ],
  "iep_goal": {{
    "goal_statement_nepali": "SMART goal in Devanagari",
    "goal_statement_english": "SMART goal in English",
    "baseline_probe": "how to measure where the student starts",
    "measurable_criteria": "e.g. 80% accuracy across 5 consecutive sessions",
    "progress_monitoring": "how and how often to collect data"
  }},
  "accommodations": ["how the student accesses learning"],
  "modifications": ["what is changed about the content"],
  "prompt_hierarchy": ["independent", "verbal", "visual", "gestural", "physical"],
  "reinforcement_plan": {{
    "preferred_reinforcer": "a concrete everyday item or activity",
    "schedule": "token board every 2 correct responses",
    "first_then_statement": "First [task], then [reinforcer]"
  }},
  "sensory_accommodations": ["specific supports for this lesson"],
  "calm_down_strategy": "what to do if the student is overwhelmed",
  "local_context_used": ["Nepali examples used"]
}}

CRITICAL:
- Produce 5 to 7 slides: 1 intro slide (what we will learn), 3 to 4 concept slides, 1 example or practice slide, and 1 review slide (slide_type "review").
- Output ONLY valid JSON. No markdown fences, no commentary.
- If a field cannot be filled, use null — never invent facts."""

        response = ollama.chat(
            model="qwen2.5:7b-instruct",
            messages=[
                {"role": "system", "content": "You output only valid JSON. You never add markdown or commentary."},
                {"role": "user", "content": planner_prompt}
            ],
            format="json",
            options={"temperature": 0.3, "num_predict": 6000, "num_ctx": 12288}
        )

        try:
            raw = response["message"]["content"]
            clean_json = re.search(r'\{.*\}', raw, re.DOTALL).group(0)
            plan = normalize_plan(json.loads(clean_json))

            score, evaluator_feedback = evaluate_asd_plan(plan, language)
            print(f"  [CoIEP Evaluator] Score: {score}/10")

            if score >= 8:
                print(f"[Pipeline] Plan passed evaluator check on pass {attempt}.")
                break
            else:
                print("  [CoIEP Evaluator] Rejected. Regenerating with feedback...")

        except Exception as e:
            print(f"[Pipeline] Planner error on pass {attempt}: {e}")
            evaluator_feedback = [f"Failed to produce valid JSON format: {str(e)}"]

    if not plan:
        return {"error": "planner_failed"}

    # --- Step 3b: Enrich Slides with Braille & NSL Gestures ---
    print("Step[3b]...Enriching slides with Braille & NSL Gestures...")
    plan = enrich_slides_with_accessibility(plan, language=language, say_func=say)

    # --- Step 3c: Picture Matching ---
    matched = 0
    if material_images:
        say("Choosing pictures from your files...")
        try:
            from agents.image_matcher import assign_images
            matched = assign_images(plan.get("slides", []), material_images)
        except Exception as e:
            print(f"[Pipeline] Picture matching failed: {e}")
    print(f"[Pipeline] Pictures matched from uploaded files: {matched}")

    # --- Step 4: Visual PECS SVG/PNG Generation ---
    print("Step[4]...Generating visual PNG assets...")
    png_paths = []
    if intent in ["presentation", "document", "quiz", "braille", "nsl"]:
        lesson_topic_str = plan.get("lesson_meta", {}).get("title", topic)
        iep_goal_str = plan.get("iep_goal", {}).get("goal_statement_english", "")
        for n, slide in enumerate(plan.get("slides", []), 1):
            if slide.get("image_path"):
                continue
            say(f"Drawing picture symbols ({n} of {len(plan.get('slides', []))})...")
            visual_desc = slide.get("visual_desc") or f"{subject} concept icon"
            try:
                path = generate_educational_svg(
                    vdescription=visual_desc,
                    filename_prefix=f"G{grade}",
                    grade=grade,
                    lesson_topic=lesson_topic_str,
                    iep_goal=iep_goal_str
                )
                slide["png_path"] = path
                if path:
                    png_paths.append(path)
            except Exception as err:
                print(f"[Pipeline] Error generating PNG for '{visual_desc}': {err}")
                slide["png_path"] = None

    # --- Step 5: Document Building & Format Exporting ---
    print(f"Step[5]...Routing Execution for Intent: [{intent.upper()}]...")
    say("Building your file...")
    os.makedirs(EXPORT_DIR, exist_ok=True)

    master_text = build_lesson_markdown(
        plan=plan,
        subject=subject,
        grade=grade,
        language=language,
        sources=sources
    )

    execution_result = {
        "session_id": session_id,
        "intent": intent,
        "grade": grade,
        "subject": subject,
        "language": language,
        "sources": sources,
        "plan_json": plan,
        "image_assets": png_paths,
        "files": {}
    }

    if intent == "chat":
        execution_result["response_text"] = master_text

    elif intent in ["presentation", "nsl", "braille"]:
        # Presentation, NSL, or Braille output format
        file_suffix = "Braille_Presentation" if intent == "braille" else ("NSL_Presentation" if intent == "nsl" else "Presentation")
        pptx_path = os.path.join(EXPORT_DIR, f"DraftBench_G{grade}_{subject.replace(' ', '_')}_{language.capitalize()}_{file_suffix}{file_tag}.pptx")
        
        formatted_slides = [
            dict(
                s,
                bullets=(s.get("bullets") or [])[:3],
                icon_path=s.get("png_path"),
                braille_text=s.get("braille_text", {}),
                nsl_gestures=s.get("nsl_gestures", [])
            )
            for s in plan.get("slides", [])
        ]
        
        generate_styled_pptx(
            slides_data=formatted_slides,
            output_path=pptx_path,
            grade=grade,
            subject=subject,
            image_paths=None,
            language=language,
            lesson_title=plan.get("lesson_meta", {}).get("title"),
            visual_schedule=plan.get("visual_schedule"),
            cdc_outcome=plan.get("lesson_meta", {}).get("cdc_outcome_ref"),
        )
        execution_result["response_text"] = f"{file_suffix.replace('_', ' ')} generated successfully."
        execution_result["files"] = {"pptx": pptx_path}

    elif intent == "quiz":
        pdf_path = os.path.join(EXPORT_DIR, f"DraftBench_G{grade}_{subject.replace(' ', '_')}_{language.capitalize()}_Quiz{file_tag}.pdf")
        generate_styled_pdf(
            master_text, pdf_path, png_paths, intent="quiz", language=language, grade=grade, subject=subject
        )
        execution_result["response_text"] = "Quiz assessment sheet compiled successfully."
        execution_result["files"] = {"pdf": pdf_path}

    else:  # Document
        pdf_path = os.path.join(EXPORT_DIR, f"DraftBench_G{grade}_{subject.replace(' ', '_')}_{language.capitalize()}_Report{file_tag}.pdf")
        generate_styled_pdf(
            master_text, pdf_path, png_paths, intent="document", language=language, grade=grade, subject=subject
        )
        execution_result["response_text"] = "Comprehensive IEP Document compiled successfully."
        execution_result["files"] = {"pdf": pdf_path}

    return execution_result