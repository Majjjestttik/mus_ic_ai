import os
import json
import asyncio
import logging
from typing import Dict, Any, Optional

import aiohttp
import stripe
import psycopg
from psycopg.rows import dict_row

from dotenv import load_dotenv

from fastapi import FastAPI, Request, Header, HTTPException

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# Load environment variables
load_dotenv()

# -------------------------
# Configuration
# -------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()

PIAPI_API_KEY = os.getenv("PIAPI_API_KEY", "").strip()
PIAPI_BASE_URL = os.getenv("PIAPI_BASE_URL", "").strip().rstrip("/")
PIAPI_GENERATE_PATH = os.getenv("PIAPI_GENERATE_PATH", "/suno/music").strip()

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "").strip()
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()
STRIPE_SUCCESS_URL = os.getenv("STRIPE_SUCCESS_URL", "").strip()
STRIPE_CANCEL_URL = os.getenv("STRIPE_CANCEL_URL", "").strip()

# -------------------------
# Logging
# -------------------------
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# -------------------------
# Stripe initialization
# -------------------------
if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

# -------------------------
# Translations
# -------------------------
TRANSLATIONS = {
    "en": {
        "welcome": "🎵 Welcome to MusicAI PRO!\nI'll help you create personalized songs.",
        "choose_language": "Choose your language:",
        "language_set": "Language set to English 🇬🇧",
        "menu": "📋 Main Menu",
        "buy": "💎 Buy Song Credits",
        "balance": "Balance: {} songs",
        "generating": "🎶 Generating your song...",
        "done": "✅ Done!",
        "error": "❌ Error: {}",
    },
    "ru": {
        "welcome": "🎵 Добро пожаловать в MusicAI PRO!\nЯ помогу создать персональную песню.",
        "choose_language": "Выберите язык:",
        "language_set": "Язык установлен: Русский 🇷🇺",
        "menu": "📋 Главное меню",
        "buy": "💎 Купить кредиты",
        "balance": "Баланс: {} песен",
        "generating": "🎶 Генерирую вашу песню...",
        "done": "✅ Готово!",
        "error": "❌ Ошибка: {}",
    },
}

LANGS = ["en", "ru", "es", "fr", "de", "it", "pt"]

# -------------------------
# Pricing packs
# -------------------------
PACKS = {
    "pack_1": {"songs": 1, "price": 6.00, "label": "1 song - €6.00"},
    "pack_5": {"songs": 5, "price": 20.00, "label": "5 songs - €20.00"},
    "pack_30": {"songs": 30, "price": 50.00, "label": "30 songs - €50.00"},
}

# -------------------------
# DB helpers (sync, call via asyncio.to_thread)
# -------------------------
def db_conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set")
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)

def init_db():
    with db_conn() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            lang TEXT NOT NULL DEFAULT 'en',
            balance INT NOT NULL DEFAULT 0,
            demo_used INT NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """)
        conn.commit()

def ensure_user(user_id: int):
    with db_conn() as conn:
        conn.execute("INSERT INTO users (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (user_id,))
        conn.commit()

def set_lang(user_id: int, lang: str):
    ensure_user(user_id)
    with db_conn() as conn:
        conn.execute("UPDATE users SET lang=%s WHERE user_id=%s", (lang, user_id))
        conn.commit()

def get_user(user_id: int) -> Dict[str, Any]:
    ensure_user(user_id)
    with db_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id=%s", (user_id,)).fetchone()
        return dict(row) if row else {}

def add_balance(user_id: int, songs: int):
    ensure_user(user_id)
    with db_conn() as conn:
        conn.execute("UPDATE users SET balance=balance+%s WHERE user_id=%s", (songs, user_id))
        conn.commit()

def consume_song(user_id: int) -> bool:
    ensure_user(user_id)
    with db_conn() as conn:
        row = conn.execute("SELECT balance FROM users WHERE user_id=%s", (user_id,)).fetchone()
        if not row or row["balance"] < 1:
            return False
        conn.execute("UPDATE users SET balance=balance-1 WHERE user_id=%s", (user_id,))
        conn.commit()
        return True

# -------------------------
# Helpers
# -------------------------
def tr(user_id: int, key: str) -> str:
    """Translate text for user"""
    user = get_user(user_id)
    lang = user.get("lang", "en")
    return TRANSLATIONS.get(lang, TRANSLATIONS["en"]).get(key, key)

# -------------------------
# OpenRouter lyrics generation
# -------------------------
async def openrouter_lyrics(topic: str, lang_code: str, genre: str, mood: str) -> str:
    """Generate song lyrics using OpenRouter"""
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY not set")

    prompt = f"""Create song lyrics in {lang_code} language.
Topic: {topic}
Genre: {genre}
Mood: {mood}

IMPORTANT: Write lyrics with proper rhyme scheme. Each verse should have rhyming lines.
Format: 
[Verse 1]
...lyrics with rhymes...

[Chorus]
...catchy chorus with rhymes...

[Verse 2]
...more lyrics with rhymes...
"""

    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "openai/gpt-3.5-turbo",
                "messages": [{"role": "user", "content": prompt}],
            },
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"OpenRouter error: {text}")
            data = await resp.json()
            return data["choices"][0]["message"]["content"]

# -------------------------
# PIAPI Suno music generation
# -------------------------
async def piapi_generate_music(lyrics: str, genre: str, mood: str, demo: bool) -> Dict[str, Any]:
    """Generate music using PIAPI Suno endpoint"""
    if not PIAPI_API_KEY:
        raise RuntimeError("PIAPI_API_KEY not set")
    
    url = f"{PIAPI_BASE_URL}{PIAPI_GENERATE_PATH}"
    
    payload = {
        "lyrics": lyrics,
        "tags": f"{genre}, {mood}",
        "title": f"{genre} song",
        "make_instrumental": False,
    }
    
    headers = {
        "Authorization": f"Bearer {PIAPI_API_KEY}",
        "Content-Type": "application/json",
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"PIAPI error {resp.status}: {text}")
            return await resp.json()

def extract_audio_urls(piapi_resp: Dict[str, Any]) -> list:
    """Extract audio URLs from PIAPI response"""
    urls = []
    if "data" in piapi_resp:
        for item in piapi_resp["data"]:
            if "audio_url" in item:
                urls.append(item["audio_url"])
    return urls

# -------------------------
# Keyboards
# -------------------------
def lang_keyboard() -> InlineKeyboardMarkup:
    buttons = []
    for lang in LANGS:
        flag = {"en": "🇬🇧", "ru": "🇷🇺", "es": "🇪🇸", "fr": "🇫🇷", "de": "🇩🇪", "it": "🇮🇹", "pt": "��🇹"}.get(lang, "🌍")
        buttons.append([InlineKeyboardButton(f"{flag} {lang.upper()}", callback_data=f"lang:{lang}")])
    return InlineKeyboardMarkup(buttons)

def menu_keyboard(lang: str) -> InlineKeyboardMarkup:
    user_trans = TRANSLATIONS.get(lang, TRANSLATIONS["en"])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(user_trans["buy"], callback_data="buy")],
    ])

def genres_keyboard(lang: str) -> InlineKeyboardMarkup:
    genres = ["Pop", "Rock", "Hip-Hop", "Classical", "Club", "Custom"]
    buttons = [[InlineKeyboardButton(g, callback_data=f"genre:{g}")] for g in genres]
    return InlineKeyboardMarkup(buttons)

def moods_keyboard(lang: str) -> InlineKeyboardMarkup:
    moods = ["Happy", "Sad", "Love", "Party", "Support", "Custom"]
    buttons = [[InlineKeyboardButton(m, callback_data=f"mood:{m}")] for m in moods]
    return InlineKeyboardMarkup(buttons)

def buy_keyboard(lang: str, user_id: int) -> InlineKeyboardMarkup:
    buttons = []
    for pack_id, pack_data in PACKS.items():
        label = pack_data["label"]
        buttons.append([InlineKeyboardButton(label, callback_data=f"buypack:{pack_id}")])
    return InlineKeyboardMarkup(buttons)

def create_checkout_session(user_id: int, pack_id: str) -> str:
    """Create Stripe checkout session and return URL"""
    if not STRIPE_SECRET_KEY:
        raise RuntimeError("Stripe not configured")
    
    pack = PACKS.get(pack_id)
    if not pack:
        raise ValueError("Invalid pack")
    
    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{
            "price_data": {
                "currency": "usd",
                "product_data": {"name": pack["label"]},
                "unit_amount": int(pack["price"] * 100),
            },
            "quantity": 1,
        }],
        mode="payment",
        success_url=STRIPE_SUCCESS_URL,
        cancel_url=STRIPE_CANCEL_URL,
        metadata={"user_id": str(user_id), "pack": pack_id},
    )
    return session.url

# -------------------------
# Telegram Handlers
# -------------------------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await asyncio.to_thread(ensure_user, user_id)
    
    text = tr(user_id, "welcome")
    await update.message.reply_text(text, reply_markup=lang_keyboard())

async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show language selection menu"""
    user_id = update.effective_user.id
    await asyncio.to_thread(ensure_user, user_id)
    
    text = tr(user_id, "choose_language")
    await update.message.reply_text(text, reply_markup=lang_keyboard())

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    if data.startswith("lang:"):
        lang = data.split(":")[1]
        await asyncio.to_thread(set_lang, user_id, lang)
        await query.edit_message_text(
            tr(user_id, "language_set"),
            reply_markup=menu_keyboard(lang)
        )
    
    elif data == "buy":
        user = await asyncio.to_thread(get_user, user_id)
        balance = user.get("balance", 0)
        text = f"{tr(user_id, 'buy')}\n{tr(user_id, 'balance').format(balance)}"
        await query.edit_message_text(text, reply_markup=buy_keyboard(user.get("lang", "en"), user_id))
    
    elif data.startswith("buypack:"):
        pack_id = data.split(":")[1]
        try:
            url = create_checkout_session(user_id, pack_id)
            await query.edit_message_text(f"Click to complete payment:\n{url}")
        except Exception as e:
            await query.edit_message_text(tr(user_id, "error").format(str(e)))
    
    elif data.startswith("genre:"):
        genre = data.split(":")[1]
        context.user_data[user_id] = {"genre": genre}
        await query.edit_message_text(f"Genre: {genre}\nNow choose mood:", reply_markup=moods_keyboard("en"))
    
    elif data.startswith("mood:"):
        mood = data.split(":")[1]
        user_data = context.user_data.get(user_id, {})
        user_data["mood"] = mood
        context.user_data[user_id] = user_data
        await query.edit_message_text(f"Mood: {mood}\n\nNow tell me about your song!")
    
    elif data.startswith("generate:"):
        # Generate music from lyrics
        user_data = context.user_data.get(user_id, {})
        lyrics = user_data.get("lyrics", "")
        genre = user_data.get("genre", "Pop")
        mood = user_data.get("mood", "Happy")
        
        if not lyrics:
            await query.edit_message_text(tr(user_id, "error").format("No lyrics found"))
            return
        
        # Check balance
        can_generate = await asyncio.to_thread(consume_song, user_id)
        if not can_generate:
            await query.edit_message_text(tr(user_id, "error").format("Insufficient balance"))
            return
        
        await query.edit_message_text("🎶 ГЕНЕРАЦИЯ ПЕСНИ НАЧАЛАСЬ! ⚡️\nОбычно занимает не более 5 минут.\nЯ сообщу, как только будет готово 🎧")
        
        try:
            result = await piapi_generate_music(lyrics, genre, mood, demo=False)
            audio_urls = extract_audio_urls(result)
            
            if audio_urls:
                for url in audio_urls:
                    await query.message.reply_audio(url)
                await query.message.reply_text(tr(user_id, "done"))
            else:
                await query.message.reply_text(tr(user_id, "error").format("No audio generated"))
        except Exception as e:
            log.error(f"Music generation error: {e}")
            await query.message.reply_text(tr(user_id, "error").format(str(e)))

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    
    user_data = context.user_data.get(user_id, {})
    
    # If user has selected genre and mood, generate lyrics
    if "genre" in user_data and "mood" in user_data:
        await update.message.reply_text(tr(user_id, "generating"))
        
        try:
            lyrics = await openrouter_lyrics(
                text,
                user_data.get("lang", "en"),
                user_data["genre"],
                user_data["mood"]
            )
            
            user_data["lyrics"] = lyrics
            context.user_data[user_id] = user_data
            
            # Show lyrics with generate button
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("🎵 Сгенерировать песню", callback_data=f"generate:{user_id}")
            ]])
            
            await update.message.reply_text(f"📝 Your lyrics:\n\n{lyrics}", reply_markup=kb)
        except Exception as e:
            log.error(f"Lyrics generation error: {e}")
            await update.message.reply_text(tr(user_id, "error").format(str(e)))
    else:
        # Start the flow
        await update.message.reply_text("Choose genre first:", reply_markup=genres_keyboard("en"))

# -------------------------
# FastAPI (Stripe webhook)
# -------------------------
app = FastAPI()

@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    await asyncio.to_thread(init_db)
    log.info("DB ready")
    
    if not PIAPI_API_KEY:
        log.warning("⚠️ PIAPI_API_KEY not set - music generation will not work")
    if not OPENROUTER_API_KEY:
        log.warning("⚠️ OPENROUTER_API_KEY not set - lyrics generation will not work")

@app.post("/stripe/webhook")
async def stripe_webhook(request: Request, stripe_signature: str = Header(None)):
    if not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=500, detail="STRIPE_WEBHOOK_SECRET not set")

    payload = await request.body()
    if not stripe_signature:
        raise HTTPException(status_code=400, detail="Missing Stripe-Signature header")

    try:
        event = stripe.Webhook.construct_event(payload, stripe_signature, STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid signature: {e}")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        meta = session.get("metadata") or {}
        user_id = meta.get("user_id")
        pack_id = meta.get("pack")

        if user_id and pack_id in PACKS:
            songs = int(PACKS[pack_id]["songs"])
            await asyncio.to_thread(add_balance, int(user_id), songs)
            log.info(f"Added {songs} songs to user {user_id}")

    return {"ok": True}

# -------------------------
# Run Telegram bot inside same process
# -------------------------
telegram_app: Optional[Application] = None

@app.on_event("startup")
async def start_telegram_bot():
    global telegram_app
    if not BOT_TOKEN:
        log.warning("BOT_TOKEN not set — telegram bot will not start")
        return

    telegram_app = Application.builder().token(BOT_TOKEN).build()

    telegram_app.add_handler(CommandHandler("start", cmd_start))
    telegram_app.add_handler(CommandHandler("menu", cmd_menu))
    telegram_app.add_handler(CallbackQueryHandler(on_callback))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    # Start polling as background task
    async def _run():
        await telegram_app.initialize()
        await telegram_app.start()
        await telegram_app.updater.start_polling(drop_pending_updates=True)
        log.info("Telegram bot started (polling)")

    asyncio.create_task(_run())

@app.get("/")
async def root():
    return {"status": "ok", "bot": "MusicAI PRO"}

# -------------------------
# Main entry point
# -------------------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
