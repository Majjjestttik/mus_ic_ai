# -*- coding: utf-8 -*-

import os
import logging
import sys
import aiohttp
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters, PreCheckoutQueryHandler
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
    raise RuntimeError("BOT_TOKEN or PIAPI_KEY not set")

# -------------------- СОСТОЯНИЯ --------------------
users = {}  # хранит выбранный язык, тему, жанр
demo_done = set()  # кто получил демо
user_songs = {}  # баланс песен у пользователя

# -------------------- ЦЕНЫ --------------------
PRICES = {
    "1": 250,
    "5": 1000,
    "25": 4000
}

# -------------------- ТЕКСТЫ --------------------
TEXT = {
    "start": {
        "en": "🎵 *MusicAi*\n\nI create songs using AI.\n\nPress START 👇",
        "ru": "🎵 *MusicAi*\n\nЯ создаю песни с помощью ИИ.\n\nНажми START 👇",
        "pl": "🎵 *MusicAi*\n\nTworzę piosenki AI.\n\nNaciśnij START 👇",
        "de": "🎵 *MusicAi*\n\nIch erstelle Songs mit KI.\n\nDrücke START 👇",
        "es": "🎵 *MusicAi*\n\nCreo canciones con IA.\n\nPulsa START 👇",
        "fr": "🎵 *MusicAi*\n\nJe crée des chansons avec l’IA.\n\nAppuie sur START 👇",
        "uk": "🎵 *MusicAi*\n\nЯ створюю пісні за допомогою ІІ.\n\nНатисни START 👇"
    },
    "choose_language": {
        "en": "Choose language:", "ru": "Выбери язык:", "pl": "Wybierz język:",
        "de": "Sprache auswählen:", "es": "Elige idioma:", "fr": "Choisissez la langue:", "uk": "Вибери мову:"
    },
    "choose_theme": {
        "en": "Choose theme:", "ru": "Выбери тему:", "pl": "Wybierz temat:",
        "de": "Wähle ein Thema:", "es": "Elige tema:", "fr": "Choisissez un thème:", "uk": "Вибери тему:"
    },
    "choose_genre": {
        "en": "Choose genre:", "ru": "Выбери жанр:", "pl": "Wybierz gatunek:",
        "de": "Wähle Genre:", "es": "Elige género:", "fr": "Choisissez un genre:", "uk": "Вибери жанр:"
    },
    "describe": {
        "en": "✍️ *Describe the song*\n- Who is it for?\n- Story / event\n- Mood & emotions\n💬 Or send a voice message",
        "ru": "✍️ *Опиши песню*\n- Кому посвящается?\n- История / событие\n- Настроение и эмоции\n💬 Или отправь голосовое сообщение",
        "pl": "✍️ *Opisz piosenkę*\n- Dla kogo?\n- Historia / wydarzenie\n- Nastrój i emocje\n💬 Lub wyślij wiadomość głosową",
        "de": "✍️ *Beschreibe das Lied*\n- Für wen?\n- Geschichte / Ereignis\n- Stimmung & Gefühle\n💬 Oder Sprachnachricht",
        "es": "✍️ *Describe la canción*\n- Para quién?\n- Historia / evento\n- Estado de ánimo y emociones\n💬 O envía un mensaje de voz",
        "fr": "✍️ *Décris la chanson*\n- Pour qui?\n- Histoire / événement\n- Ambiance et émotions\n💬 Ou envoie un message vocal",
        "uk": "✍️ *Опиши пісню*\n- Кому присвячена?\n- Історія / подія\n- Настрій та емоції\n💬 Або надішли голосове повідомлення"
    },
    "demo": {
        "en": "🎧 *Demo version (1 time only)*",
        "ru": "🎧 *Демо (только один раз)*",
        "pl": "🎧 *Demo (tylko raz)*",
        "de": "🎧 *Demo (nur einmal)*",
        "es": "🎧 *Demo (solo una vez)*",
        "fr": "🎧 *Demo (une seule fois)*",
        "uk": "🎧 *Демо (тільки один раз)*"
    },
    "buy_confirm": {
        "en": "⚠️ *Confirmation*\nYou are about to spend ⭐ {stars}.\nRefunds are NOT possible.\nAre you sure?",
        "ru": "⚠️ *Подтверждение*\nВы собираетесь потратить ⭐ {stars}.\nВозврата нет.\nВы уверены?",
        "pl": "⚠️ *Potwierdzenie*\nWydałeś ⭐ {stars}.\nBrak zwrotu.\nJesteś pewien?",
        "de": "⚠️ *Bestätigung*\nDu gibst ⭐ {stars} aus.\nKeine Rückerstattung.\nBist du sicher?",
        "es": "⚠️ *Confirmación*\nVas a gastar ⭐ {stars}.\nNo hay reembolso.\n¿Estás seguro?",
        "fr": "⚠️ *Confirmation*\nVous dépensez ⭐ {stars}.\nPas de remboursement.\nÊtes-vous sûr?",
        "uk": "⚠️ *Підтвердження*\nВи витрачаєте ⭐ {stars}.\nПовернення неможливе.\nВи впевнені?"
    },
    "paid": {
        "en": "✅ Payment successful!\nYou can now generate full songs 🎶",
        "ru": "✅ Оплата прошла!\nТеперь можно генерировать полные песни 🎶",
        "pl": "✅ Płatność zakończona!\nMożesz generować pełne piosenki 🎶",
        "de": "✅ Zahlung erfolgreich!\nJetzt volle Songs generieren 🎶",
        "es": "✅ Pago exitoso!\nAhora puedes generar canciones completas 🎶",
        "fr": "✅ Paiement réussi!\nVous pouvez générer des chansons complètes 🎶",
        "uk": "✅ Оплата пройшла!\nТепер можна генерувати повні пісні 🎶"
    },
    "error": {
        "en": "⚠️ Temporary error. Please try again later.",
        "ru": "⚠️ Временная ошибка. Попробуйте позже.",
        "pl": "⚠️ Błąd tymczasowy. Spróbuj później.",
        "de": "⚠️ Vorübergehender Fehler. Bitte später erneut.",
        "es": "⚠️ Error temporal. Intenta más tarde.",
        "fr": "⚠️ Erreur temporaire. Réessayez plus tard.",
        "uk": "⚠️ Тимчасова помилка. Спробуйте пізніше."
    },
    "help": {
        "en": "💡 Help: Bot generates songs using AI. Use /start to begin and follow instructions.",
        "ru": "💡 Помощь: Бот генерирует песни с помощью ИИ. Используй /start и следуй инструкциям.",
        "pl": "💡 Pomoc: Bot tworzy piosenki AI. Użyj /start i postępuj zgodnie z instrukcjami.",
        "de": "💡 Hilfe: Bot erstellt Songs mit KI. Nutze /start und folge den Anweisungen.",
        "es": "💡 Ayuda: Bot genera canciones con IA. Usa /start y sigue las instrucciones.",
        "fr": "💡 Aide: Le bot génère des chansons avec IA. Utilise /start et suis les instructions.",
        "uk": "💡 Допомога: Бот генерує пісні за допомогою ІІ. Використовуй /start і слідуй інструкціям."
    }
}

def t(uid, key):
    lang = users.get(uid, {}).get("lang", "en")
    return TEXT[key].get(lang, TEXT[key]["en"])

# -------------------- PiAPI --------------------
async def generate_song(prompt: str):
    url = "https://api.piapi.ai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {PIAPI_KEY}",
        "Content-Type": "application/json"
    }
    payload = {"model": "pi-music", "messages": [{"role": "user", "content": prompt}]}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=60) as r:
                data = await r.json()
                return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"PiAPI error: {e}")
        return None

# -------------------- HANDLERS --------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton("▶️ START", callback_data="start")]]
    await update.message.reply_text(TEXT["start"]["en"], reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

    # -------- START --------
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

    # -------- LANGUAGE --------
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

    # -------- THEME --------
    elif q.data.startswith("theme_"):
        users[uid]["theme"] = q.data[6:]
        kb = [
            [InlineKeyboardButton("Pop", callback_data="genre_pop"),
             InlineKeyboardButton("Rap / Hip-Hop", callback_data="genre_rap")],
            [InlineKeyboardButton("Rock", callback_data="genre_rock"),
             InlineKeyboardButton("Club", callback_data="genre_club")],
            [InlineKeyboardButton("Classical", callback_data="genre_classical")]
        ]
        await q.edit_message_text(t(uid, "choose_genre"), reply_markup=InlineKeyboardMarkup(kb))

    # -------- GENRE --------
    elif q.data.startswith("genre_"):
        users[uid]["genre"] = q.data[6:]
        await q.edit_message_text(t(uid, "describe"), parse_mode="Markdown")

# -------- USER INPUT (TEXT / VOICE) --------
async def user_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in users or "genre" not in users[uid]:
        await update.message.reply_text("Please press /start first.")
        return

    data = users[uid]
    text = update.message.text or "Voice description received"

    prompt = f"Language: {data['lang']}\nTheme: {data['theme']}\nGenre: {data['genre']}\nDescription: {text}"

    # -------- DEMO --------
    if uid not in demo_done:
        demo_done.add(uid)
        msg = await update.message.reply_text("⏳ *Generating demo...*", parse_mode="Markdown")
        song = await generate_song(prompt)
        if song:
            await msg.edit_text(f"{TEXT['demo'][data['lang']]}\n\n{song[:3500]}", parse_mode="Markdown")
        else:
            await msg.edit_text(TEXT["error"][data['lang']])
        return

    # -------- FULL SONG --------
    balance = user_songs.get(uid, 0)
    if balance <= 0:
        await update.message.reply_text("⚠️ You have no songs left. Please top up your balance via Telegram Stars.")
        return

    # Снимаем 1 песню
    user_songs[uid] -= 1
    msg = await update.message.reply_text("⏳ *Generating full song...*", parse_mode="Markdown")
    song = await generate_song(prompt)
    if song:
        await msg.edit_text(song[:3500], parse_mode="Markdown")
    else:
        await msg.edit_text(TEXT["error"][data['lang']])

# -------------------- HELP --------------------
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await update.message.reply_text(t(uid, "help"))

# -------------------- MAIN --------------------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT | filters.VOICE, user_input))
    app.add_handler(CommandHandler("help", help_command))

    logger.info("MusicAi bot started")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()