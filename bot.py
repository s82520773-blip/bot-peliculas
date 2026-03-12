import os
import re
import json
import uuid
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackQueryHandler, CallbackContext

# ========================
# VARIABLES DE ENTORNO
# ========================

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_ID = int(os.getenv("GROUP"))
ADMIN_ID = int(os.getenv("ADMIN_ID"))

PRICE = float(os.getenv("MOVIE_PRICE", "11"))
CURRENCY = os.getenv("CURRENCY_ID", "MXN")

BANK_NAME = os.getenv("BANK_NAME")
BANK_OWNER = os.getenv("BANK_OWNER")
BANK_CLABE = os.getenv("BANK_CLABE")
BANK_CARD = os.getenv("BANK_CARD")
BANK_NOTE = os.getenv("BANK_NOTE")

CATALOG_FILE = "peliculas.json"
REQUEST_FILE = "solicitudes.json"
ORDERS_FILE = "ordenes.json"

logging.basicConfig(level=logging.INFO)

# ========================
# UTILIDADES JSON
# ========================

def load_json(file):
    if not os.path.exists(file):
        return {}
    with open(file, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


peliculas = load_json(CATALOG_FILE)
solicitudes = load_json(REQUEST_FILE)
ordenes = load_json(ORDERS_FILE)

# ========================
# LIMPIAR TEXTO
# ========================

def clean(text):
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", "", text)
    return text


# ========================
# START
# ========================

def start(update: Update, context: CallbackContext):

    update.message.reply_text(
        "🎬 Bienvenido\n\n"
        "Escribe el nombre de la película que buscas."
    )


# ========================
# BUSCAR PELÍCULA
# ========================

def buscar(update: Update, context: CallbackContext):

    if update.message.chat.type != "private":
        return

    texto = clean(update.message.text)

    for titulo in peliculas:

        if texto in titulo or titulo in texto:

            keyboard = [

                [InlineKeyboardButton("💸 Transferencia", callback_data=f"transfer|{titulo}")],
                [InlineKeyboardButton("🏦 Datos bancarios", callback_data=f"bank|{titulo}")],
                [InlineKeyboardButton("🎬 Ver tráiler", callback_data=f"trailer|{titulo}")]

            ]

            update.message.reply_text(

                f"😀 Disponible\n\n"
                f"🎬 {titulo.title()}\n"
                f"💰 Precio ${PRICE}",

                reply_markup=InlineKeyboardMarkup(keyboard)

            )

            return

    keyboard = [
        [InlineKeyboardButton("📩 Solicitar película", callback_data=f"request|{texto}")]
    ]

    update.message.reply_text(

        "😕 No encontré esa película\n\n¿Quieres que la consiga?",

        reply_markup=InlineKeyboardMarkup(keyboard)

    )


# ========================
# BOTONES
# ========================

def buttons(update: Update, context: CallbackContext):

    query = update.callback_query
    query.answer()

    data = query.data.split("|")

    action = data[0]
    titulo = data[1]

    # ========================
    # TRANSFERENCIA
    # ========================

    if action == "transfer":

        ref = str(uuid.uuid4())[:6].upper()

        ordenes[ref] = {

            "user": query.from_user.id,
            "movie": titulo,
            "status": "pending"

        }

        save_json(ORDERS_FILE, ordenes)

        keyboard = [
            [InlineKeyboardButton("📋 Copiar referencia", callback_data="copy")],
            [InlineKeyboardButton("✅ Ya transferí", callback_data=f"paid|{ref}")]
        ]

        query.edit_message_text(

            f"💸 Transferencia bancaria\n\n"
            f"Banco: {BANK_NAME}\n"
            f"Beneficiario: {BANK_OWNER}\n\n"
            f"CLABE:\n{BANK_CLABE}\n\n"
            f"Monto:\n${PRICE} {CURRENCY}\n\n"
            f"Referencia única:\n{ref}\n\n"
            f"⚠️ Usa la referencia en el concepto de pago.\n"
            f"{BANK_NOTE}",

            reply_markup=InlineKeyboardMarkup(keyboard)

        )

    # ========================
    # DATOS BANCARIOS
    # ========================

    if action == "bank":

        query.edit_message_text(

            f"🏦 Datos bancarios\n\n"
            f"Banco: {BANK_NAME}\n"
            f"Beneficiario: {BANK_OWNER}\n"
            f"CLABE: {BANK_CLABE}\n\n"
            f"{BANK_NOTE}"

        )

    # ========================
    # TRAILER
    # ========================

    if action == "trailer":

        url = f"https://youtube.com/results?search_query={titulo.replace(' ','+')}+trailer"

        query.edit_message_text(

            f"🎬 Tráiler:\n{url}"

        )

    # ========================
    # SOLICITAR PELÍCULA
    # ========================

    if action == "request":

        solicitudes[titulo] = {

            "user": query.from_user.id

        }

        save_json(REQUEST_FILE, solicitudes)

        context.bot.send_message(

            ADMIN_ID,

            f"📩 Nueva solicitud de película\n\n"
            f"🎬 {titulo}\n"
            f"👤 Usuario: {query.from_user.first_name}\n"
            f"🆔 ID: {query.from_user.id}"

        )

        query.edit_message_text(

            "✅ Tu solicitud fue enviada.\n\n"
            "Te avisaré cuando esté disponible."

        )

    # ========================
    # CONFIRMAR TRANSFERENCIA
    # ========================

    if action == "paid":

        ref = titulo

        if ref not in ordenes:

            query.edit_message_text("❌ Referencia inválida")
            return

        orden = ordenes[ref]

        movie = orden["movie"]

        message_id = peliculas.get(movie)

        context.bot.send_message(

            orden["user"],

            f"✅ Pago recibido\n\n"
            f"🎬 {movie.title()}\n"
            f"Enviando película..."

        )

        context.bot.copy_message(

            chat_id=orden["user"],
            from_chat_id=GROUP_ID,
            message_id=message_id

        )

        orden["status"] = "completed"

        save_json(ORDERS_FILE, ordenes)

        query.edit_message_text("✅ Película enviada")


# ========================
# DETECTAR NUEVA PELÍCULA
# ========================

def detectar(update: Update, context: CallbackContext):

    if update.message.chat_id != GROUP_ID:
        return

    texto = update.message.caption or update.message.text

    if not texto:
        return

    titulo = clean(texto.split("\n")[0])

    peliculas[titulo] = update.message.message_id

    save_json(CATALOG_FILE, peliculas)

    logging.info(f"Película registrada: {titulo}")


# ========================
# MAIN
# ========================

def main():

    updater = Updater(BOT_TOKEN, use_context=True)

    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))

    dp.add_handler(MessageHandler(Filters.text & Filters.private, buscar))

    dp.add_handler(MessageHandler(Filters.chat(GROUP_ID), detectar))

    dp.add_handler(CallbackQueryHandler(buttons))

    updater.start_polling()

    updater.idle()


if __name__ == "__main__":
    main()
