from dotenv import load_dotenv
load_dotenv()

import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from database import engine, Base
from auth_router import router as auth_router
from materials_router import router as materials_router
from chat_router import router as chat_router

import ollama

from generate_router import router as generate_router


Base.metadata.create_all(bind=engine)

app = FastAPI(title="DraftBench API")
REQUIRED_MODELS = [
    "qwen2.5:7b-instruct",
    "nomic-embed-text"
]

def ensure_ollama_models_exist():
    """Checks if required models are present on Ollama, pulls them if missing."""
    ollama_host = os.getenv("OLLAMA_HOST", "http://host.docker.internal:11434")
    print(f"[Ollama Check] Connecting to Ollama at {ollama_host}...")
    
    try:
        # Create an explicit client pointing to the docker bridge host
        client = ollama.Client(host=ollama_host)
        
        # Fetch list of locally available models
        response = client.list()
        existing_models = [m.get("model", "") for m in response.get("models", [])]
        
        for model in REQUIRED_MODELS:
            # Check if model exists (accounting for tags like :latest)
            match_found = any(model in em for em in existing_models)
            
            if not match_found:
                print(f"[Ollama Check] Model '{model}' not found. Initiating auto-pull...")
                client.pull(model)
                print(f"[Ollama Check] Successfully pulled '{model}'!")
            else:
                print(f"[Ollama Check] Model '{model}' is ready.")
                
    except Exception as e:
        print(f"[Ollama Warning] Could not verify/pull models from Ollama: {e}")
        print("[Ollama Warning] Ensure your host machine's Ollama app is running!")

@app.on_event("startup")
def startup_event():
    """Runs database unzipping and Ollama model checks when the server starts."""
    ensure_ollama_models_exist()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,  # "*" origins can't be combined with credentials; we use Bearer tokens anyway
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(materials_router, prefix="/materials", tags=["materials"])
app.include_router(chat_router, prefix="/chat", tags=["chat"])
app.include_router(generate_router, prefix="/generate", tags=["generate"])

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

STORAGE_DIR = os.path.join(BASE_DIR, "storage", "images")
os.makedirs(STORAGE_DIR, exist_ok=True)
app.mount("/static/images", StaticFiles(directory=STORAGE_DIR), name="images")

PROFILE_PIC_DIR = os.path.join(BASE_DIR, "storage", "profile_pics")
os.makedirs(PROFILE_PIC_DIR, exist_ok=True)
app.mount("/static/profile_pics", StaticFiles(directory=PROFILE_PIC_DIR), name="profile_pics")
# Note: materials are NOT mounted as static files, so only the owner can reach them via the API.
