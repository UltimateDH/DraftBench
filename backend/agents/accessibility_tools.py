import os
import ollama
import re
import json

#this consists of both english, nepali with words and digits
BRAILLE_MAP = {
  
    'a': '⠁', 'b': '⠃', 'c': '⠉', 'd': '⠙', 'e': '⠑', 'f': '⠋', 'g': '⠛',
    'h': '⠓', 'i': '⠊', 'j': '⠚', 'k': '⠅', 'l': '⠇', 'm': '⠍', 'n': '⠝',
    'o': '⠕', 'p': '⠏', 'q': '⠟', 'r': '⠗', 's': '⠎', 't': '⠞', 'u': '⠥',
    'v': '⠧', 'w': '⠺', 'x': '⠭', 'y': '⠽', 'z': '⠵', ' ': ' ',
    '1': '⠂', '2': '⠆', '3': '⠒', '4': '⠲', '5': '⠢', '6': '⠖',
    '7': '⠶', '8': '⠦', '9': '⠔', '0': '⠴',


    'अ': '⠁', 'आ': '⠜', 'इ': '⠊', 'ई': '⠔', 'उ': '⠥', 'ऊ': '⠳',
    'ऋ': '⠐⠗', 'ए': '⠌', 'ऐ': '⠮', 'ओ': '⠕', 'औ': '⠪',

    'क': '⠅', 'ख': '⠨', 'ग': '⠛', 'घ': '⠣', 'ङ': '⠬',
    'च': '⠉', 'छ': '⠡', 'ज': '⠚', 'झ': '⠴', 'ञ': '⠒',
    'ट': '⠞', 'ठ': '⠹', 'ड': '⠙', 'ढ': '⠮', 'ण': '⠼',
    'त': '⠞', 'थ': '⠹', 'द': '⠙', 'ध': '⠮', 'न': '⠝',
    'प': '⠏', 'फ': '⠋', 'ब': '⠃', 'भ': '⠘', 'म': '⠍',
    'य': '⠽', 'र': '⠗', 'ल': '⠇', 'व': '⠧',
    'श': '⠩', 'ष': '⠯', 'स': '⠎', 'ह': '⠓', 'ळ': '⠿',
    'क्ष': '⠟', 'ज्ञ': '⠟',

    '०': '⠴', '१': '⠂', '२': '⠆', '३': '⠒', '४': '⠲',
    '५': '⠢', '६': '⠖', '७': '⠶', '८': '⠦', '९': '⠔',
}

#this should return the text in the braille format in the structured format as intented in the text
def return_braille(text:str)->str:
    if not text:
        return ""
    return "".join(BRAILLE_MAP.get(char.lower(),char) for char in text)



def get_nsl_gesture_description_for_single_word(concept:str,language:str)->str:

    target_language = (language or "english").lower().strip()
    prompt=f"""You are an expert Nepali Sign Language (NSL) describer. You write precise, signable
gesture descriptions in the style of Deaf-community NSL documentation. You are
pedantic about language purity.

    ## HARD LANGUAGE RULES

    - If TARGET_LANGUAGE is "nepali", every word of your output MUST be Nepali.
    You must NEVER output Hindi. Hindi is a different language even though it shares
    the Devanagari script. A single Hindi word invalidates your answer.
    - If TARGET_LANGUAGE is "english", output only English. Do not include any Devanagari.
    - Do not mix languages. Do not add parenthetical translations.

    ### Hindi words you must NEVER use (replace with the Nepali equivalent)

    है/हैं/हूँ      → use  छ / छन् / छु  (or restructure so no copula is needed)
    और             → र
    करना/करें/करता/करती/करते/किया → गर्नु / गर्ने / गर्छ / गरे / गरी / गर्दै
    यह/वह/ये/वे     → यो / त्यो / यी / ती
    में             → मा
    पर (on)        → मा / माथि
    के लिए         → लागि
    बहुत           → धेरै
    अच्छा          → राम्रो
    नहीं           → छैन
    क्या/कैसे/क्यों → के / कसरी / किन
    लेकिन          → तर
    भी             → पनि
    साथ            → सँग
    ओर/तरफ         → तर्फ
    उंगली          → औंला
    हथेली          → हत्केला
    चलाना          → चलाउनु / हल्लाउनु
    दिखाना         → देखाउनु
    होता/होती/होते  → हुन्छ / हुने

    ### Positive Nepali signals — your output should be full of these

    Verb endings:  गर्नु, गर्ने, गर्छ, गर्दै, गरी, गरेर, बनाउने, हल्लाउने, छुने,
                    खोल्ने, जोड्ने, देखाउने, चलाउने, राख्ने, तान्ने, घुमाउने
    Particles:     र, पनि, तर, मा, बाट, ले, सँग, लागि, तर्फ, सम्म
    Body parts:    औंला, चोर औंला (index), बुढी औंला (thumb), माझी औंला (middle),
                    हत्केला, चिउँडो, निधार, छाती, काँध, नाक
    Quantity:      दुई पटक, क्रमैसँग, दायाँ-बायाँ, माथि-तल, अगाडि-पछाडि
    Sentence end:  ।  (Nepali danda — required, never ".")

    English loanwords in Devanagari transliteration (क्रस, साइन, 'W' आकार) are
    ACCEPTABLE and common in Nepali. The ban is on Hindi grammar and Hindi-only words,
    not on loanwords.

    ## GESTURE DESCRIPTION FRAMEWORK

    Describe the gesture using these five parameters, in this order, compressed into
    1–2 natural sentences (do not label the parameters):

    1. HAND(S)      — one- or two-handed
    2. HANDSHAPE    — which fingers extended/curled; palm shape
    3. ORIENTATION  — palm direction (inward, outward, upward, sideways)
    4. LOCATION     — signing space (neutral space, chest, chin, forehead, cheek)
    5. MOVEMENT     — path, direction, repetition, manner (tap, circle, open, cross)

    Include a non-manual marker (facial expression) only if it is essential to the sign.

    ## HONESTY RULE

    If the concept has an established NSL sign, describe it directly.
    If the concept is abstract or has no established NSL sign, describe a natural
    iconic or metonymic gesture that a Deaf Nepali signer would plausibly use, and
    begin the description with the word "सङ्केत" (Nepali) or "Suggested" (English)
    so the reader knows it is an approximation, not a certified dictionary entry.

    ## FEW-SHOT EXAMPLES (match this voice exactly)

    ENGLISH:
    math  → "Cross the index fingers of both hands to form a plus sign (+),
            then move them side-to-side."
    water → "Form a 'W' shape with the fingers and tap the index finger against
            the side of the chin twice."
    count → "Tap the thumb sequentially against each fingertip, starting from
            the index finger."

    NEPALI:
    math  → "दुवै चोर औंला क्रस गरी जोड चिन्ह (+) बनाउने र दायाँ-बायाँ हल्लाउने।"
    water → "औंलाले 'W' आकार बनाउने र चोर औंलाले चिउँडोमा दुई पटक छुने।"
    count → "चोर औंलाबाट सुरु गर्दै क्रमैसँग प्रत्येक औंलाको टुप्पोमा बुढी औंलाले छुने।"

    Notice the Nepali examples use गरी, बनाउने, हल्लाउने, छुने, क्रमैसँग — pure Nepali.

    ## SELF-CHECK BEFORE YOU ANSWER

    Before emitting, silently verify:
    1. Is every word in the target language? Scan for each Hindi word in the
        blacklist above. If any appears, rewrite.
    2. Does the Nepali use a Nepali verb ending (गर्ने/गर्छ/गरी/...), not a Hindi
        one (करना/करता/किया/है)?
    3. Does it end with "।" (Nepali) or "." (English)?
    4. Does it name a handshape AND a movement? A description without movement is
        incomplete.
    5. Is it 1–2 sentences? Do not pad.

    Return ONLY the description. No preamble, no labels, no explanation."""

    if concept is None:
        return ""
    
    try:
        response = ollama.chat(
            model="qwen2.5:7b-instruct",
            messages=[
                {
                    "role": "system",
                    "content": "You are a specialized linguistic translator. Respond strictly with the final gesture description only, without quotes or additional text.",
                },
                {"role": "user", "content": prompt},
            ],
            options={"temperature": 0.1},
        )
        content=response["message"]["content"].strip()
        content = re.sub(r'^["\'`]+|["\'`]+$', "", content).strip()
        return content

    except Exception as e:
        print(f"[NSL Tool Error] Failed to generate NSL description: {e}")
        if target_language == "nepali":
            return f"साङ्केतिक सङ्केत: '{concept}' अवधारणा व्यक्त गर्ने उपयुक्त हत्केलाको आकृति र इशारा।"
        return f"NSL Gesture: Standardized handshape and motion describing '{concept}'."




def get_nsl_gesture_description_for_single_textblock(paragraph_text:str,language:str)->list:
    target_lang=(language or "english").lower().strip()

    extraction_prompt="""You extract signing-friendly concepts from educational text for a
Nepali Sign Language (NSL) accessibility system.

A "signing-friendly concept" is a word or short phrase that falls into one of these:

  1. CONCRETE OBJECT     — a thing you can point to or draw
                           (book, water, tree, hand, bicycle, rice, house)
  2. PHYSICAL ACTION     — a movement you can demonstrate with the hands
                           (count, open, write, eat, run, climb, wash)
  3. BODY / NATURE / ANIMAL — a living thing or body part
                           (eye, ear, leaf, fish, mother, child)
  4. BASIC SPATIAL / QUANTITY — a relationship that is easy to sign
                           (above, inside, many, small, first)

DO NOT extract:
  - Abstract nouns             (importance, development, freedom, system, process, idea)
  - Proper nouns / names       (Kathmandu, Ram, Google, Monday)
  - Numbers, dates, times      (1945, three, Tuesday)
  - Function words             (the, and, because, is)
  - Whole sentences or clauses (NOT "students memorize tables")

RULES
  1. Return 3 to 5 concepts, ordered by how central they are to the paragraph.
  2. Every concept must appear in, or be directly implied by, the paragraph.
  3. Prefer the SIMPLEST form: "river" over "flowing river system";
     "eat" over "consumption of food".
  4. ALWAYS output concepts in ENGLISH, even if the paragraph is Nepali or mixed.
     (Downstream NSL lookup uses English keys.)
  5. If the paragraph is fully abstract and contains fewer than 3 concrete terms,
     return the concrete supporting terms you can find — "vote" and "leader" from a
     paragraph about democracy, for instance. Never invent concepts.
  6. Return ONLY a JSON array of lowercase English strings. No explanation,
     no markdown fences, no labels.

EXAMPLES

  Paragraph: "Water is essential for life. Plants absorb water through their roots
              and use sunlight to make food."
  Output: ["water", "plant", "root", "sunlight"]

  Paragraph: "The multiplication table helps students count quickly. Students
              memorize tables from 1 to 10."
  Output: ["count", "table", "student"]

  Paragraph: "Democracy is a system of government where citizens vote for their
              leaders."
  Output: ["vote", "leader"]
  (Note: "democracy" and "system" were rejected as abstract; only the concrete
   actions and roles were kept.)

  Paragraph: "सूर्य पूर्वबाट उदाउँछ र बिहानको प्रकाशले बालबालिकालाई खुसी बनाउँछ।"
  Output: ["sun", "light", "child"]
  (English concepts even though the paragraph is Nepali.)

PARAGRAPH:
"{paragraph_text}"

JSON output (array of English strings only):
["concept1", "concept2", ...]"""


    try:
        response = ollama.chat(
            model="qwen2.5:7b-instruct",
            messages=[{"role": "user", "content": extraction_prompt}],
            options={"temperature": 0.0, "format": "json"}
        )
        raw = response["message"]["content"]
        clean_json = re.search(r'\[.*\]', raw, re.DOTALL).group(0)
        key_concepts = json.loads(clean_json)
    except Exception as e:
        print(f"[Accessibility Extractor Warning] Extraction failed, using fallback: {e}")
        # Fallback: Split paragraph into simple clauses or words
        key_concepts = [c.strip() for c in paragraph_text.split(".") if c.strip()][:3]

    accessibility_items = []

    # Loop through each extracted concept and build structured requests
    for concept in key_concepts:
        nsl_desc = get_nsl_gesture_description_for_single_word(concept, language=target_lang)
        braille_pattern = return_braille(concept)
        
        # Prepare structured SVG generation request payload
        svg_request = {
            "vdescription": f"Literal PECS icon representing {concept}",
            "concept_name": concept,
            "filename_prefix": "PECS_ICON"
        }

        accessibility_items.append({
            "concept": concept,
            "nsl_gesture": nsl_desc,
            "braille": braille_pattern,
            "svg_request_payload": svg_request
        })

    return accessibility_items
