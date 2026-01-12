import os
import uuid
import requests
from fastapi import FastAPI, HTTPException, Header, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from datetime import datetime

app = FastAPI()

# --- CORS FIX: Isse "Failed to fetch" error solve hoga ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

VALID_KEY = "SONGIFY001"
EXPIRY_DATE = datetime(2026, 2, 1)

jobs_db = {}
stats = {"total": 0}

class SongRequest(BaseModel):
    prompt: str

def process_music_gen(job_id: str, prompt: str, lyrics: str):
    music_api = "https://ab-sunoai.vercel.app/api/song"
    try:
        response = requests.post(music_api, json={"prompt": prompt, "lyrics": lyrics}, timeout=120)
        if response.status_code == 200:
            data = response.json()
            if job_id in jobs_db:
                jobs_db[job_id].update({
                    "status": "completed",
                    "music_url": data.get("music_url"),
                    "thumbnail": data.get("thumbnail_url", "")
                })
        else:
            if job_id in jobs_db: jobs_db[job_id]["status"] = "failed"
    except:
        if job_id in jobs_db: jobs_db[job_id]["status"] = "failed"

@app.post("/api/generate")
async def generate_song(request: SongRequest, background_tasks: BackgroundTasks, x_api_key: str = Header(None)):
    if x_api_key != VALID_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    
    if datetime.now() > EXPIRY_DATE:
        raise HTTPException(status_code=403, detail="Key expired")

    try:
        lyrics_res = requests.post("https://ab-sunoai.vercel.app/api/lyrics", json={"prompt": request.prompt}, timeout=15)
        lyrics = lyrics_res.json().get("lyrics", "No lyrics generated")
        
        job_id = str(uuid.uuid4())[:8]
        jobs_db[job_id] = {
            "job_id": job_id,
            "prompt": request.prompt,
            "lyrics": lyrics,
            "status": "processing",
            "created_at": datetime.now().isoformat()
        }
        stats["total"] += 1
        background_tasks.add_task(process_music_gen, job_id, request.prompt, lyrics)

        return {"success": True, "job_id": job_id, "lyrics": lyrics}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/status/{job_id}")
async def get_status(job_id: str):
    return jobs_db.get(job_id, {"error": "Job not found"})

@app.get("/xyz001", response_class=HTMLResponse)
async def admin_panel():
    return f"<h1>Total Songs: {stats['total']}</h1><p>Status: Active until Feb 2026</p>"
