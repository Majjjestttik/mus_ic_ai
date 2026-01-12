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

# ---------- ТЕКСТЫ ----------
TEXTS = {
    "start": {
        "en": "🎵 *MusicAi*\n\nI create a full song in 5 minutes.\nLyrics, mood and style — personalised.\n\nPress START to begin 👇",
        "ru": "🎵 *MusicAi*\n\nЯ создаю полноценную песню за 5 минут.\nТекст, настроение и стиль — персонально.\n\nНажми START, чтобы начать 👇",
        "pl": "🎵 *MusicAi*\n\nTworzę pełną piosenkę w 5 minut.\nTekst, klimat i styl — personalnie.\n\nNaciśnij START, aby rozpocząć 👇",
        "de": "🎵 *MusicAi*\n\nIch erstelle einen vollständigen Song in 5 Minuten.\nText, Stimmung und Stil — personalisiert.\n\nDrücke START, um zu beginnen 👇",
        "es": "🎵 *MusicAi*\n\nCreo una canción completa en 5 minutos.\nLetra, emoción y estilo — personalizados.\n\nPulsa START para comenzar 👇",
        "fr": "🎵 *MusicAi*\n\nJe crée une chanson complète en 5 minutes.\nParoles, ambiance et style — personnalisés.\n\nAppuie sur START pour commencer 👇",
    },
    "choose_language": {
        "en": "Choose language:",
        "ru": "Выбери язык:",
        "pl": "Wybierz język:",
        "de": "Sprache auswählen:",
        "es": "Elige idioma:",
        "fr": "Choisissez la langue:",
    },
    "choose_theme": {
        "en": "Choose occasion:",
        "ru": "Выбери повод:",
        "pl": "Wybierz okazję:",
        "de": "Anlass auswählen:",
        "es": "Elige ocasión:",
        "fr": "Choisissez l’occasion:",
    },
    "choose_genre": {
        "en": "Choose genre:",
        "ru": "Выбери жанр:",
        "pl": "Wybierz gatunek:",
        "de": "Genre auswählen:",
        "es": "Elige el género:",
        "fr": "Choisissez le genre:",
    },
    "write_text": {
        "en": "🎤 Now write everything about the song:\n- Names\n- Stories\n- Mood\n\nSend me your text 👇",
        "ru": "🎤 Теперь напиши всё о песне:\n- Имена\n- Истории\n- Настроение\n\nОтправь текст 👇",
        "pl": "🎤 Teraz napisz wszystko o piosence:\n- Imiona\n- Historie\n- Nastrój\n\nWyślij tekst 👇",
        "de": "🎤 Schreibe jetzt alles über den Song:\n- Namen\n- Geschichten\n- Stimmung\n\nSende mir deinen Text 👇",
        "es": "🎤 Ahora escribe todo sobre la canción:\n- Nombres\n- Historias\n- Emoción\n\nEnvíame tu texto 👇",
        "fr": "🎤 Écris maintenant tout sur la chanson:\n- Noms\n- Histoires\n- Ambiance\n\nEnvoie-moi ton texte 👇",
    },
    "wrong_order": {
        "en": "Please press /start and follow the buttons 🙂",
        "ru": "Пожалуйста, нажми /start и следуй кнопкам 🙂",
        "pl": "Naciśnij /start i postępuj zgodnie z przyciskami 🙂",
        "de": "Bitte drücke /start und folge den Schritten 🙂",
        "es": "Pulsa /start y sigue los botones 🙂",
        "fr": "Appuie sur /start et suis les boutons 🙂",
    },
    "demo": {
        "en": "✅ Got it!\n\n🎶 *Demo song preview*",
        "ru": "✅ Готово!\n\n🎶 *Демо-версия песни*",
        "pl": "✅ Gotowe!\n\n🎶 *Wersja demo piosenki*",
        "de": "✅ Fertig!\n\n🎶 *Demo-Version des Songs*",
        "es": "✅ Listo!\n\n🎶 *Versión demo de la canción*",
        "fr": "✅ Prêt!\n\n🎶 *Version démo de la chanson*",
    }
}

def t(uid, key):
    lang = user_state.get(uid, {}).get("language", "en")
    return TEXTS.get(key, {}).get(lang, TEXTS[key]["en"])

# ---------- /start ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("▶️ START", callback_data="start")]]
    await update.message.reply_text(
        TEXTS["start"]["en"],
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

# ---------- КНОПКИ ----------
async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id

    if query.data == "start":
        user_state[uid] = {}
        keyboard = [
            [InlineKeyboardButton("English 🇬🇧", callback_data="lang_en")],
            [InlineKeyboardButton("Русский 🇷🇺", callback_data="lang_ru")],
            [InlineKeyboardButton("Polski 🇵🇱", callback_data="lang_pl")],
            [InlineKeyboardButton("Deutsch 🇩🇪", callback_data="lang_de")],
            [InlineKeyboardButton("Español 🇪🇸", callback_data="lang_es")],
            [InlineKeyboardButton("Français 🇫🇷", callback_data="lang_fr")],
        ]
        await query.edit_message_text(
            TEXTS["choose_language"]["en"],
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif query.data.startswith("lang_"):
        user_state.setdefault(uid, {})
        user_state[uid]["language"] = query.data[5:]

        keyboard = [
            [InlineKeyboardButton("❤️ Love", callback_data="theme_love")],
            [InlineKeyboardButton("😄 Funny", callback_data="theme_funny")],
            [InlineKeyboardButton("🎉 Celebration", callback_data="theme_celebration")],
            [InlineKeyboardButton("😢 Sad", callback_data="theme_sad")],
            [InlineKeyboardButton("💍 Wedding", callback_data="theme_wedding")],
            [InlineKeyboardButton("🎼 Classic", callback_data="theme_classic")],
            [InlineKeyboardButton("✍️ Custom", callback_data="theme_custom")],
            [InlineKeyboardButton("🇵🇱 Disco Polo", callback_data="theme_disco_polo")],
        ]
        await query.edit_message_text(
            t(uid, "choose_theme"),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif query.data.startswith("theme_"):
        user_state.setdefault(uid, {})
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
            t(uid, "choose_genre"),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif query.data.startswith("genre_"):
        user_state.setdefault(uid, {})
        user_state[uid]["genre"] = query.data[6:]
        await query.edit_message_text(t(uid, "write_text"))

# ---------- ТЕКСТ ----------
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id

    if uid not in user_state or "genre" not in user_state[uid]:
        await update.message.reply_text(t(uid, "wrong_order"))
        return

    data = user_state[uid]
    idea = update.message.text

    await update.message.reply_text(
        f"{t(uid, 'demo')}\n\n"
        f"*Language:* {data['language']}\n"
        f"*Occasion:* {data['theme']}\n"
        f"*Genre:* {data['genre']}\n"
        f"*Idea:* {idea[:80]}...\n\n"
        "_This is a demo version._",
        parse_mode="Markdown"
    )

# ---------- MAIN ----------
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    logger.info("MusicAi bot started")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()