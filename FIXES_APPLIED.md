# Fixes Applied to main.py

## Issues Found and Fixed

### 1. ✅ Database Initialization Not Running
**Problem:** `_startup()` function was defined but never called  
**Line:** 670  
**Fix:** Added `@app.on_event("startup")` decorator to `startup_event()` function  
```python
@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    await asyncio.to_thread(init_db)
    log.info("DB ready")
```

### 2. ✅ Missing FastAPI Launch Code
**Problem:** No code to actually start the uvicorn server  
**Fix:** Added `if __name__ == "__main__"` block at the end of file  
```python
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
```

### 3. ✅ Missing .env File Support
**Problem:** No way to load environment variables from .env file for local development  
**Fix:** Added `load_dotenv()` import and call  
```python
from dotenv import load_dotenv
load_dotenv()
```

### 4. ✅ No Validation for PIAPI_API_KEY
**Problem:** If PIAPI_API_KEY not set, music generation would fail with unclear error  
**Fix:** Added warning in startup  
```python
if not PIAPI_API_KEY:
    log.warning("⚠️ PIAPI_API_KEY not set - music generation will not work")
```

### 5. ✅ Missing Dependencies
**Problem:** requirements.txt missing aiohttp and python-dotenv  
**Fix:** Updated requirements.txt with all dependencies:
```txt
python-telegram-bot==21.6
httpx==0.27.2
fastapi==0.115.5
uvicorn==0.32.1
stripe==11.1.0
psycopg[binary]==3.2.3
aiohttp==3.9.1
python-dotenv==1.0.0
```

## PIAPI Suno Integration Confirmed

✅ **PIAPI endpoint:** `/suno/music`  
✅ **Configuration variables:**
- `PIAPI_API_KEY` - Your PIAPI API key
- `PIAPI_BASE_URL` - PIAPI base URL (default: empty, set to your PIAPI server)
- `PIAPI_GENERATE_PATH` - Path to Suno endpoint (default: `/suno/music`)

✅ **Music generation flow:**
1. User sends topic/description
2. Bot generates lyrics with OpenRouter
3. User clicks "🎵 Сгенерировать песню" button
4. Bot calls PIAPI Suno API with lyrics, genre, mood
5. Bot extracts audio URLs from response
6. Bot sends audio files to user

## How to Run

### Locally:
1. Create `.env` file:
```env
BOT_TOKEN=your_telegram_bot_token
OPENROUTER_API_KEY=your_openrouter_key
PIAPI_API_KEY=your_piapi_key
PIAPI_BASE_URL=https://your-piapi-server.com
DATABASE_URL=postgresql://user:pass@host/db
STRIPE_SECRET_KEY=your_stripe_key
STRIPE_WEBHOOK_SECRET=your_webhook_secret
STRIPE_SUCCESS_URL=https://t.me/your_bot
STRIPE_CANCEL_URL=https://t.me/your_bot
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run:
```bash
python main.py
```

### On Render:
1. Set all environment variables in Render Dashboard
2. Set PORT=8000 (or Render will auto-assign)
3. Deploy - Render will run `python main.py` automatically

## Architecture

```
┌─────────────────┐
│   main.py       │
├─────────────────┤
│ FastAPI Server  │◄──── Stripe Webhooks (port 8000)
│                 │
│ Telegram Bot    │◄──── User messages (polling)
│                 │
│ PostgreSQL DB   │◄──── User balance & settings
└─────────────────┘
         │
         ├──► OpenRouter API (lyrics generation)
         └──► PIAPI Suno API (music generation)
```

## Testing

Start the bot and test the flow:
1. `/start` - Shows language selection
2. Select language
3. Choose genre (Pop, Rock, Hip-Hop, etc.)
4. Choose mood (Happy, Sad, Love, etc.)
5. Describe your song topic
6. Bot generates lyrics
7. Click "🎵 Сгенерировать песню"
8. Bot generates music via PIAPI
9. Receive audio files

## All Fixed! 🎉
