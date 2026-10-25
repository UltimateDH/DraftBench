"""Writes a real quiz (not a lesson plan): multiple choice, true/false and fill-in-the-blank with a word bank."""
import math
import random
import re

from agents.content_agent import chat_json, language_policy, material_block

TYPE_ALIASES = {
    "mcq": "mcq", "multiple_choice": "mcq", "multiplechoice": "mcq",
    "true_false": "true_false", "truefalse": "true_false", "tf": "true_false",
    "fill_blank": "fill_blank", "fill_in_the_blank": "fill_blank", "fill_in_blank": "fill_blank", "fillblank": "fill_blank",
}
ORDER = ["mcq", "true_false", "fill_blank"]
TRUE_WORDS = {"true", "t", "yes", "सही", "ठीक"}
FALSE_WORDS = {"false", "f", "no", "गलत", "बेठीक"}


def _split_counts(n: int) -> dict:
    mcq = math.ceil(n * 0.5)
    tf = round(n * 0.25)
    return {"mcq": mcq, "true_false": tf, "fill_blank": max(n - mcq - tf, 0)}


def _strip_letter(s: str) -> str:
    return re.sub(r"^\(?[A-Ca-c][\).:\-]\s+", "", str(s).strip())


def _clean_question(q, seed_text: str):
    if not isinstance(q, dict):
        return None
    qtype = TYPE_ALIASES.get(re.sub(r"[\s\-]+", "_", str(q.get("type", "")).strip().lower()))
    text = re.sub(r"\s+", " ", str(q.get("question", "")).strip())
    if not qtype or len(text.split()) < 3:
        return None
    rng = random.Random(seed_text + text)
    out = {"type": qtype, "question": text, "explanation": re.sub(r"\s+", " ", str(q.get("explanation") or "")).strip()}

    if qtype == "mcq":
        opts = [_strip_letter(o) for o in (q.get("options") or []) if str(o).strip()]
        if len(opts) != 3 or len({o.lower() for o in opts}) != 3:
            return None
        ans = str(q.get("answer", "")).strip()
        idx = next((i for i, o in enumerate(opts) if o.lower() == _strip_letter(ans).lower()), None)
        if idx is None and len(ans) == 1 and ans.upper() in "ABC":
            idx = "ABC".index(ans.upper())
        if idx is None:
            return None
        correct = opts[idx]
        rng.shuffle(opts)
        out.update(options=opts, answer_index=opts.index(correct))
    elif qtype == "true_false":
        a = q.get("answer")
        a = str(a).strip().lower() if not isinstance(a, bool) else ("true" if a else "false")
        if a in TRUE_WORDS:
            out["answer_bool"] = True
        elif a in FALSE_WORDS:
            out["answer_bool"] = False
        else:
            return None
    else:  # fill_blank
        if not re.search(r"_{2,}", text):
            return None
        out["question"] = re.sub(r"_{2,}", "___", text)
        ans = str(q.get("answer", "")).strip()
        if not ans:
            return None
        bank = [str(w).strip() for w in (q.get("word_bank") or []) if str(w).strip()]
        if ans.lower() not in [w.lower() for w in bank]:
            bank.append(ans)
        bank = list(dict.fromkeys(bank))[:4]
        if len(bank) < 2:
            return None
        rng.shuffle(bank)
        out.update(answer_text=ans, word_bank=bank)
    return out


def build_quiz(user_prompt, grade, subject, language, cdc_context, material_text, topic, num_questions=8, say=None) -> dict:
    say = say or (lambda m: None)
    want = _split_counts(max(3, min(int(num_questions or 8), 20)))
    have = {"mcq": [], "true_false": [], "fill_blank": []}
    seen, title, feedback = set(), "", ""

    for attempt in range(1, 4):
        missing = {t: max(want[t] - len(have[t]), 0) for t in ORDER}
        if sum(missing.values()) == 0:
            break
        say(f"Writing quiz questions (attempt {attempt} of 3)...")
        prompt = f"""You write quizzes for autistic learners in Nepal.
{language_policy(language)}

CURRICULUM CONTEXT:
{cdc_context}
{material_block(material_text)}
TEACHER REQUEST: {user_prompt}
TOPIC: {topic} | GRADE: {grade} | SUBJECT: {subject}
{feedback}
Write exactly these questions: {missing['mcq']} "mcq", {missing['true_false']} "true_false", {missing['fill_blank']} "fill_blank".

Return ONLY this JSON:
{{
  "title": "short literal quiz title",
  "questions": [
    {{"type": "mcq", "question": "one clear question", "options": ["short option", "short option", "short option"], "answer": "the exact text of the correct option", "explanation": "one short sentence"}},
    {{"type": "true_false", "question": "a plain true or false statement", "answer": "true", "explanation": "one short sentence"}},
    {{"type": "fill_blank", "question": "A sentence with one ___ blank.", "answer": "missing word", "word_bank": ["missing word", "wrong word", "wrong word"], "explanation": "one short sentence"}}
  ]
}}
RULES:
- One fact per question. Literal, concrete language. No tricks, no double negatives, no "which is NOT".
- mcq has exactly 3 short options and never "all of the above".
- fill_blank has exactly one blank written as ___ and a word_bank of 3 words that includes the answer.
- When the teacher's material is given, every question must be answerable from it.
- Output ONLY valid JSON."""
        try:
            data = chat_json("You output only valid JSON.", prompt, num_predict=3200, num_ctx=10240, temperature=0.4)
        except Exception as e:
            print(f"[quiz_agent] attempt {attempt} failed: {e}")
            feedback = "PREVIOUS ANSWER WAS NOT VALID JSON. Return only the JSON object."
            continue
        title = title or re.sub(r"\s+", " ", str(data.get("title") or "")).strip()
        dropped = 0
        for raw_q in data.get("questions") or []:
            q = _clean_question(raw_q, topic if isinstance(topic, str) else "")
            if not q:
                dropped += 1
                continue
            key = q["question"].lower()
            if key in seen or len(have[q["type"]]) >= want[q["type"]]:
                continue
            seen.add(key)
            have[q["type"]].append(q)
        feedback = (f"{dropped} questions were rejected for broken format. Follow the JSON shapes exactly: "
                    "mcq needs 3 options and an answer that matches one of them; fill_blank needs ___ in the question.")

    questions = [q for t in ORDER for q in have[t]]
    for i, q in enumerate(questions, 1):
        q["number"] = i
    return {"title": title or str(topic)[:60], "questions": questions, "wanted": sum(want.values())}
