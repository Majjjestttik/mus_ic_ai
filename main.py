# -*- coding: utf-8 -*-

import os
import logging
import asyncio
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
)

# 1. Логирование
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
PORT = int(os.environ.get("PORT", 8080)) # Порт, который дает Render

if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN not set")

# --- ФЕЙКОВЫЙ СЕРВЕР ДЛЯ RENDER ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive")

def run_health_check():
    server = HTTPServer(('0.0.0.0', PORT), HealthCheckHandler)
    server.serve_forever()

# --- ОБРАБОТЧИКИ КОМАНД ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🎵 Welcome to *MusicAi*\n\n"
        "In just *5 minutes* I can create a *full song* for you:\n"
        "lyrics, style and mood — all personalized.\n\n"
        "👇 Press *START* to begin"
    )

    keyboard = [
        [InlineKeyboardButton("▶️ START", callback_data="start_flow")]
    ]

    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "start_flow":
        await query.edit_message_text(
            "🎸 Awesome! Please send me the **Genre** or **Mood** of your song (e.g., Rock, Lo-fi, Sad, Happy).",
            parse_mode="Markdown"
        )

# --- ЗАПУСК ---

def main():
    # Запускаем веб-сервер в отдельном потоке, чтобы Render не убил бота
    thread = Thread(target=run_health_check, daemon=True)
    thread.start()

    # Собираем приложение бота
    app = ApplicationBuilder().token(TOKEN).build()

    # Регистрируем обработчики
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))

    logging.info(f"MusicAi bot started. Health check on port {PORT}")
    
    # Запуск бота (polling)
    app.run_polling()

if __name__ == "__main__":
    main()
