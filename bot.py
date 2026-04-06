#!/usr/bin/env python3
"""
Hugo Media Admin Bot - Dynamic Filter Version
Додає товари на сайт з динамічними фільтрами як кнопки
"""

import os
import json
import logging
import requests
import asyncio
import io
import uuid
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters
)
from ai_description_generator import generate_description_sync

logging.basicConfig(
    format='%(asctime)s | %(levelname)s | %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ─── CONFIG ────────────────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN", "")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
SITE_URL = os.getenv("SITE_URL", "https://web-production-036f7.up.railway.app")
BOT_API_SECRET = os.getenv("BOT_API_SECRET", "hugo_bot_secret_2024")
TG_CHANNEL = os.getenv("TG_CHANNEL", "@hugo_media_shop")

# ─── S3 UPLOAD HELPER ──────────────────────────────────────────────────────────
async def upload_photo_to_s3(file, bot) -> str:
    """
    Download photo from Telegram and upload to S3 via website API
    Returns the public URL
    """
    try:
        # Download file directly from Telegram
        photo_bytes = await file.download_as_bytearray()
        
        # Generate unique filename
        filename = f"product_{uuid.uuid4().hex[:8]}.jpg"
        
        # Upload to S3 via website API using requests in executor
        loop = asyncio.get_event_loop()
        
        def upload_sync():
            try:
                files = {'file': (filename, io.BytesIO(photo_bytes), 'image/jpeg')}
                headers = {'X-Bot-Secret': BOT_API_SECRET}
                
                response = requests.post(
                    f"{SITE_URL}/api/bot/upload",
                    files=files,
                    headers=headers,
                    timeout=30
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return data.get('url', '')
                else:
                    logger.error(f"❌ Upload error (status {response.status_code}): {response.text}")
                    return ""
            except Exception as e:
                logger.error(f"❌ Upload exception: {e}")
                return ""
        
        try:
            image_url = await loop.run_in_executor(None, upload_sync)
            if image_url:
                logger.info(f"✅ Фото завантажено на S3: {image_url}")
            return image_url
        except Exception as e:
            logger.error(f"❌ Executor error: {e}")
            return ""
    except Exception as e:
        logger.error(f"❌ Помилка S3 upload: {e}")
        return ""

# ─── STATES ────────────────────────────────────────────────────────────────────
(
    CHOOSE_CATEGORY,
    ENTER_NAME,
    ENTER_PRICE,
    ENTER_DISCOUNT,
    ENTER_PHOTO,
    ENTER_DESCRIPTION,
    # Laptop filters
    CHOOSE_LAPTOP_DISPLAY,
    CHOOSE_LAPTOP_RAM,
    CHOOSE_LAPTOP_PROCESSOR,
    CHOOSE_LAPTOP_BRAND,
    # Monitor filters
    CHOOSE_MONITOR_SIZE,
    CHOOSE_MONITOR_RESOLUTION,
    CHOOSE_MONITOR_REFRESH,
    CHOOSE_MONITOR_PANEL,
    # Tablet filters
    CHOOSE_TABLET_STORAGE,
    CHOOSE_TABLET_RAM,
    # SmartDevice filters
    CHOOSE_DEVICE_TYPE,
    # Accessory filters
    CHOOSE_ACCESSORY_TYPE,
    # Publish
    CHOOSE_PUBLISH,
    CONFIRM,
    CHOOSE_LAPTOP_GRAPHICS,
    CHOOSE_LAPTOP_STORAGE,
    CHOOSE_LAPTOP_WARRANTY,
    CHOOSE_LAPTOP_CATEGORIES,
    ENTER_CUSTOM_DISPLAY,
    ENTER_CUSTOM_RAM,
    ENTER_CUSTOM_PROCESSOR,
    ENTER_CUSTOM_GRAPHICS,
    ENTER_CUSTOM_STORAGE,
    ENTER_CUSTOM_WARRANTY,
    ENTER_CUSTOM_CATEGORY,
) = range(31)

# ─── FILTER OPTIONS (from website) ────────────────────────────────────────────
LAPTOP_FILTERS = {
    "display": ["11\"", "12\"", "13\"", "14\"", "15\"", "16\"", "17\"", "18\""],
    "ram": ["4 GB", "8 GB", "16 GB", "32 GB", "64 GB", "128 GB"],
    "processor": ["Intel Core i3", "Intel Core i5", "Intel Core i7", "Intel Core i9", "Intel Core Ultra 5", "Intel Core Ultra 7", "Intel Core Ultra 9", "AMD Ryzen 3", "AMD Ryzen 5", "AMD Ryzen 7", "AMD Ryzen 9"],
    "graphics": ["Intel UHD", "Intel Iris Xe", "NVIDIA GTX 1650", "NVIDIA RTX 4050", "NVIDIA RTX 4060", "NVIDIA RTX 4070", "NVIDIA RTX 4090", "AMD Radeon"],
    "brand": ["Dell", "HP", "Lenovo", "ASUS", "Acer", "MSI", "Alienware", "Apple", "Razer", "GIGABYTE"],
    "warranty": ["1 рік", "2 роки", "3 роки", "5 років", "Без гарантії"],
    "categories": ["Нові ноутбуки", "Ноутбуки після оренди", "Пропозиція для компаній", "Акції"],
    "storage": ["256 GB SSD", "512 GB SSD", "1 TB SSD", "2 TB SSD", "256 GB HDD", "512 GB HDD", "1 TB HDD"],
}

MONITOR_FILTERS = {
    "size": ["17\"", "19\"", "21\"", "22\"", "24\"", "27\"", "30\"", "32\"", "34\"", "38\"", "40\""],
    "resolution": ["720p", "1080p", "1440p", "2160p (4K)", "3440x1440", "5120x1440"],
    "refresh": ["60Hz", "75Hz", "100Hz", "120Hz", "144Hz", "165Hz", "240Hz", "360Hz"],
    "panel": ["IPS", "VA", "TN", "OLED", "Nano Cell", "QLED", "Mini-LED"],
}

CATEGORIES = {
    "laptops": "💻 Ноутбук",
    "monitors": "🖥 Монітор",
    "tablets": "📱 Планшет",
    "smartDevices": "⌚ Смарт девайс",
    "accessories": "🎧 Аксесуар",
}

CONDITIONS = ["Новий", "Б/у відмінний", "Б/у хороший", "Б/у задовільний"]
WARRANTIES = ["Без гарантії", "1 місяць", "3 місяці", "6 місяців", "1 рік", "2 роки", "3 роки", "5 років"]

# ─── HELPERS ───────────────────────────────────────────────────────────────────
def is_owner(update: Update) -> bool:
    return update.effective_user.id == OWNER_ID

def kb(buttons: list, columns: int = 2) -> InlineKeyboardMarkup:
    """Create keyboard with specified number of columns"""
    rows = []
    row = []
    for i, (text, data) in enumerate(buttons):
        row.append(InlineKeyboardButton(text, callback_data=data))
        if len(row) == columns or i == len(buttons) - 1:
            rows.append(row)
            row = []
    return InlineKeyboardMarkup(rows)

def skip_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("⏭ Пропустити", callback_data="skip")]])

# ─── START ─────────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_owner(update):
        await update.message.reply_text("❌ Тільки адміністратор може використовувати цього бота")
        return ConversationHandler.END

    buttons = [(f"{emoji} {label}", cat) for cat, (emoji, label) in 
               [(k, v.split(" ", 1)) for k, v in CATEGORIES.items()]]
    
    await update.message.reply_text(
        "🛍 Виберіть категорію товару:",
        reply_markup=kb(buttons, columns=2)
    )
    return CHOOSE_CATEGORY

# ─── CATEGORY SELECTION ────────────────────────────────────────────────────────
async def choose_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    context.user_data["category"] = query.data
    
    await query.edit_message_text(
        "📝 Введіть назву товару:",
        reply_markup=skip_kb()
    )
    return ENTER_NAME

# ─── NAME ──────────────────────────────────────────────────────────────────────
async def enter_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
        context.user_data["name"] = ""
        return await enter_price(update, context)
    
    context.user_data["name"] = update.message.text
    
    await update.message.reply_text(
        "💵 Ціна в ZŁOTY (zł) (тільки цифри, напрклад: 1500):",
        reply_markup=skip_kb()
    )
    return ENTER_PRICE

# ─── PRICE ────────────────────────────────────────────────────────────────────
async def enter_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
        context.user_data["price"] = 0
    else:
        try:
            context.user_data["price"] = float(update.message.text)
        except ValueError:
            await update.message.reply_text("❌ Будь ласка, введіть коректну ціну")
            return ENTER_PRICE
    
    category = context.user_data.get("category")
    
    if category == "laptops":
        buttons = [(size, f"laptop_display_{size}") for size in LAPTOP_FILTERS["display"]]
        await update.message.reply_text(
            "📏 Виберіть розмір дисплея:",
            reply_markup=kb(buttons, columns=3)
        ) if not update.callback_query else await update.callback_query.edit_message_text(
            "📏 Виберіть розмір дисплея:",
            reply_markup=kb(buttons, columns=3)
        )
        return CHOOSE_LAPTOP_DISPLAY
    
    elif category == "monitors":
        buttons = [(size, f"monitor_size_{size}") for size in MONITOR_FILTERS["size"]]
        msg_text = "📏 Виберіть розмір монітора:" if not update.callback_query else None
        if update.callback_query:
            await update.callback_query.edit_message_text(
                "📏 Виберіть розмір монітора:",
                reply_markup=kb(buttons, columns=3)
            )
        else:
            await update.message.reply_text(msg_text, reply_markup=kb(buttons, columns=3))
        return CHOOSE_MONITOR_SIZE
    
    else:
        # For other categories, ask for discount
        if update.callback_query:
            await update.callback_query.edit_message_text(
                "💰 Знижка (%) (або натисніть Пропустити):",
                reply_markup=skip_kb()
            )
        else:
            await update.message.reply_text(
                "💰 Знижка (%) (або натисніть Пропустити):",
                reply_markup=skip_kb()
            )
        return ENTER_DISCOUNT

# ─── DISCOUNT ──────────────────────────────────────────────────────────────────
async def choose_laptop_storage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Choose laptop storage"""
    user_data = context.user_data
    storage_options = LAPTOP_FILTERS["storage"]
    
    keyboard = [[InlineKeyboardButton(opt, callback_data=f"storage_{opt}")] for opt in storage_options]
    keyboard.append([InlineKeyboardButton("Пропустити", callback_data="storage_skip")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text(
        "💾 Оберіть обсяг пам'яті:",
        reply_markup=reply_markup
    )
    return CHOOSE_LAPTOP_WARRANTY

async def choose_laptop_warranty(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Choose laptop warranty"""
    user_data = context.user_data
    
    # Store storage from callback
    query = update.callback_query
    if query.data != "storage_skip":
        user_data["storage"] = query.data.replace("storage_", "")
    
    warranty_options = LAPTOP_FILTERS["warranty"]
    keyboard = [[InlineKeyboardButton(opt, callback_data=f"warranty_{opt}")] for opt in warranty_options]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "🛡️ Оберіть гарантію:",
        reply_markup=reply_markup
    )
    return CHOOSE_LAPTOP_CATEGORIES

async def choose_laptop_categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Choose laptop categories"""
    user_data = context.user_data
    
    # Store warranty from callback
    query = update.callback_query
    user_data["warranty"] = query.data.replace("warranty_", "")
    
    categories_options = LAPTOP_FILTERS["categories"]
    keyboard = [[InlineKeyboardButton(opt, callback_data=f"category_{opt}")] for opt in categories_options]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "📂 Оберіть категорію:",
        reply_markup=reply_markup
    )
    return ENTER_DISCOUNT

async def enter_discount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
        context.user_data["discount"] = 0
    else:
        try:
            discount = float(update.message.text)
            if discount < 0 or discount > 100:
                await update.message.reply_text("❌ Знижка має бути від 0 до 100%")
                return ENTER_DISCOUNT
            context.user_data["discount"] = discount
        except ValueError:
            await update.message.reply_text("❌ Будь ласка, введіть число")
            return ENTER_DISCOUNT
    
    # Ask for photo
    if update.callback_query:
        await update.callback_query.edit_message_text(
            "📸 Надішліть фото товару (або натисніть Пропустити):",
            reply_markup=skip_kb()
        )
    else:
        await update.message.reply_text(
            "📸 Надішліть фото товару (або натисніть Пропустити):",
            reply_markup=skip_kb()
        )
    return ENTER_PHOTO

# ─── LAPTOP FILTERS ────────────────────────────────────────────────────────────
async def choose_laptop_display(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    if query.data == "laptop_display_custom":
        await query.edit_message_text("📱 Напишіть діагональ дисплея (наприклад: 14\"):\n\nЛюбий текст, який ви введете:")
        return ENTER_CUSTOM_DISPLAY
    
    context.user_data["display"] = query.data.replace("laptop_display_", "")
    
    buttons = [(ram, f"laptop_ram_{ram}") for ram in LAPTOP_FILTERS["ram"]]
    buttons.append(("✏️ Написати вручну", "laptop_ram_custom"))
    await query.edit_message_text(
        "🧠 Виберіть обсяг RAM:",
        reply_markup=kb(buttons, columns=2)
    )
    return CHOOSE_LAPTOP_RAM

async def choose_laptop_ram(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    if query.data == "laptop_ram_custom":
        await query.edit_message_text("🧠 Напишіть ОЗУ (наприклад: 16 GB):")
        return ENTER_CUSTOM_RAM
    
    context.user_data["ram"] = query.data.replace("laptop_ram_", "")
    
    buttons = [(proc, f"laptop_proc_{proc}") for proc in LAPTOP_FILTERS["processor"]]
    buttons.append(("✏️ Написати вручну", "laptop_proc_custom"))
    await query.edit_message_text(
        "⚙️ Виберіть процесор:",
        reply_markup=kb(buttons, columns=2)
    )
    return CHOOSE_LAPTOP_PROCESSOR

async def choose_laptop_processor(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    if query.data == "laptop_proc_custom":
        await query.edit_message_text("⚙️ Напишіть процесор (наприклад: Intel Core i7):")
        return ENTER_CUSTOM_PROCESSOR
    
    context.user_data["processor"] = query.data.replace("laptop_proc_", "")
    
    buttons = [(brand, f"laptop_brand_{brand}") for brand in LAPTOP_FILTERS["brand"]]
    await query.edit_message_text(
        "🏙️ Виберіть бренд:",
        reply_markup=kb(buttons, columns=2)
    )
    return CHOOSE_LAPTOP_BRAND

async def choose_laptop_brand(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    context.user_data["brand"] = query.data.replace("laptop_brand_", "")
    
    buttons = [(gpu, f"laptop_gpu_{gpu}") for gpu in LAPTOP_FILTERS["graphics"]]
    buttons.append(("✏️ Написати вручну", "laptop_gpu_custom"))
    await query.edit_message_text(
        "🎮 Виберіть відеокарту:",
        reply_markup=kb(buttons, columns=2)
    )
    return CHOOSE_LAPTOP_GRAPHICS

async def choose_laptop_graphics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    if query.data == "laptop_gpu_custom":
        await query.edit_message_text("🎮 Напишіть відеокарту (наприклад: NVIDIA RTX 4060):")
        return ENTER_CUSTOM_GRAPHICS
    
    context.user_data["graphicsCard"] = query.data.replace("laptop_gpu_", "")
    
    buttons = [(storage, f"laptop_storage_{storage}") for storage in LAPTOP_FILTERS["storage"]]
    buttons.append(("✏️ Написати вручну", "laptop_storage_custom"))
    await query.edit_message_text(
        "💾 Виберіть обсяг пам'яті:",
        reply_markup=kb(buttons, columns=2)
    )
    return CHOOSE_LAPTOP_STORAGE

async def enter_custom_display(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle custom display input"""
    context.user_data["display"] = update.message.text
    
    buttons = [(ram, f"laptop_ram_{ram}") for ram in LAPTOP_FILTERS["ram"]]
    buttons.append(("✏️ Написати вручну", "laptop_ram_custom"))
    await update.message.reply_text(
        "🧠 Виберіть обсяг RAM:",
        reply_markup=kb(buttons, columns=2)
    )
    return CHOOSE_LAPTOP_RAM

async def enter_custom_ram(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle custom RAM input"""
    context.user_data["ram"] = update.message.text
    
    buttons = [(proc, f"laptop_proc_{proc}") for proc in LAPTOP_FILTERS["processor"]]
    buttons.append(("✏️ Написати вручну", "laptop_proc_custom"))
    await update.message.reply_text(
        "⚙️ Виберіть процесор:",
        reply_markup=kb(buttons, columns=2)
    )
    return CHOOSE_LAPTOP_PROCESSOR

async def enter_custom_processor(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle custom processor input"""
    context.user_data["processor"] = update.message.text
    
    buttons = [(brand, f"laptop_brand_{brand}") for brand in LAPTOP_FILTERS["brand"]]
    await update.message.reply_text(
        "🏙️ Виберіть бренд:",
        reply_markup=kb(buttons, columns=2)
    )
    return CHOOSE_LAPTOP_BRAND

async def enter_custom_graphics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle custom graphics input"""
    context.user_data["graphicsCard"] = update.message.text
    
    buttons = [(storage, f"laptop_storage_{storage}") for storage in LAPTOP_FILTERS["storage"]]
    buttons.append(("✏️ Написати вручну", "laptop_storage_custom"))
    await update.message.reply_text(
        "💾 Виберіть обсяг пам'яті:",
        reply_markup=kb(buttons, columns=2)
    )
    return CHOOSE_LAPTOP_STORAGE

async def choose_laptop_storage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Choose laptop storage"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "laptop_storage_custom":
        await query.edit_message_text("💾 Напишіть обсяг пам'яті (наприклад: 512 GB SSD):")
        return ENTER_CUSTOM_STORAGE
    
    context.user_data["storage"] = query.data.replace("laptop_storage_", "")
    
    buttons = [(warranty, f"laptop_warranty_{warranty}") for warranty in LAPTOP_FILTERS["warranty"]]
    buttons.append(("✏️ Написати вручну", "laptop_warranty_custom"))
    await query.edit_message_text(
        "🛡️ Виберіть гарантію:",
        reply_markup=kb(buttons, columns=2)
    )
    return CHOOSE_LAPTOP_WARRANTY

async def enter_custom_storage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle custom storage input"""
    context.user_data["storage"] = update.message.text
    
    buttons = [(warranty, f"laptop_warranty_{warranty}") for warranty in LAPTOP_FILTERS["warranty"]]
    buttons.append(("✏️ Написати вручну", "laptop_warranty_custom"))
    await update.message.reply_text(
        "🛡️ Виберіть гарантію:",
        reply_markup=kb(buttons, columns=2)
    )
    return CHOOSE_LAPTOP_WARRANTY

async def choose_laptop_warranty(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Choose laptop warranty"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "laptop_warranty_custom":
        await query.edit_message_text("🛡️ Напишіть гарантію (наприклад: 2 роки):")
        return ENTER_CUSTOM_WARRANTY
    
    context.user_data["warranty"] = query.data.replace("laptop_warranty_", "")
    
    buttons = [(cat, f"laptop_category_{cat}") for cat in LAPTOP_FILTERS["categories"]]
    buttons.append(("✏️ Написати вручну", "laptop_category_custom"))
    await query.edit_message_text(
        "📂 Виберіть категорію:",
        reply_markup=kb(buttons, columns=2)
    )
    return CHOOSE_LAPTOP_CATEGORIES

async def enter_custom_warranty(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle custom warranty input"""
    context.user_data["warranty"] = update.message.text
    
    buttons = [(cat, f"laptop_category_{cat}") for cat in LAPTOP_FILTERS["categories"]]
    buttons.append(("✏️ Написати вручну", "laptop_category_custom"))
    await update.message.reply_text(
        "📂 Виберіть категорію:",
        reply_markup=kb(buttons, columns=2)
    )
    return CHOOSE_LAPTOP_CATEGORIES

async def choose_laptop_categories(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Choose laptop categories"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "laptop_category_custom":
        await query.edit_message_text("📂 Напишіть категорію (наприклад: Спеціальні пропозиції):")
        return ENTER_CUSTOM_CATEGORY
    
    context.user_data["categories"] = query.data.replace("laptop_category_", "")
    
    await query.edit_message_text(
        "💰 Знижка (%) (або натисніть Пропустити):",
        reply_markup=skip_kb()
    )
    return ENTER_DISCOUNT

async def enter_custom_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle custom category input"""
    context.user_data["categories"] = update.message.text
    
    await update.message.reply_text(
        "💰 Знижка (%) (або натисніть Пропустити):",
        reply_markup=skip_kb()
    )
    return ENTER_DISCOUNT

# ─── MONITOR FILTERS ──────────────────────────────────────────────────────────
async def choose_monitor_size(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    context.user_data["size"] = query.data.replace("monitor_size_", "")
    
    buttons = [(res, f"monitor_res_{res}") for res in MONITOR_FILTERS["resolution"]]
    await query.edit_message_text(
        "🎨 Виберіть розширення:",
        reply_markup=kb(buttons, columns=2)
    )
    return CHOOSE_MONITOR_RESOLUTION

async def choose_monitor_resolution(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    context.user_data["resolution"] = query.data.replace("monitor_res_", "")
    
    buttons = [(hz, f"monitor_hz_{hz}") for hz in MONITOR_FILTERS["refresh"]]
    await query.edit_message_text(
        "⚡ Виберіть частоту оновлення:",
        reply_markup=kb(buttons, columns=3)
    )
    return CHOOSE_MONITOR_REFRESH

async def choose_monitor_refresh(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    context.user_data["refreshRate"] = query.data.replace("monitor_hz_", "")
    
    buttons = [(panel, f"monitor_panel_{panel}") for panel in MONITOR_FILTERS["panel"]]
    await query.edit_message_text(
        "🖼️ Виберіть тип матриці:",
        reply_markup=kb(buttons, columns=2)
    )
    return CHOOSE_MONITOR_PANEL

async def choose_monitor_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    context.user_data["panelType"] = query.data.replace("monitor_panel_", "")
    
    await query.edit_message_text(
        "📸 Надішліть фото товару (або натисніть Пропустити):",
        reply_markup=skip_kb()
    )
    return ENTER_PHOTO

# ─── PHOTO ────────────────────────────────────────────────────────────────────
async def enter_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
        context.user_data["imageUrl"] = ""
    elif update.message.photo:
        # Show loading message
        loading_msg = await update.message.reply_text("⏳ Завантажую фото на S3...")
        
        try:
            file = await update.message.photo[-1].get_file()
            # Upload photo to S3
            image_url = await upload_photo_to_s3(file, context.bot)
            
            if image_url:
                context.user_data["imageUrl"] = image_url
                await loading_msg.delete()
                await update.message.reply_text(
                    "✅ Фото завантажено!\n📝 Опис товару (або натисніть Пропустити):",
                    reply_markup=skip_kb()
                )
            else:
                context.user_data["imageUrl"] = ""
                await loading_msg.delete()
                await update.message.reply_text(
                    "❌ Помилка завантаження фото. Спробуйте ще раз.\n📝 Опис товару (або натисніть Пропустити):",
                    reply_markup=skip_kb()
                )
        except Exception as e:
            logger.error(f"❌ Помилка при завантаженні фото: {e}")
            context.user_data["imageUrl"] = ""
            await loading_msg.delete()
            await update.message.reply_text(
                "❌ Помилка при завантаженні фото.\n📝 Опис товару (або натисніть Пропустити):",
                reply_markup=skip_kb()
            )
    else:
        context.user_data["imageUrl"] = ""
        await update.message.reply_text(
            "📝 Опис товару (або натисніть Пропустити):",
            reply_markup=skip_kb()
        )
    
    return ENTER_DESCRIPTION

# ─── DESCRIPTION ──────────────────────────────────────────────────────────────
async def enter_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
        # User skipped - generate AI description
        await update.callback_query.edit_message_text(
            "🤖 Генерую опис за допомогою AI...\n⏳ Це займе кілька секунд"
        )
        
        # Generate description using ChatGPT
        product_data = context.user_data
        ai_description = generate_description_sync(product_data)
        
        if ai_description:
            context.user_data["description"] = ai_description
            logger.info(f"✅ AI description generated for {product_data.get('name', 'product')}")
        else:
            context.user_data["description"] = ""
            logger.warning(f"⚠️ AI description generation failed for {product_data.get('name', 'product')}")
    else:
        context.user_data["description"] = update.message.text
    
    # Show summary and publish options
    await show_summary(update, context)
    return CHOOSE_PUBLISH

async def show_summary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = context.user_data
    
    summary = f"""
📦 **Резюме товару:**

🏷️ Назва: {data.get('name', 'N/A')}
💵 Ціна: {data.get('price', 0)} zł
📝 Опис: {data.get('description', 'N/A')[:100]}...

**Публікувати?**
"""
    
    buttons = [
        ("🌐 На сайт", "publish_site"),
        ("📢 В TG", "publish_tg"),
        ("❌ Скасувати", "cancel"),
    ]
    
    if update.callback_query:
        await update.callback_query.edit_message_text(summary, reply_markup=kb(buttons, columns=2))
    else:
        await update.message.reply_text(summary, reply_markup=kb(buttons, columns=2))

# ─── PUBLISH ──────────────────────────────────────────────────────────────────
async def choose_publish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    action = query.data
    
    if action == "cancel":
        await query.edit_message_text("❌ Скасовано. Натисніть /start для нового товару")
        return ConversationHandler.END
    
    if action == "publish_site":
        await publish_to_site(update, context)
    elif action == "publish_tg":
        await publish_to_telegram(update, context)
    
    await query.edit_message_text("✅ Готово! Натисніть /start для нового товару")
    return ConversationHandler.END

async def publish_to_site(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = context.user_data
    category = data.get("category", "laptops")
    
    payload = {
        "name": data.get("name", "Товар"),
        "price": data.get("price", 0),
        "discountPercent": data.get("discount", 0),
        "description": data.get("description", ""),
        "imageUrl": data.get("imageUrl", ""),
        "category": category,
        "categories": json.dumps(["new"]),
        "warranty": "3 роки",
        "condition": "Новий",
    }
    
    # Add category-specific fields
    if category == "laptops":
        payload.update({
            "display": data.get("display", ""),
            "ram": data.get("ram", ""),
            "processor": data.get("processor", ""),
            "brand": data.get("brand", ""),
            "graphicsCard": data.get("graphicsCard", ""),
            "storage": data.get("storage", ""),
            "warranty": data.get("warranty", "3 роки"),
            "categories": data.get("categories", "Нові ноутбуки"),
        })
    elif category == "monitors":
        payload.update({
            "size": data.get("size", ""),
            "resolution": data.get("resolution", ""),
            "refreshRate": data.get("refreshRate", ""),
            "panelType": data.get("panelType", ""),
        })
    
    try:
        response = requests.post(
            f"{SITE_URL}/api/bot/product",
            json=payload,
            headers={"X-Bot-Secret": BOT_API_SECRET},
            timeout=10
        )
        
        if response.status_code == 201:
            logger.info(f"✅ Товар додано на сайт: {response.json()}")
        else:
            logger.error(f"❌ Помилка: {response.text}")
    except Exception as e:
        logger.error(f"❌ Помилка запиту: {e}")

async def publish_to_telegram(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = context.user_data
    
    message = f"""
🛍 **{data.get('name', 'Новий товар')}**

💵 Ціна: {data.get('price', 0)} zł
📝 {data.get('description', 'Чудовий товар!')}

🔗 [Переглянути на сайті]({SITE_URL})
"""
    
    try:
        await context.bot.send_message(
            chat_id=TG_CHANNEL,
            text=message,
            parse_mode="Markdown"
        )
        logger.info(f"✅ Опубліковано в TG: {TG_CHANNEL}")
    except Exception as e:
        logger.error(f"❌ Помилка TG: {e}")

# ─── QUICK PRODUCT COMMANDS ───────────────────────────────────────────────────────
async def quick_add_laptop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Quick add laptop command"""
    await update.message.reply_text(
        "⚡ Швидке додавання ноутбука\n\n"
        "Формат: назва | ціна | опис | URL фото | процесор, ОЗУ, накопичувач\n\n"
        "Приклад:\n"
        "Dell Precision 7680 | 18000 | Професійний ноутбук | https://example.com/photo.jpg | Intel i9, 32GB, 1TB SSD"
    )
    context.user_data["quick_add_mode"] = "laptop"
    context.user_data["awaiting_quick_product"] = True

async def quick_add_monitor(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Quick add monitor command"""
    await update.message.reply_text(
        "⚡ Швидке додавання монітора\n\n"
        "Формат: назва | ціна | опис | URL фото | роздільна здатність, розмір, частота\n\n"
        "Приклад:\n"
        "Dell U2720Q | 5000 | 4K монітор | https://example.com/photo.jpg | 3840x2160, 27\", 60Hz"
    )
    context.user_data["quick_add_mode"] = "monitor"
    context.user_data["awaiting_quick_product"] = True

async def quick_add_tablet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Quick add tablet command"""
    await update.message.reply_text(
        "⚡ Швидке додавання планшета\n\n"
        "Формат: назва | ціна | опис | URL фото | процесор, ОЗУ, накопичувач\n\n"
        "Приклад:\n"
        "iPad Pro 12.9 | 8000 | Професійний планшет | https://example.com/photo.jpg | M2, 8GB, 256GB"
    )
    context.user_data["quick_add_mode"] = "tablet"
    context.user_data["awaiting_quick_product"] = True

async def quick_add_device(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Quick add smart device command"""
    await update.message.reply_text(
        "⚡ Швидке додавання смарт девайса\n\n"
        "Формат: назва | ціна | опис | URL фото | тип, бренд, особливості\n\n"
        "Приклад:\n"
        "Apple Watch Series 9 | 3000 | Смарт годинник | https://example.com/photo.jpg | Годинник, Apple, GPS+Cellular"
    )
    context.user_data["quick_add_mode"] = "device"
    context.user_data["awaiting_quick_product"] = True

async def handle_quick_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle quick product data"""
    if not context.user_data.get("awaiting_quick_product"):
        return
    
    try:
        parts = [p.strip() for p in update.message.text.split("|")] 
        if len(parts) < 4:
            await update.message.reply_text("❌ Невірний формат. Спробуйте ще раз.")
            return
        
        name = parts[0]
        price = float(parts[1])
        description = parts[2]
        image_url = parts[3]
        specs = parts[4] if len(parts) > 4 else ""
        
        mode = context.user_data.get("quick_add_mode", "laptop")
        category_map = {
            "laptop": "laptops",
            "monitor": "monitors",
            "tablet": "tablets",
            "device": "smartDevices"
        }
        category = category_map.get(mode, "laptops")
        
        payload = {
            "name": name,
            "price": price,
            "description": description,
            "imageUrl": image_url,
            "category": category,
            "categories": json.dumps(["new"]),
            "condition": "Новий",
            "warranty": "3 роки",
        }
        
        # Parse specs based on mode
        if specs:
            spec_parts = [s.strip() for s in specs.split(",")]
            if mode == "laptop" and len(spec_parts) >= 3:
                payload["processor"] = spec_parts[0]
                payload["ram"] = spec_parts[1]
                payload["storage"] = spec_parts[2]
            elif mode == "monitor" and len(spec_parts) >= 3:
                payload["resolution"] = spec_parts[0]
                payload["size"] = spec_parts[1]
                payload["refreshRate"] = spec_parts[2]
            elif mode == "tablet" and len(spec_parts) >= 3:
                payload["processor"] = spec_parts[0]
                payload["ram"] = spec_parts[1]
                payload["storage"] = spec_parts[2]
            elif mode == "device" and len(spec_parts) >= 3:
                payload["type"] = spec_parts[0]
                payload["brand"] = spec_parts[1]
                payload["features"] = spec_parts[2]
        
        # Send to API
        await update.message.chat.send_action("typing")
        
        response = requests.post(
            f"{SITE_URL}/api/bot/product",
            json=payload,
            headers={"X-Bot-Secret": BOT_API_SECRET},
            timeout=10
        )
        
        if response.status_code == 201:
            await update.message.reply_text(
                f"✅ Товар успішно додано!\n\n"
                f"📦 {name}\n"
                f"💰 {price} zł\n"
                f"📂 {category}"
            )
        else:
            error_data = response.json()
            await update.message.reply_text(
                f"❌ Помилка: {error_data.get('error', 'Unknown error')}"
            )
        
        context.user_data["awaiting_quick_product"] = False
    
    except ValueError as e:
        await update.message.reply_text(f"❌ Помилка: {str(e)}")
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text(f"❌ Помилка сервера: {str(e)}")

# ─── CANCEL ────────────────────────────────────────────────────────────────────
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("❌ Скасовано")
    return ConversationHandler.END

# ─── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    if not BOT_TOKEN:
        logger.error("❌ ADMIN_BOT_TOKEN не встановлено")
        return
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSE_CATEGORY: [CallbackQueryHandler(choose_category)],
            ENTER_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_name),
                CallbackQueryHandler(enter_name),
            ],
            ENTER_PRICE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_price),
                CallbackQueryHandler(enter_price),
            ],
            ENTER_DISCOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_discount),
                CallbackQueryHandler(enter_discount),
            ],
            CHOOSE_LAPTOP_DISPLAY: [CallbackQueryHandler(choose_laptop_display)],
            ENTER_CUSTOM_DISPLAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_custom_display)],
            CHOOSE_LAPTOP_RAM: [CallbackQueryHandler(choose_laptop_ram)],
            ENTER_CUSTOM_RAM: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_custom_ram)],
            CHOOSE_LAPTOP_PROCESSOR: [CallbackQueryHandler(choose_laptop_processor)],
            ENTER_CUSTOM_PROCESSOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_custom_processor)],
            CHOOSE_LAPTOP_BRAND: [CallbackQueryHandler(choose_laptop_brand)],
            CHOOSE_LAPTOP_GRAPHICS: [CallbackQueryHandler(choose_laptop_graphics)],
            ENTER_CUSTOM_GRAPHICS: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_custom_graphics)],
            CHOOSE_LAPTOP_STORAGE: [CallbackQueryHandler(choose_laptop_storage)],
            ENTER_CUSTOM_STORAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_custom_storage)],
            CHOOSE_LAPTOP_WARRANTY: [CallbackQueryHandler(choose_laptop_warranty)],
            ENTER_CUSTOM_WARRANTY: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_custom_warranty)],
            CHOOSE_LAPTOP_CATEGORIES: [CallbackQueryHandler(choose_laptop_categories)],
            ENTER_CUSTOM_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_custom_category)],
            CHOOSE_MONITOR_SIZE: [CallbackQueryHandler(choose_monitor_size)],
            CHOOSE_MONITOR_RESOLUTION: [CallbackQueryHandler(choose_monitor_resolution)],
            CHOOSE_MONITOR_REFRESH: [CallbackQueryHandler(choose_monitor_refresh)],
            CHOOSE_MONITOR_PANEL: [CallbackQueryHandler(choose_monitor_panel)],
            ENTER_PHOTO: [
                MessageHandler(filters.PHOTO, enter_photo),
                CallbackQueryHandler(enter_photo),
            ],
            ENTER_DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_description),
                CallbackQueryHandler(enter_description),
            ],
            CHOOSE_PUBLISH: [CallbackQueryHandler(choose_publish)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    app.add_handler(conv_handler)
    
    # Add quick product commands
    app.add_handler(CommandHandler("quick_laptop", quick_add_laptop))
    app.add_handler(CommandHandler("quick_monitor", quick_add_monitor))
    app.add_handler(CommandHandler("quick_tablet", quick_add_tablet))
    app.add_handler(CommandHandler("quick_device", quick_add_device))
    
    # Add message handler for quick product data (must be after conv_handler)
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & 
        (lambda u: u.effective_user.id == OWNER_ID and u.message.text.count("|") >= 3),
        handle_quick_product
    ))
    
    logger.info("🤖 Бот запущено")
    app.run_polling()

if __name__ == "__main__":
    main()
