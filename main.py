# -*- coding: utf-8 -*-

import os
import logging
import sys
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
    PreCheckoutQueryHandler
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("MusicAi")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
PIAPI_KEY = os.getenv("PIAPI_KEY")
OWNER_ID = int(os.getenv("OWNER_TG_ID", "0"))

if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN not set")

users = {}
demo_used = set()

PRICES = {
    "1": 250,
    "5": 1000,
    "25": 4000
}

TEXT = {
    "start": "🎵 *MusicAi*\n\nI create songs using AI.\n\nPress START 👇",
    "lang": "Choose language:",
    "theme": "Choose theme:",
    "genre": "Choose genre:",
    "describe": (
        "✍️ *Describe the song*\n\n"
        "- Who is it for?\n"
        "- Story / event\n"
        "- Mood & emotions\n\n"
        "🎤 Or send a voice message"
    ),
    "demo": "🎧 *Demo version (1 time only)*",
    "paid": "✅ Payment successful!\nYou can now generate full songs 🎶",
    "error": "⚠️ Temporary error. Please try again later."
}

async def generate_song(prompt: str):
    url = "https://api.piapi.ai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {PIAPI_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "pi-music",
        "messages": [{"role": "user", "content": prompt}]
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=60) as r:
                data = await r.json()
                return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"PiAPI Error: {e}")
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton("▶️ START", callback_data="start")]]
    await update.message.reply_text(
        TEXT["start"],
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown"
    )

async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

    if q.data == "start":
        users[uid] = {}
        kb = [
            [InlineKeyboardButton("English 🇬🇧", callback_data="lang_en")],
            [InlineKeyboardButton("Polski 🇵🇱", callback_data="lang_pl")],
            [InlineKeyboardButton("Deutsch 🇩🇪", callback_data="lang_de")],
            [InlineKeyboardButton("Español 🇪🇸", callback_data="lang_es")],
            [InlineKeyboardButton("Français 🇫🇷", callback_data="lang_fr")],
            [InlineKeyboardButton("Українська 🇺🇦", callback_data="lang_uk")]
        ]
        await q.edit_message_text(TEXT["lang"], reply_markup=InlineKeyboardMarkup(kb))

    elif q.data.startswith("lang_"):
        users[uid]["lang"] = q.data[5:]
        kb = [
            [InlineKeyboardButton("Love ❤️", callback_data="theme_love")],
            [InlineKeyboardButton("Funny 😄", callback_data="theme_fun")],
            [InlineKeyboardButton("Sad 😢", callback_data="theme_sad")],
            [InlineKeyboardButton("Wedding 💍", callback_data="theme_wedding")],
            [InlineKeyboardButton("Custom ✏️", callback_data="theme_custom")]
        ]
        await q.edit_message_text(TEXT["theme"], reply_markup=InlineKeyboardMarkup(kb))

    elif q.data.startswith("theme_"):
        users[uid]["theme"] = q.data[6:]
        kb = [
            [InlineKeyboardButton("Pop", callback_data="genre_pop")],
            [InlineKeyboardButton("Rap / Hip-Hop", callback_data="genre_rap")],
            [InlineKeyboardButton("Rock", callback_data="genre_rock")],
            [InlineKeyboardButton("Club", callback_data="genre_club")],
            [InlineKeyboardButton("Classical", callback_data="genre_classical")],
            [InlineKeyboardButton("Disco Polo 🇵🇱", callback_data="genre_disco")]
        ]
        await q.edit_message_text(TEXT["genre"], reply_markup=InlineKeyboardMarkup(kb))

    elif q.data.startswith("genre_"):
        users[uid]["genre"] = q.data[6:]
        await q.edit_message_text(TEXT["describe"], parse_mode="Markdown")

    elif q.data.startswith("buy_"):
        pack = q.data.split("_")[1]
        amount = PRICES[pack]

        await context.bot.send_invoice(
            chat_id=uid,
            title=f"MusicAi Pack: {pack} song(s)",
            description="Full AI song generation",
            payload=f"pack_{pack}",
            currency="XTR",
            prices=[LabeledPrice("Stars", amount)]
        )

async def user_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in users or "genre" not in users[uid]:
        await update.message.reply_text("Please press /start first.")
        return

    text = update.message.text or "Voice description received"
    data = users[uid]

    prompt = (
        f"Language: {data['lang']}\n"
        f"Theme: {data['theme']}\n"
        f"Genre: {data['genre']}\n"
        f"Description: {text}"
    )

    if uid not in demo_used:
        demo_used.add(uid)
        msg = await update.message.reply_text("⏳ *Generating your demo...*", parse_mode="Markdown")
        song = await generate_song(prompt)
        if song:
            await msg.edit_text(f"{TEXT['demo']}\n\n{song[:3500]}", parse_mode="Markdown")
        else:
            await msg.edit_text(TEXT["error"])
        return

    kb = [
        [InlineKeyboardButton("⭐ 1 song — 250", callback_data="buy_1")],
        [InlineKeyboardButton("⭐ 5 songs — 1000", callback_data="buy_5")],
        [InlineKeyboardButton("⭐ 25 songs — 4000", callback_data="buy_25")]
    ]
    await update.message.reply_text("💳 Buy full version to continue:", reply_markup=InlineKeyboardMarkup(kb))

async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(TEXT["paid"])
    if OWNER_ID:
        await context.bot.send_message(
            OWNER_ID,
            f"⭐ Payment from @{update.effective_user.username}"
        )

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT | filters.VOICE, user_input))
    app.add_handler(PreCheckoutQueryHandler(pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))

    logger.info("MusicAi started")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()