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
PIAPI_KEY = os.getenv("PIAPI_KEY") 
OWNER_ID = int(os.getenv("OWNER_TG_ID", "0"))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

if not BOT_TOKEN or not PIAPI_KEY:
    raise RuntimeError("TELEGRAM_BOT_TOKEN or PIAPI_KEY not set")

# -------------------- PRICES (Telegram Stars) --------------------
PACKS = {"1": 250, "5": 1000, "25": 4000}

# -------------------- DB --------------------
DB_PATH = "musicai.db"

def db_init():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            lang TEXT DEFAULT 'en',
            demo_used INTEGER DEFAULT 0,
            songs INTEGER DEFAULT 0,
            state_json TEXT DEFAULT '{}',
            updated_at INTEGER DEFAULT 0
        )
    """)
    con.commit()
    con.close()

def db_get_user(user_id: int):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT user_id, lang, demo_used, songs, state_json FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    if not row:
        cur.execute("INSERT INTO users(user_id, lang, demo_used, songs, state_json, updated_at) VALUES(?,?,?,?,?,?)",
                    (user_id, "en", 0, 0, "{}", int(time.time())))
        con.commit()
        con.close()
        return {"user_id": user_id, "lang": "en", "demo_used": 0, "songs": 0, "state": {}}
    
    # Сначала считываем данные, потом закрываем соединение
    user_data = {
        "user_id": row[0],
        "lang": row[1],
        "demo_used": row[2],
        "songs": row[3],
        "state": json.loads(row[4] or "{}")
    }
    con.close()
    return user_data

def db_set(user_id: int, **kwargs):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    now = int(time.time())
    for key, val in kwargs.items():
        if key == "state":
            cur.execute("UPDATE users SET state_json=?, updated_at=? WHERE user_id=?", (json.dumps(val, ensure_ascii=False), now, user_id))
        else:
            cur.execute(f"UPDATE users SET {key}=?, updated_at=? WHERE user_id=?", (val, now, user_id))
    con.commit()
    con.close()

async def adb_get_user(uid): return await asyncio.to_thread(db_get_user, uid)
async def adb_set(uid, **kwargs): await asyncio.to_thread(db_set, uid, **kwargs)

# -------------------- ТЕКСТЫ (ПОЛНАЯ ВЕРСИЯ) --------------------
LANGS = ["en", "ru", "pl", "de", "es", "fr", "uk"]

TEXTS = {
    "start": {
        "en": "🎵 *MusicAi*\n\nI create a full song in 5 minutes.\nLyrics, mood and style — personalised.\n\nPress START to begin 👇",
        "ru": "🎵 *MusicAi*\n\nЯ создаю полноценную песню за 5 минут.\nТекст, настроение и стиль — персонально.\n\nНажми START, чтобы начать 👇",
        "pl": "🎵 *MusicAi*\n\nTworzę pełną piosenkę w 5 minut.\nTekst, klimat i styl — personalnie.\n\nNaciśnij START, aby rozpocząć 👇",
        "uk": "🎵 *MusicAi*\n\nЯ створюю повноцінну пісню за 5 хвилин.\nТекст, настрій та стиль — персонально.\n\nНатисни START, щоб почати 👇",
    },
    "choose_language": {"en": "Choose language:", "ru": "Выбери язык:", "pl": "Wybierz język:", "uk": "Вибери мову:"},
    "choose_theme": {"en": "Choose theme:", "ru": "Выбери тему:", "pl": "Wybierz temat:", "uk": "Вибери тему:"},
    "choose_genre": {"en": "Choose genre:", "ru": "Выбери жанр:", "pl": "Wybierz gatunek:", "uk": "Вибери жанр:"},
    "describe": {
        "en": "✍️ *Describe the song*\n\n1) Who is it for?\n2) Story/Event\n3) Mood\n\n🎤 Or send a voice message.",
        "ru": "✍️ *Опиши песню*\n\n1) Кому?\n2) История/Событие\n3) Настроение\n\n🎤 Или отправь голосовое.",
        "pl": "✍️ *Opisz piosenkę*\n\n1) Dla kogo?\n2) Historia\n3) Klimat\n\n🎤 Lub wyślij głosówkę.",
        "uk": "✍️ *Опиши пісню*\n\n1) Кому?\n2) Історія\n3) Настрій\n\n🎤 Або надішли голосове.",
    },
    "help": {
        "en": "ℹ️ *Help & FAQ*\n\n✏️ *Can I edit a ready song?*\nNo, you can only generate a new one. Each generation costs 1 song credit.\n\n🎶 *How many variants?*\nYou get 2 unique variants per generation.\n\n🔉 *Stress and pronunciation issues?*\nWrite stress with CAPITAL letters (e.g., dIma, natAsha).\n\n📄 *Rights*\nThe songs belong to you. You can publish them anywhere.",
        "ru": "ℹ️ *Помощь и FAQ*\n\n✏️ *Можно ли изменить готовую песню?*\nНет, только сгенерировать заново. Каждая генерация списывает 1 песню.\n\n🎶 *Сколько вариантов?*\nВы получаете 2 уникальных варианта за один запрос.\n\n🔉 *Ошибки в ударениях?*\nПопробуйте выделять ударную гласную КАПСОМ (например: дИма, натАша).\n\n📄 *Права*\nПрава принадлежат вам. Вы можете публиковать песни в любых соцсетях.",
        "pl": "ℹ️ *Pomoc*\n\n✏️ *Czy mogę edytować?*\nNie, tylko nowa generacja.\n\n🎶 *Ile wersji?*\n2 unikalne wersje.\n\n📄 *Prawa*\nPiosenki należą do Ciebie.",
        "uk": "ℹ️ *Допомога*\n\n✏️ *Чи можна змінити?*\nНі, тільки нова генерація.\n\n🎶 *Скільки варіантів?*\n2 унікальні варіанти.\n\n📄 *Права*\nПрава належать вам.",
    },
    "generating": {"en": "⏳ Generating...", "ru": "⏳ Генерирую...", "pl": "⏳ Generuję...", "uk": "⏳ Генерую..."},
    "no_credits": {"en": "0 songs left. Buy a pack 👇", "ru": "0 песен. Купи пакет 👇", "pl": "0 piosenek 👇", "uk": "0 пісень 👇"},
    "paid": {"en": "✅ Payment successful!", "ru": "✅ Оплата прошла!", "pl": "✅ Opłacono!", "uk": "✅ Оплачено!"},
    "temp_error": {"en": "⚠️ Error. Try later.", "ru": "⚠️ Ошибка. Попробуй позже.", "pl": "⚠️ Błąd.", "uk": "⚠️ Помилка."},
    "custom_theme_ask": {"en": "✏️ Write your theme phrase:", "ru": "✏️ Напиши тему одной фразой:", "pl": "✏️ Napisz temat:", "uk": "✏️ Напиши тему:"},
    "buy_confirm": {"en": "Spend ⭐ {stars}?", "ru": "Потратить ⭐ {stars}?", "pl": "Wydać ⭐ {stars}?", "uk": "Витратити ⭐ {stars}?"},
    "demo_header": {"en": "🎧 *Demo (1 min)*", "ru": "🎧 *Демо (1 мин)*", "pl": "🎧 *Demo (1 min)*", "uk": "🎧 *Демо (1 хв)*"}
}

THEMES = {
    "love": {"en":"Love ❤️","ru":"Любовь ❤️","pl":"Miłość ❤️","uk":"Кохання ❤️"},
    "fun": {"en":"Funny 😄","ru":"Смешная 😄","pl":"Zabawna 😄","uk":"Весела 😄"},
    "holiday": {"en":"Holiday 🎉","ru":"Праздник 🎉","pl":"Święto 🎉","uk":"Свято 🎉"},
    "sad": {"en":"Sad 😢","ru":"Грусть 😢","pl":"Smutna 😢","uk":"Сум 😢"},
    "wedding": {"en":"Wedding 💍","ru":"Свадьба 💍","pl":"Wesele 💍","uk":"Весілля 💍"},
    "custom": {"en":"Custom ✏️","ru":"Свой вариант ✏️","pl":"Własny ✏️","uk":"Свій варіант ✏️"},
}

def tr(lang, key): return TEXTS.get(key, {}).get(lang, TEXTS.get(key, {}).get("en", "Text missing"))

# -------------------- API CALLS --------------------
async def piapi_generate(prompt):
    url = "https://api.piapi.ai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {PIAPI_KEY}", "Content-Type": "application/json"}
    payload = {"model": "pi-music", "messages": [{"role": "user", "content": prompt}]}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=120) as r:
                data = await r.json()
                if "choices" in data: return data["choices"][0]["message"]["content"]
                return None
    except Exception as e:
        logger.error(f"PiAPI Error: {e}")
        return None

async def voice_to_text(file_path):
    if not OPENAI_API_KEY: return None
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        with open(file_path, "rb") as f:
            res = await client.audio.transcriptions.create(model="whisper-1", file=f)
        return res.text
    except: return None

# -------------------- UI --------------------
def kb_languages():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("English 🇬🇧", callback_data="lang_en"), InlineKeyboardButton("Русский 🇷🇺", callback_data="lang_ru")],
        [InlineKeyboardButton("Polski 🇵🇱", callback_data="lang_pl"), InlineKeyboardButton("Українська 🇺🇦", callback_data="lang_uk")]
    ])

def kb_themes(lang):
    btns = []
    keys = list(THEMES.keys())
    for i in range(0, len(keys), 2):
        row = [InlineKeyboardButton(THEMES[keys[i]][lang], callback_data=f"theme_{keys[i]}")]
        if i+1 < len(keys): row.append(InlineKeyboardButton(THEMES[keys[i+1]][lang], callback_data=f"theme_{keys[i+1]}"))
        btns.append(row)
    return InlineKeyboardMarkup(btns)

def kb_genres():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Pop", callback_data="genre_pop"), InlineKeyboardButton("Rap", callback_data="genre_rap")],
        [InlineKeyboardButton("Rock", callback_data="genre_rock"), InlineKeyboardButton("Club", callback_data="genre_club")],
        [InlineKeyboardButton("Classical", callback_data="genre_classical"), InlineKeyboardButton("Disco Polo", callback_data="genre_disco")]
    ])

# -------------------- HANDLERS --------------------
async def post_init(app):
    """ Настройка левого меню команд """
    await app.bot.set_my_commands([
        BotCommand("start", "Start / Restart"),
        BotCommand("help", "Help / FAQ"),
    ])

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = await adb_get_user(uid)
    await adb_set(uid, state={})
    await update.message.reply_text(tr(u["lang"], "start"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ START", callback_data="start")]]), parse_mode="Markdown")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = await adb_get_user(update.effective_user.id)
    await update.message.reply_text(tr(u["lang"], "help"), parse_mode="Markdown")

async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    u = await adb_get_user(uid)
    lang, state = u["lang"], u["state"]

    if q.data == "start":
        await q.edit_message_text(tr(lang, "choose_language"), reply_markup=kb_languages())
    elif q.data.startswith("lang_"):
        new_lang = q.data[5:]
        await adb_set(uid, lang=new_lang)
        await q.edit_message_text(tr(new_lang, "choose_theme"), reply_markup=kb_themes(new_lang))
    elif q.data.startswith("theme_"):
        theme = q.data[6:]
        state["theme"] = theme
        if theme == "custom":
            state["awaiting_custom"] = True
            await adb_set(uid, state=state)
            await q.edit_message_text(tr(lang, "custom_theme_ask"))
        else:
            await adb_set(uid, state=state)
            await q.edit_message_text(tr(lang, "choose_genre"), reply_markup=kb_genres())
    elif q.data.startswith("genre_"):
        state["genre"] = q.data[6:]
        await adb_set(uid, state=state)
        await q.edit_message_text(tr(lang, "describe"), parse_mode="Markdown")
    elif q.data.startswith("pay_"):
        pack = q.data.split("_")[1]
        await context.bot.send_invoice(chat_id=uid, title="MusicAi", description=f"{pack} songs", payload=f"pack_{pack}", provider_token="", currency="XTR", prices=[LabeledPrice("Stars", PACKS[pack])])

async def user_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = await adb_get_user(uid)
    lang, state = u["lang"], u["state"]

    if state.get("awaiting_custom"):
        state["custom_theme"] = update.message.text
        state["awaiting_custom"] = False
        await adb_set(uid, state=state)
        await update.message.reply_text(tr(lang, "choose_genre"), reply_markup=kb_genres())
        return

    if "genre" not in state:
        await update.message.reply_text(tr(lang, "start"))
        return

    prompt_text = ""
    if update.message.voice:
        wait = await update.message.reply_text(tr(lang, "generating"))
        file = await context.bot.get_file(update.message.voice.file_id)
        path = f"v_{uid}.ogg"
        await file.download_to_drive(path)
        prompt_text = await voice_to_text(path)
        if os.path.exists(path): os.remove(path)
        if not prompt_text: await wait.edit_text("Voice error."); return
        await wait.delete()
    else:
        prompt_text = update.message.text

    # Формируем запрос
    final_theme = state.get("custom_theme") or state.get("theme")
    prompt = f"Song about {final_theme}. Genre: {state['genre']}. User details: {prompt_text}. Language: {lang}. Create 2 variants."

    msg = await update.message.reply_text(tr(lang, "generating"))

    if u["demo_used"] == 0:
        res = await piapi_generate("DEMO 1 min: " + prompt)
        if res:
            # ФИКС: Защита от ошибок Markdown
            try: await msg.edit_text(f"{tr(lang, 'demo_header')}\n\n{res[:3500]}", parse_mode="Markdown")
            except: await msg.edit_text(f"{tr(lang, 'demo_header')}\n\n{res[:3500]}")
            await adb_set(uid, demo_used=1)
        else: await msg.edit_text(tr(lang, "temp_error"))
    elif u["songs"] > 0:
        res = await piapi_generate("FULL SONG: " + prompt)
        if res:
            try: await msg.edit_text(res[:3900], parse_mode="Markdown")
            except: await msg.edit_text(res[:3900])
            await adb_set(uid, songs=u["songs"]-1)
        else: await msg.edit_text(tr(lang, "temp_error"))
    else:
        await msg.delete()
        await update.message.reply_text(tr(lang, "no_credits"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⭐ Buy 1 song", callback_data="pay_1")]]))

# -------------------- PAYMENTS --------------------
async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = await adb_get_user(uid)
    payload = update.message.successful_payment.invoice_payload
    pack = payload.replace("pack_", "")
    await adb_set(uid, songs=u["songs"] + int(pack))
    await update.message.reply_text(tr(u["lang"], "paid"))

# -------------------- MAIN --------------------
def main():
    db_init()
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT | filters.VOICE, user_input))
    app.add_handler(PreCheckoutQueryHandler(pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))

    logger.info("Bot started")
    app.run_polling()

if __name__ == "__main__":
    main()
