# -*- coding: utf-8 -*-

import os
import logging
import sys
from openai import AsyncOpenAI  # Используем асинхронный клиент
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ===== ЛОГИ (оптимизировано для Render) =====
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ===== ENV VARIABLES =====
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")

if not TOKEN or not OPENAI_KEY:
    logger.error("Критические переменные окружения не заданы!")
    sys.exit(1)

# Инициализируем асинхронный клиент OpenAI
client = AsyncOpenAI(api_key=OPENAI_KEY)

# ===== СТЕЙТЫ (в продакшене лучше использовать БД или context.user_data) =====
user_data = {} 

# ===== /start =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("▶️ START", callback_data="start_flow")]]
    await update.message.reply_text(
        "🎵 *Welcome to MusicAi*\n"
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

    if query.data == "start_flow":
        keyboard = [
            [InlineKeyboardButton("English 🇺🇸", callback_data="lang_en")],
            [InlineKeyboardButton("Polish 🇵🇱", callback_data="lang_pl")],
            [InlineKeyboardButton("Russian 🇷🇺", callback_data="lang_ru")]
        ]
        await query.edit_message_text(
            "Choose the language for your song:", reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif query.data.startswith("lang_"):
        user_data[user_id] = {"language": query.data.split("_")[1]}
        keyboard = [
            [InlineKeyboardButton("Love ❤️", callback_data="theme_love")],
            [InlineKeyboardButton("Congratulations 🎉", callback_data="theme_congrats")],
            [InlineKeyboardButton("Funny 😎", callback_data="theme_fun")],
        ]
        await query.edit_message_text(
            "Choose the theme / occasion for your song:", reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif query.data.startswith("theme_"):
        if user_id not in user_data: user_data[user_id] = {}
        user_data[user_id]["theme"] = query.data.split("_")[1]
        keyboard = [
            [InlineKeyboardButton("Pop 🎤", callback_data="genre_pop")],
            [InlineKeyboardButton("Rap 🤘", callback_data="genre_rap")],
            [InlineKeyboardButton("Rock 🎸", callback_data="genre_rock")],
            [InlineKeyboardButton("Club 💃", callback_data="genre_club")]
        ]
        await query.edit_message_text(
            "Choose the genre for your song:", reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif query.data.startswith("genre_"):
        if user_id not in user_data: user_data[user_id] = {}
        user_data[user_id]["genre"] = query.data.split("_")[1]
        await query.edit_message_text(
            "🎤 *Now describe your idea:*\n"
            "Names, stories, mood, or specific phrases you want to include.\n\n"
            "Just send it as a text message!",
            parse_mode="Markdown"
        )

# ===== HANDLE USER TEXT =====
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    
    if user_id not in user_data or "genre" not in user_data[user_id]:
        await update.message.reply_text("Please press /start to begin the process.")
        return

    user_data[user_id]["text"] = update.message.text
    msg = await update.message.reply_text("🎶 *Generating your song...* This usually takes 30-60 seconds.", parse_mode="Markdown")

    prompt = (
        f"Write a song lyrics. Language: {user_data[user_id]['language']}. "
        f"Theme: {user_data[user_id]['theme']}. Genre: {user_data[user_id]['genre']}. "
        f"Context: {user_data[user_id]['text']}. Provide 2 creative versions."
    )

    try:
        # Асинхронный вызов OpenAI
        chat_completion = await client.chat.completions.create(
            model="gpt-4o", # Рекомендую gpt-4o-mini (быстрее и дешевле)
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800
        )
        
        song_text = chat_completion.choices[0].message.content
        await msg.edit_text(f"✨ *Here are your song versions:*\n\n{song_text}", parse_mode="Markdown")
        
        # Очищаем данные пользователя после генерации
        del user_data[user_id]
        
    except Exception as e:
        logger.error(f"OpenAI Error: {e}")
        await msg.edit_text(f"❌ Sorry, something went wrong with the AI: {e}")

# ===== MAIN =====
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("MusicAi bot is running on Background Worker...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
