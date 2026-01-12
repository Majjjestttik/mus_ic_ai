# -*- coding: utf-8 -*-

import os
import logging
import openai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ===== ЛОГИ =====
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# ===== ENV VARIABLES =====
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN not set")
if not OPENAI_KEY:
    raise RuntimeError("OPENAI_API_KEY not set")

openai.api_key = OPENAI_KEY

# ===== СТЕЙТЫ =====
user_data = {}  # хранит промежуточные ответы пользователя

# ===== /start =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("▶️ START", callback_data="start_flow")]]
    await update.message.reply_text(
        "🎵 Welcome to *MusicAi*\n"
        "I create a full song in 5 minutes!\n"
        "Press START to begin",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

# ===== CALLBACK =====
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    # Flow step
    if query.data == "start_flow":
        # Шаг 1: язык
        keyboard = [
            [InlineKeyboardButton("English", callback_data="lang_en")],
            [InlineKeyboardButton("Polish", callback_data="lang_pl")],
            [InlineKeyboardButton("Russian", callback_data="lang_ru")]
        ]
        await query.edit_message_text(
            "Choose the language for your song:", reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif query.data.startswith("lang_"):
        user_data[user_id] = {"language": query.data.split("_")[1]}
        # Шаг 2: повод/тема
        keyboard = [
            [InlineKeyboardButton("Love ❤️", callback_data="theme_love")],
            [InlineKeyboardButton("Congratulations 🎉", callback_data="theme_congrats")],
            [InlineKeyboardButton("Funny 😎", callback_data="theme_fun")],
        ]
        await query.edit_message_text(
            "Choose the theme / occasion for your song:", reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif query.data.startswith("theme_"):
        user_data[user_id]["theme"] = query.data.split("_")[1]
        # Шаг 3: жанр
        keyboard = [
            [InlineKeyboardButton("Pop", callback_data="genre_pop")],
            [InlineKeyboardButton("Rap/Hip-Hop", callback_data="genre_rap")],
            [InlineKeyboardButton("Rock", callback_data="genre_rock")],
            [InlineKeyboardButton("Club", callback_data="genre_club")],
            [InlineKeyboardButton("Classical", callback_data="genre_classical")],
            [InlineKeyboardButton("Disco Polo", callback_data="genre_disco")],
        ]
        await query.edit_message_text(
            "Choose the genre for your song:", reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif query.data.startswith("genre_"):
        user_data[user_id]["genre"] = query.data.split("_")[1]
        await query.edit_message_text(
            "🎤 Now write everything that can inspire the song:\n"
            "- Names, stories, phrases\n"
            "- Mood / feelings\n\n"
            "Send your text message, I will create your song!"
        )

# ===== HANDLE USER TEXT =====
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in user_data or "genre" not in user_data[user_id]:
        await update.message.reply_text("Press START first to begin your song flow.")
        return

    user_data[user_id]["text"] = update.message.text
    await update.message.reply_text("🎶 Generating your song, please wait...")

    # ===== Call OpenAI (asynchronously) =====
    prompt = f"""
    Write a song based on the following:
    Language: {user_data[user_id]['language']}
    Theme: {user_data[user_id]['theme']}
    Genre: {user_data[user_id]['genre']}
    User inspiration text: {user_data[user_id]['text']}
    Provide 2 versions of the lyrics.
    """

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400
        )
        song_text = response['choices'][0]['message']['content']
        await update.message.reply_text(f"Here are 2 versions of your song:\n\n{song_text}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error generating song: {e}")

# ===== MAIN =====
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logging.info("MusicAi bot started")
    app.run_polling()

if __name__ == "__main__":
    main()