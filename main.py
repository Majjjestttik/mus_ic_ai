import os
import re
import json
import time
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Tuple, Any, List

import httpx
import stripe
import psycopg
from psycopg.rows import dict_row

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    LabeledPrice,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    PreCheckoutQueryHandler,
    ContextTypes,
    filters,
)

# -----------------------
# CONFIG
# -----------------------
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("musicai")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# OpenRouter (lyrics)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini").strip()
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").strip()

# PIAPI (Suno Music)
PIAPI_API_KEY = os.getenv("PIAPI_API_KEY", "").strip()
PIAPI_BASE_URL = os.getenv("PIAPI_BASE_URL", "").strip()
PIAPI_SUNO_ENDPOINT = os.getenv("PIAPI_SUNO_ENDPOINT", "/api/v1/suno/music").strip()
PIAPI_POLL_INTERVAL_SEC = float(os.getenv("PIAPI_POLL_INTERVAL_SEC", "2.0"))
PIAPI_POLL_TIMEOUT_SEC = float(os.getenv("PIAPI_POLL_TIMEOUT_SEC", "120.0"))

# PostgreSQL
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

# Stripe Checkout (link payments)
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "").strip()
STRIPE_PRICE_CURRENCY = "eur"
SUCCESS_URL = os.getenv("STRIPE_SUCCESS_URL", "https://t.me/").strip()
CANCEL_URL = os.getenv("STRIPE_CANCEL_URL", "https://t.me/").strip()

stripe.api_key = STRIPE_SECRET_KEY

# Packs
STARS_PACKS = {
    "pack_1": {"songs": 1, "amount": 300},
    "pack_5": {"songs": 5, "amount": 1000},
    "pack_30": {"songs": 30, "amount": 2500},
}
CARD_PACKS_EUR = {
    "pack_1": {"songs": 1, "amount_cents": 600},
    "pack_5": {"songs": 5, "amount_cents": 2000},
    "pack_30": {"songs": 30, "amount_cents": 5000},
}

# -----------------------
# UX DATA
# -----------------------
LANGS = [
    ("ru", "🇷🇺 Русский"),
    ("uk", "🇺🇦 Українська"),
    ("pl", "🇵🇱 Polski"),
    ("de", "🇩🇪 Deutsch"),
    ("en", "🇬🇧 English"),
    ("es", "🇪🇸 Español"),
    ("fr", "🇫🇷 Français"),
]

SONG_TYPES = [
    ("birthday", {"ru":"🎂 День рождения","uk":"🎂 День народження","pl":"🎂 Urodziny","de":"🎂 Geburtstag","en":"🎂 Birthday","es":"🎂 Cumpleaños","fr":"🎂 Anniversaire"}),
    ("love",     {"ru":"❤️ Признание","uk":"❤️ Зізнання","pl":"❤️ Wyznanie","de":"❤️ Liebeserklärung","en":"❤️ Confession","es":"❤️ Declaración","fr":"❤️ Déclaration"}),
    ("holiday",  {"ru":"🎉 Праздник","uk":"🎉 Свято","pl":"🎉 Święto","de":"🎉 Feier","en":"🎉 Celebration","es":"🎉 Fiesta","fr":"🎉 Fête"}),
    ("wedding",  {"ru":"💍 Свадьба","uk":"💍 Весілля","pl":"💍 Ślub","de":"💍 Hochzeit","en":"💍 Wedding","es":"💍 Boda","fr":"💍 Mariage"}),
    ("support",  {"ru":"💪 Поддержка","uk":"💪 Підтримка","pl":"💪 Wsparcie","de":"💪 Unterstützung","en":"💪 Support","es":"💪 Apoyo","fr":"💪 Soutien"}),
    ("prank",    {"ru":"😈 Розыгрыш","uk":"😈 Розіграш","pl":"😈 Żart","de":"😈 Streich","en":"😈 Prank","es":"😈 Broma","fr":"😈 Farce"}),
    ("other",    {"ru":"✍️ Другое","uk":"✍️ Інше","pl":"✍️ Inne","de":"✍️ Anderes","en":"✍️ Other","es":"✍️ Otro","fr":"✍️ Autre"}),
]

GENRES = [
    ("pop",      {"ru":"🎵 Поп","uk":"🎵 Поп","pl":"🎵 Pop","de":"🎵 Pop","en":"🎵 Pop","es":"🎵 Pop","fr":"🎵 Pop"}),
    ("rap",      {"ru":"🎤 Рэп / хип-хоп","uk":"🎤 Реп / хіп-хоп","pl":"🎤 Rap / hip-hop","de":"🎤 Rap / Hip-Hop","en":"🎤 Rap / Hip-Hop","es":"🎤 Rap / hip-hop","fr":"🎤 Rap / hip-hop"}),
    ("disco",    {"ru":"💃 Диско 90-х","uk":"💃 Диско 90-х","pl":"💃 Disco lat 90.","de":"💃 90er Disco","en":"💃 90s Disco","es":"💃 Disco 90s","fr":"💃 Disco années 90"}),
    ("rock",     {"ru":"🎸 Рок","uk":"🎸 Рок","pl":"🎸 Rock","de":"🎸 Rock","en":"🎸 Rock","es":"🎸 Rock","fr":"🎸 Rock"}),
    ("classic",  {"ru":"🎻 Классика","uk":"🎻 Класика","pl":"🎻 Klasyka","de":"🎻 Klassik","en":"🎻 Classical","es":"🎻 Clásica","fr":"🎻 Classique"}),
    ("electro",  {"ru":"🎛 Электро","uk":"🎛 Електро","pl":"🎛 Electro","de":"🎛 Elektro","en":"🎛 Electro","es":"🎛 Electro","fr":"🎛 Électro"}),
    ("acoustic", {"ru":"🎻 Акустика","uk":"🎻 Акустика","pl":"🎻 Akustycznie","de":"🎻 Akustik","en":"🎻 Acoustic","es":"🎻 Acústico","fr":"🎻 Acoustique"}),
    ("custom",   {"ru":"✍️ Свой вариант","uk":"✍️ Свій варіант","pl":"✍️ Własny","de":"✍️ Eigener","en":"✍️ Custom","es":"✍️ Propio","fr":"✍️ Personnalisé"}),
]

HELP_EN = """Help

Sometimes, when using MusicAi, the same questions come up. We’ve collected the most common ones with answers below 👇

────────────────

Edits and issues

✏️ Can I edit a finished song?
No. You can only generate a new one (−1 song from your balance).

🎶 How many versions do I get per generation?
Each generation gives you two different song versions at once. This is included in the price (−1 song from your balance).

🔉 Why are there pronunciation/stress mistakes?
This is a limitation of the neural network. To reduce the risk, mark stressed syllables with a capital letter, for example: dIma, svEta, natAsha. But keep in mind the model may not follow it 100%.

🎤 Why did the voice/style change?
AI may interpret it differently. Avoid using artist names — describe the genre, mood, and tempo instead.

❌ Can I fix only the stress/pronunciation?
No. Any change requires a new generation.

────────────────

Balance and payments

💸 Why were songs deducted but I didn’t get a result?
This can happen due to a glitch, a double tap, or auto-generation when message limits are reached. In such cases, your balance is restored.

🏦 Payment went through, but I didn’t receive songs.
If the payment didn’t reach us, your bank will automatically refund it. You can also send a screenshot to support.

↩️ Can I get a refund?
Yes, if an error is confirmed.

🎁 Why isn’t the first song free?
Each generation costs resources. But in the 30-song pack, one song costs only €1.66.

────────────────

Bot operation

🤖 Why was a song generated without my confirmation?
When message limits are reached, the bot may start generation automatically (it warns you about this).

🔁 Why is the chorus repeated multiple times?
Because it was written that way in the text. Please check before starting generation.

────────────────

Technical questions

🎶 Can I hear the music without vocals before paying?
No. The song is generated as a complete track.

────────────────

Copyright

📄 Who owns the rights to the songs?
You do — as the customer.

🌍 Can I publish the song online (YouTube, Instagram, etc.)?
Yes, you can publish it under your own name or a pseudonym.

────────────────

💬 For any questions and support, contact us on Telegram:
@Music_botsong
"""

TXT = {
    "choose_lang": {
        "ru":"Привет! Я MusicAi 🎶\n\nВыбери язык 👇 (можно поменять позже)",
        "uk":"Привіт! Я MusicAi 🎶\n\nОбери мову 👇 (можна змінити пізніше)",
        "pl":"Cześć! Jestem MusicAi 🎶\n\nWybierz język 👇 (możesz zmienić później)",
        "de":"Hallo! Ich bin MusicAi 🎶\n\nWähle eine Sprache 👇 (später änderbar)",
        "en":"Hi! I’m MusicAi 🎶\n\nChoose your language 👇 (you can change it later)",
        "es":"¡Hola! Soy MusicAi 🎶\n\nElige tu idioma 👇 (puedes cambiarlo después)",
        "fr":"Salut ! Je suis MusicAi 🎶\n\nChoisis ta langue 👇 (modifiable plus tard)",
    },
    "menu_title": {
        "ru":"Меню MusicAi ✅",
        "uk":"Меню MusicAi ✅",
        "pl":"Menu MusicAi ✅",
        "de":"MusicAi Menü ✅",
        "en":"MusicAi Menu ✅",
        "es":"Menú MusicAi ✅",
        "fr":"Menu MusicAi ✅",
    },
    "balance": {"ru":"Баланс","uk":"Баланс","pl":"Saldo","de":"Guthaben","en":"Balance","es":"Saldo","fr":"Solde"},
    "songs": {"ru":"песен","uk":"пісень","pl":"piosenek","de":"Songs","en":"songs","es":"canciones","fr":"chansons"},
    "btn_create": {"ru":"🎵 Создать песню","uk":"🎵 Створити пісню","pl":"🎵 Stwórz piosenkę","de":"🎵 Song erstellen","en":"🎵 Create a song","es":"🎵 Crear canción","fr":"🎵 Créer une chanson"},
    "btn_buy": {"ru":"🛒 Купить песни","uk":"🛒 Купити пісні","pl":"🛒 Kup piosenki","de":"🛒 Songs kaufen","en":"🛒 Buy songs","es":"🛒 Comprar canciones","fr":"🛒 Acheter des chansons"},
    "btn_mysongs": {"ru":"📂 Мои песни","uk":"📂 Мої пісні","pl":"📂 Moje piosenki","de":"📂 Meine Songs","en":"📂 My songs","es":"📂 Mis canciones","fr":"📂 Mes chansons"},
    "btn_lang": {"ru":"🌍 Язык","uk":"🌍 Мова","pl":"🌍 Język","de":"🌍 Sprache","en":"🌍 Language","es":"🌍 Idioma","fr":"🌍 Langue"},
    "btn_help": {"ru":"🆘 Help","uk":"🆘 Help","pl":"🆘 Help","de":"🆘 Help","en":"🆘 Help","es":"🆘 Help","fr":"🆘 Help"},
    "choose_type": {"ru":"Выбери тип песни 👇","uk":"Обери тип пісні 👇","pl":"Wybierz typ piosenki 👇","de":"Wähle den Song-Typ 👇","en":"Choose a song type 👇","es":"Elige el tipo de canción 👇","fr":"Choisis le type de chanson 👇"},
    "choose_genre": {"ru":"Выбери жанр 👇","uk":"Обери жанр 👇","pl":"Wybierz gatunek 👇","de":"Wähle ein Genre 👇","en":"Choose a genre 👇","es":"Elige un género 👇","fr":"Choisis un genre 👇"},
    "custom_genre": {"ru":"Напиши свой жанр одним сообщением (например: Dubstep / Drum & Bass / Reggaeton).",
                     "uk":"Напиши свій жанр одним повідомленням (наприклад: Dubstep / Drum & Bass / Reggaeton).",
                     "pl":"Napisz swój gatunek w jednej wiadomości (np. Dubstep / Drum & Bass / Reggaeton).",
                     "de":"Schreibe dein Genre in einer Nachricht (z.B. Dubstep / Drum & Bass / Reggaeton).",
                     "en":"Send your custom genre in one message (e.g., Dubstep / Drum & Bass / Reggaeton).",
                     "es":"Escribe tu género en un solo mensaje (ej.: Dubstep / Drum & Bass / Reggaeton).",
                     "fr":"Écris ton genre en un seul message (ex. Dubstep / Drum & Bass / Reggaeton)."},
    "desc_hint": {"ru":"Напиши всё, что может вдохновить:\n– Как зовут героя?\n– Чем он/она запомнился?\n– Смешные истории, фразы\n– Что передать: любовь, угар, благодарность\n\nЛучше текстом — точнее.",
                 "uk":"Напиши все деталі:\n– Ім'я героя?\n– Чим запам’ятався?\n– Кумедні історії/фрази\n– Що передати: любов, гумор, вдячність\n\nКраще текстом — точніше.",
                 "pl":"Napisz szczegóły:\n– Imię bohatera?\n– Co jest wyjątkowe?\n– Śmieszne historie/cytaty\n– Co przekazać: miłość, żart, wdzięczność\n\nLepiej tekstem — dokładniej.",
                 "de":"Schreibe Details:\n– Name der Person?\n– Wofür bekannt?\n– Lustige Stories/Zitate\n– Was vermitteln: Liebe, Spaß, Dankbarkeit\n\nAm besten als Text — genauer.",
                 "en":"Write details:\n– Name of the person?\n– What makes them special?\n– Funny stories/quotes\n– What to convey: love, humor, gratitude\n\nText works best — more accurate.",
                 "es":"Escribe detalles:\n– Nombre de la persona?\n– Qué la hace especial?\n– Historias/frases divertidas\n– Qué transmitir: amor, humor, gratitud\n\nMejor en texto — más preciso.",
                 "fr":"Écris des détails:\n– Nom de la personne?\n– Ce qui la rend spéciale?\n– Histoires/citations drôles\n– À transmettre: amour, humour, gratitude\n\nLe texte est plus précis."},
    "pay_method": {"ru":"Выбери способ оплаты 👇","uk":"Обери спосіб оплати 👇","pl":"Wybierz metodę płatności 👇","de":"Zahlungsmethode wählen 👇","en":"Choose a payment method 👇","es":"Elige método de pago 👇","fr":"Choisis un mode de paiement 👇"},
    "pay_stars": {"ru":"⭐ Telegram Stars","uk":"⭐ Telegram Stars","pl":"⭐ Telegram Stars","de":"⭐ Telegram Stars","en":"⭐ Telegram Stars","es":"⭐ Telegram Stars","fr":"⭐ Telegram Stars"},
    "pay_card": {"ru":"💳 Оплата картой","uk":"💳 Оплата карткою","pl":"💳 Płatność kartą","de":"💳 Kartenzahlung","en":"💳 Pay by card","es":"💳 Pagar con tarjeta","fr":"💳 Payer par carte"},
    "generating_lyrics": {"ru":"Генерирую текст… ✍️","uk":"Генерую текст… ✍️","pl":"Tworzę tekst… ✍️","de":"Erzeuge Text… ✍️","en":"Generating lyrics… ✍️","es":"Generando letra… ✍️","fr":"Génération des paroles… ✍️"},
    "generating_music": {"ru":"Генерирую музыку… 🎶","uk":"Генерую музику… 🎶","pl":"Tworzę muzykę… 🎶","de":"Erzeuge Musik… 🎶","en":"Generating music… 🎶","es":"Generando música… 🎶","fr":"Génération de la musique… 🎶"},
    "done": {"ru":"🎧 Готово!","uk":"🎧 Готово!","pl":"🎧 Gotowe!","de":"🎧 Fertig!","en":"🎧 Done!","es":"🎧 Listo!","fr":"🎧 Terminé!"},
    "not_enough": {"ru":"Недостаточно песен на балансе. Нажми 🛒 Купить песни.",
                   "uk":"Недостатньо пісень на балансі. Натисни 🛒 Купити пісні.",
                   "pl":"Brak piosenek na saldzie. Kliknij 🛒 Kup piosenki.",
                   "de":"Nicht genug Guthaben. Klicke 🛒 Songs kaufen.",
                   "en":"Not enough balance. Tap 🛒 Buy songs.",
                   "es":"Saldo insuficiente. Pulsa 🛒 Comprar canciones.",
                   "fr":"Solde insuffisant. Appuie sur 🛒 Acheter des chansons."},
    "err": {"ru":"❌ Ошибка генерации. Баланс восстановлен (если списался).",
            "uk":"❌ Помилка генерації. Баланс відновлено (якщо списалось).",
            "pl":"❌ Błąd generowania. Saldo przywrócone (jeśli pobrano).",
            "de":"❌ Generierungsfehler. Guthaben wiederhergestellt (falls abgebucht).",
            "en":"❌ Generation failed. Balance restored (if it was deducted).",
            "es":"❌ Error de generación. Saldo restaurado (si se descontó).",
            "fr":"❌ Erreur de génération. Solde restauré (si déduit)."},
}

def t(lang: str, key: str) -> str:
    return TXT.get(key, {}).get(lang) or TXT.get(key, {}).get("en") or key

def lang_name(code: str) -> str:
    return dict(LANGS).get(code, "🇬🇧 English")

def menu_kb(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [t(lang,"btn_create"), t(lang,"btn_buy")],
            [t(lang,"btn_mysongs"), t(lang,"btn_lang")],
            [t(lang,"btn_help")],
        ],
        resize_keyboard=True
    )

# -----------------------
# DB (Postgres)
# -----------------------
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
        conn.execute("""
        CREATE TABLE IF NOT EXISTS songs (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            lang TEXT,
            song_type TEXT,
            genre TEXT,
            description TEXT,
            lyrics TEXT,
            audio_url TEXT,
            is_demo INT NOT NULL DEFAULT 0
        );
        """)
        conn.commit()

def ensure_user(user_id: int):
    with db_conn() as conn:
        conn.execute("INSERT INTO users(user_id) VALUES(%s) ON CONFLICT DO NOTHING", (user_id,))
        conn.commit()

def get_user(user_id: int) -> Dict[str, Any]:
    ensure_user(user_id)
    with db_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id=%s", (user_id,)).fetchone()
        return row

def set_user_lang(user_id: int, lang: str):
    with db_conn() as conn:
        conn.execute("UPDATE users SET lang=%s WHERE user_id=%s", (lang, user_id))
        conn.commit()

def add_balance(user_id: int, delta: int):
    with db_conn() as conn:
        conn.execute("UPDATE users SET balance = balance + %s WHERE user_id=%s", (delta, user_id))
        conn.commit()

def consume_song(user_id: int) -> bool:
    with db_conn() as conn:
        row = conn.execute("SELECT balance FROM users WHERE user_id=%s", (user_id,)).fetchone()
        if not row or row["balance"] <= 0:
            return False
        conn.execute("UPDATE users SET balance = balance - 1 WHERE user_id=%s", (user_id,))
        conn.commit()
        return True

def mark_demo_used(user_id: int):
    with db_conn() as conn:
        conn.execute("UPDATE users SET demo_used=1 WHERE user_id=%s", (user_id,))
        conn.commit()

def save_song(user_id: int, lang: str, song_type: str, genre: str, desc: str, lyrics: str, audio_url: str, is_demo: int):
    with db_conn() as conn:
        conn.execute(
            "INSERT INTO songs(user_id, lang, song_type, genre, description, lyrics, audio_url, is_demo) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
            (user_id, lang, song_type, genre, desc, lyrics, audio_url, is_demo),
        )
        conn.commit()

def list_songs(user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    with db_conn() as conn:
        return conn.execute(
            "SELECT id, created_at, song_type, genre, is_demo FROM songs WHERE user_id=%s ORDER BY id DESC LIMIT %s",
            (user_id, limit),
        ).fetchall()

# -----------------------
# State (FSM)
# -----------------------
@dataclass
class Draft:
    song_type: Optional[str] = None
    genre_key: Optional[str] = None
    genre_label: Optional[str] = None
    description: Optional[str] = None

def reset_draft(context: ContextTypes.DEFAULT_TYPE):
    context.user_data["state"] = None
    context.user_data["draft"] = Draft()

def draft(context: ContextTypes.DEFAULT_TYPE) -> Draft:
    d = context.user_data.get("draft")
    if not isinstance(d, Draft):
        d = Draft()
        context.user_data["draft"] = d
    return d

# -----------------------
# Keyboards
# -----------------------
def kb_lang() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(name, callback_data=f"lang:{code}")]
                                 for code, name in LANGS])

def kb_types(lang: str) -> InlineKeyboardMarkup:
    rows = []
    for key, labels in SONG_TYPES:
        rows.append([InlineKeyboardButton(labels.get(lang, labels["en"]), callback_data=f"type:{key}")])
    return InlineKeyboardMarkup(rows)

def kb_genres(lang: str) -> InlineKeyboardMarkup:
    rows = []
    for key, labels in GENRES:
        rows.append([InlineKeyboardButton(labels.get(lang, labels["en"]), callback_data=f"genre:{key}")])
    return InlineKeyboardMarkup(rows)

def kb_buy_methods(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang,"pay_card"), callback_data="buy:card")],
        [InlineKeyboardButton(t(lang,"pay_stars"), callback_data="buy:stars")],
    ])

def kb_buy_packs_card() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("€ 6 — 1 song", callback_data="buy:card:pack_1")],
        [InlineKeyboardButton("€ 20 — 5 songs", callback_data="buy:card:pack_5")],
        [InlineKeyboardButton("€ 50 — 30 songs", callback_data="buy:card:pack_30")],
    ])

def kb_buy_packs_stars(lang: str) -> InlineKeyboardMarkup:
    # labels are ok in any language, stars are universal
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ 300 — 1 song", callback_data="buy:stars:pack_1")],
        [InlineKeyboardButton("⭐ 1000 — 5 songs", callback_data="buy:stars:pack_5")],
        [InlineKeyboardButton("⭐ 2500 — 30 songs", callback_data="buy:stars:pack_30")],
    ])

# -----------------------
# OpenRouter lyrics
# -----------------------
async def openrouter_lyrics(target_lang: str, song_type: str, genre: str, description: str) -> str:
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY not set")

    lang_name_map = {
        "ru": "русском",
        "uk": "украинском",
        "pl": "польском",
        "de": "немецком",
        "en": "английском",
        "es": "испанском",
        "fr": "французском",
    }
    lang_name_ru = lang_name_map.get(target_lang, "английском")

    system = (
        "Ты профессиональный поэт-песенник. Пишешь строго на указанном языке. "
        "Структура: [Verse 1], [Chorus], [Verse 2], [Chorus], [Bridge], [Chorus]. "
        "Без пояснений — только текст песни."
    )
    user = (
        f"Язык текста: {lang_name_ru}.\n"
        f"Тип песни: {song_type}.\n"
        f"Жанр: {genre}.\n"
        f"Описание:\n{description}\n\n"
        "Сгенерируй текст песни."
    )

    payload = {"model": OPENROUTER_MODEL, "messages": [{"role":"system","content":system},{"role":"user","content":user}], "temperature": 0.9}
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://t.me/",
        "X-Title": "MusicAi Telegram Bot",
    }

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(f"{OPENROUTER_BASE_URL}/chat/completions", headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"].strip()

def detect_lang_override(text: str) -> Optional[str]:
    t_ = text.lower()
    if re.search(r"\b(рус|russian|по[-\s]?рус)\b", t_): return "ru"
    if re.search(r"\b(укр|україн|ukrainian)\b", t_): return "uk"
    if re.search(r"\b(поль|polski|polish)\b", t_): return "pl"
    if re.search(r"\b(нем|deutsch|german)\b", t_): return "de"
    if re.search(r"\b(англ|english)\b", t_): return "en"
    if re.search(r"\b(испан|español|spanish)\b", t_): return "es"
    if re.search(r"\b(франц|français|french)\b", t_): return "fr"
    return None

# -----------------------
# PIAPI music (adapter)
# -----------------------
async def piapi_music(lyrics: str, style: str, is_demo: bool) -> str:
    if not PIAPI_API_KEY or not PIAPI_BASE_URL:
        raise RuntimeError("PIAPI_API_KEY/PIAPI_BASE_URL not set")

    duration = 60 if is_demo else 120
    create_payload = {
        "lyrics": lyrics,
        "style": style,
        "duration": duration,
        "instrumental": False,
        "num_variations": 2,
    }
    headers = {"X-API-Key": PIAPI_API_KEY, "Content-Type": "application/json"}
    create_url = f"{PIAPI_BASE_URL}{PIAPI_SUNO_ENDPOINT}"

    async with httpx.AsyncClient(timeout=60) as client:
        cr = await client.post(create_url, headers=headers, json=create_payload)
        cr.raise_for_status()
        created = cr.json()

        task_id = created.get("task_id") or created.get("id") or (created.get("data") or {}).get("task_id")
        if not task_id:
            audio_url = created.get("audio_url") or (created.get("data") or {}).get("audio_url")
            if audio_url:
                return audio_url
            raise RuntimeError(f"PIAPI: no task_id. Response: {created}")

        poll_url = f"{PIAPI_BASE_URL}/api/v1/tasks/{task_id}"
        start = time.time()
        last = None
        while time.time() - start < PIAPI_POLL_TIMEOUT_SEC:
            await _sleep(PIAPI_POLL_INTERVAL_SEC)
            pr = await client.get(poll_url, headers=headers)
            pr.raise_for_status()
            last = pr.json()
            status = (last.get("status") or last.get("state") or "").lower()

            if status in ("succeeded","success","completed","done","finished"):
                audio_url = last.get("audio_url") or (last.get("result") or {}).get("audio_url") or (last.get("data") or {}).get("audio_url")
                if not audio_url:
                    variants = (last.get("result") or {}).get("audios") or (last.get("data") or {}).get("audios")
                    if isinstance(variants, list) and variants:
                        audio_url = variants[0].get("url") or variants[0].get("audio_url")
                if not audio_url:
                    raise RuntimeError(f"PIAPI: completed but no audio_url: {last}")
                return audio_url

            if status in ("failed","error","canceled","cancelled"):
                raise RuntimeError(f"PIAPI: failed: {last}")

        raise RuntimeError(f"PIAPI timeout. Last: {last}")

async def _sleep(sec: float):
    import asyncio
    await asyncio.sleep(sec)

# -----------------------
# Stripe Checkout Session
# -----------------------
def stripe_checkout_url(user_id: int, pack: str) -> str:
    if not STRIPE_SECRET_KEY:
        raise RuntimeError("STRIPE_SECRET_KEY not set")

    info = CARD_PACKS_EUR[pack]
    session = stripe.checkout.Session.create(
        mode="payment",
        success_url=SUCCESS_URL,
        cancel_url=CANCEL_URL,
        line_items=[{
            "price_data": {
                "currency": STRIPE_PRICE_CURRENCY,
                "product_data": {"name": f"MusicAi — {info['songs']} songs"},
                "unit_amount": info["amount_cents"],
            },
            "quantity": 1,
        }],
        metadata={"user_id": str(user_id), "pack": pack},
    )
    return session.url

# -----------------------
# Handlers
# -----------------------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update.effective_user.id)
    reset_draft(context)
    # Default language could be EN until user chooses
    await update.message.reply_text(TXT["choose_lang"]["en"], reply_markup=kb_lang())

async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    ensure_user(uid)
    reset_draft(context)
    u = get_user(uid)
    lang = u["lang"]
    await update.message.reply_text(
        f"{t(lang,'menu_title')}\n\n{t(lang,'balance')}: {u['balance']} {t(lang,'songs')}\n{lang_name(lang)}",
        reply_markup=menu_kb(lang)
    )

async def cb_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    ensure_user(uid)
    u = get_user(uid)
    lang = u["lang"]

    data = q.data or ""

    if data.startswith("lang:"):
        code = data.split(":", 1)[1]
        set_user_lang(uid, code)
        u2 = get_user(uid)
        lang2 = u2["lang"]
        reset_draft(context)
        await q.message.reply_text(
            f"✅ {lang_name(lang2)}",
            reply_markup=menu_kb(lang2)
        )
        return

    if data.startswith("type:"):
        d = draft(context)
        d.song_type = data.split(":", 1)[1]
        context.user_data["state"] = "choose_genre"
        await q.message.reply_text(t(lang,"choose_genre"), reply_markup=kb_genres(lang))
        return

    if data.startswith("genre:"):
        gkey = data.split(":", 1)[1]
        d = draft(context)
        d.genre_key = gkey
        if gkey == "custom":
            context.user_data["state"] = "await_custom_genre"
            await q.message.reply_text(t(lang,"custom_genre"))
        else:
            # resolve label
            label = next((labels.get(lang, labels["en"]) for key, labels in GENRES if key == gkey), gkey)
            d.genre_label = label
            context.user_data["state"] = "await_description"
            await q.message.reply_text(t(lang,"desc_hint"))
        return

    if data == "buy:card":
        await q.message.reply_text(t(lang,"pay_method"), reply_markup=kb_buy_packs_card())
        return

    if data == "buy:stars":
        await q.message.reply_text(t(lang,"pay_method"), reply_markup=kb_buy_packs_stars(lang))
        return

    m = re.match(r"buy:card:(pack_\d+)", data)
    if m:
        pack = m.group(1)
        try:
            url = stripe_checkout_url(uid, pack)
            await q.message.reply_text(f"💳 Pay by card:\n{url}")
        except Exception as e:
            log.exception("Stripe session failed")
            await q.message.reply_text("❌ Stripe error. Try later.")
        return

    m = re.match(r"buy:stars:(pack_\d+)", data)
    if m:
        pack = m.group(1)
        info = STARS_PACKS[pack]
        prices = [LabeledPrice(label=f"{info['songs']} songs", amount=info["amount"])]
        payload = json.dumps({"method":"stars","pack":pack})
        await context.bot.send_invoice(
            chat_id=uid,
            title="MusicAi — Songs (Stars)",
            description=f"{info['songs']} songs",
            payload=payload,
            provider_token="",
            currency="XTR",
            prices=prices,
        )
        return

async def precheckout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    ensure_user(uid)
    sp = update.message.successful_payment
    try:
        p = json.loads(sp.invoice_payload)
        pack = p.get("pack")
    except Exception:
        pack = None
    if pack in STARS_PACKS:
        add_balance(uid, STARS_PACKS[pack]["songs"])
        u = get_user(uid)
        lang = u["lang"]
        await update.message.reply_text(
            f"✅ +{STARS_PACKS[pack]['songs']} {t(lang,'songs')}\n{t(lang,'balance')}: {u['balance']} {t(lang,'songs')}",
            reply_markup=menu_kb(lang)
        )

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    ensure_user(uid)
    u = get_user(uid)
    lang = u["lang"]
    text = (update.message.text or "").strip()

    # Menu buttons (translated)
    if text == t(lang,"btn_create"):
        reset_draft(context)
        context.user_data["state"] = "choose_type"
        await update.message.reply_text(t(lang,"choose_type"), reply_markup=kb_types(lang))
        return

    if text == t(lang,"btn_buy"):
        reset_draft(context)
        await update.message.reply_text(t(lang,"pay_method"), reply_markup=kb_buy_methods(lang))
        return

    if text == t(lang,"btn_mysongs"):
        reset_draft(context)
        rows = list_songs(uid, 10)
        if not rows:
            await update.message.reply_text("No songs yet.", reply_markup=menu_kb(lang))
            return
        lines = ["Last songs:"]
        for r in rows:
            lines.append(f"• {r['created_at']} — {r['song_type']} / {r['genre']}" + (" (DEMO)" if r["is_demo"] else ""))
        await update.message.reply_text("\n".join(lines), reply_markup=menu_kb(lang))
        return

    if text == t(lang,"btn_lang"):
        reset_draft(context)
        await update.message.reply_text(t(lang,"choose_lang"), reply_markup=kb_lang())
        return

    if text == t(lang,"btn_help"):
        reset_draft(context)
        await update.message.reply_text(HELP_EN, reply_markup=menu_kb(lang))
        return

    # Flow states
    st = context.user_data.get("state")
    d = draft(context)

    if st == "await_custom_genre":
        d.genre_label = text[:60]
        context.user_data["state"] = "await_description"
        await update.message.reply_text(t(lang,"desc_hint"))
        return

    if st == "await_description":
        d.description = text
        context.user_data["state"] = "generating"

        # resolve labels
        type_label = next((labels.get(lang, labels["en"]) for key, labels in SONG_TYPES if key == d.song_type), d.song_type or "Other")
        genre_label = d.genre_label or "Pop"

        # demo?
        is_demo = 1 if int(u["demo_used"]) == 0 else 0

        # consume if not demo
        if not is_demo:
            if not consume_song(uid):
                reset_draft(context)
                await update.message.reply_text(t(lang,"not_enough"), reply_markup=menu_kb(lang))
                return

        await update.message.reply_text(t(lang,"generating_lyrics"))
        try:
            lang_final = detect_lang_override(d.description) or lang
            lyrics = await openrouter_lyrics(lang_final, type_label, genre_label, d.description)

            await update.message.reply_text(t(lang,"generating_music"))
            audio_url = await piapi_music(lyrics, genre_label, bool(is_demo))

            if is_demo:
                mark_demo_used(uid)

            await update.message.reply_text(f"{t(lang,'done')}\n{audio_url}")
            await update.message.reply_text(lyrics[:3900] + ("\n\n…(cut)" if len(lyrics) > 3900 else ""))

            save_song(uid, lang_final, type_label, genre_label, d.description, lyrics, audio_url, is_demo)

            u2 = get_user(uid)
            await update.message.reply_text(
                f"{t(lang,'balance')}: {u2['balance']} {t(lang,'songs')}",
                reply_markup=menu_kb(lang)
            )

        except Exception:
            log.exception("Generation error")
            if not is_demo:
                add_balance(uid, 1)
            await update.message.reply_text(t(lang,"err"), reply_markup=menu_kb(lang))
        finally:
            reset_draft(context)
        return

    # fallback
    await cmd_menu(update, context)

async def on_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    ensure_user(uid)
    u = get_user(uid)
    lang = u["lang"]
    await update.message.reply_text(
        "🎤 Voice received. Please send key details as text (more accurate).",
        reply_markup=menu_kb(lang)
    )

def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))

    app.add_handler(CallbackQueryHandler(cb_router))

    app.add_handler(PreCheckoutQueryHandler(precheckout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))

    app.add_handler(MessageHandler(filters.VOICE, on_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    log.info("MusicAi bot started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
