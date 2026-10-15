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

# Global in-memory session store for state persistence across turns
SESSION_STORE = {}


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


def evaluate_asd_plan(plan: dict, language: str) -> tuple[int, list]:
    """
    Evaluator Agent: Reviews generated plan against ASD evidence-based rubric
    and strict language policies (pure Devanagari Nepali vs. English).
    """
    feedback = []
    score = 10

    # Rule 1: Max 3 bullets per slide & strict word count limits
    for idx, slide in enumerate(plan.get("slides", []), 1):
        bullets = slide.get("bullets", [])
        if len(bullets) > 3:
            score -= 2
            feedback.append(f"Slide {idx} has {len(bullets)} bullets (Max 3 allowed).")
        for b in bullets:
            if len(b.split()) > 10:
                score -= 1
                feedback.append(f"Slide {idx} bullet '{b}' exceeds 10 words limit.")

    # Rule 2: Measurable IEP Goal validation
    iep = plan.get("iep_goal", {})
    if not iep.get("baseline_probe") or not iep.get("measurable_criteria"):
        score -= 2
        feedback.append("IEP Goal is missing measurable criteria or baseline probe.")

    # Rule 3: Pure Nepali policy enforcement (Prohibit Hindi loanwords)
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
  "intent": "chat" | "presentation" | "document" | "quiz",
  "topic": string or null,
  "grade": integer (1 to 12, default 7 if unspecified),
  "subject": string (e.g. "Mathematics", "Science", "English", "Nepali", "Social Studies"),
  "language": "nepali" | "english",
  "needs_autism_adaptations": boolean
}
CRITICAL RULES:
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


def run_unified_pipeline(user_prompt: str, session_id: str = "default_session") -> dict:
    """Executes the complete DraftBench pipeline with self-correction and multi-format exporting."""
    # --- Step 1: Intent Classification & Session State Synchronization ---
    print("Step[1]...Classifying intent & resolving session state...")
    extracted_params = classify_intent_and_extract_params(user_prompt)
    session = get_or_update_session(session_id, extracted_params)

    intent = extracted_params.get("intent", "document")
    language = session["language"]
    grade = session["grade"]
    subject = session["subject"]
    topic = extracted_params.get("topic") or session["topic"] or user_prompt

    print(f"[Pipeline] Intent: {intent.upper()} | Language: {language.upper()} | Grade: {grade} | Subject: {subject}")

    # --- Step 2: RAG Context Retrieval ---
    print("Step[2]...Retrieving CDC Curriculum Context via RAG...")
    cdc_context, sources = query_curriculum_rag(
        user_query=user_prompt,
        grade_filter=grade,
        subject_filter=subject,
        top_k=3
    )

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

    evaluator_feedback = []
    attempt = 0
    max_attempts = 3
    plan = {}

    while attempt < max_attempts:
        attempt += 1
        print(f"  [CoIEP Loop] Planner Pass {attempt}/{max_attempts}...")

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
TOPIC: {topic} | GRADE: {grade} | SUBJECT: {subject}
{feedback_str}
DESIGN RULES (evidence-based ASD practices):
1. LITERAL LANGUAGE ONLY — no idioms, metaphors, or sarcasm. Every sentence <= 10 words.
2. ONE CONCEPT PER SLIDE — maximum 3 bullets per slide.
3. VISUAL-FIRST — every abstract concept gets a simple, literal icon description.
4. SENSORY SAFETY — flag any potential trigger (loud video, bright colors, strong smell).
5. PREDICTABILITY — include a visual schedule using First / Then / Last / Done.
6. COMMUNICATION ACCESS — for each slide, state how the student can respond (point, gesture, say, use AAC).
7. STRENGTHS-BASED — connect content to concrete everyday interests.
8. LOCAL CONTEXT — use Nepali examples (rupees, festivals, native plants) at least twice.
9. MEASURABLE IEP GOAL — must include a number (%, trials, or time) and a baseline probe.

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
      "title": "short literal title",
      "bullets": ["max 3 bullets", "each <= 10 words"],
      "visual_desc": "simple literal icon description",
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
- Produce exactly 3 slides.
- Output ONLY valid JSON. No markdown fences, no commentary.
- If a field cannot be filled, use null — never invent facts."""

        response = ollama.chat(
            model="qwen2.5:7b-instruct",
            messages=[
                {"role": "system", "content": "You output only valid JSON. You never add markdown or commentary."},
                {"role": "user", "content": planner_prompt}
            ],
            options={"temperature": 0.3, "num_predict": 2500, "format": "json"}
        )

        try:
            raw = response["message"]["content"]
            clean_json = re.search(r'\{.*\}', raw, re.DOTALL).group(0)
            plan = json.loads(clean_json)

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

    # --- Step 4: Visual PECS SVG/PNG Generation ---
    print("Step[4]...Generating visual PNG assets...")
    png_paths = []
    if intent in ["presentation", "document", "quiz"]:
        lesson_topic_str = plan.get("lesson_meta", {}).get("title", topic)
        iep_goal_str = plan.get("iep_goal", {}).get("goal_statement_english", "")
        for slide in plan.get("slides", []):
            visual_desc = slide.get("visual_desc") or f"{subject} concept icon"
            try:
                path = generate_educational_svg(
                    vdescription=visual_desc,
                    filename_prefix=f"G{grade}",
                    grade=grade,
                    lesson_topic=lesson_topic_str,
                    iep_goal=iep_goal_str
                )
                png_paths.append(path)
                slide["png_path"] = path
            except Exception as err:
                print(f"[Pipeline] Error generating PNG for '{visual_desc}': {err}")
                slide["png_path"] = None

    # --- Step 5: Document Building & Format Exporting ---
    print(f"Step[5]...Routing Execution for Intent: [{intent.upper()}]...")
    os.makedirs("data/exports", exist_ok=True)

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

    elif intent == "presentation":
        pptx_path = f"data/exports/DraftBench_G{grade}_{subject}_{language.capitalize()}_Presentation.pptx"
        formatted_slides = [
            {
                "title": s.get("title"),
                "bullets": s.get("bullets", [])[:3],
                "teacher_script": s.get("teacher_script")
            }
            for s in plan.get("slides", [])
        ]
        generate_styled_pptx(
            slides_data=formatted_slides,
            output_path=pptx_path,
            grade=grade,
            subject=subject,
            image_paths=png_paths,
            language=language
        )
        execution_result["response_text"] = "Presentation generated successfully."
        execution_result["files"] = {"pptx": pptx_path}

    elif intent == "quiz":
        pdf_path = f"data/exports/DraftBench_G{grade}_{subject}_{language.capitalize()}_Quiz.pdf"
        generate_styled_pdf(
            master_text, pdf_path, png_paths, intent="quiz", language=language, grade=grade, subject=subject
        )
        execution_result["response_text"] = "Quiz assessment sheet compiled successfully."
        execution_result["files"] = {"pdf": pdf_path}

    else:  # Document
        pdf_path = f"data/exports/DraftBench_G{grade}_{subject}_{language.capitalize()}_Report.pdf"
        generate_styled_pdf(
            master_text, pdf_path, png_paths, intent="document", language=language, grade=grade, subject=subject
        )
        execution_result["response_text"] = "Comprehensive IEP Document compiled successfully."
        execution_result["files"] = {"pdf": pdf_path}

    return execution_result