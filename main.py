# -*- coding: utf-8 -*-
import os
import json
import asyncio
import logging
from typing import Dict, Any, Optional

import aiohttp
import stripe
import psycopg
from psycopg.rows import dict_row

from fastapi import FastAPI, Request, Header, HTTPException

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# -------------------------
# ENV
# -------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini").strip()

PIAPI_API_KEY = os.getenv("PIAPI_API_KEY", "").strip()
PIAPI_BASE_URL = os.getenv("PIAPI_BASE_URL", "").strip().rstrip("/")
PIAPI_GENERATE_PATH = os.getenv("PIAPI_GENERATE_PATH", "/suno/music").strip()  # <- если надо, меняй

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "").strip()
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()
STRIPE_SUCCESS_URL = os.getenv("STRIPE_SUCCESS_URL", "").strip()  # напр: https://t.me/your_bot
STRIPE_CANCEL_URL = os.getenv("STRIPE_CANCEL_URL", "").strip()    # напр: https://t.me/your_bot

# -------------------------
# Logging
# -------------------------
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("musicai")

# -------------------------
# Stripe setup
# -------------------------
if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

# Пакеты (цены в EUR, редактируй как хочешь)
PACKS = {
    "pack_1":  {"songs": 1,  "amount_eur": 6.00,  "title": "1 song"},
    "pack_5":  {"songs": 5,  "amount_eur": 25.00, "title": "5 songs"},
    "pack_30": {"songs": 30, "amount_eur": 50.00, "title": "30 songs"},
}

# -------------------------
# i18n (короткие кнопки/текст)
# -------------------------
LANGS = [
    ("ru", "Русский"),
    ("uk", "Українська"),
    ("pl", "Polski"),
    ("de", "Deutsch"),
    ("en", "English"),
    ("es", "Español"),
    ("fr", "Français"),
]

T = {
    "ru": {
        "choose_lang": "Выбери язык 👇",
        "menu_title": "Меню",
        "btn_create": "🎵 Создать песню",
        "btn_balance": "💼 Баланс",
        "btn_buy": "💳 Купить песни",
        "btn_help": "❓ Помощь",
        "ask_topic": "Напиши тему/историю/фразы для песни (можно голосом, но текстом надёжнее).",
        "choose_genre": "Выбери жанр:",
        "choose_mood": "Выбери настроение:",
        "demo_used": "Демо уже было. Для генерации нужна покупка пакета.",
        "no_balance": "Баланс пуст. Нажми «Купить песни».",
        "generating": "Генерирую… это может занять немного времени ⏳",
        "done_balance": "Готово ✅\nБаланс: {balance} песен(ы).",
        "buy_title": "Выбери пакет:",
        "buy_open": "Оплатить",
        "back": "⬅️ Назад",
    },
    "uk": {
        "choose_lang": "Обери мову 👇",
        "menu_title": "Меню",
        "btn_create": "🎵 Створити пісню",
        "btn_balance": "💼 Баланс",
        "btn_buy": "💳 Купити пісні",
        "btn_help": "❓ Допомога",
        "ask_topic": "Напиши тему/історію/фрази для пісні.",
        "choose_genre": "Обери жанр:",
        "choose_mood": "Обери настрій:",
        "demo_used": "Демо вже було. Для генерації потрібна покупка пакета.",
        "no_balance": "Баланс порожній. Натисни «Купити пісні».",
        "generating": "Генерую… ⏳",
        "done_balance": "Готово ✅\nБаланс: {balance} пісень.",
        "buy_title": "Обери пакет:",
        "buy_open": "Оплатити",
        "back": "⬅️ Назад",
    },
    "pl": {
        "choose_lang": "Wybierz język 👇",
        "menu_title": "Menu",
        "btn_create": "🎵 Stwórz piosenkę",
        "btn_balance": "💼 Saldo",
        "btn_buy": "💳 Kup piosenki",
        "btn_help": "❓ Pomoc",
        "ask_topic": "Napisz temat/historię/frazy do piosenki.",
        "choose_genre": "Wybierz gatunek:",
        "choose_mood": "Wybierz nastrój:",
        "demo_used": "Demo już było. Aby generować, kup pakiet.",
        "no_balance": "Brak salda. Kliknij „Kup piosenki”.",
        "generating": "Generuję… ⏳",
        "done_balance": "Gotowe ✅\nSaldo: {balance} piosenek.",
        "buy_title": "Wybierz pakiet:",
        "buy_open": "Zapłać",
        "back": "⬅️ Wstecz",
    },
    "de": {
        "choose_lang": "Sprache wählen 👇",
        "menu_title": "Menü",
        "btn_create": "🎵 Song erstellen",
        "btn_balance": "💼 Guthaben",
        "btn_buy": "💳 Songs kaufen",
        "btn_help": "❓ Hilfe",
        "ask_topic": "Schreibe Thema/Story/Phrasen für den Song.",
        "choose_genre": "Genre wählen:",
        "choose_mood": "Stimmung wählen:",
        "demo_used": "Demo wurde bereits genutzt. Bitte Paket kaufen.",
        "no_balance": "Kein Guthaben. Klicke „Songs kaufen“.",
        "generating": "Erstelle… ⏳",
        "done_balance": "Fertig ✅\nGuthaben: {balance} Songs.",
        "buy_title": "Paket wählen:",
        "buy_open": "Bezahlen",
        "back": "⬅️ Zurück",
    },
    "en": {
        "choose_lang": "Choose your language 👇",
        "menu_title": "Menu",
        "btn_create": "🎵 Create a song",
        "btn_balance": "💼 Balance",
        "btn_buy": "💳 Buy songs",
        "btn_help": "❓ Help",
        "ask_topic": "Send a topic/story/phrases for the song.",
        "choose_genre": "Choose a genre:",
        "choose_mood": "Choose a mood:",
        "demo_used": "Demo already used. Please buy a pack to generate.",
        "no_balance": "Balance is empty. Tap “Buy songs”.",
        "generating": "Generating… ⏳",
        "done_balance": "Done ✅\nBalance: {balance} song(s).",
        "buy_title": "Choose a pack:",
        "buy_open": "Pay",
        "back": "⬅️ Back",
    },
    "es": {
        "choose_lang": "Elige idioma 👇",
        "menu_title": "Menú",
        "btn_create": "🎵 Crear canción",
        "btn_balance": "💼 Balance",
        "btn_buy": "💳 Comprar canciones",
        "btn_help": "❓ Ayuda",
        "ask_topic": "Envía tema/historia/frases para la canción.",
        "choose_genre": "Elige género:",
        "choose_mood": "Elige estado de ánimo:",
        "demo_used": "El demo ya se usó. Compra un paquete.",
        "no_balance": "Balance vacío. Pulsa “Comprar canciones”.",
        "generating": "Generando… ⏳",
        "done_balance": "Listo ✅\nBalance: {balance} canción(es).",
        "buy_title": "Elige paquete:",
        "buy_open": "Pagar",
        "back": "⬅️ Atrás",
    },
    "fr": {
        "choose_lang": "Choisis la langue 👇",
        "menu_title": "Menu",
        "btn_create": "🎵 Créer une chanson",
        "btn_balance": "💼 Solde",
        "btn_buy": "💳 Acheter des chansons",
        "btn_help": "❓ Aide",
        "ask_topic": "Envoie un sujet/histoire/phrases pour la chanson.",
        "choose_genre": "Choisis un genre :",
        "choose_mood": "Choisis une humeur :",
        "demo_used": "La démo est déjà utilisée. Achète un pack.",
        "no_balance": "Solde vide. Clique “Acheter”.",
        "generating": "Génération… ⏳",
        "done_balance": "Terminé ✅\nSolde : {balance} chanson(s).",
        "buy_title": "Choisis un pack :",
        "buy_open": "Payer",
        "back": "⬅️ Retour",
    },
}

HELP_EN = (
    "Help (MusicAi)\n\n"
    "Changes & errors\n"
    "• Can I edit a finished song?\n"
    "  No — only generate again (−1 song from balance).\n"
    "• How many variants do I get?\n"
    "  Each generation produces two different variants (included in price).\n"
    "• Why wrong stress/pronunciation?\n"
    "  It’s a model limitation. You can mark stress with a CAPITAL letter (e.g., dIma).\n"
    "• Why voice/style changed?\n"
    "  Don’t use artist names. Describe genre, mood, tempo.\n\n"
    "Balance & payments\n"
    "• Payment completed but no songs?\n"
    "  Usually webhook delay. If it doesn’t appear, contact support.\n"
    "• Refunds?\n"
    "  Possible only for confirmed technical issues.\n"
    "• Why no free first song?\n"
    "  Generation costs resources. In the 30-pack, 1 song costs 1.66 €.\n\n"
    "Publishing\n"
    "• Can I publish on Instagram/YouTube/TikTok, etc.?\n"
    "  Yes — you can publish under your name or a pseudonym.\n\n"
    "Support: @Music_botsong"
)

# -------------------------
# Genres / moods
# (убрал: Инди, Народная, Шансон)
# -------------------------
GENRES = [
    "Pop", "Rap", "Hip-Hop", "Rock", "EDM", "House", "Techno", "Drum & Bass",
    "R&B", "Reggae", "Metal", "Lo-fi", "K-pop", "Latin"
]
MOODS = ["Happy", "Sad", "Romantic", "Aggressive", "Chill", "Epic", "Dark"]

# -------------------------
# DB helpers (sync, вызываем через asyncio.to_thread)
# -------------------------
def db_conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set")
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)

def init_db():
    with db_conn() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            lang TEXT NOT NULL DEFAULT 'en',
            balance INT NOT NULL DEFAULT 0,
            demo_used INT NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """)
        conn.commit()

def ensure_user(user_id: int):
    with db_conn() as conn:
        conn.execute("INSERT INTO users(user_id) VALUES(%s) ON CONFLICT DO NOTHING", (user_id,))
        conn.commit()

def set_lang(user_id: int, lang: str):
    with db_conn() as conn:
        conn.execute("INSERT INTO users(user_id) VALUES(%s) ON CONFLICT DO NOTHING", (user_id,))
        conn.execute("UPDATE users SET lang=%s WHERE user_id=%s", (lang, user_id))
        conn.commit()

def get_user(user_id: int) -> Dict[str, Any]:
    with db_conn() as conn:
        conn.execute("INSERT INTO users(user_id) VALUES(%s) ON CONFLICT DO NOTHING", (user_id,))
        row = conn.execute("SELECT * FROM users WHERE user_id=%s", (user_id,)).fetchone()
        return dict(row) if row else {"user_id": user_id, "lang": "en", "balance": 0, "demo_used": 0}

def add_balance(user_id: int, songs: int):
    with db_conn() as conn:
        conn.execute("INSERT INTO users(user_id) VALUES(%s) ON CONFLICT DO NOTHING", (user_id,))
        conn.execute("UPDATE users SET balance = balance + %s WHERE user_id=%s", (songs, user_id))
        conn.commit()

def consume_song(user_id: int) -> bool:
    with db_conn() as conn:
        conn.execute("INSERT INTO users(user_id) VALUES(%s) ON CONFLICT DO NOTHING", (user_id,))
        row = conn.execute("SELECT balance, demo_used FROM users WHERE user_id=%s", (user_id,)).fetchone()
        if not row:
            return False
        balance = int(row["balance"])
        demo_used = int(row["demo_used"])

        # первая генерация = демо 60 сек и баланс не списываем
        if demo_used == 0:
            conn.execute("UPDATE users SET demo_used=1 WHERE user_id=%s", (user_id,))
            conn.commit()
            return True

        if balance <= 0:
            return False

        conn.execute("UPDATE users SET balance = balance - 1 WHERE user_id=%s", (user_id,))
        conn.commit()
        return True

# -------------------------
# OpenRouter: lyrics
# -------------------------
async def openrouter_lyrics(topic: str, lang_code: str, genre: str, mood: str) -> str:
    if not OPENROUTER_API_KEY:
        # fallback
        return f"[Verse]\n{topic}\n\n[Chorus]\n{topic}\n"

    sys = (
        "You are a professional songwriter. Create structured song lyrics with sections.\n"
        "Return ONLY lyrics text.\n"
        "Use natural language, good rhymes if possible.\n"
    )
    user = (
        f"Language: {lang_code}\n"
        f"Genre: {genre}\n"
        f"Mood: {mood}\n"
        f"Topic/story: {topic}\n\n"
        "Write lyrics with: [Verse 1], [Chorus], [Verse 2], [Chorus], [Bridge], [Chorus]."
    )

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": sys},
            {"role": "user", "content": user},
        ],
        "temperature": 0.9,
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload, timeout=120) as r:
            data = await r.json()
            try:
                return data["choices"][0]["message"]["content"].strip()
            except Exception:
                return f"[Verse]\n{topic}\n\n[Chorus]\n{topic}\n"

# -------------------------
# PIAPI Suno Music (генерация)
# -------------------------
async def piapi_generate_music(lyrics: str, genre: str, mood: str, demo: bool) -> Dict[str, Any]:
    """
    Возвращаем dict с urls треков.
    ВАЖНО: endpoint может отличаться у твоего PIAPI.
    """
    if not (PIAPI_BASE_URL and PIAPI_API_KEY):
        raise RuntimeError("PIAPI_BASE_URL / PIAPI_API_KEY not set")

    url = f"{PIAPI_BASE_URL}{PIAPI_GENERATE_PATH}"
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": PIAPI_API_KEY,
    }

    # demo: 60 sec для первой песни
    payload = {
        "lyrics": lyrics,
        "tags": [genre, mood],
        "demo": bool(demo),          # если PIAPI не знает "demo" — убери это поле
        "max_duration": 60 if demo else 180,  # если PIAPI не знает — убери это поле
        "n_variants": 2,             # хотим 2 варианта
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload, timeout=300) as r:
            text = await r.text()
            if r.status >= 400:
                raise RuntimeError(f"PIAPI error {r.status}: {text}")
            try:
                return json.loads(text)
            except Exception:
                return {"raw": text}

def extract_audio_urls(piapi_resp: Dict[str, Any]) -> list:
    """
    Пытаемся достать audio url'ы из разных возможных форматов ответа.
    """
    urls = []

    # вариант: {"tracks":[{"audio_url":...}, ...]}
    if isinstance(piapi_resp, dict):
        tracks = piapi_resp.get("tracks")
        if isinstance(tracks, list):
            for t in tracks:
                if isinstance(t, dict):
                    for k in ("audio_url", "audioUrl", "url", "audio"):
                        v = t.get(k)
                        if isinstance(v, str) and v.startswith("http"):
                            urls.append(v)

        # вариант: {"data":{"tracks":[...]}}
        data = piapi_resp.get("data")
        if isinstance(data, dict):
            tracks = data.get("tracks")
            if isinstance(tracks, list):
                for t in tracks:
                    if isinstance(t, dict):
                        for k in ("audio_url", "audioUrl", "url", "audio"):
                            v = t.get(k)
                            if isinstance(v, str) and v.startswith("http"):
                                urls.append(v)

        # вариант: {"audio_url":"..."}
        for k in ("audio_url", "audioUrl", "url"):
            v = piapi_resp.get(k)
            if isinstance(v, str) and v.startswith("http"):
                urls.append(v)

    # уникальные, максимум 2
    uniq = []
    for u in urls:
        if u not in uniq:
            uniq.append(u)
    return uniq[:2]

# -------------------------
# Telegram UI
# -------------------------
def lang_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for code, name in LANGS:
        rows.append([InlineKeyboardButton(name, callback_data=f"lang:{code}")])
    return InlineKeyboardMarkup(rows)

def menu_keyboard(lang: str) -> InlineKeyboardMarkup:
    tr = T.get(lang, T["en"])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(tr["btn_create"], callback_data="menu:create")],
        [InlineKeyboardButton(tr["btn_buy"], callback_data="menu:buy")],
        [InlineKeyboardButton(tr["btn_balance"], callback_data="menu:balance")],
        [InlineKeyboardButton(tr["btn_help"], callback_data="menu:help")],
    ])

def genres_keyboard(lang: str) -> InlineKeyboardMarkup:
    rows = []
    for g in GENRES:
        rows.append([InlineKeyboardButton(g, callback_data=f"genre:{g}")])
    rows.append([InlineKeyboardButton(T.get(lang, T["en"])["back"], callback_data="menu:back")])
    return InlineKeyboardMarkup(rows)

def moods_keyboard(lang: str) -> InlineKeyboardMarkup:
    rows = []
    for m in MOODS:
        rows.append([InlineKeyboardButton(m, callback_data=f"mood:{m}")])
    rows.append([InlineKeyboardButton(T.get(lang, T["en"])["back"], callback_data="menu:back")])
    return InlineKeyboardMarkup(rows)

def buy_keyboard(lang: str, user_id: int) -> InlineKeyboardMarkup:
    tr = T.get(lang, T["en"])
    rows = []
    for pack_id, info in PACKS.items():
        title = f"€{info['amount_eur']:.2f} → {info['songs']}"
        rows.append([InlineKeyboardButton(title, callback_data=f"buy:{pack_id}")])
    rows.append([InlineKeyboardButton(tr["back"], callback_data="menu:back")])
    return InlineKeyboardMarkup(rows)

# -------------------------
# Stripe checkout
# -------------------------
def create_checkout_session(user_id: int, pack_id: str) -> str:
    if not STRIPE_SECRET_KEY:
        raise RuntimeError("STRIPE_SECRET_KEY not set")
    if not STRIPE_SUCCESS_URL or not STRIPE_CANCEL_URL:
        raise RuntimeError("STRIPE_SUCCESS_URL / STRIPE_CANCEL_URL not set")

    pack = PACKS[pack_id]
    amount_cents = int(round(pack["amount_eur"] * 100))

    session = stripe.checkout.Session.create(
        mode="payment",
        success_url=STRIPE_SUCCESS_URL,
        cancel_url=STRIPE_CANCEL_URL,
        line_items=[{
            "price_data": {
                "currency": "eur",
                "product_data": {"name": f"MusicAi - {pack['title']}"},
                "unit_amount": amount_cents,
            },
            "quantity": 1,
        }],
        metadata={
            "user_id": str(user_id),
            "pack": pack_id,
        }
    )
    return session.url

# -------------------------
# Telegram handlers
# -------------------------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await asyncio.to_thread(ensure_user, user_id)
    await update.message.reply_text(
        T["en"]["choose_lang"],
        reply_markup=lang_keyboard()
    )

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    user = await asyncio.to_thread(get_user, user_id)
    lang = user.get("lang", "en")
    tr = T.get(lang, T["en"])

    data = query.data or ""

    # Language choose
    if data.startswith("lang:"):
        lang_code = data.split(":", 1)[1]
        if lang_code not in [c for c, _ in LANGS]:
            lang_code = "en"
        await asyncio.to_thread(set_lang, user_id, lang_code)
        lang = lang_code
        tr = T.get(lang, T["en"])
        await query.edit_message_text(tr["menu_title"], reply_markup=menu_keyboard(lang))
        return

    # Main menu
    if data == "menu:back":
        await query.edit_message_text(tr["menu_title"], reply_markup=menu_keyboard(lang))
        return

    if data == "menu:balance":
        user = await asyncio.to_thread(get_user, user_id)
        bal = int(user.get("balance", 0))
        demo_used = int(user.get("demo_used", 0))
        await query.edit_message_text(
            f"{tr['btn_balance']}\n\nBalance: {bal}\nDemo used: {demo_used}",
            reply_markup=menu_keyboard(lang)
        )
        return

    if data == "menu:help":
        await query.edit_message_text(HELP_EN, reply_markup=menu_keyboard(lang))
        return

    if data == "menu:buy":
        await query.edit_message_text(tr["buy_title"], reply_markup=buy_keyboard(lang, user_id))
        return

    if data.startswith("buy:"):
        pack_id = data.split(":", 1)[1]
        if pack_id not in PACKS:
            await query.edit_message_text(tr["buy_title"], reply_markup=buy_keyboard(lang, user_id))
            return
        try:
            url = await asyncio.to_thread(create_checkout_session, user_id, pack_id)
        except Exception as e:
            await query.edit_message_text(f"Stripe error: {e}", reply_markup=menu_keyboard(lang))
            return

        await query.edit_message_text(
            f"{tr['buy_open']} 👇",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(tr["buy_open"], url=url)],
                                              [InlineKeyboardButton(tr["back"], callback_data="menu:back")]])
        )
        return

    if data == "menu:create":
        # step1: choose genre
        context.user_data["flow"] = {"step": "genre"}
        await query.edit_message_text(tr["choose_genre"], reply_markup=genres_keyboard(lang))
        return

    if data.startswith("genre:"):
        genre = data.split(":", 1)[1]
        context.user_data["flow"] = {"step": "mood", "genre": genre}
        await query.edit_message_text(tr["choose_mood"], reply_markup=moods_keyboard(lang))
        return

    if data.startswith("mood:"):
        mood = data.split(":", 1)[1]
        flow = context.user_data.get("flow") or {}
        genre = flow.get("genre", "Pop")
        context.user_data["flow"] = {"step": "topic", "genre": genre, "mood": mood}

        await query.edit_message_text(tr["ask_topic"])
        return

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = await asyncio.to_thread(get_user, user_id)
    lang = user.get("lang", "en")
    tr = T.get(lang, T["en"])

    flow = context.user_data.get("flow") or {}
    if flow.get("step") != "topic":
        # просто показываем меню
        await update.message.reply_text(tr["menu_title"], reply_markup=menu_keyboard(lang))
        return

    topic = (update.message.text or "").strip()
    if not topic:
        await update.message.reply_text(tr["ask_topic"])
        return

    genre = flow.get("genre", "Pop")
    mood = flow.get("mood", "Happy")

    # Проверяем демо/баланс
    ok = await asyncio.to_thread(consume_song, user_id)
    user_after = await asyncio.to_thread(get_user, user_id)

    demo_used = int(user_after.get("demo_used", 0))
    # demo_used == 1 и баланс не списан мог быть демо. Мы не знаем точно, поэтому считаем:
    # если до этого demo_used был 0, то сейчас демо = True
    demo = int(user.get("demo_used", 0)) == 0 and demo_used == 1

    if not ok:
        await update.message.reply_text(tr["no_balance"], reply_markup=menu_keyboard(lang))
        context.user_data["flow"] = {}
        return

    await update.message.reply_text(tr["generating"])

    try:
        lyrics = await openrouter_lyrics(topic=topic, lang_code=lang, genre=genre, mood=mood)
        piapi_resp = await piapi_generate_music(lyrics=lyrics, genre=genre, mood=mood, demo=demo)
        urls = extract_audio_urls(piapi_resp)

        if not urls:
            # если не смогли распарсить — покажем сырой ответ (коротко)
            raw = json.dumps(piapi_resp, ensure_ascii=False)[:1500]
            await update.message.reply_text("PIAPI response (no audio url found):\n" + raw)
        else:
            # отправляем 1-2 аудио
            for i, u in enumerate(urls, start=1):
                await update.message.reply_audio(audio=u, caption=f"Variant {i}\nLanguage: {lang}\nGenre: {genre}\nMood: {mood}")

        # баланс после
        user_final = await asyncio.to_thread(get_user, user_id)
        bal = int(user_final.get("balance", 0))
        await update.message.reply_text(tr["done_balance"].format(balance=bal), reply_markup=menu_keyboard(lang))

    except Exception as e:
        log.exception("Generation error")
        # если ошибка — возвращаем "песню" обратно, если это НЕ демо
        # (чтобы не было списаний без результата)
        if not demo:
            await asyncio.to_thread(add_balance, user_id, 1)
        await update.message.reply_text(f"Error: {e}", reply_markup=menu_keyboard(lang))

    finally:
        context.user_data["flow"] = {}

# -------------------------
# FastAPI (Stripe webhook)
# -------------------------
app = FastAPI()

@app.on_event("startup")
def _startup():
    init_db()
    log.info("DB ready")

@app.post("/stripe/webhook")
async def stripe_webhook(request: Request, stripe_signature: str = Header(None)):
    if not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=500, detail="STRIPE_WEBHOOK_SECRET not set")

    payload = await request.body()
    if not stripe_signature:
        raise HTTPException(status_code=400, detail="Missing Stripe-Signature header")

    try:
        event = stripe.Webhook.construct_event(payload, stripe_signature, STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid signature: {e}")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        meta = session.get("metadata") or {}
        user_id = meta.get("user_id")
        pack_id = meta.get("pack")

        if user_id and pack_id in PACKS:
            songs = int(PACKS[pack_id]["songs"])
            await asyncio.to_thread(add_balance, int(user_id), songs)

    return {"ok": True}

# -------------------------
# Run Telegram bot inside same process
# -------------------------
telegram_app: Optional[Application] = None

@app.on_event("startup")
async def start_telegram_bot():
    global telegram_app
    if not BOT_TOKEN:
        log.warning("BOT_TOKEN not set — telegram bot will not start")
        return

    telegram_app = Application.builder().token(BOT_TOKEN).build()

    telegram_app.add_handler(CommandHandler("start", cmd_start))
    telegram_app.add_handler(CallbackQueryHandler(on_callback))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    # запускаем polling как background task
    async def _run():
        await telegram_app.initialize()
        await telegram_app.start()
        await telegram_app.updater.start_polling(drop_pending_updates=True)
        log.info("Telegram bot started (polling)")

    asyncio.create_task(_run())
