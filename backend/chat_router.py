import os
from typing import List, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import models, database, auth_utils
from materials_router import UPLOAD_DIR

router = APIRouter()

# All settings are optional; the defaults work with a local Ollama install.
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct")
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "8192"))
OLLAMA_MAX_CONTEXT_CHARS = int(os.getenv("OLLAMA_MAX_CONTEXT_CHARS", "10000"))  # Devanagari uses many tokens
OLLAMA_NUM_PREDICT = int(os.getenv("OLLAMA_NUM_PREDICT", "600"))

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".heic"}

SYSTEM = (
    "You are the Draft Bench assistant, helping a teacher in Nepal with the materials they uploaded. "
    "Answer using only the attached materials. If the answer isn't in them, say so instead of guessing. "
    "Mention which material (and the page or slide, when you can tell) your answer comes from. "
    "Reply in the language the teacher writes in. When writing Nepali, use clear, natural Devanagari Nepali, "
    "do not use Hindi vocabulary or Bengali characters. "
    "Write in plain text only: no markdown, no asterisks, no pound signs. "
    "For lists, use numbered lines or lines starting with a hyphen. "
    "Keep answers clear and concise unless the teacher asks for more detail."
)


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    material_ids: List[int] = Field(min_length=1, max_length=10)
    message: str = Field(min_length=1, max_length=4000)
    history: List[Turn] = []


class ChatResponse(BaseModel):
    reply: str


def extract_text(path: str, ext: str) -> str:
    if ext in (".txt", ".md", ".csv"):
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    if ext == ".pdf":
        from pypdf import PdfReader
        return "\n".join(
            f"[Page {i}]\n{page.extract_text() or ''}" for i, page in enumerate(PdfReader(path).pages, 1)
        )
    if ext == ".docx":
        import docx
        d = docx.Document(path)
        parts = [p.text for p in d.paragraphs]
        for t in d.tables:
            for row in t.rows:
                parts.append(" | ".join(c.text for c in row.cells))
        return "\n".join(parts)
    if ext == ".pptx":
        from pptx import Presentation
        parts = []
        for i, slide in enumerate(Presentation(path).slides, 1):
            parts.append(f"[Slide {i}]")
            for shape in slide.shapes:
                if shape.has_text_frame:
                    parts.append(shape.text_frame.text)
        return "\n".join(parts)
    if ext == ".xlsx":
        from openpyxl import load_workbook
        wb = load_workbook(path, read_only=True, data_only=True)
        parts = []
        for ws in wb.worksheets:
            parts.append(f"[Sheet {ws.title}]")
            for row in ws.iter_rows(values_only=True):
                parts.append(" | ".join("" if c is None else str(c) for c in row))
        return "\n".join(parts)
    raise ValueError(ext)


def read_material(m: models.users) -> str:
    path = os.path.join(UPLOAD_DIR, m.stored_name)
    ext = os.path.splitext(m.stored_name)[1].lower()
    if not os.path.exists(path):
        raise HTTPException(status_code=410, detail=f'"{m.filename}" is missing on the server. Re-upload it.')
    if ext in IMAGE_EXT:
        raise HTTPException(status_code=400, detail=f'Chat can\'t read images yet ("{m.filename}"). Upload a PDF or DOCX instead.')
    try:
        return extract_text(path, ext).strip()
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f'Chat can\'t read "{m.filename}" yet. Save it as PDF or DOCX and upload that instead.',
        )


@router.post("", response_model=ChatResponse)
def chat(
    req: ChatRequest,
    db: Session = Depends(database.get_db),
    current_user: models.users = Depends(auth_utils.get_current_user),
):
    import ollama

    ids = set(req.material_ids)
    materials = (
        db.query(models.Material)
        .filter(models.Material.id.in_(ids), models.Material.owner_id == current_user.id)
        .all()
    )
    if len(materials) != len(ids):
        raise HTTPException(status_code=404, detail="One or more materials were not found.")

    parts, used, truncated = [], 0, False
    for m in materials:
        text = read_material(m)
        room = OLLAMA_MAX_CONTEXT_CHARS - used
        if room <= 0:
            truncated = True
            break
        if len(text) > room:
            text, truncated = text[:room], True
        used += len(text)
        parts.append(f'Material "{m.filename}":\n{text}')
    context = "\n\n".join(parts)
    if not context.strip():
        raise HTTPException(status_code=400, detail="Couldn't find any readable text in these files. Scanned PDFs aren't supported yet.")
    if truncated:
        context += "\n\n[The materials were cut short because they are long. Tell the teacher if the answer may be in the missing part.]"

    msgs = [{"role": t.role, "content": t.content} for t in req.history[-20:]]
    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)
    msgs.append({"role": "user", "content": req.message})
    msgs[0]["content"] = f"{context}\n\n---\nTeacher's question: {msgs[0]['content']}"

    try:
        resp = ollama.Client(host=os.getenv("OLLAMA_HOST")).chat(
            model=OLLAMA_MODEL,
            messages=[{"role": "system", "content": SYSTEM}] + msgs,
            options={
                "temperature": 0.2,
                "top_p": 0.85,
                "repeat_penalty": 1.1,
                "num_ctx": OLLAMA_NUM_CTX,
                "num_predict": OLLAMA_NUM_PREDICT,
            },
            stream=False,
        )
    except ollama.ResponseError as e:
        raise HTTPException(status_code=502, detail=f"Local model error: {e.error}")
    except (ConnectionError, OSError):
        raise HTTPException(status_code=502, detail="Couldn't reach Ollama. Is it running on the server?")
    return {"reply": resp["message"]["content"]}