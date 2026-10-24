import os
import re
import threading
import time
import uuid
from datetime import datetime, timedelta
from typing import List, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from jose import JWTError, jwt
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import models, database, auth_utils
from chat_router import read_material
from materials_router import UPLOAD_DIR
from utils.media_extractor import extract_images

router = APIRouter()

JOBS: dict = {}                    # job_id -> state (in memory: cleared when the server restarts)
_run_lock = threading.Lock()       # one generation at a time; a local model can't run several well
MATERIAL_MAX_CHARS = int(os.getenv("GENERATE_MAX_MATERIAL_CHARS", "8000"))
MEDIA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "exports", "media")
MEDIA = {
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".pdf": "application/pdf",
}


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=2000)
    output: Literal["presentation", "document"]
    grade: int = Field(ge=1, le=12)
    subject: str = Field(min_length=2, max_length=40)
    language: Literal["nepali", "english"]
    material_ids: List[int] = Field(default=[], max_length=10)


def load_material(user_id: int, material_ids: List[int], job_id: str):
    """Returns (text, pictures). Slow for big files, so it runs inside the background job."""
    if not material_ids:
        return "", []
    db = database.SessionLocal()
    try:
        mats = (
            db.query(models.Material)
            .filter(models.Material.id.in_(set(material_ids)), models.Material.owner_id == user_id)
            .all()
        )
        parts, images, used = [], [], 0
        out_dir = os.path.join(MEDIA_DIR, job_id)
        for m in mats:
            room = MATERIAL_MAX_CHARS - used
            if room <= 0:
                break
            text = read_material(m)[:room]
            used += len(text)
            parts.append(f'Material "{m.filename}":\n{text}')
            # Only look for pictures in the pages the AI will actually read
            pages = [int(x) for x in re.findall(r"\[Page (\d+)\]", text)]
            ext = os.path.splitext(m.stored_name)[1].lower()
            found = extract_images(os.path.join(UPLOAD_DIR, m.stored_name), ext, out_dir, f"m{m.id}",
                                   max_page=max(pages) if pages else 40)
            for img in found:
                img["material"] = m.id
            images.extend(found)
        return "\n\n".join(parts), images
    finally:
        db.close()


def run_job(job_id: str, user_id: int, req: GenerateRequest):
    job = JOBS[job_id]
    try:
        job["step"] = "Reading your files..."
        material_text, material_images = load_material(user_id, req.material_ids, job_id)
    except HTTPException as e:
        job.update(status="failed", error=str(e.detail))
        return
    except Exception as e:
        job.update(status="failed", error=str(e) or e.__class__.__name__)
        return

    with _run_lock:
        job["status"] = "running"
        try:
            # Imported here so the server still starts (and chat still works) if these dependencies are missing
            from agents.unified_pipeline import run_unified_pipeline

            result = run_unified_pipeline(
                user_prompt=req.prompt,
                session_id=f"user-{user_id}",
                forced_intent=req.output,
                forced_grade=req.grade,
                forced_subject=req.subject,
                forced_language=req.language,
                material_text=material_text,
                material_images=material_images,
                file_tag=f"_{job_id[:8]}",
                on_progress=lambda msg: job.update(step=msg),
            )
            if result.get("error"):
                raise RuntimeError("The AI couldn't produce a valid lesson plan. Try again, or simplify the request.")
            path = next(iter((result.get("files") or {}).values()), None)
            if not path or not os.path.exists(path):
                raise RuntimeError("The file wasn't created.")
            job.update(status="done", step="Done", file=path)
        except Exception as e:
            job.update(status="failed", error=str(e) or e.__class__.__name__)


def owned_job(job_id: str, user_id: int) -> dict:
    job = JOBS.get(job_id)
    if not job or job["owner_id"] != user_id:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


@router.post("")
def start_generation(
    req: GenerateRequest,
    background: BackgroundTasks,
    db: Session = Depends(database.get_db),
    current_user=Depends(auth_utils.get_current_user),
):
    if req.material_ids:  # quick ownership check only; the files are read inside the job
        ids = set(req.material_ids)
        found = (
            db.query(models.Material)
            .filter(models.Material.id.in_(ids), models.Material.owner_id == current_user.id)
            .count()
        )
        if found != len(ids):
            raise HTTPException(status_code=404, detail="One or more materials were not found.")

    job_id = uuid.uuid4().hex
    JOBS[job_id] = {
        "owner_id": current_user.id, "status": "queued", "step": "Waiting to start...",
        "file": None, "error": None, "created": time.time(),
    }
    background.add_task(run_job, job_id, current_user.id, req)
    return {"job_id": job_id}


@router.get("/{job_id}")
def job_status(job_id: str, current_user=Depends(auth_utils.get_current_user)):
    job = owned_job(job_id, current_user.id)
    return {
        "status": job["status"], "step": job["step"], "error": job["error"],
        "filename": os.path.basename(job["file"]) if job["file"] else None,
    }


@router.get("/{job_id}/link")
def download_link(job_id: str, current_user=Depends(auth_utils.get_current_user)):
    """Short-lived signed link, so the phone can open the file in a browser without sending headers."""
    job = owned_job(job_id, current_user.id)
    if job["status"] != "done":
        raise HTTPException(status_code=409, detail="The file isn't ready yet.")
    token = jwt.encode(
        {"jid": job_id, "uid": current_user.id, "exp": datetime.utcnow() + timedelta(minutes=5)},
        auth_utils.SECRET_KEY, algorithm=auth_utils.ALGORITHM,
    )
    return {"path": f"/generate/{job_id}/download?t={token}"}


@router.get("/{job_id}/download")
def download(job_id: str, t: str = Query(...)):
    try:
        data = jwt.decode(t, auth_utils.SECRET_KEY, algorithms=[auth_utils.ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="This link expired. Go back and tap Open again.")
    job = JOBS.get(job_id)
    if data.get("jid") != job_id or not job or job["owner_id"] != data.get("uid") or not job["file"]:
        raise HTTPException(status_code=404, detail="File not found.")
    ext = os.path.splitext(job["file"])[1].lower()
    return FileResponse(job["file"], media_type=MEDIA.get(ext, "application/octet-stream"),
                        filename=os.path.basename(job["file"]))
