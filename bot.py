import os
import re
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    CallbackQueryHandler,
    CallbackContext,
)

# =======================
# CONFIG
# =======================
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_ENV = os.getenv("GROUP")

if not BOT_TOKEN:
    raise ValueError("Falta la variable de entorno BOT_TOKEN")

if not GROUP_ENV:
    raise ValueError("Falta la variable de entorno GROUP")

GROUP_ID = int(GROUP_ENV)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# =======================
# MEMORIA TEMPORAL
# =======================
# clave = titulo limpio
# valor = message_id
peliculas = {}

# =======================
# UTILS
# =======================
def clean_text(text: str) -> str:
    if not text:
        return ""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text

def es_chat_privado(update: Update) -> bool:
    return update.message and update.message.chat.type == "private"

def reconstruir_desde_grupo() -> None:
    """
    Nota importante:
    Telegram Bot API NO permite leer automáticamente el historial viejo del grupo
    usando solo polling normal.
    Así que este catálogo se arma desde que el bot está corriendo y detecta mensajes nuevos.
    """
    logger.info("Catálogo iniciado vacío en memoria.")

# =======================
# COMANDOS
# =======================
def start(update: Update, context: CallbackContext) -> None:
    if not update.message:
        return

    update.message.reply_text(
        "🎬 Bienvenido\n\n"
        "Escribe el nombre de la película que buscas."
    )

def help_command(update: Update, context: CallbackContext) -> None:
    if not update.message:
        return

    update.message.reply_text(
        "Comandos disponibles:\n"
        "/start - iniciar\n"
        "/help - ayuda\n"
        "/listar - ver catálogo cargado en memoria (solo grupo)"
    )

def listar(update: Update, context: CallbackContext) -> None:
    if not update.message:
        return

    if update.message.chat_id != GROUP_ID:
        update.message.reply_text("Este comando solo funciona en el grupo de catálogo.")
        return

    if not peliculas:
        update.message.reply_text("No hay películas cargadas en memoria todavía.")
        return

    titulos = sorted(peliculas.keys())
    texto = "🎬 Películas cargadas:\n\n" + "\n".join(f"- {t.title()}" for t in titulos)

    # Evitar mensajes demasiado largos
    if len(texto) > 4000:
        partes = []
        actual = "🎬 Películas cargadas:\n\n"
        for t in titulos:
            linea = f"- {t.title()}\n"
            if len(actual) + len(linea) > 4000:
                partes.append(actual)
                actual = linea
            else:
                actual += linea
        if actual:
            partes.append(actual)

        for parte in partes:
            update.message.reply_text(parte)
    else:
        update.message.reply_text(texto)

# =======================
# REGISTRAR PELÍCULAS
# =======================
def detectar_pelicula(update: Update, context: CallbackContext) -> None:
    if not update.message:
        return

    if update.message.chat_id != GROUP_ID:
        return

    # Solo registrar si trae video o documento
    if not (update.message.video or update.message.document):
        return

    texto = update.message.caption or update.message.text
    if not texto:
        return

    lineas = [line.strip() for line in texto.split("\n") if line.strip()]
    if not lineas:
        return

    titulo_original = lineas[0]
    titulo = clean_text(titulo_original)

    if not titulo:
        return

    peliculas[titulo] = update.message.message_id
    logger.info("Película registrada: %s | message_id=%s", titulo, update.message.message_id)

# =======================
# BÚSQUEDA
# =======================
def buscar(update: Update, context: CallbackContext) -> None:
    if not update.message or not update.message.text:
        return

    # Solo responder búsquedas en privado
    if not es_chat_privado(update):
        return

    texto_usuario = clean_text(update.message.text)
    if not texto_usuario:
        update.message.reply_text("Escribe un nombre válido.")
        return

    coincidencias = []
    for titulo in peliculas.keys():
        if texto_usuario in titulo or titulo in texto_usuario:
            coincidencias.append(titulo)

    if not coincidencias:
        update.message.reply_text("😕 No encontré esa película.")
        return

    coincidencias = sorted(coincidencias)

    # Si hay varias, mostrar hasta 5
    if len(coincidencias) > 1:
        keyboard = []
        for titulo in coincidencias[:5]:
            keyboard.append([
                InlineKeyboardButton(
                    f"🎬 {titulo.title()}",
                    callback_data=f"seleccionar|{titulo}"
                )
            ])

        update.message.reply_text(
            "Encontré varias coincidencias. Elige una:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    titulo = coincidencias[0]
    enviar_ficha_pelicula(update.message.reply_text, titulo)

def enviar_ficha_pelicula(reply_func, titulo: str) -> None:
    keyboard = [
        [InlineKeyboardButton("💳 Comprar", callback_data=f"comprar|{titulo}")],
        [InlineKeyboardButton("🎬 Ver tráiler", callback_data=f"trailer|{titulo}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    reply_func(
        f"😀 Disponible\n\n🎬 {titulo.title()}\n💰 Precio $11",
        reply_markup=reply_markup
    )

# =======================
# BOTONES
# =======================
def button_handler(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    if not query:
        return

    query.answer()

    data = query.data.split("|", 1)
    if len(data) != 2:
        query.edit_message_text("❌ Error en el botón.")
        return

    accion, titulo = data

    if accion == "seleccionar":
        keyboard = [
            [InlineKeyboardButton("💳 Comprar", callback_data=f"comprar|{titulo}")],
            [InlineKeyboardButton("🎬 Ver tráiler", callback_data=f"trailer|{titulo}")]
        ]
        query.edit_message_text(
            f"😀 Disponible\n\n🎬 {titulo.title()}\n💰 Precio $11",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if accion == "comprar":
        message_id = peliculas.get(titulo)
        if not message_id:
            query.edit_message_text("❌ Esa película ya no está disponible en memoria.")
            return

        context.bot.send_message(
            chat_id=query.from_user.id,
            text=f"✅ Compra realizada: {titulo.title()}\nEnviando película..."
        )

        context.bot.copy_message(
            chat_id=query.from_user.id,
            from_chat_id=GROUP_ID,
            message_id=message_id
        )
        return

    if accion == "trailer":
        trailer_url = f"https://www.youtube.com/results?search_query={titulo.replace(' ', '+')}"
        query.edit_message_text(
            f"🎬 Tráiler de '{titulo.title()}': {trailer_url}"
        )
        return

# =======================
# ERRORES
# =======================
def error_handler(update: object, context: CallbackContext) -> None:
    logger.exception("Ocurrió un error:", exc_info=context.error)

# =======================
# MAIN
# =======================
def main() -> None:
    reconstruir_desde_grupo()

    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_command))
    dp.add_handler(CommandHandler("listar", listar))

    # Registrar películas desde el grupo
    dp.add_handler(MessageHandler(Filters.chat(GROUP_ID), detectar_pelicula))

    # Buscar películas en privado
    dp.add_handler(
        MessageHandler(
            Filters.text & ~Filters.command & Filters.private,
            buscar
        )
    )

    dp.add_handler(CallbackQueryHandler(button_handler))
    dp.add_error_handler(error_handler)

    logger.info("Bot iniciado...")
    updater.start_polling(drop_pending_updates=True)
    updater.idle()

if __name__ == "__main__":
    main()
