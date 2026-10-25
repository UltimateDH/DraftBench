"""Writes a real quiz: multiple choice, true/false and fill-in-the-blank with a word bank.

Fixes over the first version
- Plans DISTINCT facts first, then writes exactly one question per fact (no more near-duplicate questions).
- Every question gets a thinking level (recall / understand / apply) so the quiz is not all easy.
- True/false: half the statements are deliberately FALSE (common misconceptions), enforced in code.
- 4 answer options, plausible distractors, and a check that the stem does not contain the answer.
- Code-level duplicate guard (word overlap) and a limit on how often one answer can repeat.
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


def similar(a: str, b: str, thr: float = 0.55) -> bool:
    ta, tb = _tokens(a), _tokens(b)
    return bool(ta and tb) and len(ta & tb) / len(ta | tb) >= thr


def _norm(s: str) -> str:
    return re.sub(r"\W+", " ", str(s).lower()).strip()


def _split_counts(n: int) -> dict:
    mcq = math.ceil(n * 0.5)
    tf = round(n * 0.25)
    return {"mcq": mcq, "true_false": tf, "fill_blank": max(n - mcq - tf, 0)}


def _build_assignments(want: dict, seed: str) -> list:
    """One slot per question: its type, thinking level and (for true/false) whether it must be true or false."""
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
                slot["truth"] = truths[ti]
                ti += 1
            slots.append(slot)
    for i, s in enumerate(slots, 1):
        s["id"] = i
    return slots


def _strip_letter(s: str) -> str:
    return re.sub(r"^\(?[A-Da-d][\).:\-]\s+", "", str(s).strip())


def _clean_question(q, slot: dict, seed_text: str):
    if not isinstance(q, dict):
        return None
    qtype = TYPE_ALIASES.get(re.sub(r"[\s\-]+", "_", str(q.get("type", slot["type"])).strip().lower()))
    if qtype != slot["type"]:
        return None
    text = re.sub(r"\s+", " ", str(q.get("question", "")).strip())
    if len(text.split()) < 3:
        return None
    rng = random.Random(seed_text + text)
    out = {"type": qtype, "level": slot["level"], "question": text,
           "explanation": re.sub(r"\s+", " ", str(q.get("explanation") or "")).strip()}

    if qtype == "mcq":
        opts = [_strip_letter(o) for o in (q.get("options") or []) if str(o).strip()]
        if len(opts) != N_OPTIONS or len({o.lower() for o in opts}) != N_OPTIONS:
            return None
        ans = str(q.get("answer", "")).strip()
        idx = next((i for i, o in enumerate(opts) if o.lower() == _strip_letter(ans).lower()), None)
        if idx is None and len(ans) == 1 and ans.upper() in "ABCD":
            idx = "ABCD".index(ans.upper())
        if idx is None:
            return None
        correct = opts[idx]
        if len(_norm(correct)) >= 3 and _norm(correct) in _norm(text):
            return None  # the question already contains the answer
        rng.shuffle(opts)
        out.update(options=opts, answer_index=opts.index(correct), answer_key=_norm(correct))
    elif qtype == "true_false":
        a = q.get("answer")
        a = str(a).strip().lower() if not isinstance(a, bool) else ("true" if a else "false")
        if a in TRUE_WORDS:
            val = True
        elif a in FALSE_WORDS:
            val = False
        else:
            return None
        if val != slot["truth"]:
            return None  # the model did not follow the true/false plan
        out.update(answer_bool=val, answer_key="")
    else:  # fill_blank
        if not re.search(r"_{2,}", text):
            return None
        out["question"] = re.sub(r"_{2,}", "___", text)
        ans = str(q.get("answer", "")).strip()
        if not ans:
            return None
        rest = out["question"].replace("___", " ")
        if len(_norm(ans)) >= 3 and _norm(ans) in _norm(rest):
            return None  # the answer is written elsewhere in the sentence
        bank = [str(w).strip() for w in (q.get("word_bank") or []) if str(w).strip()]
        if ans.lower() not in [w.lower() for w in bank]:
            bank.append(ans)
        bank = list(dict.fromkeys(bank))
        if len(bank) > 4:
            bank = [ans] + [w for w in bank if w.lower() != ans.lower()][:3]
        if len(bank) < 3:
            return None
        rng.shuffle(bank)
        out.update(answer_text=ans, word_bank=bank, answer_key=_norm(ans))
    return out


def _plan_facts(topic, grade, subject, language, cdc_context, material_text, user_prompt, count, say) -> tuple:
    """Stage 1: a list of DIFFERENT facts to test. Returns (title, facts)."""
    title, facts, feedback = "", [], ""
    for attempt in range(1, 3):
        say(f"Planning the quiz topics (attempt {attempt} of 2)...")
        prompt = f"""You plan a quiz for autistic learners in Nepal.
{language_policy(language)}

CURRICULUM CONTEXT:
{cdc_context}
{material_block(material_text)}
TEACHER REQUEST: {user_prompt}
TOPIC: {topic} | GRADE: {grade} | SUBJECT: {subject}
{feedback}
List {count + 2} DIFFERENT facts a Grade {grade} student should know about the topic.
Each fact must be about a separate idea: no two facts may share the same answer or describe the same thing.
Include definitions, evidence/cause-and-effect, and at least two facts that can be used to predict or explain a new situation.
Facts must be true and, when the teacher's material is given, come from it.

Return ONLY this JSON:
{{"title": "short literal quiz title", "facts": ["one complete true sentence", "another different fact"]}}"""
        try:
            data = chat_json("You output only valid JSON.", prompt, num_predict=1500, num_ctx=10240, temperature=0.3)
        except Exception as e:
            print(f"[quiz_agent] fact planning attempt {attempt} failed: {e}")
            feedback = "PREVIOUS ANSWER WAS NOT VALID JSON. Return only the JSON object."
            continue
        title = re.sub(r"\s+", " ", str(data.get("title") or "")).strip()
        for f in data.get("facts") or []:
            f = re.sub(r"\s+", " ", str(f.get("fact") if isinstance(f, dict) else f or "")).strip()
            if len(f.split()) >= 4 and not any(similar(f, x, 0.5) for x in facts):
                facts.append(f)
        if len(facts) >= count:
            break
        feedback = "PREVIOUS LIST HAD TOO FEW DIFFERENT FACTS. Give clearly different facts."
    return title, facts


_TYPE_RULES = {
    "mcq": 'MCQ: "options" = exactly 4 short options; 1 correct + 3 plausible wrong options that match common misconceptions '
           '(same kind of thing as the answer). "answer" = the exact text of the correct option. The question must NOT contain the answer.',
    "true_false": 'TRUE/FALSE: "question" is one plain statement. "answer" must be exactly the truth value required for that item. '
                  'A FALSE statement must sound plausible (a common misconception) and the explanation states the correct fact.',
    "fill_blank": 'FILL BLANK: one sentence with exactly one ___ blank; the answer word must not appear elsewhere in the sentence. '
                  '"word_bank" = 4 words: the answer + 3 plausible wrong words of the same kind.',
}
_LEVEL_RULES = {
    "recall": "recall: asks for a single fact or definition.",
    "understand": "understand: asks WHY or WHAT SOMETHING SHOWS (cause, reason, meaning), not just a name.",
    "apply": "apply: a short concrete situation (1-2 sentences) where the student must use the fact to predict or decide.",
}


def build_quiz(user_prompt, grade, subject, language, cdc_context, material_text, topic, num_questions=8, say=None) -> dict:
    say = say or (lambda m: None)
    topic_s = topic if isinstance(topic, str) else ""
    want = _split_counts(max(3, min(int(num_questions or 8), 20)))
    n_total = sum(want.values())
    slots = _build_assignments(want, topic_s or "quiz")

    title, facts = _plan_facts(topic, grade, subject, language, cdc_context, material_text, user_prompt, n_total, say)
    rng = random.Random(topic_s + "facts")
    rng.shuffle(facts)
    for i, slot in enumerate(slots):
        slot["fact"] = facts[i] if i < len(facts) else "(choose a clearly different idea about the topic)"

    done, accepted_q, answer_use, feedback = {}, [], {}, ""
    for attempt in range(1, 4):
        todo = [s for s in slots if s["id"] not in done]
        if not todo:
            break
        say(f"Writing quiz questions (attempt {attempt} of 3)...")
        items = "\n".join(
            f'{s["id"]}. type={s["type"]} | level={s["level"]}'
            + (f' | the statement must be {"TRUE" if s["truth"] else "FALSE"}' if s["type"] == "true_false" else "")
            + f' | fact to test: {s["fact"]}'
            for s in todo)
        used_levels = sorted({s["level"] for s in todo})
        prompt = f"""You write quizzes for autistic learners in Nepal.
{language_policy(language)}

CURRICULUM CONTEXT:
{cdc_context}
{material_block(material_text)}
TOPIC: {topic} | GRADE: {grade} | SUBJECT: {subject}
{feedback}
Write ONE question for each numbered item below, in the same order. Each question tests only its own fact.
ITEMS:
{items}

TYPE RULES:
""" + "\n".join(_TYPE_RULES[t] for t in ORDER if any(s["type"] == t for s in todo)) + """

LEVEL RULES:
""" + "\n".join(_LEVEL_RULES[l] for l in used_levels) + f"""

GENERAL RULES:
- Literal, concrete wording at Grade {grade} difficulty. No tricks, no double negatives, no "which is NOT", no "all of the above".
- Never repeat or rephrase another question. Each question must have a different answer.
- When the teacher's material is given, every question must be answerable from it.
- "explanation" is one short sentence stating the correct fact.

Return ONLY this JSON:
{{"questions": [
  {{"id": 1, "type": "mcq", "question": "...", "options": ["...", "...", "...", "..."], "answer": "exact text of the correct option", "explanation": "..."}},
  {{"id": 2, "type": "true_false", "question": "...", "answer": "true", "explanation": "..."}},
  {{"id": 3, "type": "fill_blank", "question": "A sentence with one ___ blank.", "answer": "word", "word_bank": ["word", "x", "y", "z"], "explanation": "..."}}
]}}"""
        try:
            data = chat_json("You output only valid JSON.", prompt, num_predict=3600, num_ctx=10240, temperature=0.4)
        except Exception as e:
            print(f"[quiz_agent] attempt {attempt} failed: {e}")
            feedback = "PREVIOUS ANSWER WAS NOT VALID JSON. Return only the JSON object."
            continue

        by_id = {s["id"]: s for s in todo}
        raws = data.get("questions") or []
        dropped = 0
        for pos, raw_q in enumerate(raws):
            sid = raw_q.get("id") if isinstance(raw_q, dict) else None
            try:
                sid = int(sid)
            except (TypeError, ValueError):
                sid = todo[pos]["id"] if pos < len(todo) else None
            slot = by_id.get(sid)
            if not slot or slot["id"] in done:
                continue
            q = _clean_question(raw_q, slot, topic_s)
            if not q or any(similar(q["question"], x) for x in accepted_q):
                dropped += 1
                continue
            key = q.get("answer_key")
            if key and answer_use.get(key, 0) >= 2:
                dropped += 1
                continue
            if key:
                answer_use[key] = answer_use.get(key, 0) + 1
            accepted_q.append(q["question"])
            done[slot["id"]] = q
        feedback = (f"{dropped} questions were rejected (duplicate, wrong format, answer given away in the question, "
                    "or the wrong true/false value). Follow the item list and type rules exactly.")

    questions = [done[s["id"]] for s in slots if s["id"] in done]
    questions.sort(key=lambda q: ORDER.index(q["type"]))
    for i, q in enumerate(questions, 1):
        q["number"] = i
    return {"title": title or str(topic)[:60], "questions": questions, "wanted": n_total}
