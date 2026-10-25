"""Small, fast content writer used by the Braille and Sign-language sections (no full lesson plan needed)."""
import json
import os
import re

MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct")


def language_policy(language: str) -> str:
    if language == "nepali":
        return (
            "LANGUAGE POLICY: 100% PURE NEPALI (नेपाली) in Devanagari script. "
            "Never use Hindi words (और, करना, में, के लिए, नहीं, बहुत...). Use 'र', 'दहाइ', 'सय', 'फरक'."
        )
    return "LANGUAGE POLICY: simple, clear English. Do not use Nepali script."


def chat_json(system: str, user: str, num_predict: int = 2000, num_ctx: int = 8192, temperature: float = 0.3) -> dict:
    import ollama
    resp = ollama.chat(
        model=MODEL,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        format="json",
        options={"temperature": temperature, "num_predict": num_predict, "num_ctx": num_ctx},
    )
    raw = resp["message"]["content"]
    return json.loads(re.search(r"\{.*\}", raw, re.DOTALL).group(0))


def material_block(material_text: str) -> str:
    if not material_text:
        return ""
    return ("\nTEACHER'S UPLOADED MATERIAL (use its facts and words; do not invent facts beyond it):\n"
            + material_text + "\n")


def _clean_sentence(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def build_key_content(user_prompt, grade, subject, language, cdc_context, material_text, topic, say=None) -> dict:
    """Returns {title, key_points[], key_terms[{term, term_en, meaning}]} or empty lists on failure."""
    say = say or (lambda m: None)
    feedback = ""
    best = {"title": "", "key_points": [], "key_terms": []}
    for attempt in range(1, 4):
        say(f"Writing the key content (attempt {attempt} of 3)...")
        prompt = f"""You are a special-education content designer for autistic learners in Nepal.
{language_policy(language)}

CURRICULUM CONTEXT:
{cdc_context}
{material_block(material_text)}
TEACHER REQUEST: {user_prompt}
TOPIC: {topic} | GRADE: {grade} | SUBJECT: {subject}
{feedback}
Write a compact study sheet as JSON:
{{
  "title": "short literal title",
  "key_points": ["5 complete sentences, each 4 to 9 words"],
  "key_terms": [{{"term": "word in the lesson language", "term_en": "the same word in English, lower case", "meaning": "simple meaning in the lesson language, under 10 words"}}]
}}
RULES:
- Literal language only: no idioms, no metaphors.
- 5 key points. Each is a full sentence, not a fragment.
- 4 to 6 key terms. Prefer concrete words that can be pointed to, drawn or signed. No abstract words.
- Output ONLY valid JSON."""
        try:
            data = chat_json("You output only valid JSON.", prompt, num_predict=1800)
        except Exception as e:
            print(f"[content_agent] attempt {attempt} failed: {e}")
            feedback = "PREVIOUS ANSWER WAS NOT VALID JSON. Return only the JSON object."
            continue

        points = [_clean_sentence(p) for p in (data.get("key_points") or []) if _clean_sentence(p)]
        points = [p for p in points if 3 <= len(p.split()) <= 14][:6]
        terms = []
        for t in data.get("key_terms") or []:
            if isinstance(t, dict) and _clean_sentence(t.get("term")):
                terms.append({
                    "term": _clean_sentence(t.get("term")),
                    "term_en": _clean_sentence(t.get("term_en")).lower(),
                    "meaning": _clean_sentence(t.get("meaning")),
                })
        terms = terms[:6]
        result = {"title": _clean_sentence(data.get("title")) or str(topic)[:60], "key_points": points, "key_terms": terms}
        if len(points) + len(terms) > len(best["key_points"]) + len(best["key_terms"]):
            best = result
        if len(points) >= 4 and len(terms) >= 3:
            return result
        feedback = ("PREVIOUS ANSWER WAS TOO SHORT. Give 5 full key_points (4 to 9 words each) "
                    "and at least 4 key_terms.")
    return best
