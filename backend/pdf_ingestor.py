import json
import os
import ollama
import pdfplumber
import pymupdf

pdf_path = os.path.join(
    os.path.dirname(__file__), "data/pdfs/"
)
output = os.path.join(os.path.dirname(__file__), "data/json")


def extract_from_each_page(text_chunk):
  system_prompt = """You are a JSON converter script.
    Extract educational competencies from the raw Nepal CDC curriculum text into valid JSON format.

    JSON Schema format:
    [
    {
        "id": "MATH-G1-01",
        "grade": 1,
        "subject": "Mathematics",
        "topic": "Topic name (in the same language/script as the source text)",
        "competency": "Competency description (in the same language/script as the source text)",
        "teaching_strategy": "Suggested teaching method or practical activity (in the same language/script as the source text)"
    }
    ]

    LANGUAGE RULES:
    1. Detect the language and script of the source text chunk.
    2. If the source text is in Devanagari (Nepali), write "topic", "competency", and "teaching_strategy" in Devanagari Nepali.
    3. If the source text is in English, write "topic", "competency", and "teaching_strategy" in English.
    4. Never translate between languages. Always mirror the language and script of the source chunk.
    5. Keep field names ("id", "grade", "subject", "topic", "competency", "teaching_strategy") in English regardless of source language.

    OUTPUT RULES:
    1. Output ONLY a valid JSON array. No conversational text, no markdown code fences, no explanations.
    2. If no competency exists in the text chunk, return []."""

  response = ollama.chat(
      model="qwen2.5:7b-instruct",
      messages=[
          {"role": "system", "content": system_prompt},
          {"role": "user", "content": f"Raw Curriculum Text:\n{text_chunk}"},
      ],
      options={"temperature": 0.1},
  )

  try:
    content = response["message"]["content"].strip()
    if content.startswith("```json"):
      content = content[7:-3].strip()
    elif content.startswith("```"):
      content = content[3:-3].strip()
    return json.loads(content)
  except Exception as e:
    print(f"Error parsing page chunk: {e}")
    return []


def find_chapters(single_pdf_path):
  doc = pymupdf.open(single_pdf_path)
  toc = doc.get_toc()  #
  chapters = []

  if toc:
    print(f"Found {len(toc)} bookmark entries in TOC.")
    for i, item in enumerate(toc):
      level, title, start_page = item
      end_page = toc[i + 1][2] - 1 if i + 1 < len(toc) else len(doc)
      chapters.append({
          "title": title.strip(),
          "start_page": start_page,
          "end_page": max(start_page, end_page),
      })
  else:
    print("No bookmarks/TOC found. Falling back to page-by-page mapping.")
    total_pages = len(doc)
    for i in range(total_pages):
      chapters.append({
          "title": f"Page {i + 1}",
          "start_page": i + 1,
          "end_page": i + 1,
      })

  doc.close()
  return chapters


def process_pdf(single_pdf_path):
    all_standards = []
    
    # Load existing data if file already exists so we don't overwrite
    output_json_path = os.path.join(output, "cdc_standards.json")
    if os.path.exists(output_json_path):
        with open(output_json_path, "r", encoding="utf-8") as f:
            try:
                all_standards = json.load(f)
            except Exception:
                all_standards = []

    chapters = find_chapters(single_pdf_path)
    print(f"Starting extraction across {len(chapters)} tracked sections...")

    with pdfplumber.open(single_pdf_path) as pdf:
        for chap in chapters:
            start = chap["start_page"] - 1
            end = chap["end_page"]

            for page_num in range(start, end):
                if page_num < len(pdf.pages):
                    page = pdf.pages[page_num]
                    text = page.extract_text()

                    if text and len(text.strip()) > 50:
                        print(f"Extracting competencies from: {chap['title']} (Page {page_num + 1})")
                        extracted = extract_from_each_page(text)

                        if isinstance(extracted, list) and extracted:
                            for item in extracted:
                                item["source_page"] = page_num + 1
                                item["chapter"] = chap["title"]
                                item["source_file"] = os.path.basename(single_pdf_path)  # Tag original filename
                            all_standards.extend(extracted)

    # Write merged results back
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(all_standards, f, ensure_ascii=False, indent=2)

    print(f"Finished {os.path.basename(single_pdf_path)}! Total standards stored so far: {len(all_standards)}")


if __name__ == "__main__":
    if not os.path.exists(pdf_path):
        print(f"Error: Directory '{pdf_path}' does not exist.")
    else:
        pdf_files = [f for f in os.listdir(pdf_path) if f.lower().endswith('.pdf')]
        
        print(f"Found {len(pdf_files)} PDF(s) to process in {pdf_path}\n")
        
        for filename in pdf_files:
            full_pdf_path = os.path.join(pdf_path, filename)
            print(f"==========================================")
            print(f"Processing PDF: {filename}")
            print(f"==========================================")
            
            process_pdf(full_pdf_path)