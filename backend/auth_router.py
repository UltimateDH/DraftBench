import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import EmailStr

import models, schemas, database, auth_utils

router = APIRouter()

@router.post("/signup", response_model=schemas.UserResponse, status_code=status.HTTP_201_CREATED)
async def signup(
    username: str = Form(...),
    email: EmailStr = Form(...),
    password: str = Form(...),
    profile_pic: UploadFile = File(None),
    db: Session = Depends(database.get_db)
):
    # Check if user or email already exists
    existing_user = db.query(models.users).filter(
        (models.users.username == username) | (models.users.email == email)
    ).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Username or Email already registered")

    profile_pic_path = None
    if profile_pic:
        # Generate unique filename to avoid overwrites
        file_extension = os.path.splitext(profile_pic.filename)[1]
        unique_filename = f"{uuid.uuid4().hex}{file_extension}"
        
        # Save file into local storage directory
        base_dir = os.path.dirname(os.path.abspath(__file__))
        save_path = os.path.join(base_dir, "storage", "profile_pics", unique_filename)
        
        contents = await profile_pic.read()
        with open(save_path, "wb") as f:
            f.write(contents)
        
        # Static file route path corresponding to app.mount configuration
        profile_pic_path = f"/static/profile_pics/{unique_filename}"

    hashed_pw = auth_utils.hash_password(password)
    new_user = models.users(
        username=username,
        email=email,
        hashed_password=hashed_pw,
        profile_pic=profile_pic_path
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    return new_user

@router.post("/login", response_model=schemas.Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(database.get_db)
):
    user = db.query(models.users).filter(models.users.username == form_data.username).first()
    if not user or not auth_utils.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = auth_utils.create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=schemas.UserResponse)
def get_user_profile(current_user: models.users = Depends(auth_utils.get_current_user)):
    return current_user