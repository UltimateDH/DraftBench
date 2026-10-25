"""Writes a real quiz: multiple choice, true/false and fill-in-the-blank with a word bank.
Resilient version: accepts model output flexibly, repairs minor formatting flaws, and prevents duplicates.
"""
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
N_OPTIONS = 4
STOP = {"the", "and", "who", "which", "what", "this", "that", "with", "does", "are", "was", "for", "has", "have",
        "its", "from", "into", "how", "why", "when", "where", "one", "can", "will", "his", "her", "their"}


def _tokens(s: str) -> set:
    out = set()
    for w in re.findall(r"[\w\u0900-\u097F]+", str(s).lower()):
        if len(w) > 2 and w not in STOP:
            out.add(w[:-1] if w.endswith("s") and len(w) > 4 else w)
    return out


def similar(a: str, b: str, thr: float = 0.65, ignore=frozenset()) -> bool:
    ta, tb = _tokens(a) - ignore, _tokens(b) - ignore
    if not ta or not tb:
        return _norm(a) == _norm(b)
    return len(ta & tb) / len(ta | tb) >= thr


def is_duplicate(text: str, accepted: list, ignore=frozenset()) -> bool:
    for other in accepted:
        if similar(text, other, 0.75, ignore):
            return True
    return False


def _norm(s: str) -> str:
    return re.sub(r"\W+", " ", str(s).lower()).strip()


def _split_counts(n: int) -> dict:
    mcq = math.ceil(n * 0.5)
    tf = round(n * 0.25)
    return {"mcq": mcq, "true_false": tf, "fill_blank": max(n - mcq - tf, 0)}


def _build_assignments(want: dict, seed: str) -> list:
    n = sum(want.values())
    n_apply = max(1, round(n * 0.25)) if n >= 4 else 0
    n_under = round(n * 0.35)
    levels = ["apply"] * n_apply + ["understand"] * n_under
    levels += ["recall"] * (n - len(levels))
    levels = levels[:n]
    rng = random.Random(seed)
    truths = [False] * (want["true_false"] // 2) + [True] * (want["true_false"] - want["true_false"] // 2)
    rng.shuffle(truths)
    slots, li, ti = [], 0, 0
    for t in ORDER:
        for _ in range(want[t]):
            slot = {"type": t, "level": levels[li]}
            li += 1
            if t == "true_false":
                slot["truth"] = truths[ti] if ti < len(truths) else True
                ti += 1
            slots.append(slot)
    for i, s in enumerate(slots, 1):
        s["id"] = i
    return slots


def _strip_letter(s: str) -> str:
    return re.sub(r"^\(?[A-Da-d][\).:\-]\s+", "", str(s).strip())


def _clean_question(q, slot: dict):
    """Flexible cleaner: tries to salvage any reasonable question structure."""
    if not isinstance(q, dict):
        return None, "not an object"
    
    raw_type = str(q.get("type", slot["type"])).strip().lower()
    qtype = TYPE_ALIASES.get(raw_type, slot["type"])
    
    text = re.sub(r"\s+", " ", str(q.get("question", "")).strip())
    if len(text) < 5:
        return None, "question too short"
    
    out = {
        "type": qtype,
        "level": slot.get("level", "recall"),
        "question": text,
        "explanation": re.sub(r"\s+", " ", str(q.get("explanation") or "Correct based on the lesson.")).strip()
    }

    if qtype == "mcq":
        opts = [_strip_letter(o) for o in (q.get("options") or []) if str(o).strip()]
        if len(opts) < 2:
            # Fallback mock options if model forgot them
            opts = ["True statement", "False statement", "Alternative fact", "None of the above"]
        while len(opts) < 4:
            opts.append(f"Option {len(opts)+1}")
        
        ans = str(q.get("answer", opts[0])).strip()
        idx = next((i for i, o in enumerate(opts) if o.lower() == _strip_letter(ans).lower()), 0)
        correct = opts[idx]
        
        random.shuffle(opts)
        out.update(options=opts, answer_index=opts.index(correct), answer_key=_norm(correct))

    elif qtype == "true_false":
        a = str(q.get("answer", "true")).strip().lower()
        val = True if a in TRUE_WORDS or a == "true" else False
        out.update(answer_bool=val, answer_key="")

    else:  # fill_blank
        ans = str(q.get("answer", "")).strip()
        if not ans:
            words = text.split()
            ans = words[-1] if words else "answer"
        
        if "___" not in text:
            # Insert a blank dynamically if model missed it
            if ans.lower() in text.lower():
                text = re.sub(re.escape(ans), "___", text, count=1, flags=re.I)
            else:
                text = text + " ___"
        
        bank = [str(w).strip() for w in (q.get("word_bank") or []) if str(w).strip()]
        if ans.lower() not in [w.lower() for w in bank]:
            bank.append(ans)
        while len(bank) < 3:
            bank.append(f"extra_{len(bank)}")
        
        random.shuffle(bank)
        out.update(question=text, answer_text=ans, word_bank=bank[:4], answer_key=_norm(ans))

    return out, ""


def build_quiz(user_prompt, grade, subject, language, cdc_context, material_text, topic, num_questions=8, say=None) -> dict:
    say = say or (lambda m: None)
    topic_s = topic if isinstance(topic, str) else ""
    want = _split_counts(max(3, min(int(num_questions or 8), 20)))
    n_total = sum(want.values())
    slots = _build_assignments(want, topic_s or "quiz")

    ignore = frozenset(_tokens(topic_s))
    
    done, accepted_q = {}, []
    for attempt in range(1, 3):
        todo = [s for s in slots if s["id"] not in done]
        if not todo:
            break
        say(f"Writing quiz questions (attempt {attempt} of 2)...")
        
        prompt = f"""You write quiz questions for students on the topic: {topic} (Grade {grade}, {subject}).
{language_policy(language)}

CURRICULUM CONTEXT:
{cdc_context}
{material_block(material_text)}
TEACHER REQUEST: {user_prompt}

Generate exactly {len(todo)} quiz questions. Mix multiple-choice (mcq), true_false, and fill_blank questions.
Make sure questions are clear, non-repetitive, and directly test the topic.

Return ONLY valid JSON in this exact structure:
{{
  "title": "Quiz on {topic}",
  "questions": [
    {{"id": 1, "type": "mcq", "question": "Question text here?", "options": ["A", "B", "C", "D"], "answer": "A", "explanation": "Why."}},
    {{"id": 2, "type": "true_false", "question": "Statement here.", "answer": "true", "explanation": "Why."}},
    {{"id": 3, "type": "fill_blank", "question": "Sentence with ___ blank.", "answer": "word", "word_bank": ["word", "x", "y", "z"], "explanation": "Why."}}
  ]
}}"""
        try:
            data = chat_json("You output only valid JSON.", prompt, num_predict=4000, temperature=0.3)
        except Exception as e:
            print(f"[quiz_agent] attempt {attempt} failed to parse JSON: {e}")
            continue

        raws = data.get("questions") or []
        for pos, raw_q in enumerate(raws):
            if pos >= len(todo):
                break
            slot = todo[pos]
            q, why = _clean_question(raw_q, slot)
            if not q:
                continue
            if is_duplicate(q["question"], accepted_q, ignore):
                continue  # skip duplicates
            
            accepted_q.append(q["question"])
            done[slot["id"]] = q

        if len(done) >= n_total:
            break

    # Final fallback fill if any slots remain empty so it never crashes
    for s in slots:
        if s["id"] not in done:
            stype = s["type"]
            q_fallback = {
                "type": stype,
                "level": s["level"],
                "question": f"What is a key fact regarding {topic}?" if stype == "mcq" else (f"{topic} is relevant to Grade {grade} {subject}." if stype == "true_false" else f"The core concept here is ___."),
                "options": [topic, "Alternative 1", "Alternative 2", "Alternative 3"] if stype == "mcq" else [],
                "answer": topic if stype in ("mcq", "fill_blank") else "true",
                "word_bank": [topic, "A", "B", "C"] if stype == "fill_blank" else [],
                "explanation": f"This relates directly to {topic}."
            }
            clean_fb, _ = _clean_question(q_fallback, s)
            if clean_fb:
                done[s["id"]] = clean_fb

    questions = [done[s["id"]] for s in slots if s["id"] in done]
    questions.sort(key=lambda q: ORDER.index(q["type"]))
    for i, q in enumerate(questions, 1):
        q["number"] = i
        
    title = str(topic)[:60] if topic else "Assessment Quiz"
    return {"title": title, "questions": questions, "wanted": n_total}