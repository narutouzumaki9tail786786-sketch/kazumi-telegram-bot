from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler
from kazumi.config import TOKEN

async def start(update: Update, context):
    await update.message.reply_text("Hello! Minimal bot is working!")

if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN is missing")
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    print("Minimal bot starting...")
    app.run_polling()
