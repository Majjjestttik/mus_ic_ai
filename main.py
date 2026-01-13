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
OWNER_ID = int(os.getenv("OWNER_TG_ID", "0"))  # твой numeric id (не @)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")  # опционально: для распознавания голосовых

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
    cur.execute("SELECT user_id, lang, demo_used, songs, state_json FROM users WHERE user_id=?", (user_id,))
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

def db_set(user_id: int, *, lang: Optional[str] = None, demo_used: Optional[int] = None, songs: Optional[int] = None, state: Optional[dict] = None) -> None:
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO users(user_id, lang, demo_used, songs, state_json, updated_at) VALUES(?,?,?,?,?,?)",
            (user_id, "en", 0, 0, "{}", int(time.time())),
        )
        con.commit()

    if state is not None:
        state_json = json.dumps(state, ensure_ascii=False)
        cur.execute("UPDATE users SET state_json=?, updated_at=? WHERE user_id=?", (state_json, int(time.time()), user_id))

    if lang is not None:
        cur.execute("UPDATE users SET lang=?, updated_at=? WHERE user_id=?", (lang, int(time.time()), user_id))

    if demo_used is not None:
        cur.execute("UPDATE users SET demo_used=?, updated_at=? WHERE user_id=?", (demo_used, int(time.time()), user_id))

    if songs is not None:
        cur.execute("UPDATE users SET songs=?, updated_at=? WHERE user_id=?", (songs, int(time.time()), user_id))

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
        "en": "🎧 *Demo version (1 time only)*\n(Short preview ~1 minute)",
        "ru": "🎧 *Демо-версия (только 1 раз)*\n(Короткий превью ~1 минута)",
        "pl": "🎧 *Wersja demo (tylko 1 raz)*\n(Krótkie preview ~1 minuta)",
        "de": "🎧 *Demo-Version (nur 1x)*\n(Kurzes Preview ~1 Minute)",
        "es": "🎧 *Versión demo (solo 1 vez)*\n(Preview corto ~1 minuto)",
        "fr": "🎧 *Version démo (1 seule fois)*\n(Aperçu court ~1 minute)",
        "uk": "🎧 *Демо-версія (лише 1 раз)*\n(Коротке превʼю ~1 хвилина)",
    },
    "buy_title": {
        "en": "💳 Buy songs with Telegram Stars",
        "ru": "💳 Покупка песен за Telegram Stars",
        "pl": "💳 Kup piosenki za Telegram Stars",
        "de": "💳 Songs mit Telegram Stars kaufen",
        "es": "💳 Compra canciones con Telegram Stars",
        "fr": "💳 Acheter des chansons avec Telegram Stars",
        "uk": "💳 Купівля пісень за Telegram Stars",
    },
    "buy_confirm": {
        "en": "⚠️ *Confirmation*\n\nYou are about to spend ⭐ {stars}.\nRefunds are NOT possible.\n\nAre you sure?",
        "ru": "⚠️ *Подтверждение*\n\nТы собираешься потратить ⭐ {stars}.\nВозврата НЕ будет.\n\nТы уверен?",
        "pl": "⚠️ *Potwierdzenie*\n\nWydasz ⭐ {stars}.\nZwrotów NIE ma.\n\nJesteś pewien?",
        "de": "⚠️ *Bestätigung*\n\nDu gibst ⭐ {stars} aus.\nKeine Rückerstattung.\n\nBist du sicher?",
        "es": "⚠️ *Confirmación*\n\nVas a gastar ⭐ {stars}.\nNo hay reembolsos.\n\n¿Seguro?",
        "fr": "⚠️ *Confirmation*\n\nTu vas dépenser ⭐ {stars}.\nAucun remboursement.\n\nTu confirmes ?",
        "uk": "⚠️ *Підтвердження*\n\nТи витрачаєш ⭐ {stars}.\nПовернення НЕ буде.\n\nТи впевнений?",
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
            "ℹ️ *Help*\n\n"
            "✏️ Edit a ready song? — No, only generate again (−1 song).\n"
            "🎶 How many variants? — 2 variants are generated per request.\n"
            "🔉 Stress/pronunciation issues? — It's a model feature. You can mark stress with CAPS: dIma, svEta.\n"
            "🎤 Voice/style changed? — Describe genre/mood/tempo, avoid artist names.\n"
            "🔁 Chorus repeats? — If it was in your text, the model may repeat it.\n\n"
            "📄 Rights belong to you as the customer.\n"
            "🌍 You can publish/use the song in any social network."
        ),
        "ru": (
            "ℹ️ *Help*\n\n"
            "✏️ Изменить готовую песню? — Нет, только сгенерировать заново (−1 песня).\n"
            "🎶 Сколько вариантов? — 2 варианта на одну генерацию.\n"
            "🔉 Ошибки ударений/дикции? — Особенность модели. Можно отмечать ударение КАПСОМ: дИма, свЕта.\n"
            "🎤 Поменялся голос/стиль? — Опиши жанр/настроение/темп, не используй имена артистов.\n"
            "🔁 Припев повторяется? — Если так было в тексте, модель может повторить.\n\n"
            "📄 Права на песню принадлежат тебе как заказчику.\n"
            "🌍 Можно использовать/публиковать в любой соцсети."
        ),
        "pl": (
            "ℹ️ *Pomoc*\n\n"
            "✏️ Zmienić gotową piosenkę? — Nie, tylko wygenerować ponownie (−1 piosenka).\n"
            "🎶 Ile wersji? — 2 wersje na jedno żądanie.\n"
            "🔉 Akcent/dykcja? — Cecha modelu. Możesz oznaczać akcent WIELKIMI literami.\n"
            "🎤 Zmienił się głos/styl? — Opisz gatunek/nastrój/tempo, unikaj nazw artystów.\n"
            "🔁 Refren się powtarza? — Jeśli było to w tekście, model może powtórzyć.\n\n"
            "📄 Prawa należą do Ciebie jako klienta.\n"
            "🌍 Możesz publikować w dowolnej sieci społecznościowej."
        ),
        "de": (
            "ℹ️ *Hilfe*\n\n"
            "✏️ Fertigen Song ändern? — Nein, nur neu generieren (−1 Song).\n"
            "🎶 Wie viele Varianten? — 2 Varianten pro Anfrage.\n"
            "🔉 Betonung/Aussprache? — Modelleigenschaft. Du kannst Betonung mit GROSSBUCHSTABEN markieren.\n"
            "🎤 Stimme/Stil geändert? — Genre/Stimmung/Tempo beschreiben, keine Künstlernamen.\n"
            "🔁 Refrain wiederholt sich? — Wenn es im Text war, kann es wiederholt werden.\n\n"
            "📄 Rechte gehören dir als Kunde.\n"
            "🌍 Du kannst den Song in jedem sozialen Netzwerk verwenden."
        ),
        "es": (
            "ℹ️ *Ayuda*\n\n"
            "✏️ ¿Editar una canción lista? — No, solo generar de nuevo (−1 canción).\n"
            "🎶 ¿Cuántas variantes? — 2 variantes por solicitud.\n"
            "🔉 ¿Acento/dicción? — Característica del modelo. Marca el acento con MAYÚSCULAS.\n"
            "🎤 ¿Cambió la voz/estilo? — Describe género/ánimo/tempo, evita nombres de artistas.\n"
            "🔁 ¿Se repite el coro? — Si estaba en tu texto, el modelo puede repetirlo.\n\n"
            "📄 Los derechos son tuyos como cliente.\n"
            "🌍 Puedes publicar en cualquier red social."
        ),
        "fr": (
            "ℹ️ *Aide*\n\n"
            "✏️ Modifier une chanson finie ? — Non, seulement régénérer (−1 chanson).\n"
            "🎶 Combien de variantes ? — 2 variantes par demande.\n"
            "🔉 Accent/diction ? — Caractéristique du modèle. Marque l’accent en MAJUSCULES.\n"
            "🎤 Voix/style changé ? — Décris genre/ambiance/tempo, évite les noms d’artistes.\n"
            "🔁 Refrain répété ? — Si c’était dans ton texte, le modèle peut le répéter.\n\n"
            "📄 Les droits t’appartiennent en tant que client.\n"
            "🌍 Tu peux publier sur n’importe quel réseau social."
        ),
        "uk": (
            "ℹ️ *Допомога*\n\n"
            "✏️ Змінити готову пісню? — Ні, тільки згенерувати заново (−1 пісня).\n"
            "🎶 Скільки варіантів? — 2 варіанти на одну генерацію.\n"
            "🔉 Наголоси/дикція? — Особливість моделі. Можна позначати наголос ВЕЛИКИМИ: дИма.\n"
            "🎤 Змінився голос/стиль? — Опиши жанр/настрій/темп, уникай імен артистів.\n"
            "🔁 Приспів повторюється? — Якщо так було в тексті, модель може повторити.\n\n"
            "📄 Права на пісню належать тобі як замовнику.\n"
            "🌍 Можна публікувати в будь-якій соцмережі."
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

GENRES = [
    ("Pop", "pop"),
    ("Rap / Hip-Hop", "rap"),
    ("Rock", "rock"),
    ("Club", "club"),
    ("Classical", "classical"),
    ("Disco Polo", "disco"),
]

def tr(lang: str, key: str) -> str:
    return TEXTS.get(key, {}).get(lang, TEXTS[key]["en"])

def help_btn(lang: str) -> InlineKeyboardButton:
    label = {"en": "Help ℹ️", "ru": "Help ℹ️", "pl": "Help ℹ️", "de": "Help ℹ️", "es": "Help ℹ️", "fr": "Help ℹ️", "uk": "Help ℹ️"}
    return InlineKeyboardButton(label.get(lang, "Help ℹ️"), callback_data="help")

# -------------------- PIAPI CALL --------------------
async def piapi_generate(prompt: str) -> Optional[str]:
    url = "https://api.piapi.ai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {PIAPI_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "pi-music",
        "messages": [{"role": "user", "content": prompt}],
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=90) as r:
                data = await r.json()
                return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error("PiAPI Error: %s", e)
        return None

# -------------------- OPTIONAL: Voice -> text (OpenAI) --------------------
async def voice_to_text(file_path: str) -> Optional[str]:
    if not OPENAI_API_KEY:
        return None
    try:
        import openai  # type: ignore
    except Exception:
        return None

    try:
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        with open(file_path, "rb") as f:
            res = client.audio.transcriptions.create(model="whisper-1", file=f)
        return getattr(res, "text", None)
    except Exception as e:
        logger.error("OpenAI Whisper Error: %s", e)
        return None

# -------------------- UI KEYBOARDS --------------------
def kb_languages() -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton("English 🇬🇧", callback_data="lang_en"), InlineKeyboardButton("Русский 🇷🇺", callback_data="lang_ru")],
        [InlineKeyboardButton("Polski 🇵🇱", callback_data="lang_pl"), InlineKeyboardButton("Deutsch 🇩🇪", callback_data="lang_de")],
        [InlineKeyboardButton("Español 🇪🇸", callback_data="lang_es"), InlineKeyboardButton("Français 🇫🇷", callback_data="lang_fr")],
        [InlineKeyboardButton("Українська 🇺🇦", callback_data="lang_uk")],
    ]
    return InlineKeyboardMarkup(kb)

def kb_themes(lang: str) -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton(THEMES["love"][lang], callback_data="theme_love"), InlineKeyboardButton(THEMES["fun"][lang], callback_data="theme_fun")],
        [InlineKeyboardButton(THEMES["holiday"][lang], callback_data="theme_holiday"), InlineKeyboardButton(THEMES["sad"][lang], callback_data="theme_sad")],
        [InlineKeyboardButton(THEMES["wedding"][lang], callback_data="theme_wedding"), InlineKeyboardButton(THEMES["custom"][lang], callback_data="theme_custom")],
        [help_btn(lang)],
    ]
    return InlineKeyboardMarkup(kb)

def kb_genres(lang: str) -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton("Pop", callback_data="genre_pop"), InlineKeyboardButton("Rap / Hip-Hop", callback_data="genre_rap")],
        [InlineKeyboardButton("Rock", callback_data="genre_rock"), InlineKeyboardButton("Club", callback_data="genre_club")],
        [InlineKeyboardButton("Classical", callback_data="genre_classical"), InlineKeyboardButton("Disco Polo", callback_data="genre_disco")],
        [help_btn(lang)],
    ]
    return InlineKeyboardMarkup(kb)

def kb_buy(lang: str) -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton("⭐ 1 song — 250", callback_data="buy_1")],
        [InlineKeyboardButton("⭐ 5 songs — 1000", callback_data="buy_5")],
        [InlineKeyboardButton("⭐ 25 songs — 4000", callback_data="buy_25")],
        [help_btn(lang)],
    ]
    return InlineKeyboardMarkup(kb)

def kb_confirm(pack: str, lang: str) -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton("✅ Yes", callback_data=f"pay_{pack}"), InlineKeyboardButton("❌ No", callback_data="cancel_buy")],
        [help_btn(lang)],
    ]
    return InlineKeyboardMarkup(kb)

# -------------------- ERROR HANDLER --------------------
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Unhandled exception:", exc_info=context.error)

# -------------------- COMMANDS --------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = await adb_get_user(uid)
    lang = u["lang"]

    # reset flow state
    await adb_set(uid, state={})

    kb = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ START", callback_data="start")], [help_btn(lang)]])
    await update.message.reply_text(tr(lang, "start"), reply_markup=kb, parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = await adb_get_user(uid)
    lang = u["lang"]
    await update.message.reply_text(tr(lang, "help"), parse_mode="Markdown")

# -------------------- BUTTONS --------------------
async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    u = await adb_get_user(uid)
    lang = u["lang"]
    state = u["state"] or {}

    data = q.data

    if data == "help":
        await q.message.reply_text(tr(lang, "help"), parse_mode="Markdown")
        return

    if data == "start":
        # start flow
        await adb_set(uid, state={})
        await q.edit_message_text(tr(lang, "choose_language"), reply_markup=kb_languages())
        return

    if data.startswith("lang_"):
        new_lang = data[5:]
        if new_lang not in LANGS:
            new_lang = "en"
        lang = new_lang
        await adb_set(uid, lang=lang)

        state = state or {}
        state["lang"] = lang
        await adb_set(uid, state=state)

        await q.edit_message_text(tr(lang, "choose_theme"), reply_markup=kb_themes(lang))
        return

    if data.startswith("theme_"):
        theme = data[6:]
        state = state or {}
        state["theme"] = theme
        await adb_set(uid, state=state)

        await q.edit_message_text(tr(lang, "choose_genre"), reply_markup=kb_genres(lang))
        return

    if data.startswith("genre_"):
        genre = data[6:]
        state = state or {}
        state["genre"] = genre
        await adb_set(uid, state=state)

        await q.edit_message_text(tr(lang, "describe"), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[help_btn(lang)]]))
        return

    if data.startswith("buy_"):
        pack = data.split("_")[1]
        stars = PACKS.get(pack)
        if not stars:
            return
        state = state or {}
        state["pending_pack"] = pack
        await adb_set(uid, state=state)

        await q.edit_message_text(
            tr(lang, "buy_confirm").format(stars=stars),
            parse_mode="Markdown",
            reply_markup=kb_confirm(pack, lang),
        )
        return

    if data.startswith("pay_"):
        pack = data.split("_")[1]
        stars = PACKS.get(pack)
        if not stars:
            return

        # Telegram Stars invoice (provider_token must be "" for Stars)
        await context.bot.send_invoice(
            chat_id=uid,
            title=f"MusicAi Pack: {pack} song(s)",
            description="AI song generation credits",
            payload=f"pack_{pack}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice("Stars", stars)],
        )
        return

    if data == "cancel_buy":
        await q.edit_message_text(tr(lang, "buy_title"), reply_markup=kb_buy(lang))
        return

# -------------------- INPUT (TEXT / VOICE) --------------------
async def user_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = await adb_get_user(uid)
    lang = u["lang"]
    state = u["state"] or {}

    if "genre" not in state or "theme" not in state:
        await update.message.reply_text(tr(lang, "need_start"))
        return

    # get user prompt
    prompt_text = ""
    if update.message.voice:
        # download voice
        try:
            msg = await update.message.reply_text(tr(lang, "generating"))
            file = await context.bot.get_file(update.message.voice.file_id)
            path = f"voice_{uid}.ogg"
            await file.download_to_drive(path)

            text = await voice_to_text(path)
            try:
                os.remove(path)
            except Exception:
                pass

            if not text:
                await msg.edit_text("🎤 Voice received. Please type your description (text) 🙂")
                return

            prompt_text = text
            await msg.delete()
        except Exception:
            await update.message.reply_text("🎤 Voice received. Please type your description (text) 🙂")
            return
    else:
        prompt_text = (update.message.text or "").strip()

    if not prompt_text:
        await update.message.reply_text("Please send a text 🙂")
        return

    # build prompt for PiAPI
    theme = state["theme"]
    genre = state["genre"]
    user_lang = state.get("lang", lang)

    # demo / credits logic
    demo_used = int(u["demo_used"] or 0)
    songs = int(u["songs"] or 0)

    # 1) Demo once
    if demo_used == 0:
        wait = await update.message.reply_text(tr(lang, "generating"))
        pi_prompt = (
            f"Create TWO short song lyric variants.\n"
            f"Language: {user_lang}\n"
            f"Theme: {theme}\n"
            f"Genre: {genre}\n"
            f"User description: {prompt_text}\n\n"
            f"Keep it short like a ~1 minute preview. No extra explanations."
        )
        song = await piapi_generate(pi_prompt)
        if song:
            # limit Telegram message size
            out = song[:3500]
            await wait.edit_text(f"{tr(lang, 'demo_header')}\n\n{out}", parse_mode="Markdown")
            await adb_set(uid, demo_used=1)
        else:
            await wait.edit_text("⚠️ Temporary error. Please try again later.")
        return

    # 2) Full song requires credits
    if songs <= 0:
        await update.message.reply_text(tr(lang, "no_credits"), reply_markup=kb_buy(lang))
        return

    # generate full + decrement
    wait = await update.message.reply_text(tr(lang, "generating"))
    pi_prompt = (
        f"Write FULL song lyrics (structure: verse/chorus/verse/chorus/bridge/chorus).\n"
        f"Language: {user_lang}\n"
        f"Theme: {theme}\n"
        f"Genre: {genre}\n"
        f"User description: {prompt_text}\n\n"
        f"Output ONLY the lyrics. No explanations. Make it catchy."
    )
    song = await piapi_generate(pi_prompt)
    if song:
        out = song[:3900]
        await wait.edit_text(out)
        await adb_set(uid, songs=songs - 1)
    else:
        await wait.edit_text("⚠️ Temporary error. Please try again later.")

# -------------------- PAYMENTS --------------------
async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = await adb_get_user(uid)
    state = u["state"] or {}
    lang = u["lang"]

    payload = update.message.successful_payment.invoice_payload  # e.g. pack_5
    pack = payload.replace("pack_", "").strip()
    add = int(pack) if pack in PACKS else 0
    if add <= 0:
        await update.message.reply_text(tr(lang, "paid"))
        return

    new_songs = int(u["songs"] or 0) + add
    await adb_set(uid, songs=new_songs)

    await update.message.reply_text(f"{tr(lang, 'paid')}\n🎶 Balance: {new_songs} songs")

    if OWNER_ID:
        try:
            username = update.effective_user.username or "-"
            await context.bot.send_message(
                OWNER_ID,
                f"⭐ Payment received: @{username} ({uid}) | Pack {pack} | New balance: {new_songs}",
            )
        except Exception:
            pass

# -------------------- MAIN --------------------
async def post_init(app):
    # set commands
    try:
        await app.bot.set_my_commands([BotCommand("start", "Start"), BotCommand("help", "Help")])
    except Exception:
        pass

def main():
    db_init()

    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_error_handler(error_handler)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(buttons))

    app.add_handler(MessageHandler(filters.TEXT | filters.VOICE, user_input))

    app.add_handler(PreCheckoutQueryHandler(pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))

    logger.info("MusicAi started (PTB v20 polling)")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()