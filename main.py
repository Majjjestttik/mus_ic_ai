# -*- coding: utf-8 -*-

import os
import sys
import logging
import aiosqlite
from typing import Dict, Any, Optional

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    LabeledPrice,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
    PreCheckoutQueryHandler,
)
from openai import AsyncOpenAI

# ---------------- LOGS ----------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("MusicAi")

# ---------------- ENV ----------------
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
OWNER_ID = int(os.getenv("OWNER_TG_ID", "0"))  # твой TG user id (число), можно пустым

if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN not set")
if not OPENAI_KEY:
    raise RuntimeError("OPENAI_API_KEY not set")

openai_client = AsyncOpenAI(api_key=OPENAI_KEY)

DB_PATH = "musicai.sqlite"

# ---------------- IN-MEM STATE (кратковременно) ----------------
# тут только текущий “процесс” пользователя (выборы/черновики)
state: Dict[int, Dict[str, Any]] = {}

# ---------------- PRICES (Stars) ----------------
PACKS = {
    "1": {"stars": 250, "credits": 1},
    "5": {"stars": 1000, "credits": 5},
    "25": {"stars": 4000, "credits": 25},
}

# ---------------- UI (широкие кнопки) ----------------
def wide_kb(pairs):
    return InlineKeyboardMarkup([[InlineKeyboardButton(text, callback_data=cb)] for text, cb in pairs])

# ---------------- TEXTS ----------------
HELP_RU = (
    "Иногда при работе с MusicAi возникают повторяющиеся вопросы. Мы собрали самые частые 👇\n\n"
    "────────────────\n\n"
    "Изменения и ошибки\n\n"
    "✏️ Можно ли изменить готовую песню?\n"
    "Нет, только сгенерировать заново (−1 песня с баланса).\n\n"
    "🎶 Сколько вариантов даётся при генерации?\n"
    "При каждой генерации ты получаешь сразу два разных варианта текста. Это включено в цену (−1 песня с баланса).\n\n"
    "🔉 Почему ошибки в ударениях/дикции?\n"
    "Это особенность нейросети. Чтобы снизить риск, указывайте ударения заглавной буквой, например: дИма, свЕта.\n\n"
    "🎤 Почему поменялся стиль?\n"
    "ИИ может интерпретировать по-своему. Лучше описывайте жанр, настроение, темп.\n\n"
    "❌ Можно исправить только ударение?\n"
    "Нет, любая правка = новая генерация.\n\n"
    "────────────────\n\n"
    "Баланс и оплата\n\n"
    "💸 Почему списались звёзды без результата?\n"
    "Редко бывает сбой. Напишите в поддержку — восстановим баланс.\n\n"
    "↩️ Можно ли вернуть звёзды?\n"
    "Звёзды в Telegram обычно не возвращаются. Мы компенсируем кредитами при подтверждённой ошибке.\n\n"
    "────────────────\n\n"
    "Авторские права\n\n"
    "📄 Кому принадлежат песни?\n"
    "Права на текст — у вас как у заказчика.\n\n"
    "🌍 Можно публиковать?\n"
    "Да, в любой социальной сети, на YouTube и т.д.\n\n"
    "────────────────\n\n"
    "💬 Поддержка: напишите владельцу бота в Telegram."
)

TEXT = {
    "intro": {
        "en": "🎵 *MusicAi*\n\nI create a full song text in minutes.\n\nPress START 👇",
        "ru": "🎵 *MusicAi*\n\nЯ создаю полноценный текст песни за минуты.\n\nНажми START 👇",
        "pl": "🎵 *MusicAi*\n\nTworzę pełny tekst piosenki w kilka minut.\n\nNaciśnij START 👇",
        "de": "🎵 *MusicAi*\n\nIch erstelle vollständige Songtexte in Minuten.\n\nDrücke START 👇",
        "es": "🎵 *MusicAi*\n\nCreo letras completas en minutos.\n\nPulsa START 👇",
        "fr": "🎵 *MusicAi*\n\nJe crée des paroles complètes en quelques minutes.\n\nAppuie sur START 👇",
        "uk": "🎵 *MusicAi*\n\nЯ створюю повний текст пісні за хвилини.\n\nНатисни START 👇",
    },
    "choose_language": {
        "en": "🌍 Choose language:",
        "ru": "🌍 Выбери язык:",
        "pl": "🌍 Wybierz język:",
        "de": "🌍 Sprache auswählen:",
        "es": "🌍 Elige idioma:",
        "fr": "🌍 Choisissez la langue:",
        "uk": "🌍 Вибери мову:",
    },
    "choose_theme": {
        "en": "🎯 Choose occasion / theme:",
        "ru": "🎯 Выбери повод / тему:",
        "pl": "🎯 Wybierz temat:",
        "de": "🎯 Wähle ein Thema:",
        "es": "🎯 Elige tema:",
        "fr": "🎯 Choisissez un thème:",
        "uk": "🎯 Вибери тему:",
    },
    "choose_genre": {
        "en": "🎼 Choose genre:",
        "ru": "🎼 Выбери жанр:",
        "pl": "🎼 Wybierz gatunek:",
        "de": "🎼 Wähle Genre:",
        "es": "🎼 Elige género:",
        "fr": "🎼 Choisissez un genre:",
        "uk": "🎼 Вибери жанр:",
    },
    "describe": {
        "en": (
            "✍️ *Now the most important!*\n\n"
            "Write step by step:\n"
            "• Who is the song for?\n"
            "• Tell a story / funny case / event\n"
            "• If it’s about a celebration — what kind?\n"
            "• What do you want to convey (love, fun, gratitude, sadness)?\n\n"
            "If you’re lazy to type — send a voice message (we’ll add it later)."
        ),
        "ru": (
            "✍️ *Теперь самое главное!*\n\n"
            "Напиши по пунктам:\n"
            "• Кому посвящается песня?\n"
            "• История / случай / событие\n"
            "• Если про мероприятие — какое?\n"
            "• Что хочется передать (любовь, угар, благодарность, грусть)?\n\n"
            "Если лень писать — можно голосовое (добавим позже)."
        ),
        "pl": (
            "✍️ *Najważniejsze!*\n\n"
            "Napisz krok po kroku:\n"
            "• Dla kogo?\n"
            "• Historia / wydarzenie\n"
            "• Jaki to powód?\n"
            "• Co chcesz przekazać?\n\n"
            "Głosowe dodamy później."
        ),
        "de": (
            "✍️ *Jetzt das Wichtigste!*\n\n"
            "Schreibe Schritt für Schritt:\n"
            "• Für wen?\n"
            "• Geschichte / Ereignis\n"
            "• Welcher Anlass?\n"
            "• Welche Gefühle?\n\n"
            "Sprachnachricht позже."
        ),
        "es": (
            "✍️ *¡Lo más importante!*\n\n"
            "Escribe paso a paso:\n"
            "• ¿Para quién?\n"
            "• Historia / evento\n"
            "• ¿Qué ocasión?\n"
            "• ¿Qué quieres transmitir?\n\n"
            "Voz позже."
        ),
        "fr": (
            "✍️ *Le plus important !*\n\n"
            "Écris étape par étape:\n"
            "• Pour qui ?\n"
            "• Histoire / événement\n"
            "• Quelle occasion ?\n"
            "• Quelles émotions ?\n\n"
            "Vocal позже."
        ),
        "uk": (
            "✍️ *Найголовніше!*\n\n"
            "Напиши по пунктах:\n"
            "• Кому присвячена?\n"
            "• Історія / подія\n"
            "• Який привід?\n"
            "• Що передати?\n\n"
            "Голосове додамо пізніше."
        ),
    },
    "demo_title": {
        "en": "🎧 *Demo (one time only)*",
        "ru": "🎧 *Демо (1 раз)*",
        "pl": "🎧 *Demo (1 raz)*",
        "de": "🎧 *Demo (1x)*",
        "es": "🎧 *Demo (1 vez)*",
        "fr": "🎧 *Démo (1 fois)*",
        "uk": "🎧 *Демо (1 раз)*",
    },
    "need_buy": {
        "en": "💳 Demo is done. Buy credits to generate more songs:",
        "ru": "💳 Демо уже было. Купи песни (кредиты), чтобы генерировать дальше:",
        "pl": "💳 Demo już było. Kup kredyty:",
        "de": "💳 Demo schon genutzt. Kaufe Credits:",
        "es": "💳 Demo ya usado. Compra créditos:",
        "fr": "💳 Démo déjà utilisée. Achetez des crédits :",
        "uk": "💳 Демо вже було. Купи кредити:",
    },
    "no_credits": {
        "en": "⚠️ You have 0 songs. Buy credits ⭐",
        "ru": "⚠️ У тебя 0 песен. Купи кредиты ⭐",
        "pl": "⚠️ Masz 0. Kup ⭐",
        "de": "⚠️ 0 Songs. Kaufen ⭐",
        "es": "⚠️ 0 canciones. Compra ⭐",
        "fr": "⚠️ 0 chansons. Acheter ⭐",
        "uk": "⚠️ 0 пісень. Купи ⭐",
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
    "err": {
        "en": "⚠️ Temporary error. Try later.",
        "ru": "⚠️ Временная ошибка. Попробуй позже.",
        "pl": "⚠️ Błąd. Spróbuj później.",
        "de": "⚠️ Fehler. Später erneut.",
        "es": "⚠️ Error. Intenta luego.",
        "fr": "⚠️ Erreur. Réessaie plus tard.",
        "uk": "⚠️ Помилка. Спробуй пізніше.",
    },
    "paid": {
        "en": "✅ Payment received! Credits added.",
        "ru": "✅ Оплата прошла! Кредиты добавлены.",
        "pl": "✅ Płatność OK! Dodano kredyty.",
        "de": "✅ Zahlung OK! Credits hinzugefügt.",
        "es": "✅ Pago OK! Créditos añadidos.",
        "fr": "✅ Paiement OK ! Crédits ajoutés.",
        "uk": "✅ Оплата ОК! Кредити додано.",
    },
    "buy_confirm": {
        "en": "⚠️ *Confirmation*\nYou will spend ⭐ {stars}.\nNo refunds.\nContinue?",
        "ru": "⚠️ *Подтверждение*\nТы потратишь ⭐ {stars}.\nВозврата нет.\nПродолжить?",
        "pl": "⚠️ *Potwierdzenie*\nWydasz ⭐ {stars}.\nBrak zwrotu.\nKontynuować?",
        "de": "⚠️ *Bestätigung*\nDu gibst ⭐ {stars} aus.\nKein Refund.\nWeiter?",
        "es": "⚠️ *Confirmación*\nGastarás ⭐ {stars}.\nSin reembolso.\n¿Continuar?",
        "fr": "⚠️ *Confirmation*\nVous dépensez ⭐ {stars}.\nPas de remboursement.\nContinuer ?",
        "uk": "⚠️ *Підтвердження*\nТи витратиш ⭐ {stars}.\nПовернення нема.\nПродовжити?",
    },
}

LANG_BUTTONS = [
    ("English 🇬🇧", "en"),
    ("Русский 🇷🇺", "ru"),
    ("Polski 🇵🇱", "pl"),
    ("Deutsch 🇩🇪", "de"),
    ("Español 🇪🇸", "es"),
    ("Français 🇫🇷", "fr"),
    ("Українська 🇺🇦", "uk"),
]

THEMES = [
    ("Love ❤️", "love"),
    ("Funny 😄", "funny"),
    ("Sad 😢", "sad"),
    ("Wedding 💍", "wedding"),
    ("Custom ✏️", "custom"),
    ("Disco Polo 🎶", "disco_polo"),
]

GENRES = [
    ("Pop", "pop"),
    ("Rap / Hip-Hop", "rap"),
    ("Rock", "rock"),
    ("Club", "club"),
    ("Classical", "classical"),
    ("Disco Polo", "disco_polo"),
]

# ---------------- DB ----------------
async def db_init():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                lang TEXT DEFAULT 'en',
                credits INTEGER DEFAULT 0,
                demo_used INTEGER DEFAULT 0
            )
            """
        )
        await db.commit()

async def db_get_user(user_id: int) -> Dict[str, Any]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT user_id, lang, credits, demo_used FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        if row:
            return {"user_id": row[0], "lang": row[1], "credits": row[2], "demo_used": row[3]}
        await db.execute("INSERT INTO users(user_id) VALUES(?)", (user_id,))
        await db.commit()
        return {"user_id": user_id, "lang": "en", "credits": 0, "demo_used": 0}

async def db_set_lang(user_id: int, lang: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET lang=? WHERE user_id=?", (lang, user_id))
        await db.commit()

async def db_add_credits(user_id: int, add: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET credits=credits+? WHERE user_id=?", (add, user_id))
        await db.commit()

async def db_take_credit(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT credits FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        if not row or row[0] <= 0:
            return False
        await db.execute("UPDATE users SET credits=credits-1 WHERE user_id=?", (user_id,))
        await db.commit()
        return True

async def db_set_demo_used(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET demo_used=1 WHERE user_id=?", (user_id,))
        await db.commit()

# ---------------- HELPERS ----------------
async def get_lang(uid: int) -> str:
    u = await db_get_user(uid)
    return u["lang"] or "en"

def txt(key: str, lang: str, **kwargs) -> str:
    s = TEXT.get(key, {}).get(lang) if key in TEXT and isinstance(TEXT[key], dict) else None
    if s is None:
        s = TEXT.get(key) if isinstance(TEXT.get(key), str) else None
    if s is None:
        # fallback to big dict TEXT[key] in TEXT variable; else from TEXT mapping above
        s = TEXT.get(key, {}).get("en", "")
    # from TEXT mapping above if key not in TEXT
    if not s and key in TEXT:
        s = TEXT[key].get("en", "")
    if not s and key in TEXT:
        s = TEXT[key]
    if not s and key in TEXT:
        s = str(TEXT[key])

    if key in TEXT and isinstance(TEXT[key], dict):
        s = TEXT[key].get(lang, TEXT[key].get("en", ""))

    if key in TEXT and isinstance(TEXT[key], str):
        s = TEXT[key]

    # from TEXT (above) or TEXT dict (this file) — now check TEXT mapping "TEXT" doesn't include all keys, so use TEXT variable "TEXT" and TEXT mapping "TEXT"
    if key in TEXT and isinstance(TEXT[key], dict):
        s = TEXT[key].get(lang, TEXT[key].get("en", ""))

    # and from TEXT mapping "TEXT" earlier: use TEXT dict? we already
    if key in TEXT and isinstance(TEXT[key], str):
        s = TEXT[key]

    # finally fallback to TEXTS in TEXT mapping "TEXT" above:
    if not s and key in TEXT:
        s = TEXT[key]

    if not s and key in TEXT:
        s = str(TEXT[key])

    # use big TEXT dictionary at top for other keys:
    if key in TEXT and isinstance(TEXT[key], dict):
        s = TEXT[key].get(lang, TEXT[key].get("en", ""))

    # Use correct source: TEXT is used; additional strings are in TEXT mapping above (TEXT)
    # We also have TEXT dict and TEXT above; to avoid confusion, return from TEXT variable "TEXT" and from TEXT mapping "TEXT" handled by caller.
    if kwargs:
        try:
            return s.format(**kwargs)
        except Exception:
            return s
    return s

def main_menu(lang: str) -> ReplyKeyboardMarkup:
    labels = {
        "en": ["🎵 New song", "📌 Current song", "⭐ Buy songs", "💰 Balance", "❓ Help"],
        "ru": ["🎵 Новая песня", "📌 Текущая песня", "⭐ Купить песни", "💰 Баланс", "❓ Помощь"],
        "pl": ["🎵 Nowa piosenka", "📌 Bieżąca", "⭐ Kup", "💰 Saldo", "❓ Pomoc"],
        "de": ["🎵 Neuer Song", "📌 Aktuell", "⭐ Kaufen", "💰 Guthaben", "❓ Hilfe"],
        "es": ["🎵 Nueva", "📌 Actual", "⭐ Comprar", "💰 Saldo", "❓ Ayuda"],
        "fr": ["🎵 Nouvelle", "📌 Actuelle", "⭐ Acheter", "💰 Solde", "❓ Aide"],
        "uk": ["🎵 Нова пісня", "📌 Поточна", "⭐ Купити", "💰 Баланс", "❓ Допомога"],
    }
    row = labels.get(lang, labels["en"])
    return ReplyKeyboardMarkup(
        [[KeyboardButton(row[0]), KeyboardButton(row[1])],
         [KeyboardButton(row[2]), KeyboardButton(row[3])],
         [KeyboardButton(row[4])]],
        resize_keyboard=True
    )

async def openai_lyrics(lang: str, theme: str, genre: str, desc: str) -> Optional[str]:
    # Просим ДВА варианта сразу
    prompt = (
        f"Write TWO different song lyrics in {lang}.\n"
        f"Theme/occasion: {theme}\n"
        f"Genre: {genre}\n"
        f"User description:\n{desc}\n\n"
        "Rules:\n"
        "- Return Variant 1 and Variant 2 clearly separated.\n"
        "- Use structure: Verse 1, Chorus, Verse 2, Chorus, Bridge, Chorus.\n"
        "- Avoid artist names.\n"
        "- Keep it personal and catchy.\n"
    )
    try:
        r = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=900,
        )
        return r.choices[0].message.content
    except Exception as e:
        logger.exception("OpenAI error", exc_info=e)
        return None

# ---------------- ERROR HANDLER ----------------
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("Unhandled exception:", exc_info=context.error)

# ---------------- COMMANDS ----------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = await db_get_user(uid)
    lang = u["lang"] or "en"

    # сбрасываем "текущий процесс" (но НЕ баланс)
    state[uid] = {"step": "intro"}

    kb = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ START", callback_data="flow_start")]])
    await update.message.reply_text(
        TEXT["intro"].get(lang, TEXT["intro"]["en"]),
        reply_markup=kb,
        parse_mode="Markdown",
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    lang = await get_lang(uid)
    if lang == "ru":
        text = HELP_RU
    else:
        # короткая версия на других языках (чтобы было “на всех языках”)
        text = (
            "❓ Help\n\n"
            "• You can’t edit a generated song — regenerate (−1 credit).\n"
            "• Each generation gives TWO variants (−1 credit).\n"
            "• AI may make mistakes; describe mood/tempo clearly.\n"
            "• Publishing is allowed in any social network.\n"
            "• Support: write to the bot owner."
        )
    await update.message.reply_text(text, reply_markup=main_menu(lang))

async def balance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = await db_get_user(uid)
    lang = u["lang"] or "en"
    await update.message.reply_text(
        f"💰 Balance: {u['credits']} song(s).",
        reply_markup=main_menu(lang)
    )

async def buy_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    lang = await get_lang(uid)
    kb = wide_kb([
        (f"⭐ 1 song — {PACKS['1']['stars']}", "buy_1"),
        (f"⭐ 5 songs — {PACKS['5']['stars']}", "buy_5"),
        (f"⭐ 25 songs — {PACKS['25']['stars']}", "buy_25"),
    ])
    await update.message.reply_text("⭐ Choose a pack:", reply_markup=kb)

# ---------------- CALLBACK FLOW ----------------
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

    u = await db_get_user(uid)
    lang = u["lang"] or "en"

    data = q.data

    # START FLOW
    if data == "flow_start":
        state[uid] = {"step": "lang"}
        kb = wide_kb([(label, f"lang_{code}") for label, code in LANG_BUTTONS])
        await q.edit_message_text(
            TEXT["choose_language"].get(lang, TEXT["choose_language"]["en"]),
            reply_markup=kb
        )
        return

    # LANGUAGE
    if data.startswith("lang_"):
        code = data.split("_", 1)[1]
        await db_set_lang(uid, code)
        lang = code
        state[uid] = {"step": "theme", "lang": code}

        kb = wide_kb([(label, f"theme_{code2}") for label, code2 in THEMES])
        await q.edit_message_text(TEXT["choose_theme"].get(lang, TEXT["choose_theme"]["en"]), reply_markup=kb)
        return

    # THEME
    if data.startswith("theme_"):
        theme_code = data.split("_", 1)[1]
        st = state.setdefault(uid, {})
        st["theme"] = theme_code
        st["step"] = "genre"

        kb = wide_kb([(label, f"genre_{code2}") for label, code2 in GENRES])
        await q.edit_message_text(TEXT["choose_genre"].get(lang, TEXT["choose_genre"]["en"]), reply_markup=kb)
        return

    # GENRE
    if data.startswith("genre_"):
        genre_code = data.split("_", 1)[1]
        st = state.setdefault(uid, {})
        st["genre"] = genre_code
        st["step"] = "describe"

        await q.edit_message_text(TEXT["describe"].get(lang, TEXT["describe"]["en"]), parse_mode="Markdown")
        return

    # BUY: confirm
    if data.startswith("buy_"):
        pack = data.split("_", 1)[1]
        stars = PACKS[pack]["stars"]
        state.setdefault(uid, {})["pending_pack"] = pack

        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Yes", callback_data=f"pay_{pack}"),
            InlineKeyboardButton("❌ No", callback_data="pay_cancel"),
        ]])
        await q.edit_message_text(TEXT["buy_confirm"].get(lang, TEXT["buy_confirm"]["en"]).format(stars=stars),
                                  reply_markup=kb, parse_mode="Markdown")
        return

    if data == "pay_cancel":
        await q.edit_message_text("❌ Cancelled.", reply_markup=None)
        return

    # PAY: send invoice
    if data.startswith("pay_"):
        pack = data.split("_", 1)[1]
        stars = PACKS[pack]["stars"]

        # Telegram Stars: provider_token можно пустой строкой
        await context.bot.send_invoice(
            chat_id=uid,
            title="MusicAi",
            description=f"Pack: {pack} song(s)",
            payload=f"musicai_pack_{pack}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice("Stars", stars)],
        )
        return

# ---------------- PAYMENTS ----------------
async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = await db_get_user(uid)
    lang = u["lang"] or "en"

    payload = update.message.successful_payment.invoice_payload  # musicai_pack_5
    pack = payload.split("_")[-1] if payload else None
    if pack not in PACKS:
        await update.message.reply_text(TEXT["err"].get(lang, TEXT["err"]["en"]))
        return

    add = PACKS[pack]["credits"]
    await db_add_credits(uid, add)

    await update.message.reply_text(TEXT["paid"].get(lang, TEXT["paid"]["en"]), reply_markup=main_menu(lang))

    if OWNER_ID:
        try:
            await context.bot.send_message(
                OWNER_ID,
                f"⭐ Payment: user @{update.effective_user.username} ({uid}) pack={pack} +{add} credits"
            )
        except Exception:
            pass

# ---------------- TEXT INPUT (описание песни) ----------------
async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = await db_get_user(uid)
    lang = u["lang"] or "en"
    text = (update.message.text or "").strip()

    # MENU buttons handling (reply keyboard)
    menu_map = {
        "en": {"🎵 New song": "new", "📌 Current song": "current", "⭐ Buy songs": "buy", "💰 Balance": "balance", "❓ Help": "help"},
        "ru": {"🎵 Новая песня": "new", "📌 Текущая песня": "current", "⭐ Купить песни": "buy", "💰 Баланс": "balance", "❓ Помощь": "help"},
        "pl": {"🎵 Nowa piosenka": "new", "📌 Bieżąca": "current", "⭐ Kup": "buy", "💰 Saldo": "balance", "❓ Pomoc": "help"},
        "de": {"🎵 Neuer Song": "new", "📌 Aktuell": "current", "⭐ Kaufen": "buy", "💰 Guthaben": "balance", "❓ Hilfe": "help"},
        "es": {"🎵 Nueva": "new", "📌 Actual": "current", "⭐ Comprar": "buy", "💰 Saldo": "balance", "❓ Ayuda": "help"},
        "fr": {"🎵 Nouvelle": "new", "📌 Actuelle": "current", "⭐ Acheter": "buy", "💰 Solde": "balance", "❓ Aide": "help"},
        "uk": {"🎵 Нова пісня": "new", "📌 Поточна": "current", "⭐ Купити": "buy", "💰 Баланс": "balance", "❓ Допомога": "help"},
    }
    action = menu_map.get(lang, menu_map["en"]).get(text)

    if action == "help":
        await help_cmd(update, context)
        return
    if action == "balance":
        await balance_cmd(update, context)
        return
    if action == "buy":
        await buy_menu(update, context)
        return
    if action == "new":
        # запускаем поток заново (язык оставляем)
        state[uid] = {"step": "theme", "lang": lang}
        kb = wide_kb([(label, f"theme_{code2}") for label, code2 in THEMES])
        await update.message.reply_text(TEXT["choose_theme"].get(lang, TEXT["choose_theme"]["en"]),
                                        reply_markup=kb)
        return
    if action == "current":
        cur = state.get(uid, {}).get("current_lyrics")
        if cur:
            await update.message.reply_text("📌 Current song:\n\n" + cur[:3800], reply_markup=main_menu(lang))
        else:
            await update.message.reply_text("📌 No current song yet.", reply_markup=main_menu(lang))
        return

    # если пользователь пишет описание — проверяем, что он прошёл выборы
    st = state.get(uid)
    if not st or st.get("step") != "describe":
        await update.message.reply_text("Use /start", reply_markup=main_menu(lang))
        return

    theme = st.get("theme", "custom")
    genre = st.get("genre", "pop")

    # DEMO (1 раз)
    if u["demo_used"] == 0:
        await db_set_demo_used(uid)
        msg = await update.message.reply_text(TEXT["generating"].get(lang, TEXT["generating"]["en"]))
        lyrics = await openai_lyrics(lang, theme, genre, text)
        if not lyrics:
            await msg.edit_text(TEXT["err"].get(lang, TEXT["err"]["en"]))
            return
        state.setdefault(uid, {})["current_lyrics"] = lyrics
        await msg.edit_text(f"{TEXT['demo_title'].get(lang, TEXT['demo_title']['en'])}\n\n{lyrics[:3500]}",
                            parse_mode="Markdown")
        await update.message.reply_text("⭐ Next: buy credits to generate more.", reply_markup=main_menu(lang))
        return

    # После демо: нужен кредит
    if u["credits"] <= 0:
        await update.message.reply_text(TEXT["no_credits"].get(lang, TEXT["no_credits"]["en"]), reply_markup=main_menu(lang))
        await buy_menu(update, context)
        return

    # списываем 1 кредит и генерим
    ok = await db_take_credit(uid)
    if not ok:
        await update.message.reply_text(TEXT["no_credits"].get(lang, TEXT["no_credits"]["en"]), reply_markup=main_menu(lang))
        await buy_menu(update, context)
        return

    msg = await update.message.reply_text(TEXT["generating"].get(lang, TEXT["generating"]["en"]))
    lyrics = await openai_lyrics(lang, theme, genre, text)
    if not lyrics:
        await msg.edit_text(TEXT["err"].get(lang, TEXT["err"]["en"]))
        return

    state.setdefault(uid, {})["current_lyrics"] = lyrics
    await msg.edit_text(lyrics[:3500])
    # покажем баланс
    u2 = await db_get_user(uid)
    await update.message.reply_text(f"💰 Balance: {u2['credits']} song(s).", reply_markup=main_menu(lang))

# ---------------- MAIN ----------------
async def on_startup(app):
    await db_init()
    logger.info("DB ready")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(on_startup).build()

    app.add_error_handler(error_handler)

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))

    app.add_handler(CallbackQueryHandler(on_callback))

    app.add_handler(PreCheckoutQueryHandler(pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    logger.info("MusicAi RUNNING (polling)")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()