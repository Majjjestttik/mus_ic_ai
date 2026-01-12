# -*- coding: utf-8 -*-

import os
import logging
import sys
from openai import AsyncOpenAI
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters, PreCheckoutQueryHandler
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
OWNER_TG_ID = os.getenv("OWNER_TG_ID")  # твой @majjjestttik numeric id

if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN not set")
if not OPENAI_KEY:
    raise RuntimeError("OPENAI_API_KEY not set")
if not OWNER_TG_ID:
    raise RuntimeError("OWNER_TG_ID not set")

client = AsyncOpenAI(api_key=OPENAI_KEY)

# ---------- СОСТОЯНИЯ ----------
user_state = {}
user_demo_done = set()

# ---------- ЦЕНЫ В ЗВЁЗДАХ ----------
BUY_OPTIONS = {
    "1_song": 250,
    "5_songs": 1000,
    "25_songs": 4000
}

# ---------- ЛОКАЛИЗАЦИЯ ----------
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
        "en": "Choose language:", "ru": "Выбери язык:", "pl": "Wybierz język:", "de": "Sprache auswählen:",
        "es": "Elige idioma:", "fr": "Choisissez la langue:", "uk": "Вибери мову:"
    },
    "choose_theme": {
        "en": "Choose theme:", "ru": "Выбери тему:", "pl": "Wybierz temat:", "de": "Wähle ein Thema:",
        "es": "Elige tema:", "fr": "Choisissez un thème:", "uk": "Вибери тему:"
    },
    "choose_genre": {
        "en": "Choose genre:", "ru": "Выбери жанр:", "pl": "Wybierz gatunek:", "de": "Wähle Genre:",
        "es": "Elige género:", "fr": "Choisissez un genre:", "uk": "Вибери жанр:"
    },
    "write_text": {
        "en": "🎤 Now the most important part!\nWrite step by step:\n- Who is the song about?\n- Tell their story or event\n- Mood and feelings\n💬 Or send a voice message.",
        "ru": "🎤 Теперь самое главное!\nНапиши по пунктам:\n- Кому посвящается песня?\n- Расскажи историю или событие\n- Настроение и эмоции\n💬 Или отправь голосовое сообщение.",
        "pl": "🎤 Teraz najważniejsze!\nNapisz krok po kroku:\n- Dla kogo jest piosenka?\n- Opowiedz historię lub wydarzenie\n- Nastrój i emocje\n💬 Lub wyślij wiadomość głosową.",
        "de": "🎤 Jetzt das Wichtigste!\nSchreibe Schritt für Schritt:\n- Für wen ist das Lied?\n- Erzähle ihre Geschichte oder Ereignis\n- Stimmung und Gefühle\n💬 Oder sende eine Sprachnachricht.",
        "es": "🎤 Ahora lo más importante!\nEscribe paso a paso:\n- Para quién es la canción?\n- Cuenta su historia o evento\n- Estado de ánimo y emociones\n💬 O envía un mensaje de voz.",
        "fr": "🎤 Maintenant le plus important!\nÉcris étape par étape:\n- Pour qui est la chanson?\n- Raconte l’histoire ou l’événement\n- Ambiance et émotions\n💬 Ou envoie un message vocal.",
        "uk": "🎤 Тепер найголовніше!\nНапиши по пунктах:\n- Кому присвячена пісня?\n- Розкажи історію або подію\n- Настрій та емоції\n💬 Або надішли голосове повідомлення."
    },
    "help_text": {
        "en": "Help: Rules and usage instructions. You can use songs in any social network.",
        "ru": "Помощь: Правила и инструкции. Песни можно использовать в любых соцсетях.",
        "pl": "Pomoc: Zasady i instrukcje. Piosenki można wykorzystać w dowolnych sieciach społecznościowych.",
        "de": "Hilfe: Regeln und Anweisungen. Songs können in allen sozialen Netzwerken verwendet werden.",
        "es": "Ayuda: Reglas e instrucciones. Las canciones se pueden usar en cualquier red social.",
        "fr": "Aide: Règles et instructions. Les chansons peuvent être utilisées sur tous les réseaux sociaux.",
        "uk": "Допомога: Правила та інструкції. Пісні можна використовувати в будь-яких соцмережах."
    }
}

# ---------- ФУНКЦИИ ----------
def t(uid, key):
    lang = user_state.get(uid, {}).get("language", "en")
    return TEXTS.get(key, {}).get(lang, TEXTS[key]["en"])

# ---------- ОШИБКИ ----------
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

# ---------- START ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("▶️ START", callback_data="start")]]
    await update.message.reply_text(TEXTS["start"]["en"], reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# ---------- КНОПКИ ----------
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
        await query.edit_message_text(t(uid, "choose_language"), reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data.startswith("lang_"):
        user_state[uid]["language"] = query.data[5:]
        keyboard = [
            [InlineKeyboardButton("Love ❤️", callback_data="theme_love"),
             InlineKeyboardButton("Congratulations 🎉", callback_data="theme_congrats")],
            [InlineKeyboardButton("Funny 😄", callback_data="theme_fun"),
             InlineKeyboardButton("Sad 😢", callback_data="theme_sad")],
            [InlineKeyboardButton("Wedding 💍", callback_data="theme_wedding"),
             InlineKeyboardButton("Classical 🎼", callback_data="theme_classic")],
            [InlineKeyboardButton("Custom ✏️", callback_data="theme_custom"),
             InlineKeyboardButton("Disco Polo 🎶", callback_data="theme_disco")]
        ]
        await query.edit_message_text(t(uid, "choose_theme"), reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data.startswith("theme_"):
        user_state[uid]["theme"] = query.data[6:]
        keyboard = [
            [InlineKeyboardButton("Pop", callback_data="genre_pop"),
             InlineKeyboardButton("Rap / Hip-Hop", callback_data="genre_rap")],
            [InlineKeyboardButton("Rock", callback_data="genre_rock"),
             InlineKeyboardButton("Club", callback_data="genre_club")],
            [InlineKeyboardButton("Classical", callback_data="genre_classic")]
        ]
        await query.edit_message_text(t(uid, "choose_genre"), reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data.startswith("genre_"):
        user_state[uid]["genre"] = query.data[6:]
        await query.edit_message_text(t(uid, "write_text"), parse_mode="Markdown")

# ---------- ОБРАБОТКА ВВОДА ----------
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

    # ---------- DEMO или ПОКУПКА ----------
    if uid not in user_demo_done:
        wait_msg = await update.message.reply_text("🎶 *Generating your demo...*", parse_mode="Markdown")
        prompt = f"Write 2 song lyrics. Language: {data['language']}, Theme: {data['theme']}, Genre: {data['genre']}. Story: {user_prompt}"
        try:
            res = await client.chat.completions.create(model="gpt-4o-mini", messages=[{"role":"user","content":prompt}])
            lyrics = res.choices[0].message.content
            await wait_msg.edit_text(f"✅ *Demo Ready!*\n\n{lyrics}\n\n💳 Full version available after purchase.", parse_mode="Markdown")
            user_demo_done.add(uid)
        except Exception as e:
            await wait_msg.edit_text(f"❌ Error: {e}")
    else:
        # ---------- Покупка через звёзды Telegram ----------
        prices = [
            LabeledPrice(label="1 song", amount=BUY_OPTIONS["1_song"]*100),
            LabeledPrice(label="5 songs", amount=BUY_OPTIONS["5_songs"]*100),
            LabeledPrice(label="25 songs", amount=BUY_OPTIONS["25_songs"]*100)
        ]
        await update.message.reply_text("🎵 Choose purchase option (Telegram Stars only):")
        for price in prices:
            await context.bot.send_invoice(
                chat_id=uid,
                title=f"MusicAi - {price.label}",
                description=f"Purchase {price.label} with Telegram Stars",
                provider_token=os.getenv("PAYMENTS_PROVIDER_TOKEN"),
                currency="USD",  # Telegram показывает цену в звёздах автоматически
                prices=[price],
                payload=price.label
            )

# ---------- TELEGRAM PAYMENTS ----------
async def pre_checkout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    await query.answer(ok=True)

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    amount = update.message.successful_payment.total_amount / 100
    await context.bot.send_message(int(OWNER_TG_ID), text=f"Пользователь @{update.effective_user.username} купил песню на сумму {amount} {update.message.successful_payment.currency}")
    await update.message.reply_text("✅ Payment received! You can now generate your full song 🎶")

# ---------- HELP ----------
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await update.message.reply_text(t(uid, "help_text"))

# ---------- MAIN ----------
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_error_handler(error_handler)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT | filters.VOICE, handle_input))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(PreCheckoutQueryHandler(pre_checkout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))

    logger.info("MusicAi bot started")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()