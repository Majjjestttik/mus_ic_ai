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
PIAPI_KEY = os.getenv("PIAPI_KEY")  # put WITHOUT "sk", just the token as you have it
OWNER_ID = int(os.getenv("OWNER_TG_ID", "0"))
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
    try:
        state = json.loads(row[4] or "{}")
    except Exception:
        state = {}
    return {"user_id": row[0], "lang": row[1], "demo_used": row[2], "songs": row[3], "state": state}

def db_set(user_id: int, lang: str = None, demo_used: int = None, songs: int = None, state: dict = None) -> None:
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    cur.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO users(user_id, lang, demo_used, songs, state_json, updated_at) VALUES(?,?,?,?,?,?)",
            (user_id, "en", 0, 0, "{}", int(time.time())),
        )

    now = int(time.time())
    if state is not None:
        state_json = json.dumps(state, ensure_ascii=False)
        cur.execute("UPDATE users SET state_json=?, updated_at=? WHERE user_id=?", (state_json, now, user_id))
    if lang is not None:
        cur.execute("UPDATE users SET lang=?, updated_at=? WHERE user_id=?", (lang, now, user_id))
    if demo_used is not None:
        cur.execute("UPDATE users SET demo_used=?, updated_at=? WHERE user_id=?", (demo_used, now, user_id))
    if songs is not None:
        cur.execute("UPDATE users SET songs=?, updated_at=? WHERE user_id=?", (songs, now, user_id))

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
    "custom_theme_ask": {
        "en": "✏️ Write your custom theme in one phrase (example: “About my best friend”).",
        "ru": "✏️ Напиши свой вариант темы одной фразой (пример: «Про лучшего друга»).",
        "pl": "✏️ Napisz własny temat jednym zdaniem (np. „O moim najlepszym przyjacielu”).",
        "de": "✏️ Schreibe dein eigenes Thema in einem Satz (z.B. „Über meinen besten Freund”).",
        "es": "✏️ Escribe tu tema en una frase (ej.: “Sobre mi mejor amigo”).",
        "fr": "✏️ Écris ton thème en une phrase (ex. « À propos de mon meilleur ami »).",
        "uk": "✏️ Напиши свій варіант теми одним реченням (приклад: «Про найкращого друга»).",
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
    "temp_error": {
        "en": "⚠️ Temporary error. Please try again later.",
        "ru": "⚠️ Временная ошибка. Попробуй позже.",
        "pl": "⚠️ Błąd tymczasowy. Spróbuj później.",
        "de": "⚠️ Vorübergehender Fehler. Bitte später erneut.",
        "es": "⚠️ Error temporal. Inténtalo más tarde.",
        "fr": "⚠️ Erreur temporaire. Réessaie plus tard.",
        "uk": "⚠️ Тимчасова помилка. Спробуй пізніше.",
    },
    "help": {
        "en": "ℹ️ *Help*\n\n✏️ Can I edit a ready song?\nNo — only generate again (−1 song).\n\n🎶 How many variants?\nYou get 2 different variants per request.\n\n🔉 Stress / diction issues?\nWrite stress with CAPS: dIma, natAsha.\n\n📄 Rights\nThe songs belong to you. You can publish in any social network.",
        "ru": "ℹ️ *Help*\n\n✏️ Можно ли изменить готовую песню?\nНет — только сгенерировать заново (−1 песня).\n\n🎶 Сколько вариантов?\n2 разных варианта на один запрос.\n\n🔉 Ударения/дикция?\nПиши ударение КАПСОМ: дИма, натАша.\n\n📄 Права\nПесни принадлежат тебе. Можно публиковать в любой социальной сети.",
        "pl": "ℹ️ *Help*\n\n✏️ Czy mogę edytować gotową piosenkę?\nNie — tylko wygenerować ponownie (−1 piosenka).\n\n🎶 Ile wariantów?\n2 różne warianty na jedno zamówienie.\n\n🔉 Akcent / dykcja?\nZaznacz akcent WIELKIMI literami.\n\n📄 Prawa\nPiosenki należą do Ciebie. Możesz publikować w każdej sieci społecznościowej.",
        "de": "ℹ️ *Help*\n\n✏️ Kann ich einen fertigen Song ändern?\nNein — nur neu generieren (−1 Song).\n\n🎶 Wie viele Varianten?\n2 verschiedene Varianten pro Anfrage.\n\n🔉 Betonung/Diktion?\nBetonung mit GROSSBUCHSTABEN.\n\n📄 Rechte\nDie Songs gehören dir. Du kannst sie in jedem sozialen Netzwerk posten.",
        "es": "ℹ️ *Help*\n\n✏️ ¿Puedo editar una canción lista?\nNo — solo generar de nuevo (−1 canción).\n\n🎶 ¿Cuántas variantes?\n2 variantes diferentes por solicitud.\n\n🔉 Acentos/dicción?\nMarca el acento con MAYÚSCULAS.\n\n📄 Derechos\nLas canciones son tuyas. Puedes publicarlas en cualquier red social.",
        "fr": "ℹ️ *Help*\n\n✏️ Puis-je modifier une chanson prête ?\nNon — seulement régénérer (−1 chanson).\n\n🎶 Combien de variantes ?\n2 variantes différentes par demande.\n\n🔉 Accents/diction ?\nMarque l’accent en MAJUSCULES.\n\n📄 Droits\nLes chansons t’appartiennent. Tu peux publier sur n’importe quel réseau social.",
        "uk": "ℹ️ *Help*\n\n✏️ Чи можна змінити готову пісню?\nНі — лише згенерувати заново (−1 пісня).\n\n🎶 Скільки варіантів?\n2 різні варіанти на один запит.\n\n🔉 Наголос/дикція?\nПозначай наголос ВЕЛИКИМИ літерами.\n\n📄 Права\nПісні належать тобі. Можна публікувати в будь-якій соцмережі.",
    },
}

THEMES = {
    "love":    {"en":"Love ❤️","ru":"Любовь ❤️","pl":"Miłość ❤️","de":"Liebe ❤️","es":"Amor ❤️","fr":"Amour ❤️","uk":"Кохання ❤️"},
    "fun":     {"en":"Funny 😄","ru":"Смешная 😄","pl":"Zabawna 😄","de":"Lustig 😄","es":"Divertida 😄","fr":"Drôle 😄","uk":"Весела 😄"},
    "holiday": {"en":"Holiday 🎉","ru":"Праздник 🎉","pl":"Święto 🎉","de":"Feier 🎉","es":"Fiesta 🎉","fr":"Fête 🎉","uk":"Свято 🎉"},
    "sad":     {"en":"Sad 😢","ru":"Грусть 😢","pl":"Smutna 😢","de":"Traurig 😢","es":"Triste 😢","fr":"Triste 😢","uk":"Сум 😢"},
    "wedding": {"en":"Wedding 💍","ru":"Свадьба 💍","pl":"Wesele 💍","de":"Hochzeit 💍","es":"Boda 💍","fr":"Mariage 💍","uk":"Весілля 💍"},
    "custom":  {"en":"Custom ✏️","ru":"Свой вариант ✏️","pl":"Własny wariant ✏️","de":"Eigene Variante ✏️","es":"Tu opción ✏️","fr":"Votre option ✏️","uk":"Свій варіант ✏️"},
}

HELP_BTN = {
    "en": "Help ℹ️",
    "ru": "Помощь ℹ️",
    "pl": "Pomoc ℹ️",
    "de": "Hilfe ℹ️",
    "es": "Ayuda ℹ️",
    "fr": "Aide ℹ️",
    "uk": "Допомога ℹ️",
}

def tr(lang: str, key: str) -> str:
    return TEXTS.get(key, {}).get(lang, TEXTS.get(key, {}).get("en", "Text missing"))

def help_btn(lang: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(HELP_BTN.get(lang, "Help ℹ️"), callback_data="help")

# -------------------- PIAPI CALL (FIXED) --------------------
async def piapi_generate(prompt: str) -> Optional[str]:
    url = "https://api.piapi.ai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {PIAPI_KEY}", "Content-Type": "application/json"}
    payload = {"model": "pi-music", "messages": [{"role": "user", "content": prompt}]}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=120) as r:
                text_body = await r.text()

                # try json
                try:
                    data = json.loads(text_body)
                except Exception:
                    logger.error("PiAPI non-JSON response (%s): %s", r.status, text_body[:2000])
                    return None

                # common formats
                if isinstance(data, dict):
                    if "choices" in data and data["choices"]:
                        try:
                            return data["choices"][0]["message"]["content"]
                        except Exception:
                            pass

                    if "text" in data and isinstance(data["text"], str):
                        return data["text"]

                    if "result" in data and isinstance(data["result"], str):
                        return data["result"]

                    if "data" in data and isinstance(data["data"], dict):
                        if "output" in data["data"] and isinstance(data["data"]["output"], str):
                            return data["data"]["output"]

                logger.error("PiAPI unknown response (%s): %s", r.status, text_body[:2000])
                return None

    except Exception as e:
        logger.error("PiAPI Error: %s", e, exc_info=True)
        return None

# -------------------- VOICE -> TEXT (OpenAI Whisper, optional) --------------------
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
        logger.error("OpenAI Whisper Error: %s", e, exc_info=True)
        return None

# -------------------- UI KEYBOARDS --------------------
def kb_languages(lang_for_help: str) -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton("English 🇬🇧", callback_data="lang_en"), InlineKeyboardButton("Русский 🇷🇺", callback_data="lang_ru")],
        [InlineKeyboardButton("Polski 🇵🇱", callback_data="lang_pl"), InlineKeyboardButton("Deutsch 🇩🇪", callback_data="lang_de")],
        [InlineKeyboardButton("Español 🇪🇸", callback_data="lang_es"), InlineKeyboardButton("Français 🇫🇷", callback_data="lang_fr")],
        [InlineKeyboardButton("Українська 🇺🇦", callback_data="lang_uk")],
        [help_btn(lang_for_help)],
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

# -------------------- ERROR HANDLER --------------------
async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Unhandled error: %s", context.error, exc_info=True)

# -------------------- HANDLERS --------------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = await adb_get_user(uid)
    lang = u["lang"] or "en"
    # reset flow state
    await adb_set(uid, state={})
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("▶️ START", callback_data="start")],
        [help_btn(lang)],
    ])
    await update.message.reply_text(tr(lang, "start"), reply_markup=kb, parse_mode="Markdown")

async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    u = await adb_get_user(uid)
    lang = (u["lang"] or "en")
    state = (u["state"] or {})

    data = q.data

    if data == "help":
        await q.message.reply_text(tr(lang, "help"), parse_mode="Markdown")
        return

    if data == "start":
        # show language selection
        await q.edit_message_text(tr(lang, "choose_language"), reply_markup=kb_languages(lang))
        return

    if data.startswith("lang_"):
        new_lang = data[5:]
        if new_lang not in LANGS:
            new_lang = "en"

        # IMPORTANT: don't wipe state, just update
        state["lang"] = new_lang
        state.pop("theme", None)
        state.pop("genre", None)
        state.pop("awaiting_custom_theme", None)
        state.pop("custom_theme", None)

        await adb_set(uid, lang=new_lang, state=state)
        await q.edit_message_text(tr(new_lang, "choose_theme"), reply_markup=kb_themes(new_lang))
        return

    if data.startswith("theme_"):
        theme_key = data[6:]
        # if custom -> ask text
        if theme_key == "custom":
            state["theme"] = "custom"
            state["awaiting_custom_theme"] = True
            await adb_set(uid, state=state)
            await q.edit_message_text(tr(lang, "custom_theme_ask"), reply_markup=InlineKeyboardMarkup([[help_btn(lang)]]))
            return

        state["theme"] = theme_key
        state.pop("awaiting_custom_theme", None)
        state.pop("custom_theme", None)
        await adb_set(uid, state=state)
        await q.edit_message_text(tr(lang, "choose_genre"), reply_markup=kb_genres(lang))
        return

    if data.startswith("genre_"):
        genre = data[6:]
        state["genre"] = genre
        await adb_set(uid, state=state)
        await q.edit_message_text(tr(lang, "describe"), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[help_btn(lang)]]))
        return

    if data.startswith("buy_"):
        pack = data.split("_", 1)[1]
        stars = PACKS.get(pack)
        if not stars:
            return

        state["buy_pack"] = pack
        await adb_set(uid, state=state)

        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Yes", callback_data=f"pay_{pack}"),
            InlineKeyboardButton("❌ No", callback_data="start"),
        ]])
        await q.edit_message_text(tr(lang, "buy_confirm").format(stars=stars), reply_markup=kb, parse_mode="Markdown")
        return

    if data.startswith("pay_"):
        pack = data.split("_", 1)[1]
        stars = PACKS.get(pack)
        if not stars:
            return

        # Telegram Stars invoice. provider_token must be empty string for XTR
        await context.bot.send_invoice(
            chat_id=uid,
            title="MusicAi — Songs pack",
            description=f"{pack} song(s) added to your balance",
            payload=f"pack_{pack}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice("Stars", stars)],
        )
        return

async def user_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = await adb_get_user(uid)
    lang = (u["lang"] or "en")
    state = (u["state"] or {})

    # handle custom theme text step
    if state.get("awaiting_custom_theme"):
        txt = (update.message.text or "").strip()
        if not txt:
            await update.message.reply_text(tr(lang, "custom_theme_ask"), reply_markup=InlineKeyboardMarkup([[help_btn(lang)]]))
            return
        state["custom_theme"] = txt
        state["awaiting_custom_theme"] = False
        await adb_set(uid, state=state)
        await update.message.reply_text(tr(lang, "choose_genre"), reply_markup=kb_genres(lang))
        return

    # must have genre chosen
    if "genre" not in state:
        await update.message.reply_text(tr(lang, "need_start"))
        return

    # get prompt text
    prompt_text = ""
    if update.message.voice:
        wait = await update.message.reply_text(tr(lang, "generating"))
        try:
            file = await context.bot.get_file(update.message.voice.file_id)
            path = f"v_{uid}.ogg"
            await file.download_to_drive(path)
            prompt_text = await voice_to_text(path)
            try:
                os.remove(path)
            except Exception:
                pass
        except Exception:
            prompt_text = None

        if not prompt_text:
            # fallback: if no OpenAI key or whisper failed
            await wait.edit_text(tr(lang, "temp_error"))
            return

        await wait.delete()
    else:
        prompt_text = (update.message.text or "").strip()

    if not prompt_text:
        await update.message.reply_text(tr(lang, "temp_error"))
        return

    demo_used = int(u["demo_used"] or 0)
    songs = int(u["songs"] or 0)

    # build prompt
    theme_part = state.get("theme", "love")
    if theme_part == "custom":
        theme_part = state.get("custom_theme", "custom")

    base_info = (
        f"Language: {state.get('lang', lang)}\n"
        f"Theme: {theme_part}\n"
        f"Genre: {state.get('genre')}\n"
        f"User description: {prompt_text}\n"
        f"IMPORTANT: Return 2 different variants.\n"
    )

    # demo once
    if demo_used == 0:
        msg = await update.message.reply_text(tr(lang, "generating"))
        res = await piapi_generate("Create a SHORT DEMO (~1 minute). " + base_info)
        if res:
            await msg.edit_text(f"{tr(lang, 'demo_header')}\n\n{res[:3500]}", parse_mode="Markdown")
            await adb_set(uid, demo_used=1)
        else:
            await msg.edit_text(tr(lang, "temp_error"))
        return

    # full song requires credits
    if songs > 0:
        msg = await update.message.reply_text(tr(lang, "generating"))
        res = await piapi_generate("Create a FULL song. " + base_info)
        if res:
            await msg.edit_text(res[:3900])
            await adb_set(uid, songs=songs - 1)
        else:
            await msg.edit_text(tr(lang, "temp_error"))
        return

    # no credits -> buy
    await update.message.reply_text(tr(lang, "no_credits"), reply_markup=kb_buy(lang))

async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = await adb_get_user(uid)

    payload = update.message.successful_payment.invoice_payload or ""
    pack = payload.replace("pack_", "").strip()

    if pack not in PACKS:
        # unknown payload, do nothing but don't crash
        await update.message.reply_text(tr(u["lang"], "paid"))
        return

    current = int(u["songs"] or 0)
    await adb_set(uid, songs=current + int(pack))

    await update.message.reply_text(tr(u["lang"], "paid"))

    # optional notify owner
    if OWNER_ID:
        try:
            user = update.effective_user
            uname = f"@{user.username}" if user.username else "(no username)"
            await context.bot.send_message(
                OWNER_ID,
                f"⭐ Payment: {pack} song(s) from {uname} (id={user.id}). New balance: {current + int(pack)}",
            )
        except Exception:
            pass

async def post_init(app):
    # nice menu commands
    try:
        await app.bot.set_my_commands([
            BotCommand("start", "Start / Restart"),
            BotCommand("help", "Help"),
        ])
    except Exception:
        pass

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = await adb_get_user(uid)
    lang = u["lang"] or "en"
    await update.message.reply_text(tr(lang, "help"), parse_mode="Markdown")

def main():
    db_init()
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_error_handler(on_error)
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT | filters.VOICE, user_input))
    app.add_handler(PreCheckoutQueryHandler(pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))

    logger.info("Bot started")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()