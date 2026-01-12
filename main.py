# -*- coding: utf-8 -*-

import os
import logging
import sys
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters, PreCheckoutQueryHandler
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
PIAPI_KEY = os.getenv("PIAPI_KEY")  # для музыки (пока не используется)
OWNER_ID = int(os.getenv("OWNER_TG_ID", "0"))

if not BOT_TOKEN or not OPENAI_KEY:
    raise RuntimeError("BOT_TOKEN или OPENAI_KEY не установлены")

# -------------------- ИНИЦИАЛИЗАЦИЯ --------------------
client = AsyncOpenAI(api_key=OPENAI_KEY)
users = {}
demo_used = set()

# -------------------- ЦЕНЫ --------------------
PRICES = {"1": 250, "5": 1000, "25": 4000}

# -------------------- ЛОКАЛИЗАЦИЯ --------------------
TEXT = {
    "start": {
        "en": "🎵 *MusicAi*\n\nI create full songs in minutes.\nPress START 👇",
        "ru": "🎵 *MusicAi*\n\nСоздаю полноценные песни за минуты.\nНажми START 👇",
        "pl": "🎵 *MusicAi*\n\nTworzę pełne piosenki w kilka minut.\nNaciśnij START 👇",
        "de": "🎵 *MusicAi*\n\nIch erstelle vollständige Songs in Minuten.\nDrücke START 👇",
        "es": "🎵 *MusicAi*\n\nCreo canciones completas en minutos.\nPulsa START 👇",
        "fr": "🎵 *MusicAi*\n\nJe crée des chansons complètes en quelques minutes.\nAppuie sur START 👇",
        "uk": "🎵 *MusicAi*\n\nСтворюю повноцінні пісні за кілька хвилин.\nНатисни START 👇",
    },
    "choose_language": {
        "en": "Choose language:",
        "ru": "Выберите язык:",
        "pl": "Wybierz język:",
        "de": "Sprache auswählen:",
        "es": "Elige idioma:",
        "fr": "Choisissez la langue:",
        "uk": "Виберіть мову:",
    },
    "choose_theme": {
        "en": "Choose theme:",
        "ru": "Выберите тему:",
        "pl": "Wybierz temat:",
        "de": "Wähle ein Thema:",
        "es": "Elige tema:",
        "fr": "Choisissez un thème:",
        "uk": "Виберіть тему:",
    },
    "choose_genre": {
        "en": "Choose genre:",
        "ru": "Выберите жанр:",
        "pl": "Wybierz gatunek:",
        "de": "Wähle Genre:",
        "es": "Elige género:",
        "fr": "Choisissez un genre:",
        "uk": "Виберіть жанр:",
    },
    "describe": {
        "en": "🎤 *Describe the song*\n- Who is it for?\n- Story / event\n- Mood & emotions\n💬 Or send a voice message",
        "ru": "🎤 *Опишите песню*\n- Кому посвящена?\n- История / событие\n- Настроение и эмоции\n💬 Или отправьте голосовое сообщение",
        "pl": "🎤 *Opisz piosenkę*\n- Dla kogo?\n- Historia / wydarzenie\n- Nastrój i emocje\n💬 Lub wyślij wiadomość głosową",
        "de": "🎤 *Beschreibe das Lied*\n- Für wen?\n- Geschichte / Ereignis\n- Stimmung & Emotionen\n💬 Oder Sprachnachricht senden",
        "es": "🎤 *Describe la canción*\n- Para quién?\n- Historia / evento\n- Estado de ánimo y emociones\n💬 O envía un mensaje de voz",
        "fr": "🎤 *Décris la chanson*\n- Pour qui?\n- Histoire / événement\n- Ambiance et émotions\n💬 Ou envoie un message vocal",
        "uk": "🎤 *Опишіть пісню*\n- Кому присвячена?\n- Історія / подія\n- Настрій та емоції\n💬 Або надішли голосове",
    },
    "demo": {
        "en": "🎧 *Demo version (1 time only)*",
        "ru": "🎧 *Демо (только 1 раз)*",
        "pl": "🎧 *Demo (tylko raz)*",
        "de": "🎧 *Demo (nur einmal)*",
        "es": "🎧 *Demo (solo 1 vez)*",
        "fr": "🎧 *Démo (une seule fois)*",
        "uk": "🎧 *Демо (тільки 1 раз)*",
    },
    "buy_confirm": "⚠️ *Confirmation*\nSpend ⭐ {stars}? Refunds NOT possible.\nAre you sure?",
    "paid": "✅ Payment successful! You can now generate full songs 🎶",
    "error": "⚠️ Temporary error. Please try again later."
}

# -------------------- ВСПОМОГАТЕЛЬНЫЕ --------------------
def t(uid, key):
    lang = users.get(uid, {}).get("lang", "en")
    return TEXT.get(key, {}).get(lang, TEXT[key]["en"]) if key in ["start","choose_language","choose_theme","choose_genre","describe","demo"] else TEXT[key]

# -------------------- /start --------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton("▶️ START", callback_data="start")]]
    await update.message.reply_text(t(0, "start"), reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

# -------------------- BUTTONS --------------------
async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

    if q.data == "start":
        users[uid] = {}
        kb = [
            [InlineKeyboardButton("English 🇬🇧", callback_data="lang_en"),
             InlineKeyboardButton("Русский 🇷🇺", callback_data="lang_ru")],
            [InlineKeyboardButton("Polski 🇵🇱", callback_data="lang_pl"),
             InlineKeyboardButton("Deutsch 🇩🇪", callback_data="lang_de")],
            [InlineKeyboardButton("Español 🇪🇸", callback_data="lang_es"),
             InlineKeyboardButton("Français 🇫🇷", callback_data="lang_fr")],
            [InlineKeyboardButton("Українська 🇺🇦", callback_data="lang_uk")]
        ]
        await q.edit_message_text(t(uid, "choose_language"), reply_markup=InlineKeyboardMarkup(kb))

    elif q.data.startswith("lang_"):
        users[uid]["lang"] = q.data[5:]
        kb = [
            [InlineKeyboardButton("Love ❤️", callback_data="theme_love"),
             InlineKeyboardButton("Funny 😄", callback_data="theme_fun")],
            [InlineKeyboardButton("Sad 😢", callback_data="theme_sad"),
             InlineKeyboardButton("Wedding 💍", callback_data="theme_wedding")],
            [InlineKeyboardButton("Custom ✏️", callback_data="theme_custom"),
             InlineKeyboardButton("Disco Polo 🎶", callback_data="theme_disco")]
        ]
        await q.edit_message_text(t(uid, "choose_theme"), reply_markup=InlineKeyboardMarkup(kb))

    elif q.data.startswith("theme_"):
        users[uid]["theme"] = q.data[6:]
        kb = [
            [InlineKeyboardButton("Pop", callback_data="genre_pop"),
             InlineKeyboardButton("Rap / Hip-Hop", callback_data="genre_rap")],
            [InlineKeyboardButton("Rock", callback_data="genre_rock"),
             InlineKeyboardButton("Club", callback_data="genre_club")],
            [InlineKeyboardButton("Classical", callback_data="genre_classic"),
             InlineKeyboardButton("Disco Polo", callback_data="genre_disco")]
        ]
        await q.edit_message_text(t(uid, "choose_genre"), reply_markup=InlineKeyboardMarkup(kb))

    elif q.data.startswith("genre_"):
        users[uid]["genre"] = q.data[6:]
        await q.edit_message_text(t(uid, "describe"), parse_mode="Markdown")

# -------------------- USER INPUT --------------------
async def user_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in users or "genre" not in users[uid]:
        await update.message.reply_text("Please press /start first.")
        return

    text = update.message.text or "Voice description received"
    data = users[uid]
    prompt = f"Language: {data['lang']}\nTheme: {data['theme']}\nGenre: {data['genre']}\nDescription: {text}"

    if uid not in demo_used:
        demo_used.add(uid)
        msg = await update.message.reply_text("⏳ *Generating your demo...*", parse_mode="Markdown")
        try:
            res = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role":"user","content":prompt}]
            )
            song = res.choices[0].message.content
            await msg.edit_text(f"{t(uid,'demo')}\n\n{song[:3500]}", parse_mode="Markdown")
        except Exception as e:
            logger.error(e)
            await msg.edit_text(TEXT["error"])
        return

    # После демо — показать кнопки покупки
    kb = [
        [InlineKeyboardButton("⭐ 1 song — 250", callback_data="buy_1")],
        [InlineKeyboardButton("⭐ 5 songs — 1000", callback_data="buy_5")],
        [InlineKeyboardButton("⭐ 25 songs — 4000", callback_data="buy_25")]
    ]
    await update.message.reply_text("💳 Buy full version to continue:", reply_markup=InlineKeyboardMarkup(kb))

# -------------------- PAYMENTS --------------------
async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(TEXT["paid"])
    if OWNER_ID:
        await context.bot.send_message(OWNER_ID, f"⭐ Payment received from @{update.effective_user.username}")

# -------------------- HELP --------------------
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await update.message.reply_text("Help: rules and instructions of the bot.")

# -------------------- MAIN --------------------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT | filters.VOICE, user_input))
    app.add_handler(PreCheckoutQueryHandler(pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    app.add_handler(CommandHandler("help", help_command))

    logger.info("MusicAi bot started")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()