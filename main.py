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

# Выводим логи в stdout, чтобы Render их видел мгновенно
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN not set")

# Хранилище состояний
user_state = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("▶️ START", callback_data="start")]]
    await update.message.reply_text(
        "🎵 *MusicAi*\n\n"
        "I create a full song in 5 minutes.\n"
        "Lyrics, mood and style — personalised.\n\n"
        "Press START to begin 👇",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id

    if query.data == "start":
        user_state[uid] = {} # Инициализируем пустой словарь для пользователя
        keyboard = [
            [InlineKeyboardButton("English", callback_data="lang_en")],
            [InlineKeyboardButton("Polish", callback_data="lang_pl")],
            [InlineKeyboardButton("Russian", callback_data="lang_ru")],
        ]
        await query.edit_message_text(
            "Choose language:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif query.data.startswith("lang_"):
        # Проверяем, существует ли запись (защита от KeyError)
        if uid not in user_state: user_state[uid] = {}
        user_state[uid]["language"] = query.data[5:]
        keyboard = [
            [InlineKeyboardButton("Love ❤️", callback_data="theme_love")],
            [InlineKeyboardButton("Congratulations 🎉", callback_data="theme_congrats")],
            [InlineKeyboardButton("Funny 😄", callback_data="theme_fun")],
        ]
        await query.edit_message_text(
            "Choose theme:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif query.data.startswith("theme_"):
        if uid not in user_state: user_state[uid] = {}
        user_state[uid]["theme"] = query.data[6:]
        keyboard = [
            [InlineKeyboardButton("Pop", callback_data="genre_pop")],
            [InlineKeyboardButton("Rap / Hip-Hop", callback_data="genre_rap")],
            [InlineKeyboardButton("Rock", callback_data="genre_rock")],
            [InlineKeyboardButton("Club", callback_data="genre_club")],
            [InlineKeyboardButton("Classical", callback_data="genre_classic")],
            [InlineKeyboardButton("Disco Polo", callback_data="genre_disco")],
        ]
        await query.edit_message_text(
            "Choose genre:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif query.data.startswith("genre_"):
        if uid not in user_state: user_state[uid] = {}
        user_state[uid]["genre"] = query.data[6:]
        await query.edit_message_text(
            "🎤 Now write everything about the song:\n"
            "- Names\n"
            "- Stories\n"
            "- Mood\n\n"
            "Send me your text 👇"
        )

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id

    # Проверяем, прошел ли пользователь все шаги кнопок
    if uid not in user_state or "genre" not in user_state[uid]:
        await update.message.reply_text("Please press /start and follow the buttons first 🙂")
        return

    data = user_state[uid]
    prompt_text = update.message.text

    await update.message.reply_text(
        "✅ Got it!\n\n"
        "🎶 *Demo song preview*\n\n"
        f"*Language:* {data.get('language')}\n"
        f"*Theme:* {data.get('theme')}\n"
        f"*Genre:* {data.get('genre')}\n"
        f"*Idea:* {prompt_text[:50]}...\n\n"
        "This is a demo version.\n"
        "Full song generation will be available after purchase 💳",
        parse_mode="Markdown"
    )
    
    # Очищаем данные, чтобы не забивать память (опционально)
    # del user_state[uid]

def main():
    # Используем drop_pending_updates, чтобы бот не отвечал на старые сообщения после перезагрузки
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    logger.info("MusicAi bot started successfully")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
