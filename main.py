import telegram, sys
print("PTB VERSION:", telegram.__version__, "PY:", sys.version)
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
    raise RuntimeError("BOT_TOKEN or PIAPI_KEY not set in Environment Variables")

# -------------------- PRICES --------------------
PACKS = {"1": 250, "5": 1000, "25": 4000}

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

    # Сначала забираем данные, потом закрываем!
    res = {
        "user_id": row[0],
        "lang": row[1],
        "demo_used": row[2],
        "songs": row[3],
        "state": json.loads(row[4] or "{}")
    }
    con.close()
    return res

def db_set(user_id: int, lang: str = None, demo_used: int = None, songs: int = None, state: dict = None) -> None:
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    now = int(time.time())

    if lang is not None:
        cur.execute("UPDATE users SET lang=?, updated_at=? WHERE user_id=?", (lang, now, user_id))
    if demo_used is not None:
        cur.execute("UPDATE users SET demo_used=?, updated_at=? WHERE user_id=?", (demo_used, now, user_id))
    if songs is not None:
        cur.execute("UPDATE users SET songs=?, updated_at=? WHERE user_id=?", (songs, now, user_id))
    if state is not None:
        cur.execute("UPDATE users SET state_json=?, updated_at=? WHERE user_id=?", (json.dumps(state, ensure_ascii=False), now, user_id))

    con.commit()
    con.close()

async def adb_get_user(user_id: int): return await asyncio.to_thread(db_get_user, user_id)
async def adb_set(user_id: int, **kwargs): await asyncio.to_thread(db_set, user_id, **kwargs)

# -------------------- TEXTS --------------------
# (Тексты полностью сохранены из твоего кода)
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
        "en": "✍️ *Describe the song*\n\n1) Who is it for?\n2) Story / event\n3) Mood & emotions\n\n🎤 Or send a voice message.",
        "ru": "✍️ *Опиши песню*\n\n1) Кому посвящается?\n2) История / событие\n3) Настроение и эмоции\n\n🎤 Если лень писать — отправь голосовое.",
        "pl": "✍️ *Opisz piosenkę*\n\n1) Dla kogo?\n2) Historia / wydarzenie\n3) Klimat i emocje\n\n🎤 Jeśli nie chcesz pisać — wyślij głosówkę.",
        "de": "✍️ *Beschreibe das Lied*\n\n1) Für wen?\n2) Geschichte / Ereignis\n3) Stimmung & Emotionen\n\n🎤 Если ты не хочешь печатать — отправь голосовое.",
        "es": "✍️ *Describe la canción*\n\n1) ¿Para quién es?\n2) Historia / evento\n3) Ánimo y emociones\n\n🎤 Si no quieres escribir — envía un mensaje de voz.",
        "fr": "✍️ *Décris la chanson*\n\n1) Pour qui ?\n2) Histoire / événement\n3) Ambiance & émotions\n\n🎤 Si tu ne veux pas écrire — envoie un vocal.",
        "uk": "✍️ *Опиши пісню*\n\n1) Кому присвячена?\n2) Історія / подія\n3) Настрій і емоції\n\n🎤 Якщо не хочеш писати — надішли голосове.",
    },
    "custom_theme_ask": {"en": "✏️ Write your custom theme:", "ru": "✏️ Напиши свой вариант темы:", "pl": "✏️ Napisz własny temat:", "de": "✏️ Eigene Variante:", "es": "✏️ Tu opción:", "fr": "✏️ Votre option:", "uk": "✏️ Свій варіант:"},
    "demo_header": {"en": "🎧 *Demo version*", "ru": "🎧 *Демо-версия*", "pl": "🎧 *Wersja demo*", "de": "🎧 *Demo-Version*", "es": "🎧 *Versión demo*", "fr": "🎧 *Version démo*", "uk": "🎧 *Демо-версія*"},
    "buy_confirm": {"en": "⚠️ Spend ⭐ {stars}?", "ru": "⚠️ Потратить ⭐ {stars}?", "pl": "⚠️ Wydać ⭐ {stars}?", "de": "⚠️ ⭐ {stars} ausgeben?", "es": "⚠️ ¿Gastar ⭐ {stars}?", "fr": "⚠️ Dépenser ⭐ {stars}?", "uk": "⚠️ Витратити ⭐ {stars}?"},
    "paid": {"en": "✅ Done!", "ru": "✅ Оплачено!", "pl": "✅ Zapłacono!", "de": "✅ Bezahlt!", "es": "✅ ¡Pagado!", "fr": "✅ Payé !", "uk": "✅ Оплачено!"},
    "need_start": {"en": "Press /start", "ru": "Нажми /start", "pl": "Naciśnij /start", "de": "Bitte /start", "es": "Pulsa /start", "fr": "Appuie sur /start", "uk": "Натисни /start"},
    "generating": {"en": "⏳ Generating...", "ru": "⏳ Генерирую...", "pl": "⏳ Generuję...", "de": "⏳ Generiere...", "es": "⏳ Generando...", "fr": "⏳ Génération...", "uk": "⏳ Генерую..."},
    "no_credits": {"en": "0 songs left. Buy pack 👇", "ru": "0 песен. Купи пакет 👇", "pl": "0 piosenek. Kup pakiet 👇", "de": "0 Songs. Paket kaufen 👇", "es": "0 canciones. Compra 👇", "fr": "0 chanson. Achète 👇", "uk": "0 пісень. Купи пакет 👇"},
    "temp_error": {"en": "⚠️ Error. Try later.", "ru": "⚠️ Ошибка. Попробуй позже.", "pl": "⚠️ Błąd. Spróbuj później.", "de": "⚠️ Fehler. Später.", "es": "⚠️ Error.", "fr": "⚠️ Erreur.", "uk": "⚠️ Помилка."},
    "help": {"en": "ℹ️ *Help*\nSongs belong to you.", "ru": "ℹ️ *Help*\nПрава принадлежат вам.", "pl": "ℹ️ *Help*\nPrawa należą do Ciebie.", "de": "ℹ️ *Help*\nRechte gehören dir.", "es": "ℹ️ *Help*", "fr": "ℹ️ *Aide*", "uk": "ℹ️ *Допомога*"}
}

THEMES = {
    "love": {"en":"Love ❤️","ru":"Любовь ❤️","pl":"Miłość ❤️","de":"Liebe ❤️","es":"Amor ❤️","fr":"Amour ❤️","uk":"Кохання ❤️"},
    "fun": {"en":"Funny 😄","ru":"Смешная 😄","pl":"Zabawna 😄","de":"Lustig 😄","es":"Divertida 😄","fr":"Drôle 😄","uk":"Весела 😄"},
    "holiday": {"en":"Holiday 🎉","ru":"Праздник 🎉","pl":"Święto 🎉","de":"Feier 🎉","es":"Fiesta 🎉","fr":"Fête 🎉","uk":"Свято 🎉"},
    "sad": {"en":"Sad 😢","ru":"Грусть 😢","pl":"Smutna 😢","de":"Traurig 😢","es":"Triste 😢","fr":"Triste 😢","uk":"Сум 😢"},
    "wedding": {"en":"Wedding 💍","ru":"Свадьба 💍","pl":"Wesele 💍","de":"Hochzeit 💍","es":"Boda 💍","fr":"Mariage 💍","uk":"Весілля 💍"},
    "custom": {"en":"Custom ✏️","ru":"Свой вариант ✏️","pl":"Własny ✏️","de":"Eigene ✏️","es":"Tu opción ✏️","fr":"Votre option ✏️","uk":"Свій варіант ✏️"},
}

def tr(lang, key): return TEXTS.get(key, {}).get(lang, TEXTS.get(key, {}).get("en", "Missing text"))

# -------------------- API CALLS --------------------
async def piapi_generate(prompt: str) -> Optional[str]:
    url = "https://api.piapi.ai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {PIAPI_KEY}", "Content-Type": "application/json"}
    payload = {"model": "pi-music", "messages": [{"role": "user", "content": prompt}]}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=120) as r:
                data = await r.json()
                if "choices" in data: return data["choices"][0]["message"]["content"]
                if "content" in data: return data["content"]
                return str(data)
    except Exception as e:
        logger.error("PiAPI Error: %s", e)
        return None

async def voice_to_text(file_path: str) -> Optional[str]:
    if not OPENAI_API_KEY: return None
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        with open(file_path, "rb") as f:
            res = await client.audio.transcriptions.create(model="whisper-1", file=f)
        return res.text
    except Exception as e:
        logger.error("Whisper Error: %s", e)
        return None

# -------------------- KEYBOARDS --------------------
def kb_languages():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("English 🇬🇧", callback_data="lang_en"), InlineKeyboardButton("Русский 🇷🇺", callback_data="lang_ru")],
        [InlineKeyboardButton("Polski 🇵🇱", callback_data="lang_pl"), InlineKeyboardButton("Deutsch 🇩🇪", callback_data="lang_de")],
        [InlineKeyboardButton("Español 🇪🇸", callback_data="lang_es"), InlineKeyboardButton("Français 🇫🇷", callback_data="lang_fr")],
        [InlineKeyboardButton("Українська 🇺🇦", callback_data="lang_uk")]
    ])

def kb_themes(lang):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(THEMES["love"][lang], callback_data="theme_love"), InlineKeyboardButton(THEMES["fun"][lang], callback_data="theme_fun")],
        [InlineKeyboardButton(THEMES["holiday"][lang], callback_data="theme_holiday"), InlineKeyboardButton(THEMES["sad"][lang], callback_data="theme_sad")],
        [InlineKeyboardButton(THEMES["wedding"][lang], callback_data="theme_wedding"), InlineKeyboardButton(THEMES["custom"][lang], callback_data="theme_custom")]
    ])

def kb_genres():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Pop", callback_data="genre_pop"), InlineKeyboardButton("Rap", callback_data="genre_rap")],
        [InlineKeyboardButton("Rock", callback_data="genre_rock"), InlineKeyboardButton("Club", callback_data="genre_club")],
        [InlineKeyboardButton("Classical", callback_data="genre_classical"), InlineKeyboardButton("Disco Polo", callback_data="genre_disco")]
    ])

def kb_buy():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ 1 song — 250", callback_data="buy_1")],
        [InlineKeyboardButton("⭐ 5 songs — 1000", callback_data="buy_5")],
        [InlineKeyboardButton("⭐ 25 songs — 4000", callback_data="buy_25")]
    ])

# -------------------- HANDLERS --------------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = await adb_get_user(uid)
    await adb_set(uid, state={})
    await update.message.reply_text(tr(u["lang"], "start"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ START", callback_data="start")]]), parse_mode="Markdown")

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
        await adb_set(uid, lang=new_lang, state={"lang": new_lang})
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
    elif q.data.startswith("buy_"):
        pack = q.data.split("_")[1]
        stars = PACKS[pack]
        await q.edit_message_text(tr(lang, "buy_confirm").format(stars=stars), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Yes", callback_data=f"pay_{pack}"), InlineKeyboardButton("❌ No", callback_data="start")]]), parse_mode="Markdown")
    elif q.data.startswith("pay_"):
        pack = q.data.split("_")[1]
        await context.bot.send_invoice(chat_id=uid, title="MusicAi Pack", description=f"{pack} songs", payload=f"pack_{pack}", provider_token="", currency="XTR", prices=[LabeledPrice("Stars", PACKS[pack])])

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
        await update.message.reply_text(tr(lang, "need_start")); return

    prompt_text = ""
    if update.message.voice:
        wait = await update.message.reply_text(tr(lang, "generating"))
        file = await context.bot.get_file(update.message.voice.file_id)
        path = f"v_{uid}.ogg"
        await file.download_to_drive(path)
        prompt_text = await voice_to_text(path)
        os.remove(path)
        if not prompt_text: await wait.edit_text("Voice error."); return
        await wait.delete()
    else:
        prompt_text = update.message.text

    theme = state.get("custom_theme") or state.get("theme")
    prompt = f"Song about {theme}, Genre: {state['genre']}, Story: {prompt_text}. Language: {state.get('lang', lang)}"

    if u["demo_used"] == 0:
        msg = await update.message.reply_text(tr(lang, "generating"))
        res = await piapi_generate("DEMO: " + prompt)
        if res:
            await msg.edit_text(f"{tr(lang, 'demo_header')}\n\n{res[:3500]}", parse_mode="Markdown")
            await adb_set(uid, demo_used=1)
        else: await msg.edit_text(tr(lang, "temp_error"))
    elif u["songs"] > 0:
        msg = await update.message.reply_text(tr(lang, "generating"))
        res = await piapi_generate("FULL SONG: " + prompt)
        if res:
            await msg.edit_text(res[:3900])
            await adb_set(uid, songs=u["songs"]-1)
        else: await msg.edit_text(tr(lang, "temp_error"))
    else:
        await update.message.reply_text(tr(lang, "no_credits"), reply_markup=kb_buy())

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
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT | filters.VOICE, user_input))
    app.add_handler(PreCheckoutQueryHandler(pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    app.run_polling()

if __name__ == "__main__":
    main()
