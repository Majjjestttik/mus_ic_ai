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
from openai import AsyncOpenAI
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

# -------------------- ЛОГИ (Для Render) --------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("MusicAi")

# -------------------- ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ --------------------
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # For Whisper voice transcription
OWNER_ID = int(os.getenv("OWNER_TG_ID", "1225282893"))

if not BOT_TOKEN or not OPENROUTER_API_KEY:
    raise RuntimeError("КРИТИЧЕСКАЯ ОШИБКА: TELEGRAM_BOT_TOKEN и OPENROUTER_API_KEY должны быть установлены!")
if not OPENAI_API_KEY:
    logger.warning("OPENAI_API_KEY не установлен - голосовые сообщения не будут работать")

# -------------------- API CLIENTS --------------------
# Initialize OpenRouter client at module level (best practice)
openrouter_client = AsyncOpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url="https://openrouter.ai/api/v1"
)

# Initialize OpenAI client for Whisper (if key is available)
openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# -------------------- ЦЕНЫ И ПАКЕТЫ --------------------
PACKS = {"1": 250, "5": 1000, "25": 4000}

# -------------------- БАЗА ДАННЫХ --------------------
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
    if "state" in kwargs:
        cur.execute("UPDATE users SET state_json=?, updated_at=? WHERE user_id=?", (json.dumps(kwargs["state"], ensure_ascii=False), now, user_id))
    if "lang" in kwargs:
        cur.execute("UPDATE users SET lang=?, updated_at=? WHERE user_id=?", (kwargs["lang"], now, user_id))
    if "demo_used" in kwargs:
        cur.execute("UPDATE users SET demo_used=?, updated_at=? WHERE user_id=?", (kwargs["demo_used"], now, user_id))
    if "songs" in kwargs:
        cur.execute("UPDATE users SET songs=?, updated_at=? WHERE user_id=?", (kwargs["songs"], now, user_id))
    con.commit()
    con.close()

async def adb_get_user(uid): return await asyncio.to_thread(db_get_user, uid)
async def adb_set(uid, **kwargs): await asyncio.to_thread(db_set, uid, **kwargs)

# -------------------- ТЕКСТЫ (ВСЕ 7 ЯЗЫКОВ И ВСЕ КЛЮЧИ) --------------------
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
    "choose_theme": {"en": "Choose theme:", "ru": "Выбери тему:", "pl": "Wybierz temat:", "de": "Wähle ein Thema:", "es": "Elige tema:", "fr": "Choisissez un thème:", "uk": "Виберіть тему:"},
    "choose_genre": {"en": "Choose genre:", "ru": "Выбери жанр:", "pl": "Wybierz gatunek:", "de": "Wähle Genre:", "es": "Elige género:", "fr": "Choisissez un genre:", "uk": "Виберіть жанр:"},
    "describe": {
        "en": "✍️ *Describe the song*\n\n🎤 Or send a voice message.",
        "ru": "✍️ *Опиши песню*\n\n🎤 Или отправь голосовое.",
        "pl": "✍️ *Opisz piosenkę*\n\n🎤 Lub wyślij głosówkę.",
        "de": "✍️ *Beschreibe das Lied*\n\n🎤 Sprachnachricht senden.",
        "es": "✍️ *Describe la canción*\n\n🎤 O envía un mensaje de voz.",
        "fr": "✍️ *Décris la chanson*\n\n🎤 Ou envoie un vocal.",
        "uk": "✍️ *Опиши пісню*\n\n🎤 Або надішли голосове.",
    },
    "help": {
        "ru": """ℹ️ *Помощь*

Иногда при работе с MusicAi возникают повторяющиеся вопросы. Мы собрали самые частые из них с ответами 👇

────────────────

*Изменения и ошибки*

✏️ *Можно ли изменить готовую песню?*
Нет, только сгенерировать заново (−1 песня с баланса).

🎶 *Сколько вариантов даётся при генерации?*
При каждой генерации ты получаешь сразу два разных варианта песни. Это включено в цену (−1 песня с баланса).

🔉 *Почему ошибки в ударениях/дикции?*
Это особенность нейросети. Чтобы снизить риск, указывайте ударения прямо в тексте заглавной буквой, например: дИма, свЕта, натАша. Но помните — модель не всегда это учитывает на 100%.

🎤 *Почему поменялся голос/стиль?*
ИИ может интерпретировать по-своему. Не используйте имена артистов, а описывайте жанр, настроение, темп.

❌ *Можно исправить только ударение?*
Нет, любая правка = новая генерация.

────────────────

*Баланс и оплата*

💸 *Почему списались песни без результата?*
Возможен сбой, двойное нажатие или авто-генерация при лимите сообщений. В таких случаях мы восстанавливаем баланс + бонус.

🏦 *Оплата прошла, а песен нет?*
Если платёж не дошёл, банк вернёт его автоматически.

↩️ *Можно ли вернуть деньги?*
Да, при подтверждённой ошибке. В других случаях, нельзя, поэтому, перед нажатием кнопки Сгенерировать песню, хорошо прочитайте текст.

🎁 *Почему нет бесплатной первой песни?*
Каждая генерация стоит ресурсов.

────────────────

*Работа бота*

🤖 *Почему песня создалась без согласия?*
При лимите сообщений бот автоматически запускает генерацию (он предупреждает об этом).

🔁 *Почему припев повторяется несколько раз?*
Так было в тексте. Проверяйте перед запуском.

────────────────

*Технические вопросы*

🎶 *Можно ли услышать музыку без слов до оплаты?*
Нет, песня генерируется целиком.

────────────────

*Авторские права*

📄 *Кому принадлежат песни?*
Правообладатель — Вы как заказчик.

🌍 *Можно публиковать в соцсетях или платформах как YouTube и др.?*
Да, под своим именем или псевдонимом.""",
        "en": """ℹ️ *Help*

Here are the most frequently asked questions about MusicAi 👇

────────────────

*Changes and Errors*

✏️ *Can I edit a finished song?*
No, you can only generate a new one (−1 song from balance).

🎶 *How many variants per generation?*
Each generation gives you two different song variants. This is included in the price (−1 song from balance).

🔉 *Why are there stress/pronunciation errors?*
This is a neural network feature. To reduce risk, indicate stress with CAPS: dIma, natAsha. But remember — the model doesn't always follow this 100%.

🎤 *Why did the voice/style change?*
AI can interpret in its own way. Don't use artist names, describe genre, mood, tempo instead.

❌ *Can I fix just the stress?*
No, any edit = new generation.

────────────────

*Balance and Payment*

💸 *Why were songs deducted without result?*
Possible glitch, double click, or auto-generation at message limit. In such cases we restore balance + bonus.

🏦 *Payment went through but no songs?*
If payment didn't arrive, the bank will return it automatically.

↩️ *Can I get a refund?*
Yes, for confirmed errors. Otherwise no, so please read the text carefully before clicking Generate Song.

🎁 *Why is there no free first song?*
Each generation costs resources.

────────────────

*Bot Operations*

🤖 *Why was a song created without consent?*
At message limit, the bot automatically starts generation (it warns about this).

🔁 *Why does the chorus repeat multiple times?*
That's how it was in the text. Check before launching.

────────────────

*Technical Questions*

🎶 *Can I hear music without words before payment?*
No, the song is generated as a whole.

────────────────

*Copyright*

📄 *Who owns the songs?*
Rights holder — You as the customer.

🌍 *Can I publish on social media or platforms like YouTube?*
Yes, under your name or pseudonym.""",
        "pl": """ℹ️ *Pomoc*

Najczęściej zadawane pytania o MusicAi 👇

────────────────

*Zmiany i błędy*

✏️ *Czy mogę edytować gotową piosenkę?*
Nie, tylko wygenerować nową (−1 piosenka z salda).

🎶 *Ile wariantów przy generacji?*
Każda generacja daje dwa różne warianty. To jest w cenie (−1 piosenka z salda).

🔉 *Dlaczego błędy w akcentach/dykcji?*
To cecha sieci neuronowej. Aby zmniejszyć ryzyko, zaznacz akcent CAPS: dIma. Ale model nie zawsze to uwzględnia w 100%.

────────────────

*Saldo i płatności*

💸 *Dlaczego odliczono piosenki bez wyniku?*
Możliwy błąd, podwójne kliknięcie. W takich przypadkach przywracamy saldo + bonus.

📄 *Kto jest właścicielem piosenek?*
Ty jako klient.""",
        "de": """ℹ️ *Hilfe*

Die häufigsten Fragen zu MusicAi 👇

────────────────

*Änderungen und Fehler*

✏️ *Kann ich ein fertiges Lied bearbeiten?*
Nein, nur neu generieren (−1 Song vom Guthaben).

🎶 *Wie viele Varianten pro Generierung?*
Jede Generierung gibt zwei verschiedene Varianten. Dies ist im Preis enthalten (−1 Song).

🔉 *Warum Betonungs-/Aussprachefehler?*
Das ist eine Besonderheit des neuronalen Netzes. Um das Risiko zu verringern, markieren Sie die Betonung mit GROSSBUCHSTABEN: dIma.

────────────────

*Guthaben und Zahlung*

💸 *Warum wurden Songs ohne Ergebnis abgezogen?*
Möglicher Fehler, Doppelklick. In solchen Fällen stellen wir das Guthaben + Bonus wieder her.

📄 *Wem gehören die Songs?*
Rechteinhaber — Sie als Kunde.""",
        "es": """ℹ️ *Ayuda*

Las preguntas más frecuentes sobre MusicAi 👇

────────────────

*Cambios y errores*

✏️ *¿Puedo editar una canción terminada?*
No, solo generar una nueva (−1 canción del saldo).

🎶 *¿Cuántas variantes por generación?*
Cada generación da dos variantes diferentes. Esto está incluido en el precio (−1 canción).

🔉 *¿Por qué errores de acentuación/dicción?*
Es una característica de la red neuronal. Para reducir el riesgo, indique el acento con MAYÚSCULAS: dIma.

────────────────

*Saldo y pago*

💸 *¿Por qué se dedujeron canciones sin resultado?*
Posible error, doble clic. En tales casos restauramos el saldo + bonificación.

📄 *¿A quién pertenecen las canciones?*
Titular de derechos — Usted como cliente.""",
        "fr": """ℹ️ *Aide*

Les questions les plus fréquentes sur MusicAi 👇

────────────────

*Changements et erreurs*

✏️ *Puis-je modifier une chanson finie?*
Non, seulement en générer une nouvelle (−1 chanson du solde).

🎶 *Combien de variantes par génération?*
Chaque génération donne deux variantes différentes. C'est inclus dans le prix (−1 chanson).

🔉 *Pourquoi des erreurs d'accentuation/diction?*
C'est une caractéristique du réseau neuronal. Pour réduire le risque, indiquez l'accent en MAJUSCULES: dIma.

────────────────

*Solde et paiement*

💸 *Pourquoi des chansons déduites sans résultat?*
Erreur possible, double clic. Dans de tels cas, nous restaurons le solde + bonus.

📄 *À qui appartiennent les chansons?*
Titulaire des droits — Vous en tant que client.""",
        "uk": """ℹ️ *Допомога*

Найчастіші питання про MusicAi 👇

────────────────

*Зміни та помилки*

✏️ *Чи можна змінити готову пісню?*
Ні, тільки згенерувати знову (−1 пісня з балансу).

🎶 *Скільки варіантів при генерації?*
При кожній генерації ти отримуєш відразу два різних варіанти пісні. Це включено в ціну (−1 пісня з балансу).

🔉 *Чому помилки в наголосах/дикції?*
Це особливість нейромережі. Щоб знизити ризик, вказуйте наголоси прямо в тексті великою літерою, наприклад: дІма, свЕта, натАша.

────────────────

*Баланс та оплата*

💸 *Чому списалися пісні без результату?*
Можливий збій, подвійне натискання. У таких випадках ми відновлюємо баланс + бонус.

📄 *Кому належать пісні?*
Правовласник — Ви як замовник.""",
    },
    "balance": {
        "en": "💰 *Balance*\n\nYou have {songs} songs available.",
        "ru": "💰 *Баланс*\n\nУ вас доступно {songs} песен.",
        "pl": "💰 *Saldo*\n\nMasz {songs} piosenek.",
        "de": "💰 *Guthaben*\n\nSie haben {songs} Songs verfügbar.",
        "es": "💰 *Saldo*\n\nTienes {songs} canciones disponibles.",
        "fr": "💰 *Solde*\n\nVous avez {songs} chansons disponibles.",
        "uk": "💰 *Баланс*\n\nУ вас доступно {songs} пісень.",
    },
    "current_song": {
        "en": "🎵 *Current Song*\n\nNo active song generation.\n\nUse /start to create a new song.",
        "ru": "🎵 *Текущая песня*\n\nНет активной генерации.\n\nИспользуйте /start для создания новой песни.",
        "pl": "🎵 *Aktualna piosenka*\n\nBrak aktywnej generacji.\n\nUżyj /start aby utworzyć nową piosenkę.",
        "de": "🎵 *Aktuelles Lied*\n\nKeine aktive Generierung.\n\nVerwenden Sie /start um ein neues Lied zu erstellen.",
        "es": "🎵 *Canción actual*\n\nNo hay generación activa.\n\nUsa /start para crear una nueva canción.",
        "fr": "🎵 *Chanson actuelle*\n\nAucune génération active.\n\nUtilisez /start pour créer une nouvelle chanson.",
        "uk": "🎵 *Поточна пісня*\n\nНемає активної генерації.\n\nВикористовуйте /start для створення нової пісні.",
    },
    "buy_menu": {
        "en": "🛒 *Buy Songs*\n\nChoose a package:",
        "ru": "🛒 *Купить песни*\n\nВыбери пакет:",
        "pl": "🛒 *Kup piosenki*\n\nWybierz pakiet:",
        "de": "🛒 *Songs kaufen*\n\nWählen Sie ein Paket:",
        "es": "🛒 *Comprar canciones*\n\nElige un paquete:",
        "fr": "🛒 *Acheter des chansons*\n\nChoisissez un forfait:",
        "uk": "🛒 *Купити пісні*\n\nОбери пакет:",
    },
    "custom_theme_ask": {"en": "✏️ Write theme:", "ru": "✏️ Напиши тему:", "pl": "✏️ Napisz temat:", "uk": "✏️ Напиши тему:"},
    "generating": {"en": "⏳ Generating...", "ru": "⏳ Генерирую...", "pl": "⏳ Generuję...", "uk": "⏳ Генерую...", "de": "⏳ Generiere...", "es": "⏳ Generando...", "fr": "⏳ Génération..."},
    "demo_header": {"en": "🎧 *Demo*", "ru": "🎧 *Демо*", "pl": "🎧 *Demo*", "uk": "🎧 *Демо*", "de": "🎧 *Demo*", "es": "🎧 *Demo*", "fr": "🎧 *Démo*"},
    "no_credits": {"en": "0 songs. Buy 👇", "ru": "0 песен. Купи пакет 👇", "pl": "0 piosenek 👇", "uk": "0 пісень 👇", "de": "0 Lieder 👇", "es": "0 canciones 👇", "fr": "0 chansons 👇"},
    "paid": {"en": "✅ Paid!", "ru": "✅ Оплачено!", "pl": "✅ Opłacono!", "uk": "✅ Оплачено!", "de": "✅ Bezahlt!", "es": "✅ ¡Pagado!", "fr": "✅ Payé!"},
    "temp_error": {"en": "⚠️ Error generating song. Check API key and try again.", "ru": "⚠️ Ошибка генерации. Проверьте API ключ и попробуйте снова.", "pl": "⚠️ Błąd generowania. Sprawdź klucz API.", "uk": "⚠️ Помилка генерації. Перевірте API ключ.", "de": "⚠️ Fehler. Prüfen Sie den API-Schlüssel.", "es": "⚠️ Error. Verifique la clave API.", "fr": "⚠️ Erreur. Vérifiez la clé API."},
    "buy_confirm": {"en": "Spend ⭐ {stars}?", "ru": "Потратить ⭐ {stars}?", "pl": "Wydać ⭐ {stars}?", "uk": "Витратити ⭐ {stars}?", "de": "⭐ {stars} ausgeben?", "es": "¿Gastar ⭐ {stars}?", "fr": "Dépenser ⭐ {stars}?"},
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
async def openai_generate_song(prompt):
    """Generate a song using OpenRouter API with multiple model fallback"""
    # Try multiple models available on OpenRouter
    models_to_try = [
        "openai/gpt-4",
        "openai/gpt-3.5-turbo",
        "anthropic/claude-2",
        "meta-llama/llama-2-70b-chat"
    ]
    
    for model in models_to_try:
        try:
            logger.info(f"Attempting to generate song with OpenRouter model: {model}")
            response = await openrouter_client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a creative songwriting assistant. Create complete song lyrics with verses, chorus, and structure based on the user's description. Be creative and match the requested genre, theme, and language."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1500,
                temperature=0.8,
                extra_headers={
                    "HTTP-Referer": "https://github.com/Majjjestttik/mus_ic_ai",
                    "X-Title": "MusicAi Telegram Bot"
                }
            )
            
            logger.info(f"Successfully generated song with OpenRouter {model}")
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"OpenRouter API error with {model}: {type(e).__name__}: {e}")
            if model == models_to_try[-1]:
                # Last model failed, return None
                return None
            # Try next model
            continue
    
    return None

async def voice_to_text(file_path):
    """Transcribe voice message using OpenAI Whisper"""
    if not openai_client:
        return None
    try:
        with open(file_path, "rb") as f:
            res = await openai_client.audio.transcriptions.create(model="whisper-1", file=f)
        return res.text
    except Exception as e:
        logger.error(f"Whisper transcription error: {type(e).__name__}: {e}")
        return None

# -------------------- КЛАВИАТУРЫ --------------------
def kb_languages():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("English 🇬🇧", callback_data="lang_en"), InlineKeyboardButton("Русский 🇷🇺", callback_data="lang_ru")],
        [InlineKeyboardButton("Polski 🇵🇱", callback_data="lang_pl"), InlineKeyboardButton("Deutsch 🇩🇪", callback_data="lang_de")],
        [InlineKeyboardButton("Español 🇪🇸", callback_data="lang_es"), InlineKeyboardButton("Français 🇫🇷", callback_data="lang_fr")],
        [InlineKeyboardButton("Українська 🇺🇦", callback_data="lang_uk")]
    ])

def kb_themes(lang):
    kb = [
        [InlineKeyboardButton(THEMES["love"][lang], callback_data="theme_love"), InlineKeyboardButton(THEMES["fun"][lang], callback_data="theme_fun")],
        [InlineKeyboardButton(THEMES["holiday"][lang], callback_data="theme_holiday"), InlineKeyboardButton(THEMES["sad"][lang], callback_data="theme_sad")],
        [InlineKeyboardButton(THEMES["wedding"][lang], callback_data="theme_wedding"), InlineKeyboardButton(THEMES["custom"][lang], callback_data="theme_custom")]
    ]
    return InlineKeyboardMarkup(kb)

def kb_genres():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Pop", callback_data="genre_pop"), InlineKeyboardButton("Rap", callback_data="genre_rap")],
        [InlineKeyboardButton("Rock", callback_data="genre_rock"), InlineKeyboardButton("Club", callback_data="genre_club")],
        [InlineKeyboardButton("Classical", callback_data="genre_classical"), InlineKeyboardButton("Disco Polo", callback_data="genre_disco")]
    ])

# -------------------- ХЕНДЛЕРЫ --------------------
async def post_init(app):
    # Set bot menu commands (persistent left menu)
    await app.bot.set_my_commands([
        BotCommand("start", "🏠 Start"),
        BotCommand("current", "🎵 Current Song"),
        BotCommand("balance", "💰 Balance"),
        BotCommand("buy", "🛒 Buy Songs"),
        BotCommand("help", "ℹ️ Help")
    ])

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = await adb_get_user(uid)
    await adb_set(uid, state={})
    await update.message.reply_text(tr(u["lang"], "start"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ START", callback_data="start")]]), parse_mode="Markdown")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = await adb_get_user(update.effective_user.id)
    await update.message.reply_text(tr(u["lang"], "help"), parse_mode="Markdown")

async def balance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = await adb_get_user(update.effective_user.id)
    await update.message.reply_text(tr(u["lang"], "balance").format(songs=u["songs"]), parse_mode="Markdown")

async def current_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = await adb_get_user(update.effective_user.id)
    # Could check state here if we're tracking current generation
    await update.message.reply_text(tr(u["lang"], "current_song"), parse_mode="Markdown")

async def buy_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = await adb_get_user(update.effective_user.id)
    lang = u["lang"]
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"1 song - ⭐ {PACKS['1']}", callback_data="pay_1")],
        [InlineKeyboardButton(f"5 songs - ⭐ {PACKS['5']} (20% off)", callback_data="pay_5")],
        [InlineKeyboardButton(f"25 songs - ⭐ {PACKS['25']} (36% off)", callback_data="pay_25")]
    ])
    await update.message.reply_text(tr(lang, "buy_menu"), reply_markup=kb, parse_mode="Markdown")

async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    u = await adb_get_user(uid)
    lang, state = u["lang"], u["state"]

    if q.data == "start":
        await q.edit_message_text(tr(lang, "choose_language"), reply_markup=kb_languages())
    elif q.data.startswith("lang_"):
        new_lang = q.data[5:]; await adb_set(uid, lang=new_lang)
        await q.edit_message_text(tr(new_lang, "choose_theme"), reply_markup=kb_themes(new_lang))
    elif q.data.startswith("theme_"):
        theme = q.data[6:]; state["theme"] = theme
        if theme == "custom":
            state["awaiting_custom"] = True; await adb_set(uid, state=state)
            await q.edit_message_text(tr(lang, "custom_theme_ask"))
        else:
            await adb_set(uid, state=state)
            await q.edit_message_text(tr(lang, "choose_genre"), reply_markup=kb_genres())
    elif q.data.startswith("genre_"):
        state["genre"] = q.data[6:]; await adb_set(uid, state=state)
        await q.edit_message_text(tr(lang, "describe"), parse_mode="Markdown")
    elif q.data.startswith("pay_"):
        pack = q.data.split("_")[1]
        await context.bot.send_invoice(chat_id=uid, title="MusicAi Pack", description=f"{pack} songs", payload=f"pack_{pack}", provider_token="", currency="XTR", prices=[LabeledPrice("Stars", PACKS[pack])])

async def user_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = await adb_get_user(uid)
    lang, state = u["lang"], u["state"]

    if state.get("awaiting_custom"):
        state["custom_theme"] = update.message.text; state["awaiting_custom"] = False
        await adb_set(uid, state=state)
        await update.message.reply_text(tr(lang, "choose_genre"), reply_markup=kb_genres())
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

    theme = state.get("custom_theme") or state.get("theme")
    prompt = f"Song about {theme}, Genre: {state['genre']}, Story: {prompt_text}. Language: {lang}. 2 variants."
    msg = await update.message.reply_text(tr(lang, "generating"))

    if u["demo_used"] == 0:
        res = await openai_generate_song("DEMO: " + prompt)
        if res:
            try: await msg.edit_text(f"{tr(lang, 'demo_header')}\n\n{res[:3500]}", parse_mode="Markdown")
            except: await msg.edit_text(f"{tr(lang, 'demo_header')}\n\n{res[:3500]}")
            await adb_set(uid, demo_used=1)
        else: await msg.edit_text(tr(lang, "temp_error"))
    elif u["songs"] > 0:
        res = await openai_generate_song("FULL SONG: " + prompt)
        if res:
            try: await msg.edit_text(res[:3900], parse_mode="Markdown")
            except: await msg.edit_text(res[:3900])
            await adb_set(uid, songs=u["songs"]-1)
        else: await msg.edit_text(tr(lang, "temp_error"))
    else:
        await msg.delete()
        await update.message.reply_text(tr(lang, "no_credits"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⭐ Buy 1 song", callback_data="pay_1")]]))

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
    app.add_handler(CommandHandler("balance", balance_cmd))
    app.add_handler(CommandHandler("current", current_cmd))
    app.add_handler(CommandHandler("buy", buy_cmd))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT | filters.VOICE, user_input))
    app.add_handler(PreCheckoutQueryHandler(pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    app.run_polling()

if __name__ == "__main__":
    main()
