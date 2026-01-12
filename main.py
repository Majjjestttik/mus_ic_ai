# -*- coding: utf-8 -*-
import os
import logging
import sys
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters
)

# 1. Настройка логирования для консоли Render
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# 2. Получение токена
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    logger.error("ОШИБКА: Переменная TELEGRAM_BOT_TOKEN не задана в настройках Render!")
    sys.exit(1)

# --- Логика бота ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет приветственное сообщение с кнопкой."""
    text = (
        "🎵 *Welcome to MusicAi*\n\n"
        "In just *5 minutes* I can create a *full song* for you:\n"
        "lyrics, style and mood — all personalized.\n\n"
        "👇 Press *START* to begin"
    )
    keyboard = [[InlineKeyboardButton("▶️ START", callback_data="start_flow")]]
    
    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def button_tap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатия на кнопку START."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "start_flow":
        await query.edit_message_text(
            "🎸 Excellent! Now, please **type the genre** or **mood** for your song (e.g., Jazz, Techno, Sad Rock).",
            parse_mode="Markdown"
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений от пользователя."""
    user_text = update.message.text
    await update.message.reply_text(f"Working on your {user_text} song... ⏳ (Coming soon!)")

# --- Запуск ---

def main():
    try:
        # Создаем приложение
        app = ApplicationBuilder().token(TOKEN).build()

        # Добавляем обработчики
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CallbackQueryHandler(button_tap))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        logger.info("--- Бот MusicAi запущен в режиме Background Worker ---")
        
        # Запуск цикла опроса (polling)
        # drop_pending_updates=True помогает избежать "шквала" старых сообщений при перезапуске
        app.run_polling(drop_pending_updates=True)

    except Exception as e:
        logger.error(f"Критическая ошибка при запуске: {e}")

if __name__ == "__main__":
    main()

