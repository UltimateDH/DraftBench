import json
import os
import re
import ollama
import pdfplumber
from pydantic import BaseModel, Field
from typing import List
from concurrent.futures import ThreadPoolExecutor, as_completed

pdf_path = os.path.join(os.path.dirname(__file__), "data/pdfs/")
output = os.path.join(os.path.dirname(__file__), "data/json")

class CurriculumItem(BaseModel):
    topic: str = Field(description="Topic or lesson title")
    competency: str = Field(description="What the student learns or solves")
    teaching_strategy: str = Field(description="Teaching method or practical activity")

class PageExtraction(BaseModel):
    items: List[CurriculumItem]

def extract_from_single_page(args):
    """Processes a single page using strict language prompts based on the subject and language flag."""
    text_chunk, page_num, subject, grade, base_name, is_english = args
    
    if not text_chunk or len(text_chunk.strip()) <= 30:
        return []

    if is_english:
        system_prompt = f"""You are an expert curriculum data parser for Nepal's CDC curriculum.
Analyze the textbook page and extract core learning concepts.

CRITICAL RULES:
1. STRICTLY CONSOLIDATE: Extract AT MOST 2 to 3 core curriculum items per page. NEVER list individual exercises, drills, or minor repetitive sub-topics.
2. LANGUAGE: Write 100% in pure English. Do NOT use any Nepali or Hindi words, letters, or Devanagari script.
3. PRACTICAL ACTIVITIES: Provide actionable teaching methods (e.g., phonics games, role-playing, flashcards, guided practice). Avoid generic filler like 'teach the lesson'.
4. GRADE APPROPRIATENESS: Target Grade {grade} students. Do not mention nursery or pre-school.
5. Return an empty list [] for cover pages, contents, or non-educational pages."""
    else:
        system_prompt = f"""You are an expert curriculum data parser for Nepal's CDC curriculum.
Analyze the textbook page and extract overarching curriculum concepts.

CRITICAL RULES:
1. STRICTLY CONSOLIDATE: Extract AT MOST 2 to 3 core curriculum items per page. NEVER list individual exercise questions or drills.
2. LANGUAGE: Write 100% in pure Nepali (नेपाली). Do NOT use English script or Hindi words.
   - FORBIDDEN HINDI WORDS: 'और', 'दशक', 'मूल्य ज्ञात करना', 'सैकड़ा', 'ज्ञात कीजिए', 'अंतर'.
   - MANDATORY NEPALI TERMS: Use 'र', 'दहाइ', 'मान पत्ता लगाउने', 'सय', 'पत्ता लगाउनुहोस्', 'फरक'.
3. PRACTICAL ACTIVITIES: Provide actionable teaching methods (e.g., counters, seeds, NPR currency notes). Never use generic filler like 'व्यवस्थित शिक्षण'.
4. GRADE APPROPRIATENESS: Target Grade {grade} students. Do not mention nursery or pre-school.
5. Return an empty list [] for cover pages, contents, or non-educational pages."""

    try:
        response = ollama.chat(
            model="qwen2.5:7b-instruct",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Source Text (Page {page_num}):\n{text_chunk}"},
            ],
            options={
                "temperature": 0.1,
                "num_ctx": 4096,
                "num_predict": 1024,
                "num_thread": 4
            },
            keep_alive="1h",
            format=PageExtraction.model_json_schema(),
        )

        content = response["message"]["content"].strip()
        parsed_data = PageExtraction.model_validate_json(content)
        
        extracted_items = []
        for item in parsed_data.items:
            extracted_items.append({
                "grade": grade,
                "subject": subject,
                "topic": item.topic.strip(),
                "competency": item.competency.strip(),
                "teaching_strategy": item.teaching_strategy.strip(),
                "chapter": f"Page {page_num}",
                "source_page": page_num,
                "source_file": base_name
            })
        print(f"[{base_name}] Page {page_num} Extracted ({subject}) ✓")
        return extracted_items

    except Exception as e:
        print(f"Error parsing page {page_num}: {e}")
        return []

def deduplicate_records(records):
    """Filters out duplicate topics/competencies within the extracted batch."""
    seen = set()
    unique_records = []
    
    for r in records:
        sig = (r["subject"].lower(), r["grade"], r["topic"].strip().lower(), r["competency"].strip().lower())
        if sig not in seen:
            seen.add(sig)
            unique_records.append(r)
            
    return unique_records

def process_pdf_safe(single_pdf_path):
    output_json_path = os.path.join(output, "cdc_standards.json")
    
    existing_data = []
    if os.path.exists(output_json_path):
        with open(output_json_path, "r", encoding="utf-8") as f:
            try: existing_data = json.load(f)
            except: existing_data = []

    base_name = os.path.basename(single_pdf_path)
    base_lower = base_name.lower()

    # 1. Extract Grade (handles 'class 7', 'grde-11', 'grade_11', 'csgrade 10', etc.)
    grade_match = re.search(r'(?:class|grde|grade|csgrade)[-_]?\s*(\d+)', base_lower)
    if grade_match:
        grade = int(grade_match.group(1))
    else:
        digits = re.findall(r'\d+', base_lower)
        grade = int(digits[1]) if len(digits) > 1 else (int(digits[0]) if len(digits) == 1 else 2)

    # 2. Extract Subject & Determine Language with Correct Priority
    if any(kw in base_lower for kw in ["math", "mathematics", "गणित"]):
        subject = "Mathematics"
        is_english = True if "englishtranslation" in base_lower or "english" in base_lower else False
        prefix = "MAT"
    elif "physics" in base_lower:
        subject = "Physics"
        is_english = False
        prefix = "PHY"
    elif "chemistry" in base_lower:
        subject = "Chemistry"
        is_english = False
        prefix = "CHE"
    elif "biology" in base_lower:
        subject = "Biology"
        is_english = False
        prefix = "BIO"
    elif "science" in base_lower or "sc" in base_lower:
        subject = "Science"
        is_english = False
        prefix = "SCI"
    elif any(kw in base_lower for kw in ["samajik", "social"]):
        subject = "Social Studies"
        is_english = False
        prefix = "SOC"
    elif "account" in base_lower:
        subject = "Accountancy"
        is_english = False
        prefix = "ACC"
    elif "health" in base_lower:
        subject = "Health"
        is_english = False
        prefix = "HLT"
    elif "economics" in base_lower:
        subject = "Economics"
        is_english = False
        prefix = "ECO"
    elif "computer" in base_lower or "cs" in base_lower:
        subject = "Computer Science"
        is_english = False
        prefix = "CSC"
    elif "nepali" in base_lower or "nep" in base_lower:
        subject = "Nepali"
        is_english = False
        prefix = "NEP"
    elif "english" in base_lower or base_lower.startswith("eng"):
        subject = "English"
        is_english = True
        prefix = "ENG"
    else:
        subject = "General"
        is_english = False
        prefix = "GEN"

    print(f"\nProcessing: {base_name} | Subject: {subject} | Grade: {grade} | English Mode: {is_english}")

    page_tasks = []
    with pdfplumber.open(single_pdf_path) as pdf:
        total_pages = len(pdf.pages)
        start_page = 5 if total_pages > 5 else 0
        
        for idx in range(start_page, total_pages):
            page_num = idx + 1
            text = pdf.pages[idx].extract_text()
            if text and len(text.strip()) > 30:
                page_tasks.append((text, page_num, subject, grade, base_name, is_english))

    print(f"Dispatched {len(page_tasks)} pages to GPU threads...")

    raw_records = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(extract_from_single_page, task) for task in page_tasks]
        
        for future in as_completed(futures):
            res = future.result()
            if res:
                raw_records.extend(res)

    unique_new_records = deduplicate_records(raw_records)

    global_counter = len(existing_data) + 1
    for record in unique_new_records:
        record["id"] = f"{prefix}-G{grade}-{global_counter:03d}"
        global_counter += 1

    existing_data.extend(unique_new_records)
    
    os.makedirs(output, exist_ok=True)
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(existing_data, f, ensure_ascii=False, indent=2)

    print(f"Finished {base_name}! Added {len(unique_new_records)} unique records. Master total: {len(existing_data)}")

if __name__ == "__main__":
    if not os.path.exists(pdf_path):
        print(f"Error: Directory '{pdf_path}' does not exist.")
    else:
        pdf_files = [f for f in os.listdir(pdf_path) if f.lower().endswith('.pdf')]
        print(f"Found {len(pdf_files)} PDF(s) to process in {pdf_path}\n")
        
        for filename in pdf_files:
            process_pdf_safe(os.path.join(pdf_path, filename))