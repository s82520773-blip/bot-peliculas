import os
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters

TOKEN = os.getenv("BOT_TOKEN")

def start(update, context):
    update.message.reply_text(
        "🎬 Bienvenido\n\n¿Que puedo hacer por ti?\n\nEscribe el nombre de la película que buscas."
    )

def buscar(update, context):
    texto = update.message.text.lower()

    if "gigantes" in texto:
        update.message.reply_text(
            "😀 Disponible\n\n🎬 Gigantes de acero\n📅 2011\n🎥 1080p\n\n💰 Precio $11"
        )
    else:
        update.message.reply_text("😕 No encontré esa película.")

def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.text, buscar))

    updater.start_polling()
    updater.idle()

main()
