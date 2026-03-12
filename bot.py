import os
import re
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters

# Variables de entorno
TOKEN = os.getenv("BOT_TOKEN")
GROUP_ID = int(os.getenv("GROUP_ID"))

# Diccionario para guardar películas
# Clave: título limpio en minúsculas, Valor: message_id en el grupo privado
peliculas = {}

# Función para limpiar texto (quitar emojis, símbolos y pasar a minúsculas)
def clean_text(text):
    return re.sub(r'[^\w\s]', '', text).strip().lower()

# Comando /start
def start(update, context):
    update.message.reply_text(
        "🎬 Bienvenido\n\n¿Que puedo hacer por ti?\n\nEscribe el nombre de la película que buscas."
    )

# Función de búsqueda de películas
def buscar(update, context):
    texto_usuario = clean_text(update.message.text)

    for titulo in peliculas:
        if titulo in texto_usuario:
            update.message.reply_text(
                f"😀 Disponible\n\n🎬 {titulo.title()}\n\n💰 Precio $11\n\nEscribe COMPRAR para adquirirla."
            )
            return

    update.message.reply_text("😕 No encontré esa película.")

# Función para detectar nuevas películas en el grupo privado
def detectar_pelicula(update, context):
    if update.message.chat_id == GROUP_ID:
        texto = update.message.text
        if texto and "🎬" in texto:
            # Limpiamos el título y lo guardamos
            titulo = clean_text(texto.replace("🎬", ""))
            peliculas[titulo] = update.message.message_id
            print("Película registrada:", titulo)

# Función principal
def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    # Handlers
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, buscar))
    dp.add_handler(MessageHandler(Filters.chat(GROUP_ID), detectar_pelicula))

    # Inicia el bot
    updater.start_polling()
    updater.idle()

# Ejecutar
if __name__ == "__main__":
    main()
