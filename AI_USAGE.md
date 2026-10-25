# AI Usage Disclosure: DraftBench

|                              |                                                                                                                         |
| ---------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| **Project**                  | DraftBench                                                                                                              |
| **Repository**               | https://github.com/UltimateDH/DraftBench                                                                                |
| **Purpose of this document** | Declares every point in the codebase where machine-learning model output is produced and then consumed programmatically |
| **Last updated**             | 2026-10-25                                                                                                              |

---

## Table of Contents

1. [Core AI Integration and Purpose](#1-core-ai-integration-and-purpose)
2. [Models and Runtime](#2-models-and-runtime)
3. [Codebase Mapping (File and Function Level)](#3-codebase-mapping-file-and-function-level)
4. [End-to-End Data Flow](#4-end-to-end-data-flow)
5. [Execution Environment](#5-execution-environment)
6. [Output Validation and Failure Handling](#6-output-validation-and-failure-handling)
7. [How to Verify This Disclosure](#7-how-to-verify-this-disclosure)

---

## 1. Core AI Integration and Purpose

In DraftBench, AI is **core business logic**. It is not a chat window and not a text box that echoes a model reply. The models classify intent, reason over retrieved curriculum data, produce structured records that other code depends on, and take part in an automatic self-correction loop. Remove the models and the pipeline has nothing to route, retrieve, plan, or draw.

| Role of AI                                                   | What the model does                                                                                                       | What the code does with the result                                                                                                                                                                    |
| ------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Intent classification and parameter extraction**           | Turns a free-text teacher prompt into a typed JSON record (intent, topic, grade, subject, language, ASD-adaptation flag). | Parses it, uses `intent` to choose the pipeline branch, and uses grade and subject as retrieval filters.                                                                                              |
| **Autonomous self-correction (CoIEP writer-evaluator loop)** | Writes structured lesson content as strict JSON.                                                                          | A rule-based ASD rubric scores each draft out of 10. A score below 8 is converted into itemised corrections that are fed back into the next generation, up to 3 attempts, and the best draft is kept. |
| **Retrieval-grounded reasoning (local RAG)**                 | `nomic-embed-text` embeds the topic and the CDC curriculum records.                                                       | ChromaDB similarity search with grade and subject metadata filters. The retrieved standards are injected into generation prompts.                                                                     |
| **Structured knowledge extraction**                          | Reads CDC textbook pages and returns schema-constrained JSON.                                                             | Validated with Pydantic, de-duplicated, and stored as curriculum records for embedding.                                                                                                               |
| **Structured content generation**                            | Writes teacher support, the IEP goal, quiz questions, and Braille and sign-language study sheets as JSON.                 | Normalised, validated, de-duplicated, and merged into the lesson plan or rendered into export files.                                                                                                  |
| **Dynamic vector asset generation**                          | Writes SVG markup for diagrams and schematic sign-language hand illustrations.                                            | Extracted by pattern match, rendered to PNG by CairoSVG, and embedded in the exported documents.                                                                                                      |

---

## 2. Models and Runtime

All models are open-weight and are run locally.

| Component            | Exact identifier                | Developer          | Served by           | License    | Role in DraftBench                                              |
| -------------------- | ------------------------------- | ------------------ | ------------------- | ---------- | --------------------------------------------------------------- |
| Large language model | `qwen2.5:7b-instruct`           | Qwen team, Alibaba | Ollama (local)      | Apache 2.0 | Classification, structured generation, extraction, SVG drafting |
| Embedding model      | `nomic-embed-text`              | Nomic AI           | Ollama (local)      | Apache 2.0 | Embeddings for CDC curriculum retrieval                         |
| Inference runtime    | Ollama (Python client `ollama`) | Ollama             | Local process       | MIT        | Hosts both models; called from the backend                      |
| Vector store         | ChromaDB (persistent client)    | Chroma             | Embedded in backend | Apache 2.0 | Stores and searches CDC curriculum embeddings                   |
| SVG renderer         | CairoSVG                        | Kozea              | Embedded in backend | LGPL-3.0   | Renders model-generated SVG to PNG                              |

Where the identifiers are set:

- `qwen2.5:7b-instruct` is the default of the `OLLAMA_MODEL` environment variable in `backend/agents/unified_pipeline.py` and `backend/agents/content_agent.py`, and is named directly in `backend/agents/svg_agent.py` and `backend/pdf_ingestor.py`.
- `nomic-embed-text` is named directly in `backend/rag.py`.

The model weights are pulled once with `ollama pull` before deployment. After that, no model is downloaded or contacted over a network.

---

## 3. Codebase Mapping (File and Function Level)

### 3.1 Every AI Invocation

| ID  | Capability                                      | File                                    | Function                                                                                     | Model                  | Output contract                                                                     | Programmatic consumption                                                                                                         |
| --- | ----------------------------------------------- | --------------------------------------- | -------------------------------------------------------------------------------------------- | ---------------------- | ----------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| A1  | Intent classification and parameter extraction  | `backend/agents/unified_pipeline.py`    | `classify_intent_and_extract_params()`                                                       | `qwen2.5:7b-instruct`  | JSON: `intent`, `topic`, `grade`, `subject`, `language`, `needs_autism_adaptations` | Selects the pipeline branch; supplies RAG filters and language                                                                   |
| A2  | CoIEP writer (lesson content)                   | `backend/agents/unified_pipeline.py`    | `plan_slide_content()` using `_chat_json()`                                                  | `qwen2.5:7b-instruct`  | JSON: `lesson_meta` and `slides[]`                                                  | Repaired by `normalize_plan()`, then scored by `evaluate_content_plan()`                                                         |
| A3  | CoIEP evaluator (rubric gate on model output)   | `backend/agents/unified_pipeline.py`    | `evaluate_content_plan()` (rule-based; called inside `plan_slide_content()`)                 | None (rule-based code) | `(score, feedback[])`                                                               | `score >= 8` accepts the draft; otherwise `feedback` is injected into the next prompt                                            |
| A4  | Teacher support and IEP goal                    | `backend/agents/unified_pipeline.py`    | `plan_teacher_support()` then `merge_support()`                                              | `qwen2.5:7b-instruct`  | JSON: per-slide support text, `iep_goal`, accommodations                            | Merged into the plan consumed by the Markdown, PDF, and PPTX builders                                                            |
| A5  | Query embedding and curriculum retrieval        | `backend/rag.py`                        | `query_curriculum_rag()`                                                                     | `nomic-embed-text`     | Embedding vector                                                                    | ChromaDB `collection.query()` with grade and subject filters; retrieved text is injected into prompts                            |
| A6  | Curriculum index embedding                      | `backend/rag.py`                        | `initialize_vector_database()`                                                               | `nomic-embed-text`     | Embedding vectors (batches of 100)                                                  | `collection.upsert()` into the persistent ChromaDB collection                                                                    |
| A7  | Curriculum extraction from textbook pages       | `backend/pdf_ingestor.py`               | `extract_from_single_page()`                                                                 | `qwen2.5:7b-instruct`  | Schema-constrained JSON (`PageExtraction`)                                          | Validated by `model_validate_json()`, de-duplicated by `deduplicate_records()`, saved as curriculum records                      |
| A8  | Quiz generation                                 | `backend/agents/quiz_agent.py`          | `build_quiz()` using `chat_json()`                                                           | `qwen2.5:7b-instruct`  | JSON: `questions[]` (mcq, true_false, fill_blank)                                   | Each question is cleaned by `_clean_question()` and de-duplicated by `is_duplicate()`; rendered to the quiz PDF                  |
| A9  | Key content for Braille and sign-language cards | `backend/agents/content_agent.py`       | `build_key_content()` using `chat_json()`                                                    | `qwen2.5:7b-instruct`  | JSON: `title`, `key_points[]`, `key_terms[]`                                        | Length-filtered and cleaned; drives Braille translation and NSL term selection                                                   |
| A10 | Dynamic SVG illustration                        | `backend/agents/svg_agent.py`           | `generate_educational_svg()`                                                                 | `qwen2.5:7b-instruct`  | Raw SVG markup                                                                      | Extracted with a regex, rendered by `cairosvg.svg2png()`, path stored in the slide or card for embedding                         |
| A11 | Sign instruction and schematic hand sign        | `backend/agents/svg_agent.py`           | `generate_hand_sign_instruction_and_illustration()`, called by `add_nsl_svg_illustrations()` | `qwen2.5:7b-instruct`  | JSON: `{"instruction": "..."}` then SVG                                             | Instruction text becomes the card description and the prompt for A10 (`is_sign=True`)                                            |
| A12 | Sign description drafts (optional)              | `backend/agents/accessibility_tools.py` | `nsl_descriptions()`                                                                         | `qwen2.5:7b-instruct`  | JSON keyed by term index                                                            | Validated by `_valid_description()`; accepted entries are marked `suggested` for signer review. Only runs when `NSL_AI_DRAFTS=1` |

`backend/testing_model.py` also calls the model, but it is a standalone connectivity check and is not part of the runtime pipeline.

### 3.2 Intent Classification and Parameter Extraction

**File:** `backend/agents/unified_pipeline.py` | **Function:** `classify_intent_and_extract_params()`

- The model is called through `ollama.chat` at temperature `0.0`, with a system prompt that defines the exact JSON schema.
- **Output contract:** `intent` is one of `chat`, `presentation`, `document`, `quiz`, `braille`, `nsl`. The record also holds `topic`, `grade`, `subject`, `language` (`nepali` or `english`), and `needs_autism_adaptations`.
- **Parsing:** a regular expression isolates the JSON object and `json.loads` parses it. If parsing fails, a code fallback returns safe defaults and detects Devanagari script to choose the language.
- **Consumption in `run_unified_pipeline()`:**
  - Values passed in by the caller override the model's values.
  - `topic` falls back to `derive_topic()` when the model returns none.
  - The parameters are stored with `get_or_update_session()`.
  - `intent` controls the branch: `quiz`, `braille`, and `nsl` go to `special_outputs.run_special_output()`; everything else runs the lesson pipeline.
  - `grade` and `subject` become the metadata filters for `query_curriculum_rag()`.
  - `language` selects the instruction block added to every later prompt.

### 3.3 CoIEP Writer-Evaluator Loop

**File:** `backend/agents/unified_pipeline.py` | **Functions:** `plan_slide_content()`, `evaluate_content_plan()`, `normalize_plan()`, `plan_teacher_support()`, `merge_support()`

**Stage A: writer and evaluator**

1. `plan_slide_content()` asks the model for 5 to 7 lesson slides as strict JSON through `_chat_json()` (`format="json"`, temperature 0.3). The prompt requires literal language, factual sentences, one idea per slide, and 2 to 3 bullets.
2. `normalize_plan()` repairs the shape of the model JSON (types, allowed `slide_type` values, string cleaning, bullet splitting) so later steps can rely on it.
3. `evaluate_content_plan()` scores the draft out of 10 with rule-based checks for ASD-friendly content:

| Check                                                                                                                                                                                                                                                                 | Penalty |
| --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------- |
| Slide count outside 5 to 7                                                                                                                                                                                                                                            | -2      |
| Per slide (capped at -2 per slide): not 2 to 3 bullets; imperative or teacher-talk text; repeated bullet; bullet under 5 words or over 16 words; missing or out-of-range `key_idea`; missing or too-short `explanation`, or a sentence over 20 words; missing example | -1 each |
| Repeated examples across slides                                                                                                                                                                                                                                       | -2      |
| Slides drifting off the requested topic                                                                                                                                                                                                                               | -2      |
| Hindi vocabulary in Nepali-language output                                                                                                                                                                                                                            | -3      |

4. **Self-correction:** if the score is below 8, every failed check becomes a sentence in a `CORRECTIONS REQUIRED` block (first 12 items) that is added to the next prompt. If the model returns invalid JSON, that failure is also fed back. The loop runs for up to 3 attempts and keeps the best-scoring draft; a score of 8 or more ends it early.
5. If no slides are produced, `run_unified_pipeline()` returns a `planner_failed` error instead of continuing.

**Stage B: teacher support and IEP**

- `plan_teacher_support()` asks the model for teacher scripts, communication support, sensory notes, the IEP goal, and accommodations, with up to 2 attempts when the response cannot be parsed.
- `merge_support()` writes `teacher_script`, `communication_support`, and `sensory_note` onto each slide, sets `iep_goal` (with code defaults for `baseline_probe` and `measurable_criteria`), and copies fields such as `visual_schedule`, `accommodations`, `modifications`, `prompt_hierarchy`, `reinforcement_plan`, `sensory_accommodations`, and `calm_down_strategy` into the plan.
- The merged plan is consumed by `build_lesson_markdown()` and the PDF and PPTX generators.

### 3.4 Local RAG over CDC Curriculum Standards

**Files:** `backend/rag.py` (retrieval and indexing), `backend/pdf_ingestor.py` (record extraction) | **Store:** ChromaDB persistent client, collection `cdc_curriculumn_standards`, directory `backend/data/chromadb`

- **Extraction:** `extract_from_single_page()` sends one textbook page to the model with a JSON schema (`PageExtraction.model_json_schema()`) as the output format, at temperature 0.1. The response is validated with `model_validate_json()`. Each page yields at most 2 to 3 records (grade, subject, topic, competency, teaching strategy).
- **Indexing:** `initialize_vector_database()` reads the curriculum records, builds a text document per record, embeds them in batches of 100 with `ollama.embed(model="nomic-embed-text")`, and writes them with `collection.upsert()`.
- **Retrieval:** `query_curriculum_rag(user_query, grade_filter, subject_filter, top_k=3)` embeds the topic, applies a `where` filter on grade and subject, and calls `collection.query()`. It returns formatted standards (`Standard N [Subject Grade G]`) plus the metadata for source attribution.
- **Consumption:** `run_unified_pipeline()` passes the topic, grade, and subject, then `filter_curriculum()` keeps only relevant results. The text is injected into the writer, quiz, and key-content prompts, and the source list is returned with the output.
- **Failure handling:** if the embedding call fails, retrieval returns a placeholder message and the pipeline continues without curriculum context.

### 3.5 Dynamic Vector Asset Generation

**File:** `backend/agents/svg_agent.py` | **Functions:** `generate_educational_svg()`, `generate_hand_sign_instruction_and_illustration()`, `add_nsl_svg_illustrations()` | **Renderer:** CairoSVG

- `generate_educational_svg()` chooses one of two system prompts: general educational diagrams, or schematic sign-language hand illustrations (palm shape, finger lines, movement arrows). The model replies with raw SVG on a fixed 500 by 340 canvas.
- The SVG is extracted with the pattern `<svg ... </svg>`. If extraction fails or the model errors, a built-in fallback vector is written instead, so a valid image is always produced.
- `cairosvg.svg2png()` renders the SVG to a 600 by 408 PNG. The temporary SVG file is removed, and the PNG path is stored on the slide (`png_path`) or the sign card (`sign_illustration`) for embedding in the exported PDF or PPTX.
- `generate_hand_sign_instruction_and_illustration()` first asks the model for a one- to two-sentence sign instruction as JSON, parses it, and uses it as the description for the schematic illustration. `add_nsl_svg_illustrations()` repeats this for each term and stores `description` and `sign_illustration` on each item. Terms that had no verified glossary entry are marked `suggested`.
- **When it runs:** always for sign-language (`nsl`) requests. For lesson slides it runs only when `DRAFTBENCH_AI_SVG=1` (off by default).

---

## 4. End-to-End Data Flow

```text
Teacher prompt
   |
   v
A1  classify_intent_and_extract_params()   ----> intent, topic, grade, subject, language
   |                                              (routes quiz / braille / nsl to special_outputs)
   v
A5  query_curriculum_rag()   <---- A6/A7 index built from CDC records (nomic-embed-text, ChromaDB)
   |
   v
A2  plan_slide_content()  --JSON-->  normalize_plan()  --->  A3  evaluate_content_plan()
   ^                                                              |
   |                       score < 8: itemised corrections        |
   +--------------------------------------------------------------+
                                                                  | score >= 8 (or best of 3)
                                                                  v
A4  plan_teacher_support() ---> merge_support()   (teacher support + IEP goal merged into plan)
   |
   v
A10 / A11  generate_educational_svg() ---> CairoSVG PNG   (NSL always; lesson slides if enabled)
   |
   v
Exports: Markdown, PDF, PPTX, quiz (A8), Braille and sign cards (A9, A11, A12)
```

---

## 5. Execution Environment

- **All inference is local.** `qwen2.5:7b-instruct` and `nomic-embed-text` run in a local Ollama instance on the school's own machine. Prompts, observations, retrieved text, and generated materials stay on that machine.
- **Containerised backend.** The FastAPI backend (and the Expo frontend) run as Docker containers defined in `docker-compose.yml`. The backend reaches the local Ollama instance through `OLLAMA_HOST=http://host.docker.internal:11434`.
- **Air-gapped operation.** After the one-time `ollama pull qwen2.5:7b-instruct` and `ollama pull nomic-embed-text`, the system needs no network connection. The vector store, SVG generation, and exports all run locally.
- **Standard hardware.** The models run on a CPU-only laptop (about 16 GB of RAM is recommended for the 7B model; 8 GB is workable with a quantised build). No GPU is required, and no image-diffusion model is used.

---

## 6. Output Validation and Failure Handling

Model output is never used raw. Each invocation has a parsing step and a defined fallback.

| Invocation         | Validation                                                     | Failure behaviour                                                                         |
| ------------------ | -------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| A1 classification  | Regex isolates JSON; `json.loads`                              | Code fallback with default grade and subject and Devanagari-based language detection      |
| A2 writer          | `format="json"`; `normalize_plan()`; `evaluate_content_plan()` | Retry with corrections (max 3); best draft kept; `planner_failed` error if empty          |
| A4 teacher support | JSON parse; `merge_support()` defaults                         | Retry (max 2); defaults for IEP baseline and criteria                                     |
| A5/A6 embeddings   | Exceptions caught                                              | Placeholder context; pipeline continues                                                   |
| A7 extraction      | Pydantic `model_validate_json()`; `deduplicate_records()`      | Page skipped and an empty list returned                                                   |
| A8 quiz            | `_clean_question()`; `is_duplicate()`; question-type quotas    | Retry (max 2); fallback questions fill empty slots; error if fewer than 3 valid questions |
| A9 key content     | Sentence-length and structure filters                          | Retry (max 3); best result returned; error if too short                                   |
| A10/A11 SVG        | Pattern extraction of `<svg>`                                  | Built-in fallback vector; PNG path is empty if rendering fails                            |
| A12 sign drafts    | `_valid_description()`                                         | Falls back to fingerspelling; draft entries are flagged `suggested` for signer review     |

---

## 7. How to Verify This Disclosure

Every model call in the backend goes through the `ollama` client, so the call sites can be listed directly:

```bash
grep -rnE "ollama\.(chat|embed)" backend --include=*.py
```

Each match corresponds to a row in [Section 3.1](#31-every-ai-invocation). To confirm local-only operation, start the stack, disable the machine's internet access, and generate a lesson, a quiz, a Braille sheet, and a sign-language sheet; all of them complete without a network connection.
