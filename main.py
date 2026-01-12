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

# ---------- ЛОГИ ----------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ---------- ТОКЕН ----------
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN not set")

# ---------- СОСТОЯНИЯ ----------
user_state = {}

# ---------- ТЕКСТЫ (Добавлен ключ menu) ----------
TEXTS = {
    "start": {
        "en": "🎵 *MusicAi*\n\nI create a full song in 5 minutes.\nLyrics, mood and style — personalised.\n\nPress START to begin 👇",
        "ru": "🎵 *MusicAi*\n\nЯ создаю полноценную песню за 5 минут.\nТекст, настроение и стиль — персонально.\n\nНажми START, чтобы начать 👇",
        # ... остальные языки оставляем как у вас ...
    },
    "choose_language": {
        "en": "Choose language:", "ru": "Выбери язык:", "pl": "Wybierz język:",
        "de": "Sprache auswählen:", "es": "Elige idioma:", "fr": "Choisissez la langue:", "uk": "Вибери мову:",
    },
    "choose_theme": {
        "en": "Choose theme:", "ru": "Выбери тему:", "pl": "Wybierz temat:",
        "de": "Wähle ein Thema:", "es": "Elige tema:", "fr": "Choisissez un thème:", "uk": "Вибери тему:",
    },
    "choose_genre": {
        "en": "Choose genre:", "ru": "Выбери жанр:", "pl": "Wybierz gatunek:",
        "de": "Wähle Genre:", "es": "Elige género:", "fr": "Choisissez un genre:", "uk": "Вибери жанр:",
    },
    "write_text": {
        "en": "🎤 Now the most important part! Write everything about the song...",
        "ru": "🎤 Ну а теперь самое главное! Напиши всё о песне...",
        # ... остальные языки ...
    }
}

# Добавим недостающий словарь для Help
HELP_TEXTS = {
    "en": "Help: All rules and FAQ...",
    "ru": "Помощь: Все правила и ответы...",
    # ...
}

# ---------- ФУНКЦИИ-ПОМОЩНИКИ ----------
def t(uid, key):
    lang = user_state.get(uid, {}).get("language", "en")
    return TEXTS.get(key, {}).get(lang, TEXTS.get(key, {}).get("en", "Text missing"))

# ---------- ОБРАБОТЧИК ОШИБОК ----------
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

# ---------- /start ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    # При старте всегда предлагаем выбрать язык, если он не выбран
    keyboard = [[InlineKeyboardButton("▶️ START", callback_data="start")]]
    await update.message.reply_text(
        TEXTS["start"]["en"],
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

# ---------- КНОПКИ (Исправлено и дополнено) ----------
async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id

    if query.data == "start":
        user_state[uid] = {}
        keyboard = [
            [InlineKeyboardButton("English 🇬🇧", callback_data="lang_en"), 
             InlineKeyboardButton("Русский 🇷🇺", callback_data="lang_ru")],
            [InlineKeyboardButton("Polski 🇵🇱", callback_data="lang_pl"),
             InlineKeyboardButton("Deutsch 🇩🇪", callback_data="lang_de")]
        ]
        await query.edit_message_text(TEXTS["choose_language"]["en"], reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data.startswith("lang_"):
        lang = query.data.split("_")[1]
        user_state[uid] = {"language": lang}
        
        keyboard = [
            [InlineKeyboardButton("Love ❤️", callback_data="theme_love")],
            [InlineKeyboardButton("Funny 😄", callback_data="theme_fun")]
        ]
        await query.edit_message_text(t(uid, "choose_theme"), reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data.startswith("theme_"):
        if uid not in user_state: user_state[uid] = {"language": "en"}
        user_state[uid]["theme"] = query.data.split("_")[1]
        
        keyboard = [
            [InlineKeyboardButton("Pop 🎤", callback_data="genre_pop")],
            [InlineKeyboardButton("Rock 🎸", callback_data="genre_rock")]
        ]
        await query.edit_message_text(t(uid, "choose_genre"), reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data.startswith("genre_"):
        if uid not in user_state: user_state[uid] = {"language": "en"}
        user_state[uid]["genre"] = query.data.split("_")[1]
        
        await query.edit_message_text(t(uid, "write_text"), parse_mode="Markdown")

# ---------- ОБРАБОТКА ТЕКСТА ----------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in user_state or "genre" not in user_state[uid]:
        await update.message.reply_text("Please use /start first.")
        return
    
    # Здесь будет логика генерации или оплаты
    await update.message.reply_text(f"✅ Received! Genre: {user_state[uid]['genre']}. Processing...")

# ---------- MAIN ----------
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_error_handler(error_handler)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT | filters.VOICE, handle_message))

    logger.info("MusicAi bot started")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
