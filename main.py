# -*- coding: utf-8 -*-

import os
import sys
import json
import time
import logging
import sqlite3
import asyncio
from typing import Optional, Dict, Any

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

# -------------------- LOGS (Render-friendly) --------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("MusicAi")

# -------------------- ENV --------------------
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
PIAPI_KEY = os.getenv("PIAPI_KEY")  # PiAPI key (Bearer ...)
OWNER_ID = int(os.getenv("OWNER_TG_ID", "1225282893"))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN not set")
if not PIAPI_KEY:
    raise RuntimeError("PIAPI_KEY not set")

# -------------------- PRICES (Telegram Stars) --------------------
PACKS = {
    "1": 250,
    "5": 1000,
    "25": 4000,
}

# -------------------- DB --------------------
DB_PATH = "musicai.db"


def db_init() -> None:
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            lang TEXT DEFAULT 'en',
            demo_used INTEGER DEFAULT 0,
            songs INTEGER DEFAULT 0,
            state_json TEXT DEFAULT '{}',
            updated_at INTEGER DEFAULT 0
        )
        """
    )
    con.commit()
    con.close()


def db_get_user(user_id: int) -> Dict[str, Any]:
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(
        "SELECT user_id, lang, demo_used, songs, state_json FROM users WHERE user_id=?",
        (user_id,),
    )
    row = cur.fetchone()
    if not row:
        cur.execute(
            "INSERT INTO users(user_id, lang, demo_used, songs, state_json, updated_at) VALUES(?,?,?,?,?,?)",
            (user_id, "en", 0, 0, "{}", int(time.time())),
        )
        con.commit()
        con.close()
        return {"user_id": user_id, "lang": "en", "demo_used": 0, "songs": 0, "state": {}}
    con.close()
    state = {}
    try:
        state = json.loads(row[4] or "{}")
    except Exception:
        state = {}
    return {"user_id": row[0], "lang": row[1], "demo_used": row[2], "songs": row[3], "state": state}


def db_set(user_id: int, lang: str = None, demo_used: int = None, songs: int = None, state: dict = None) -> None:
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    # ensure row
    cur.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO users(user_id, lang, demo_used, songs, state_json, updated_at) VALUES(?,?,?,?,?,?)",
            (user_id, "en", 0, 0, "{}", int(time.time())),
        )

    if state is not None:
        state_json = json.dumps(state, ensure_ascii=False)
        cur.execute(
            "UPDATE users SET state_json=?, updated_at=? WHERE user_id=?",
            (state_json, int(time.time()), user_id),
        )
    if lang is not None:
        cur.execute(
            "UPDATE users SET lang=?, updated_at=? WHERE user_id=?",
            (lang, int(time.time()), user_id),
        )
    if demo_used is not None:
        cur.execute(
            "UPDATE users SET demo_used=?, updated_at=? WHERE user_id=?",
            (demo_used, int(time.time()), user_id),
        )
    if songs is not None:
        cur.execute(
            "UPDATE users SET songs=?, updated_at=? WHERE user_id=?",
            (songs, int(time.time()), user_id),
        )

    con.commit()
    con.close()


async def adb_get_user(user_id: int) -> Dict[str, Any]:
    return await asyncio.to_thread(db_get_user, user_id)


async def adb_set(user_id: int, **kwargs) -> None:
    await asyncio.to_thread(db_set, user_id, **kwargs)


# -------------------- TEXTS --------------------
LANGS = ["en", "ru", "pl", "de", "es", "fr", "uk"]

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
    "describe": {
        "en": "✍️ *Describe the song*\n\n1) Who is it for?\n2) Tell their story / event / situation\n3) Mood & emotions (what you want to deliver)\n\n🎤 If you don’t want to type — send a voice message.",
        "ru": "✍️ *Опиши песню*\n\n1) Кому посвящается?\n2) История / событие / ситуация\n3) Настроение и эмоции (что хочешь передать)\n\n🎤 Если лень писать — отправь голосовое.",
        "pl": "✍️ *Opisz piosenkę*\n\n1) Dla kogo?\n2) Historia / wydarzenie / sytuacja\n3) Klimat i emocje (co chcesz przekazać)\n\n🎤 Jeśli nie chcesz pisać — wyślij głosówkę.",
        "de": "✍️ *Beschreibe das Lied*\n\n1) Für wen?\n2) Geschichte / Ereignis / Situation\n3) Stimmung & Emotionen (was du vermitteln willst)\n\n🎤 Wenn du nicht tippen willst — sende eine Sprachnachricht.",
        "es": "✍️ *Describe la canción*\n\n1) ¿Para quién es?\n2) Historia / evento / situación\n3) Ánimo y emociones (qué quieres transmitir)\n\n🎤 Si no quieres escribir — envía un mensaje de voz.",
        "fr": "✍️ *Décris la chanson*\n\n1) Pour qui ?\n2) Histoire / événement / situation\n3) Ambiance & émotions (ce que tu veux transmettre)\n\n🎤 Si tu ne veux pas écrire — envoie un vocal.",
        "uk": "✍️ *Опиши пісню*\n\n1) Кому присвячена?\n2) Історія / подія / ситуація\n3) Настрій і емоції (що хочеш передати)\n\n🎤 Якщо не хочеш писати — надішли голосове.",
    },
    "demo_header": {
        "en": "🎧 Demo version (1 time only)\n(Short preview ~1 minute)",
        "ru": "🎧 Демо-версия (только 1 раз)\n(Короткий превью ~1 минута)",
        "pl": "🎧 Wersja demo (tylko 1 raz)\n(Krótkie preview ~1 minuta)",
        "de": "🎧 Demo-Version (nur 1x)\n(Kurzes Preview ~1 Minute)",
        "es": "🎧 Versión demo (solo 1 vez)\n(Preview corto ~1 minuto)",
        "fr": "🎧 Version démo (1 seule fois)\n(Aperçu court ~1 minute)",
        "uk": "🎧 Демо-версія (лише 1 раз)\n(Коротке превʼю ~1 хвилина)",
    },
    "buy_title": {
        "en": "Buy songs with Telegram Stars",
        "ru": "Покупка песен за Telegram Stars",
        "pl": "Kup piosenki za Telegram Stars",
        "de": "Songs mit Telegram Stars kaufen",
        "es": "Compra canciones con Telegram Stars",
        "fr": "Acheter des chansons avec Telegram Stars",
        "uk": "Купівля пісень за Telegram Stars",
    },
    "buy_confirm": {
        "en": "⚠️ Confirmation\n\nYou are about to spend ⭐ {stars}.\nRefunds are NOT possible.\n\nAre you sure?",
        "ru": "⚠️ Подтверждение\n\nТы собираешься потратить ⭐ {stars}.\nВозврата НЕ будет.\n\nТы уверен?",
        "pl": "⚠️ Potwierdzenie\n\nWydasz ⭐ {stars}.\nZwrotów NIE ma.\n\nJesteś pewien?",
        "de": "⚠️ Bestätigung\n\nDu gibst ⭐ {stars} aus.\nKeine Rückerstattung.\n\nBist du sicher?",
        "es": "⚠️ Confirmación\n\nVas a gastar ⭐ {stars}.\nNo hay reembolsos.\n\n¿Seguro?",
        "fr": "⚠️ Confirmation\n\nTu vas dépenser ⭐ {stars}.\nAucun remboursement.\n\nTu confirmes ?",
        "uk": "⚠️ Підтвердження\n\nТи витрачаєш ⭐ {stars}.\nПовернення НЕ буде.\n\nТи впевнений?",
    },
    "paid": {
        "en": "✅ Payment successful! Songs added to your balance.",
        "ru": "✅ Оплата прошла! Песни добавлены на баланс.",
        "pl": "✅ Płatność udana! Piosenki dodane do salda.",
        "de": "✅ Zahlung erfolgreich! Songs wurden hinzugefügt.",
        "es": "✅ ¡Pago exitoso! Canciones añadidas al saldo.",
        "fr": "✅ Paiement réussi ! Chansons ajoutées au solde.",
        "uk": "✅ Оплата успішна! Пісні додано на баланс.",
    },
    "need_start": {
        "en": "Please press /start and follow the buttons 🙂",
        "ru": "Нажми /start и пройди шаги кнопками 🙂",
        "pl": "Naciśnij /start i przejdź kroki przyciskami 🙂",
        "de": "Bitte /start drücken und die Schritte folgen 🙂",
        "es": "Pulsa /start y sigue los pasos 🙂",
        "fr": "Appuie sur /start et suis les étapes 🙂",
        "uk": "Натисни /start і пройди кроки кнопками 🙂",
    },
    "generating": {
        "en": "⏳ Generating...",
        "ru": "⏳ Генерирую...",
        "pl": "⏳ Generuję...",
        "de": "⏳ Generiere...",
        "es": "⏳ Generando...",
        "fr": "⏳ Génération...",
        "uk": "⏳ Генерую...",
    },
    "no_credits": {
        "en": "You have 0 songs. Buy a pack to continue 👇",
        "ru": "У тебя 0 песен. Купи пакет, чтобы продолжить 👇",
        "pl": "Masz 0 piosenek. Kup pakiet, aby kontynuować 👇",
        "de": "Du hast 0 Songs. Kaufe ein Paket, um fortzufahren 👇",
        "es": "Tienes 0 canciones. Compra un paquete para continuar 👇",
        "fr": "Tu as 0 chanson. Achète un pack pour continuer 👇",
        "uk": "У тебе 0 пісень. Купи пакет, щоб продовжити 👇",
    },
    "help": {
        "en": (
            "ℹ️ Help\n\n"
            "✏️ Can I edit a ready song?\n"
            "No — only generate again (−1 song).\n\n"
            "🎶 How many variants?\n"
            "Each generation gives 2 different variants.\n\n"
            "🔉 Stress / diction issues?\n"
            "Write stress with CAPS inside the word, e.g. dIma, svEta.\n\n"
            "📄 Rights\n"
            "The rights belong to you as the customer.\n\n"
            "🌍 Publishing\n"
            "You can publish the song in any social network."
        ),
        "ru": (
            "ℹ️ Help\n\n"
            "✏️ Можно ли изменить готовую песню?\n"
            "Нет — только сгенерировать заново (−1 песня).\n\n"
            "🎶 Сколько вариантов даётся?\n"
            "При каждой генерации ты получаешь 2 разных варианта.\n\n"
            "🔉 Почему ошибки в ударениях/дикции?\n"
            "Пиши ударение КАПСОМ внутри слова: дИма, свЕта.\n\n"
            "📄 Авторские права\n"
            "Права принадлежат тебе как заказчику.\n\n"
            "🌍 Публикация\n"
            "Можно публиковать в любой социальной сети."
        ),
        "pl": (
            "ℹ️ Pomoc\n\n"
            "✏️ Czy można edytować gotową piosenkę?\n"
            "Nie — tylko wygenerować ponownie (−1 piosenka).\n\n"
            "🎶 Ile wersji?\n"
            "Każde generowanie daje 2 różne wersje.\n\n"
            "🔉 Akcent / dykcja?\n"
            "Zaznacz akcent WIELKIMI literami w słowie.\n\n"
            "📄 Prawa\n"
            "Prawa należą do Ciebie jako klienta.\n\n"
            "🌍 Publikacja\n"
            "Możesz publikować w dowolnej sieci społecznościowej."
        ),
        "de": (
            "ℹ️ Hilfe\n\n"
            "✏️ Fertigen Song ändern?\n"
            "Nein — nur neu generieren (−1 Song).\n\n"
            "🎶 Wie viele Varianten?\n"
            "Pro Generierung gibt es 2 verschiedene Varianten.\n\n"
            "🔉 Betonung / Aussprache?\n"
            "Betonung mit GROSSBUCHSTABEN markieren.\n\n"
            "📄 Rechte\n"
            "Die Rechte gehören dir als Kunde.\n\n"
            "🌍 Veröffentlichen\n"
            "Du kannst es in jedem sozialen Netzwerk veröffentlichen."
        ),
        "es": (
            "ℹ️ Ayuda\n\n"
            "✏️ ¿Se puede editar una canción lista?\n"
            "No — solo generar de nuevo (−1 canción).\n\n"
            "🎶 ¿Cuántas versiones?\n"
            "Cada generación da 2 versiones diferentes.\n\n"
            "🔉 ¿Acento / dicción?\n"
            "Marca el acento con MAYÚSCULAS dentro de la palabra.\n\n"
            "📄 Derechos\n"
            "Los derechos son tuyos como cliente.\n\n"
            "🌍 Publicación\n"
            "Puedes publicarla en cualquier red social."
        ),
        "fr": (
            "ℹ️ Aide\n\n"
            "✏️ Modifier une chanson prête ?\n"
            "Non — il faut régénérer (−1 chanson).\n\n"
            "🎶 Combien de versions ?\n"
            "Chaque génération donne 2 versions différentes.\n\n"
            "🔉 Accent / diction ?\n"
            "Indique l’accent en MAJUSCULES dans le mot.\n\n"
            "📄 Droits\n"
            "Les droits t’appartiennent en tant que client.\n\n"
            "🌍 Publication\n"
            "Tu peux publier sur n’importe quel réseau social."
        ),
        "uk": (
            "ℹ️ Допомога\n\n"
            "✏️ Чи можна змінити готову пісню?\n"
            "Ні — лише згенерувати заново (−1 пісня).\n\n"
            "🎶 Скільки варіантів?\n"
            "Кожна генерація дає 2 різні варіанти.\n\n"
            "🔉 Наголос / дикція?\n"
            "Позначай наголос ВЕЛИКИМИ літерами в слові.\n\n"
            "📄 Права\n"
            "Права належать тобі як замовнику.\n\n"
            "🌍 Публікація\n"
            "Можна публікувати в будь-якій соцмережі."
        ),
    },
}

THEMES = {
    "love": {"en": "Love ❤️", "ru": "Любовь ❤️", "pl": "Miłość ❤️", "de": "Liebe ❤️", "es": "Amor ❤️", "fr": "Amour ❤️", "uk": "Кохання ❤️"},
    "fun": {"en": "Funny 😄", "ru": "Смешная 😄", "pl": "Zabawna 😄", "de": "Lustig 😄", "es": "Divertida 😄", "fr": "Drôle 😄", "uk": "Весела 😄"},
    "holiday": {"en": "Holiday 🎉", "ru": "Праздник 🎉", "pl": "Święto 🎉", "de": "Feier 🎉", "es": "Fiesta 🎉", "fr": "Fête 🎉", "uk": "Свято 🎉"},
    "sad": {"en": "Sad 😢", "ru": "Грусть 😢", "pl": "Smutna 😢", "de": "Traurig 😢", "es": "Triste 😢", "fr": "Triste 😢", "uk": "Сум 😢"},
    "wedding": {"en": "Wedding 💍", "ru": "Свадьба 💍", "pl": "Wesele 💍", "de": "Hochzeit 💍", "es": "Boda 💍", "fr": "Mariage 💍", "uk": "Весілля 💍"},
    "custom": {"en": "Custom ✏️", "ru": "Свой вариант ✏️", "pl": "Własny wariant ✏️", "de": "Eigene Variante ✏️", "es": "Tu opción ✏️", "fr": "Votre option ✏️", "uk": "Свій варіант ✏️"},
}

# Genres MUST stay in English (as you requested)
GENRES = [
    ("pop", "Pop"),
    ("rap", "Rap / Hip-Hop"),
    ("hiphop", "Hip-Hop"),  # keep both if you want separate
    ("rock", "Rock"),
    ("club", "Club"),
    ("classic", "Classical"),
    ("disco", "Disco Polo"),
]


def tr(lang: str, key: str) -> str:
    return TEXTS.get(key, {}).get(lang, TEXTS.get(key, {}).get("en", "Text missing"))


def help_btn() -> InlineKeyboardButton:
    return InlineKeyboardButton("Help ℹ️", callback_data="help")


# -------------------- PIAPI CALL (robust) --------------------
async def piapi_generate(prompt: str) -> Optional[str]:
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
            async with session.post(url, json=payload, headers=headers, timeout=120) as r:
                text = await r.text()
                try:
                    data = json.loads(text)
                except Exception:
                    logger.error("PiAPI non-JSON response: %s", text[:500])
                    return None

                # if error format
                if isinstance(data, dict) and "error" in data:
                    logger.error("PiAPI error payload: %s", str(data.get("error"))[:500])
                    return None

                # normal format
                try:
                    choices = data.get("choices")
                    if not choices:
                        logger.error("PiAPI Error: 'choices' missing. Full payload: %s", str(data)[:800])
                        return None
                    return choices[0]["message"]["content"]
                except Exception as e:
                    logger.error("PiAPI parsing error: %s | payload=%s", e, str(data)[:800])
                    return None
    except Exception as e:
        logger.error("PiAPI request exception: %s", e)
        return None


# -------------------- VOICE -> TEXT (OpenAI Whisper) --------------------
async def voice_to_text(file_path: str) -> Optional[str]:
    if not OPENAI_API_KEY:
        return None
    try:
        from openai import AsyncOpenAI as AIClient
        aclient = AIClient(api_key=OPENAI_API_KEY)
        with open(file_path, "rb") as f:
            res = await aclient.audio.transcriptions.create(model="whisper-1", file=f)
        return res.text
    except Exception as e:
        logger.error("OpenAI Whisper Error: %s", e)
        return None


# -------------------- UI KEYBOARDS --------------------
def kb_start(lang: str) -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton("▶️ START", callback_data="start")],
        [help_btn()],
    ]
    return InlineKeyboardMarkup(kb)


def kb_languages() -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton("English 🇬🇧", callback_data="lang_en"), InlineKeyboardButton("Русский 🇷🇺", callback_data="lang_ru")],
        [InlineKeyboardButton("Polski 🇵🇱", callback_data="lang_pl"), InlineKeyboardButton("Deutsch 🇩🇪", callback_data="lang_de")],
        [InlineKeyboardButton("Español 🇪🇸", callback_data="lang_es"), InlineKeyboardButton("Français 🇫🇷", callback_data="lang_fr")],
        [InlineKeyboardButton("Українська 🇺🇦", callback_data="lang_uk")],
        [help_btn()],
    ]
    return InlineKeyboardMarkup(kb)


def kb_themes(lang: str) -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton(THEMES["love"][lang], callback_data="theme_love"), InlineKeyboardButton(THEMES["fun"][lang], callback_data="theme_fun")],
        [InlineKeyboardButton(THEMES["holiday"][lang], callback_data="theme_holiday"), InlineKeyboardButton(THEMES["sad"][lang], callback_data="theme_sad")],
        [InlineKeyboardButton(THEMES["wedding"][lang], callback_data="theme_wedding"), InlineKeyboardButton(THEMES["custom"][lang], callback_data="theme_custom")],
        [help_btn()],
    ]
    return InlineKeyboardMarkup(kb)


def kb_genres() -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton("Pop", callback_data="genre_pop"), InlineKeyboardButton("Rap", callback_data="genre_rap")],
        [InlineKeyboardButton("Hip-Hop", callback_data="genre_hiphop"), InlineKeyboardButton("Rock", callback_data="genre_rock")],
        [InlineKeyboardButton("Club", callback_data="genre_club"), InlineKeyboardButton("Classical", callback_data="genre_classic")],
        [InlineKeyboardButton("Disco Polo", callback_data="genre_disco")],
        [help_btn()],
    ]
    return InlineKeyboardMarkup(kb)


def kb_buy() -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton("⭐ 1 song — 250", callback_data="buy_1")],
        [InlineKeyboardButton("⭐ 5 songs — 1000", callback_data="buy_5")],
        [InlineKeyboardButton("⭐ 25 songs — 4000", callback_data="buy_25")],
        [help_btn()],
    ]
    return InlineKeyboardMarkup(kb)


def kb_confirm_buy(pack: str, lang: str) -> InlineKeyboardMarkup:
    kb = [
        [
            InlineKeyboardButton("✅ Yes", callback_data=f"pay_{pack}"),
            InlineKeyboardButton("❌ No", callback_data="start"),
        ],
        [help_btn()],
    ]
    return InlineKeyboardMarkup(kb)


# -------------------- HANDLERS --------------------
async def set_commands(app):
    try:
        await app.bot.set_my_commands(
            [
                BotCommand("start", "Start"),
                BotCommand("help", "Help"),
            ]
        )
    except Exception:
        pass


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = await adb_get_user(uid)
    lang = u["lang"]
    await adb_set(uid, state={})
    await update.message.reply_text(tr(lang, "start"), reply_markup=kb_start(lang), parse_mode="Markdown")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = await adb_get_user(uid)
    await update.message.reply_text(tr(u["lang"], "help"))  # NO Markdown here (safe)


async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

    u = await adb_get_user(uid)
    lang = u["lang"]
    state = u["state"] or {}

    if q.data == "help":
        await q.message.reply_text(tr(lang, "help"))
        return

    if q.data == "start":
        await adb_set(uid, state={})
        await q.edit_message_text(tr(lang, "choose_language"), reply_markup=kb_languages())
        return

    if q.data.startswith("lang_"):
        lang = q.data[5:]
        await adb_set(uid, lang=lang, state={"lang": lang})
        await q.edit_message_text(tr(lang, "choose_theme"), reply_markup=kb_themes(lang))
        return

    # refresh lang/state after lang selection
    u = await adb_get_user(uid)
    lang = u["lang"]
    state = u["state"] or {}

    if q.data.startswith("theme_"):
        state["theme"] = q.data[6:]
        await adb_set(uid, state=state)
        await q.edit_message_text(tr(lang, "choose_genre"), reply_markup=kb_genres())
        return

    if q.data.startswith("genre_"):
        state["genre"] = q.data[6:]
        await adb_set(uid, state=state)
        await q.edit_message_text(tr(lang, "describe"), parse_mode="Markdown")
        return

    if q.data.startswith("buy_"):
        pack = q.data.split("_")[1]
        stars = PACKS.get(pack, 0)
        await q.edit_message_text(
            tr(lang, "buy_confirm").format(stars=stars),
            reply_markup=kb_confirm_buy(pack, lang),
        )
        return

    if q.data.startswith("pay_"):
        pack = q.data.split("_")[1]
        stars = PACKS.get(pack, 0)

        # Telegram Stars: provider_token MUST be empty string
        await context.bot.send_invoice(
            chat_id=uid,
            title="MusicAi",
            description=f"{pack} song(s)",
            payload=f"pack_{pack}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice("Stars", stars)],
        )
        return


async def user_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = await adb_get_user(uid)
    lang, state = u["lang"], (u["state"] or {})

    if not state or "genre" not in state or "lang" not in state:
        await update.message.reply_text(tr(lang, "need_start"))
        return

    prompt_text = ""
    if update.message.voice:
        wait = await update.message.reply_text(tr(lang, "generating"))
        file = await context.bot.get_file(update.message.voice.file_id)
        path = f"v_{uid}.ogg"
        await file.download_to_drive(path)
        prompt_text = await voice_to_text(path)
        try:
            os.remove(path)
        except Exception:
            pass
        if not prompt_text:
            await wait.edit_text("Voice not recognized. Please type the text.")
            return
        await wait.delete()
    else:
        prompt_text = update.message.text or ""

    demo_used, songs = int(u["demo_used"]), int(u["songs"])

    # Add theme text to prompt (including custom)
    theme = state.get("theme", "custom")
    genre = state.get("genre", "pop")
    req_lang = state.get("lang", lang)

    # If custom theme selected, user can write anything in description; we still pass theme=custom
    base_prompt_demo = (
        "Create a SHORT DEMO song preview (~1 minute). "
        "Return 2 variants. "
        f"Language: {req_lang}. Theme: {theme}. Genre: {genre}. "
        f"User description: {prompt_text}"
    )

    base_prompt_full = (
        "Create a FULL SONG. Return 2 variants. "
        "Include: intro, verse 1, chorus, verse 2, chorus, bridge, final chorus. "
        f"Language: {req_lang}. Theme: {theme}. Genre: {genre}. "
        f"User description: {prompt_text}"
    )

    if demo_used == 0:
        msg = await update.message.reply_text(tr(lang, "generating"))
        res = await piapi_generate(base_prompt_demo)
        if res:
            # IMPORTANT: no Markdown for AI responses (fixes entity parse errors)
            await msg.edit_text(f"{tr(lang, 'demo_header')}\n\n{res[:3500]}")
            await adb_set(uid, demo_used=1)
        else:
            await msg.edit_text("⚠️ Temporary error. Please try again later.")
        return

    if songs > 0:
        msg = await update.message.reply_text(tr(lang, "generating"))
        res = await piapi_generate(base_prompt_full)
        if res:
            # IMPORTANT: no Markdown for AI responses
            await msg.edit_text(res[:3900])
            await adb_set(uid, songs=songs - 1)
        else:
            await msg.edit_text("⚠️ Temporary error. Please try again later.")
        return

    await update.message.reply_text(tr(lang, "no_credits"), reply_markup=kb_buy())


async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Always ok. Telegram will handle "not enough stars" itself and show top-up flow.
    await update.pre_checkout_query.answer(ok=True)


async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = await adb_get_user(uid)

    payload = update.message.successful_payment.invoice_payload or ""
    pack = payload.replace("pack_", "").strip()
    add = int(pack) if pack.isdigit() else 0

    await adb_set(uid, songs=int(u["songs"]) + add)

    await update.message.reply_text(tr(u["lang"], "paid"))

    # notify owner
    if OWNER_ID:
        try:
            user = update.effective_user
            await context.bot.send_message(
                OWNER_ID,
                f"⭐ Payment received: +{add} songs from @{user.username} ({user.id})",
            )
        except Exception:
            pass


# -------------------- MAIN --------------------
def main():
    db_init()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT | filters.VOICE, user_input))
    app.add_handler(PreCheckoutQueryHandler(pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))

    app.post_init = set_commands  # set bot commands on startup (best effort)

    logger.info("MusicAi bot started")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()