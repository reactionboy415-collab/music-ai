import os
import uuid
from fastapi import FastAPI, HTTPException, Header, BackgroundTasks
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from datetime import datetime
import requests

app = FastAPI()

# --- CONFIGURATION ---
VALID_KEY = "SONGIFY001"
EXPIRY_DATE = datetime(2026, 2, 1)

# In-Memory Storage (Note: Reset after 15-30 mins of inactivity)
jobs_db = {}
stats = {"total": 0}

class SongRequest(BaseModel):
    prompt: str

# --- BACKGROUND WORKER ---
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

# --- 1. GENERATE ENDPOINT ---
@app.post("/api/generate")
async def generate_song(request: SongRequest, background_tasks: BackgroundTasks, x_api_key: str = Header(None)):
    if x_api_key != VALID_KEY:
        raise HTTPException(status_code=401, detail="Invalid Key")
    if datetime.now() > EXPIRY_DATE:
        raise HTTPException(status_code=403, detail="Key expired use new")

    # Step 1: Lyrics Gen
    try:
        lyrics_res = requests.post("https://ab-sunoai.vercel.app/api/lyrics", json={"prompt": request.prompt}, timeout=15)
        if lyrics_res.status_code != 200:
            return {"success": False, "message": "Lyrics service error"}
        
        lyrics = lyrics_res.json().get("lyrics")
        job_id = str(uuid.uuid4())[:8]

        # Save to Local Memory
        jobs_db[job_id] = {
            "job_id": job_id,
            "prompt": request.prompt,
            "lyrics": lyrics,
            "status": "processing",
            "created_at": datetime.now().isoformat()
        }
        stats["total"] += 1

        # Start Background Task
        background_tasks.add_task(process_music_gen, job_id, request.prompt, lyrics)

        return {
            "success": True,
            "job_id": job_id,
            "lyrics": lyrics,
            "status_url": f"/api/status/{job_id}"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

# --- 2. STATUS CHECK ---
@app.get("/api/status/{job_id}")
async def get_status(job_id: str):
    job = jobs_db.get(job_id)
    if not job:
        return {"error": "Job not found (might have expired or server reset)"}
    return job

# --- 3. ADMIN PANEL ---
@app.get("/xyz001", response_class=HTMLResponse)
async def admin_panel():
    days_left = (EXPIRY_DATE - datetime.now()).days
    status_msg = "ACTIVE" if days_left > 0 else "EXPIRED"
    
    # List last 5 jobs from memory
    recent_jobs = list(jobs_db.values())[-5:]
    jobs_html = "".join([f"<li>{j['job_id']} - {j['status']}</li>" for j in recent_jobs])

    return f"""
    <html>
        <body style="font-family:sans-serif; background:#0f172a; color:white; text-align:center; padding:50px;">
            <div style="background:#1e293b; padding:30px; border-radius:15px; display:inline-block; border:1px solid #334155;">
                <h2>📊 Songify Admin (Local Mode)</h2>
                <h1 style="font-size:48px; color:#38bdf8;">{stats['total']}</h1>
                <p>Songs in this Session</p>
                <hr style="border:0; border-top:1px solid #334155;">
                <p>Status: <b style="color:{"#4ade80" if days_left > 0 else "#f87171"}">{status_msg}</b></p>
                <p>Days Left: {max(0, days_left)}</p>
                <div style="text-align:left; font-size:12px;">
                    <h4>Recent Jobs:</h4><ul>{jobs_html}</ul>
                </div>
            </div>
        </body>
    </html>
    """
