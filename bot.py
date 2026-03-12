import os
import re
import json
import uuid
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

# ========================
# VARIABLES DE ENTORNO
# ========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_ID = int(os.getenv("GROUP"))
ADMIN_ID = int(os.getenv("ADMIN_ID"))

PRICE = float(os.getenv("MOVIE_PRICE", "11"))
CURRENCY = os.getenv("CURRENCY_ID", "MXN")

BANK_NAME = os.getenv("BANK_NAME", "BANCO")
BANK_OWNER = os.getenv("BANK_OWNER", "BENEFICIARIO")
BANK_CLABE = os.getenv("BANK_CLABE", "000000000000000000")
BANK_CARD = os.getenv("BANK_CARD", "")
BANK_NOTE = os.getenv("BANK_NOTE", "Usa la referencia unica en el concepto de pago")

CATALOG_FILE = "peliculas.json"
REQUEST_FILE = "solicitudes.json"
ORDERS_FILE = "ordenes.json"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ========================
# JSON HELPERS
# ========================
def load_json(file_path):
    if not os.path.exists(file_path):
        return {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        logger.exception("Error cargando %s", file_path)
        return {}


def save_json(file_path, data):
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        logger.exception("Error guardando %s", file_path)


peliculas = load_json(CATALOG_FILE)
solicitudes = load_json(REQUEST_FILE)
ordenes = load_json(ORDERS_FILE)

# ========================
# UTILIDADES
# ========================
def clean(text: str) -> str:
    text = (text or "").lower().strip()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def make_reference(title: str) -> str:
    base = clean(title).replace(" ", "")[:4].upper()
    if not base:
        base = "PEL"
    return f"{base}-{uuid.uuid4().hex[:6].upper()}"


def price_text() -> str:
    return f"{int(PRICE) if float(PRICE).is_integer() else PRICE}"


def bank_text(reference: str) -> str:
    text = (
        "💸 Transferencia bancaria\n\n"
        f"Banco: {BANK_NAME}\n"
        f"Beneficiario: {BANK_OWNER}\n"
        f"CLABE:\n{BANK_CLABE}\n\n"
        f"Monto:\n${price_text()} {CURRENCY}\n\n"
        f"Referencia única:\n{reference}\n\n"
        "⚠️ Usa la referencia en el concepto de pago.\n"
        f"{BANK_NOTE}"
    )

    if BANK_CARD:
        text += f"\n\nTarjeta:\n{BANK_CARD}"

    return text


def bank_data_only_text() -> str:
    text = (
        "🏦 Datos bancarios\n\n"
        f"Banco: {BANK_NAME}\n"
        f"Beneficiario: {BANK_OWNER}\n"
        f"CLABE: {BANK_CLABE}\n"
    )
    if BANK_CARD:
        text += f"Tarjeta: {BANK_CARD}\n"
    text += f"\n{BANK_NOTE}"
    return text


def build_movie_keyboard(titulo: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💸 Transferencia", callback_data=f"transfer|{titulo}")],
        [InlineKeyboardButton("🏦 Datos bancarios", callback_data=f"bank|{titulo}")],
        [InlineKeyboardButton("🎬 Ver tráiler", callback_data=f"trailer|{titulo}")]
    ])


def send_movie_card(reply_func, titulo: str):
    reply_func(
        f"😀 Disponible\n\n"
        f"🎬 {titulo.title()}\n"
        f"💰 Precio ${price_text()}",
        reply_markup=build_movie_keyboard(titulo)
    )


# ========================
# COMANDOS
# ========================
def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "🎬 Bienvenido\n\n"
        "Escribe el nombre de la película que buscas.\n\n"
        "También puedes usar /catalogo para ver lo disponible."
    )


def help_command(update: Update, context: CallbackContext):
    update.message.reply_text(
        "Comandos disponibles:\n"
        "/start - iniciar\n"
        "/help - ayuda\n"
        "/catalogo - ver películas disponibles\n"
        "/listar - ver catálogo (solo admin/grupo)\n"
        "/pagorealizado REFERENCIA - confirmar pago y entregar (solo admin)"
    )


def catalogo(update: Update, context: CallbackContext):
    if update.message.chat.type != "private":
        update.message.reply_text("📩 Usa /catalogo en privado para ver las películas disponibles.")
        return

    if not peliculas:
        update.message.reply_text("📭 No hay películas disponibles por el momento.")
        return

    titulos = sorted(peliculas.keys())

    encabezado = (
        "🎬 Catálogo disponible\n\n"
        "Escribe el nombre de la película que te interese para comprarla.\n\n"
    )

    bloques = []
    actual = encabezado

    for titulo in titulos:
        linea = f"- {titulo.title()}\n"
        if len(actual) + len(linea) > 3900:
            bloques.append(actual)
            actual = linea
        else:
            actual += linea

    if actual:
        bloques.append(actual)

    for bloque in bloques:
        update.message.reply_text(bloque)


def listar(update: Update, context: CallbackContext):
    if update.message.chat_id != GROUP_ID and update.message.from_user.id != ADMIN_ID:
        update.message.reply_text("❌ No autorizado.")
        return

    if not peliculas:
        update.message.reply_text("📭 No hay películas registradas.")
        return

    titulos = sorted(peliculas.keys())
    texto = "🎬 Películas registradas:\n\n" + "\n".join(f"- {t.title()}" for t in titulos)

    for i in range(0, len(texto), 4000):
        update.message.reply_text(texto[i:i + 4000])


def pagorealizado(update: Update, context: CallbackContext):
    if update.message.from_user.id != ADMIN_ID:
        update.message.reply_text("❌ No autorizado.")
        return

    if not context.args:
        update.message.reply_text("Uso correcto:\n/pagorealizado REFERENCIA")
        return

    referencia = context.args[0].strip().upper()

    if referencia not in ordenes:
        update.message.reply_text("❌ No encontré esa referencia.")
        return

    orden = ordenes[referencia]

    if orden.get("status") == "completed":
        update.message.reply_text("✅ Esa orden ya fue entregada.")
        return

    user_id = orden.get("user")
    movie = orden.get("movie")
    message_id = orden.get("message_id")

    if not user_id or not movie or not message_id:
        update.message.reply_text("❌ Orden incompleta o inválida.")
        return

    try:
        context.bot.send_message(
            chat_id=user_id,
            text=(
                "✅ Pago confirmado\n\n"
                f"🎬 {str(movie).title()}\n"
                "Enviando película..."
            )
        )

        context.bot.copy_message(
            chat_id=user_id,
            from_chat_id=GROUP_ID,
            message_id=message_id
        )

        orden["status"] = "completed"
        save_json(ORDERS_FILE, ordenes)

        update.message.reply_text(
            f"✅ Película entregada correctamente.\n\n"
            f"Referencia: {referencia}\n"
            f"Usuario: {user_id}\n"
            f"Película: {str(movie).title()}"
        )

    except Exception:
        logger.exception("Error entregando película con referencia %s", referencia)
        update.message.reply_text("❌ Ocurrió un error al entregar la película.")


# ========================
# BÚSQUEDA
# ========================
def buscar(update: Update, context: CallbackContext):
    if update.message.chat.type != "private":
        return

    texto = clean(update.message.text)

    coincidencias = []

    for titulo in peliculas:
        if texto in titulo or titulo in texto:
            coincidencias.append(titulo)

    coincidencias = sorted(set(coincidencias))

    if coincidencias:
        if len(coincidencias) == 1:
            titulo = coincidencias[0]
            send_movie_card(update.message.reply_text, titulo)
            return

        keyboard = []
        for titulo in coincidencias[:8]:
            keyboard.append([
                InlineKeyboardButton(f"🎬 {titulo.title()}", callback_data=f"select|{titulo}")
            ])

        update.message.reply_text(
            "Encontré varias coincidencias. Elige una:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    keyboard = [
        [InlineKeyboardButton("📩 Solicitar película", callback_data=f"request|{texto}")]
    ]

    update.message.reply_text(
        "😕 No encontré esa película.\n\n¿Quieres que la consiga?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ========================
# BOTONES
# ========================
def buttons(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()

    parts = query.data.split("|", 1)
    if len(parts) != 2:
        query.edit_message_text("❌ Error en el botón.")
        return

    action, value = parts[0], parts[1]
    value = clean(value) if action not in ("paid",) else value.upper()

    if action == "select":
        titulo = value
        query.edit_message_text(
            f"😀 Disponible\n\n"
            f"🎬 {titulo.title()}\n"
            f"💰 Precio ${price_text()}",
            reply_markup=build_movie_keyboard(titulo)
        )
        return

    if action == "transfer":
        titulo = value
        message_id = peliculas.get(titulo)

        if not message_id:
            query.edit_message_text("❌ Esa película ya no está disponible.")
            return

        referencia = make_reference(titulo)

        ordenes[referencia] = {
            "user": query.from_user.id,
            "movie": titulo,
            "message_id": message_id,
            "status": "pending"
        }
        save_json(ORDERS_FILE, ordenes)

        keyboard = [
            [InlineKeyboardButton("🏦 Ver datos bancarios", callback_data=f"bank|{titulo}")],
            [InlineKeyboardButton("✅ Ya transferí", callback_data=f"paid|{referencia}")],
            [InlineKeyboardButton("🎬 Ver tráiler", callback_data=f"trailer|{titulo}")]
        ]

        query.edit_message_text(
            bank_text(referencia),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if action == "bank":
        titulo = value
        keyboard = [
            [InlineKeyboardButton("💸 Generar referencia", callback_data=f"transfer|{titulo}")],
            [InlineKeyboardButton("🎬 Ver tráiler", callback_data=f"trailer|{titulo}")]
        ]

        query.edit_message_text(
            bank_data_only_text(),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if action == "trailer":
        titulo = value
        url = f"https://youtube.com/results?search_query={titulo.replace(' ', '+')}+trailer"
        query.edit_message_text(f"🎬 Tráiler:\n{url}")
        return

    if action == "request":
        titulo = value

        if titulo not in solicitudes:
            solicitudes[titulo] = []

        ya_existe = any(item.get("user_id") == query.from_user.id for item in solicitudes[titulo])

        if not ya_existe:
            solicitudes[titulo].append({
                "user_id": query.from_user.id,
                "name": query.from_user.first_name or "",
                "username": query.from_user.username or "",
            })
            save_json(REQUEST_FILE, solicitudes)

        username = f"@{query.from_user.username}" if query.from_user.username else "Sin username"

        context.bot.send_message(
            ADMIN_ID,
            "📩 Nueva solicitud de película\n\n"
            f"🎬 Película: {titulo}\n"
            f"👤 Usuario: {query.from_user.first_name}\n"
            f"🆔 ID: {query.from_user.id}\n"
            f"🔗 Username: {username}"
        )

        if ya_existe:
            query.edit_message_text(
                "✅ Ya tenía registrada tu solicitud.\n\n"
                "Te avisaré cuando la película esté disponible."
            )
        else:
            query.edit_message_text(
                "✅ Tu solicitud fue enviada.\n\n"
                "Te avisaré cuando la película esté disponible."
            )
        return

    if action == "paid":
        referencia = value

        if referencia not in ordenes:
            query.edit_message_text("❌ Referencia inválida.")
            return

        orden = ordenes[referencia]

        if orden.get("status") == "completed":
            query.edit_message_text("✅ Esa orden ya fue confirmada.")
            return

        orden["status"] = "reported"
        save_json(ORDERS_FILE, ordenes)

        movie = orden.get("movie", "")
        user_id = orden.get("user", "")

        context.bot.send_message(
            ADMIN_ID,
            "🚨 Cliente reportó pago\n\n"
            f"🔖 Referencia: {referencia}\n"
            f"🎬 Película: {str(movie).title()}\n"
            f"👤 Cliente ID: {user_id}\n\n"
            f"Para entregar usa:\n"
            f"/pagorealizado {referencia}"
        )

        query.edit_message_text(
            "✅ Recibí tu aviso de transferencia.\n\n"
            f"Referencia: {referencia}\n\n"
            "Tu pago será validado y luego recibirás la película."
        )
        return


# ========================
# DETECTAR NUEVA PELÍCULA
# ========================
def detectar(update: Update, context: CallbackContext):
    if update.message.chat_id != GROUP_ID:
        return

    if not (update.message.video or update.message.document):
        return

    texto = update.message.caption or update.message.text
    if not texto:
        return

    titulo = clean(texto.split("\n")[0])

    peliculas[titulo] = update.message.message_id
    save_json(CATALOG_FILE, peliculas)

    logger.info("Película registrada: %s", titulo)

    if titulo in solicitudes and solicitudes[titulo]:
        for item in solicitudes[titulo]:
            user_id = item.get("user_id")
            if not user_id:
                continue

            try:
                context.bot.send_message(
                    chat_id=user_id,
                    text=(
                        "🎉 Buenas noticias\n\n"
                        "La película que pediste ya está disponible:\n\n"
                        f"🎬 {titulo.title()}\n"
                        f"💰 Precio ${price_text()}"
                    ),
                    reply_markup=build_movie_keyboard(titulo)
                )
            except Exception:
                logger.exception("No se pudo notificar al usuario %s", user_id)

        solicitudes.pop(titulo, None)
        save_json(REQUEST_FILE, solicitudes)


# ========================
# MAIN
# ========================
def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_command))
    dp.add_handler(CommandHandler("catalogo", catalogo))
    dp.add_handler(CommandHandler("listar", listar))
    dp.add_handler(CommandHandler("pagorealizado", pagorealizado))

    dp.add_handler(MessageHandler(Filters.text & Filters.private & ~Filters.command, buscar))
    dp.add_handler(MessageHandler(Filters.chat(GROUP_ID), detectar))

    dp.add_handler(CallbackQueryHandler(buttons))

    logger.info("✅ Bot iniciado...")
    updater.start_polling(drop_pending_updates=True)
    updater.idle()


if __name__ == "__main__":
    main()
