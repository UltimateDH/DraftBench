import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from database import engine, Base
from auth_router import router as auth_router

Base.metadata.create_all(bind=engine)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/auth", tags=["auth"])

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

STORAGE_DIR = os.path.join(BASE_DIR, "storage", "images")
os.makedirs(STORAGE_DIR, exist_ok=True)
app.mount("/static/images", StaticFiles(directory=STORAGE_DIR), name="images")

PROFILE_PIC_DIR = os.path.join(BASE_DIR, "storage", "profile_pics")
os.makedirs(PROFILE_PIC_DIR, exist_ok=True)
app.mount("/static/profile_pics", StaticFiles(directory=PROFILE_PIC_DIR), name="profile_pics")