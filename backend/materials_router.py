import os
import uuid
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

import models, schemas, database, auth_utils

router = APIRouter()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "storage", "materials")
os.makedirs(UPLOAD_DIR, exist_ok=True)

MAX_BYTES = 25 * 1024 * 1024  # 25 MB per file
ALLOWED_EXT = {
    ".pdf", ".doc", ".docx", ".odt", ".rtf", ".txt", ".md",
    ".ppt", ".pptx", ".xls", ".xlsx", ".csv",
    ".png", ".jpg", ".jpeg", ".webp", ".heic",
}


@router.post("/upload", response_model=schemas.MaterialResponse, status_code=status.HTTP_201_CREATED)
async def upload_material(
    file: UploadFile = File(...),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    original = os.path.basename(file.filename or "untitled")
    ext = os.path.splitext(original)[1].lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=400, detail=f"{ext or 'This'} files aren't supported yet.")

    contents = await file.read()
    if len(contents) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="File is larger than 25 MB.")

    stored_name = f"{uuid.uuid4().hex}{ext}"
    with open(os.path.join(UPLOAD_DIR, stored_name), "wb") as f:
        f.write(contents)

    material = models.Material(
        owner_id=current_user.id,
        filename=original,
        stored_name=stored_name,
        content_type=file.content_type,
        size_bytes=len(contents),
    )
    db.add(material)
    db.commit()
    db.refresh(material)
    return material


@router.get("", response_model=List[schemas.MaterialResponse])
def list_materials(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    return (
        db.query(models.Material)
        .filter(models.Material.owner_id == current_user.id)
        .order_by(models.Material.created_at.desc())
        .all()
    )


@router.delete("/{material_id}")
def delete_material(
    material_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    material = (
        db.query(models.Material)
        .filter(models.Material.id == material_id, models.Material.owner_id == current_user.id)
        .first()
    )
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")

    path = os.path.join(UPLOAD_DIR, material.stored_name)
    if os.path.exists(path):
        os.remove(path)
    db.delete(material)
    db.commit()
    return {"ok": True}
