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
user_state = {}        # Хранение выбора пользователя
user_demo_done = {}    # Флаг, был ли у пользователя демо
user_balance = {}      # Баланс пользователя
user_last_song = {}    # Последняя демо/текст песни

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
        "en": "Choose occasion:",
        "ru": "Выбери повод:",
        "pl": "Wybierz okazję:",
        "de": "Anlass auswählen:",
        "es": "Elige ocasión:",
        "fr": "Choisissez l’occasion:",
        "uk": "Вибери привід:",
    },
    "ask_custom": {
        "en": "✍️ Write your custom occasion:",
        "ru": "✍️ Напиши свой повод:",
        "pl": "✍️ Napisz własną okazję:",
        "de": "✍️ Schreibe deinen eigenen Anlass:",
        "es": "✍️ Escribe tu ocasión personalizada:",
        "fr": "✍️ Écris ta propre occasion:",
        "uk": "✍️ Напиши свій привід:",
    },
    "choose_genre": {
        "en": "Choose genre:",
        "ru": "Выбери жанр:",
        "pl": "Wybierz gatunek:",
        "de": "Genre auswählen:",
        "es": "Elige el género:",
        "fr": "Choisissez le genre:",
        "uk": "Вибери жанр:",
    },
    "write_text": {
        "en": "🎤 Now write everything about the song:\n- Names\n- Stories\n- Mood\n\nSend me your text 👇",
        "ru": "🎤 Теперь напиши всё о песне:\n- Имена\n- Истории\n- Настроение\n\nОтправь текст 👇",
        "pl": "🎤 Teraz napisz wszystko o piosence:\n- Imiona\n- Historie\n- Nastrój\n\nWyślij tekst 👇",
        "de": "🎤 Schreibe jetzt alles über den Song:\n- Namen\n- Geschichten\n- Stimmung\n\nSende mir deinen Text 👇",
        "es": "🎤 Ahora escribe todo sobre la canción:\n- Nombres\n- Historias\n- Emoción\n\nEnvíame tu texto 👇",
        "fr": "🎤 Écris maintenant tout sur la chanson:\n- Noms\n- Histoires\n- Ambiance\n\nEnvoie-moi ton texte 👇",
        "uk": "🎤 Тепер напиши все про пісню:\n- Імена\n- Історії\n- Настрій\n\nНадішли текст 👇",
    },
    "wrong_order": {
        "en": "Please press /start and follow the buttons 🙂",
        "ru": "Пожалуйста, нажми /start и следуй кнопкам 🙂",
        "pl": "Naciśnij /start i postępuj zgodно z przyciskами 🙂",
        "de": "Bitte drücke /start und folge den Schritten 🙂",
        "es": "Pulsa /start y sigue los botones 🙂",
        "fr": "Appuie sur /start et suis les boutons 🙂",
        "uk": "Будь ласка, натисни /start та дотримуйся кнопок 🙂",
    },
    "demo": {
        "en": "✅ Got it!\n\n🎶 *Demo song preview*",
        "ru": "✅ Готово!\n\n🎶 *Демо-версия песни*",
        "pl": "✅ Gotowe!\n\n🎶 *Wersja demo piosenki*",
        "de": "✅ Fertig!\n\n🎶 *Demo-Version des Songs*",
        "es": "✅ Listo!\n\n🎶 *Versión demo de la canción*",
        "fr": "✅ Prêt!\n\n🎶 *Version démo de la chanson*",
        "uk": "✅ Готово!\n\n🎶 *Демо-версія пісні*",
    },
    "themes": {
        "en": ["❤️ Love", "😄 Funny", "🎉 Celebration", "😢 Sad", "💍 Wedding", "🎼 Classic", "✍️ Custom", "🇵🇱 Disco Polo"],
        "ru": ["❤️ Любовь", "😄 Смешная", "🎉 Праздник", "😢 Грусть", "💍 Свадьба", "🎼 Классика", "✍️ Свой вариант", "🇵🇱 Disco Polo"],
        "pl": ["❤️ Miłość", "😄 Śmieszna", "🎉 Święto", "😢 Smutek", "💍 Ślub", "🎼 Klasyka", "✍️ Własny", "🇵🇱 Disco Polo"],
        "de": ["❤️ Liebe", "😄 Lustig", "🎉 Feier", "😢 Traurig", "💍 Hochzeit", "🎼 Klassik", "✍️ Eigenes", "🇵🇱 Disco Polo"],
        "es": ["❤️ Amor", "😄 Divertida", "🎉 Celebración", "😢 Triste", "💍 Boda", "🎼 Clásica", "✍️ Personalizada", "🇵🇱 Disco Polo"],
        "fr": ["❤️ Amour", "😄 Drôle", "🎉 Fête", "😢 Tristesse", "💍 Mariage", "🎼 Classique", "✍️ Personnalisé", "🇵🇱 Disco Polo"],
        "uk": ["❤️ Любов", "😄 Кумедна", "🎉 Свято", "😢 Смуток", "💍 Весілля", "🎼 Класика", "✍️ Свій варіант", "🇵🇱 Disco Polo"],
    },
    "menu": {
        "en": ["New Song", "Current Song", "Buy Songs", "Balance", "Help"],
        "ru": ["Новая песня", "Текущая песня", "Купить песни", "Баланс", "Помощь"],
        "pl": ["Nowa piosenka", "Aktualna piosenka", "Kup piosenki", "Saldo", "Pomoc"],
        "de": ["Neues Lied", "Aktuelles Lied", "Songs kaufen", "Kontostand", "Hilfe"],
        "es": ["Nueva canción", "Canción actual", "Comprar canciones", "Saldo", "Ayuda"],
        "fr": ["Nouvelle chanson", "Chanson actuelle", "Acheter chansons", "Solde", "Aide"],
        "uk": ["Нова пісня", "Поточна пісня", "Купити пісні", "Баланс", "Допомога"],
    }
}

def t(uid, key):
    lang = user_state.get(uid, {}).get("language", "en")
    return TEXTS.get(key, {}).get(lang, TEXTS[key]["en"])

def get_menu(uid):
    labels = TEXTS["menu"].get(user_state.get(uid, {}).get("language", "en"), TEXTS["menu"]["en"])
    keyboard = [[InlineKeyboardButton(l, callback_data=f"menu_{i}")] for i, l in enumerate(labels)]
    return InlineKeyboardMarkup(keyboard)

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
            TEXTS["choose_language"]["en"],
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # --- Язык ---
    elif query.data.startswith("lang_"):
        user_state.setdefault(uid, {})
        user_state[uid]["language"] = query.data[5:]
        lang = user_state[uid]["language"]
        themes = TEXTS["themes"][lang]
        keyboard = [[InlineKeyboardButton(theme, callback_data=f"theme_{i}")] for i, theme in enumerate(themes)]
        await query.edit_message_text(
            t(uid, "choose_theme"),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # --- Тема ---
    elif query.data.startswith("theme_"):
        user_state.setdefault(uid, {})
        idx = int(query.data.split("_")[1])
        lang = user_state[uid]["language"]
        selected_theme = TEXTS["themes"][lang][idx]

        if idx == 6:  # Custom
            user_state[uid]["theme"] = None
            await query.edit_message_text(t(uid, "ask_custom"))
        else:
            user_state[uid]["theme"] = selected_theme
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

    # --- Жанр ---
    elif query.data.startswith("genre_"):
        user_state.setdefault(uid, {})
        user_state[uid]["genre"] = query.data[6:]

        # Демо или полный трек
        if not user_demo_done.get(uid, False):
            user_demo_done[uid] = True
            demo_text = "🎵 *Demo Song (1 min)* — first time only!"
        else:
            demo_text = "🎵 Full song available after purchase 💳"

        user_last_song[uid] = f"{demo_text}\n\nGenre: {user_state[uid]['genre']}"
        await query.edit_message_text(
            f"{demo_text}\n\n{t(uid,'write_text')}",
            reply_markup=get_menu(uid),
            parse_mode="Markdown"
        )

    # --- Меню ---
    elif query.data.startswith("menu_"):
        idx = int(query.data.split("_")[1])

        if idx == 0:  # New Song
            user_state.pop(uid, None)
            await query.edit_message_text("Starting new song...", reply_markup=None)
            await start(update, context)
        elif idx == 1:  # Current Song
            last = user_last_song.get(uid, "No song yet.")
            await query.edit_message_text(f"🎶 Current song:\n{last}", reply_markup=get_menu(uid))
        elif idx == 2:  # Buy Songs
            await query.edit_message_text(
                "💳 Buy songs:\n1 song — 250 stars\n5 songs — 1000 stars\n25 songs — 5000 stars",
                reply_markup=get_menu(uid)
            )
        elif idx == 3:  # Balance
            bal = user_balance.get(uid, 0)
            await query.edit_message_text(f"💰 Your balance: {bal} stars", reply_markup=get_menu(uid))
        elif idx == 4:  # Help
            await update.message.reply_text(
                "📝 Rules:\n- Demo only first time\n- Any changes require new generation\n- Prices: 1 song 250 stars, 5 songs 1000 stars\n...",
                reply_markup=get_menu(uid)
            )

# ---------- ТЕКСТ ----------
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id
    text = update.message.text

    if uid in user_state and user_state[uid].get("theme") is None:
        # Custom theme
        user_state[uid]["theme"] = text
        keyboard = [
            [InlineKeyboardButton("Pop", callback_data="genre_pop")],
            [InlineKeyboardButton("Rap / Hip-Hop", callback_data="genre_rap")],
            [InlineKeyboardButton("Rock", callback_data="genre_rock")],
            [InlineKeyboardButton("Club", callback_data="genre_club")],
            [InlineKeyboardButton("Classical", callback_data="genre_classic")],
            [InlineKeyboardButton("Disco Polo", callback_data="genre_disco")],
        ]
        await update.message.reply_text(
            t(uid, "choose_genre"),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if uid not in user_state or "theme" not in user_state[uid] or "genre" not in user_state[uid]:
        await update.message.reply_text(t(uid, "wrong_order"))
        return

    data = user_state[uid]
    idea = text

    # Сохраняем последнюю песню
    if not user_demo_done.get(uid, False):
        user_demo_done[uid] = True
        demo_text = "✅ Demo song preview (first time only)"
    else:
        demo_text = "✅ Full song ready — available after purchase"

    user_last_song[uid] = f"{demo_text}\nLanguage: {data['language']}\nOccasion: {data['theme']}\nGenre: {data['genre']}\nIdea: {idea[:80]}..."

    await update.message.reply_text(
        user_last_song[uid],
        reply_markup=get_menu(uid)
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