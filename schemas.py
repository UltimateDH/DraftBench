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
    profile_pic:Optional[str]=None

    class Config:
        from_attributes=True

class Token(BaseModel):
    access_token: str
    token_type: str
