# -*- coding: utf-8 -*-
import os
import json
import logging
import asyncio
from typing import Dict, Any

import psycopg
from psycopg.rows import dict_row

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    LabeledPrice,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    ConversationHandler,
    filters,
    PreCheckoutQueryHandler,
)

# =========================
# CONFIG & ENV
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
# Для Stars токен провайдера всегда пустой
STARS_PROVIDER_TOKEN = "" 

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger("musicai-bot")

# Цены и паки
PACKS = {
    "pack_1": {"songs": 1, "price": 300, "label": "1 песня"},
    "pack_5": {"songs": 5, "price": 1000, "label": "5 песен"},
    "pack_25": {"songs": 25, "price": 2500, "label": "25 песен"},
}

# Состояния диалога
ST_LANG, ST_MENU, ST_MOOD, ST_GENRE, ST_TOPIC, ST_EDIT_LYRICS = range(6)

# =========================
# DATABASE LOGIC
# =========================
def db_conn():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)

def init_db():
    with db_conn() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            lang TEXT NOT NULL DEFAULT 'ru',
            balance INT NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            pack_id TEXT,
            amount INT,
            currency TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """)
        conn.commit()

def get_user(user_id: int):
    with db_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id=%s", (user_id,)).fetchone()
        if not row:
            conn.execute("INSERT INTO users(user_id) VALUES(%s)", (user_id,))
            conn.commit()
            return {"user_id": user_id, "balance": 0, "lang": "ru"}
        return row

def add_balance(user_id: int, songs: int):
    with db_conn() as conn:
        conn.execute("UPDATE users SET balance = balance + %s WHERE user_id=%s", (songs, user_id))
        conn.commit()

# =========================
# ПРОВЕРКА НА ДВОЙНОЙ ЗАПУСК
# =========================
def check_single_instance():
    lock_file = "bot.lock"
    if os.path.exists(lock_file):
        with open(lock_file, "r") as f:
            old_pid = f.read()
        print(f"ОШИБКА: Бот уже запущен (PID {old_pid}). Завершите старый процесс.")
        exit(1)
    with open(lock_file, "w") as f:
        f.write(str(os.getpid()))

# =========================
# KEYBOARDS
# =========================
def main_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎵 Создать песню", callback_data="menu:create")],
        [InlineKeyboardButton("💳 Купить баланс", callback_data="menu:buy")],
        [InlineKeyboardButton("👤 Профиль", callback_data="menu:profile")],
        [InlineKeyboardButton("ℹ️ Помощь", callback_data="menu:help")],
    ])

def buy_kb():
    buttons = []
    for pid, data in PACKS.items():
        buttons.append([InlineKeyboardButton(f"⭐ {data['label']} — {data['price']} Stars", callback_data=f"buy_stars:{pid}")])
    buttons.append([InlineKeyboardButton("⬅️ Назад", callback_data="menu:home")])
    return InlineKeyboardMarkup(buttons)

# =========================
# HANDLERS
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    await update.message.reply_text(
        "👋 Добро пожаловать в MusicAI!\nЯ помогу тебе создать хит с помощью нейросетей.",
        reply_markup=main_menu_kb()
    )
    return ST_MENU

async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    help_text = (
        "<b>📖 Как пользоваться MusicAI:</b>\n\n"
        "1. Нажмите <b>Создать песню</b>.\n"
        "2. Следуйте инструкциям (выбор жанра, настроения).\n"
        "3. Введите тему (о чем петь).\n"
        "4. Получите текст от ИИ и подтвердите запуск.\n\n"
        "<b>💳 Оплата:</b> Мы принимаем Telegram Stars. Баланс пополняется мгновенно.\n"
        "<b>⚠️ Важно:</b> Одна генерация занимает около 2 минут."
    )
    await query.message.edit_text(help_text, parse_mode=ParseMode.HTML, 
                                 reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Меню", callback_data="menu:home")]]))

async def profile_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = get_user(update.effective_user.id)
    text = (
        f"<b>👤 Ваш профиль</b>\n\n"
        f"🆔 ID: <code>{user['user_id']}</code>\n"
        f"🎵 Баланс: <b>{user['balance']} песен</b>"
    )
    await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=main_menu_kb())

# --- Блок платежей ---
async def send_stars_invoice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    pack_id = query.data.split(":")[1]
    pack = PACKS.get(pack_id)
    
    await context.bot.send_invoice(
        chat_id=update.effective_chat.id,
        title=f"Пополнение баланса: {pack['label']}",
        description=f"Доступ к генерации {pack['songs']} композиций в MusicAI",
        payload=f"stars_pay:{pack_id}",
        provider_token=STARS_PROVIDER_TOKEN,
        currency="XTR",
        prices=[LabeledPrice("Цена", pack['price'])]
    )
    await query.answer()

async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    await query.answer(ok=True)

async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payment = update.message.successful_payment
    payload = payment.invoice_payload
    pack_id = payload.split(":")[1]
    songs_to_add = PACKS[pack_id]["songs"]
    
    user_id = update.effective_user.id
    add_balance(user_id, songs_to_add)
    
    await update.message.reply_text(
        f"✅ Успешно! Вам начислено {songs_to_add} песен.\nПриступайте к творчеству!",
        reply_markup=main_menu_kb()
    )

# =========================
# MAIN ENTRY POINT
# =========================
def main():
    check_single_instance() # ТЗ: Проверка на один запуск
    init_db()
    
    application = Application.builder().token(BOT_TOKEN).build()

    # Хэндлеры платежей
    application.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))

    # Основной диалог
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ST_MENU: [
                CallbackQueryHandler(help_handler, pattern="^menu:help$"),
                CallbackQueryHandler(profile_handler, pattern="^menu:profile$"),
                CallbackQueryHandler(lambda u, c: u.callback_query.message.edit_text("Выберите пакет:", reply_markup=buy_kb()), pattern="^menu:buy$"),
                CallbackQueryHandler(start, pattern="^menu:home$"), # Возврат в меню
                CallbackQueryHandler(send_stars_invoice, pattern="^buy_stars:"),
            ],
            # Здесь можно добавить логику генерации (MOOD -> GENRE и т.д.)
        },
        fallbacks=[CommandHandler("start", start)],
    )

    application.add_handler(conv_handler)

    print("Бот запущен...")
    try:
        application.run_polling()
    finally:
        if os.path.exists("bot.lock"):
            os.remove("bot.lock")

if __name__ == "__main__":
    main()
