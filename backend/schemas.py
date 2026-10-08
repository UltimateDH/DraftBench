from datetime import datetime
from pydantic import BaseModel, EmailStr
from typing import Optional

class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: int
    username: str
    email: EmailStr
    profile_pic: Optional[str] = None

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class MaterialResponse(BaseModel):
    id: int
    filename: str
    content_type: Optional[str] = None
    size_bytes: int
    created_at: datetime

    class Config:
        from_attributes = True
