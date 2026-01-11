import os
import uuid
from fastapi import FastAPI, HTTPException, Header, BackgroundTasks
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from datetime import datetime
import requests
from upstash_redis import Redis

app = FastAPI()

# --- CONFIGURATION ---
VALID_KEY = "SONGIFY001"
EXPIRY_DATE = datetime(2026, 2, 1)

# Connect to Vercel KV (Zero Setup: Just add KV from Vercel Dashboard)
# It will automatically pick credentials from environment variables
redis = Redis.from_env()

class SongRequest(BaseModel):
    prompt: str

# --- BACKGROUND WORKER ---
def process_music_gen(job_id: str, prompt: str, lyrics: str):
    music_api = "https://ab-sunoai.vercel.app/api/song"
    try:
        response = requests.post(music_api, json={"prompt": prompt, "lyrics": lyrics}, timeout=120)
        if response.status_code == 200:
            data = response.json()
            # Update status in Redis
            redis.hset(f"job:{job_id}", mapping={
                "status": "completed",
                "music_url": data.get("music_url"),
                "thumbnail": data.get("thumbnail_url", "")
            })
        else:
            redis.hset(f"job:{job_id}", mapping={"status": "failed"})
    except:
        redis.hset(f"job:{job_id}", mapping={"status": "failed"})

# --- 1. GENERATE ENDPOINT ---
@app.post("/api/generate")
async def generate_song(request: SongRequest, background_tasks: BackgroundTasks, x_api_key: str = Header(None)):
    if x_api_key != VALID_KEY:
        raise HTTPException(status_code=401, detail="Invalid Key")
    if datetime.now() > EXPIRY_DATE:
        raise HTTPException(status_code=403, detail="Key expired use new")

    # Step 1: Lyrics Gen
    lyrics_res = requests.post("https://ab-sunoai.vercel.app/api/lyrics", json={"prompt": request.prompt})
    if lyrics_res.status_code != 200:
        return {"success": False, "message": "Lyrics failed"}
    
    lyrics = lyrics_res.json().get("lyrics")
    job_id = str(uuid.uuid4())[:8]

    # Save Job to Redis (Expires in 24 hours automatically to save space)
    redis.hset(f"job:{job_id}", mapping={
        "job_id": job_id,
        "prompt": request.prompt,
        "lyrics": lyrics,
        "status": "processing",
        "created_at": datetime.now().isoformat()
    })
    redis.expire(f"job:{job_id}", 86400) # 24 hours

    # Update Global Stats
    redis.incr("stats:total_req")

    # Start Music Task
    background_tasks.add_task(process_music_gen, job_id, request.prompt, lyrics)

    return {
        "success": True,
        "job_id": job_id,
        "lyrics": lyrics,
        "status_url": f"/api/status/{job_id}"
    }

# --- 2. STATUS CHECK ---
@app.get("/api/status/{job_id}")
async def get_status(job_id: str):
    job = redis.hgetall(f"job:{job_id}")
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or expired")
    return job

# --- 3. ADMIN PANEL ---
@app.get("/xyz001", response_class=HTMLResponse)
async def admin_panel():
    total = redis.get("stats:total_req") or 0
    days_left = (EXPIRY_DATE - datetime.now()).days
    status_msg = "ACTIVE" if days_left > 0 else "EXPIRED"
    
    return f"""
    <html>
        <head><title>Admin</title><meta name="viewport" content="width=device-width, initial-scale=1"></head>
        <body style="font-family:sans-serif; background:#0f172a; color:white; text-align:center; padding:50px;">
            <div style="background:#1e293b; padding:30px; border-radius:15px; display:inline-block; border:1px solid #334155;">
                <h2>📊 Songify Stats</h2>
                <h1 style="font-size:48px; color:#38bdf8; margin:10px 0;">{total}</h1>
                <p>Total Songs Generated</p>
                <hr style="border:0; border-top:1px solid #334155; margin:20px 0;">
                <p>Key Status: <b style="color:{"#4ade80" if days_left > 0 else "#f87171"}">{status_msg}</b></p>
                <p>Days Remaining: <b>{max(0, days_left)}</b></p>
            </div>
        </body>
    </html>
    """
                
