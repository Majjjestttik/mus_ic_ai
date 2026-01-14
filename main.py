# -*- coding: utf-8 -*-
"""
MusicAi PRO (Telegram bot) + Free Version
Updated: Removed payments; Added 'Generate Song' button and Suno Music API integration.
"""

import os
import re
import json
import time
import asyncio
import logging
import sqlite3
from dataclasses import dataclass
from typing import Dict, Any, Tuple, List

import aiohttp
from dotenv import load_dotenv
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# =========================
# ENV
# =========================
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()

if not TELEGRAM_TOKEN:
    raise RuntimeError("❌ TELEGRAM_TOKEN is missing.")

# =========================
# LOGGING
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("MusicAiPRO")


# =========================
# CALLBACKS
# =========================
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    user_ensure(user_id)
    u = user_get(user_id)
    data = query.data or ""

    # User clicked 'Generate Song'
    if data == "generate_song":
        await query.message.reply_text("⏳ Генерирую трек по этим текстам...")
        async with aiohttp.ClientSession() as session:
            try:
                songs_payload = [{"text": history_last(user_id, 1)[0]["response"]}]
                async with session.post("https://suno-music-api-endpoint", json={"songs": songs_payload}) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        for track in result.get("tracks", []):
                            await query.message.reply_audio(track["audio_url"])
                    else:
                        await query.message.reply_text("❌ Error: Suno API недоступен.")
            except Exception as e:
                await query.message.reply_text(f"❌ Ошибка генерации: {e}")
        return


# =========================
# GENERATION HANDLER
# =========================
async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_ensure(user_id)
    u = user_get(user_id)

    text = normalize_user_text(update.message.text or "")
    if not text:
        await update.message.reply_text(tr(u, "need_topic"), reply_markup=kb_main(u))
        return

    await update.message.reply_text(tr(u, "busy"))

    system_prompt = build_system_prompt(u)
    user_prompt = build_user_prompt(u, text)

    async with aiohttp.ClientSession() as session:
        res = await llm_chat(session, system_prompt, user_prompt)

    if not res.ok:
        await update.message.reply_text(f"{tr(u, 'gen_error')} Debug: {res.text}", reply_markup=kb_main(u))
        return

    out = (res.text or "").strip()
    history_add(user_id, text, out)

    for part in split_text(out, MAX_TG_MESSAGE):
        await update.message.reply_text(part)

    # Add 'Generate Song' button below the generated song text
    await update.message.reply_text(
        "🎵 Хотите сгенерировать трек по этим текстам?",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("🎤 Сгенерировать песню", callback_data="generate_song")]]
        ),
    )