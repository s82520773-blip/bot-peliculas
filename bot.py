import os
import re
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackQueryHandler

# Variables de entorno
BOT_TOKEN = os.getenv("BOT_TOKEN")
MP_ACCESS = os.getenv("MP_ACCESS")

# Verificar GROUP
group_env = os.getenv("GROUP")
if group_env is None:
    raise ValueError("❌ La variable de entorno GROUP no está definida.")
GROUP_ID = int(group_env)  # Convertir a entero

# Diccionario para películas
peliculas = {}

def clean_text(text):
    return re.sub(r'[^\w\s]', '', text).strip().lower()

# Comando /start
def start(update, context):
    update.message.reply_text(
        "🎬 Bienvenido\n\n¿Que puedo hacer por ti?\nEscribe el nombre de la película que buscas."
    )

# Buscar película
def buscar(update, context):
    texto_usuario = clean_text(update.message.text)
    for titulo in peliculas:
        if titulo in texto_usuario:
            keyboard = [
                [InlineKeyboardButton("💳 Comprar", callback_data=f"comprar|{titulo}")],
                [InlineKeyboardButton("🎬 Ver tráiler", callback_data=f"trailer|{titulo}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            update.message.reply_text(
                f"😀 Disponible\n\n🎬 {titulo.title()}\n💰 Precio $11",
                reply_markup=reply_markup
            )
            return
    update.message.reply_text("😕 No encontré esa película.")

# Detectar película en grupo privado
def detectar_pelicula(update, context):
    if update.message.chat_id == GROUP_ID:
        texto = update.message.text
        if texto:
            lineas = texto.split("\n")
            titulo = clean_text(lineas[0])  # Primera línea solo, sin emojis
            peliculas[titulo] = update.message.message_id
            print("Película registrada:", titulo)

# Manejo de botones
def button_handler(update, context):
    query = update.callback_query
    query.answer()
    data = query.data.split("|")
    accion = data[0]
    titulo = data[1].title()

    if accion == "comprar":
        query.edit_message_text(
            f"💳 Para comprar '{titulo}', el pago será simulado en esta prueba.\n(En producción se conectaría a Mercado Pago)"
        )
    elif accion == "trailer":
        query.edit_message_text(
            f"🎬 Tráiler de '{titulo}': https://www.youtube.com/results?search_query={titulo.replace(' ', '+')}"
        )

def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, buscar))
    dp.add_handler(MessageHandler(Filters.chat(GROUP_ID), detectar_pelicula))
    dp.add_handler(CallbackQueryHandler(button_handler))

    # Start polling (no webhook)
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
