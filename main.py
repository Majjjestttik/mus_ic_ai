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
user_state = {}        # Состояния пользователя
user_demo_done = {}    # Флаг демо
user_balance = {}      # Баланс
user_last_song = {}    # Последняя песня

# ---------- ЦЕНЫ ----------
BUY_OPTIONS = {
    "1_song": 250,
    "5_songs": 1000,
    "25_songs": 4000
}

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
        "en": "Choose language:",
        "ru": "Выбери язык:",
        "pl": "Wybierz język:",
        "de": "Sprache auswählen:",
        "es": "Elige idioma:",
        "fr": "Choisissez la langue:",
        "uk": "Вибери мову:",
    },
    "choose_theme": {
        "en": "Choose theme:",
        "ru": "Выбери тему:",
        "pl": "Wybierz temat:",
        "de": "Wähle ein Thema:",
        "es": "Elige tema:",
        "fr": "Choisissez un thème:",
        "uk": "Вибери тему:",
    },
    "choose_genre": {
        "en": "Choose genre:",
        "ru": "Выбери жанр:",
        "pl": "Wybierz gatunek:",
        "de": "Wähle Genre:",
        "es": "Elige género:",
        "fr": "Choisissez un genre:",
        "uk": "Вибери жанр:",
    },
    "write_text": {
        "en": "🎤 Now the most important part!\n\nWrite everything about the song step by step:\n1️⃣ Who is it dedicated to?\n2️⃣ Tell a story about them, funny or important moments.\n3️⃣ If the song is about an event — what event?\n4️⃣ If it is about weather or nature — describe it.\n5️⃣ What do you want to convey with this track — love, joy, gratitude, fun etc.\n\n💬 If you don’t want to type — send a voice message, I will understand everything.",
        "ru": "🎤 Ну а теперь самое главное!\n\nНапиши всё о песне по пунктам:\n1️⃣ Кому посвящается песня?\n2️⃣ Расскажи историю о нём/ней, смешные или важные моменты.\n3️⃣ Если песня про мероприятие — что за событие?\n4️⃣ Если песня про погоду или природу — расскажи детали.\n5️⃣ Что хочется передать этим треком — любовь, радость, благодарность, угар и т.д.\n\n💬 Если лень писать — можешь отправить голосовое, я всё уловлю.",
        "pl": "🎤 Teraz najważniejsze!\n\nNapisz wszystko o piosence krok po kroku:\n1️⃣ Dla kogo jest dedykowana?\n2️⃣ Opowiedz historię o nim/niej, zabawne lub ważne momenty.\n3️⃣ Jeśli piosenka dotyczy wydarzenia — jakie?\n4️⃣ Jeśli o pogodzie lub przyrodzie — opisz.\n5️⃣ Co chcesz przekazać utworem — miłość, radość, wdzięczność, zabawę itd.\n\n💬 Jeśli nie chce Ci się pisać — wyślij wiadomość głosową, wszystko zrozumiem.",
        "de": "🎤 Jetzt das Wichtigste!\n\nSchreibe alles über das Lied Schritt für Schritt:\n1️⃣ Für wen ist es gedacht?\n2️⃣ Erzähle eine Geschichte über ihn/sie, lustige oder wichtige Momente.\n3️⃣ Wenn das Lied über ein Ereignis ist — welches?\n4️⃣ Wenn es um Wetter oder Natur geht — beschreibe es.\n5️⃣ Was möchtest du mit dem Song vermitteln — Liebe, Freude, Dankbarkeit, Spaß usw.\n\n💬 Wenn du nicht tippen willst — sende eine Sprachnachricht, ich verstehe alles.",
        "es": "🎤 Ahora lo más importante!\n\nEscribe todo sobre la canción paso a paso:\n1️⃣ ¿Para quién está dedicada?\n2️⃣ Cuenta una historia sobre esa persona, momentos divertidos o importantes.\n3️⃣ Si la canción es sobre un evento — ¿cuál?\n4️⃣ Si es sobre el clima o la naturaleza — descríbelo.\n5️⃣ Qué quieres transmitir con esta canción — amor, alegría, gratitud, diversión, etc.\n\n💬 Si no quieres escribir — envía un mensaje de voz, lo entenderé todo.",
        "fr": "🎤 Maintenant le plus important!\n\nÉcris tout sur la chanson étape par étape:\n1️⃣ À qui est-elle dédiée?\n2️⃣ Raconte une histoire sur cette personne, moments drôles ou importants.\n3️⃣ Si la chanson parle d’un événement — lequel?\n4️⃣ Si elle parle de météo ou nature — décris-la.\n5️⃣ Que veux-tu transmettre avec ce morceau — amour, joie, gratitude, fun etc.\n\n💬 Si tu ne veux pas écrire — envoie un message vocal, je comprendrai tout.",
        "uk": "🎤 Тепер найголовніше!\n\nНапиши все про пісню по пунктах:\n1️⃣ Кому присвячена пісня?\n2️⃣ Розкажи історію про нього/неї, смішні або важливі моменти.\n3️⃣ Якщо пісня про захід — що за подія?\n4️⃣ Якщо про погоду або природу — опиши.\n5️⃣ Що хочеш передати цим треком — любов, радість, вдячність, веселощі тощо.\n\n💬 Якщо не хочеш писати — надішли голосове, я все зрозумію."
    }
}

HELP_TEXTS = {
    "en": "Help:\nAll rules and FAQ as described above.\nYou can publish songs anywhere under your name or nickname.",
    "ru": "Помощь:\nВсе правила и ответы на частые вопросы.\nМожно публиковать песни в любой социальной сети под своим именем или псевдонимом.",
    "pl": "Pomoc:\nWszystkie zasady i FAQ.\nMożesz publikować piosenki w dowolnej sieci społecznościowej pod swoim imieniem lub pseudonimem.",
    "de": "Hilfe:\nAlle Regeln und FAQs.\nSongs können überall unter deinem Namen oder Nickname veröffentlicht werden.",
    "es": "Ayuda:\nTodas las reglas y preguntas frecuentes.\nPuedes publicar canciones en cualquier red social con tu nombre o seudónimo.",
    "fr": "Aide:\nToutes les règles et FAQ.\nVous pouvez publier des chansons sur n’importe quel réseau social sous votre nom ou pseudonyme.",
    "uk": "Допомога:\nУсі правила та відповіді на часті питання.\nМожна публікувати пісні в будь-якій соціальній мережі під своїм ім’ям або псевдонімом."
}

# ---------- ФУНКЦИИ ----------
def t(uid, key):
    lang = user_state.get(uid, {}).get("language", "en")
    return TEXTS.get(key, {}).get(lang, TEXTS[key]["en"])

def get_menu(uid):
    labels = TEXTS["menu"].get(user_state.get(uid, {}).get("language","en"), TEXTS["menu"]["en"])
    keyboard = [[InlineKeyboardButton(l, callback_data=f"menu_{i}")] for i, l in enumerate(labels)]
    return InlineKeyboardMarkup(keyboard)

# ---------- ОБРАБОТЧИК ОШИБОК ----------
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(msg="Exception while handling an update:", exc_info=context.error)
    if update and hasattr(update, "message") and update.message:
        await update.message.reply_text("❌ Something went wrong. Check logs.")

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

    # --- Старт ---
    if query.data == "start":
        user_state[uid] = {}
        keyboard = [
            [InlineKeyboardButton("English 🇬🇧", callback_data="lang_en")],
            [InlineKeyboardButton("Русский 🇷🇺", callback_data="lang_ru")],
            [InlineKeyboardButton("Polski 🇵🇱", callback_data="lang_pl")],
            [InlineKeyboardButton("Deutsch 🇩🇪", callback_data="lang_de")],
            [InlineKeyboardButton("Español 🇪🇸", callback_data="lang_es")],
            [InlineKeyboardButton("Français 🇫🇷", callback_data="lang_fr")],
            [InlineKeyboardButton("Українська 🇺🇦", callback_data="lang_uk")],
        ]
        await query.edit_message_text(
            t(uid, "choose_language"),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif query.data.startswith("menu_"):
        idx = int(query.data.split("_")[1])
        if idx == 4:  # Help
            lang = user_state.get(uid, {}).get("language","en")
            await query.edit_message_text(HELP_TEXTS.get(lang, HELP_TEXTS["en"]))

# ---------- MAIN ----------
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_error_handler(error_handler)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(buttons))

    logger.info("MusicAi bot started")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()