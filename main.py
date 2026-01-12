# -*- coding: utf-8 -*-

import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

# логирование (Render любит это)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# берём токен ТОЛЬКО из Environment Variables
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN not set")


# ===== /start =====
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


# ===== main =====
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    logging.info("MusicAi bot started")
    app.run_polling()


if __name__ == "__main__":
    main()