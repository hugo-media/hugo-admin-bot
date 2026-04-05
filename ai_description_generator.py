"""
AI Description Generator using OpenAI ChatGPT
Generates product descriptions in Hugo Media's style
"""

import os
import json
import logging
from typing import Optional

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

logger = logging.getLogger(__name__)

# Initialize OpenAI client
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
client = None

if OPENAI_AVAILABLE and OPENAI_API_KEY:
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        logger.info("✅ OpenAI client initialized successfully")
    except Exception as e:
        logger.error(f"❌ Failed to initialize OpenAI client: {e}")
        client = None
else:
    if not OPENAI_AVAILABLE:
        logger.warning("⚠️ OpenAI package not installed")
    if not OPENAI_API_KEY:
        logger.warning("⚠️ OPENAI_API_KEY not set - AI description generation will be disabled")

# System prompt that teaches ChatGPT Hugo Media's style
SYSTEM_PROMPT = """You are a professional product description writer for Hugo Media, a tech retailer in Poland.

Your task is to write product descriptions in Ukrainian that match Hugo Media's exact style.

**Style Guidelines:**

1. **Structure**:
   - Start with 🔥 emoji + product name + positioning statement
   - Write 2-3 sentence hook explaining the main value/benefit
   - Add ⚙️ Характеристики: section with bullet points
   - Add 🚀 section explaining key features/innovations
   - Add ⚡️ Підходить для: section with use cases
   - Add 💼 Плюси: section if relevant
   - Add 📦 Стан: and 🛡 Гарантія: lines
   - Add 💰 Ціна: line
   - End with 📲 Контакт: @HUGO_Medi

2. **Tone**: Professional, enthusiastic, benefit-focused, honest
   - Highlight what makes the product special
   - Explain WHY specs matter, not just listing them
   - Use specific details and technical accuracy
   - Sound like you're talking to a knowledgeable buyer

3. **Emoji Usage**:
   - 🔥 for main header and hot deals
   - ⚙️ for specifications
   - 🚀 for innovations and key features
   - ⚡️ for use cases and benefits
   - 💼 for advantages
   - 📦 for condition
   - 🛡 for warranty
   - 💰 for price
   - 📲 for contact
   - 🎮 for gaming
   - 💎 for premium features

4. **Language**: Ukrainian, professional but friendly, no corporate jargon

5. **Content**:
   - Be specific about specs (exact models, not vague descriptions)
   - Explain benefits, not just features
   - Mention realistic use cases
   - For used items: honestly describe condition
   - For new items: emphasize freshness and warranty
   - Compare to alternatives when relevant

**Example of good description structure:**
🔥 [Product Name] — [positioning statement]

[2-3 sentence hook about value]

⚙️ Характеристики:
• [spec]: [value]
• [spec]: [value]

🚀 [Key innovation/feature]:
[explanation of why it matters]

⚡️ Підходить для:
[use case 1], [use case 2], [use case 3]

💼 Плюси:
• [advantage 1]
• [advantage 2]

📦 Стан: [condition]
🛡 Гарантія: [warranty]

💰 Ціна: [price] zł

📲 Контакт: @HUGO_Medi

Remember: Write like Hugo Media would write it - professional, detailed, benefit-focused, with specific technical accuracy."""


async def generate_description(
    product_data: dict,
    model: str = "gpt-4o-mini"
) -> Optional[str]:
    """
    Generate a product description using ChatGPT in Hugo Media's style
    
    Args:
        product_data: Dictionary with product information:
            - name: Product name
            - price: Price in zł
            - category: Product category (laptops, monitors, etc.)
            - display: Display size (for laptops)
            - ram: RAM amount
            - processor: Processor model
            - graphicsCard: Graphics card
            - storage: Storage capacity
            - warranty: Warranty period
            - condition: New/Used condition
            - categories: Product category/type
            - brand: Brand name
            - additional_info: Any other relevant info
        
        model: OpenAI model to use
    
    Returns:
        Generated description string or None if generation fails
    """
    
    if not client:
        logger.warning("⚠️ OpenAI client not initialized - cannot generate description")
        return None
    
    try:
        # Build product summary for ChatGPT
        product_summary = f"""
Product Information:
- Name: {product_data.get('name', 'Unknown')}
- Category: {product_data.get('category', 'Unknown')}
- Brand: {product_data.get('brand', 'Unknown')}
- Price: {product_data.get('price', 'N/A')} zł
- Condition: {product_data.get('condition', 'New')}
- Warranty: {product_data.get('warranty', '3 years')}
- Categories: {product_data.get('categories', 'New')}

Specifications:
- Display: {product_data.get('display', 'N/A')}
- Processor: {product_data.get('processor', 'N/A')}
- RAM: {product_data.get('ram', 'N/A')}
- Graphics: {product_data.get('graphicsCard', 'N/A')}
- Storage: {product_data.get('storage', 'N/A')}

Additional Info: {product_data.get('additional_info', 'None')}

Please write a product description in Ukrainian that matches Hugo Media's style exactly.
The description should be compelling, detailed, benefit-focused, and use the exact emoji structure shown in the examples.
"""
        
        # Call ChatGPT
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT
                },
                {
                    "role": "user",
                    "content": product_summary
                }
            ],
            temperature=0.7,
            max_tokens=1000
        )
        
        description = response.choices[0].message.content.strip()
        logger.info(f"✅ Generated description for {product_data.get('name', 'product')}")
        return description
        
    except Exception as e:
        logger.error(f"❌ Error generating description: {e}")
        return None


def generate_description_sync(
    product_data: dict,
    model: str = "gpt-4o-mini"
) -> Optional[str]:
    """
    Synchronous wrapper for generate_description (for use in non-async contexts)
    
    Args:
        product_data: Dictionary with product information
        model: OpenAI model to use
    
    Returns:
        Generated description string or None if generation fails
    """
    
    if not client:
        logger.warning("⚠️ OpenAI client not initialized - cannot generate description")
        return None
    
    try:
        # Build product summary for ChatGPT
        product_summary = f"""
Product Information:
- Name: {product_data.get('name', 'Unknown')}
- Category: {product_data.get('category', 'Unknown')}
- Brand: {product_data.get('brand', 'Unknown')}
- Price: {product_data.get('price', 'N/A')} zł
- Condition: {product_data.get('condition', 'New')}
- Warranty: {product_data.get('warranty', '3 years')}
- Categories: {product_data.get('categories', 'New')}

Specifications:
- Display: {product_data.get('display', 'N/A')}
- Processor: {product_data.get('processor', 'N/A')}
- RAM: {product_data.get('ram', 'N/A')}
- Graphics: {product_data.get('graphicsCard', 'N/A')}
- Storage: {product_data.get('storage', 'N/A')}

Additional Info: {product_data.get('additional_info', 'None')}

Please write a product description in Ukrainian that matches Hugo Media's style exactly.
The description should be compelling, detailed, benefit-focused, and use the exact emoji structure shown in the examples.
"""
        
        # Call ChatGPT
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT
                },
                {
                    "role": "user",
                    "content": product_summary
                }
            ],
            temperature=0.7,
            max_tokens=1000
        )
        
        description = response.choices[0].message.content.strip()
        logger.info(f"✅ Generated description for {product_data.get('name', 'product')}")
        return description
        
    except Exception as e:
        logger.error(f"❌ Error generating description: {e}")
        return None
