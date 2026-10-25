"""Braille (Nepali/Bharati + English Grade 1) and Nepali Sign Language (NSL) helpers.

Braille: pure rules, no AI. Each print character becomes one or more 6-dot cells.
NSL: a verified glossary (data/nsl_glossary.json) wins; otherwise ONE batched AI call writes
     *suggested* gesture descriptions, which are always labelled as unverified.
"""
import json
import os
import re
import unicodedata
from typing import Dict, List, Tuple

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GLOSSARY_PATH = os.path.join(BASE_DIR, "data", "nsl_glossary.json")
BLANK = "\u2800"  # an empty braille cell


def _cell(*dots: int) -> str:
    v = 0x2800
    for d in dots:
        v |= 1 << (d - 1)
    return chr(v)


# ---------------------------------------------------------------- English (Grade 1)
_LATIN = {
    "a": (1,), "b": (1, 2), "c": (1, 4), "d": (1, 4, 5), "e": (1, 5), "f": (1, 2, 4), "g": (1, 2, 4, 5),
    "h": (1, 2, 5), "i": (2, 4), "j": (2, 4, 5), "k": (1, 3), "l": (1, 2, 3), "m": (1, 3, 4),
    "n": (1, 3, 4, 5), "o": (1, 3, 5), "p": (1, 2, 3, 4), "q": (1, 2, 3, 4, 5), "r": (1, 2, 3, 5),
    "s": (2, 3, 4), "t": (2, 3, 4, 5), "u": (1, 3, 6), "v": (1, 2, 3, 6), "w": (2, 4, 5, 6),
    "x": (1, 3, 4, 6), "y": (1, 3, 4, 5, 6), "z": (1, 3, 5, 6),
}
LATIN = {k: _cell(*v) for k, v in _LATIN.items()}
NUMBER_SIGN = _cell(3, 4, 5, 6)
CAPITAL_SIGN = _cell(6)
DIGIT_LETTERS = "jabcdefghi"  # 0..9 use the cells of j,a,b,c,d,e,f,g,h,i

PUNCT = {
    ".": _cell(2, 5, 6), ",": _cell(2), ";": _cell(2, 3), ":": _cell(2, 5), "!": _cell(2, 3, 5),
    "?": _cell(2, 3, 6), "-": _cell(3, 6), "'": _cell(3), "।": _cell(2, 5, 6),
    "(": _cell(5) + _cell(1, 2, 6), ")": _cell(5) + _cell(3, 4, 5),
    '"': _cell(2, 3, 6), "“": _cell(2, 3, 6), "”": _cell(3, 5, 6), "/": _cell(4, 5, 6) + _cell(3, 4),
    "+": _cell(3, 4, 6), "=": _cell(2, 3, 5, 6), "%": _cell(4, 5, 6) + _cell(3, 5, 6),
}

# ---------------------------------------------------------------- Devanagari (Bharati Braille)
_CONS = {
    "क": (1, 3), "ख": (4, 6), "ग": (1, 2, 4, 5), "घ": (1, 2, 6), "ङ": (3, 4, 6),
    "च": (1, 4), "छ": (1, 6), "ज": (2, 4, 5), "झ": (3, 5, 6), "ञ": (2, 5),
    "ट": (2, 3, 4, 5, 6), "ठ": (2, 4, 5, 6), "ड": (1, 2, 4, 6), "ढ": (1, 2, 3, 4, 5, 6), "ण": (3, 4, 5, 6),
    "त": (2, 3, 4, 5), "थ": (1, 4, 5, 6), "द": (1, 4, 5), "ध": (2, 3, 4, 6), "न": (1, 3, 4, 5),
    "प": (1, 2, 3, 4), "फ": (2, 3, 5), "ब": (1, 2), "भ": (4, 5), "म": (1, 3, 4),
    "य": (1, 3, 4, 5, 6), "र": (1, 2, 3, 5), "ल": (1, 2, 3), "व": (1, 2, 3, 6),
    "श": (1, 4, 6), "ष": (1, 2, 3, 4, 6), "स": (2, 3, 4), "ह": (1, 2, 5), "ळ": (4, 5, 6),
}
_VOWEL = {  # an independent vowel and its dependent sign share the same cell
    "आ": (3, 4, 5), "इ": (2, 4), "ई": (3, 5), "उ": (1, 3, 6), "ऊ": (1, 2, 5, 6),
    "ए": (1, 5), "ऐ": (3, 4), "ओ": (1, 3, 5), "औ": (2, 4, 6),
}
_SIGN_TO_VOWEL = {"ा": "आ", "ि": "इ", "ी": "ई", "ु": "उ", "ू": "ऊ", "े": "ए", "ै": "ऐ", "ो": "ओ", "ौ": "औ"}
RI = _cell(5) + _cell(1, 2, 3, 5)           # ऋ / ृ
HALANT = _cell(4)
# These three signs come from the Bharati standard from memory and MUST be checked by a braille reader:
ANUSVARA, CHANDRABINDU, VISARGA = _cell(5, 6), _cell(3), _cell(6)
UNVERIFIED_SIGNS = "ंँः"

DEVA = {k: _cell(*v) for k, v in _CONS.items()}
DEVA.update({k: _cell(*v) for k, v in _VOWEL.items()})
DEVA["अ"] = _cell(1)
DEVA["ऋ"] = RI
DEVA["ृ"] = RI
for _sign, _vowel in _SIGN_TO_VOWEL.items():
    DEVA[_sign] = DEVA[_vowel]
DEVA["्"] = HALANT
DEVA["ं"], DEVA["ँ"], DEVA["ः"] = ANUSVARA, CHANDRABINDU, VISARGA


def translate(text: str) -> Tuple[str, List[str], List[Tuple[str, str]]]:
    """Convert text to braille.

    Returns (braille_string, unknown_characters, pairs) where pairs is [(print_unit, cells)] for legends.
    Words are separated by one blank cell. Numbers get a number sign; capitals get a capital sign.
    """
    out, unknown, pairs = [], [], []
    in_number = False

    def emit(unit: str, cells: str):
        out.append(cells)
        pairs.append((unit, cells))

    for ch in (text or "").replace("\u200c", "").replace("\u200d", ""):
        if ch.isspace():
            out.append(BLANK)
            in_number = False
            continue

        digit = None
        if "0" <= ch <= "9":
            digit = int(ch)
        elif "\u0966" <= ch <= "\u096f":
            digit = ord(ch) - 0x0966
        if digit is not None:
            cells = LATIN[DIGIT_LETTERS[digit]]
            if not in_number:
                cells = NUMBER_SIGN + cells
                in_number = True
            emit(ch, cells)
            continue
        in_number = False

        low = ch.lower()
        if "a" <= low <= "z":
            emit(ch, (CAPITAL_SIGN if ch.isupper() else "") + LATIN[low])
        elif ch in DEVA:
            emit(ch, DEVA[ch])
        elif ch in PUNCT:
            emit(ch, PUNCT[ch])
        elif ch == "\u093c":  # nukta: not mapped, skipped silently
            continue
        else:
            unknown.append(ch)
    return "".join(out), sorted(set(unknown)), pairs


def return_braille(text: str, language: str = None) -> str:
    """Backward compatible helper used by older code: braille string only."""
    return translate(text)[0]


def legend_entries(texts: List[str], limit: int = 48) -> List[Tuple[str, str]]:
    """Unique (print character, cells) pairs used in the given texts, in order of first use."""
    seen, entries = set(), []
    for t in texts:
        for unit, cells in translate(t)[2]:
            if unit not in seen and not unit.isspace():
                seen.add(unit)
                entries.append((unit, cells))
    return entries[:limit]


# ---------------------------------------------------------------- NSL
_HINDI_WORDS = {
    "है", "हैं", "हूँ", "और", "करना", "करें", "करता", "करती", "करते", "किया", "यह", "वह", "ये", "वे", "में",
    "पर", "बहुत", "अच्छा", "नहीं", "क्या", "कैसे", "क्यों", "लेकिन", "भी", "साथ", "ओर", "तरफ", "उंगली",
    "हथेली", "चलाना", "दिखाना", "होता", "होती", "होते", "के", "लिए",
}


def load_glossary() -> Dict[str, dict]:
    """Verified NSL entries: {"water": {"en": "...", "ne": "...", "source": "..."}}. Keys are lower-case."""
    try:
        with open(GLOSSARY_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return {str(k).strip().lower(): v for k, v in raw.items() if isinstance(v, dict)}
    except Exception:
        return {}


def _valid_description(text: str, language: str) -> bool:
    if not text or len(text.split()) < 4:
        return False
    has_deva = bool(re.search(r"[\u0900-\u097F]", text))
    if language == "nepali":
        if not has_deva:
            return False
        tokens = set(re.findall(r"[\u0900-\u097F]+", text))
        return not (tokens & _HINDI_WORDS)
    return not has_deva


def _nsl_prompt(items: List[dict], language: str) -> str:
    target = "Nepali (Devanagari)" if language == "nepali" else "English"
    lines = "\n".join(
        f'{i}. {it.get("term_en") or it["term"]}'
        + (f' ({it["term"]})' if it.get("term_en") and it["term"] != it.get("term_en") else "")
        + (f' - {it["meaning"]}' if it.get("meaning") else "")
        for i, it in enumerate(items, 1)
    )
    rules = (
        "Write ONLY Nepali. Never use Hindi words or Hindi grammar (है, और, करना, में, के लिए, नहीं, बहुत...). "
        "Use Nepali verb endings such as गर्ने, बनाउने, हल्लाउने, छुने, देखाउने, and end each sentence with '।'."
        if language == "nepali"
        else "Write only English. Do not use Devanagari."
    )
    return f"""You describe signs for Nepali Sign Language (NSL) for a teacher.
TARGET LANGUAGE: {target}. {rules}

For each numbered concept write ONE or TWO sentences that say: which hand(s), the handshape,
where the hand is (chest, chin, forehead, neutral space), and the movement. No labels, no padding.
If you do not know an established NSL sign, describe a natural gesture that acts out or draws the idea.

Style examples:
math: Cross the index fingers of both hands to make a plus sign, then move them side to side.
water: Make a 'W' shape with three fingers and tap the side of the chin twice.
count: Tap the thumb against each fingertip in turn, starting with the index finger.

CONCEPTS:
{lines}

Return ONLY a JSON object that maps each number to its description, for example {{"1": "...", "2": "..."}}."""


def _graphemes(text: str) -> List[str]:
    """Split into letters, keeping Devanagari vowel signs and marks with their consonant."""
    out = []
    for ch in text:
        if ch.isspace():
            continue
        if out and unicodedata.category(ch) in ("Mn", "Mc") or (out and out[-1].endswith("\u094d")):
            out[-1] += ch
        else:
            out.append(ch)
    return out


def _fingerspell(term: str, lang: str) -> str:
    letters = "-".join(g.upper() if g.isascii() else g for g in _graphemes(term or ""))
    if lang == "nepali":
        return (f"स्थापित सङ्केत भेटिएन। यो शब्द अक्षर-अक्षर गरी देखाउनुहोस्: {letters}। "
                "सहमत सङ्केतबारे साङ्केतिक भाषा जान्ने व्यक्तिसँग सोध्नुहोस्।")
    return f"No established sign on file. Fingerspell the word: {letters}. Ask an NSL signer for the agreed sign."


def _resolve_media(path: str) -> str:
    if not path:
        return ""
    full = path if os.path.isabs(path) else os.path.join(BASE_DIR, path)
    return full if os.path.exists(full) else ""


def nsl_descriptions(terms: List[dict], language: str, say=None) -> List[dict]:
    """terms: [{term, term_en?, meaning?}]. Returns the same items plus description + status + image/video.

    status:
      "verified"    - from data/nsl_glossary.json (checked by a signer). May carry "image" and "video_url".
      "fingerspell" - no sign on file: show the word to fingerspell and ask a signer. (default for unknown words)
      "suggested"   - AI-drafted gesture, only when env NSL_AI_DRAFTS=1. Always needs a signer to confirm.
    Glossary entry: {"nucleus": {"en": "...", "ne": "...", "source": "...", "image": "data/nsl/nucleus.jpg", "video_url": "https://..."}}
    """
    say = say or (lambda m: None)
    lang = "nepali" if (language or "").lower() == "nepali" else "english"
    glossary = load_glossary()
    results, need_ai = [], []

    for it in terms:
        row = dict(it, description="", status="missing", source="", image="", video="")
        keys = [str(it.get("term_en") or "").strip().lower(), str(it.get("term") or "").strip().lower()]
        hit = next((glossary[k] for k in keys if k and k in glossary), None)
        if hit:
            desc = hit.get("ne" if lang == "nepali" else "en") or hit.get("en") or hit.get("ne")
            if desc:
                row.update(description=desc, status="verified", source=hit.get("source", ""),
                           image=_resolve_media(hit.get("image", "")), video=hit.get("video_url", ""))
        results.append(row)
        if row["status"] != "verified":
            need_ai.append(row)

    if need_ai and os.getenv("NSL_AI_DRAFTS") == "1":
        say("Drafting sign descriptions...")
        try:
            import ollama
            resp = ollama.chat(
                model=os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct"),
                messages=[
                    {"role": "system", "content": "You output only valid JSON."},
                    {"role": "user", "content": _nsl_prompt(need_ai, lang)},
                ],
                format="json",
                options={"temperature": 0.1, "num_predict": 900, "num_ctx": 4096},
            )
            data = json.loads(re.search(r"\{.*\}", resp["message"]["content"], re.DOTALL).group(0))
            for i, row in enumerate(need_ai, 1):
                desc = str(data.get(str(i), "")).strip().strip("\"\'")
                if lang == "nepali" and desc and not desc.endswith("।"):
                    desc = desc.rstrip(".") + "।"
                if _valid_description(desc, lang):
                    row.update(description=desc, status="suggested")
        except Exception as e:
            print(f"[NSL] could not draft descriptions: {e}")

    for row in results:
        if row["status"] not in ("verified", "suggested"):
            row.update(status="fingerspell", description=_fingerspell(row.get("term") or row.get("term_en") or "", lang))
    return results


# ---- kept so older imports do not break ----
def get_nsl_gesture_description_for_single_word(concept: str, language: str) -> str:
    return nsl_descriptions([{"term": concept, "term_en": concept}], language)[0]["description"]


def get_nsl_gesture_description_for_single_textblock(paragraph_text: str, language: str) -> list:
    return []
