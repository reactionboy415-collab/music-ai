import time
import requests
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

# Admin stats
STATS = {
    "total_requests": 0,
    "total_music_generated": 0,
    "started_at": time.time()
}

# ================= HELPERS =================
def get_client_ip(request: Request):
    xff = request.headers.get("x-forwarded-for")
    return xff.split(",")[0].strip() if xff else "0.0.0.0"


def cleanup_daily(ip):
    record = daily_requests.get(ip)
    if not record:
        return
    if time.time() - record["start"] > DAY_SECONDS:
        daily_requests[ip] = {"count": 0, "start": time.time()}


def days_to_expiry():
    delta = EXPIRY_DATE - datetime.utcnow()
    return max(delta.days, 0)

# ================= MAIN API =================
@app.post("/api")
async def generate(request: Request):
    STATS["total_requests"] += 1

    # ---- API KEY CHECK ----
    key = request.headers.get("x-api-key")
    if not key:
        return JSONResponse({"success": False, "error": "API key required"}, 401)

    if key != API_KEY:
        return JSONResponse({"success": False, "error": "Invalid API key"}, 403)

    if datetime.utcnow() >= EXPIRY_DATE:
        return JSONResponse(
            {"success": False, "error": "Key expired, use new key"}, 403
        )

    body = await request.json()
    prompt = body.get("prompt")
    if not prompt:
        return JSONResponse({"success": False, "error": "Prompt required"}, 400)

    ip = get_client_ip(request)

    # ---- CONCURRENT LIMIT ----
    if concurrent_requests.get(ip, 0) >= MAX_CONCURRENT:
        return JSONResponse(
            {"success": False, "error": "Too many concurrent requests"}, 429
        )

    concurrent_requests[ip] = concurrent_requests.get(ip, 0) + 1

    try:
        # ---- DAILY LIMIT ----
        cleanup_daily(ip)
        daily = daily_requests.get(ip)
        if not daily:
            daily_requests[ip] = {"count": 0, "start": time.time()}
            daily = daily_requests[ip]

        if daily["count"] >= MAX_DAILY:
            return JSONResponse(
                {"success": False, "error": "Daily limit reached (30/24h)"}, 429
            )

        daily["count"] += 1

        # ---- STEP 1: LYRICS ----
        lyrics_res = requests.post(
            "https://google-web-utgk.onrender.com/get-lyrics",
            headers={
                "X-Forwarded-For": ip,
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"prompt": prompt},
            timeout=60,
        )

        lyrics_data = lyrics_res.json()
        lyrics = lyrics_data.get("lyrics")
        if not lyrics:
            raise Exception("Lyrics failed")

        # ---- STEP 2: MUSIC ----
        music_res = requests.post(
            "https://google-web-utgk.onrender.com/direct-music",
            headers={
                "X-Forwarded-For": ip,
                "Content-Type": "application/json",
            },
            json={"prompt": prompt, "lyrics": lyrics},
            timeout=120,
        )

        music_data = music_res.json()
        if not music_data.get("music_url"):
            raise Exception("Music failed")

        STATS["total_music_generated"] += 1

        return {
            "success": True,
            "lyrics": lyrics,
            "music_url": music_data["music_url"],
            "thumbnail_url": music_data.get("thumbnail_url"),
        }

    except Exception:
        return JSONResponse(
            {"success": False, "error": "Generation failed"}, 500
        )

    finally:
        concurrent_requests[ip] = max(concurrent_requests.get(ip, 1) - 1, 0)


# ================= ADMIN PANEL =================
@app.get("/xyz001", response_class=HTMLResponse)
async def admin_panel():
    uptime = int(time.time() - STATS["started_at"])

    rows = ""
    for ip, data in daily_requests.items():
        rows += f"""
        <tr>
            <td>{ip}</td>
            <td>{data['count']}</td>
        </tr>
        """

    return f"""
    <html>
    <head>
        <title>SONGIFY ADMIN</title>
        <style>
            body {{
                background:#0b0b0f;
                color:white;
                font-family:Arial;
                padding:40px;
            }}
            h1 {{ color:#3b82f6; }}
            table {{
                width:100%;
                border-collapse:collapse;
                margin-top:30px;
            }}
            th, td {{
                border:1px solid #222;
                padding:12px;
                text-align:left;
            }}
            th {{
                background:#111;
                color:#60a5fa;
            }}
        </style>
    </head>
    <body>
        <h1>SONGIFY ADMIN PANEL</h1>

        <p><b>API Key:</b> {API_KEY}</p>
        <p><b>Key Expiry Date:</b> {EXPIRY_DATE.date()}</p>
        <p><b>Days Remaining:</b> {days_to_expiry()}</p>

        <hr>

        <p><b>Total Requests:</b> {STATS['total_requests']}</p>
        <p><b>Total Music Generated:</b> {STATS['total_music_generated']}</p>
        <p><b>Active IPs:</b> {len(daily_requests)}</p>
        <p><b>Server Uptime:</b> {uptime} seconds</p>

        <h2>Per-IP Daily Usage</h2>
        <table>
            <tr>
                <th>IP Address</th>
                <th>Requests (24h)</th>
            </tr>
            {rows if rows else "<tr><td colspan='2'>No data</td></tr>"}
        </table>
    </body>
    </html>
    """
