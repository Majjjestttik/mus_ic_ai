# -*- coding: utf-8 -*-
import os
import logging
import sys
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)
from openai import AsyncOpenAI

# -------------------- ЛОГИ --------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("MusicAi")

# -------------------- ENV --------------------
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
PIAPI_KEY = os.getenv("PIAPI_KEY")  # пока оставляем для будущей музыки

if not BOT_TOKEN or not OPENAI_KEY:
    raise RuntimeError("BOT_TOKEN or OPENAI_KEY not set")

client = AsyncOpenAI(api_key=OPENAI_KEY)

# -------------------- STATE --------------------
users = {}
demo_done = set()

# -------------------- ЦЕНЫ --------------------
PRICES = {"1": 250, "5": 1000, "25": 4000}

# -------------------- ТЕКСТЫ --------------------
TEXT = {
    "start": "🎵 *MusicAi*\n\nI create songs using AI.\n\nPress START 👇",
    "lang": "Choose language:",
    "theme": "Choose theme:",
    "genre": "Choose genre:",
    "describe": "🎤 *Now the most important part!*\nWrite everything about the song step by step, or send a voice message.",
    "demo": "🎧 *Demo version (1 time only)*",
    "buy": "💳 Buy full version to continue:",
    "error": "⚠️ Temporary error. Try again later."
}

LANGS = ["English 🇬🇧", "Русский 🇷🇺", "Polski 🇵🇱", "Deutsch 🇩🇪", "Español 🇪🇸", "Français 🇫🇷", "Українська 🇺🇦"]
LANG_CODES = ["en", "ru", "pl", "de", "es", "fr", "uk"]

THEMES = ["Love ❤️", "Funny 😄", "Sad 😢", "Wedding 💍", "Classical 🎼", "Custom ✏️", "Disco Polo 🎶"]
THEME_CODES = ["love", "fun", "sad", "wedding", "classic", "custom", "disco"]

GENRES = ["Pop", "Rap / Hip-Hop", "Rock", "Club", "Classical", "Disco Polo"]
GENRE_CODES = ["pop", "rap", "rock", "club", "classic", "disco"]

# -------------------- OPENAI --------------------
async def generate_song_text(prompt: str):
    try:
        res = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        return res.choices[0].message.content
    except Exception as e:
        logger.error(f"OpenAI Error: {e}")
        return None

# -------------------- /start --------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton("▶️ START", callback_data="start")]]
    await update.message.reply_text(TEXT["start"], reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

# -------------------- BUTTONS --------------------
async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

    if q.data == "start":
        users[uid] = {}
        kb = [[InlineKeyboardButton(lang, callback_data=f"lang_{code}")] for lang, code in zip(LANGS, LANG_CODES)]
        await q.edit_message_text(TEXT["lang"], reply_markup=InlineKeyboardMarkup(kb))

    elif q.data.startswith("lang_"):
        users[uid]["lang"] = q.data[5:]
        kb = [[InlineKeyboardButton(theme, callback_data=f"theme_{code}")] for theme, code in zip(THEMES, THEME_CODES)]
        await q.edit_message_text(TEXT["theme"], reply_markup=InlineKeyboardMarkup(kb))

    elif q.data.startswith("theme_"):
        users[uid]["theme"] = q.data[6:]
        kb = [[InlineKeyboardButton(genre, callback_data=f"genre_{code}")] for genre, code in zip(GENRES, GENRE_CODES)]
        await q.edit_message_text(TEXT["genre"], reply_markup=InlineKeyboardMarkup(kb))

    elif q.data.startswith("genre_"):
        users[uid]["genre"] = q.data[6:]
        await q.edit_message_text(TEXT["describe"], parse_mode="Markdown")

# -------------------- USER INPUT --------------------
async def user_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in users or "genre" not in users[uid]:
        await update.message.reply_text("Please press /start first.")
        return

    user_text = update.message.text or "Voice input received"
    data = users[uid]
    prompt = f"Language: {data['lang']}, Theme: {data['theme']}, Genre: {data['genre']}. Story: {user_text}"

    if uid not in demo_done:
        demo_done.add(uid)
        msg = await update.message.reply_text("⏳ *Generating demo...*", parse_mode="Markdown")
        song_text = await generate_song_text(prompt)
        if song_text:
            await msg.edit_text(f"{TEXT['demo']}\n\n{song_text[:3500]}", parse_mode="Markdown")
        else:
            await msg.edit_text(TEXT["error"])
        return

    # После демо — показать кнопки покупки
    kb = [[InlineKeyboardButton(f"⭐ {k} song(s) — {v}", callback_data=f"buy_{k}")] for k, v in PRICES.items()]
    await update.message.reply_text(TEXT["buy"], reply_markup=InlineKeyboardMarkup(kb))

# -------------------- MAIN --------------------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT, user_input))
    logger.info("MusicAi bot started (OpenAI text + PiAPI ready for music)")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()