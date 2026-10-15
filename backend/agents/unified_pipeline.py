import ollama
import json
import re
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rag import query_curriculum_rag


def classifiy_intent_and_extract_params(user_prompt:str):
    system_prompt="""You are the Master Intent Classifier for DraftBench.
    Analyze the user prompt and return a strict JSON object with:
    {
    "intent": "chat" | "presentation" | "document" | "quiz",
    "grade": integer (1 to 12, default 7 if unspecified),
    "subject": string (e.g. "Mathematics", "Science", "English", "Nepali", "Social Studies"),
    "needs_autism_adaptations": boolean
    }
    CRITICAL: Output ONLY valid JSON."""

    response=ollama.chat(
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
    except Exception: #for now i am just returning random class that i have more data of in RAG
        return {
            "intent": "document",
            "grade": 7,
            "subject": "Mathematics",
            "needs_autism_adaptations": True
        }



def run_unified_pipeline(user_prompt:str):
    print("Step[1]...Classifiying the intent of the user...")
    intent_data=classifiy_intent_and_extract_params(user_prompt=user_prompt)
    intent = intent_data.get("intent", "document")
    topic = intent_data.get("topic") or user_prompt
    grade = intent_data.get("grade", 7)
    subject = intent_data.get("subject", "Mathematics")
    needs_asd = intent_data.get("needs_autism_adaptations", True)

    print("[Pipeline] Intent detected: {intent.upper()} | Grade: {grade} | Subject: {subject}")
    print("Step[2]...Using RAG...")
    cdc_context, sources=query_curriculum_rag(user_query=user_prompt, 
        grade_filter=grade, 
        subject_filter=subject, 
        top_k=3)

    print("Step[3]...Planning content...")
    planner_prompt=f"""You are an expert special education content designer for Autism Spectrum Disorder (ASD), grounded in Nepal's CDC curriculum.

    CDC CONTEXT (from RAG):
    {cdc_context}

    TEACHER REQUEST: {user_prompt}
    TOPIC: {topic} | GRADE: {grade} | SUBJECT: {subject}

    DESIGN RULES (evidence-based ASD practices):
    1. LITERAL LANGUAGE ONLY — no idioms, metaphors, or sarcasm. Every sentence <= 10 words.
    2. ONE CONCEPT PER SLIDE — maximum 3 bullets per slide.
    3. VISUAL-FIRST — every abstract concept gets a simple, literal icon description (e.g. "a red circle with the number 2 inside").
    4. SENSORY SAFETY — flag any potential trigger (loud video, bright colors, strong smell).
    5. PREDICTABILITY — include a visual schedule using First / Then / Last / Done.
    6. COMMUNICATION ACCESS — for each slide, state how the student can respond (point, gesture, say, use AAC).
    7. STRENGTHS-BASED — where possible, connect the content to concrete everyday interests (e.g. trains, animals, food).
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
        "schedule": "e.g. token board every 2 correct responses",
        "first_then_statement": "First [task], then [reinforcer]"
    }},
    "sensory_accommodations": ["specific supports for this lesson"],
    "calm_down_strategy": "what to do if the student is overwhelmed",
    "local_context_used": ["Nepali examples used"]
    }}

    CRITICAL:
    - Produce exactly 3 slides.
    - Output ONLY valid JSON. No markdown fences, no commentary.
    - If a field cannot be filled, use null — never invent facts.
    - Nepali text must be in Devanagari script."""

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
        print(f"[Pipeline] Plan generated: {len(plan.get('slides', []))} slides | IEP goal present: {bool(plan.get('iep_goal'))}")
    except Exception as e:
        print(f"[Pipeline] Planner failed to produce valid JSON: {e}")
        print(f"[Pipeline] Raw output:\n{raw[:500]}")
        return {"error": "planner_failed", "raw": raw}


    print("Step[4]...Generating multiple svgs...")
    svg_paths=[]
    if intent in ["presentation", "document", "quiz"] :
        for slide in plan.get("slides",[]):
            visual_desc=slide.get("visual_desc") or f"{subject} concept icon"
            