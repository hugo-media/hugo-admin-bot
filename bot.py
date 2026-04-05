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

logging.basicConfig(
    format='%(asctime)s | %(levelname)s | %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ─── CONFIG ────────────────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN", "")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
SITE_URL = os.getenv("SITE_URL", "https://laptopcat-dmlwym6z.manus.space")
BOT_API_SECRET = os.getenv("BOT_API_SECRET", "hugo_bot_secret_2024")
TG_CHANNEL = os.getenv("TG_CHANNEL", "@hugo_media_shop")

# ─── S3 UPLOAD HELPER ──────────────────────────────────────────────────────────
async def upload_photo_to_s3(photo_file_path: str, bot) -> str:
    """
    Download photo from Telegram and upload to S3 via website API
    Returns the public URL
    """
    try:
        # Download file from Telegram
        file = await bot.get_file(photo_file_path)
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
            except asyncio.TimeoutError:
                logger.error(f"❌ Timeout при завантаженні фото на S3")
                return ""
    except Exception as e:
        logger.error(f"❌ Помилка S3 upload: {e}")
        return ""
    except Exception as e:
        logger.error(f"❌ Помилка S3 upload: {e}")
        return ""

# ─── STATES ────────────────────────────────────────────────────────────────────
(
    CHOOSE_CATEGORY,
    ENTER_NAME,
    ENTER_PRICE,
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
) = range(19)

# ─── FILTER OPTIONS (from website) ────────────────────────────────────────────
LAPTOP_FILTERS = {
    "display": ["13\"", "14\"", "15\"", "16\"", "17\"", "18\""],
    "ram": ["8 GB", "16 GB", "32 GB", "64 GB"],
    "processor": ["Intel Core i5", "Intel Core i7", "Intel Core i9", "Intel Core Ultra", "AMD Ryzen 5", "AMD Ryzen 7", "AMD Ryzen 9"],
    "brand": ["Dell", "HP", "Lenovo", "ASUS", "Acer", "MSI", "Alienware", "Apple"],
}

MONITOR_FILTERS = {
    "size": ["21\"", "22\"", "24\"", "27\"", "32\"", "34\"", "38\""],
    "resolution": ["1080p", "1440p", "2160p (4K)", "3440x1440"],
    "refresh": ["60Hz", "75Hz", "100Hz", "120Hz", "144Hz", "165Hz", "240Hz"],
    "panel": ["IPS", "VA", "TN", "OLED", "Nano Cell"],
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
        # For other categories, skip to photo
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
    
    context.user_data["display"] = query.data.replace("laptop_display_", "")
    
    buttons = [(ram, f"laptop_ram_{ram}") for ram in LAPTOP_FILTERS["ram"]]
    await query.edit_message_text(
        "🧠 Виберіть обсяг RAM:",
        reply_markup=kb(buttons, columns=2)
    )
    return CHOOSE_LAPTOP_RAM

async def choose_laptop_ram(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    context.user_data["ram"] = query.data.replace("laptop_ram_", "")
    
    buttons = [(proc, f"laptop_proc_{proc}") for proc in LAPTOP_FILTERS["processor"]]
    await query.edit_message_text(
        "⚙️ Виберіть процесор:",
        reply_markup=kb(buttons, columns=2)
    )
    return CHOOSE_LAPTOP_PROCESSOR

async def choose_laptop_processor(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    context.user_data["processor"] = query.data.replace("laptop_proc_", "")
    
    buttons = [(brand, f"laptop_brand_{brand}") for brand in LAPTOP_FILTERS["brand"]]
    await query.edit_message_text(
        "🏢 Виберіть бренд:",
        reply_markup=kb(buttons, columns=2)
    )
    return CHOOSE_LAPTOP_BRAND

async def choose_laptop_brand(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    context.user_data["brand"] = query.data.replace("laptop_brand_", "")
    
    await query.edit_message_text(
        "📸 Надішліть фото товару (або натисніть Пропустити):",
        reply_markup=skip_kb()
    )
    return ENTER_PHOTO

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
            image_url = await upload_photo_to_s3(file.file_path, context.bot)
            
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
        context.user_data["description"] = ""
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
            CHOOSE_LAPTOP_DISPLAY: [CallbackQueryHandler(choose_laptop_display)],
            CHOOSE_LAPTOP_RAM: [CallbackQueryHandler(choose_laptop_ram)],
            CHOOSE_LAPTOP_PROCESSOR: [CallbackQueryHandler(choose_laptop_processor)],
            CHOOSE_LAPTOP_BRAND: [CallbackQueryHandler(choose_laptop_brand)],
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
    
    logger.info("🤖 Бот запущено")
    app.run_polling()

if __name__ == "__main__":
    main()
