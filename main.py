# -*- coding: utf-8 -*-

import os
import logging
import sys
from openai import AsyncOpenAI
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ---------- ЛОГИ (Исправлено для Render) ----------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ---------- ТОКЕНЫ ----------
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")

if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN not set")
if not OPENAI_KEY:
    raise RuntimeError("OPENAI_API_KEY not set")

# Инициализируем клиент OpenAI (Новый синтаксис)
client = AsyncOpenAI(api_key=OPENAI_KEY)

# ---------- СОСТОЯНИЯ ----------
user_state = {}

# ---------- ЦЕНЫ ----------
BUY_OPTIONS = {
    "1_song": 250,
    "5_songs": 1000,
    "25_songs": 4000
}

# ---------- ТЕКСТЫ (ТВОИ ОРИГИНАЛЬНЫЕ БЕЗ ИЗМЕНЕНИЙ) ----------
TEXTS = {
    "start": {
        "en": "🎵 *MusicAi*\n\nI create a full song in 5 minutes.\nLyrics, mood and style — personalised.\n\nPress START to begin 👇",
        "ru": "🎵 *MusicAi*\n\nЯ создаю полноценную песню за 5 минут.\nТекст, настроение и стиль — персонально.\n\nНажми START, чтобы начать 👇",
        "pl": "🎵 *MusicAi*\n\nTworzę pełną piosenkę w 5 minut.\nTekst, klimat i styl — personalnie.\n\nNaciśnij START, aby rozpocząć 👇",
        "de": "🎵 *MusicAi*\n\nIch erstelle einen vollständigen Song in 5 Minuten.\nText, Stimmung und Stil — personalisiert.\n\nDrücke START, um zu beginnen 👇",
        "es": "🎵 *MusicAi*\n\nCreo una canción completa en 5 minutos.\nLetra, emoción y estilo — personalizados.\n\nPulsa START para comenzar 👇",
        "fr": "🎵 *MusicAi*\n\nJe crée une chanson complète en 5 minutes.\nParoles, ambiance et style — personnalisés.\n\nAppuie sur START pour commencer 👇",
        "uk": "🎵 *MusicAi*\n\nЯ створюю повноцінну пісню за 5 хвилин.\nТекст, настрій та стиль — персонально.\n\nНатисни START, щоб почати 👇",
    },
    "choose_language": {
        "en": "Choose language:", "ru": "Выбери язык:", "pl": "Wybierz język:", "de": "Sprache auswählen:", "es": "Elige idioma:", "fr": "Choisissez la langue:", "uk": "Вибери мову:",
    },
    "choose_theme": {
        "en": "Choose theme:", "ru": "Выбери тему:", "pl": "Wybierz temat:", "de": "Wähle ein Thema:", "es": "Elige tema:", "fr": "Choisissez un thème:", "uk": "Вибери тему:",
    },
    "choose_genre": {
        "en": "Choose genre:", "ru": "Выбери жанр:", "pl": "Wybierz gatunek:", "de": "Wähle Genre:", "es": "Elige género:", "fr": "Choisissez un genre:", "uk": "Вибери жанр:",
    },
    "write_text": {
        "en": "🎤 Now the most important part!\n\nWrite everything about the song step by step...\n💬 If you don’t want to type — send a voice message, I will understand everything.",
        "ru": "🎤 Ну а теперь самое главное!\n\nНапиши всё о песне по пунктам...\n💬 Если лень писать — можешь отправить голосовое, я всё уловлю.",
        "pl": "🎤 Teraz najważniejsze!\n\nNapisz wszystko o piosence krok po kroku...\n💬 Jeśli nie chce Ci się pisać — wyślij wiadomość głosową, wszystko zrozumiem.",
        "de": "🎤 Jetzt das Wichtigste!\n\nSchreibe alles über das Lied Schritt für Schritt...\n💬 Wenn du nicht tippen willst — sende eine Sprachnachricht, ich verstehe alles.",
        "es": "🎤 Ahora lo más importante!\n\nEscribe todo sobre la canción paso a paso...\n💬 Si no quieres escribir — envía un mensaje de voz, lo entenderé todo.",
        "fr": "🎤 Maintenant le plus important!\n\nÉcris tout sur la chanson étape par étape...\n💬 Si tu ne veux pas écrire — envoie un message vocal, je comprendrai tout.",
        "uk": "🎤 Тепер найголовніше!\n\nНапиши все про пісню по пунктах...\n💬 Якщо не хочеш писати — надішли голосове, я все зрозумію."
    }
}

# ---------- ФУНКЦИИ ----------
def t(uid, key):
    lang = user_state.get(uid, {}).get("language", "en")
    return TEXTS.get(key, {}).get(lang, TEXTS[key]["en"])

# ---------- ОБРАБОТЧИК ОШИБОК ----------
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

# ---------- /start ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("▶️ START", callback_data="start")]]
    await update.message.reply_text(
        TEXTS["start"]["en"],
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

# ---------- КНОПКИ (Исправлено) ----------
async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id

    if query.data == "start":
        user_state[uid] = {}
        keyboard = [
            [InlineKeyboardButton("English 🇬🇧", callback_data="lang_en"), InlineKeyboardButton("Русский 🇷🇺", callback_data="lang_ru")],
            [InlineKeyboardButton("Polski 🇵🇱", callback_data="lang_pl"), InlineKeyboardButton("Deutsch 🇩🇪", callback_data="lang_de")],
            [InlineKeyboardButton("Español 🇪🇸", callback_data="lang_es"), InlineKeyboardButton("Français 🇫🇷", callback_data="lang_fr")],
            [InlineKeyboardButton("Українська 🇺🇦", callback_data="lang_uk")],
        ]
        await query.edit_message_text(t(uid, "choose_language"), reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif query.data.startswith("lang_"):
        user_state[uid]["language"] = query.data[5:]
        keyboard = [
            [InlineKeyboardButton("Love ❤️", callback_data="theme_love")],
            [InlineKeyboardButton("Congratulations 🎉", callback_data="theme_congrats")],
            [InlineKeyboardButton("Funny 😄", callback_data="theme_fun")],
        ]
        await query.edit_message_text(t(uid, "choose_theme"), reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data.startswith("theme_"):
        if uid not in user_state: user_state[uid] = {"language": "en"}
        user_state[uid]["theme"] = query.data[6:]
        keyboard = [
            [InlineKeyboardButton("Pop", callback_data="genre_pop"), InlineKeyboardButton("Rap", callback_data="genre_rap")],
            [InlineKeyboardButton("Rock", callback_data="genre_rock"), InlineKeyboardButton("Club", callback_data="genre_club")],
            [InlineKeyboardButton("Classical", callback_data="genre_classic"), InlineKeyboardButton("Disco Polo", callback_data="genre_disco")],
        ]
        await query.edit_message_text(t(uid, "choose_genre"), reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data.startswith("genre_"):
        if uid not in user_state: user_state[uid] = {"language": "en"}
        user_state[uid]["genre"] = query.data[6:]
        await query.edit_message_text(t(uid, "write_text"), parse_mode="Markdown")

# ---------- ОБРАБОТКА ВВОДА (Текст + Голос) ----------
async def handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in user_state or "genre" not in user_state[uid]:
        await update.message.reply_text("Please press /start first.")
        return

    data = user_state[uid]
    user_prompt = ""

    if update.message.voice:
        msg = await update.message.reply_text("🎤 Listening...")
        file = await context.bot.get_file(update.message.voice.file_id)
        path = f"v_{uid}.ogg"
        await file.download_to_drive(path)
        with open(path, "rb") as f:
            trans = await client.audio.transcriptions.create(model="whisper-1", file=f)
            user_prompt = trans.text
        os.remove(path)
        await msg.delete()
    else:
        user_prompt = update.message.text

    # Финальный ответ с демо-песней через OpenAI
    wait_msg = await update.message.reply_text("🎶 *Generating your demo...*", parse_mode="Markdown")
    
    prompt = f"Write 2 song lyrics. Language: {data['language']}, Theme: {data['theme']}, Genre: {data['genre']}. Story: {user_prompt}"
    
    try:
        res = await client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
        lyrics = res.choices[0].message.content
        await wait_msg.edit_text(f"✅ *Demo Ready!*\n\n{lyrics}\n\n💳 Full version available after purchase.", parse_mode="Markdown")
        del user_state[uid]
    except Exception as e:
        await wait_msg.edit_text(f"❌ Error: {e}")

# ---------- MAIN ----------
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_error_handler(error_handler)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT | filters.VOICE, handle_input))

    logger.info("MusicAi bot started")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
