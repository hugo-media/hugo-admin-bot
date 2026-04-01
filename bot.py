#!/usr/bin/env python3
"""
Hugo Media Admin Bot
Додає товари на сайт і публікує в TG канал
"""

import os
import json
import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters
)

logging.basicConfig(
    format='%(asctime)s | %(levelname)s | %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ─── CONFIG ────────────────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN", "")
OWNER_ID = int(os.getenv("OWNER_CHAT_ID", "0"))
SITE_URL = os.getenv("SITE_URL", "https://laptopcat-dmlwym6z.manus.space")
BOT_API_SECRET = os.getenv("BOT_API_SECRET", "hugo_bot_secret_2024")
TG_CHANNEL = os.getenv("TG_CHANNEL", "@hugo_media_shop")

# ─── STATES ────────────────────────────────────────────────────────────────────
(
    CHOOSE_CATEGORY,
    CHOOSE_SUBCATEGORY,
    ENTER_NAME,
    ENTER_PROCESSOR,
    ENTER_GPU,
    ENTER_RAM,
    ENTER_STORAGE,
    ENTER_DISPLAY,
    ENTER_OS,
    ENTER_CONDITION,
    ENTER_WARRANTY,
    ENTER_PRICE,
    ENTER_DISCOUNT,
    ENTER_PHOTO,
    ENTER_DESCRIPTION,
    CONFIRM,
    # Monitor specific
    ENTER_RESOLUTION,
    ENTER_PANEL_TYPE,
    ENTER_REFRESH_RATE,
    ENTER_BRIGHTNESS,
    ENTER_CONTRAST,
    ENTER_RESPONSE_TIME,
    ENTER_CONNECTIVITY,
    ENTER_SIZE,
    # Accessory / SmartDevice specific
    ENTER_TYPE,
    ENTER_BRAND,
    ENTER_COMPATIBILITY,
    ENTER_COLOR,
    ENTER_BATTERY,
    ENTER_FEATURES,
    ENTER_CAMERA,
) = range(31)

# ─── CATEGORIES ────────────────────────────────────────────────────────────────
CATEGORIES = {
    "laptops": "💻 Ноутбук",
    "monitors": "🖥 Монітор",
    "accessories": "🎧 Аксесуар",
    "tablets": "📱 Планшет",
    "smartDevices": "⌚ Смарт девайс",
}

SUBCATEGORIES = ["new", "refurbished", "business", "promotions"]

CONDITIONS = ["Новий", "Б/у відмінний", "Б/у хороший", "Б/у задовільний"]
WARRANTIES = ["Без гарантії", "1 місяць", "3 місяці", "6 місяців", "1 рік", "2 роки"]


# ─── HELPERS ───────────────────────────────────────────────────────────────────
def is_owner(update: Update) -> bool:
    return update.effective_user.id == OWNER_ID


def kb(buttons: list) -> InlineKeyboardMarkup:
    """Build inline keyboard from list of (text, callback_data) tuples."""
    rows = []
    row = []
    for i, (text, data) in enumerate(buttons):
        row.append(InlineKeyboardButton(text, callback_data=data))
        if len(row) == 2 or i == len(buttons) - 1:
            rows.append(row)
            row = []
    return InlineKeyboardMarkup(rows)


def skip_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("⏭ Пропустити", callback_data="skip")]])


def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Скасувати", callback_data="cancel")]])


async def upload_photo_to_site(photo_bytes: bytes, filename: str) -> str | None:
    """Upload photo to site and return URL."""
    try:
        resp = requests.post(
            f"{SITE_URL}/api/bot/upload",
            headers={"x-bot-secret": BOT_API_SECRET},
            files={"file": (filename, photo_bytes, "image/jpeg")},
            timeout=30
        )
        if resp.status_code == 200:
            return resp.json().get("url")
    except Exception as e:
        logger.error(f"Photo upload failed: {e}")
    return None


async def send_to_site(data: dict) -> bool:
    """Send product data to site API."""
    try:
        resp = requests.post(
            f"{SITE_URL}/api/bot/product",
            headers={
                "x-bot-secret": BOT_API_SECRET,
                "Content-Type": "application/json"
            },
            json=data,
            timeout=30
        )
        logger.info(f"Site API response: {resp.status_code} {resp.text[:200]}")
        return resp.status_code == 201
    except Exception as e:
        logger.error(f"Site API error: {e}")
        return False


async def publish_to_channel(bot, data: dict, photo_url: str | None = None) -> bool:
    """Publish product post to TG channel."""
    cat = data.get("category", "")
    name = data.get("name", "")
    price = data.get("price", "")
    discount = int(data.get("discountPercent", 0))
    desc = data.get("description", "")

    # Build post text
    lines = [f"🛒 {name}"]
    lines.append("")

    # Category-specific specs
    if cat == "laptops":
        if data.get("processor"): lines.append(f"⚙️ Процесор: {data['processor']}")
        if data.get("graphicsCard") and data["graphicsCard"] != "Integrated": lines.append(f"🎮 GPU: {data['graphicsCard']}")
        if data.get("ram"): lines.append(f"💾 RAM: {data['ram']}")
        if data.get("storage"): lines.append(f"💿 Накопичувач: {data['storage']}")
        if data.get("display"): lines.append(f"🖥 Дисплей: {data['display']}")
        if data.get("operatingSystem"): lines.append(f"💻 ОС: {data['operatingSystem']}")
    elif cat == "monitors":
        if data.get("size"): lines.append(f"📐 Розмір: {data['size']}")
        if data.get("resolution"): lines.append(f"🔲 Розширення: {data['resolution']}")
        if data.get("panelType"): lines.append(f"🖥 Панель: {data['panelType']}")
        if data.get("refreshRate"): lines.append(f"⚡ Частота: {data['refreshRate']}")
        if data.get("connectivity"): lines.append(f"🔌 Підключення: {data['connectivity']}")
    elif cat == "accessories":
        if data.get("type"): lines.append(f"📦 Тип: {data['type']}")
        if data.get("brand"): lines.append(f"🏷 Бренд: {data['brand']}")
        if data.get("compatibility"): lines.append(f"🔗 Сумісність: {data['compatibility']}")
        if data.get("color"): lines.append(f"🎨 Колір: {data['color']}")
    elif cat == "tablets":
        if data.get("processor"): lines.append(f"⚙️ Процесор: {data['processor']}")
        if data.get("ram"): lines.append(f"💾 RAM: {data['ram']}")
        if data.get("storage"): lines.append(f"💿 Пам'ять: {data['storage']}")
        if data.get("display"): lines.append(f"🖥 Дисплей: {data['display']}")
        if data.get("battery"): lines.append(f"🔋 Батарея: {data['battery']}")
        if data.get("camera"): lines.append(f"📷 Камера: {data['camera']}")
    elif cat == "smartDevices":
        if data.get("type"): lines.append(f"📦 Тип: {data['type']}")
        if data.get("brand"): lines.append(f"🏷 Бренд: {data['brand']}")
        if data.get("connectivity"): lines.append(f"📡 Підключення: {data['connectivity']}")
        if data.get("battery"): lines.append(f"🔋 Батарея: {data['battery']}")
        if data.get("features"): lines.append(f"✨ Функції: {data['features']}")

    lines.append("")
    if data.get("condition"): lines.append(f"✅ Стан: {data['condition']}")
    if data.get("warranty"): lines.append(f"🛡 Гарантія: {data['warranty']}")
    lines.append("")

    if discount > 0:
        original = int(price)
        discounted = int(original * (1 - discount / 100))
        lines.append(f"💰 Ціна: ~{original} грн~ → {discounted} грн (-{discount}%)")
    else:
        lines.append(f"💰 Ціна: {price} грн")

    if desc:
        lines.append("")
        lines.append(desc)

    lines.append("")
    lines.append(f"📲 Замовити: {TG_CHANNEL}")

    text = "\n".join(lines)

    try:
        if photo_url:
            await bot.send_photo(
                chat_id=TG_CHANNEL,
                photo=photo_url,
                caption=text
            )
        else:
            await bot.send_message(chat_id=TG_CHANNEL, text=text)
        return True
    except Exception as e:
        logger.error(f"Channel publish error: {e}")
        return False


def format_summary(data: dict) -> str:
    """Format product summary for confirmation."""
    cat_name = CATEGORIES.get(data.get("category", ""), data.get("category", ""))
    lines = [f"📋 ПІДСУМОК ТОВАРУ", f"", f"Категорія: {cat_name}"]

    fields = {
        "name": "Назва",
        "processor": "Процесор",
        "graphicsCard": "GPU",
        "ram": "RAM",
        "storage": "Накопичувач",
        "display": "Дисплей",
        "operatingSystem": "ОС",
        "resolution": "Розширення",
        "panelType": "Тип панелі",
        "refreshRate": "Частота",
        "brightness": "Яскравість",
        "contrast": "Контраст",
        "responseTime": "Час відгуку",
        "connectivity": "Підключення",
        "size": "Розмір",
        "type": "Тип",
        "brand": "Бренд",
        "compatibility": "Сумісність",
        "color": "Колір",
        "battery": "Батарея",
        "features": "Функції",
        "camera": "Камера",
        "condition": "Стан",
        "warranty": "Гарантія",
        "price": "Ціна (грн)",
        "discountPercent": "Знижка %",
        "categories": "Підкатегорія",
        "description": "Опис",
    }

    for key, label in fields.items():
        val = data.get(key)
        if val and val not in ("", "0", 0, [], None):
            if key == "categories" and isinstance(val, list):
                val = ", ".join(val)
            lines.append(f"{label}: {val}")

    if data.get("imageUrl"):
        lines.append("Фото: ✅ завантажено")

    return "\n".join(lines)


# ─── HANDLERS ──────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        await update.message.reply_text("⛔ Доступ заборонено.")
        return ConversationHandler.END

    context.user_data.clear()

    buttons = [(v, f"cat_{k}") for k, v in CATEGORIES.items()]
    await update.message.reply_text(
        "👋 Hugo Media Admin Bot\n\nОбери категорію товару:",
        reply_markup=kb(buttons)
    )
    return CHOOSE_CATEGORY


async def choose_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "cancel":
        await query.edit_message_text("❌ Скасовано.")
        return ConversationHandler.END

    category = query.data.replace("cat_", "")
    context.user_data["category"] = category
    context.user_data["categories"] = ["new"]

    # Choose subcategory
    buttons = [
        ("🆕 Новий", "sub_new"),
        ("♻️ Refurbished", "sub_refurbished"),
        ("💼 Бізнес", "sub_business"),
        ("🔥 Акція", "sub_promotions"),
    ]
    await query.edit_message_text(
        f"Обрано: {CATEGORIES[category]}\n\nОбери підкатегорію:",
        reply_markup=kb(buttons)
    )
    return CHOOSE_SUBCATEGORY


async def choose_subcategory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    sub = query.data.replace("sub_", "")
    context.user_data["categories"] = [sub]

    await query.edit_message_text(
        f"Підкатегорія: {sub}\n\nВведи назву товару:"
    )
    return ENTER_NAME


async def enter_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = update.message.text.strip()
    cat = context.user_data["category"]

    if cat == "laptops":
        await update.message.reply_text("Процесор (наприклад: Intel Core i5-1235U):", reply_markup=cancel_kb())
        return ENTER_PROCESSOR
    elif cat == "monitors":
        await update.message.reply_text("Розмір монітора (наприклад: 27 inch):", reply_markup=cancel_kb())
        return ENTER_SIZE
    elif cat == "accessories":
        await update.message.reply_text("Тип аксесуара (наприклад: Навушники, Зарядка, Мишка):", reply_markup=cancel_kb())
        return ENTER_TYPE
    elif cat == "tablets":
        await update.message.reply_text("Процесор (наприклад: Apple A14 Bionic):", reply_markup=cancel_kb())
        return ENTER_PROCESSOR
    elif cat == "smartDevices":
        await update.message.reply_text("Тип пристрою (наприклад: Смартгодинник, Навушники, Колонка):", reply_markup=cancel_kb())
        return ENTER_TYPE


# ─── LAPTOP FLOW ───────────────────────────────────────────────────────────────
async def enter_processor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["processor"] = update.message.text.strip()
    cat = context.user_data["category"]
    if cat == "tablets":
        await update.message.reply_text("RAM (наприклад: 4GB, 8GB):", reply_markup=cancel_kb())
        return ENTER_RAM
    await update.message.reply_text("Відеокарта (наприклад: NVIDIA RTX 3060 або Integrated):", reply_markup=skip_kb())
    return ENTER_GPU


async def enter_gpu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        context.user_data["graphicsCard"] = "Integrated"
        await update.callback_query.edit_message_text("RAM (наприклад: 8GB DDR4, 16GB DDR5):")
    else:
        context.user_data["graphicsCard"] = update.message.text.strip()
        await update.message.reply_text("RAM (наприклад: 8GB DDR4, 16GB DDR5):", reply_markup=cancel_kb())
    return ENTER_RAM


async def enter_ram(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["ram"] = update.message.text.strip()
    cat = context.user_data["category"]
    await update.message.reply_text(
        "Накопичувач (наприклад: 256GB SSD, 512GB NVMe):",
        reply_markup=cancel_kb()
    )
    return ENTER_STORAGE


async def enter_storage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["storage"] = update.message.text.strip()
    cat = context.user_data["category"]
    if cat == "tablets":
        await update.message.reply_text("Дисплей (наприклад: 10.9 inch Retina):", reply_markup=cancel_kb())
        return ENTER_DISPLAY
    await update.message.reply_text("Дисплей (наприклад: 15.6 inch FHD IPS):", reply_markup=cancel_kb())
    return ENTER_DISPLAY


async def enter_display(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["display"] = update.message.text.strip()
    cat = context.user_data["category"]
    if cat == "tablets":
        await update.message.reply_text("Батарея (наприклад: 5000 mAh, 28.65 Wh):", reply_markup=cancel_kb())
        return ENTER_BATTERY
    await update.message.reply_text("Операційна система (наприклад: Windows 11, No OS):", reply_markup=skip_kb())
    return ENTER_OS


async def enter_os(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        context.user_data["operatingSystem"] = "No OS"
        await update.callback_query.edit_message_text("Стан товару:")
    else:
        context.user_data["operatingSystem"] = update.message.text.strip()
        await update.message.reply_text("Стан товару:", reply_markup=kb([(c, f"cond_{c}") for c in CONDITIONS]))
    return ENTER_CONDITION


# ─── MONITOR FLOW ──────────────────────────────────────────────────────────────
async def enter_size(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["size"] = update.message.text.strip()
    await update.message.reply_text("Розширення (наприклад: 1920x1080, 2560x1440):", reply_markup=cancel_kb())
    return ENTER_RESOLUTION


async def enter_resolution(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["resolution"] = update.message.text.strip()
    await update.message.reply_text("Тип панелі (IPS, VA, TN, OLED):", reply_markup=kb([
        ("IPS", "panel_IPS"), ("VA", "panel_VA"), ("TN", "panel_TN"), ("OLED", "panel_OLED")
    ]))
    return ENTER_PANEL_TYPE


async def enter_panel_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        context.user_data["panelType"] = update.callback_query.data.replace("panel_", "")
        await update.callback_query.edit_message_text("Частота оновлення (наприклад: 60Hz, 144Hz, 240Hz):")
    else:
        context.user_data["panelType"] = update.message.text.strip()
        await update.message.reply_text("Частота оновлення (наприклад: 60Hz, 144Hz, 240Hz):", reply_markup=cancel_kb())
    return ENTER_REFRESH_RATE


async def enter_refresh_rate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["refreshRate"] = update.message.text.strip()
    await update.message.reply_text("Підключення (наприклад: HDMI, DisplayPort, USB-C):", reply_markup=cancel_kb())
    return ENTER_CONNECTIVITY


async def enter_connectivity_monitor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["connectivity"] = update.message.text.strip()
    # Skip brightness/contrast/responseTime — use defaults
    context.user_data["brightness"] = "250 nits"
    context.user_data["contrast"] = "1000:1"
    context.user_data["responseTime"] = "5ms"
    await update.message.reply_text("Стан товару:", reply_markup=kb([(c, f"cond_{c}") for c in CONDITIONS]))
    return ENTER_CONDITION


# ─── ACCESSORY FLOW ────────────────────────────────────────────────────────────
async def enter_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["type"] = update.message.text.strip()
    cat = context.user_data["category"]
    if cat == "smartDevices":
        await update.message.reply_text("Бренд (наприклад: Samsung, Apple, Xiaomi):", reply_markup=cancel_kb())
        return ENTER_BRAND
    await update.message.reply_text("Бренд (наприклад: Logitech, Apple, Samsung):", reply_markup=cancel_kb())
    return ENTER_BRAND


async def enter_brand(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["brand"] = update.message.text.strip()
    cat = context.user_data["category"]
    if cat == "smartDevices":
        await update.message.reply_text("Підключення (наприклад: Bluetooth 5.0, WiFi):", reply_markup=cancel_kb())
        return ENTER_CONNECTIVITY
    await update.message.reply_text("Сумісність (наприклад: Universal, Apple, Lenovo):", reply_markup=cancel_kb())
    return ENTER_COMPATIBILITY


async def enter_compatibility(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["compatibility"] = update.message.text.strip()
    await update.message.reply_text("Колір (наприклад: Чорний, Білий, Сірий):", reply_markup=cancel_kb())
    return ENTER_COLOR


async def enter_color(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["color"] = update.message.text.strip()
    await update.message.reply_text("Стан товару:", reply_markup=kb([(c, f"cond_{c}") for c in CONDITIONS]))
    return ENTER_CONDITION


# ─── SMART DEVICE FLOW ─────────────────────────────────────────────────────────
async def enter_connectivity_smart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["connectivity"] = update.message.text.strip()
    await update.message.reply_text("Батарея (наприклад: 5 днів, 20 годин):", reply_markup=cancel_kb())
    return ENTER_BATTERY


async def enter_battery(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["battery"] = update.message.text.strip()
    cat = context.user_data["category"]
    if cat == "tablets":
        await update.message.reply_text("Камера (наприклад: 12MP, 8MP):", reply_markup=skip_kb())
        return ENTER_CAMERA
    await update.message.reply_text("Основні функції (наприклад: GPS, пульс, вологозахист):", reply_markup=skip_kb())
    return ENTER_FEATURES


async def enter_camera(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        context.user_data["camera"] = "Unknown"
        await update.callback_query.edit_message_text("Операційна система (наприклад: iPadOS 17, Android 14):")
    else:
        context.user_data["camera"] = update.message.text.strip()
        await update.message.reply_text("Операційна система (наприклад: iPadOS 17, Android 14):", reply_markup=cancel_kb())
    return ENTER_OS


async def enter_features(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        context.user_data["features"] = "N/A"
        await update.callback_query.edit_message_text("Сумісність (наприклад: iOS/Android, Universal):")
    else:
        context.user_data["features"] = update.message.text.strip()
        await update.message.reply_text("Сумісність (наприклад: iOS/Android, Universal):", reply_markup=cancel_kb())
    return ENTER_COMPATIBILITY


async def enter_compatibility_smart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["compatibility"] = update.message.text.strip()
    await update.message.reply_text("Стан товару:", reply_markup=kb([(c, f"cond_{c}") for c in CONDITIONS]))
    return ENTER_CONDITION


# ─── COMMON FLOW ───────────────────────────────────────────────────────────────
async def enter_condition(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "cancel":
        await query.edit_message_text("❌ Скасовано.")
        return ConversationHandler.END

    context.user_data["condition"] = query.data.replace("cond_", "")
    await query.edit_message_text(
        "Гарантія:",
        reply_markup=kb([(w, f"warr_{w}") for w in WARRANTIES])
    )
    return ENTER_WARRANTY


async def enter_warranty(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "cancel":
        await query.edit_message_text("❌ Скасовано.")
        return ConversationHandler.END

    context.user_data["warranty"] = query.data.replace("warr_", "")
    await query.edit_message_text("Ціна в гривнях (тільки цифри, наприклад: 14700):")
    return ENTER_PRICE


async def enter_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().replace(" ", "").replace(",", "")
    if not text.isdigit():
        await update.message.reply_text("Введи тільки цифри! Наприклад: 14700")
        return ENTER_PRICE
    context.user_data["price"] = int(text)
    await update.message.reply_text(
        "Знижка у відсотках (0 якщо без знижки):",
        reply_markup=kb([("0%", "disc_0"), ("5%", "disc_5"), ("10%", "disc_10"),
                         ("15%", "disc_15"), ("20%", "disc_20"), ("25%", "disc_25"),
                         ("30%", "disc_30"), ("50%", "disc_50")])
    )
    return ENTER_DISCOUNT


async def enter_discount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        context.user_data["discountPercent"] = int(update.callback_query.data.replace("disc_", ""))
        await update.callback_query.edit_message_text("Надішли фото товару (або натисни Пропустити):", reply_markup=skip_kb())
    else:
        text = update.message.text.strip().replace("%", "")
        context.user_data["discountPercent"] = int(text) if text.isdigit() else 0
        await update.message.reply_text("Надішли фото товару (або натисни Пропустити):", reply_markup=skip_kb())
    return ENTER_PHOTO


async def enter_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        context.user_data["imageUrl"] = None
        await update.callback_query.edit_message_text("Опис товару (або натисни Пропустити):", reply_markup=skip_kb())
    elif update.message.photo:
        photo = update.message.photo[-1]
        file = await photo.get_file()
        photo_bytes = await file.download_as_bytearray()
        url = await upload_photo_to_site(bytes(photo_bytes), f"product_{photo.file_id}.jpg")
        if url:
            context.user_data["imageUrl"] = url
            await update.message.reply_text(f"✅ Фото завантажено!\n\nОпис товару (або натисни Пропустити):", reply_markup=skip_kb())
        else:
            context.user_data["imageUrl"] = None
            await update.message.reply_text("⚠️ Не вдалось завантажити фото. Продовжуємо без нього.\n\nОпис товару:", reply_markup=skip_kb())
    else:
        await update.message.reply_text("Надішли фото або натисни Пропустити:", reply_markup=skip_kb())
        return ENTER_PHOTO
    return ENTER_DESCRIPTION


async def enter_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        context.user_data["description"] = None
    else:
        context.user_data["description"] = update.message.text.strip()

    summary = format_summary(context.user_data)
    confirm_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Опублікувати", callback_data="confirm_yes")],
        [InlineKeyboardButton("❌ Скасувати", callback_data="confirm_no")],
    ])

    if update.callback_query:
        await update.callback_query.edit_message_text(summary + "\n\nПублікуємо?", reply_markup=confirm_kb)
    else:
        await update.message.reply_text(summary + "\n\nПублікуємо?", reply_markup=confirm_kb)
    return CONFIRM


async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "confirm_no":
        await query.edit_message_text("❌ Скасовано. Напиши /start щоб почати знову.")
        return ConversationHandler.END

    await query.edit_message_text("⏳ Публікую...")

    data = dict(context.user_data)

    # Send to site
    site_ok = await send_to_site(data)

    # Publish to channel
    channel_ok = await publish_to_channel(
        query.get_bot(),
        data,
        data.get("imageUrl")
    )

    result_lines = ["📊 Результат:"]
    result_lines.append(f"{'✅' if site_ok else '❌'} Сайт — {'додано' if site_ok else 'помилка'}")
    result_lines.append(f"{'✅' if channel_ok else '❌'} Telegram канал — {'опубліковано' if channel_ok else 'помилка'}")
    result_lines.append("")
    result_lines.append("Натисни /start щоб додати ще один товар.")

    await query.edit_message_text("\n".join(result_lines))
    context.user_data.clear()
    return ConversationHandler.END


async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Скасовано. Напиши /start щоб почати знову.")
    return ConversationHandler.END


# ─── ROUTING: CONNECTIVITY STATE ───────────────────────────────────────────────
async def enter_connectivity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Route connectivity input based on category."""
    cat = context.user_data.get("category")
    if cat == "monitors":
        return await enter_connectivity_monitor(update, context)
    elif cat == "smartDevices":
        return await enter_connectivity_smart(update, context)
    else:
        context.user_data["connectivity"] = update.message.text.strip()
        await update.message.reply_text("Стан товару:", reply_markup=kb([(c, f"cond_{c}") for c in CONDITIONS]))
        return ENTER_CONDITION


async def enter_compatibility_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Route compatibility input based on category."""
    cat = context.user_data.get("category")
    if cat == "smartDevices":
        return await enter_compatibility_smart(update, context)
    else:
        return await enter_compatibility(update, context)


# ─── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    if not BOT_TOKEN:
        logger.error("ADMIN_BOT_TOKEN not set!")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSE_CATEGORY: [CallbackQueryHandler(choose_category)],
            CHOOSE_SUBCATEGORY: [CallbackQueryHandler(choose_subcategory)],
            ENTER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_name)],
            ENTER_PROCESSOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_processor)],
            ENTER_GPU: [
                CallbackQueryHandler(enter_gpu, pattern="^skip$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_gpu),
            ],
            ENTER_RAM: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_ram)],
            ENTER_STORAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_storage)],
            ENTER_DISPLAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_display)],
            ENTER_OS: [
                CallbackQueryHandler(enter_os, pattern="^skip$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_os),
            ],
            ENTER_SIZE: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_size)],
            ENTER_RESOLUTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_resolution)],
            ENTER_PANEL_TYPE: [
                CallbackQueryHandler(enter_panel_type, pattern="^panel_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_panel_type),
            ],
            ENTER_REFRESH_RATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_refresh_rate)],
            ENTER_CONNECTIVITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_connectivity)],
            ENTER_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_type)],
            ENTER_BRAND: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_brand)],
            ENTER_COMPATIBILITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_compatibility_router)],
            ENTER_COLOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_color)],
            ENTER_BATTERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_battery)],
            ENTER_FEATURES: [
                CallbackQueryHandler(enter_features, pattern="^skip$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_features),
            ],
            ENTER_CAMERA: [
                CallbackQueryHandler(enter_camera, pattern="^skip$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_camera),
            ],
            ENTER_CONDITION: [CallbackQueryHandler(enter_condition, pattern="^cond_")],
            ENTER_WARRANTY: [CallbackQueryHandler(enter_warranty, pattern="^warr_")],
            ENTER_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_price)],
            ENTER_DISCOUNT: [
                CallbackQueryHandler(enter_discount, pattern="^disc_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_discount),
            ],
            ENTER_PHOTO: [
                CallbackQueryHandler(enter_photo, pattern="^skip$"),
                MessageHandler(filters.PHOTO, enter_photo),
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_photo),
            ],
            ENTER_DESCRIPTION: [
                CallbackQueryHandler(enter_description, pattern="^skip$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_description),
            ],
            CONFIRM: [CallbackQueryHandler(confirm, pattern="^confirm_")],
        },
        fallbacks=[CommandHandler("cancel", cancel_cmd)],
        allow_reentry=True,
    )

    app.add_handler(conv)

    logger.info("Hugo Admin Bot started!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
