# -*- coding: utf-8 -*-

import os
import sys
import json
import time
import logging
import sqlite3
import asyncio
from typing import Dict, Any, Optional

import aiohttp
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    BotCommand,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    PreCheckoutQueryHandler,
    ContextTypes,
    filters,
)

# -------------------- LOGS --------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("MusicAi")

# -------------------- ENV --------------------
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")          # для текста (лирики)
PIAPI_KEY = os.getenv("PIAPI_KEY")                # для "полной" генерации (piapi)
OWNER_ID = int(os.getenv("OWNER_TG_ID", "0"))     # твой числовой id (не @)

if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN not set")

# Можно запускать даже без OPENAI/PIAPI, но генерация будет выдавать ошибку в ответе пользователю.
# Поэтому не делаем raise, чтобы бот хотя бы стартовал.
if not OPENAI_KEY:
    logger.warning("OPENAI_API_KEY not set (lyrics demo will fail)")
if not PIAPI_KEY:
    logger.warning("PIAPI_KEY not set (full generation will fail)")

# -------------------- PRICES (Stars) --------------------
PRICES = {
    "1": 250,
    "5": 1000,
    "25": 4000
}

# -------------------- DB (songs balance + demo flag) --------------------
DB_PATH = "musicai.db"

def db_init():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            songs INTEGER NOT NULL DEFAULT 0,
            demo_used INTEGER NOT NULL DEFAULT 0,
            lang TEXT NOT NULL DEFAULT 'en'
        )
    """)
    con.commit()
    con.close()

def db_get_user(user_id: int) -> Dict[str, Any]:
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT user_id, songs, demo_used, lang FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    if not row:
        cur.execute("INSERT INTO users(user_id, songs, demo_used, lang) VALUES(?,?,?,?)", (user_id, 0, 0, "en"))
        con.commit()
        row = (user_id, 0, 0, "en")
    con.close()
    return {"user_id": row[0], "songs": row[1], "demo_used": bool(row[2]), "lang": row[3]}

def db_set_lang(user_id: int, lang: str):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("INSERT INTO users(user_id, songs, demo_used, lang) VALUES(?,?,?,?) "
                "ON CONFLICT(user_id) DO UPDATE SET lang=excluded.lang",
                (user_id, 0, 0, lang))
    con.commit()
    con.close()

def db_set_demo_used(user_id: int, used: bool):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("UPDATE users SET demo_used=? WHERE user_id=?", (1 if used else 0, user_id))
    con.commit()
    con.close()

def db_add_songs(user_id: int, add: int):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("UPDATE users SET songs = songs + ? WHERE user_id=?", (add, user_id))
    con.commit()
    con.close()

def db_take_song(user_id: int) -> bool:
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT songs FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    if not row or row[0] <= 0:
        con.close()
        return False
    cur.execute("UPDATE users SET songs = songs - 1 WHERE user_id=?", (user_id,))
    con.commit()
    con.close()
    return True

# -------------------- STATE (in-memory flow) --------------------
# Здесь только текущие выборы (язык/тема/жанр/кастом-тема/описание)
state: Dict[int, Dict[str, Any]] = {}
# временно хранить выбранный пакет до оплаты
pending_pack: Dict[int, str] = {}

# -------------------- LOCALIZATION --------------------
LANGS = ["en", "ru", "pl", "de", "es", "fr", "uk"]

TEXTS = {
    "start": {
        "en": "🎵 *MusicAi*\n\nI create songs using AI.\n\nPress START 👇",
        "ru": "🎵 *MusicAi*\n\nЯ создаю песни с помощью ИИ.\n\nНажми START 👇",
        "pl": "🎵 *MusicAi*\n\nTworzę piosenki z pomocą AI.\n\nNaciśnij START 👇",
        "de": "🎵 *MusicAi*\n\nIch erstelle Songs mit KI.\n\nDrücke START 👇",
        "es": "🎵 *MusicAi*\n\nCreo canciones con IA.\n\nPulsa START 👇",
        "fr": "🎵 *MusicAi*\n\nJe crée des chansons avec l’IA.\n\nAppuie sur START 👇",
        "uk": "🎵 *MusicAi*\n\nЯ створюю пісні за допомогою ШІ.\n\nНатисни START 👇",
    },
    "choose_language": {
        "en": "Choose language:",
        "ru": "Выбери язык:",
        "pl": "Wybierz język:",
        "de": "Sprache auswählen:",
        "es": "Elige idioma:",
        "fr": "Choisis la langue :",
        "uk": "Вибери мову:",
    },
    "choose_theme": {
        "en": "Choose theme:",
        "ru": "Выбери тему:",
        "pl": "Wybierz temat:",
        "de": "Wähle ein Thema:",
        "es": "Elige tema:",
        "fr": "Choisis un thème :",
        "uk": "Вибери тему:",
    },
    "choose_genre": {
        "en": "Choose genre (genres are in English):",
        "ru": "Выбери жанр (жанры на английском):",
        "pl": "Wybierz gatunek (gatunki po angielsku):",
        "de": "Wähle Genre (Genres auf Englisch):",
        "es": "Elige género (géneros en inglés):",
        "fr": "Choisis un genre (genres en anglais) :",
        "uk": "Вибери жанр (жанри англійською):",
    },
    "ask_custom_theme": {
        "en": "✏️ Write your custom theme (1–5 words):",
        "ru": "✏️ Напиши свою тему (1–5 слов):",
        "pl": "✏️ Napisz własny temat (1–5 słów):",
        "de": "✏️ Schreibe dein eigenes Thema (1–5 Wörter):",
        "es": "✏️ Escribe tu tema (1–5 palabras):",
        "fr": "✏️ Écris ton thème (1–5 mots) :",
        "uk": "✏️ Напиши свою тему (1–5 слів):",
    },
    "describe": {
        "en": (
            "✍️ *Describe the song*\n\n"
            "• Who is it for?\n"
            "• Tell their story / an event / situation\n"
            "• Mood & emotions\n"
            "• What do you want to say with this track?\n\n"
            "🎤 If you don’t want to type — send a voice message."
        ),
        "ru": (
            "✍️ *Опиши песню*\n\n"
            "• Кому посвящается?\n"
            "• История / событие / ситуация\n"
            "• Настроение и эмоции\n"
            "• Что хочешь передать этим треком?\n\n"
            "🎤 Если лень писать — отправь голосовое."
        ),
        "pl": (
            "✍️ *Opisz piosenkę*\n\n"
            "• Dla kogo?\n"
            "• Historia / wydarzenie / sytuacja\n"
            "• Nastrój i emocje\n"
            "• Co chcesz przekazać tym utworem?\n\n"
            "🎤 Jeśli nie chcesz pisać — wyślij głosówkę."
        ),
        "de": (
            "✍️ *Beschreibe den Song*\n\n"
            "• Für wen ist er?\n"
            "• Geschichte / Ereignis / Situation\n"
            "• Stimmung & Gefühle\n"
            "• Was willst du mit dem Track sagen?\n\n"
            "🎤 Wenn du nicht tippen willst — sende eine Sprachnachricht."
        ),
        "es": (
            "✍️ *Describe la canción*\n\n"
            "• ¿Para quién es?\n"
            "• Historia / evento / situación\n"
            "• Ánimo y emociones\n"
            "• ¿Qué quieres transmitir con este tema?\n\n"
            "🎤 Si no quieres escribir — envía un audio."
        ),
        "fr": (
            "✍️ *Décris la chanson*\n\n"
            "• Pour qui ?\n"
            "• Histoire / événement / situation\n"
            "• Ambiance & émotions\n"
            "• Que veux-tu transmettre avec ce titre ?\n\n"
            "🎤 Si tu ne veux pas écrire — envoie un vocal."
        ),
        "uk": (
            "✍️ *Опиши пісню*\n\n"
            "• Для кого вона?\n"
            "• Історія / подія / ситуація\n"
            "• Настрій та емоції\n"
            "• Що хочеш передати цим треком?\n\n"
            "🎤 Якщо не хочеш писати — надішли голосове."
        ),
    },
    "demo_header": {
        "en": "🎧 *Demo version (1 time only)*",
        "ru": "🎧 *Демо-версия (только 1 раз)*",
        "pl": "🎧 *Wersja demo (tylko 1 raz)*",
        "de": "🎧 *Demo-Version (nur 1 Mal)*",
        "es": "🎧 *Versión demo (solo 1 vez)*",
        "fr": "🎧 *Version démo (1 seule fois)*",
        "uk": "🎧 *Демо-версія (лише 1 раз)*",
    },
    "no_balance": {
        "en": "❌ You have no songs on balance.\nBuy a pack to continue 👇",
        "ru": "❌ У тебя нет песен на балансе.\nКупи пакет, чтобы продолжить 👇",
        "pl": "❌ Nie masz piosenek na saldzie.\nKup pakiet, aby kontynuować 👇",
        "de": "❌ Du hast keine Songs im Guthaben.\nKaufe ein Paket, um fortzufahren 👇",
        "es": "❌ No tienes canciones en el saldo.\nCompra un paquete para continuar 👇",
        "fr": "❌ Tu n’as aucune chanson sur le solde.\nAchète un pack pour continuer 👇",
        "uk": "❌ У тебе немає пісень на балансі.\nКупи пакет, щоб продовжити 👇",
    },
    "buy_title": {
        "en": "💳 Choose a pack (Telegram Stars):",
        "ru": "💳 Выбери пакет (Telegram Stars):",
        "pl": "💳 Wybierz pakiet (Telegram Stars):",
        "de": "💳 Wähle ein Paket (Telegram Stars):",
        "es": "💳 Elige un paquete (Telegram Stars):",
        "fr": "💳 Choisis un pack (Telegram Stars) :",
        "uk": "💳 Обери пакет (Telegram Stars):",
    },
    "confirm": {
        "en": "⚠️ *Confirmation*\n\nYou will spend ⭐ {stars}.\nRefunds are NOT possible.\n\nAre you sure?",
        "ru": "⚠️ *Подтверждение*\n\nТы потратишь ⭐ {stars}.\nВозврата НЕ будет.\n\nТы уверен?",
        "pl": "⚠️ *Potwierdzenie*\n\nWydasz ⭐ {stars}.\nZwrotów NIE ma.\n\nJesteś pewien?",
        "de": "⚠️ *Bestätigung*\n\nDu gibst ⭐ {stars} aus.\nKeine Rückerstattung.\n\nBist du sicher?",
        "es": "⚠️ *Confirmación*\n\nGastarás ⭐ {stars}.\nNo hay reembolsos.\n\n¿Estás seguro?",
        "fr": "⚠️ *Confirmation*\n\nTu vas dépenser ⭐ {stars}.\nAucun remboursement.\n\nTu es sûr ?",
        "uk": "⚠️ *Підтвердження*\n\nТи витратиш ⭐ {stars}.\nПовернення НЕ буде.\n\nТи впевнений?",
    },
    "paid": {
        "en": "✅ Payment successful!\nYour balance is updated.",
        "ru": "✅ Оплата прошла!\nБаланс обновлён.",
        "pl": "✅ Płatność udana!\nSaldo zaktualizowane.",
        "de": "✅ Zahlung erfolgreich!\nGuthaben aktualisiert.",
        "es": "✅ Pago exitoso!\nSaldo actualizado.",
        "fr": "✅ Paiement réussi !\nSolde mis à jour.",
        "uk": "✅ Оплата успішна!\nБаланс оновлено.",
    },
    "balance": {
        "en": "🎵 Your balance: *{songs}* song(s).",
        "ru": "🎵 Твой баланс: *{songs}* песен.",
        "pl": "🎵 Twoje saldo: *{songs}* piosenek.",
        "de": "🎵 Dein Guthaben: *{songs}* Song(s).",
        "es": "🎵 Tu saldo: *{songs}* canción(es).",
        "fr": "🎵 Ton solde : *{songs}* chanson(s).",
        "uk": "🎵 Твій баланс: *{songs}* пісень.",
    },
    "help": {
        "en": (
            "❓ *Help*\n\n"
            "• You can’t edit a finished song — generate again.\n"
            "• AI may make mistakes in stress/pronunciation.\n"
            "• Avoid artist names — describe mood/tempo/genre.\n"
            "• You can publish your songs in *any social network*.\n\n"
            "Payments are via *Telegram Stars*."
        ),
        "ru": (
            "❓ *Помощь*\n\n"
            "• Изменить готовую песню нельзя — только генерировать заново.\n"
            "• ИИ может ошибаться в ударениях/дикции.\n"
            "• Не используй имена артистов — описывай жанр/темп/настроение.\n"
            "• Песни можно публиковать в *любой социальной сети*.\n\n"
            "Оплата — через *Telegram Stars*."
        ),
        "pl": (
            "❓ *Pomoc*\n\n"
            "• Nie da się edytować gotowej piosenki — generuj ponownie.\n"
            "• AI może popełniać błędy w wymowie.\n"
            "• Unikaj nazw artystów — opisuj klimat/tempo/gatunek.\n"
            "• Piosenki możesz publikować w *dowolnych social media*.\n\n"
            "Płatności: *Telegram Stars*."
        ),
        "de": (
            "❓ *Hilfe*\n\n"
            "• Fertige Songs kann man nicht bearbeiten — neu generieren.\n"
            "• KI kann Fehler bei Betonung/Aussprache machen.\n"
            "• Keine Künstlernamen — beschreibe Stimmung/Tempo/Genre.\n"
            "• Du kannst Songs in *jedem sozialen Netzwerk* posten.\n\n"
            "Zahlung: *Telegram Stars*."
        ),
        "es": (
            "❓ *Ayuda*\n\n"
            "• No se puede editar una canción lista — genera otra.\n"
            "• La IA puede cometer errores de pronunciación.\n"
            "• Evita nombres de artistas — describe ánimo/tempo/género.\n"
            "• Puedes publicar las canciones en *cualquier red social*.\n\n"
            "Pagos: *Telegram Stars*."
        ),
        "fr": (
            "❓ *Aide*\n\n"
            "• On ne peut pas modifier une chanson finie — régénère.\n"
            "• L’IA peut faire des erreurs de prononciation.\n"
            "• Évite les noms d’artistes — décris ambiance/tempo/genre.\n"
            "• Tu peux publier dans *n’importe quel réseau social*.\n\n"
            "Paiement : *Telegram Stars*."
        ),
        "uk": (
            "❓ *Допомога*\n\n"
            "• Готову пісню не можна редагувати — лише згенерувати знову.\n"
            "• ШІ може помилятися у вимові/наголосах.\n"
            "• Не використовуй імена артистів — опиши настрій/темп/жанр.\n"
            "• Пісні можна публікувати в *будь-якій соцмережі*.\n\n"
            "Оплата — *Telegram Stars*."
        ),
    },
    "error": {
        "en": "⚠️ Temporary error. Please try again later.",
        "ru": "⚠️ Временная ошибка. Попробуй ещё раз позже.",
        "pl": "⚠️ Błąd tymczasowy. Spróbuj później.",
        "de": "⚠️ Temporärer Fehler. Bitte später erneut versuchen.",
        "es": "⚠️ Error temporal. Inténtalo más tarde.",
        "fr": "⚠️ Erreur temporaire. Réessaie plus tard.",
        "uk": "⚠️ Тимчасова помилка. Спробуй пізніше.",
    },
}

THEMES = [
    ("love",   {"en":"Love ❤️","ru":"Любовь ❤️","pl":"Miłość ❤️","de":"Liebe ❤️","es":"Amor ❤️","fr":"Amour ❤️","uk":"Кохання ❤️"}),
    ("fun",    {"en":"Funny 😄","ru":"Смешная 😄","pl":"Zabawna 😄","de":"Lustig 😄","es":"Divertida 😄","fr":"Drôle 😄","uk":"Смішна 😄"}),
    ("congr",  {"en":"Holiday 🎉","ru":"Праздник 🎉","pl":"Święto 🎉","de":"Feier 🎉","es":"Fiesta 🎉","fr":"Fête 🎉","uk":"Свято 🎉"}),
    ("sad",    {"en":"Sad 😢","ru":"Грусть 😢","pl":"Smutna 😢","de":"Traurig 😢","es":"Triste 😢","fr":"Triste 😢","uk":"Сум 😢"}),
    ("wedding",{"en":"Wedding 💍","ru":"Свадьба 💍","pl":"Wesele 💍","de":"Hochzeit 💍","es":"Boda 💍","fr":"Mariage 💍","uk":"Весілля 💍"}),
    ("custom", {"en":"Custom ✏️","ru":"Свой вариант ✏️","pl":"Własny temat ✏️","de":"Eigenes Thema ✏️","es":"Tema propio ✏️","fr":"Thème perso ✏️","uk":"Свій варіант ✏️"}),
    ("disco",  {"en":"Disco Polo 🇵🇱","ru":"Disco Polo 🇵🇱","pl":"Disco Polo 🇵🇱","de":"Disco Polo 🇵🇱","es":"Disco Polo 🇵🇱","fr":"Disco Polo 🇵🇱","uk":"Disco Polo 🇵🇱"}),
]

GENRES = ["Pop", "Rap / Hip-Hop", "Rock", "Club", "Classical", "Disco Polo"]

def get_lang(uid: int) -> str:
    u = db_get_user(uid)
    lang = u.get("lang", "en")
    return lang if lang in LANGS else "en"

def tr(uid: int, key: str) -> str:
    lang = get_lang(uid)
    return TEXTS[key].get(lang, TEXTS[key]["en"])

# -------------------- AI CALLS --------------------
async def openai_demo_lyrics(prompt: str) -> Optional[str]:
    if not OPENAI_KEY:
        return None
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.9,
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=60) as r:
                data = await r.json()
                return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"OpenAI demo error: {e}")
        return None

async def piapi_full_generate(prompt: str) -> Optional[str]:
    if not PIAPI_KEY:
        return None
    url = "https://api.piapi.ai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {PIAPI_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "pi-music",
        "messages": [{"role": "user", "content": prompt}],
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=120) as r:
                data = await r.json()
                # логируем ответ, если структура не та
                if "choices" not in data:
                    logger.error(f"PiAPI unexpected response: {json.dumps(data)[:1000]}")
                    return None
                return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"PiAPI error: {e}")
        return None

# -------------------- UI BUILDERS --------------------
def kb_start() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("▶️ START", callback_data="start")]])

def kb_languages() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("English 🇬🇧", callback_data="lang_en")],
        [InlineKeyboardButton("Русский 🇷🇺", callback_data="lang_ru")],
        [InlineKeyboardButton("Polski 🇵🇱", callback_data="lang_pl")],
        [InlineKeyboardButton("Deutsch 🇩🇪", callback_data="lang_de")],
        [InlineKeyboardButton("Español 🇪🇸", callback_data="lang_es")],
        [InlineKeyboardButton("Français 🇫🇷", callback_data="lang_fr")],
        [InlineKeyboardButton("Українська 🇺🇦", callback_data="lang_uk")],
    ]
    return InlineKeyboardMarkup(rows)

def kb_themes(uid: int) -> InlineKeyboardMarkup:
    lang = get_lang(uid)
    rows = []
    for key, names in THEMES:
        rows.append([InlineKeyboardButton(names.get(lang, names["en"]), callback_data=f"theme_{key}")])
    return InlineKeyboardMarkup(rows)

def kb_genres() -> InlineKeyboardMarkup:
    rows = []
    for g in GENRES:
        cb = g.lower().replace(" / ", "_").replace(" ", "_")
        rows.append([InlineKeyboardButton(g, callback_data=f"genre_{cb}")])
    return InlineKeyboardMarkup(rows)

def kb_buy(uid: int) -> InlineKeyboardMarkup:
    lang = get_lang(uid)
    # одна кнопка — одна строка (широко)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"⭐ 1 song — {PRICES['1']}", callback_data="buy_1")],
        [InlineKeyboardButton(f"⭐ 5 songs — {PRICES['5']}", callback_data="buy_5")],
        [InlineKeyboardButton(f"⭐ 25 songs — {PRICES['25']}", callback_data="buy_25")],
    ])

def kb_confirm(pack: str, stars: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Yes", callback_data=f"pay_{pack}"),
        InlineKeyboardButton("❌ No", callback_data="cancel")
    ]])

# -------------------- COMMANDS --------------------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    db_get_user(uid)  # ensure exists
    await update.message.reply_text(
        TEXTS["start"]["en"],  # старт всегда EN (как раньше у тебя)
        reply_markup=kb_start(),
        parse_mode="Markdown"
    )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await update.message.reply_text(tr(uid, "help"), parse_mode="Markdown")

async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = db_get_user(uid)
    await update.message.reply_text(tr(uid, "balance").format(songs=u["songs"]), parse_mode="Markdown")

# -------------------- BUTTONS --------------------
async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    data = q.data

    # ensure user record
    db_get_user(uid)

    if data == "start":
        state[uid] = {}
        await q.edit_message_text(tr(uid, "choose_language"), reply_markup=kb_languages())
        return

    if data.startswith("lang_"):
        lang = data[5:]
        if lang not in LANGS:
            lang = "en"
        db_set_lang(uid, lang)
        state.setdefault(uid, {})
        state[uid]["lang"] = lang
        await q.edit_message_text(tr(uid, "choose_theme"), reply_markup=kb_themes(uid))
        return

    if data.startswith("theme_"):
        theme_key = data[6:]
        state.setdefault(uid, {})
        state[uid]["theme_key"] = theme_key

        if theme_key == "custom":
            state[uid]["awaiting_custom_theme"] = True
            await q.edit_message_text(tr(uid, "ask_custom_theme"))
            return

        # обычная тема
        state[uid]["awaiting_custom_theme"] = False
        await q.edit_message_text(tr(uid, "choose_genre"), reply_markup=kb_genres())
        return

    if data.startswith("genre_"):
        state.setdefault(uid, {})
        state[uid]["genre"] = data[6:]  # уже норм
        state[uid]["awaiting_description"] = True
        await q.edit_message_text(tr(uid, "describe"), parse_mode="Markdown")
        return

    if data.startswith("buy_"):
        pack = data.split("_")[1]
        stars = PRICES.get(pack)
        if not stars:
            await q.edit_message_text(tr(uid, "error"))
            return
        pending_pack[uid] = pack
        await q.edit_message_text(
            tr(uid, "confirm").format(stars=stars),
            reply_markup=kb_confirm(pack, stars),
            parse_mode="Markdown"
        )
        return

    if data.startswith("pay_"):
        pack = data.split("_")[1]
        stars = PRICES.get(pack)
        if not stars:
            await q.edit_message_text(tr(uid, "error"))
            return

        # Telegram Stars invoice
        # provider_token для XTR обычно пустой
        await context.bot.send_invoice(
            chat_id=uid,
            title=f"MusicAi Pack: {pack} song(s)",
            description="AI song generation. Payment via Telegram Stars.",
            payload=f"pack_{pack}_{uid}_{int(time.time())}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice("Stars", stars)],
        )
        return

    if data == "cancel":
        await q.edit_message_text("❌ Cancelled. Use /start.")
        return

# -------------------- INPUT (TEXT/VOICE) --------------------
async def on_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = db_get_user(uid)

    st = state.get(uid, {})

    # 1) ждем кастом-тему
    if st.get("awaiting_custom_theme"):
        custom_theme = (update.message.text or "").strip()
        if not custom_theme:
            await update.message.reply_text(tr(uid, "ask_custom_theme"))
            return
        # ограничим длину
        custom_theme = custom_theme[:40]
        st["custom_theme"] = custom_theme
        st["awaiting_custom_theme"] = False
        state[uid] = st
        await update.message.reply_text(tr(uid, "choose_genre"), reply_markup=kb_genres())
        return

    # 2) ждем описание песни
    if not st.get("awaiting_description"):
        await update.message.reply_text("Please press /start and follow the buttons.")
        return

    description = (update.message.text or "").strip()
    if not description:
        await update.message.reply_text(tr(uid, "describe"), parse_mode="Markdown")
        return

    # Собираем параметры
    lang = get_lang(uid)
    theme_key = st.get("theme_key", "love")
    theme_text = ""
    for k, names in THEMES:
        if k == theme_key:
            theme_text = names.get(lang, names["en"])
            break
    if theme_key == "custom":
        theme_text = st.get("custom_theme", "Custom")

    # genre в англ.
    genre = st.get("genre", "pop")

    # ДЕМО (1 раз)
    if not u["demo_used"]:
        await update.message.reply_text("⏳ Generating demo…")
        demo_prompt = (
            "Write TWO short song lyrics (with chorus), NOT too long.\n"
            f"Language: {lang}\n"
            f"Theme: {theme_text}\n"
            f"Genre: {genre}\n"
            f"Description: {description}\n"
        )
        lyrics = await openai_demo_lyrics(demo_prompt)
        if not lyrics:
            await update.message.reply_text(tr(uid, "error"))
            return

        db_set_demo_used(uid, True)
        await update.message.reply_text(
            f"{tr(uid,'demo_header')}\n\n{lyrics[:3500]}",
            parse_mode="Markdown"
        )
        # после демо — предложим купить
        await update.message.reply_text(tr(uid, "buy_title"), reply_markup=kb_buy(uid))
        return

    # ПОЛНАЯ ГЕНЕРАЦИЯ (только если есть баланс песен)
    if u["songs"] <= 0:
        await update.message.reply_text(tr(uid, "no_balance"), reply_markup=kb_buy(uid))
        return

    # списываем 1 песню
    ok = db_take_song(uid)
    if not ok:
        await update.message.reply_text(tr(uid, "no_balance"), reply_markup=kb_buy(uid))
        return

    wait = await update.message.reply_text("⏳ Generating full song…")
    full_prompt = (
        "Generate a full song output.\n"
        f"Language: {lang}\n"
        f"Theme: {theme_text}\n"
        f"Genre: {genre}\n"
        f"Description: {description}\n"
        "Return the result in a clean readable format."
    )

    result = await piapi_full_generate(full_prompt)
    if not result:
        # если piapi упал — вернем песню обратно
        db_add_songs(uid, 1)
        await wait.edit_text(tr(uid, "error"))
        return

    await wait.edit_text(result[:3900])

# -------------------- PAYMENTS --------------------
async def on_precheckout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Всегда ok=True, иначе платеж не пройдет
    await update.pre_checkout_query.answer(ok=True)

async def on_success_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    payload = update.message.successful_payment.invoice_payload

    # payload: pack_{pack}_{uid}_{ts}
    pack = None
    try:
        parts = payload.split("_")
        if len(parts) >= 2 and parts[0] == "pack":
            pack = parts[1]
    except:
        pack = None

    if pack not in PRICES:
        await update.message.reply_text(tr(uid, "paid"))
        return

    # добавляем песни
    add = int(pack)
    db_add_songs(uid, add)

    await update.message.reply_text(tr(uid, "paid"))

    # уведомление владельцу (если указан)
    if OWNER_ID:
        try:
            username = update.effective_user.username or "-"
            await context.bot.send_message(
                OWNER_ID,
                f"⭐ Stars payment from @{username} ({uid}) — pack {pack} (+{add} songs)"
            )
        except Exception as e:
            logger.error(f"Owner notify failed: {e}")

# -------------------- ERROR HANDLER --------------------
async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Exception while handling an update:", exc_info=context.error)

# -------------------- MAIN --------------------
async def set_menu_commands(app):
    # help внизу (последним)
    cmds = [
        BotCommand("start", "Start"),
        BotCommand("balance", "Balance"),
        BotCommand("help", "Help"),
    ]
    try:
        await app.bot.set_my_commands(cmds)
    except Exception as e:
        logger.error(f"set_my_commands error: {e}")

def main():
    db_init()

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_error_handler(on_error)

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("balance", cmd_balance))

    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_user_message))

    app.add_handler(PreCheckoutQueryHandler(on_precheckout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, on_success_payment))

    # ставим команды в меню
    app.post_init = set_menu_commands

    logger.info("MusicAi started")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()