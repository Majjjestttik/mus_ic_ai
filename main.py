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

# ---------- ЛОГИ ----------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ---------- ТОКЕНЫ ----------
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")

if not TOKEN or not OPENAI_KEY:
    raise RuntimeError("TELEGRAM_BOT_TOKEN или OPENAI_API_KEY не установлены в Render!")

client = AsyncOpenAI(api_key=OPENAI_KEY)

# ---------- СОСТОЯНИЯ ----------
user_state = {}

# ---------- ТЕКСТЫ ----------
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
        "en": "🎤 *Now describe your song!*\nWho is it for? What is the story? Send text or voice message 👇",
        "ru": "🎤 *Теперь опиши свою песню!*\nКому она? Какая история? Пришли текст или голосовое сообщение 👇",
        "pl": "🎤 *Teraz opisz swoją piosenkę!* Dla kogo jest? Jaka jest historia? Wyślij tekst lub wiadomość głosową 👇",
        "de": "🎤 *Beschreibe jetzt dein Lied!* Für wen ist es? Was ist die Geschichte? Sende Text oder Sprache 👇",
        "es": "🎤 *¡Ahora describe tu canción!* ¿Для кого es? ¿Cuál es la historia? Envía texto o voz 👇",
        "fr": "🎤 *Décrivez votre chanson!* Pour qui est-elle? Quelle est l'histoire? Envoyez un texte ou un message vocal 👇",
        "uk": "🎤 *Тепер опиши свою пісню!* Кому вона? Яка історія? Надішліть текст або голосове 👇",
    }
}

# ---------- ФУНКЦИИ-ПОМОЩНИКИ ----------
def get_t(uid, key):
    lang = user_state.get(uid, {}).get("language", "en")
    return TEXTS[key].get(lang, TEXTS[key]["en"])

# ---------- ОБРАБОТЧИКИ ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("▶️ START", callback_data="start")]]
    await update.message.reply_text(TEXTS["start"]["en"], reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

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
            [InlineKeyboardButton("Українська 🇺🇦", callback_data="lang_uk")]
        ]
        await query.edit_message_text(TEXTS["choose_language"]["en"], reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data.startswith("lang_"):
        user_state[uid]["language"] = query.data[5:]
        keyboard = [
            [InlineKeyboardButton("Love ❤️", callback_data="theme_love")],
            [InlineKeyboardButton("Congratulations 🎉", callback_data="theme_congrats")],
            [InlineKeyboardButton("Funny 😄", callback_data="theme_fun")],
        ]
        await query.edit_message_text(get_t(uid, "choose_theme"), reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data.startswith("theme_"):
        user_state[uid]["theme"] = query.data[6:]
        keyboard = [
            [InlineKeyboardButton("Pop", callback_data="genre_pop"), InlineKeyboardButton("Rap", callback_data="genre_rap")],
            [InlineKeyboardButton("Rock", callback_data="genre_rock"), InlineKeyboardButton("Club", callback_data="genre_club")],
            [InlineKeyboardButton("Classical", callback_data="genre_classic"), InlineKeyboardButton("Disco Polo", callback_data="genre_disco")]
        ]
        await query.edit_message_text(get_t(uid, "choose_genre"), reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data.startswith("genre_"):
        user_state[uid]["genre"] = query.data[6:]
        await query.edit_message_text(get_t(uid, "write_text"), parse_mode="Markdown")

async def handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in user_state or "genre" not in user_state[uid]:
        await update.message.reply_text("Please use /start first.")
        return

    data = user_state[uid]
    user_text = ""

    # Обработка ГОЛОСА
    if update.message.voice:
        msg = await update.message.reply_text("🎤 Listening...")
        file = await context.bot.get_file(update.message.voice.file_id)
        f_path = f"voice_{uid}.ogg"
        await file.download_to_drive(f_path)
        
        with open(f_path, "rb") as audio:
            trans = await client.audio.transcriptions.create(model="whisper-1", file=audio)
            user_text = trans.text
        os.remove(f_path)
        await msg.delete()
    else:
        user_text = update.message.text

    # ГЕНЕРАЦИЯ
    wait_msg = await update.message.reply_text("🎶 *Creating your song...*", parse_mode="Markdown")
    
    prompt = f"Write a song. Language: {data['language']}, Theme: {data['theme']}, Genre: {data['genre']}. Context: {user_text}. Provide 2 versions."
    
    try:
        res = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        await wait_msg.edit_text(f"✨ *Your Song:*\n\n{res.choices[0].message.content}", parse_mode="Markdown")
        del user_state[uid] # Сброс после успеха
    except Exception as e:
        await wait_msg.edit_text(f"❌ Error: {e}")

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT | filters.VOICE, handle_input))
    
    logger.info("Bot is running...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
