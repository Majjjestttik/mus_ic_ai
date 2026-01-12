# -*- coding: utf-8 -*-

import os
import logging
import sys
import aiohttp
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
    PreCheckoutQueryHandler
)

# -------------------- ЛОГИ --------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("MusicAi")

# -------------------- ENV --------------------
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
PIAPI_KEY = os.getenv("PIAPI_KEY")
OWNER_ID = int(os.getenv("OWNER_TG_ID", "0"))

if not BOT_TOKEN or not PIAPI_KEY:
    raise RuntimeError("ENV variables not set")

# -------------------- STATE --------------------
users = {}
demo_used = set()

# -------------------- ЦЕНЫ (STARS) --------------------
PRICES = {
    "1": 250,
    "5": 1000,
    "25": 4000
}

# -------------------- ТЕКСТЫ --------------------
TEXTS = {
    "start": {
        "en": "🎵 *MusicAi*\n\nI create a full song in 5 minutes.\nLyrics, mood and style — personalised.\n\nPress START 👇",
        "ru": "🎵 *MusicAi*\n\nЯ создаю полноценную песню за 5 минут.\nТекст, настроение и стиль — персонально.\n\nНажми START, чтобы начать 👇",
        "pl": "🎵 *MusicAi*\n\nTworzę pełną piosenkę w 5 minut.\nTekst, klimat i styl — personalnie.\n\nNaciśnij START, aby rozpocząć 👇",
        "de": "🎵 *MusicAi*\n\nIch erstelle einen vollständigen Song in 5 Minuten.\nText, Stimmung und Stil — personalisiert.\n\nDrücke START, um zu beginnen 👇",
        "es": "🎵 *MusicAi*\n\nCreo una canción completa en 5 minutos.\nLetra, emoción y estilo — personalizados.\n\nPulsa START para comenzar 👇",
        "fr": "🎵 *MusicAi*\n\nJe crée une chanson complète en 5 minutes.\nParoles, ambiance et style — personnalisés.\n\nAppuie sur START pour commencer 👇",
        "uk": "🎵 *MusicAi*\n\nЯ створюю повноцінну пісню за 5 хвилин.\nТекст, настрій та стиль — персонально.\n\nНатисни START, щоб почати 👇"
    },
    "lang": {
        "en": "Choose language:",
        "ru": "Выбери язык:",
        "pl": "Wybierz język:",
        "de": "Sprache auswählen:",
        "es": "Elige idioma:",
        "fr": "Choisissez la langue:",
        "uk": "Вибери мову:"
    },
    "theme": {
        "en": "Choose theme:",
        "ru": "Выбери тему:",
        "pl": "Wybierz temat:",
        "de": "Wähle ein Thema:",
        "es": "Elige tema:",
        "fr": "Choisissez un thème:",
        "uk": "Вибери тему:"
    },
    "genre": {
        "en": "Choose genre:",
        "ru": "Выбери жанр:",
        "pl": "Wybierz gatunek:",
        "de": "Wähle Genre:",
        "es": "Elige género:",
        "fr": "Choisissez un genre:",
        "uk": "Вибери жанр:"
    },
    "describe": {
        "en": "🎤 Now the most important part!\nWrite step by step:\n- Who is the song for?\n- Story / event\n- Mood & emotions\n💬 Or send a voice message",
        "ru": "🎤 Теперь самое главное!\nНапиши по пунктам:\n- Кому посвящается песня?\n- Расскажи историю или событие\n- Настроение и эмоции\n💬 Или отправь голосовое сообщение.",
        "pl": "🎤 Teraz najważniejsze!\nNapisz krok po kroku:\n- Dla kogo jest piosenka?\n- Opowiedz historię lub wydarzenie\n- Nastrój i emocje\n💬 Lub wyślij wiadomość głosową.",
        "de": "🎤 Jetzt das Wichtigste!\nSchreibe Schritt für Schritt:\n- Für wen ist das Lied?\n- Erzähle ihre Geschichte oder Ereignis\n- Stimmung und Gefühle\n💬 Oder sende eine Sprachnachricht.",
        "es": "🎤 Ahora lo más importante!\nEscribe paso a paso:\n- Para quién es la canción?\n- Cuenta su historia o evento\n- Estado de ánimo y emociones\n💬 O envía un mensaje de voz.",
        "fr": "🎤 Maintenant le plus important!\nÉcris étape par étape:\n- Pour qui est la chanson?\n- Raconte l’histoire ou l’événement\n- Ambiance et émotions\n💬 Ou envoie un message vocal.",
        "uk": "🎤 Тепер найголовніше!\nНапиши по пунктах:\n- Кому присвячена пісня?\n- Розкажи історію або подію\n- Настрій та емоції\n💬 Або надішли голосове повідомлення."
    },
    "demo": "🎧 *Demo version (1 time only)*",
    "buy_confirm": "⚠️ *Confirmation*\n\nYou are about to spend ⭐ {stars}.\nRefunds are NOT possible.\n\nAre you sure?",
    "paid": "✅ Payment successful!\nYou can now generate full songs 🎶",
    "error": "⚠️ Temporary error. Please try again later.",
    "help": {
        "en": "Help: Rules and instructions for using the MusicAi bot.",
        "ru": "Помощь: Правила и инструкции для MusicAi бота.",
        "pl": "Pomoc: Zasady i instrukcje dla bota MusicAi.",
        "de": "Hilfe: Regeln und Anleitungen für MusicAi Bot.",
        "es": "Ayuda: Reglas e instrucciones para el bot MusicAi.",
        "fr": "Aide: Règles et instructions pour le bot MusicAi.",
        "uk": "Допомога: Правила та інструкції для MusicAi бота."
    }
}

# -------------------- ВСПОМОГАТЕЛЬНЫЕ --------------------
def t(uid, key):
    lang = users.get(uid, {}).get("lang", "en")
    return TEXTS[key].get(lang, TEXTS[key]["en"]) if key in TEXTS else key

def wide_buttons(labels_callbacks):
    return [[InlineKeyboardButton(label, callback_data=cb)] for label, cb in labels_callbacks]

# -------------------- PIAPI --------------------
async def generate_song(prompt: str):
    url = "https://api.piapi.ai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {PIAPI_KEY}", "Content-Type": "application/json"}
    payload = {"model": "pi-music", "messages": [{"role": "user", "content": prompt}]}
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=60) as r:
                data = await r.json()
                return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"PiAPI Error: {e}")
        return None

# -------------------- START --------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton("▶️ START", callback_data="start")]]
    await update.message.reply_text(t(update.effective_user.id, "start"),
                                    reply_markup=InlineKeyboardMarkup(kb),
                                    parse_mode="Markdown")

# -------------------- BUTTONS --------------------
async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

    if q.data == "start":
        users[uid] = {}
        kb = wide_buttons([
            ("English 🇬🇧", "lang_en"),
            ("Русский 🇷🇺", "lang_ru"),
            ("Polski 🇵🇱", "lang_pl"),
            ("Deutsch 🇩🇪", "lang_de"),
            ("Español 🇪🇸", "lang_es"),
            ("Français 🇫🇷", "lang_fr"),
            ("Українська 🇺🇦", "lang_uk")
        ])
        await q.edit_message_text(t(uid, "lang"), reply_markup=InlineKeyboardMarkup(kb))

    elif q.data.startswith("lang_"):
        users[uid]["lang"] = q.data[5:]
        kb = wide_buttons([
            ("Love ❤️", "theme_love"),
            ("Funny 😄", "theme_fun"),
            ("Sad 😢", "theme_sad"),
            ("Wedding 💍", "theme_wedding"),
            ("Custom ✏️", "theme_custom"),
            ("Disco Polo 🎶", "theme_disco")
        ])
        await q.edit_message_text(t(uid, "theme"), reply_markup=InlineKeyboardMarkup(kb))

    elif q.data.startswith("theme_"):
        users[uid]["theme"] = q.data[6:]
        kb = wide_buttons([
            ("Pop", "genre_pop"),
            ("Rap / Hip-Hop", "genre_rap"),
            ("Rock", "genre_rock"),
            ("Club", "genre_club"),
            ("Classical", "genre_classical"),
            ("Disco Polo 🎶", "genre_disco")
        ])
        await q.edit_message_text(t(uid, "genre"), reply_markup=InlineKeyboardMarkup(kb))

    elif q.data.startswith("genre_"):
        users[uid]["genre"] = q.data[6:]
        await q.edit_message_text(t(uid, "describe"), parse_mode="Markdown")

# -------------------- TEXT/VOICE INPUT --------------------
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
        song = await generate_song(prompt)
        if song:
            await msg.edit_text(f"{TEXTS['demo']}\n\n{song[:3500]}", parse_mode="Markdown")
        else:
            await msg.edit_text(TEXTS["error"])
        return

    kb = wide_buttons([
        (f"⭐ 1 song — 250", "buy_1"),
        (f"⭐ 5 songs — 1000", "buy_5"),
        (f"⭐ 25 songs — 4000", "buy_25")
    ])
    await update.message.reply_text("💳 Buy full version to continue:", reply_markup=InlineKeyboardMarkup(kb))

# -------------------- PAYMENTS --------------------
async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(TEXTS["paid"])
    if OWNER_ID:
        try:
            await context.bot.send_message(OWNER_ID,
                                           f"⭐ Payment received from @{update.effective_user.username} ({update.effective_user.id})")
        except:
            pass

# -------------------- HELP --------------------
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await update.message.reply_text(TEXTS["help"].get(users.get(uid, {}).get("lang", "en"), TEXTS["help"]["en"]))

# -------------------- MAIN --------------------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT | filters.VOICE, user_input))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(PreCheckoutQueryHandler(pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))

    logger.info("MusicAi bot started")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()