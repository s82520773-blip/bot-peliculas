import os
import re
import json
import uuid
import threading
import logging
import requests

from flask import Flask, request, jsonify
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
MP_ACCESS = os.getenv("MP_ACCESS")
PRICE = float(os.getenv("MOVIE_PRICE", "11"))
CURRENCY_ID = os.getenv("CURRENCY_ID", "MXN")
PUBLIC_BASE_URL = os.getenv(
    "PUBLIC_BASE_URL",
    "https://bot-peliculas-production.up.railway.app"
)
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

if not BOT_TOKEN:
    raise ValueError("❌ Falta BOT_TOKEN")

if not GROUP_ENV:
    raise ValueError("❌ Falta GROUP")

if not MP_ACCESS:
    raise ValueError("❌ Falta MP_ACCESS")

GROUP_ID = int(GROUP_ENV)
CATALOG_FILE = "peliculas.json"
REQUESTS_FILE = "solicitudes.json"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# =======================
# APP WEBHOOK
# =======================
app = Flask(__name__)

# =======================
# DATOS
# =======================
peliculas = {}
solicitudes = {}


# =======================
# UTILIDADES
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


def price_text() -> str:
    return f"{int(PRICE) if float(PRICE).is_integer() else PRICE}"


# =======================
# PELICULAS JSON
# =======================
def cargar_peliculas() -> dict:
    if not os.path.exists(CATALOG_FILE):
        return {}

    try:
        with open(CATALOG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return {k: int(v) for k, v in data.items()}
    except Exception:
        logger.exception("Error cargando peliculas.json")
        return {}


def guardar_peliculas() -> None:
    try:
        with open(CATALOG_FILE, "w", encoding="utf-8") as f:
            json.dump(peliculas, f, ensure_ascii=False, indent=2)
    except Exception:
        logger.exception("Error guardando peliculas.json")


# =======================
# SOLICITUDES JSON
# =======================
def cargar_solicitudes() -> dict:
    if not os.path.exists(REQUESTS_FILE):
        return {}

    try:
        with open(REQUESTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
            return {}
    except Exception:
        logger.exception("Error cargando solicitudes.json")
        return {}


def guardar_solicitudes() -> None:
    try:
        with open(REQUESTS_FILE, "w", encoding="utf-8") as f:
            json.dump(solicitudes, f, ensure_ascii=False, indent=2)
    except Exception:
        logger.exception("Error guardando solicitudes.json")


def agregar_solicitud(titulo: str, user) -> bool:
    """
    Devuelve True si se agregó una solicitud nueva.
    False si el usuario ya había pedido esa película.
    """
    titulo = clean_text(titulo)
    if not titulo:
        return False

    if titulo not in solicitudes:
        solicitudes[titulo] = []

    for item in solicitudes[titulo]:
        if item.get("user_id") == user.id:
            return False

    solicitudes[titulo].append({
        "user_id": user.id,
        "first_name": user.first_name or "",
        "username": user.username or "",
    })
    guardar_solicitudes()
    return True


def notificar_solicitudes_si_existen(titulo: str) -> None:
    titulo = clean_text(titulo)
    if titulo not in solicitudes or not solicitudes[titulo]:
        return

    interesados = solicitudes[titulo][:]

    for item in interesados:
        user_id = item.get("user_id")
        if not user_id:
            continue

        try:
            keyboard = [
                [InlineKeyboardButton("💳 Comprar", callback_data=f"comprar|{titulo}")],
                [InlineKeyboardButton("🎬 Ver tráiler", callback_data=f"trailer|{titulo}")]
            ]

            updater.bot.send_message(
                chat_id=user_id,
                text=(
                    "🎉 Buenas noticias\n\n"
                    f"La película que pediste ya está disponible:\n\n"
                    f"🎬 {titulo.title()}\n"
                    f"💰 Precio ${price_text()}"
                ),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            logger.info("Usuario notificado | user_id=%s | titulo=%s", user_id, titulo)

        except Exception:
            logger.exception("No se pudo notificar al usuario %s sobre %s", user_id, titulo)

    # Una vez notificados, se elimina la lista de espera de esa película
    solicitudes.pop(titulo, None)
    guardar_solicitudes()


def send_movie_card(reply_func, titulo: str) -> None:
    keyboard = [
        [InlineKeyboardButton("💳 Comprar", callback_data=f"comprar|{titulo}")],
        [InlineKeyboardButton("🎬 Ver tráiler", callback_data=f"trailer|{titulo}")]
    ]
    reply_func(
        f"😀 Disponible\n\n"
        f"🎬 {titulo.title()}\n"
        f"💰 Precio ${price_text()}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


def get_payment_info(payment_id: str) -> dict:
    url = f"https://api.mercadopago.com/v1/payments/{payment_id}"
    headers = {
        "Authorization": f"Bearer {MP_ACCESS}",
        "Content-Type": "application/json",
    }

    response = requests.get(url, headers=headers, timeout=30)

    if response.status_code != 200:
        logger.error("Error consultando pago %s: %s", payment_id, response.text)
        raise RuntimeError(response.text)

    return response.json()


def create_mp_preference(title: str, user_id: int, message_id: int) -> str:
    url = "https://api.mercadopago.com/checkout/preferences"

    external_reference = f"tg-{user_id}-{uuid.uuid4().hex[:12]}"

    payload = {
        "items": [
            {
                "title": title.title(),
                "quantity": 1,
                "unit_price": PRICE,
                "currency_id": CURRENCY_ID
            }
        ],
        "external_reference": external_reference,
        "metadata": {
            "telegram_user_id": user_id,
            "movie_title": title,
            "message_id": message_id
        },
        "back_urls": {
            "success": f"{PUBLIC_BASE_URL}/success",
            "failure": f"{PUBLIC_BASE_URL}/failure",
            "pending": f"{PUBLIC_BASE_URL}/pending"
        },
        "auto_return": "approved",
        "notification_url": f"{PUBLIC_BASE_URL}/webhook"
    }

    headers = {
        "Authorization": f"Bearer {MP_ACCESS}",
        "Content-Type": "application/json",
    }

    response = requests.post(url, json=payload, headers=headers, timeout=30)

    if response.status_code not in (200, 201):
        logger.error("Mercado Pago error %s: %s", response.status_code, response.text)
        raise RuntimeError(response.text)

    data = response.json()
    payment_url = data["init_point"]

    if not payment_url:
        raise RuntimeError("Mercado Pago no devolvió URL de pago.")

    logger.info(
        "Preferencia creada | title=%s | user_id=%s | external_reference=%s | pref_id=%s",
        title,
        user_id,
        external_reference,
        data.get("id"),
    )

    return payment_url


def entregar_pelicula_si_corresponde(payment_data: dict) -> None:
    status = payment_data.get("status")

    if status != "approved":
        logger.info("Pago no aprobado todavía | status=%s", status)
        return

    metadata = payment_data.get("metadata", {}) or {}

    user_id = metadata.get("telegram_user_id")
    titulo = metadata.get("movie_title")
    message_id = metadata.get("message_id")

    if not user_id or not titulo or not message_id:
        logger.warning("Faltan datos en metadata del pago: %s", metadata)
        return

    try:
        user_id = int(user_id)
        message_id = int(message_id)
    except Exception:
        logger.warning("Metadata inválida: %s", metadata)
        return

    try:
        updater.bot.send_message(
            chat_id=user_id,
            text=f"✅ Pago aprobado\n\n🎬 {str(titulo).title()}\nEnviando película..."
        )
        updater.bot.copy_message(
            chat_id=user_id,
            from_chat_id=GROUP_ID,
            message_id=message_id
        )
        logger.info(
            "Película entregada | user_id=%s | titulo=%s | message_id=%s",
            user_id,
            titulo,
            message_id
        )
    except Exception:
        logger.exception("Error entregando película desde metadata")


# =======================
# WEBHOOKS / HTTP
# =======================
@app.route("/", methods=["GET"])
def home():
    return "OK", 200


@app.route("/success", methods=["GET"])
def success():
    return "Pago aprobado. Vuelve a Telegram.", 200


@app.route("/failure", methods=["GET"])
def failure():
    return "Pago rechazado. Vuelve a Telegram.", 200


@app.route("/pending", methods=["GET"])
def pending():
    return "Pago pendiente. Vuelve a Telegram.", 200


@app.route("/favicon.ico", methods=["GET"])
def favicon():
    return "", 204


@app.route("/webhook", methods=["POST"])
def mp_webhook():
    data = request.get_json(silent=True) or {}
    logger.info("Webhook recibido: %s", data)

    event_type = data.get("type")
    payment_id = data.get("data", {}).get("id")

    if event_type == "payment" and payment_id:
        try:
            payment_data = get_payment_info(payment_id)
            entregar_pelicula_si_corresponde(payment_data)
        except Exception:
            logger.exception("Error procesando webhook payment_id=%s", payment_id)

    return jsonify({"status": "ok"}), 200


def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)


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
        "/listar - ver catálogo cargado (solo grupo)"
    )


def listar(update: Update, context: CallbackContext) -> None:
    if not update.message:
        return

    if update.message.chat_id != GROUP_ID:
        update.message.reply_text("❌ Este comando solo funciona en el grupo de catálogo.")
        return

    if not peliculas:
        update.message.reply_text("📭 No hay películas registradas.")
        return

    titulos = sorted(peliculas.keys())
    texto = "🎬 Películas registradas:\n\n" + "\n".join(f"- {t.title()}" for t in titulos)

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
    guardar_peliculas()
    logger.info("Película registrada: %s | message_id=%s", titulo, update.message.message_id)

    # Notificar a quienes la pidieron antes
    notificar_solicitudes_si_existen(titulo)


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
        keyboard = [
            [InlineKeyboardButton("📥 Puedo conseguirla", callback_data=f"solicitar|{texto_usuario}")]
        ]

        update.message.reply_text(
            "😕 No encontré esa película.\n\n"
            "Si quieres, puedo intentar conseguirla para ti.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
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
        keyboard = [
            [InlineKeyboardButton("💳 Comprar", callback_data=f"comprar|{titulo}")],
            [InlineKeyboardButton("🎬 Ver tráiler", callback_data=f"trailer|{titulo}")]
        ]
        query.edit_message_text(
            f"😀 Disponible\n\n"
            f"🎬 {titulo.title()}\n"
            f"💰 Precio ${price_text()}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if accion == "solicitar":
        user = query.from_user
        pelicula = clean_text(titulo)

        fue_agregada = agregar_solicitud(pelicula, user)

        if ADMIN_ID:
            username = f"@{user.username}" if user.username else "Sin username"
            mensaje_admin = (
                "📥 Nueva solicitud de película\n\n"
                f"🎬 Película: {pelicula}\n"
                f"👤 Usuario: {user.first_name}\n"
                f"🆔 ID: {user.id}\n"
                f"🔗 Username: {username}"
            )
            try:
                updater.bot.send_message(chat_id=ADMIN_ID, text=mensaje_admin)
            except Exception:
                logger.exception("No se pudo enviar solicitud al admin")

        if fue_agregada:
            query.edit_message_text(
                "✅ Tu solicitud fue enviada.\n\n"
                "Te avisaré cuando la película esté disponible."
            )
        else:
            query.edit_message_text(
                "✅ Ya tenía registrada tu solicitud para esa película.\n\n"
                "Te avisaré cuando esté disponible."
            )
        return

    if accion == "comprar":
        message_id = peliculas.get(titulo)
        if not message_id:
            query.edit_message_text("❌ Esa película ya no está disponible.")
            return

        try:
            payment_url = create_mp_preference(titulo, query.from_user.id, message_id)
        except Exception as e:
            logger.exception("Error creando preferencia de Mercado Pago")
            query.edit_message_text(
                f"❌ No pude generar el pago para '{titulo.title()}'.\n\n"
                f"Detalle:\n{str(e)}"
            )
            return

        keyboard = [
            [InlineKeyboardButton("💳 Pagar ahora", url=payment_url)],
            [InlineKeyboardButton("🎬 Ver tráiler", callback_data=f"trailer|{titulo}")]
        ]

        query.edit_message_text(
            f"🎬 {titulo.title()}\n"
            f"💰 Precio ${price_text()}\n\n"
            f"Se generó tu pago.\n"
            f"Completa el checkout desde el botón de abajo.\n\n"
            f"✅ La película se enviará automáticamente cuando el pago sea aprobado.",
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
    global updater
    global peliculas
    global solicitudes

    peliculas = cargar_peliculas()
    solicitudes = cargar_solicitudes()

    logger.info("✅ Catálogo cargado: %s películas", len(peliculas))
    logger.info("✅ Solicitudes cargadas: %s títulos", len(solicitudes))

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

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
