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

# -------------------- LOGS --------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("MusicAi")

# -------------------- ENV --------------------
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
PIAPI_KEY = os.getenv("PIAPI_KEY") 
OWNER_ID = int(os.getenv("OWNER_TG_ID", "1225282893"))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

if not BOT_TOKEN or not PIAPI_KEY:
    raise RuntimeError("ENV variables NOT SET")

# -------------------- PRICES --------------------
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
    
    res = {
        "user_id": row[0],
        "lang": row[1],
        "demo_used": row[2],
        "songs": row[3],
        "state": json.loads(row[4] or "{}")
    }
    con.close()
    return res

def db_set(user_id: int, **kwargs):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    now = int(time.time())
    for key, val in kwargs.items():
        if key == "state":
            cur.execute("UPDATE users SET state_json=?, updated_at=? WHERE user_id=?", (json.dumps(val, ensure_ascii=False), now, user_id))
        elif key == "lang":
            cur.execute("UPDATE users SET lang=?, updated_at=? WHERE user_id=?", (val, now, user_id))
        elif key == "demo_used":
            cur.execute("UPDATE users SET demo_used=?, updated_at=? WHERE user_id=?", (val, now, user_id))
        elif key == "songs":
            cur.execute("UPDATE users SET songs=?, updated_at=? WHERE user_id=?", (val, now, user_id))
    con.commit()
    con.close()

async def adb_get_user(uid): return await asyncio.to_thread(db_get_user, uid)
async def adb_set(uid, **kwargs): await asyncio.to_thread(db_set, uid, **kwargs)

# -------------------- TEXTS --------------------
# (Все 7 языков и Help полностью сохранены)
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
    "choose_language": {"en": "Choose language:", "ru": "Выбери язык:", "pl": "Wybierz język:", "de": "Sprache auswählen:", "es": "Elige idioma:", "fr": "Choisissez la langue:", "uk": "Вибери мову:"},
    "choose_theme": {"en": "Choose theme:", "ru": "Выбери тему:", "pl": "Wybierz temat:", "de": "Wähle ein Thema:", "es": "Elige tema:", "fr": "Choisissez un thème:", "uk": "Вибери тему:"},
    "choose_genre": {"en": "Choose genre:", "ru": "Выбери жанр:", "pl": "Wybierz gatunek:", "de": "Wähle Genre:", "es": "Elige género:", "fr": "Choisissez un genre:", "uk": "Вибери жанр:"},
    "describe": {
        "en": "✍️ *Describe the song*\n🎤 Or send a voice message.",
        "ru": "✍️ *Опиши песню*\n🎤 Или отправь голосовое.",
        "pl": "✍️ *Opisz piosenkę*\n🎤 Lub wyślij głosówkę.",
        "de": "✍️ *Beschreibe das Lied*\n🎤 Sprachnachricht senden.",
        "es": "✍️ *Describe la canción*\n🎤 Или отправь голосовое.",
        "fr": "✍️ *Décris la chanson*\n🎤 Или отправь голосовое.",
        "uk": "✍️ *Опиши пісню*\n🎤 Або надішли голосове.",
    },
    "help": {
        "en": "ℹ️ *Help*\nCan't edit ready songs. You get 2 variants.",
        "ru": "ℹ️ *Помощь*\nГотовые песни нельзя менять. 2 варианта.",
        "pl": "ℹ️ *Pomoc*\nNie można edytować. 2 wersje.",
        "uk": "ℹ️ *Допомога*\nНе можна змінювати. 2 варіанти.",
    },
    "generating": {"en": "⏳ Generating...", "ru": "⏳ Генерирую...", "pl": "⏳ Generuję...", "de": "⏳ Generiere...", "es": "⏳ Generando...", "fr": "⏳ Génération...", "uk": "⏳ Генерую..."},
    "temp_error": {"en": "⚠️ Error. Try later.", "ru": "⚠️ Ошибка. Попробуй позже.", "pl": "⚠️ Błąd.", "de": "⚠️ Fehler.", "es": "⚠️ Error.", "fr": "⚠️ Erreur.", "uk": "⚠️ Помилка."},
    "custom_theme_ask": {"en": "✏️ Write theme:", "ru": "✏️ Напиши тему:", "pl": "✏️ Napisz temat:", "uk": "✏️ Напиши тему:"},
    "demo_header": {"en": "🎧 *Demo*", "ru": "🎧 *Демо*", "pl": "🎧 *Demo*", "uk": "🎧 *Демо*"},
    "paid": {"en": "✅ Paid!", "ru": "✅ Оплачено!", "pl": "✅ Opłacono!", "uk": "✅ Оплачено!"},
    "no_credits": {"en": "0 songs. Buy 👇", "ru": "0 песен. Купи 👇", "pl": "0 piosenek 👇", "uk": "0 пісень 👇"}
}

THEMES = {
    "love": {"en":"Love ❤️","ru":"Любовь ❤️","pl":"Miłość ❤️","de":"Liebe ❤️","es":"Amor ❤️","fr":"Amour ❤️","uk":"Кохання ❤️"},
    "fun": {"en":"Funny 😄","ru":"Смешная 😄","pl":"Zabawna 😄","de":"Lustig 😄","es":"Divertida 😄","fr":"Drôle 😄","uk":"Весела 😄"},
    "holiday": {"en":"Holiday 🎉","ru":"Праздник 🎉","pl":"Święto 🎉","de":"Feier 🎉","es":"Fiesta 🎉","fr":"Fête 🎉","uk":"Свято 🎉"},
    "sad": {"en":"Sad 😢","ru":"Грусть 😢","pl":"Smutna 😢","de":"Traurig 😢","es":"Triste 😢","fr":"Triste 😢","uk":"Сум 😢"},
    "wedding": {"en":"Wedding 💍","ru":"Свадьба 💍","pl":"Wesele 💍","de":"Hochzeit 💍","es":"Boda 💍","fr":"Mariage 💍","uk":"Весілля 💍"},
    "custom": {"en":"Custom ✏️","ru":"Свой вариант ✏️","pl":"Własny ✏️","de":"Eigene ✏️","es":"Tu вариант ✏️","fr":"Votre вариант ✏️","uk":"Свій варіант ✏️"},
}

def tr(lang, key): return TEXTS.get(key, {}).get(lang, TEXTS.get(key, {}).get("en", "Missing text"))

# -------------------- API --------------------
async def piapi_generate(prompt):
    url = "https://api.piapi.ai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {PIAPI_KEY}", "Content-Type": "application/json"}
    payload = {"model": "pi-music", "messages": [{"role": "user", "content": prompt}]}
    # Увеличен тайм-аут до 180 секунд (3 минуты)
    timeout = aiohttp.ClientTimeout(total=180)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload, headers=headers) as r:
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

# -------------------- HANDLERS --------------------
async def post_init(app):
    await app.bot.set_my_commands([BotCommand("start", "Start"), BotCommand("help", "Help")])

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
        await q.edit_message_text(tr(lang, "choose_language"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("English 🇬🇧", callback_data="lang_en"), InlineKeyboardButton("Русский 🇷🇺", callback_data="lang_ru")], [InlineKeyboardButton("Polski 🇵🇱", callback_data="lang_pl"), InlineKeyboardButton("Українська 🇺🇦", callback_data="lang_uk")]]))
    elif q.data.startswith("lang_"):
        new_lang = q.data[5:]; await adb_set(uid, lang=new_lang)
        kb = [[InlineKeyboardButton(THEMES["love"][new_lang], callback_data="theme_love"), InlineKeyboardButton(THEMES["fun"][new_lang], callback_data="theme_fun")], [InlineKeyboardButton(THEMES["holiday"][new_lang], callback_data="theme_holiday"), InlineKeyboardButton(THEMES["sad"][new_lang], callback_data="theme_sad")], [InlineKeyboardButton(THEMES["wedding"][new_lang], callback_data="theme_wedding"), InlineKeyboardButton(THEMES["custom"][new_lang], callback_data="theme_custom")]]
        await q.edit_message_text(tr(new_lang, "choose_theme"), reply_markup=InlineKeyboardMarkup(kb))
    elif q.data.startswith("theme_"):
        theme = q.data[6:]; state["theme"] = theme
        if theme == "custom":
            state["awaiting_custom"] = True; await adb_set(uid, state=state)
            await q.edit_message_text(tr(lang, "custom_theme_ask"))
        else:
            await adb_set(uid, state=state)
            await q.edit_message_text(tr(lang, "choose_genre"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Pop", callback_data="genre_pop"), InlineKeyboardButton("Rap", callback_data="genre_rap")], [InlineKeyboardButton("Rock", callback_data="genre_rock"), InlineKeyboardButton("Club", callback_data="genre_club")]]))
    elif q.data.startswith("genre_"):
        state["genre"] = q.data[6:]; await adb_set(uid, state=state)
        await q.edit_message_text(tr(lang, "describe"), parse_mode="Markdown")
    elif q.data.startswith("pay_"):
        pack = q.data.split("_")[1]
        await context.bot.send_invoice(chat_id=uid, title="Music Credits", description=f"{pack} songs", payload=f"pack_{pack}", provider_token="", currency="XTR", prices=[LabeledPrice("Stars", PACKS[pack])])

async def user_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = await adb_get_user(uid)
    lang, state = u["lang"], u["state"]

    if state.get("awaiting_custom"):
        state["custom_theme"] = update.message.text; state["awaiting_custom"] = False
        await adb_set(uid, state=state)
        await update.message.reply_text(tr(lang, "choose_genre"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Pop", callback_data="genre_pop"), InlineKeyboardButton("Rap", callback_data="genre_rap")]]))
        return

    if "genre" not in state:
        await update.message.reply_text(tr(lang, "start")); return

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

    final_theme = state.get("custom_theme") or state.get("theme")
    prompt = f"Song: {final_theme}, Genre: {state['genre']}, Story: {prompt_text}, Lang: {lang}"

    msg = await update.message.reply_text(tr(lang, "generating"))

    if u["demo_used"] == 0:
        res = await piapi_generate("DEMO: " + prompt)
        if res:
            try: await msg.edit_text(f"{tr(lang, 'demo_header')}\n\n{res[:3500]}", parse_mode="Markdown")
            except: await msg.edit_text(f"{tr(lang, 'demo_header')}\n\n{res[:3500]}")
            # ОБНОВЛЯЕМ БАЗУ ТОЛЬКО ПОСЛЕ УСПЕШНОЙ ОТПРАВКИ
            await adb_set(uid, demo_used=1)
        else: await msg.edit_text(tr(lang, "temp_error"))
    elif u["songs"] > 0:
        res = await piapi_generate("FULL: " + prompt)
        if res:
            try: await msg.edit_text(res[:3900], parse_mode="Markdown")
            except: await msg.edit_text(res[:3900])
            await adb_set(uid, songs=u["songs"]-1)
        else: await msg.edit_text(tr(lang, "temp_error"))
    else:
        await msg.delete()
        await update.message.reply_text(tr(lang, "no_credits"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⭐ Buy 1", callback_data="pay_1")]]))

async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = await adb_get_user(uid)
    pack = update.message.successful_payment.invoice_payload.replace("pack_", "")
    await adb_set(uid, songs=u["songs"] + int(pack))
    await update.message.reply_text(tr(u["lang"], "paid"))

def main():
    db_init()
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT | filters.VOICE, user_input))
    app.add_handler(PreCheckoutQueryHandler(pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    app.run_polling()

if __name__ == "__main__":
    main()
