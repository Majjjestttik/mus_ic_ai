# -*- coding: utf-8 -*-

import os
import logging
import sys
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)
from piapi import PiAPI  # подключаем PiApi
from openai import AsyncOpenAI

# ---------- Логи ----------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ---------- Токены ----------
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
OWNER_TG = int(os.getenv("OWNER_TG_ID"))

if not TOKEN or not OPENAI_KEY or not OWNER_TG:
    raise RuntimeError("Please set TELEGRAM_BOT_TOKEN, OPENAI_API_KEY, and OWNER_TG_ID environment variables")

# ---------- API Клиенты ----------
client = AsyncOpenAI(api_key=OPENAI_KEY)
pi = PiAPI()

# ---------- Состояния ----------
user_state = {}
user_demo_done = set()

# ---------- Цены ----------
BUY_OPTIONS = {
    "1": 250,
    "5": 1000,
    "25": 4000
}

# ---------- Локализация ----------
TEXTS = {
    "start": {
        "en": "🎵 *MusicAi*\n\nI create a full song in 5 minutes.\nLyrics, mood and style — personalised.\n\nPress START 👇",
        "ru": "🎵 *MusicAi*\n\nЯ создаю полноценную песню за 5 минут.\nТекст, настроение и стиль — персонально.\n\nНажми START 👇",
        "pl": "🎵 *MusicAi*\n\nTworzę pełną piosenkę w 5 minut.\nTekst, klimat i styl — personalnie.\n\nNaciśnij START 👇",
        "de": "🎵 *MusicAi*\n\nIch erstelle einen vollständigen Song in 5 Minuten.\nText, Stimmung und Stil — personalisiert.\n\nDrücke START 👇",
        "es": "🎵 *MusicAi*\n\nCreo una canción completa en 5 minutos.\nLetra, emoción y estilo — personalizados.\n\nPulsa START 👇",
        "fr": "🎵 *MusicAi*\n\nJe crée une chanson complète en 5 minutes.\nParoles, ambiance et style — personnalisés.\n\nAppuie sur START 👇",
        "uk": "🎵 *MusicAi*\n\nЯ створюю повноцінну пісню за 5 хвилин.\nТекст, настрій та стиль — персонально.\n\nНатисни START 👇",
    },
    "choose_language": {"en":"Choose language:", "ru":"Выбери язык:", "pl":"Wybierz język:", "de":"Sprache auswählen:", "es":"Elige idioma:", "fr":"Choisissez la langue:", "uk":"Вибери мову:"},
    "choose_theme": {"en":"Choose theme:", "ru":"Выбери тему:", "pl":"Wybierz temat:", "de":"Wähle ein Thema:", "es":"Elige tema:", "fr":"Choisissez un thème:", "uk":"Вибери тему:"},
    "choose_genre": {"en":"Choose genre:", "ru":"Выбери жанр:", "pl":"Wybierz gatunek:", "de":"Wähle Genre:", "es":"Elige género:", "fr":"Choisissez un genre:", "uk":"Вибери жанр:"},
    "write_text": {
        "en":"🎤 Write step by step:\n- Who is the song about?\n- Story or event\n- Mood & feelings\n💬 Or send a voice message.",
        "ru":"🎤 Напиши по пунктам:\n- Кому посвящается песня?\n- История или событие\n- Настроение и эмоции\n💬 Или отправь голосовое сообщение.",
        "pl":"🎤 Napisz krok po kroku:\n- Dla kogo jest piosenka?\n- Historia lub wydarzenie\n- Nastrój i emocje\n💬 Lub wyślij wiadomość głosową.",
        "de":"🎤 Schreibe Schritt für Schritt:\n- Für wen ist das Lied?\n- Geschichte oder Ereignis\n- Stimmung und Gefühle\n💬 Oder sende Sprachnachricht.",
        "es":"🎤 Escribe paso a paso:\n- Para quién es la canción?\n- Historia o evento\n- Estado de ánimo\n💬 O envía un mensaje de voz.",
        "fr":"🎤 Écris étape par étape:\n- Pour qui est la chanson?\n- Histoire ou événement\n- Ambiance et émotions\n💬 Ou envoie un message vocal.",
        "uk":"🎤 Напиши по пунктах:\n- Кому присвячена пісня?\n- Історія або подія\n- Настрій та емоції\n💬 Або надішли голосове повідомлення."
    },
    "help_text": {
        "en":"Help: Rules and instructions for MusicAi. Use in any social network.",
        "ru":"Помощь: Правила и инструкции MusicAi. Используйте в любой соцсети.",
        "pl":"Pomoc: Zasady i instrukcje MusicAi. Używaj w dowolnej sieci społecznościowej.",
        "de":"Hilfe: Regeln und Anleitungen MusicAi. In jedem sozialen Netzwerk verwendbar.",
        "es":"Ayuda: Reglas e instrucciones MusicAi. Se puede usar en cualquier red social.",
        "fr":"Aide: Règles et instructions MusicAi. Peut être utilisé sur n’importe quel réseau social.",
        "uk":"Допомога: Правила та інструкції MusicAi. Використовуйте у будь-якій соцмережі."
    }
}

# ---------- Вспомогательная ----------
def t(uid, key):
    lang = user_state.get(uid, {}).get("language","en")
    return TEXTS.get(key, {}).get(lang, TEXTS[key]["en"])

# ---------- Ошибки ----------
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

# ---------- START ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("▶️ START", callback_data="start")]]
    await update.message.reply_text(t(update.effective_user.id,"start"), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# ---------- Кнопки ----------
async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id

    if query.data=="start":
        user_state[uid]={}
        keyboard = [
            [InlineKeyboardButton("English 🇬🇧",callback_data="lang_en"), InlineKeyboardButton("Русский 🇷🇺",callback_data="lang_ru")],
            [InlineKeyboardButton("Polski 🇵🇱",callback_data="lang_pl"), InlineKeyboardButton("Deutsch 🇩🇪",callback_data="lang_de")],
            [InlineKeyboardButton("Español 🇪🇸",callback_data="lang_es"), InlineKeyboardButton("Français 🇫🇷",callback_data="lang_fr")],
            [InlineKeyboardButton("Українська 🇺🇦",callback_data="lang_uk")]
        ]
        await query.edit_message_text(t(uid,"choose_language"),reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data.startswith("lang_"):
        user_state[uid]["language"]=query.data[5:]
        keyboard=[
            [InlineKeyboardButton("Love ❤️",callback_data="theme_love"),InlineKeyboardButton("Congratulations 🎉",callback_data="theme_congrats")],
            [InlineKeyboardButton("Funny 😄",callback_data="theme_fun"),InlineKeyboardButton("Sad 😢",callback_data="theme_sad")],
            [InlineKeyboardButton("Wedding 💍",callback_data="theme_wedding"),InlineKeyboardButton("Classical 🎼",callback_data="theme_classic")],
            [InlineKeyboardButton("Custom ✏️",callback_data="theme_custom"),InlineKeyboardButton("Disco Polo 🎶",callback_data="theme_disco")]
        ]
        await query.edit_message_text(t(uid,"choose_theme"),reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data.startswith("theme_"):
        user_state[uid]["theme"]=query.data[6:]
        keyboard=[
            [InlineKeyboardButton("Pop",callback_data="genre_pop"),InlineKeyboardButton("Rap / Hip-Hop",callback_data="genre_rap")],
            [InlineKeyboardButton("Rock",callback_data="genre_rock"),InlineKeyboardButton("Club",callback_data="genre_club")],
            [InlineKeyboardButton("Classical",callback_data="genre_classic")]
        ]
        await query.edit_message_text(t(uid,"choose_genre"),reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data.startswith("genre_"):
        user_state[uid]["genre"]=query.data[6:]
        await query.edit_message_text(t(uid,"write_text"),parse_mode="Markdown")

    elif query.data.startswith("buy_"):
        # Подтверждение покупки
        user_state[uid]["pending_buy"]=int(query.data.split("_")[1])
        keyboard=[[InlineKeyboardButton("✅ Yes, charge my stars",callback_data="confirm_buy")],
                  [InlineKeyboardButton("❌ Cancel",callback_data="cancel_buy")]]
        await query.edit_message_text(f"⭐ You are about to spend {user_state[uid]['pending_buy']} stars.\nNo refunds! Are you sure?", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data=="confirm_buy":
        amount=user_state[uid].get("pending_buy")
        if amount:
            balance = await pi.get_balance(user_id=uid)
            if balance>=amount:
                await pi.spend_stars(user_id=uid,amount=amount)
                await context.bot.send_message(OWNER_TG,text=f"User @{query.from_user.username} bought {amount} stars worth of songs")
                await query.edit_message_text("✅ Purchase complete! You can now generate your full song 🎶")
            else:
                await query.edit_message_text("❌ Not enough stars. Please top up your Telegram Stars first.")
        user_state[uid].pop("pending_buy",None)

    elif query.data=="cancel_buy":
        user_state[uid].pop("pending_buy",None)
        await query.edit_message_text("❌ Purchase cancelled.")

# ---------- Обработка текста и голоса ----------
async def handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id
    if uid not in user_state or "genre" not in user_state[uid]:
        await update.message.reply_text("Please press /start first.")
        return

    data=user_state[uid]
    user_prompt=""
    if update.message.voice:
        msg=await update.message.reply_text("🎤 Listening...")
        file=await context.bot.get_file(update.message.voice.file_id)
        path=f"v_{uid}.ogg"
        await file.download_to_drive(path)
        with open(path,"rb") as f:
            trans=await client.audio.transcriptions.create(model="whisper-1",file=f)
            user_prompt=trans.text
        os.remove(path)
        await msg.delete()
    else:
        user_prompt=update.message.text

    if uid not in user_demo_done:
        wait_msg=await update.message.reply_text("🎶 *Generating your demo...*",parse_mode="Markdown")
        prompt=f"Write 2 song lyrics. Language: {data['language']}, Theme: {data['theme']}, Genre: {data['genre']}. Story: {user_prompt}"
        try:
            res=await client.chat.completions.create(model="gpt-4o-mini",messages=[{"role":"user","content":prompt}])
            lyrics=res.choices[0].message.content
            await wait_msg.edit_text(f"✅ *Demo Ready!*\n\n{lyrics}\n\n💳 Full version available after purchase.",parse_mode="Markdown")
            user_demo_done.add(uid)
        except Exception as e:
            await wait_msg.edit_text(f"❌ Error: {e}")
    else:
        keyboard=[
            [InlineKeyboardButton(f"Buy 1 song ⭐ {BUY_OPTIONS['1']}",callback_data="buy_1")],
            [InlineKeyboardButton(f"Buy 5 songs ⭐ {BUY_OPTIONS['5']}",callback_data="buy_5")],
            [InlineKeyboardButton(f"Buy 25 songs ⭐ {BUY_OPTIONS['25']}",callback_data="buy_25")]
        ]
        await update.message.reply_text("🎵 Choose purchase option:",reply_markup=InlineKeyboardMarkup(keyboard))

# ---------- HELP ----------
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id
    await update.message.reply_text(t(uid,"help_text"))

# ---------- MAIN ----------
def main():
    app=ApplicationBuilder().token(TOKEN).build()
    app.add_error_handler(error_handler)
    app.add_handler(CommandHandler("start",start))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT | filters.VOICE,handle_input))
    app.add_handler(CommandHandler("help",help_command))
    logger.info("MusicAi bot started")
    app.run_polling(drop_pending_updates=True)

if __name__=="__main__":
    main()