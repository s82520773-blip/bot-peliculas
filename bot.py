import os
import re
import uuid
import logging
import requests
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
MP_ACCESS = os.getenv("MP_ACCESS")  # token de prueba o productivo
PRICE = float(os.getenv("MOVIE_PRICE", "11"))

if not BOT_TOKEN:
    raise ValueError("❌ Falta la variable BOT_TOKEN")

if not GROUP_ENV:
    raise ValueError("❌ Falta la variable GROUP")

if not MP_ACCESS:
    raise ValueError("❌ Falta la variable MP_ACCESS")

GROUP_ID = int(GROUP_ENV)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# =======================
# MEMORIA TEMPORAL
# =======================
# titulo_limpio -> message_id
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

def is_private_chat(update: Update) -> bool:
    return bool(update.message and update.message.chat.type == "private")

def create_mp_preference(title: str, user_id: int) -> str:
    """
    Crea una preferencia de Mercado Pago Checkout Pro y devuelve la URL de pago.
    En pruebas, normalmente conviene usar sandbox_init_point si existe.
    """
    url = "https://api.mercadopago.com/checkout/preferences"

    external_reference = f"tg-{user_id}-{uuid.uuid4().hex[:12]}"

    payload = {
        "items": [
            {
                "title": title.title(),
                "quantity": 1,
                "unit_price": PRICE,
                "currency_id": "MXN"
            }
        ],
        "external_reference": external_reference,
        "metadata": {
            "telegram_user_id": user_id,
            "movie_title": title,
        }
    }

    headers = {
        "Authorization": f"Bearer {MP_ACCESS}",
        "Content-Type": "application/json",
    }

    response = requests.post(url, json=payload, headers=headers, timeout=30)

    if response.status_code not in (200, 201):
        logger.error("Mercado Pago error %s: %s", response.status_code, response.text)
        raise RuntimeError("No se pudo crear la preferencia de pago.")

    data = response.json()

    # En pruebas suele existir sandbox_init_point
    payment_url = data.get("sandbox_init_point") or data.get("init_point")
    if not payment_url:
        raise RuntimeError("Mercado Pago no devolvió una URL de pago.")

    logger.info(
        "Preferencia creada | title=%s | user_id=%s | pref_id=%s",
        title,
        user_id,
        data.get("id"),
    )

    return payment_url

def send_movie_card(reply_func, titulo: str) -> None:
    keyboard = [
        [InlineKeyboardButton("💳 Comprar", callback_data=f"comprar|{titulo}")],
        [InlineKeyboardButton("🎬 Ver tráiler", callback_data=f"trailer|{titulo}")]
    ]

    reply_func(
        f"😀 Disponible\n\n"
        f"🎬 {titulo.title()}\n"
        f"💰 Precio ${int(PRICE) if PRICE.is_integer() else PRICE}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

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
        update.message.reply_text("❌ Este comando solo funciona en el grupo de catálogo.")
        return

    if not peliculas:
        update.message.reply_text("📭 No hay películas cargadas en memoria todavía.")
        return

    titulos = sorted(peliculas.keys())
    texto = "🎬 Películas cargadas:\n\n" + "\n".join(f"- {t.title()}" for t in titulos)

    for i in range(0, len(texto), 4000):
        update.message.reply_text(texto[i:i + 4000])

# =======================
# REGISTRO DESDE GRUPO
# =======================
def detectar_pelicula(update: Update, context: CallbackContext) -> None:
    if not update.message:
        return

    if update.message.chat_id != GROUP_ID:
        return

    if not (update.message.video or update.message.document):
        return

    texto = update.message.caption or update.message.text
    if not texto:
        return

    lineas = [line.strip() for line in texto.split("\n") if line.strip()]
    if not lineas:
        return

    titulo = clean_text(lineas[0])
    if not titulo:
        return

    peliculas[titulo] = update.message.message_id
    logger.info("Película registrada: %s | message_id=%s", titulo, update.message.message_id)

# =======================
# BÚSQUEDA PRIVADA
# =======================
def buscar(update: Update, context: CallbackContext) -> None:
    if not update.message or not update.message.text:
        return

    if not is_private_chat(update):
        return

    texto_usuario = clean_text(update.message.text)
    if not texto_usuario:
        update.message.reply_text("😕 Escribe un nombre válido.")
        return

    coincidencias = []
    for titulo in peliculas.keys():
        if texto_usuario in titulo or titulo in texto_usuario:
            coincidencias.append(titulo)

    coincidencias = sorted(set(coincidencias))

    if not coincidencias:
        update.message.reply_text("😕 No encontré esa película.")
        return

    if len(coincidencias) == 1:
        send_movie_card(update.message.reply_text, coincidencias[0])
        return

    keyboard = []
    for titulo in coincidencias[:8]:
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
        send_movie_card(query.edit_message_text, titulo)
        return

    if accion == "comprar":
        message_id = peliculas.get(titulo)
        if not message_id:
            query.edit_message_text("❌ Esa película ya no está disponible.")
            return

        try:
            payment_url = create_mp_preference(titulo, query.from_user.id)
        except Exception as e:
            logger.exception("Error creando preferencia de Mercado Pago")
            query.edit_message_text(
                f"❌ No pude generar el pago para '{titulo.title()}'.\n\n"
                f"Detalle: {str(e)}"
            )
            return

        keyboard = [
            [InlineKeyboardButton("💳 Pagar ahora", url=payment_url)],
            [InlineKeyboardButton("🎬 Ver tráiler", callback_data=f"trailer|{titulo}")]
        ]

        query.edit_message_text(
            f"🎬 {titulo.title()}\n"
            f"💰 Precio ${int(PRICE) if PRICE.is_integer() else PRICE}\n\n"
            f"Se generó tu pago de prueba en Mercado Pago.\n"
            f"Completa el pago desde el botón de abajo.\n\n"
            f"⚠️ Esta versión aún no entrega automáticamente después del pago.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if accion == "trailer":
        trailer_url = f"https://www.youtube.com/results?search_query={titulo.replace(' ', '+')}"
        query.edit_message_text(
            f"🎬 Tráiler de '{titulo.title()}':\n{trailer_url}"
        )
        return

# =======================
# ERRORES
# =======================
def error_handler(update: object, context: CallbackContext) -> None:
    logger.exception("❌ Ocurrió un error", exc_info=context.error)

# =======================
# MAIN
# =======================
def main() -> None:
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_command))
    dp.add_handler(CommandHandler("listar", listar))

    dp.add_handler(MessageHandler(Filters.chat(GROUP_ID), detectar_pelicula))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command & Filters.private, buscar))

    dp.add_handler(CallbackQueryHandler(button_handler))
    dp.add_error_handler(error_handler)

    logger.info("✅ Bot iniciado...")
    updater.start_polling(drop_pending_updates=True)
    updater.idle()

if __name__ == "__main__":
    main()
