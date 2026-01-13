# -*- coding: utf-8 -*-
"""
MusicAi PRO (Telegram bot) + Telegram Stars payments (XTR)
- python-telegram-bot v21+ (async)
- OpenRouter Chat Completions (LLM)
- SQLite user settings + credits
- Buttons: language, genre, mood, etc.
- Payments: sendInvoice (XTR), pre_checkout_query, successful_payment
"""

import os
import re
import json
import time
import asyncio
import logging
import sqlite3
from dataclasses import dataclass
from typing import Dict, Any, Tuple, List

import aiohttp
from dotenv import load_dotenv

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    PreCheckoutQueryHandler,
    filters,
)

# =========================
# ENV
# =========================
# On Render you can skip .env entirely and use Environment Variables,
# but load_dotenv() won't hurt locally.
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini").strip()

PIAPI_API_KEY = os.getenv("PIAPI_API_KEY", "").strip()

ADMIN_ID = int((os.getenv("ADMIN_ID", "0") or "0").strip())

if not TELEGRAM_TOKEN:
    raise RuntimeError("❌ TELEGRAM_TOKEN is missing (Render Env Vars or .env)")

# =========================
# LOGGING
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("MusicAiPRO")

# =========================
# DB
# =========================
DB_PATH = "musicai.db"


def db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def start_of_day_ts(ts: int) -> int:
    return ts - (ts % 86400)


def db_init():
    conn = db_connect()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        created_at INTEGER NOT NULL,
        last_seen INTEGER NOT NULL,

        lang TEXT NOT NULL DEFAULT 'ru',
        song_language TEXT NOT NULL DEFAULT 'ru',
        genre TEXT NOT NULL DEFAULT 'pop',
        mood TEXT NOT NULL DEFAULT 'neutral',
        vocal TEXT NOT NULL DEFAULT 'male',
        energy TEXT NOT NULL DEFAULT 'medium',
        structure TEXT NOT NULL DEFAULT 'classic',
        rhyme TEXT NOT NULL DEFAULT 'yes',

        credits INTEGER NOT NULL DEFAULT 1,  -- starter credits

        cooldown_until INTEGER NOT NULL DEFAULT 0,
        daily_count INTEGER NOT NULL DEFAULT 0,
        daily_reset INTEGER NOT NULL DEFAULT 0
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        ts INTEGER NOT NULL,
        prompt TEXT NOT NULL,
        response TEXT NOT NULL
    );
    """)

    conn.commit()

    # If upgrading old DB without credits column, add it
    try:
        cur.execute("SELECT credits FROM users LIMIT 1;")
    except sqlite3.OperationalError:
        cur.execute("ALTER TABLE users ADD COLUMN credits INTEGER NOT NULL DEFAULT 1;")
        conn.commit()

    conn.close()


def now_ts() -> int:
    return int(time.time())


def user_ensure(user_id: int):
    now = now_ts()
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    if not row:
        cur.execute(
            "INSERT INTO users (user_id, created_at, last_seen, daily_reset) VALUES (?, ?, ?, ?)",
            (user_id, now, now, start_of_day_ts(now))
        )
    else:
        cur.execute("UPDATE users SET last_seen=? WHERE user_id=?", (now, user_id))
    conn.commit()
    conn.close()


def user_get(user_id: int) -> Dict[str, Any]:
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else {}


def user_set(user_id: int, **fields):
    if not fields:
        return
    conn = db_connect()
    cur = conn.cursor()
    keys = list(fields.keys())
    vals = [fields[k] for k in keys]
    set_clause = ", ".join([f"{k}=?" for k in keys])
    cur.execute(f"UPDATE users SET {set_clause} WHERE user_id=?", (*vals, user_id))
    conn.commit()
    conn.close()


def history_add(user_id: int, prompt: str, response: str):
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO history (user_id, ts, prompt, response) VALUES (?, ?, ?, ?)",
        (user_id, now_ts(), prompt[:4000], response[:20000])
    )
    conn.commit()
    conn.close()


def history_last(user_id: int, limit: int = 5) -> List[Dict[str, Any]]:
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT ts, prompt, response FROM history WHERE user_id=? ORDER BY id DESC LIMIT ?",
        (user_id, limit)
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# =========================
# LIMITS
# =========================
DAILY_LIMIT = 200
COOLDOWN_SECONDS = 3
MAX_USER_TEXT = 800
MAX_TG_MESSAGE = 3900


def normalize_user_text(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s


def split_text(text: str, chunk: int = MAX_TG_MESSAGE) -> List[str]:
    if len(text) <= chunk:
        return [text]
    return [text[i:i + chunk] for i in range(0, len(text), chunk)]


def ensure_daily_limits(user_id: int) -> Tuple[bool, str]:
    u = user_get(user_id)
    now = now_ts()

    reset_ts = int(u.get("daily_reset") or 0)
    if reset_ts <= 0:
        user_set(user_id, daily_reset=start_of_day_ts(now), daily_count=0)
        reset_ts = start_of_day_ts(now)

    if start_of_day_ts(now) != reset_ts:
        user_set(user_id, daily_reset=start_of_day_ts(now), daily_count=0)

    u = user_get(user_id)
    if int(u.get("daily_count") or 0) >= DAILY_LIMIT:
        return False, "daily_limit"

    if now < int(u.get("cooldown_until") or 0):
        return False, "cooldown"

    return True, ""


def bump_usage(user_id: int):
    u = user_get(user_id)
    now = now_ts()
    user_set(
        user_id,
        daily_count=int(u.get("daily_count") or 0) + 1,
        cooldown_until=now + COOLDOWN_SECONDS
    )


# =========================
# UI TEXT
# =========================
TXT = {
    "ru": {
        "start": "🎵 *MusicAi PRO*\n\nНапиши тему песни одним сообщением.\n\nТакже можно настроить жанр/язык кнопками.\n\n⭐ Оплата: генерации списывают *1 credit*. Купи кредиты через *Stars*.",
        "help": "Команды:\n"
                "/start — меню\n"
                "/settings — настройки\n"
                "/history — история\n"
                "/reset — сброс\n"
                "/buy — купить кредиты (Stars)\n\n"
                "Просто напиши тему песни — я верну текст + *Style Prompt* для Suno.\n\n"
                "При наличии PIAPI_API_KEY можно генерировать музыку (до 60 сек).",
        "need_topic": "Напиши тему/идею песни одним сообщением 🙂",
        "busy": "⏳ Генерирую…",
        "no_key": "❌ Нет OPENROUTER_API_KEY. Добавь ключ в Render → Environment Variables и перезапусти сервис.",
        "cooldown": "⏳ Слишком часто. Подожди немного.",
        "daily_limit": "🚫 Дневной лимит исчерпан. Попробуй завтра.",
        "settings": "⚙️ *Настройки*\n\nВыбери параметры — они сохраняются.",
        "saved": "✅ Сохранено.",
        "reset": "♻️ Сбросил настройки к стандартным.",
        "history": "🕘 *История (последние)*",
        "history_empty": "История пустая.",
        "gen_error": "❌ Ошибка генерации. Попробуй позже.",
        "no_credits": "🚫 Нет кредитов. Нажми ⭐ *Buy* и оплати Stars, потом попробуй снова.",
        "credits": "⭐ Credits: *{credits}*",
        "buy_title": "⭐ Купить кредиты",
        "buy_text": "Выбери пакет. Оплата в Telegram Stars (XTR). После оплаты кредиты начислятся автоматически.",
        "buy_ok": "✅ Оплата прошла! Начислил кредиты: +{add}. Сейчас у тебя: {credits}.",
        "buy_fail": "❌ Оплата не прошла или отменена.",
        "music_generating": "🎵 Создаю музыку через PIAPI (Suno)...",
        "music_success": "✅ Музыка создана! Task ID: {task_id}",
        "music_error": "❌ Ошибка создания музыки через PIAPI.",
    },
    "en": {
        "start": "🎵 *MusicAi PRO*\n\nSend a song topic in one message.\n\n⭐ Billing: each generation costs *1 credit*. Buy credits with *Telegram Stars*.",
        "help": "Commands:\n"
                "/start — menu\n"
                "/settings — settings\n"
                "/history — history\n"
                "/reset — reset\n"
                "/buy — buy credits (Stars)\n\n"
                "Send a topic — I will return lyrics + *Suno Style Prompt*.\n\n"
                "With PIAPI_API_KEY you can generate music (up to 60 sec).",
        "need_topic": "Send a song topic in one message 🙂",
        "busy": "⏳ Generating…",
        "no_key": "❌ Missing OPENROUTER_API_KEY. Add it in Render → Environment Variables and restart.",
        "cooldown": "⏳ Too fast. Please wait.",
        "daily_limit": "🚫 Daily limit reached. Try tomorrow.",
        "settings": "⚙️ *Settings*\n\nChoose options — they are saved.",
        "saved": "✅ Saved.",
        "reset": "♻️ Reset to defaults.",
        "history": "🕘 *History (last)*",
        "history_empty": "History is empty.",
        "gen_error": "❌ Generation error. Try later.",
        "no_credits": "🚫 No credits. Tap ⭐ *Buy* and pay with Stars, then retry.",
        "credits": "⭐ Credits: *{credits}*",
        "buy_title": "⭐ Buy credits",
        "buy_text": "Choose a pack. Payment in Telegram Stars (XTR). Credits are added automatically after payment.",
        "buy_ok": "✅ Payment successful! Added credits: +{add}. You now have: {credits}.",
        "buy_fail": "❌ Payment failed or canceled.",
        "music_generating": "🎵 Creating music via PIAPI (Suno)...",
        "music_success": "✅ Music created! Task ID: {task_id}",
        "music_error": "❌ Error creating music via PIAPI.",
    }
}


def tr(u: Dict[str, Any], key: str) -> str:
    lang = (u.get("lang") or "ru").lower()
    return TXT.get(lang, TXT["ru"]).get(key, TXT["ru"].get(key, key))


def format_settings(u: Dict[str, Any]) -> str:
    return (
        f"UI: {u.get('lang')}\n"
        f"Song language: {u.get('song_language')}\n"
        f"Genre: {u.get('genre')}\n"
        f"Mood: {u.get('mood')}\n"
        f"Vocal: {u.get('vocal')}\n"
        f"Energy: {u.get('energy')}\n"
        f"Structure: {u.get('structure')}\n"
        f"Rhyme: {u.get('rhyme')}\n"
        f"Credits: {u.get('credits')}\n"
    )


# =========================
# OPTIONS
# =========================
LANG_UI = [("Русский", "ru"), ("English", "en")]

SONG_LANG = [
    ("Русский", "ru"),
    ("Polski", "pl"),
    ("English", "en"),
    ("Deutsch", "de"),
    ("Español", "es"),
    ("Italiano", "it"),
    ("Français", "fr"),
]

GENRES = [
    ("Pop", "pop"),
    ("Disco Polo", "disco_polo"),
    ("Rap/Hip-Hop", "rap"),
    ("Rock", "rock"),
    ("EDM", "edm"),
    ("Ballad", "ballad"),
    ("Reggaeton", "reggaeton"),
    ("Synthwave", "synthwave"),
]

MOODS = [
    ("Happy", "happy"),
    ("Sad", "sad"),
    ("Romantic", "romantic"),
    ("Party", "party"),
    ("Dark", "dark"),
    ("Neutral", "neutral"),
]

VOCALS = [
    ("Male", "male"),
    ("Female", "female"),
    ("Duo", "duo"),
    ("No preference", "any"),
]

ENERGY = [
    ("Low", "low"),
    ("Medium", "medium"),
    ("High", "high"),
]

STRUCTURES = [
    ("Classic", "classic"),
    ("Short (TikTok)", "short"),
    ("Extended", "extended"),
]

RHYME = [
    ("Yes", "yes"),
    ("No (free)", "no"),
]

# =========================
# STARS PACKS (edit here)
# amount = Stars (XTR) integer
# credits_add = how many generations user gets
# =========================
STARS_PACKS = {
    "p1": {"title_ru": "5 генераций", "title_en": "5 generations", "amount_xtr": 25, "credits_add": 5},
    "p2": {"title_ru": "25 генераций", "title_en": "25 generations", "amount_xtr": 90, "credits_add": 25},
    "p3": {"title_ru": "100 генераций", "title_en": "100 generations", "amount_xtr": 300, "credits_add": 100},
}


# =========================
# PROMPT BUILDER
# =========================
def build_system_prompt(u: Dict[str, Any]) -> str:
    structure = u.get("structure", "classic")
    if structure == "short":
        structure_text = "[Intro]\n[Verse 1]\n[Chorus]\n[Verse 2]\n[Chorus]\n[Outro]"
    elif structure == "extended":
        structure_text = "[Intro]\n[Verse 1]\n[Pre-Chorus]\n[Chorus]\n[Verse 2]\n[Pre-Chorus]\n[Chorus]\n[Bridge]\n[Chorus]\n[Outro]"
    else:
        structure_text = "[Intro]\n[Verse 1]\n[Chorus]\n[Verse 2]\n[Bridge]\n[Chorus]\n[Outro]"

    rhyme = u.get("rhyme", "yes")
    rhyme_text = "с чёткой рифмой" if rhyme == "yes" else "без строгой рифмы (свободный стих), но музыкально"

    song_lang = (u.get("song_language") or "ru").lower()
    lang_hint = {
        "ru": "Русский",
        "pl": "Polish",
        "en": "English",
        "de": "Deutsch",
        "es": "Español",
        "it": "Italiano",
        "fr": "Français",
    }.get(song_lang, "Русский")

    genre = u.get("genre", "pop")
    mood = u.get("mood", "neutral")
    vocal = u.get("vocal", "male")
    energy = u.get("energy", "medium")

    genre_map = {
        "pop": "Pop",
        "disco_polo": "Polish Disco Polo",
        "rap": "Hip-Hop / Rap",
        "rock": "Rock",
        "edm": "EDM",
        "ballad": "Pop Ballad",
        "reggaeton": "Reggaeton",
        "synthwave": "Synthwave",
    }
    mood_map = {
        "happy": "Happy",
        "sad": "Melancholic",
        "romantic": "Romantic",
        "party": "Party",
        "dark": "Dark",
        "neutral": "Neutral",
    }
    vocal_map = {
        "male": "Male Vocal",
        "female": "Female Vocal",
        "duo": "Duet Vocals",
        "any": "Vocal",
    }
    energy_map = {"low": "Low Energy", "medium": "Medium Energy", "high": "High Energy"}

    style_prompt = (
        f"Style: {genre_map.get(genre, 'Pop')}, "
        f"{vocal_map.get(vocal, 'Male Vocal')}, "
        f"{mood_map.get(mood, 'Neutral')}, "
        f"{energy_map.get(energy, 'Medium Energy')}"
    )

    sys = f"""
Ты — профессиональный автор песен и композитор.
Твоя задача — написать текст песни на языке: {lang_hint}.

Правила:
1) Всегда используй чёткую структуру (метки строками):
{structure_text}

2) Текст должен быть ритмичным и подходить для музыкального исполнения, {rhyme_text}.
3) Не пиши лишних объяснений — только песня.
4) В конце КАЖДОГО ответа добавляй отдельной строкой:
Style Prompt: {style_prompt}

Важно: Style Prompt всегда на английском.
"""
    return normalize_user_text(sys)


def build_user_prompt(u: Dict[str, Any], user_text: str) -> str:
    genre = u.get("genre", "pop")
    mood = u.get("mood", "neutral")
    user_text = normalize_user_text(user_text)[:MAX_USER_TEXT]
    return f"Жанр: {genre}. Настроение: {mood}. Тема: {user_text}"


# =========================
# OPENROUTER CLIENT
# =========================
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


@dataclass
class LLMResult:
    ok: bool
    text: str
    status: int = 0
    raw: str = ""


async def llm_chat(session: aiohttp.ClientSession, system_prompt: str, user_prompt: str) -> LLMResult:
    if not OPENROUTER_API_KEY:
        return LLMResult(ok=False, text="NO_KEY", status=401)

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        # Not required, but recommended by OpenRouter:
        "HTTP-Referer": "https://render.com",
        "X-Title": "MusicAi Telegram Bot",
    }

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.9,
        "max_tokens": 900,
    }

    try:
        async with session.post(
            OPENROUTER_URL,
            headers=headers,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=60),
        ) as resp:
            status = resp.status
            raw = await resp.text()
            if status != 200:
                return LLMResult(ok=False, text=f"HTTP_{status}", status=status, raw=raw)

            data = json.loads(raw)
            return LLMResult(
                ok=True,
                text=data["choices"][0]["message"]["content"],
                status=status,
                raw=raw,
            )

    except asyncio.TimeoutError:
        return LLMResult(ok=False, text="TIMEOUT", status=0)
    except Exception as e:
        return LLMResult(ok=False, text=f"EXC: {e}", status=0)


# =========================
# PIAPI CLIENT (SUNO)
# =========================
PIAPI_URL = "https://api.piapi.ai/api/v1/task"


@dataclass
class PIAPIResult:
    ok: bool
    text: str
    status: int = 0
    raw: str = ""
    task_id: str = ""


async def piapi_generate_music(
    session: aiohttp.ClientSession,
    prompt: str,
    lyrics: str,
    style: str,
    language: str,
    duration: int = 60
) -> PIAPIResult:
    """
    Generate music using PIAPI (Suno Music API).
    
    Args:
        session: aiohttp client session
        prompt: Description of the song
        lyrics: Song lyrics text
        style: Music genre/style
        language: Language code (e.g., 'ru', 'en', 'de')
        duration: Duration in seconds (max 60 for demo)
    
    Returns:
        PIAPIResult with task information
    """
    if not PIAPI_API_KEY:
        return PIAPIResult(ok=False, text="NO_PIAPI_KEY", status=401)

    headers = {
        "X-API-Key": PIAPI_API_KEY,
        "Content-Type": "application/json",
    }

    # Limit duration to 60 seconds for demo
    duration = min(duration, 60)

    payload = {
        "model": "suno",
        "task_type": "music",
        "input": {
            "prompt": prompt,
            "lyrics": lyrics,
            "style": style,
            "language": language,
            "duration": duration,
        }
    }

    try:
        async with session.post(
            PIAPI_URL,
            headers=headers,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=120),
        ) as resp:
            status = resp.status
            raw = await resp.text()
            if status != 200:
                return PIAPIResult(ok=False, text=f"HTTP_{status}", status=status, raw=raw)

            data = json.loads(raw)
            task_id = data.get("task_id", "")
            return PIAPIResult(
                ok=True,
                text="TASK_CREATED",
                status=status,
                raw=raw,
                task_id=task_id,
            )

    except asyncio.TimeoutError:
        return PIAPIResult(ok=False, text="TIMEOUT", status=0)
    except Exception as e:
        log.exception("PIAPI music generation error: %s", e)
        return PIAPIResult(ok=False, text="API_ERROR", status=0)


# =========================
# KEYBOARDS
# =========================
def kb_main(u: Dict[str, Any]) -> InlineKeyboardMarkup:
    credits = int(u.get("credits") or 0)
    credits_line = tr(u, "credits").format(credits=credits)

    buttons = [
        [InlineKeyboardButton("⭐ Buy", callback_data="menu:buy"),
         InlineKeyboardButton("⚙️ Settings", callback_data="menu:settings")],
        [InlineKeyboardButton("🌍 UI Lang", callback_data="menu:ui_lang"),
         InlineKeyboardButton("📝 Song Lang", callback_data="menu:song_lang")],
        [InlineKeyboardButton("🎧 Genre", callback_data="menu:genre"),
         InlineKeyboardButton("😊 Mood", callback_data="menu:mood")],
        [InlineKeyboardButton("🎤 Vocal", callback_data="menu:vocal"),
         InlineKeyboardButton("⚡ Energy", callback_data="menu:energy")],
        [InlineKeyboardButton("🧩 Structure", callback_data="menu:structure"),
         InlineKeyboardButton("🎵 Rhyme", callback_data="menu:rhyme")],
        [InlineKeyboardButton("🕘 History", callback_data="menu:history"),
         InlineKeyboardButton("❓ Help", callback_data="menu:help")],
        [InlineKeyboardButton(f"{credits_line}", callback_data="noop")],
    ]
    return InlineKeyboardMarkup(buttons)


def kb_list(items: List[Tuple[str, str]], prefix: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(name, callback_data=f"set:{prefix}:{val}")] for name, val in items]
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data="menu:settings")])
    return InlineKeyboardMarkup(rows)


def kb_buy(u: Dict[str, Any]) -> InlineKeyboardMarkup:
    rows = []
    lang = (u.get("lang") or "ru").lower()
    for pack_id, p in STARS_PACKS.items():
        title = p["title_ru"] if lang == "ru" else p["title_en"]
        rows.append([InlineKeyboardButton(f"{title} — {p['amount_xtr']}⭐", callback_data=f"buy:{pack_id}")])
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data="menu:settings")])
    return InlineKeyboardMarkup(rows)


# =========================
# COMMANDS
# =========================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_ensure(user_id)
    u = user_get(user_id)
    await update.message.reply_text(tr(u, "start"), parse_mode=ParseMode.MARKDOWN, reply_markup=kb_main(u))


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_ensure(user_id)
    u = user_get(user_id)
    await update.message.reply_text(tr(u, "help"), reply_markup=kb_main(u))


async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_ensure(user_id)
    u = user_get(user_id)
    text = tr(u, "settings") + "\n\n```" + "\n" + format_settings(u) + "```"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb_main(u))


async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_ensure(user_id)
    user_set(
        user_id,
        lang="ru",
        song_language="ru",
        genre="pop",
        mood="neutral",
        vocal="male",
        energy="medium",
        structure="classic",
        rhyme="yes",
    )
    u = user_get(user_id)
    await update.message.reply_text(tr(u, "reset"), reply_markup=kb_main(u))


async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_ensure(user_id)
    u = user_get(user_id)
    items = history_last(user_id, 5)
    if not items:
        await update.message.reply_text(tr(u, "history_empty"), reply_markup=kb_main(u))
        return
    lines = [tr(u, "history")]
    for it in items:
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(it["ts"]))
        resp = it["response"]
        if len(resp) > 600:
            resp = resp[:600] + "…"
        lines.append(f"\n*{ts}*\n_Topic:_ {it['prompt']}\n{resp}")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN, reply_markup=kb_main(u))


async def cmd_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_ensure(user_id)
    u = user_get(user_id)
    await update.message.reply_text(tr(u, "buy_text"), reply_markup=kb_buy(u))


# =========================
# PAYMENTS (STARS)
# =========================
def make_payload(user_id: int, pack_id: str) -> str:
    # payload must be 1-128 bytes. Keep it short.
    return f"musicai|{user_id}|{pack_id}|{now_ts()}"


async def send_stars_invoice(update: Update, context: ContextTypes.DEFAULT_TYPE, pack_id: str):
    user_id = update.effective_user.id
    u = user_get(user_id)
    p = STARS_PACKS.get(pack_id)
    if not p:
        return

    lang = (u.get("lang") or "ru").lower()
    title = tr(u, "buy_title")
    desc = (p["title_ru"] if lang == "ru" else p["title_en"]) + f". +{p['credits_add']} credits."
    payload = make_payload(user_id, pack_id)

    # For Stars: currency="XTR", prices must contain exactly one item.
    prices = [LabeledPrice(label="Credits", amount=int(p["amount_xtr"]))]

    await context.bot.send_invoice(
        chat_id=update.effective_chat.id,
        title=title,
        description=desc,
        payload=payload,
        provider_token="",  # Stars: empty token
        currency="XTR",
        prices=prices,
    )


async def on_precheckout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Must answer pre-checkout query
    query = update.pre_checkout_query
    try:
        await query.answer(ok=True)
    except Exception:
        pass


async def on_successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_ensure(user_id)
    u = user_get(user_id)

    sp = update.message.successful_payment
    payload = (sp.invoice_payload or "")
    # expected: musicai|<user_id>|<pack_id>|<ts>
    add = 0

    try:
        parts = payload.split("|")
        if len(parts) >= 3 and parts[0] == "musicai":
            pay_user = int(parts[1])
            pack_id = parts[2]
            if pay_user == user_id and pack_id in STARS_PACKS:
                add = int(STARS_PACKS[pack_id]["credits_add"])
    except Exception:
        add = 0

    if add > 0:
        credits = int(u.get("credits") or 0) + add
        user_set(user_id, credits=credits)
        u = user_get(user_id)
        await update.message.reply_text(
            tr(u, "buy_ok").format(add=add, credits=int(u.get("credits") or 0)),
            reply_markup=kb_main(u)
        )
    else:
        await update.message.reply_text(tr(u, "buy_fail"), reply_markup=kb_main(u))


# =========================
# CALLBACKS
# =========================
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    user_ensure(user_id)
    u = user_get(user_id)
    data = query.data or ""

    if data == "noop":
        return

    # Buy flow
    if data.startswith("buy:"):
        pack_id = data.split(":", 1)[1]
        # send invoice in chat (not editing old msg)
        await query.message.reply_text(tr(u, "busy"))
        await send_stars_invoice(update, context, pack_id)
        return

    if data.startswith("menu:"):
        section = data.split(":", 1)[1]

        if section == "settings":
            txt = tr(u, "settings") + "\n\n```" + "\n" + format_settings(u) + "```"
            await query.edit_message_text(txt, parse_mode=ParseMode.MARKDOWN, reply_markup=kb_main(u))
            return

        if section == "buy":
            await query.edit_message_text(tr(u, "buy_text"), reply_markup=kb_buy(u))
            return

        if section == "ui_lang":
            await query.edit_message_text("🌍 UI language:", reply_markup=kb_list(LANG_UI, "ui_lang"))
            return

        if section == "song_lang":
            await query.edit_message_text("📝 Song language:", reply_markup=kb_list(SONG_LANG, "song_language"))
            return

        if section == "genre":
            await query.edit_message_text("🎧 Genre:", reply_markup=kb_list(GENRES, "genre"))
            return

        if section == "mood":
            await query.edit_message_text("😊 Mood:", reply_markup=kb_list(MOODS, "mood"))
            return

        if section == "vocal":
            await query.edit_message_text("🎤 Vocal:", reply_markup=kb_list(VOCALS, "vocal"))
            return

        if section == "energy":
            await query.edit_message_text("⚡ Energy:", reply_markup=kb_list(ENERGY, "energy"))
            return

        if section == "structure":
            await query.edit_message_text("🧩 Structure:", reply_markup=kb_list(STRUCTURES, "structure"))
            return

        if section == "rhyme":
            await query.edit_message_text("🎵 Rhyme:", reply_markup=kb_list(RHYME, "rhyme"))
            return

        if section == "history":
            await query.message.reply_text(tr(u, "busy"))
            items = history_last(user_id, 5)
            if not items:
                await query.message.reply_text(tr(u, "history_empty"), reply_markup=kb_main(u))
                return
            lines = [tr(u, "history")]
            for it in items:
                ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(it["ts"]))
                resp = it["response"]
                if len(resp) > 600:
                    resp = resp[:600] + "…"
                lines.append(f"\n*{ts}*\n_Topic:_ {it['prompt']}\n{resp}")
            await query.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN, reply_markup=kb_main(u))
            return

        if section == "help":
            await query.message.reply_text(tr(u, "help"), reply_markup=kb_main(u))
            return

    if data.startswith("set:"):
        _, field, value = data.split(":", 2)
        if field == "ui_lang":
            user_set(user_id, lang=value)
        elif field in ("song_language", "genre", "mood", "vocal", "energy", "structure", "rhyme"):
            user_set(user_id, **{field: value})

        u = user_get(user_id)
        await query.message.reply_text(
            tr(u, "saved") + "\n\n```" + "\n" + format_settings(u) + "```",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb_main(u)
        )
        try:
            await query.edit_message_reply_markup(reply_markup=kb_main(u))
        except Exception:
            pass
        return


# =========================
# GENERATION HANDLER
# =========================
async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_ensure(user_id)
    u = user_get(user_id)

    text = normalize_user_text(update.message.text or "")
    if not text:
        await update.message.reply_text(tr(u, "need_topic"), reply_markup=kb_main(u))
        return

    if text.startswith("/"):
        return

    ok, reason = ensure_daily_limits(user_id)
    if not ok:
        await update.message.reply_text(tr(u, reason), reply_markup=kb_main(u))
        return

    if not OPENROUTER_API_KEY:
        await update.message.reply_text(tr(u, "no_key"), reply_markup=kb_main(u))
        return

    # credits check (admin bypass)
    if ADMIN_ID > 0 and user_id == ADMIN_ID:
        pass
    else:
        credits = int(u.get("credits") or 0)
        if credits <= 0:
            await update.message.reply_text(
                tr(u, "no_credits"),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=kb_buy(u)
            )
            return
        # reserve 1 credit immediately (prevents spam double-spend)
        user_set(user_id, credits=credits - 1)
        u = user_get(user_id)

    bump_usage(user_id)
    await update.message.reply_text(tr(u, "busy"))

    system_prompt = build_system_prompt(u)
    user_prompt = build_user_prompt(u, text)

    async with aiohttp.ClientSession() as session:
        res = await llm_chat(session, system_prompt, user_prompt)

    if not res.ok:
        # refund credit on failure (non-admin)
        if not (ADMIN_ID > 0 and user_id == ADMIN_ID):
            u2 = user_get(user_id)
            user_set(user_id, credits=int(u2.get("credits") or 0) + 1)

        if res.status == 401:
            await update.message.reply_text(
                "❌ 401: ключ OpenRouter не принят. Проверь OPENROUTER_API_KEY.",
                reply_markup=kb_main(user_get(user_id))
            )
            return

        await update.message.reply_text(
            tr(u, "gen_error") + f"\n\nDebug: {res.text}\n{res.raw[:600]}",
            reply_markup=kb_main(user_get(user_id))
        )
        return

    out = (res.text or "").strip()
    history_add(user_id, text, out)

    for part in split_text(out, MAX_TG_MESSAGE):
        await update.message.reply_text(part)

    # Optional: Try to generate music via PIAPI if key is available
    if PIAPI_API_KEY:
        await update.message.reply_text(tr(u, "music_generating"))
        
        # Extract style prompt from LLM output if present
        style_prompt = ""
        if "Style Prompt:" in out:
            style_prompt = out.split("Style Prompt:")[-1].strip()
        
        # Map genre to style
        genre = u.get("genre", "pop")
        genre_map = {
            "pop": "Pop",
            "disco_polo": "Disco Polo",
            "rap": "Hip-Hop",
            "rock": "Rock",
            "edm": "EDM",
            "ballad": "Ballad",
            "reggaeton": "Reggaeton",
            "synthwave": "Synthwave",
        }
        style = style_prompt if style_prompt else genre_map.get(genre, "Pop")
        
        # Get language code
        song_lang = u.get("song_language", "ru")
        
        # Use the generated output (includes lyrics with structure markers)
        llm_output = out
        
        # Build prompt for PIAPI
        piapi_prompt = f"Create a {genre} song: {text}"
        
        async with aiohttp.ClientSession() as session:
            music_res = await piapi_generate_music(
                session,
                prompt=piapi_prompt,
                lyrics=llm_output,
                style=style,
                language=song_lang,
                duration=60  # Max 60 seconds for demo
            )
        
        if music_res.ok:
            await update.message.reply_text(
                tr(u, "music_success").format(task_id=music_res.task_id)
            )
        else:
            # Music generation failed, but lyrics were generated successfully
            # Log the error but don't expose details to user
            log.warning("PIAPI music generation failed: %s", music_res.text)
            await update.message.reply_text(tr(u, "music_error"))

    u = user_get(user_id)
    await update.message.reply_text(
        "✅ Готово.\n" + tr(u, "credits").format(credits=int(u.get("credits") or 0)),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb_main(u)
    )


# =========================
# ADMIN
# =========================
async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ADMIN_ID <= 0 or user_id != ADMIN_ID:
        return
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as c FROM users")
    users_count = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) as c FROM history")
    hist_count = cur.fetchone()["c"]
    conn.close()
    await update.message.reply_text(
        f"Admin:\nUsers: {users_count}\nHistory: {hist_count}\nModel: {OPENROUTER_MODEL}"
    )


# =========================
# ERROR HANDLER
# =========================
async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    log.exception("Unhandled error: %s", context.error)


# =========================
# MAIN
# =========================
def build_app() -> Application:
    db_init()

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("settings", cmd_settings))
    app.add_handler(CommandHandler("history", cmd_history))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CommandHandler("buy", cmd_buy))
    app.add_handler(CommandHandler("admin", cmd_admin))

    # callbacks
    app.add_handler(CallbackQueryHandler(on_callback))

    # payments
    app.add_handler(PreCheckoutQueryHandler(on_precheckout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, on_successful_payment))

    # text
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    app.add_error_handler(on_error)
    return app


def main():
    app = build_app()
    log.info("✅ MusicAi PRO started (polling)")
    app.run_polling(close_loop=False)


if __name__ == "__main__":
    main()
