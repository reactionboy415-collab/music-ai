from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import requests

app = FastAPI()

LYRICS_API = "https://ab-sunoai.vercel.app/api/lyrics"
MUSIC_API  = "https://ab-sunoai.vercel.app/api/song"

HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0"
}

# =====================================
# 🚀 MAIN TEXT → MUSIC API
# =====================================
@app.post("/generate")
async def generate_music(request: Request):
    data = await request.json()
    prompt = data.get("prompt")

    if not prompt:
        return JSONResponse(
            {"success": False, "error": "prompt is required"},
            status_code=400
        )

    # -------------------------------
    # STEP 1: Lyrics Generation
    # -------------------------------
    lyrics_res = requests.post(
        LYRICS_API,
        headers=HEADERS,
        json={"prompt": prompt},
        timeout=30
    )

    lyrics_data = lyrics_res.json()

    if not lyrics_data.get("success"):
        return JSONResponse(
            {"success": False, "error": "Lyrics generation failed"},
            status_code=500
        )

    lyrics = lyrics_data.get("lyrics")

    # -------------------------------
    # STEP 2: Music Generation
    # -------------------------------
    music_res = requests.post(
        MUSIC_API,
        headers=HEADERS,
        json={
            "prompt": prompt,
            "lyrics": lyrics
        },
        timeout=60
    )

    music_data = music_res.json()

    if not music_data.get("success"):
        return JSONResponse(
            {"success": False, "error": "Music generation failed"},
            status_code=500
        )

    # -------------------------------
    # FINAL RESPONSE (CLEAN)
    # -------------------------------
    return {
        "success": True,
        "prompt": prompt,
        "lyrics": lyrics,
        "music_url": music_data.get("music_url"),
        "thumbnail_url": music_data.get("thumbnail_url")
    }


# =====================================
# 🩺 HEALTH CHECK
# =====================================
@app.get("/")
def health():
    return {"status": "Text → Lyrics → Music API LIVE 🚀"}
