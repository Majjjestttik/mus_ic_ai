# -*- coding: utf-8 -*-

import os
import logging
import sys
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)
from openai import AsyncOpenAI
from openai import OpenAIError

# -------------------- ЛОГИ --------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("MusicAi")

# -------------------- ENV --------------------
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PIAPI_KEY = os.getenv("PIAPI_KEY")  # для музыки (пока не используется)
OWNER_ID = int(os.getenv("OWNER_TG_ID", "0"))

if not BOT_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN не установлен.")
    sys.exit("TELEGRAM_BOT_TOKEN не установлен.")
if not OPENAI_API_KEY:
    logger.error("OPENAI_API_KEY не установлен.")
    sys.exit("OPENAI_API_KEY не установлен.")

# -------------------- ИНИЦИАЛИЗАЦИЯ --------------------
client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# Структура для хранения данных пользователей.
# В реальном приложении лучше использовать базу данных.
# Пример: users[user_id] = {"language": "ru", "balance": 0}
users = {}

# Множество для отслеживания использованных демо-запросов, если планируется такая функция.
demo_used = set()

# -------------------- ЛОКАЛИЗАЦИЯ --------------------
TEXT = {
    "start": {
        "en": "🎵 *MusicAi*\n\nI create full songs in minutes.\nPress START 👇",
        "ru": "🎵 *MusicAi*\n\nСоздаю полноценные песни за минуты.\nНажми START 👇",
        "pl": "🎵 *MusicAi*\n\nTworzę pełne piosenki w kilka minut.\nNaciśnij START 👇",
    },
    "welcome_language_choice": {
        "en": "Please choose your language:",
        "ru": "Пожалуйста, выберите ваш язык:",
        "pl": "Proszę wybrać język:",
    },
    "language_selected": {
        "en": "Language set to English.",
        "ru": "Язык установлен на русский.",
        "pl": "Język ustawiony na polski.",
    },
    "help_message": {
        "en": "Here is a list of commands:\n"
              "/start - Start the bot and choose language\n"
              "/help - Show this help message\n"
              "/balance - Check your remaining requests\n"
              "Send me a text prompt to generate music!",
        "ru": "Вот список команд:\n"
              "/start - Запустить бота и выбрать язык\n"
              "/help - Показать это сообщение справки\n"
              "/balance - Проверить оставшиеся запросы\n"
              "Отправьте мне текстовый запрос для генерации музыки!",
        "pl": "Oto lista komend:\n"
              "/start - Uruchom bota i wybierz język\n"
              "/help - Pokaż tę pomoc\n"
              "/balance - Sprawdź pozostałe zapytania\n"
              "Wyślij mi tekst, aby wygenerować muzykę!",
    },
    "balance_info": {
        "en": "You have {balance} requests remaining.",
        "ru": "У вас осталось {balance} запросов.",
        "pl": "Pozostało Ci {balance} zapytań.",
    },
    "error_openai": {
        "en": "An error occurred while generating music with OpenAI. Please try again later.",
        "ru": "Произошла ошибка при генерации музыки через OpenAI. Попробуйте позже.",
        "pl": "Wystąpił błąd podczas generowania muzyki przez OpenAI. Spróbuj ponownie później.",
    },
    "error_generic": {
        "en": "An unexpected error occurred. Please contact the administrator.",
        "ru": "Произошла непредвиденная ошибка. Пожалуйста, свяжитесь с администратором.",
        "pl": "Wystąpił nieoczekiwany błąd. Prosimy o kontakt z administratorem.",
    },
    "generating_music": {
        "en": "Generating music based on your request... This may take a moment.",
        "ru": "Генерируем музыку по вашему запросу... Это может занять некоторое время.",
        "pl": "Generowanie muzyki na podstawie Twojego zapytania... Może to chwilę potrwać.",
    },
    "insufficient_balance": {
        "en": "You don't have enough requests. Please purchase more.",
        "ru": "У вас недостаточно запросов. Пожалуйста, купите еще.",
        "pl": "Masz za mało zapytań. Kup więcej.",
    }
}

# --- Функции для работы с пользователями ---

def get_user_language(user_id: int) -> str:
    """Получает язык пользователя, возвращает 'en' по умолчанию, если не установлен."""
    return users.get(user_id, {}).get("language", "en")

def get_user_balance(user_id: int) -> int:
    """Получает баланс пользователя, возвращает 0 по умолчанию."""
    return users.get(user_id, {}).get("balance", 0)

def update_user_balance(user_id: int, amount: int):
    """Обновляет баланс пользователя."""
    if user_id not in users:
        users[user_id] = {"language": "en", "balance": 0} # Создаем запись, если пользователь новый
    users[user_id]["balance"] = max(0, users[user_id]["balance"] + amount) # Баланс не может быть отрицательным

# --- Обработчики команд ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает команду /start."""
    user_id = update.effective_user.id
    if user_id not in users:
        # Инициализация нового пользователя
        users[user_id] = {"language": "en", "balance": 0} # Язык по умолчанию "en", баланс 0

    # Создаем кнопки для выбора языка
    keyboard = [
        [
            InlineKeyboardButton("English", callback_data="lang_en"),
            InlineKeyboardButton("Русский", callback_data="lang_ru"),
            InlineKeyboardButton("Polski", callback_data="lang_pl"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    lang = get_user_language(user_id)
    await update.message.reply_text(TEXT["welcome_language_choice"][lang], reply_markup=reply_markup)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает команду /help."""
    user_id = update.effective_user.id
    lang = get_user_language(user_id)
    await update.message.reply_text(TEXT["help_message"][lang], parse_mode='Markdown')

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает команду /balance."""
    user_id = update.effective_user.id
    lang = get_user_language(user_id)
    balance = get_user_balance(user_id)
    await update.message.reply_text(TEXT["balance_info"][lang].format(balance=balance), parse_mode='Markdown')

# --- Обработчики callback-запросов ---

async def language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает выбор языка."""
    query = update.callback_query
    await query.answer() # Отвечаем на callback, чтобы кнопка перестала "вращаться"

    user_id = query.from_user.id
    lang_code = query.data.split("_")[1] # Ожидаем "lang_en", "lang_ru" и т.д.

    if lang_code in ["en", "ru", "pl"]:
        users[user_id]["language"] = lang_code
        lang = get_user_language(user_id) # Получаем обновленный язык
        await query.edit_message_text(text=TEXT["language_selected"][lang])
        # После выбора языка можно показать главное меню или команды
        await help_command(update, context) # Покажем помощь после выбора языка
    else:
        lang = get_user_language(user_id)
        await query.edit_message_text(text=TEXT["error_generic"][lang]) # Общая ошибка, если код языка некорректен

# --- Обработчики сообщений ---

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает текстовые сообщения пользователя (запросы на музыку)."""
    user_id = update.effective_user.id
    lang = get_user_language(user_id)
    text_prompt = update.message.text

    # Проверяем баланс перед генерацией
    if get_user_balance(user_id) <= 0:
        await update.message.reply_text(TEXT["insufficient_balance"][lang], parse_mode='Markdown')
        return

    # Снижаем баланс на 1 запрос
    update_user_balance(user_id, -1)

    # Отправляем сообщение о начале генерации
    await update.message.reply_text(TEXT["generating_music"][lang])

    # --- Здесь должна быть логика вызова OpenAI API для генерации музыки ---
    # Этот блок — заглушка. Вам нужно будет интегрировать реальный вызов API.
    try:
        await logger.info(f"User {user_id} requested music generation with prompt: '{text_prompt}'")

        # TODO: Замените этот блок на реальный вызов OpenAI API для генерации музыки.
        # Вам нужно будет найти подходящий эндпоинт OpenAI или использовать сторонние сервисы,
        # если OpenAI не предоставляет прямого API для генерации музыки по тексту.
        # Если есть API, которое возвращает аудиофайл или ссылку:
        # response = await client.audio.create_music(...)
        # audio_file_url = response.url # или как-то так

        # Пока что просто отправляем подтверждение
        await update.message.reply_text(f"✅ Музыка сгенерирована по запросу: '{text_prompt}' (имитация). У вас осталось {get_user_balance(user_id)} запросов.")

    except OpenAIError as e:
        logger.error(f"OpenAI API error for user {user_id}: {e}")
        await update.message.reply_text(TEXT["error_openai"][lang])
    except Exception as e:
        logger.error(f"Unexpected error during music generation for user {user_id}: {e}")
        await update.message.reply_text(TEXT["error_generic"][lang])
    # --- Конец блока вызова OpenAI API ---


# --- Главная функция запуска бота ---

def main() -> None:
    """Запускает бота."""
    # Создаем ApplicationBuilder
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("balance", balance_command))

    # Обработчик для выбора языка
    application.add_handler(CallbackQueryHandler(language_callback, pattern="^lang_"))

    # Обработчик для текстовых сообщений (генерация музыки)
    # Важно: ~filters.COMMAND означает "не команды"
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Запускаем бота
    logger.info("Bot started polling.")
    application.run_polling()

if __name__ == "__main__":
    main()