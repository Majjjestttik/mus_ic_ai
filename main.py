# -*- coding: utf-8 -*-
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

TOKEN = &quot;8428388107:AAHwETVemOZ78SJGomvMUaurlBgU6ozbDdE&quot;

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        &quot;🎵 MusicAinn&quot;
        &quot;This bot creates a full song in 5 minutes.n&quot;
        &quot;Press Start and let's begin 🎶&quot;
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    await update.message.reply_text(
        f&quot;📝 Song draft based on your idea:nn{text}nn(Demo version)&quot;
    )

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler(&quot;start&quot;, start))
app.add_handler(MessageHandler(filters.TEXT &amp; ~filters.COMMAND, handle_text))


app.run_polling()
