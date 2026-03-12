import os
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters

TOKEN = os.getenv("BOT_TOKEN")
GROUP_ID = int(os.getenv("GROUP_ID"))

peliculas = {}

def start(update, context):
    update.message.reply_text(
        "🎬 Bienvenido\n\nEscribe el nombre de la película que buscas."
    )

def buscar(update, context):
    texto = update.message.text.lower()

    for titulo in peliculas:
        if titulo in texto:
            update.message.reply_text(
                f"😀 Disponible\n\n🎬 {titulo}\n\n💰 Precio $11\n\nEscribe COMPRAR para adquirirla."
            )
            return

    update.message.reply_text("😕 No encontré esa película.")

def detectar_pelicula(update, context):

    if update.message.chat_id == GROUP_ID:

        texto = update.message.text

        if texto and "🎬" in texto:

            titulo = texto.replace("🎬", "").strip().lower()

            peliculas[titulo] = update.message.message_id

            print("Película registrada:", titulo)

def main():

    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))

    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, buscar))

    dp.add_handler(MessageHandler(Filters.chat(GROUP_ID), detectar_pelicula))

    updater.start_polling()
    updater.idle()

main()
