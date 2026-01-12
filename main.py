# -*- coding: utf-8 -*-
import os
import logging
import sys
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from openai import AsyncOpenAI

# ---------- ЛОГИ ----------
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("MusicAi")

# ---------- ENV ----------
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")

if not BOT_TOKEN or not OPENAI_KEY:
    raise RuntimeError("BOT_TOKEN or OPENAI_KEY missing!")

client = AsyncOpenAI(api_key=OPENAI_KEY)

# ---------- STATE ----------
users = {}
demo_done = set()

# ---------- ЦЕНЫ ----------
PRICES = {"1": 250, "5": 1000, "25": 4000}

# ---------- ТЕКСТЫ ----------
TEXT = {
    "start": "🎵 *MusicAi*\nI create songs using AI.\n\nPress START 👇",
    "lang": "🌍 Choose language:",
    "theme": "🎯 Choose theme:",
    "genre": "🎼 Choose genre:",
    "describe": "✍️ Describe the song:\n• Who is it for?\n• Story / Event\n• Mood & Emotions",
    "demo": "🎧 *Demo version (1 time only)*",
    "error": "⚠️ Temporary error. Try again later.",
}

# ---------- START ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton("▶️ START", callback_data="start")]]
    await update.message.reply_text(TEXT["start"], reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

# ---------- BUTTONS ----------
async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

    if q.data == "start":
        users[uid] = {}
        kb = [
            [InlineKeyboardButton("English 🇬🇧", callback_data="lang_en")],
            [InlineKeyboardButton("Deutsch 🇩🇪", callback_data="lang_de")],
            [InlineKeyboardButton("Español 🇪🇸", callback_data="lang_es")],
            [InlineKeyboardButton("Français 🇫🇷", callback_data="lang_fr")],
            [InlineKeyboardButton("Polski 🇵🇱", callback_data="lang_pl")],
            [InlineKeyboardButton("Українська 🇺🇦", callback_data="lang_uk")]
        ]
        await q.edit_message_text(TEXT["lang"], reply_markup=InlineKeyboardMarkup(kb))

    elif q.data.startswith("lang_"):
        users[uid]["lang"] = q.data[5:]
        kb = [
            [InlineKeyboardButton("Love ❤️", callback_data="theme_love")],
            [InlineKeyboardButton("Funny 😄", callback_data="theme_fun")],
            [InlineKeyboardButton("Sad 😢", callback_data="theme_sad")],
            [InlineKeyboardButton("Wedding 💍", callback_data="theme_wedding")],
            [InlineKeyboardButton("Custom ✏️", callback_data="theme_custom")],
        ]
        await q.edit_message_text(TEXT["theme"], reply_markup=InlineKeyboardMarkup(kb))

    elif q.data.startswith("theme_"):
        users[uid]["theme"] = q.data[6:]
        kb = [
            [InlineKeyboardButton("Pop", callback_data="genre_pop")],
            [InlineKeyboardButton("Rap / Hip-Hop", callback_data="genre_rap")],
            [InlineKeyboardButton("Rock", callback_data="genre_rock")],
            [InlineKeyboardButton("Club", callback_data="genre_club")],
            [InlineKeyboardButton("Classical", callback_data="genre_classical")],
            [InlineKeyboardButton("Disco Polo", callback_data="genre_disco")],
        ]
        await q.edit_message_text(TEXT["genre"], reply_markup=InlineKeyboardMarkup(kb))

    elif q.data.startswith("genre_"):
        users[uid]["genre"] = q.data[6:]
        await q.edit_message_text(TEXT["describe"], parse_mode="Markdown")

# ---------- INPUT ----------
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in users or "genre" not in users[uid]:
        await update.message.reply_text("Please press /start first")
        return

    prompt = (
        f"Language: {users[uid]['lang']}\n"
        f"Theme: {users[uid]['theme']}\n"
        f"Genre: {users[uid]['genre']}\n"
        f"Description: {update.message.text}"
    )

    if uid not in demo_done:
        demo_done.add(uid)
        msg = await update.message.reply_text("⏳ Generating demo...")
        try:
            res = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=700
            )
            text = res.choices[0].message.content
            await msg.edit_text(f"{TEXT['demo']}\n\n{text[:3500]}", parse_mode="Markdown")
        except Exception as e:
            logger.error(e)
            await msg.edit_text(TEXT["error"])
        return

# ---------- MAIN ----------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("MusicAi STARTED")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()