import os
import json
import asyncio
import logging
from typing import Dict, Any, Optional

import aiohttp
import stripe
import psycopg
from psycopg.rows import dict_row

from dotenv import load_dotenv

from fastapi import FastAPI, Request, Header, HTTPException

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BotCommand,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# Load environment variables
load_dotenv()

# -------------------------
# Configuration
# -------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()

PIAPI_API_KEY = os.getenv("PIAPI_API_KEY", "").strip()
PIAPI_BASE_URL = os.getenv("PIAPI_BASE_URL", "https://api.piapi.ai").strip().rstrip("/")
PIAPI_GENERATE_PATH = os.getenv("PIAPI_GENERATE_PATH", "/api/v1/task").strip()

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "").strip()
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()
# Get bot username for Telegram redirect URLs
BOT_USERNAME = os.getenv("BOT_USERNAME", "").strip()
# Default redirect URLs point back to Telegram bot
STRIPE_SUCCESS_URL = os.getenv("STRIPE_SUCCESS_URL", f"https://t.me/{BOT_USERNAME}" if BOT_USERNAME else "").strip()
STRIPE_CANCEL_URL = os.getenv("STRIPE_CANCEL_URL", f"https://t.me/{BOT_USERNAME}" if BOT_USERNAME else "").strip()

# -------------------------
# Logging
# -------------------------
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# -------------------------
# Stripe initialization
# -------------------------
if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

# -------------------------
# Translations
# -------------------------
TRANSLATIONS = {
    "uk": {
        "welcome": "🎵 Ласкаво просимо до MusicAI PRO!\nЯ допоможу створити персональну пісню.",
        "choose_language": "Оберіть мову:",
        "language_set": "Мову встановлено: Українська 🇺🇦",
        "choose_genre": "🎵 Чудово! Тепер оберіть жанр для вашої пісні:",
        "choose_mood": "Жанр: {}\n\n🎭 Тепер оберіть настрій пісні:",
        "describe_song": "Настрій: {}\n\n✍️ Тепер розкажіть, про що ваша пісня!",
        "menu": "📋 Головне меню",
        "buy": "💎 Купити пісні",
        "balance": "Баланс: {} пісень",
        "generating": "🎶 Генерую вашу пісню...",
        "generating_music": "🎶 ГЕНЕРАЦІЯ МУЗИКИ ПОЧАЛАСЬ! ⚡️\nЗазвичай займає не більше 5 хвилин.\nЯ повідомлю, як тільки буде готово 🎧",
        "done": "✅ Готово!",
        "error": "❌ Помилка: {}",
        "no_lyrics": "Тексти не знайдено",
        "no_balance": "Недостатньо балансу",
        "no_audio": "Аудіо не згенеровано",
        "payment_success": "✅ Оплата пройшла успішно!\n\n💎 +{songs} пісень додано на ваш баланс.\n🎵 Ваш баланс: {balance} пісень\n\nТепер ви можете створювати персональні пісні!",
        "help": """🎵 MusicAI PRO - Створюй унікальні пісні!

Як використовувати:
1️⃣ Виберіть мову інтерфейсу
2️⃣ Виберіть жанр музики
3️⃣ Виберіть настрій пісні
4️⃣ Опишіть про що ваша пісня
5️⃣ Я створю текст і музику!

💎 Вартість: 1 пісня = 1 кредит
💰 Купити пісні: /menu → Купити пісні
🌍 Змінити мову: /language

Питання? Напишіть @support""",
        "choose_genre_first": "Спочатку оберіть жанр:",
        "generate_button": "🎵 Згенерувати пісню",
        "your_lyrics": "📝 Ваш текст пісні:",
        "enter_custom_genre": "✏️ Введіть свій жанр:",
        "enter_custom_mood": "✏️ Введіть свій настрій:",
    },
    "en": {
        "welcome": "🎵 Welcome to MusicAI PRO!\nI'll help you create personalized songs.",
        "choose_language": "Choose your language:",
        "language_set": "Language set to English 🇬🇧",
        "choose_genre": "🎵 Great! Now choose a genre for your song:",
        "choose_mood": "Genre: {}\n\n🎭 Now choose the mood of your song:",
        "describe_song": "Mood: {}\n\n✍️ Now tell me what your song is about!",
        "menu": "📋 Main Menu",
        "buy": "💎 Buy Songs",
        "balance": "Balance: {} songs",
        "generating": "🎶 Generating your song...",
        "generating_music": "🎶 MUSIC GENERATION STARTED! ⚡️\nUsually takes no more than 5 minutes.\nI'll notify you when it's ready 🎧",
        "done": "✅ Done!",
        "error": "❌ Error: {}",
        "no_lyrics": "No lyrics found",
        "no_balance": "Insufficient balance",
        "no_audio": "No audio generated",
        "payment_success": "✅ Payment successful!\n\n💎 +{songs} songs added to your balance.\n🎵 Your balance: {balance} songs\n\nYou can now create your personalized songs!",
        "help": """🎵 MusicAI PRO - Create unique songs!

How to use:
1️⃣ Choose interface language
2️⃣ Select music genre
3️⃣ Select song mood
4️⃣ Describe what your song is about
5️⃣ I'll create lyrics and music!

💎 Cost: 1 song = 1 credit
💰 Buy songs: /menu → Buy Songs
🌍 Change language: /language

Questions? Contact @support""",
        "choose_genre_first": "Choose genre first:",
        "generate_button": "🎵 Generate Song",
        "your_lyrics": "📝 Your lyrics:",
        "enter_custom_genre": "✏️ Enter your custom genre:",
        "enter_custom_mood": "✏️ Enter your custom mood:",
    },
    "ru": {
        "welcome": "🎵 Добро пожаловать в MusicAI PRO!\nЯ помогу создать персональную песню.",
        "choose_language": "Выберите язык:",
        "language_set": "Язык установлен: Русский 🇷🇺",
        "choose_genre": "🎵 Отлично! Теперь выберите жанр для вашей песни:",
        "choose_mood": "Жанр: {}\n\n🎭 Теперь выберите настроение песни:",
        "describe_song": "Настроение: {}\n\n✍️ Теперь расскажите, о чём ваша песня!",
        "menu": "📋 Главное меню",
        "buy": "💎 Купить песни",
        "balance": "Баланс: {} песен",
        "generating": "🎶 Генерирую вашу песню...",
        "generating_music": "🎶 ГЕНЕРАЦИЯ МУЗЫКИ НАЧАЛАСЬ! ⚡️\nОбычно занимает не более 5 минут.\nЯ сообщу, как только будет готово 🎧",
        "done": "✅ Готово!",
        "error": "❌ Ошибка: {}",
        "no_lyrics": "Тексты не найдены",
        "no_balance": "Недостаточно баланса",
        "no_audio": "Аудио не сгенерировано",
        "payment_success": "✅ Оплата прошла успешно!\n\n💎 +{songs} песен добавлено на ваш баланс.\n🎵 Ваш баланс: {balance} песен\n\nТеперь вы можете создавать персональные песни!",
        "help": """🎵 MusicAI PRO - Создавай уникальные песни!

Как использовать:
1️⃣ Выберите язык интерфейса
2️⃣ Выберите жанр музыки
3️⃣ Выберите настроение песни
4️⃣ Опишите о чём ваша песня
5️⃣ Я создам текст и музыку!

💎 Стоимость: 1 песня = 1 кредит
💰 Купить песни: /menu → Купить песни
🌍 Изменить язык: /language

Вопросы? Напишите @support""",
        "choose_genre_first": "Сначала выберите жанр:",
        "generate_button": "🎵 Сгенерировать песню",
        "your_lyrics": "📝 Ваш текст песни:",
        "enter_custom_genre": "✏️ Введите свой жанр:",
        "enter_custom_mood": "✏️ Введите своё настроение:",
    },
    "pl": {
        "welcome": "🎵 Witamy w MusicAI PRO!\nPomogę Ci stworzyć spersonalizowaną piosenkę.",
        "choose_language": "Wybierz język:",
        "language_set": "Język ustawiony: Polski 🇵🇱",
        "choose_genre": "🎵 Świetnie! Teraz wybierz gatunek dla twojej piosenki:",
        "choose_mood": "Gatunek: {}\n\n🎭 Teraz wybierz nastrój piosenki:",
        "describe_song": "Nastrój: {}\n\n✍️ Teraz powiedz mi o czym jest twoja piosenka!",
        "menu": "📋 Menu główne",
        "buy": "💎 Kup piosenki",
        "balance": "Saldo: {} piosenek",
        "generating": "🎶 Generuję twoją piosenkę...",
        "generating_music": "🎶 GENERACJA MUZYKI ROZPOCZĘTA! ⚡️\nZwykle trwa nie więcej niż 5 minut.\nPowiadomię Cię, gdy będzie gotowe 🎧",
        "done": "✅ Gotowe!",
        "error": "❌ Błąd: {}",
        "no_lyrics": "Nie znaleziono tekstów",
        "no_balance": "Niewystarczające saldo",
        "no_audio": "Nie wygenerowano audio",
        "payment_success": "✅ Płatność zakończona sukcesem!\n\n💎 +{songs} piosenek dodano do twojego salda.\n🎵 Twoje saldo: {balance} piosenek\n\nTeraz możesz tworzyć spersonalizowane piosenki!",
        "help": """🎵 MusicAI PRO - Twórz unikalne piosenki!

Jak używać:
1️⃣ Wybierz język interfejsu
2️⃣ Wybierz gatunek muzyki
3️⃣ Wybierz nastrój piosenki
4️⃣ Opisz o czym jest twoja piosenka
5️⃣ Stworzę tekst i muzykę!

💎 Koszt: 1 piosenka = 1 kredyt
💰 Kup piosenki: /menu → Kup piosenki
🌍 Zmień język: /language

Pytania? Skontaktuj się @support""",
        "choose_genre_first": "Najpierw wybierz gatunek:",
        "generate_button": "🎵 Generuj piosenkę",
        "your_lyrics": "📝 Twój tekst:",
        "enter_custom_genre": "✏️ Wprowadź własny gatunek:",
        "enter_custom_mood": "✏️ Wprowadź własny nastrój:",
    },
    "es": {
        "welcome": "🎵 ¡Bienvenido a MusicAI PRO!\nTe ayudaré a crear canciones personalizadas.",
        "choose_language": "Elige tu idioma:",
        "language_set": "Idioma configurado: Español 🇪🇸",
        "choose_genre": "🎵 ¡Genial! Ahora elige un género para tu canción:",
        "choose_mood": "Género: {}\n\n🎭 Ahora elige el estado de ánimo de tu canción:",
        "describe_song": "Estado de ánimo: {}\n\n✍️ ¡Ahora cuéntame de qué trata tu canción!",
        "menu": "📋 Menú principal",
        "buy": "💎 Comprar canciones",
        "balance": "Saldo: {} canciones",
        "generating": "🎶 Generando tu canción...",
        "generating_music": "🎶 ¡GENERACIÓN DE MÚSICA INICIADA! ⚡️\nNormalmente tarda no más de 5 minutos.\nTe avisaré cuando esté lista 🎧",
        "done": "✅ ¡Listo!",
        "error": "❌ Error: {}",
        "no_lyrics": "No se encontraron letras",
        "no_balance": "Saldo insuficiente",
        "no_audio": "No se generó audio",
        "payment_success": "✅ ¡Pago exitoso!\n\n💎 +{songs} canciones añadidas a tu saldo.\n🎵 Tu saldo: {balance} canciones\n\n¡Ahora puedes crear tus canciones personalizadas!",
        "help": """🎵 MusicAI PRO - ¡Crea canciones únicas!

Cómo usar:
1️⃣ Elige el idioma de la interfaz
2️⃣ Selecciona el género musical
3️⃣ Selecciona el estado de ánimo de la canción
4️⃣ Describe de qué trata tu canción
5️⃣ ¡Crearé la letra y la música!

💎 Costo: 1 canción = 1 crédito
💰 Comprar canciones: /menu → Comprar canciones
🌍 Cambiar idioma: /language

¿Preguntas? Contacta @support""",
        "choose_genre_first": "Primero elige un género:",
        "generate_button": "🎵 Generar canción",
        "your_lyrics": "📝 Tu letra:",
        "enter_custom_genre": "✏️ Introduce tu género personalizado:",
        "enter_custom_mood": "✏️ Introduce tu estado de ánimo personalizado:",
    },
    "fr": {
        "welcome": "🎵 Bienvenue sur MusicAI PRO!\nJe vais vous aider à créer des chansons personnalisées.",
        "choose_language": "Choisissez votre langue:",
        "language_set": "Langue définie: Français 🇫🇷",
        "choose_genre": "🎵 Super! Maintenant choisissez un genre pour votre chanson:",
        "choose_mood": "Genre: {}\n\n🎭 Maintenant choisissez l'ambiance de votre chanson:",
        "describe_song": "Ambiance: {}\n\n✍️ Maintenant dites-moi de quoi parle votre chanson!",
        "menu": "📋 Menu principal",
        "buy": "💎 Acheter des chansons",
        "balance": "Solde: {} chansons",
        "generating": "🎶 Génération de votre chanson...",
        "generating_music": "🎶 GÉNÉRATION DE MUSIQUE DÉMARRÉE! ⚡️\nPrend généralement pas plus de 5 minutes.\nJe vous préviendrai quand c'est prêt 🎧",
        "done": "✅ Terminé!",
        "error": "❌ Erreur: {}",
        "no_lyrics": "Aucune parole trouvée",
        "no_balance": "Solde insuffisant",
        "no_audio": "Aucun audio généré",
        "payment_success": "✅ Paiement réussi!\n\n💎 +{songs} chansons ajoutées à votre solde.\n🎵 Votre solde: {balance} chansons\n\nVous pouvez maintenant créer vos chansons personnalisées!",
        "help": """🎵 MusicAI PRO - Créez des chansons uniques!

Comment utiliser:
1️⃣ Choisissez la langue de l'interface
2️⃣ Sélectionnez le genre musical
3️⃣ Sélectionnez l'ambiance de la chanson
4️⃣ Décrivez le sujet de votre chanson
5️⃣ Je créerai les paroles et la musique!

💎 Coût: 1 chanson = 1 crédit
💰 Acheter des chansons: /menu → Acheter des chansons
🌍 Changer de langue: /language

Questions? Contactez @support""",
        "choose_genre_first": "Choisissez d'abord un genre:",
        "generate_button": "🎵 Générer la chanson",
        "your_lyrics": "📝 Vos paroles:",
        "enter_custom_genre": "✏️ Entrez votre genre personnalisé:",
        "enter_custom_mood": "✏️ Entrez votre ambiance personnalisée:",
    },
    "de": {
        "welcome": "🎵 Willkommen bei MusicAI PRO!\nIch helfe dir, personalisierte Songs zu erstellen.",
        "choose_language": "Wähle deine Sprache:",
        "language_set": "Sprache eingestellt: Deutsch 🇩🇪",
        "choose_genre": "🎵 Großartig! Wähle jetzt ein Genre für deinen Song:",
        "choose_mood": "Genre: {}\n\n🎭 Wähle jetzt die Stimmung deines Songs:",
        "describe_song": "Stimmung: {}\n\n✍️ Erzähl mir jetzt, worum es in deinem Song geht!",
        "menu": "📋 Hauptmenü",
        "buy": "💎 Songs kaufen",
        "balance": "Guthaben: {} Songs",
        "generating": "🎶 Generiere deinen Song...",
        "generating_music": "🎶 MUSIKGENERIERUNG GESTARTET! ⚡️\nDauert normalerweise nicht länger als 5 Minuten.\nIch benachrichtige dich, wenn er fertig ist 🎧",
        "done": "✅ Fertig!",
        "error": "❌ Fehler: {}",
        "no_lyrics": "Keine Texte gefunden",
        "no_balance": "Unzureichendes Guthaben",
        "no_audio": "Kein Audio generiert",
        "payment_success": "✅ Zahlung erfolgreich!\n\n💎 +{songs} Songs zu deinem Guthaben hinzugefügt.\n🎵 Dein Guthaben: {balance} Songs\n\nDu kannst jetzt deine personalisierten Songs erstellen!",
        "help": """🎵 MusicAI PRO - Erstelle einzigartige Songs!

Wie zu verwenden:
1️⃣ Wähle die Schnittstellensprache
2️⃣ Wähle das Musikgenre
3️⃣ Wähle die Stimmung des Songs
4️⃣ Beschreibe, worum es in deinem Song geht
5️⃣ Ich erstelle den Text und die Musik!

💎 Kosten: 1 Song = 1 Kredit
💰 Songs kaufen: /menu → Songs kaufen
🌍 Sprache ändern: /language

Fragen? Kontaktiere @support""",
        "choose_genre_first": "Wähle zuerst ein Genre:",
        "generate_button": "🎵 Song generieren",
        "your_lyrics": "📝 Dein Text:",
        "enter_custom_genre": "✏️ Gib dein eigenes Genre ein:",
        "enter_custom_mood": "✏️ Gib deine eigene Stimmung ein:",
    },
}

LANGS = ["uk", "en", "ru", "es", "fr", "de", "pl"]

# -------------------------
# Pricing packs
# -------------------------
PACKS = {
    "pack_1": {"songs": 1, "price": 6.00, "label": "1 song - €6.00"},
    "pack_5": {"songs": 5, "price": 20.00, "label": "5 songs - €20.00"},
    "pack_30": {"songs": 30, "price": 50.00, "label": "30 songs - €50.00"},
}

# -------------------------
# DB helpers (sync, call via asyncio.to_thread)
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
            lang TEXT NOT NULL DEFAULT 'uk',
            balance INT NOT NULL DEFAULT 0,
            demo_used INT NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """)
        conn.commit()

def ensure_user(user_id: int):
    with db_conn() as conn:
        conn.execute("INSERT INTO users (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (user_id,))
        conn.commit()

def set_lang(user_id: int, lang: str):
    ensure_user(user_id)
    with db_conn() as conn:
        conn.execute("UPDATE users SET lang=%s WHERE user_id=%s", (lang, user_id))
        conn.commit()

def get_user(user_id: int) -> Dict[str, Any]:
    ensure_user(user_id)
    with db_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id=%s", (user_id,)).fetchone()
        return dict(row) if row else {}

def add_balance(user_id: int, songs: int):
    ensure_user(user_id)
    with db_conn() as conn:
        conn.execute("UPDATE users SET balance=balance+%s WHERE user_id=%s", (songs, user_id))
        conn.commit()

def get_balance(user_id: int) -> int:
    """Get user's current balance"""
    user = get_user(user_id)
    return user.get("balance", 0)

def consume_song(user_id: int) -> bool:
    ensure_user(user_id)
    with db_conn() as conn:
        row = conn.execute("SELECT balance FROM users WHERE user_id=%s", (user_id,)).fetchone()
        if not row or row["balance"] < 1:
            return False
        conn.execute("UPDATE users SET balance=balance-1 WHERE user_id=%s", (user_id,))
        conn.commit()
        return True

# -------------------------
# Helpers
# -------------------------
def tr(user_id: int, key: str) -> str:
    """Translate text for user"""
    user = get_user(user_id)
    lang = user.get("lang", "uk")
    return TRANSLATIONS.get(lang, TRANSLATIONS["uk"]).get(key, key)

# -------------------------
# OpenRouter lyrics generation
# -------------------------
async def openrouter_lyrics(topic: str, genre: str, mood: str) -> str:
    """Generate song lyrics using OpenRouter with two-step validation.
    
    Language is automatically detected from the topic text itself (not passed as parameter).
    """
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY not set")
    
    # Step 1: Generate initial lyrics - PROFESSIONAL SONGWRITER LEVEL
    # Detect language from topic text
    def detect_language(text):
        """Detect if text is in Ukrainian, Russian, or English"""
        ukrainian_chars = set('іїєґІЇЄҐ')
        russian_chars = set('ыъэёЫЪЭЁ')
        
        if any(char in text for char in ukrainian_chars):
            return "Ukrainian"
        elif any(char in text for char in russian_chars):
            return "Russian"
        elif any('a' <= char.lower() <= 'z' for char in text):
            return "English"
        else:
            # Default to Ukrainian if can't detect
            return "Ukrainian"
    
    detected_lang = detect_language(topic)
    
    system_prompt_step1 = f"""You are a professional songwriter.

Write a SONG, not a poem, in {detected_lang} language ONLY.

Rules:
- Use clear rhyme schemes (ABAB or AABB in verses)
- Every verse must rhyme
- Chorus must be catchy, emotional and easy to sing
- Simple, spoken language
- Focus on emotions, people, real situations
- Avoid complex metaphors
- Lyrics must sound natural when sung
- No poetry style

Structure:
Verse 1  
Chorus  
Verse 2  
Chorus  
Bridge  
Final Chorus  

Rhyme rules:
- Lines must end with rhyming words
- Rhymes must sound natural, not forced

Style:
Warm, emotional, personal  
Like popular radio songs

CRITICAL: Write ONLY in {detected_lang}. DO NOT use any other language.

Output ONLY the lyrics in {detected_lang}."""
    
    user_prompt_step1 = f"""Language: {detected_lang}

Topic: {topic}
Mood: {mood}

Write a radio-friendly song in {detected_lang} with clear rhymes and emotional appeal:"""

    
    async with aiohttp.ClientSession() as session:
        # Step 1: Generate initial lyrics
        async with session.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "openai/gpt-4o-mini",  # Upgraded to GPT-4o-mini for better language detection
                "messages": [
                    {"role": "system", "content": system_prompt_step1},
                    {"role": "user", "content": user_prompt_step1}
                ],
            },
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"OpenRouter error: {text}")
            data = await resp.json()
            initial_lyrics = data["choices"][0]["message"]["content"]
        
        # Step 2: Simple rhyme check and correction
        rhyme_correction_prompt = f"""**LANGUAGE: {detected_lang} ONLY**
The lyrics below are in {detected_lang}. Keep them in {detected_lang}.
DO NOT translate. ONLY fix rhymes if needed.

**Requirements:**
- Check if verses have clear rhymes (ABAB or AABB)
- Make sure rhymes sound natural (not forced)
- Keep the story and emotions the same
- Simple, spoken language (like radio songs)
- Make sure it sounds good when sung
- Write ONLY in {detected_lang}

**Original lyrics:**
{initial_lyrics}

**Fix any rhyme issues and make it sound more natural (keep {detected_lang} language):**"""

        async with session.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "openai/gpt-4o-mini",  # Upgraded to GPT-4o-mini for better rhyme and language handling
                "messages": [
                    {"role": "system", "content": f"You are an expert rhyme editor. You rewrite lyrics to have perfect phonetic rhymes (rhymes by SOUND) while ABSOLUTELY writing in {detected_lang} ONLY. Write every word in {detected_lang}. NEVER use English or any other language."},
                    {"role": "user", "content": rhyme_correction_prompt}
                ],
            },
        ) as resp:
            if resp.status != 200:
                # If rhyme correction fails, return initial lyrics
                print(f"Warning: Rhyme correction step failed with status {resp.status}, using initial lyrics")
                return initial_lyrics
            data = await resp.json()
            final_lyrics = data["choices"][0]["message"]["content"]
            return final_lyrics

# -------------------------
# PIAPI Suno music generation
# -------------------------
def generate_song_title(lyrics: str, max_length: int = 50) -> str:
    """Generate a meaningful song title from lyrics"""
    if not lyrics:
        return "Untitled Song"
    
    # Try to extract chorus (most common approach)
    lines = lyrics.split('\n')
    chorus_lines = []
    in_chorus = False
    
    for line in lines:
        line = line.strip()
        if '[Chorus]' in line or '[CHORUS]' in line:
            in_chorus = True
            continue
        elif line.startswith('[') and line.endswith(']'):
            in_chorus = False
            continue
        
        if in_chorus and line:
            chorus_lines.append(line)
    
    # If we found a chorus, use first line
    if chorus_lines:
        title = chorus_lines[0]
    else:
        # Otherwise, use the first meaningful line (skip tags like [Verse 1])
        for line in lines:
            line = line.strip()
            if line and not (line.startswith('[') and line.endswith(']')):
                title = line
                break
        else:
            title = "Untitled Song"
    
    # Clean up the title - remove rhyme markers (A)/(B) and punctuation
    import re
    title = re.sub(r'\s*\([AB]\)\s*$', '', title)  # Remove (A) or (B) at end
    title = title.rstrip('.,!?;:')  # Remove trailing punctuation
    title = title.strip()  # Remove extra whitespace
    
    # Limit length
    if len(title) > max_length:
        title = title[:max_length].rsplit(' ', 1)[0]  # Cut at word boundary
    
    return title if title else "Untitled Song"

def get_user_gender(user_id: int) -> str:
    """Get user gender from database. Returns 'male', 'female', or 'unknown'"""
    user = get_user(user_id)
    return user.get("gender", "unknown")

async def analyze_song_gender_logic(topic: str, lyrics: str) -> str:
    """Analyze if song should have male or female vocals using AI.
    
    Returns: 'male', 'female', 'neutral', or 'unclear'
    """
    # Create a prompt to analyze gender context
    prompt = f"""Analyze if this song should be sung by a male or female vocalist based on the content.

Topic: {topic}

Lyrics excerpt: {lyrics[:400]}

Consider:
- First-person perspective (I/me pronouns and gender context)
- Subject matter (soldier, father, mother, bride, etc.)
- Gender-specific themes

Answer with ONLY ONE word:
- "male" if the song is clearly from a male perspective or should be sung by male
- "female" if the song is clearly from a female perspective or should be sung by female
- "neutral" if gender doesn't matter or could be either
- "unclear" if you cannot determine

Answer:"""

    try:
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": OPENROUTER_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 10,
            "temperature": 0.3,
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post("https://openrouter.ai/api/v1/chat/completions", 
                                   json=payload, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    result = data["choices"][0]["message"]["content"].lower().strip()
                    # Return only if valid result
                    if result in ["male", "female", "neutral", "unclear"]:
                        return result
    except Exception as e:
        log.error(f"Error analyzing gender: {e}")
    
    return "unclear"

def sanitize_for_piapi(text: str) -> str:
    """
    Sanitize text for PIAPI to avoid special characters that may cause issues.
    
    - Replace smart quotes with regular quotes
    - Replace em/en dashes with regular hyphens
    - Remove zero-width spaces and invisible characters
    - Strip excessive whitespace and newlines
    """
    import re
    
    # Replace smart quotes with regular quotes
    text = text.replace('"', '"').replace('"', '"')
    text = text.replace(''', "'").replace(''', "'")
    
    # Replace em/en dashes with regular hyphens
    text = text.replace('—', '-').replace('–', '-')
    
    # Remove zero-width spaces and other invisible Unicode characters
    text = re.sub(r'[\u200B-\u200D\uFEFF]', '', text)
    
    # Replace multiple spaces with single space
    text = re.sub(r' +', ' ', text)
    
    # Replace multiple newlines with single newline
    text = re.sub(r'\n\n+', '\n', text)
    
    # Strip leading/trailing whitespace
    text = text.strip()
    
    return text

async def piapi_generate_music(lyrics: str, genre: str, mood: str, demo: bool, gender: str = None, use_udio: bool = False) -> Dict[str, Any]:
    """Generate music using PIAPI Suno or Udio endpoint - Step 1: Create task
    
    Args:
        lyrics: Song lyrics
        genre: Music genre
        mood: Song mood
        demo: Whether this is demo mode
        gender: Optional vocal gender ('male', 'female', or None for default)
        use_udio: If True, use Udio (music-u) instead of Suno (default: False)
    """
    if not PIAPI_API_KEY:
        raise RuntimeError("PIAPI_API_KEY not set")
    
    if not PIAPI_BASE_URL:
        raise RuntimeError("PIAPI_BASE_URL not set. Please configure the PIAPI server URL in environment variables.")
    
    # Check if PIAPI_BASE_URL looks like a placeholder
    if "your-piapi-server.com" in PIAPI_BASE_URL or "example.com" in PIAPI_BASE_URL:
        raise RuntimeError(f"PIAPI_BASE_URL is set to a placeholder value '{PIAPI_BASE_URL}'. Please set it to your actual PIAPI server URL.")
    
    # Check if user incorrectly included the path in PIAPI_BASE_URL
    if "/api/v1/task" in PIAPI_BASE_URL:
        raise RuntimeError(f"PIAPI_BASE_URL should not include the path. Set PIAPI_BASE_URL='https://api.piapi.ai' (without /api/v1/task). Current value: {PIAPI_BASE_URL}")
    
    url = f"{PIAPI_BASE_URL}{PIAPI_GENERATE_PATH}"
    
    # Generate a meaningful title from the lyrics
    song_title = generate_song_title(lyrics)
    
    # Sanitize all text inputs for PIAPI compatibility
    lyrics_clean = sanitize_for_piapi(lyrics)
    title_clean = sanitize_for_piapi(song_title)
    
    if use_udio:
        # Udio (music-u) format
        log.info(f"Calling PIAPI Udio (music-u) at: {url}")
        
        # Build description for Udio
        gpt_description = f"{mood} {genre} song"
        if gender == "male":
            gpt_description += " with male vocals"
        elif gender == "female":
            gpt_description += " with female vocals"
        
        payload = {
            "model": "music-u",
            "task_type": "generate_music",
            "input": {
                "gpt_description_prompt": sanitize_for_piapi(gpt_description),
                "lyrics": lyrics_clean,
                "lyrics_type": "song",
                "seed": -1
            }
        }
    else:
        # Suno format (default)
        log.info(f"Calling PIAPI Suno at: {url}")
        
        tags_clean = sanitize_for_piapi(f"{genre}, {mood}")
        
        # Add gender to tags if specified
        if gender == "male":
            tags_clean += ", male_vocals"
            log.info("Generating with male vocals")
        elif gender == "female":
            tags_clean += ", female_vocals"
            log.info("Generating with female vocals")
        
        # PIAPI Suno format - task-based API
        # Use MINIMAL parameters - only send non-empty required fields
        # Do NOT send mv, make_instrumental, or any experimental fields
        payload = {
            "model": "suno",
            "task_type": "music",
            "input": {}
        }
        
        # Only add non-empty fields to minimize payload
        if lyrics_clean:
            payload["input"]["prompt"] = lyrics_clean
        if tags_clean:
            payload["input"]["tags"] = tags_clean
        if title_clean:
            payload["input"]["title"] = title_clean
    
    # PIAPI uses X-API-Key header, not Authorization Bearer
    headers = {
        "X-API-Key": PIAPI_API_KEY,
        "Content-Type": "application/json",
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    error_msg = f"PIAPI error {resp.status}: {text if text else '(empty response)'}"
                    log.error(f"{error_msg}. URL: {url}")
                    if resp.status == 404:
                        raise RuntimeError(f"PIAPI endpoint not found (404). The URL '{url}' does not exist. Make sure PIAPI_BASE_URL='https://api.piapi.ai' (without /api/v1/task path) and PIAPI_GENERATE_PATH='/api/v1/task'")
                    raise RuntimeError(error_msg)
                return await resp.json()
    except aiohttp.ClientError as e:
        error_msg = f"Cannot connect to PIAPI server at {PIAPI_BASE_URL}. Error: {str(e)}"
        log.error(error_msg)
        raise RuntimeError(f"Connection failed: {str(e)}. Please check that PIAPI_BASE_URL is set to a valid server URL.")

async def piapi_generate_music_with_retry(lyrics: str, genre: str, mood: str, demo: bool = False, gender: str = None, max_retries: int = 4):
    """
    Generate music with retry logic, exponential backoff, and automatic Udio fallback.
    
    Strategy:
    1. Try Suno with retries (attempts 1-4): 0s → 10s → 25s → 60s
    2. If all Suno attempts fail with error code 10000, automatically fallback to Udio
    3. Try Udio (1 attempt without retries)
    
    This helps handle transient PIAPI service issues, rate limiting, and Suno downtime.
    
    Args:
        lyrics: Song lyrics
        genre: Music genre
        mood: Song mood
        demo: Demo mode flag
        gender: Optional gender for vocals
        max_retries: Maximum number of Suno attempts (default: 4)
    
    Returns:
        dict: PIAPI response with task_id
        
    Raises:
        RuntimeError: If all retry attempts fail (both Suno and Udio)
    """
    retry_delays = [0, 10, 25, 60]  # seconds between retries
    suno_failed_with_10000 = False
    last_suno_error = None
    
    # First try Suno with retries
    for attempt in range(max_retries):
        try:
            log.info(f"Suno generation attempt {attempt + 1}/{max_retries}")
            result = await piapi_generate_music(lyrics, genre, mood, demo, gender, use_udio=False)
            
            # Success! Return immediately
            if attempt > 0:
                log.info(f"Suno generation succeeded on attempt {attempt + 1}")
            return result
            
        except Exception as e:
            last_suno_error = e
            error_str = str(e)
            
            # Check if this is error code 10000 (Suno connection failure)
            if "code': 10000" in error_str or "failed to do request" in error_str:
                suno_failed_with_10000 = True
                log.warning(f"Suno attempt {attempt + 1} failed with error code 10000")
            
            is_last_attempt = (attempt == max_retries - 1)
            
            if is_last_attempt:
                # All Suno attempts failed
                if suno_failed_with_10000:
                    log.warning(f"All {max_retries} Suno attempts failed with code 10000. Trying Udio fallback...")
                    break  # Exit loop to try Udio
                else:
                    # Not error 10000 - don't try Udio, just fail
                    log.error(f"All {max_retries} Suno attempts failed. Last error: {e}")
                    raise RuntimeError("Service overloaded or temporarily unavailable. Please try again in a few minutes.")
            
            # Not last attempt - wait and retry with exponential backoff
            delay = retry_delays[attempt + 1] if attempt + 1 < len(retry_delays) else 60
            log.warning(f"Suno attempt {attempt + 1} failed: {e}. Retrying in {delay} seconds...")
            await asyncio.sleep(delay)
    
    # If we got here, all Suno attempts failed with error code 10000
    # Try Udio as fallback
    if suno_failed_with_10000:
        try:
            log.info("Attempting Udio (music-u) as fallback...")
            result = await piapi_generate_music(lyrics, genre, mood, demo, gender, use_udio=True)
            log.info("✅ Udio generation successful! Using Udio as alternative to Suno.")
            return result
        except Exception as udio_error:
            log.error(f"Udio fallback also failed: {udio_error}")
            raise RuntimeError(f"Both Suno and Udio generation failed. Suno error: {last_suno_error}. Udio error: {udio_error}")
    
    # Should never reach here, but just in case
    raise RuntimeError("Music generation failed unexpectedly.")

async def piapi_poll_task(task_id: str, max_attempts: int = 60, delay: int = 5) -> Dict[str, Any]:
    """Poll PIAPI task until completion - Step 2: Wait for results
    
    Args:
        task_id: The task ID returned from piapi_generate_music
        max_attempts: Maximum number of polling attempts (default 60 = 5 minutes)
        delay: Delay between polling attempts in seconds (default 5)
    
    Returns:
        Complete task response with audio URLs
    """
    if not PIAPI_API_KEY:
        raise RuntimeError("PIAPI_API_KEY not set")
    
    url = f"{PIAPI_BASE_URL}/api/v1/task/{task_id}"
    headers = {
        "X-API-Key": PIAPI_API_KEY,
    }
    
    log.info(f"Polling PIAPI task: {task_id}")
    
    try:
        async with aiohttp.ClientSession() as session:
            for attempt in range(max_attempts):
                async with session.get(url, headers=headers) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        raise RuntimeError(f"PIAPI polling error {resp.status}: {text}")
                    
                    data = await resp.json()
                    
                    # Check task status
                    if "data" in data:
                        task_data = data["data"]
                        status = task_data.get("status", "")
                        
                        log.info(f"Task {task_id} status: {status} (attempt {attempt + 1}/{max_attempts})")
                        
                        if status == "completed":
                            log.info(f"Task {task_id} completed successfully")
                            return data
                        elif status in ["failed", "error"]:
                            error_info = task_data.get("error", task_data)
                            # Check for specific PIAPI error codes
                            if isinstance(error_info, dict):
                                error_code = error_info.get("code")
                                error_msg = error_info.get("message", "Unknown error")
                                
                                if error_code == 10000:
                                    raise RuntimeError(f"PIAPI failed to connect to Suno API. This usually means:\n- Suno service is temporarily down\n- Rate limiting\n- PIAPI account needs credits/subscription\nError: {error_info}")
                                else:
                                    raise RuntimeError(f"Task failed (code {error_code}): {error_msg}\nDetails: {error_info}")
                            else:
                                raise RuntimeError(f"Task failed: {error_info}")
                        elif status in ["pending", "processing", "queued"]:
                            # Task still processing, wait and retry
                            await asyncio.sleep(delay)
                            continue
                        else:
                            # Unknown status, wait and retry
                            await asyncio.sleep(delay)
                            continue
            
            # Max attempts reached
            raise RuntimeError(f"Task polling timeout after {max_attempts * delay} seconds. Task may still be processing.")
    
    except aiohttp.ClientError as e:
        error_msg = f"Cannot poll PIAPI task. Error: {str(e)}"
        log.error(error_msg)
        raise RuntimeError(error_msg)

def extract_audio_urls(piapi_resp: Dict[str, Any]) -> list:
    """Extract audio URLs from PIAPI completed task response"""
    urls = []
    
    # Check for data in response
    if "data" in piapi_resp:
        data = piapi_resp["data"]
        
        # If data is a dict with task results
        if isinstance(data, dict):
            # Check for output or clips in the response
            if "output" in data and isinstance(data["output"], list):
                for item in data["output"]:
                    if isinstance(item, dict) and "audio_url" in item:
                        urls.append(item["audio_url"])
            elif "clips" in data and isinstance(data["clips"], list):
                for clip in data["clips"]:
                    if isinstance(clip, dict) and "audio_url" in clip:
                        urls.append(clip["audio_url"])
            # Also check for direct audio_url in data
            elif "audio_url" in data:
                urls.append(data["audio_url"])
        
        # If data is a list
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and "audio_url" in item:
                    urls.append(item["audio_url"])
    
    return urls

# -------------------------
# Keyboards
# -------------------------
def lang_keyboard() -> InlineKeyboardMarkup:
    buttons = []
    for lang in LANGS:
        flag = {"uk": "🇺🇦", "en": "🇬🇧", "ru": "🇷🇺", "es": "🇪🇸", "fr": "🇫🇷", "de": "🇩🇪", "it": "��🇹", "pt": "🇵🇹"}.get(lang, "🌍")
        buttons.append([InlineKeyboardButton(f"{flag} {lang.upper()}", callback_data=f"lang:{lang}")])
    return InlineKeyboardMarkup(buttons)

def menu_keyboard(lang: str) -> InlineKeyboardMarkup:
    # Simple button labels in user's language with "New Song" option
    button_labels = {
        "uk": ("🎵 Нова пісня", "💰 Купити", "💎 Баланс", "❓ Допомога"),
        "en": ("🎵 New Song", "💰 Buy", "💎 Balance", "❓ Help"),
        "ru": ("🎵 Новая песня", "💰 Купить", "💎 Баланс", "❓ Помощь"),
        "pl": ("🎵 Nowa piosenka", "💰 Kup", "💎 Saldo", "❓ Pomoc"),
        "es": ("🎵 Nueva canción", "💰 Comprar", "💎 Saldo", "❓ Ayuda"),
        "fr": ("🎵 Nouvelle chanson", "💰 Acheter", "💎 Solde", "❓ Aide"),
        "de": ("🎵 Neues Lied", "💰 Kaufen", "💎 Guthaben", "❓ Hilfe"),
    }
    labels = button_labels.get(lang, button_labels["en"])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(labels[0], callback_data="newsong")],
        [InlineKeyboardButton(labels[1], callback_data="buy")],
        [InlineKeyboardButton(labels[2], callback_data="balance")],
        [InlineKeyboardButton(labels[3], callback_data="help")],
    ])

def genres_keyboard(lang: str) -> InlineKeyboardMarkup:
    # Genres with emojis and translations
    genre_labels = {
        "uk": {"Pop": "🎵 Поп", "Rock": "🎸 Рок", "Hip-Hop": "🎤 Хіп-Хоп", "Classical": "🎻 Класика", "Club": "💃 Клубна", "Custom": "✏️ Своя"},
        "en": {"Pop": "🎵 Pop", "Rock": "🎸 Rock", "Hip-Hop": "🎤 Hip-Hop", "Classical": "🎻 Classical", "Club": "💃 Club", "Custom": "✏️ Custom"},
        "ru": {"Pop": "🎵 Поп", "Rock": "🎸 Рок", "Hip-Hop": "🎤 Хип-Хоп", "Classical": "🎻 Классика", "Club": "💃 Клубная", "Custom": "✏️ Своя"},
        "pl": {"Pop": "🎵 Pop", "Rock": "🎸 Rock", "Hip-Hop": "🎤 Hip-Hop", "Classical": "🎻 Klasyczna", "Club": "💃 Klubowa", "Custom": "✏️ Własna"},
        "es": {"Pop": "🎵 Pop", "Rock": "🎸 Rock", "Hip-Hop": "🎤 Hip-Hop", "Classical": "🎻 Clásica", "Club": "💃 Club", "Custom": "✏️ Personalizada"},
        "fr": {"Pop": "🎵 Pop", "Rock": "🎸 Rock", "Hip-Hop": "🎤 Hip-Hop", "Classical": "🎻 Classique", "Club": "💃 Club", "Custom": "✏️ Personnalisé"},
        "de": {"Pop": "🎵 Pop", "Rock": "🎸 Rock", "Hip-Hop": "🎤 Hip-Hop", "Classical": "🎻 Klassisch", "Club": "💃 Club", "Custom": "✏️ Eigene"},
    }
    labels = genre_labels.get(lang, genre_labels["en"])
    genres = ["Pop", "Rock", "Hip-Hop", "Classical", "Club", "Custom"]
    buttons = [[InlineKeyboardButton(labels[g], callback_data=f"genre:{g}")] for g in genres]
    return InlineKeyboardMarkup(buttons)

def moods_keyboard(lang: str) -> InlineKeyboardMarkup:
    # Moods with emojis and translations
    mood_labels = {
        "uk": {"Happy": "😊 Радісна", "Sad": "😢 Сумна", "Love": "❤️ Кохання", "Party": "🎉 Вечірка", "Support": "🤝 Підтримка", "Custom": "✏️ Своя"},
        "en": {"Happy": "😊 Happy", "Sad": "😢 Sad", "Love": "❤️ Love", "Party": "🎉 Party", "Support": "🤝 Support", "Custom": "✏️ Custom"},
        "ru": {"Happy": "😊 Радостная", "Sad": "😢 Грустная", "Love": "❤️ Любовь", "Party": "🎉 Вечеринка", "Support": "🤝 Поддержка", "Custom": "✏️ Своя"},
        "pl": {"Happy": "😊 Wesoła", "Sad": "😢 Smutna", "Love": "❤️ Miłość", "Party": "🎉 Impreza", "Support": "🤝 Wsparcie", "Custom": "✏️ Własny"},
        "es": {"Happy": "😊 Feliz", "Sad": "😢 Triste", "Love": "❤️ Amor", "Party": "🎉 Fiesta", "Support": "🤝 Apoyo", "Custom": "✏️ Personalizado"},
        "fr": {"Happy": "😊 Joyeux", "Sad": "😢 Triste", "Love": "❤️ Amour", "Party": "🎉 Fête", "Support": "🤝 Soutien", "Custom": "✏️ Personnalisé"},
        "de": {"Happy": "😊 Fröhlich", "Sad": "😢 Traurig", "Love": "❤️ Liebe", "Party": "🎉 Party", "Support": "🤝 Unterstützung", "Custom": "✏️ Eigene"},
    }
    labels = mood_labels.get(lang, mood_labels["en"])
    moods = ["Happy", "Sad", "Love", "Party", "Support", "Custom"]
    buttons = [[InlineKeyboardButton(labels[m], callback_data=f"mood:{m}")] for m in moods]
    return InlineKeyboardMarkup(buttons)

def buy_keyboard(lang: str, user_id: int) -> InlineKeyboardMarkup:
    buttons = []
    for pack_id, pack_data in PACKS.items():
        label = pack_data["label"]
        buttons.append([InlineKeyboardButton(label, callback_data=f"buypack:{pack_id}")])
    return InlineKeyboardMarkup(buttons)

def create_checkout_session(user_id: int, pack_id: str) -> str:
    """Create Stripe checkout session and return URL"""
    if not STRIPE_SECRET_KEY:
        raise RuntimeError("Stripe not configured")
    
    pack = PACKS.get(pack_id)
    if not pack:
        raise ValueError("Invalid pack")
    
    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{
            "price_data": {
                "currency": "usd",
                "product_data": {"name": pack["label"]},
                "unit_amount": int(pack["price"] * 100),
            },
            "quantity": 1,
        }],
        mode="payment",
        success_url=STRIPE_SUCCESS_URL,
        cancel_url=STRIPE_CANCEL_URL,
        metadata={"user_id": str(user_id), "pack": pack_id},
    )
    return session.url

# -------------------------
# Telegram Handlers
# -------------------------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await asyncio.to_thread(ensure_user, user_id)
    
    text = tr(user_id, "welcome")
    await update.message.reply_text(text, reply_markup=lang_keyboard())

async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show main menu"""
    user_id = update.effective_user.id
    await asyncio.to_thread(ensure_user, user_id)
    
    user = await asyncio.to_thread(get_user, user_id)
    lang = user.get("lang", "uk")
    await update.message.reply_text(tr(user_id, "menu"), reply_markup=menu_keyboard(lang))

async def cmd_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Change language"""
    user_id = update.effective_user.id
    await asyncio.to_thread(ensure_user, user_id)
    
    await update.message.reply_text(tr(user_id, "choose_language"), reply_markup=lang_keyboard())

async def cmd_current(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show current song progress"""
    user_id = update.effective_user.id
    await asyncio.to_thread(ensure_user, user_id)
    
    user_data = context.user_data
    genre = user_data.get("genre", "Not selected")
    mood = user_data.get("mood", "Not selected")
    lyrics = user_data.get("lyrics", "Not generated yet")
    
    message = f"📝 **Current Song:**\n\n"
    message += f"🎸 Genre: {genre}\n"
    message += f"😊 Mood: {mood}\n\n"
    
    if lyrics != "Not generated yet":
        message += f"📄 Lyrics:\n{lyrics[:500]}{'...' if len(lyrics) > 500 else ''}"
    else:
        message += "No lyrics generated yet. Use /start to create a song!"
    
    await update.message.reply_text(message)

async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user balance"""
    user_id = update.effective_user.id
    await asyncio.to_thread(ensure_user, user_id)
    
    user = await asyncio.to_thread(get_user, user_id)
    balance = user.get("balance", 0)
    lang = user.get("lang", "en")
    
    message = tr(user_id, "balance").format(balance)
    await update.message.reply_text(message, reply_markup=menu_keyboard(lang))

async def cmd_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show purchase options"""
    user_id = update.effective_user.id
    await asyncio.to_thread(ensure_user, user_id)
    
    user = await asyncio.to_thread(get_user, user_id)
    balance = user.get("balance", 0)
    lang = user.get("lang", "en")
    
    text = f"{tr(user_id, 'buy')}\n{tr(user_id, 'balance').format(balance)}"
    await update.message.reply_text(text, reply_markup=buy_keyboard(lang, user_id))

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help text"""
    user_id = update.effective_user.id
    await asyncio.to_thread(ensure_user, user_id)
    
    user = await asyncio.to_thread(get_user, user_id)
    lang = user.get("lang", "en")
    
    await update.message.reply_text(tr(user_id, "help"), reply_markup=menu_keyboard(lang))

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        if not query:
            log.warning("Callback query is None")
            return
            
        user_id = query.from_user.id
        data = query.data
        
        log.info(f"Callback from user {user_id}: {data}")
        
        # Ensure user exists in database first
        try:
            await asyncio.to_thread(ensure_user, user_id)
        except Exception as db_err:
            log.error(f"Failed to ensure user {user_id} in database: {db_err}", exc_info=True)
            await query.answer("❌ Database error. Please contact support.", show_alert=True)
            return
        
        # Answer the callback query first
        try:
            await query.answer()
        except Exception as e:
            log.error(f"Failed to answer callback query: {e}")
        
        if data.startswith("lang:"):
            lang = data.split(":")[1]
            await asyncio.to_thread(set_lang, user_id, lang)
            # Store language in context for later use
            context.user_data["lang"] = lang
            # Go directly to genre selection for song creation
            await query.edit_message_text(
                tr(user_id, "choose_genre"),
                reply_markup=genres_keyboard(lang)
            )
        
        elif data == "buy":
            user = await asyncio.to_thread(get_user, user_id)
            balance = user.get("balance", 0)
            text = f"{tr(user_id, 'buy')}\n{tr(user_id, 'balance').format(balance)}"
            await query.edit_message_text(text, reply_markup=buy_keyboard(user.get("lang", "en"), user_id))
        
        elif data.startswith("buypack:"):
            pack_id = data.split(":")[1]
            try:
                url = create_checkout_session(user_id, pack_id)
                await query.edit_message_text(f"Click to complete payment:\n{url}")
            except Exception as e:
                log.error(f"Checkout session error: {e}")
                await query.edit_message_text(tr(user_id, "error").format(str(e)))
        
        elif data == "balance":
            user = await asyncio.to_thread(get_user, user_id)
            balance = user.get("balance", 0)
            lang = user.get("lang", "uk")
            text = tr(user_id, "balance").format(balance)
            await query.edit_message_text(text, reply_markup=menu_keyboard(lang))
        
        elif data == "help":
            user = await asyncio.to_thread(get_user, user_id)
            lang = user.get("lang", "uk")
            await query.edit_message_text(tr(user_id, "help"), reply_markup=menu_keyboard(lang))
        
        elif data == "menu":
            user = await asyncio.to_thread(get_user, user_id)
            lang = user.get("lang", "uk")
            await query.edit_message_text(tr(user_id, "menu"), reply_markup=menu_keyboard(lang))
        
        elif data == "newsong":
            # Start new song creation - go directly to genre selection
            lang = context.user_data.get("lang")
            if not lang:
                user = await asyncio.to_thread(get_user, user_id)
                lang = user.get("lang", "en")
                context.user_data["lang"] = lang
            await query.edit_message_text(
                tr(user_id, "choose_genre"),
                reply_markup=genres_keyboard(lang)
            )
        
        elif data.startswith("genre:"):
            genre = data.split(":")[1]
            
            if genre == "Custom":
                # Ask user to type their custom genre
                context.user_data["awaiting_custom_genre"] = True
                lang = context.user_data.get("lang", "en")
                await query.edit_message_text(
                    tr(user_id, "enter_custom_genre")
                )
            else:
                context.user_data["genre"] = genre
                # Get user language
                lang = context.user_data.get("lang")
                if not lang:
                    user = await asyncio.to_thread(get_user, user_id)
                    lang = user.get("lang", "en")
                    context.user_data["lang"] = lang
                await query.edit_message_text(
                    tr(user_id, "choose_mood").format(genre),
                    reply_markup=moods_keyboard(lang)
                )
        
        elif data.startswith("mood:"):
            mood = data.split(":")[1]
            
            if mood == "Custom":
                # Ask user to type their custom mood
                context.user_data["awaiting_custom_mood"] = True
                await query.edit_message_text(
                    tr(user_id, "enter_custom_mood")
                )
            else:
                context.user_data["mood"] = mood
                await query.edit_message_text(
                    tr(user_id, "describe_song").format(mood)
                )
        
        elif data.startswith("generate:"):
            # Generate music from lyrics
            user_data = context.user_data
            lyrics = user_data.get("lyrics", "")
            genre = user_data.get("genre", "Pop")
            mood = user_data.get("mood", "Happy")
            topic = user_data.get("topic", "")  # Get original song description
            
            if not lyrics:
                await query.edit_message_text(tr(user_id, "error").format(tr(user_id, "no_lyrics")))
                return
            
            # Check balance
            can_generate = await asyncio.to_thread(consume_song, user_id)
            if not can_generate:
                await query.edit_message_text(tr(user_id, "error").format(tr(user_id, "no_balance")))
                return
            
            # Remove the "Generate Song" button but keep the lyrics visible
            await query.edit_message_reply_markup(reply_markup=None)
            # Send a new message about music generation
            await query.message.reply_text(tr(user_id, "generating_music"))
            
            try:
                # Step 0: Determine gender-based vocal selection
                user_gender = get_user_gender(user_id)  # 'male', 'female', or 'unknown'
                song_gender = await analyze_song_gender_logic(topic, lyrics)  # 'male', 'female', 'neutral', 'unclear'
                
                log.info(f"User gender: {user_gender}, Song gender analysis: {song_gender}")
                
                # Decide which versions to generate
                generate_versions = []
                
                if song_gender in ["male", "female"]:
                    # Song has clear gender logic - respect it
                    generate_versions = [song_gender]
                    log.info(f"Song has clear {song_gender} context - generating {song_gender} version only")
                elif user_gender == "male" and song_gender in ["neutral", "unclear"]:
                    # Male user + ambiguous song -> generate BOTH versions
                    generate_versions = ["male", "female"]
                    log.info("Male user + neutral song - generating both male and female versions")
                elif user_gender == "female" and song_gender in ["neutral", "unclear"]:
                    # Female user + ambiguous song -> generate female version
                    generate_versions = ["female"]
                    log.info("Female user + neutral song - generating female version")
                else:
                    # Unknown user gender or other cases -> no specific gender
                    generate_versions = [None]
                    log.info("No specific gender preference - generating default version")
                
                # Generate song title from lyrics (will be used for all versions)
                song_title = generate_song_title(lyrics)
                log.info(f"Generated song title: {song_title}")
                
                # Generate each version SEQUENTIALLY (not parallel) with delays between tracks
                generated_count = 0
                last_error = None
                for idx, gender_version in enumerate(generate_versions):
                    try:
                        gender_label = gender_version if gender_version else "default"
                        log.info(f"Generating version {idx + 1}/{len(generate_versions)}: {gender_label} vocals")
                        
                        # Add delay between tracks (except first) to reduce server load
                        if idx > 0:
                            log.info("Waiting 2 seconds before next generation to avoid rate limiting...")
                            await asyncio.sleep(2)
                        
                        # Step 1: Create music generation task WITH RETRY LOGIC
                        result = await piapi_generate_music_with_retry(lyrics, genre, mood, demo=False, gender=gender_version)
                        log.info(f"PIAPI generate response: {result}")
                        
                        # Extract task_id from response
                        task_id = None
                        if "data" in result and isinstance(result["data"], dict):
                            task_id = result["data"].get("task_id")
                        
                        if not task_id:
                            error_msg = f"No task_id in PIAPI response: {result}"
                            log.error(error_msg)
                            last_error = error_msg
                            continue
                        
                        log.info(f"Music generation task created: {task_id} ({gender_label} vocals)")
                        
                        # Step 2: Poll for task completion (this may take 1-5 minutes)
                        completed_result = await piapi_poll_task(task_id, max_attempts=60, delay=5)
                        log.info(f"Polling completed. Result: {completed_result}")
                        
                        # Step 3: Extract audio URLs from completed task
                        audio_urls = extract_audio_urls(completed_result)
                        log.info(f"Extracted audio URLs: {audio_urls}")
                        
                        if audio_urls:
                            for url in audio_urls:
                                # Build caption with title and gender version
                                caption_parts = [f"🎵 {song_title}"]
                                if len(generate_versions) > 1:
                                    version_label = "🎤 Male version" if gender_version == "male" else "🎤 Female version"
                                    caption_parts.append(version_label)
                                
                                caption = "\n".join(caption_parts)
                                await query.message.reply_audio(url, caption=caption)
                                generated_count += 1
                        else:
                            error_msg = f"No audio URLs extracted for {gender_label} version. Response: {completed_result}"
                            log.warning(error_msg)
                            last_error = error_msg
                    
                    except Exception as e:
                        error_msg = f"Error generating {gender_version if gender_version else 'default'} version: {e}"
                        log.error(error_msg, exc_info=True)
                        last_error = str(e)
                        # Continue with next version instead of failing completely
                        continue
                
                # Final message
                if generated_count > 0:
                    await query.message.reply_text(tr(user_id, "done"))
                else:
                    # Provide more specific error message if we have one
                    if last_error:
                        error_text = f"{tr(user_id, 'no_audio')}\n\nDetails: {last_error}"
                    else:
                        error_text = tr(user_id, "no_audio")
                    await query.message.reply_text(tr(user_id, "error").format(error_text))
                    
            except Exception as e:
                log.error(f"Music generation error: {e}")
                await query.message.reply_text(tr(user_id, "error").format(str(e)))
        else:
            log.warning(f"Unknown callback data: {data}")
            
    except Exception as e:
        error_msg = str(e)
        log.error(f"Error in on_callback handler: {error_msg}", exc_info=True)
        try:
            if update and update.callback_query:
                # Try to send a more helpful error message
                if "DATABASE_URL" in error_msg or "psycopg" in error_msg:
                    await update.callback_query.answer("❌ Database connection error. Please contact support.", show_alert=True)
                elif "user" in error_msg.lower():
                    await update.callback_query.answer("❌ User error. Try /start to reinitialize.", show_alert=True)
                else:
                    await update.callback_query.answer(f"❌ Error: {error_msg[:100]}", show_alert=True)
        except Exception as reply_error:
            log.error(f"Failed to send error message to user: {reply_error}")

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    
    user_data = context.user_data
    
    # Handle custom genre input
    if user_data.get("awaiting_custom_genre"):
        user_data["genre"] = text
        user_data.pop("awaiting_custom_genre")
        # Show mood selection
        lang = user_data.get("lang")
        if not lang:
            user = await asyncio.to_thread(get_user, user_id)
            lang = user.get("lang", "en")
            user_data["lang"] = lang
        await update.message.reply_text(
            tr(user_id, "choose_mood").format(text),
            reply_markup=moods_keyboard(lang)
        )
        return
    
    # Handle custom mood input
    if user_data.get("awaiting_custom_mood"):
        user_data["mood"] = text
        user_data.pop("awaiting_custom_mood")
        # Ask for song description
        await update.message.reply_text(
            tr(user_id, "describe_song").format(text)
        )
        return
    
    # If user has selected genre and mood, generate lyrics
    if "genre" in user_data and "mood" in user_data:
        await update.message.reply_text(tr(user_id, "generating"))
        
        try:
            # Get language from context or database
            lang = user_data.get("lang")
            if not lang:
                user = await asyncio.to_thread(get_user, user_id)
                lang = user.get("lang", "en")
                user_data["lang"] = lang  # Store for future use
            
            # Save the topic (user's song description) for later gender analysis
            context.user_data["topic"] = text
            
            # Generate lyrics - language auto-detected from topic text
            lyrics = await openrouter_lyrics(
                text,  # Topic text (language auto-detected from here)
                user_data.get("genre", "Pop"),
                user_data.get("mood", "Happy")
            )
            
            context.user_data["lyrics"] = lyrics
            
            # Show lyrics with generate button
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton(tr(user_id, "generate_button"), callback_data=f"generate:{user_id}")
            ]])
            
            await update.message.reply_text(f"{tr(user_id, 'your_lyrics')}\n\n{lyrics}", reply_markup=kb)
        except Exception as e:
            log.error(f"Lyrics generation error: {e}", exc_info=True)
            await update.message.reply_text(tr(user_id, "error").format(str(e)))
    else:
        # Start the flow
        lang = user_data.get("lang", "en")
        await update.message.reply_text(tr(user_id, "choose_genre_first"), reply_markup=genres_keyboard(lang))

# -------------------------
# FastAPI (Stripe webhook)
# -------------------------
app = FastAPI()

@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    await asyncio.to_thread(init_db)
    log.info("DB ready")
    
    if not PIAPI_API_KEY:
        log.warning("⚠️ PIAPI_API_KEY not set - music generation will not work")
    if not PIAPI_BASE_URL:
        log.warning("⚠️ PIAPI_BASE_URL not set - music generation will not work. Please set PIAPI_BASE_URL environment variable.")
    elif "your-piapi-server.com" in PIAPI_BASE_URL or "example.com" in PIAPI_BASE_URL:
        log.warning(f"⚠️ PIAPI_BASE_URL is set to placeholder value '{PIAPI_BASE_URL}' - please set it to your actual PIAPI server URL")
    elif "/api/v1/task" in PIAPI_BASE_URL:
        log.warning(f"⚠️ PIAPI_BASE_URL should not include the path. Set PIAPI_BASE_URL='https://api.piapi.ai' (without /api/v1/task). Current: {PIAPI_BASE_URL}")
    if not OPENROUTER_API_KEY:
        log.warning("⚠️ OPENROUTER_API_KEY not set - lyrics generation will not work")

@app.get("/stripe/webhook")
async def stripe_webhook_verification():
    """GET endpoint for Stripe webhook verification during setup"""
    return {"status": "ok", "message": "Stripe webhook endpoint is ready"}

@app.get("/webhook/stripe")
async def webhook_stripe_verification():
    """GET endpoint for Stripe webhook verification at alternative path"""
    return {"status": "ok", "message": "Stripe webhook endpoint is ready"}

@app.post("/stripe/webhook")
async def stripe_webhook(request: Request, stripe_signature: str = Header(None)):
    """POST endpoint for Stripe webhook events"""
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
            log.info(f"Added {songs} songs to user {user_id}")
            
            # Notify user about successful payment
            if telegram_app and telegram_app.bot:
                try:
                    balance = await asyncio.to_thread(get_balance, int(user_id))
                    msg = tr(int(user_id), "payment_success").format(songs=songs, balance=balance)
                    await telegram_app.bot.send_message(chat_id=int(user_id), text=msg)
                except Exception as e:
                    log.error(f"Failed to notify user {user_id}: {e}")

    return {"ok": True}

@app.post("/webhook/stripe")
async def webhook_stripe(request: Request, stripe_signature: str = Header(None)):
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
            log.info(f"Added {songs} songs to user {user_id}")
            
            # Notify user about successful payment
            if telegram_app and telegram_app.bot:
                try:
                    balance = await asyncio.to_thread(get_balance, int(user_id))
                    msg = tr(int(user_id), "payment_success").format(songs=songs, balance=balance)
                    await telegram_app.bot.send_message(chat_id=int(user_id), text=msg)
                except Exception as e:
                    log.error(f"Failed to notify user {user_id}: {e}")

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
    telegram_app.add_handler(CommandHandler("menu", cmd_menu))
    telegram_app.add_handler(CommandHandler("language", cmd_language))
    telegram_app.add_handler(CommandHandler("current", cmd_current))
    telegram_app.add_handler(CommandHandler("balance", cmd_balance))
    telegram_app.add_handler(CommandHandler("buy", cmd_buy))
    telegram_app.add_handler(CommandHandler("help", cmd_help))
    telegram_app.add_handler(CallbackQueryHandler(on_callback))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    # Start polling as background task
    async def _run():
        await telegram_app.initialize()
        await telegram_app.start()
        
        # Set bot commands menu (shows in Telegram's "/" menu)
        commands = [
            BotCommand("start", "Start the bot"),
            BotCommand("menu", "Show main menu"),
            BotCommand("language", "Change language"),
            BotCommand("current", "Current song"),
            BotCommand("balance", "Check balance"),
            BotCommand("buy", "Buy credits"),
            BotCommand("help", "Show help"),
        ]
        try:
            await telegram_app.bot.set_my_commands(commands)
            log.info("Bot commands menu set successfully")
        except Exception as e:
            log.warning(f"Failed to set bot commands: {e}")
        
        await telegram_app.updater.start_polling(drop_pending_updates=True)
        log.info("Telegram bot started (polling)")

    asyncio.create_task(_run())

@app.get("/")
async def root():
    return {"status": "ok", "bot": "MusicAI PRO"}

# -------------------------
# Main entry point
# -------------------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
