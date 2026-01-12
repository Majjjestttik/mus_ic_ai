# -*- coding: utf-8 -*-

import os
import logging
import sys
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
    PreCheckoutQueryHandler
)
from openai import AsyncOpenAI

# ---------------- LOGS ----------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("MusicAi")

# ---------------- ENV ----------------
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
OWNER_ID = int(os.getenv("OWNER_TG_ID", "0"))

if not BOT_TOKEN or not OPENAI_KEY:
    raise RuntimeError("ENV variables missing")

openai_client = AsyncOpenAI(api_key=OPENAI_KEY)

# ---------------- STATE ----------------
users = {}
demo_used = set()

# ---------------- STARS PRICES ----------------
PRICES = {
    "1": 250,
    "5": 1000,
    "25": 4000
}

# ---------------- TEXTS ----------------
TEXT = {
    "start": "🎵 *MusicAi*\n\nI create song lyrics using AI.\n\nPress START 👇",
    "lang": "🌍 Choose language:",
    "theme": "🎯 Choose theme:",
    "genre": "🎼 Choose genre:",
    "describe": (
        "✍️ *Describe the song*\n\n"
        "• Who is it for?\n"
        "• Story / event\n"
        "• Mood & emotions\n\n"
        "🎤 Or just write freely"
    ),
    "demo": "🎧 *Demo version (1 time only)*",
    "buy_confirm": (
        "⚠️ *Confirmation*\n\n"
        "You will spend ⭐ {stars}\n"
        "No refunds.\n\n"
        "Continue?"
    ),
    "paid": "✅ Payment successful!\nYou can continue 🎶",
    "error": "⚠️ Temporary error. Try later."
}

# ---------------- OPENAI ----------------
async def generate_text(prompt: str):
    try:
        r = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=700
        )
        return r.choices[0].message.content
    except Exception as e:
        logger.error(e)
        return None

# ---------------- /start ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton("▶️ START", callback_data="start")]]
    await update.message.reply_text(
        TEXT["start"],
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown"
    )

# ---------------- BUTTONS ----------------
async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

    if q.data == "start":
        users[uid] = {}
        kb = [
            [InlineKeyboardButton("English 🇬🇧", callback_data="lang_en")],
            [InlineKeyboardButton("Deutsch 🇩🇪", callback_data="lang_de")],
            [InlineKeyboardButton("Español 🇪🇸", callback_data="lang_es")],
            [InlineKeyboardButton("Français 🇫🇷", callback_data="lang_fr")],
            [InlineKeyboardButton("Polski 🇵🇱", callback_data="lang_pl")],
            [InlineKeyboardButton("Українська 🇺🇦", callback_data="lang_uk")]
        ]
        await q.edit_message_text(TEXT["lang"], reply_markup=InlineKeyboardMarkup(kb))

    elif q.data.startswith("lang_"):
        users.setdefault(uid, {})["lang"] = q.data[5:]
        kb = [
            [InlineKeyboardButton("Love ❤️", callback_data="theme_love")],
            [InlineKeyboardButton("Funny 😄", callback_data="theme_fun")],
            [InlineKeyboardButton("Sad 😢", callback_data="theme_sad")],
            [InlineKeyboardButton("Wedding 💍", callback_data="theme_wedding")],
            [InlineKeyboardButton("Custom ✏️", callback_data="theme_custom")]
        ]
        await q.edit_message_text(TEXT["theme"], reply_markup=InlineKeyboardMarkup(kb))

    elif q.data.startswith("theme_"):
        users.setdefault(uid, {})["theme"] = q.data[6:]
        kb = [
            [InlineKeyboardButton("Pop", callback_data="genre_pop")],
            [InlineKeyboardButton("Rap / Hip-Hop", callback_data="genre_rap")],
            [InlineKeyboardButton("Rock", callback_data="genre_rock")],
            [InlineKeyboardButton("Club", callback_data="genre_club")],
            [InlineKeyboardButton("Classical", callback_data="genre_classical")],
            [InlineKeyboardButton("Disco Polo", callback_data="genre_disco")]
        ]
        await q.edit_message_text(TEXT["genre"], reply_markup=InlineKeyboardMarkup(kb))

    elif q.data.startswith("genre_"):
        users.setdefault(uid, {})["genre"] = q.data[6:]
        await q.edit_message_text(TEXT["describe"], parse_mode="Markdown")

    elif q.data.startswith("buy_"):
        pack = q.data.split("_")[1]
        stars = PRICES[pack]
        users[uid]["buy"] = pack
        kb = [[
            InlineKeyboardButton("✅ Yes", callback_data=f"pay_{pack}"),
            InlineKeyboardButton("❌ No", callback_data="cancel")
        ]]
        await q.edit_message_text(
            TEXT["buy_confirm"].format(stars=stars),
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode="Markdown"
        )

    elif q.data.startswith("pay_"):
        pack = q.data.split("_")[1]
        await context.bot.send_invoice(
            chat_id=uid,
            title="MusicAi Songs",
            description="AI generated song lyrics",
            payload=f"songs_{pack}",
            currency="XTR",
            prices=[LabeledPrice("Stars", PRICES[pack])]
        )

    elif q.data == "cancel":
        await q.edit_message_text("❌ Cancelled. Use /start")

# ---------------- TEXT INPUT ----------------
async def user_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in users or "genre" not in users[uid]:
        await update.message.reply_text("Use /start")
        return

    data = users[uid]
    prompt = (
        f"Language: {data['lang']}\n"
        f"Theme: {data['theme']}\n"
        f"Genre: {data['genre']}\n"
        f"Text: {update.message.text}"
    )

    if uid not in demo_used:
        demo_used.add(uid)
        msg = await update.message.reply_text("⏳ Generating demo...")
        text = await generate_text(prompt)
        if text:
            await msg.edit_text(f"{TEXT['demo']}\n\n{text[:3500]}", parse_mode="Markdown")
        else:
            await msg.edit_text(TEXT["error"])
        return

    kb = [
        [InlineKeyboardButton("⭐ 1 song — 250", callback_data="buy_1")],
        [InlineKeyboardButton("⭐ 5 songs — 1000", callback_data="buy_5")],
        [InlineKeyboardButton("⭐ 25 songs — 4000", callback_data="buy_25")]
    ]
    await update.message.reply_text("💳 Buy to continue:", reply_markup=InlineKeyboardMarkup(kb))

# ---------------- PAYMENTS ----------------
async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(TEXT["paid"])
    if OWNER_ID:
        await context.bot.send_message(
            OWNER_ID,
            f"⭐ Payment from @{update.effective_user.username}"
        )

# ---------------- MAIN ----------------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, user_text))
    app.add_handler(PreCheckoutQueryHandler(pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))

    logger.info("MusicAi RUNNING")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()