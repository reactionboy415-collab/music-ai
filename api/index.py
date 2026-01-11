import time, uuid, threading, requests
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, HTMLResponse

app = FastAPI()

# ================= CONFIG =================
API_KEY = "SONGIFY001"
EXPIRY_DATE = datetime(2026, 2, 1)

MAX_CONCURRENT = 2
MAX_DAILY = 30
DAY_SECONDS = 86400

# ================= MEMORY STORES =================
concurrent_requests = {}
daily_requests = {}
jobs = {}

STATS = {
    "total_requests": 0,
    "total_music_generated": 0,
    "started_at": time.time()
}

# ================= HELPERS =================
def get_ip(req: Request):
    xff = req.headers.get("x-forwarded-for")
    return xff.split(",")[0].strip() if xff else "0.0.0.0"

def cleanup_daily(ip):
    d = daily_requests.get(ip)
    if d and time.time() - d["start"] > DAY_SECONDS:
        daily_requests[ip] = {"count": 0, "start": time.time()}

def days_left():
    return max((EXPIRY_DATE - datetime.utcnow()).days, 0)

# ================= WORKER =================
def generate_worker(job_id, ip, prompt):
    try:
        # ---- Lyrics ----
        lr = requests.post(
            "https://google-web-utgk.onrender.com/get-lyrics",
            headers={"X-Forwarded-For": ip},
            data={"prompt": prompt},
            timeout=60
        )
        lyrics = lr.json().get("lyrics")
        if not lyrics:
            raise Exception()

        # ---- Music ----
        mr = requests.post(
            "https://google-web-utgk.onrender.com/direct-music",
            headers={"X-Forwarded-For": ip, "Content-Type": "application/json"},
            json={"prompt": prompt, "lyrics": lyrics},
            timeout=180
        )
        m = mr.json()
        if not m.get("music_url"):
            raise Exception()

        jobs[job_id] = {
            "status": "success",
            "lyrics": lyrics,
            "music_url": m["music_url"],
            "thumbnail_url": m.get("thumbnail_url")
        }
        STATS["total_music_generated"] += 1

    except:
        jobs[job_id] = {"status": "failed"}

    finally:
        concurrent_requests[ip] = max(concurrent_requests.get(ip, 1) - 1, 0)

# ================= MAIN API =================
@app.post("/api")
async def generate(req: Request):
    STATS["total_requests"] += 1

    # ---- KEY ----
    key = req.headers.get("x-api-key")
    if not key:
        return JSONResponse({"success": False, "error": "API key required"}, 401)
    if key != API_KEY:
        return JSONResponse({"success": False, "error": "Invalid API key"}, 403)
    if datetime.utcnow() >= EXPIRY_DATE:
        return JSONResponse({"success": False, "error": "Key expired, use new key"}, 403)

    body = await req.json()
    prompt = body.get("prompt")
    if not prompt:
        return JSONResponse({"success": False, "error": "Prompt required"}, 400)

    ip = get_ip(req)

    # ---- RATE LIMIT ----
    if concurrent_requests.get(ip, 0) >= MAX_CONCURRENT:
        return JSONResponse({"success": False, "error": "Too many concurrent requests"}, 429)

    cleanup_daily(ip)
    d = daily_requests.get(ip)
    if not d:
        daily_requests[ip] = {"count": 0, "start": time.time()}
        d = daily_requests[ip]

    if d["count"] >= MAX_DAILY:
        return JSONResponse({"success": False, "error": "Daily limit reached (30/24h)"}, 429)

    concurrent_requests[ip] = concurrent_requests.get(ip, 0) + 1
    d["count"] += 1

    # ---- JOB ----
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "processing"}

    threading.Thread(
        target=generate_worker,
        args=(job_id, ip, prompt),
        daemon=True
    ).start()

    return {"success": True, "job_id": job_id, "status": "processing"}

# ================= STATUS =================
@app.get("/status/{job_id}")
async def status(job_id: str):
    return jobs.get(job_id, {"status": "not_found"})

# ================= ADMIN PANEL =================
@app.get("/xyz001", response_class=HTMLResponse)
async def admin():
    uptime = int(time.time() - STATS["started_at"])
    rows = "".join(
        f"<tr><td>{ip}</td><td>{d['count']}</td></tr>"
        for ip, d in daily_requests.items()
    ) or "<tr><td colspan=2>No data</td></tr>"

    return f"""
    <html>
    <head>
    <title>SONGIFY ADMIN</title>
    <style>
    body{{background:#0b0b0f;color:white;font-family:Arial;padding:40px}}
    table{{width:100%;border-collapse:collapse}}
    td,th{{border:1px solid #222;padding:10px}}
    th{{color:#60a5fa}}
    </style>
    </head>
    <body>
    <h1>SONGIFY ADMIN PANEL</h1>
    <p><b>Total Requests:</b> {STATS['total_requests']}</p>
    <p><b>Total Music Generated:</b> {STATS['total_music_generated']}</p>
    <p><b>Active IPs:</b> {len(daily_requests)}</p>
    <p><b>Key Expiry:</b> {EXPIRY_DATE.date()}</p>
    <p><b>Days Left:</b> {days_left()}</p>
    <p><b>Server Uptime:</b> {uptime}s</p>

    <h3>Per-IP Usage</h3>
    <table>
    <tr><th>IP</th><th>Requests (24h)</th></tr>
    {rows}
    </table>
    </body></html>
    """
