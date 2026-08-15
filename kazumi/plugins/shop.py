# Copyright (c) 2025 Telegram:- @WTF_Phantom <DevixOP>
# Location: Supaul, Bihar 
#
# All rights reserved.
#
# This code is the intellectual property of @WTF_Phantom.
# You are not allowed to copy, modify, redistribute, or use this
# code for commercial or personal projects without explicit permission.
#
# Allowed:
# - Forking for personal learning
# - Submitting improvements via pull requests
#
# Not Allowed:
# - Claiming this code as your own
# - Re-uploading without credit or permission
# - Selling or using commercially
#
# Contact for permissions:
# Email: king25258069@gmail.com

from datetime import datetime

from telegram import Update, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from kazumi.utils import ensure_user_exists, format_money, get_mention, stylize_text, Button
from kazumi.database import users_collection
from kazumi.ledger import adjust_user_balance
from kazumi.config import SHOP_ITEMS

ITEMS_PER_PAGE = 6
SHOP_SELL_RATE = 0.60

# --- HELPERS ---

def get_rarity(price):
    if price < 5000: return "⚪ Common"
    if price < 20000: return "🟢 Uncommon"
    if price < 100000: return "🔵 Rare"
    if price < 1000000: return "🟣 Epic"
    if price < 10000000: return "🟡 Legendary"
    return "🔴 GODLY"

def get_description(item):
    """Generates a cool description based on item type."""
    if item['id'] == "deathnote": return "Writes names. Deletes people. 60% Kill Buff."
    if item['id'] == "plot": return "Literal Plot Armor. You cannot die. 60% Block."
    
    if item['type'] == 'weapon':
        return f"A deadly weapon. Increases your kill rewards by +{int(item['buff']*100)}%."
    elif item['type'] == 'armor':
        return f"Protective gear. Gives a {int(item['buff']*100)}% chance to block any robbery attempt."
    elif item['type'] == 'flex':
        return "A useless item for rich people. Shows off your massive wealth."
    return "Unknown Item."

import re

def clean_string(text: str) -> str:
    if not text:
        return ""
    clean = re.sub(r'[^\w\s]', '', str(text)).strip().lower()
    return re.sub(r'\s+', ' ', clean)

def find_shop_item(query: str, user_inventory: list = None):
    if not query:
        return None
    raw_query = str(query).strip().lower()
    cleaned_query = clean_string(raw_query)

    # 1. Direct ID match in SHOP_ITEMS
    for item in SHOP_ITEMS:
        if item["id"].lower() == raw_query or item["id"].lower() == cleaned_query:
            return item

    # 2. Exact cleaned name match in SHOP_ITEMS
    for item in SHOP_ITEMS:
        if clean_string(item["name"]) == cleaned_query:
            return item

    # 3. Exact match inside user's inventory
    if user_inventory:
        for item in user_inventory:
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("id", "")).lower()
            item_name = clean_string(str(item.get("name", "")))
            if item_id == raw_query or item_id == cleaned_query or item_name == cleaned_query:
                # Map back to full shop item if possible
                shop_item = next((s for s in SHOP_ITEMS if s["id"] == item_id), None)
                return shop_item or item

    # 4. Partial substring match in clean name or ID in SHOP_ITEMS
    for item in SHOP_ITEMS:
        clean_n = clean_string(item["name"])
        item_id = item["id"].lower()
        if cleaned_query and (cleaned_query == clean_n or cleaned_query == item_id or cleaned_query in clean_n or clean_n in cleaned_query or cleaned_query in item_id):
            return item

    # 5. Partial match inside user's inventory
    if user_inventory:
        for item in user_inventory:
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("id", "")).lower()
            item_name = clean_string(str(item.get("name", "")))
            if cleaned_query and (cleaned_query in item_name or item_name in cleaned_query or cleaned_query in item_id):
                shop_item = next((s for s in SHOP_ITEMS if s["id"] == item_id), None)
                return shop_item or item

    return None

def sell_price(item):
    return max(1, int(int(item.get("price", 0)) * SHOP_SELL_RATE))

def user_owns_item(user, item_id):
    return any(
        isinstance(item, dict) and item.get("id") == item_id
        for item in (user.get("inventory") or [])
    )

def remove_one_inventory_item(user_doc, item_id):
    inventory = list(user_doc.get("inventory", []) or [])
    kept = []
    removed = None
    for item in inventory:
        if not isinstance(item, dict):
            kept.append(item)
            continue
        if not removed and item.get("id") == item_id:
            removed = item
            continue
        kept.append(item)
    if not removed:
        return None
    users_collection.update_one({"user_id": user_doc["user_id"]}, {"$set": {"inventory": kept}})
    return removed

# --- KEYBOARD BUILDERS ---

def get_main_menu_kb():
    return InlineKeyboardMarkup([
        [
            Button("\u2694\ufe0f 𝐖𝐞𝐚𝐩𝐨𝐧𝐬", callback_data="shop_cat|weapon"),
            Button("\U0001F6E1\ufe0f 𝐀𝐫𝐦𝐨𝐫", callback_data="shop_cat|armor")
        ],
        [
            Button("\U0001F48E 𝐅𝐥𝐞𝐱 & 𝐕𝐈𝐏", callback_data="shop_cat|flex")
        ],
        [Button("\U0001F519 𝐂𝐥𝐨𝐬𝐞", callback_data="shop_close")]
    ])

def get_category_kb(category_type, page=0):
    items = [i for i in SHOP_ITEMS if i['type'] == category_type]
    start_idx = page * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    current_items = items[start_idx:end_idx]
    
    keyboard = []
    row = []
    for item in current_items:
        price_k = f"{item['price']//1000}k" if item['price'] >= 1000 else item['price']
        text = f"{item['name']} [{price_k}]"
        callback = f"shop_view|{item['id']}|{category_type}|{page}"
        row.append(Button(text, callback_data=callback))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row: keyboard.append(row)
    
    nav = []
    if page > 0:
        nav.append(Button("\u2B05\ufe0f 𝐏𝐫𝐞𝐯", callback_data=f"shop_cat|{category_type}|{page-1}"))
    nav.append(Button("\U0001F519 𝐌𝐞𝐧𝐮", callback_data="shop_home"))
    if end_idx < len(items):
        nav.append(Button("\u27A1\ufe0f 𝐍𝐞𝐱𝐭", callback_data=f"shop_cat|{category_type}|{page+1}"))
    
    keyboard.append(nav)
    return InlineKeyboardMarkup(keyboard)

def get_item_kb(item_id, category, page, can_afford, is_owned):
    kb = []
    if is_owned:
        kb.append([
            Button("\u2705 𝐎𝐰𝐧𝐞𝐝", callback_data="shop_owned"),
            Button("\U0001F4B0 𝐒𝐞𝐥𝐥", callback_data=f"shop_sell|{item_id}|{category}|{page}")
        ])
    elif can_afford:
        kb.append([Button("\U0001F4B3 𝐁𝐮𝐲 𝐍𝐨𝐰", callback_data=f"shop_buy|{item_id}|{category}|{page}")])
    else:
        kb.append([Button("\u274C 𝐂𝐚𝐧'𝐭 𝐀𝐟𝐟𝐨𝐫𝐝", callback_data="shop_poor")])
        
    kb.append([Button("\U0001F519 𝐁𝐚𝐜𝐤", callback_data=f"shop_cat|{category}|{page}")])
    return InlineKeyboardMarkup(kb)

# --- MENUS ---

async def shop_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = ensure_user_exists(update.effective_user)
        bal = format_money(user['balance'])
        
        text = (
            f"\U0001F6D2 <b>𝐊𝐚𝐳𝐮𝐦𝐢 𝐌𝐚𝐫𝐤𝐞𝐭𝐩𝐥𝐚𝐜𝐞</b>\n\n"
            f"👤 <b>Customer:</b> {get_mention(user)}\n"
            f"👛 <b>Wallet:</b> <code>{bal}</code>\n\n"
            f"<i>Select a category to browse our goods!</i>"
        )
        
        kb = get_main_menu_kb()
        
        if update.callback_query:
            await update.callback_query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        else:
            await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            
    except Exception as e:
        print(f"Shop Error: {e}")
        # Fallback in case of error
        if update.callback_query:
            await update.callback_query.answer("❌ Shop Error", show_alert=True)
        else:
            await update.message.reply_text("❌ <b>Shop Error:</b> Please check logs.", parse_mode=ParseMode.HTML)

# --- CALLBACK HANDLER ---

async def shop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = ensure_user_exists(query.from_user)
    data = query.data.split("|")
    action = data[0]
    
    if action == "shop_close":
        await query.message.delete()
        return

    if action == "shop_home":
        await shop_menu(update, context)
        return
    
    # --- CATEGORY VIEW ---
    if action == "shop_cat":
        cat_type = data[1]
        page = int(data[2]) if len(data) > 2 else 0
        
        titles = {
            "weapon": "⚔️ <b>𝐖𝐞𝐚𝐩𝐨𝐧𝐬 𝐀𝐫𝐦𝐨𝐫𝐲</b>\n<i>Lethal gear for killers.</i>",
            "armor": "🛡️ <b>𝐃𝐞𝐟𝐞𝐧𝐬𝐞 𝐒𝐲𝐬𝐭𝐞𝐦𝐬</b>\n<i>Protection against thieves.</i>",
            "flex": "💎 <b>𝐕𝐈𝐏 𝐅𝐥𝐞𝐱 𝐙𝐨𝐧𝐞</b>\n<i>Pure status symbols.</i>"
        }
        
        text = f"{titles.get(cat_type, 'Shop')}\n\n💰 <b>Balance:</b> <code>{format_money(user['balance'])}</code>"
        
        await query.message.edit_text(
            text, 
            parse_mode=ParseMode.HTML, 
            reply_markup=get_category_kb(cat_type, page)
        )
        return

    # --- ITEM INSPECTOR ---
    if action == "shop_view":
        item_id, cat, page = data[1], data[2], data[3]
        item = find_shop_item(item_id)
        if not item: return await query.answer("❌ Item removed.", show_alert=True)
        
        # Stats Display
        rarity = get_rarity(item['price'])
        desc = get_description(item)
        
        stats = ""
        life = "♾️ Permanent" if item['type'] == 'flex' else "⏳ 24 Hours"
        
        if item['type'] == 'weapon':
            stats = f"💥 <b>Buff:</b> +{int(item['buff']*100)}% Kill Loot"
        elif item['type'] == 'armor':
            stats = f"🛡️ <b>Defense:</b> {int(item['buff']*100)}% Block Chance"
        
        is_owned = user_owns_item(user, item_id)
        can_afford = user['balance'] >= item['price']
        owned_line = f"\n\U0001F4B0 <b>Sell value:</b> <code>{format_money(sell_price(item))}</code>" if is_owned else ""
        
        text = (
            f"🛍️ <b>{item['name']}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📖 <i>{desc}</i>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💰 <b>Price:</b> <code>{format_money(item['price'])}</code>\n"
            f"🌟 <b>Rarity:</b> {rarity}\n"
            f"{stats}\n"
            f"⏱️ <b>Life:</b> {life}\n\n"
            f"👛 <b>Your Wallet:</b> <code>{format_money(user['balance'])}</code>"
            f"{owned_line}"
        )
        
        await query.message.edit_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_item_kb(item_id, cat, page, can_afford, is_owned)
        )
        return

    # --- BUY ACTION ---
    if action == "shop_buy":
        item_id = data[1]
        item = find_shop_item(item_id)
        
        if not item: return await query.answer("❌ Error", show_alert=True)
        
        # Re-fetch user to be safe
        user = ensure_user_exists(query.from_user)

        if user['balance'] < item['price']:
            return await query.answer(f"❌ You need {format_money(item['price'])}!", show_alert=True)
            
        # FAIR PLAY: Unique Items
        if any(isinstance(item, dict) and item.get('id') == item_id for item in (user.get('inventory') or [])):
            return await query.answer("⚠️ You already own this item!", show_alert=True)
            
        # Add Timestamp for 24h expiry
        item_with_time = item.copy()
        item_with_time['bought_at'] = datetime.utcnow()

        bought = adjust_user_balance(
            user["user_id"],
            -item["price"],
            "shop_buy",
            f"Bought {item['name']}",
            chat_id=query.message.chat_id if query.message else None,
            source="shop_buy",
            require_gte=item["price"],
            extra_push={"inventory": item_with_time},
            meta={"item_id": item["id"], "item_name": item["name"]},
        )
        if not bought:
            return await query.answer(f"❌ You need {format_money(item['price'])}!", show_alert=True)
        
        await query.answer(f"🎉 Bought {item['name']}!", show_alert=True)
        
        # Refresh View to show "Owned"
        await shop_callback(update, context)

    if action == "shop_sell":
        item_id = data[1]
        item = find_shop_item(item_id)
        if not item:
            return await query.answer("❌ Item removed.", show_alert=True)
        user = ensure_user_exists(query.from_user)
        removed = remove_one_inventory_item(user, item_id)
        if not removed:
            return await query.answer("❌ You do not own this item.", show_alert=True)
        payout = sell_price(item)
        adjust_user_balance(
            user["user_id"],
            payout,
            "shop_sell",
            f"Sold {item['name']}",
            chat_id=query.message.chat_id if query.message else None,
            source="shop_sell",
            meta={"item_id": item["id"], "item_name": item["name"], "sell_rate": SHOP_SELL_RATE},
        )
        await query.answer(f"Sold for {format_money(payout)}.", show_alert=True)
        return await query.message.edit_text(
            f"\U0001F4B0 <b>{stylize_text('Item Sold')}</b>\n\n"
            f"\U0001F392 <b>Item:</b> {item['name']}\n"
            f"\U0001F4B5 <b>Received:</b> <code>{format_money(payout)}</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_menu_kb(),
        )

    # --- ALERTS ---
    if action == "shop_poor":
        await query.answer("📉 You are too poor for this!", show_alert=True)
    
    if action == "shop_owned":
        await query.answer("🎒 You already have this in your inventory!", show_alert=True)

# --- SHORTCUT (/buy) ---
async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = ensure_user_exists(update.effective_user)
    
    if not context.args: 
        return await update.message.reply_text("⚠️ <b>Usage:</b> <code>/buy knife</code> or <code>/buy super yacht</code>", parse_mode=ParseMode.HTML)
    
    user_inv = [i for i in (user.get('inventory') or []) if isinstance(i, dict)]
    item_query = " ".join(context.args).strip()
    item = find_shop_item(item_query, user_inv)
    
    if not item: 
        return await update.message.reply_text(f"❌ Item <b>{item_query}</b> not found in shop.", parse_mode=ParseMode.HTML)
    
    item_id = item["id"]
    if user['balance'] < item['price']: 
        return await update.message.reply_text(f"❌ You need <code>{format_money(item['price'])}</code>!", parse_mode=ParseMode.HTML)
    
    if any(i.get('id') == item_id for i in user_inv):
        return await update.message.reply_text("⚠️ You already own this item!", parse_mode=ParseMode.HTML)

    item_with_time = item.copy()
    item_with_time['bought_at'] = datetime.utcnow()

    bought = adjust_user_balance(
        user["user_id"],
        -item["price"],
        "shop_buy",
        f"Bought {item['name']}",
        chat_id=update.effective_chat.id if update.effective_chat else None,
        source="/buy",
        require_gte=item["price"],
        extra_push={"inventory": item_with_time},
        meta={"item_id": item["id"], "item_name": item["name"]},
    )
    if not bought:
        return await update.message.reply_text(f"❌ You need <code>{format_money(item['price'])}</code>!", parse_mode=ParseMode.HTML)
    await update.message.reply_text(f"✅ Bought <b>{item['name']}</b>!", parse_mode=ParseMode.HTML)

async def sell(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = ensure_user_exists(update.effective_user)
    if not context.args:
        return await update.message.reply_text(
            f"\U0001F4B0 <b>{stylize_text('Sell Item')}</b>\n\n"
            f"<b>Usage:</b> <code>/sell knife</code> or <code>/sell super yacht</code>\n"
            f"<i>Sell returns {int(SHOP_SELL_RATE * 100)}% of shop price.</i>",
            parse_mode=ParseMode.HTML,
        )
    user_inv = [i for i in (user.get('inventory') or []) if isinstance(i, dict)]
    item_query = " ".join(context.args).strip()
    item = find_shop_item(item_query, user_inv)
    if not item:
        return await update.message.reply_text(f"❌ Item <b>{item_query}</b> not found.", parse_mode=ParseMode.HTML)
    
    item_id = item["id"]
    removed = remove_one_inventory_item(user, item_id)
    if not removed:
        return await update.message.reply_text(f"❌ You do not own <b>{item['name']}</b>.", parse_mode=ParseMode.HTML)
    payout = sell_price(item)
    adjust_user_balance(
        user["user_id"],
        payout,
        "shop_sell",
        f"Sold {item['name']}",
        chat_id=update.effective_chat.id if update.effective_chat else None,
        source="/sell",
        meta={"item_id": item["id"], "item_name": item["name"], "sell_rate": SHOP_SELL_RATE},
    )
    await update.message.reply_text(
        f"\U0001F4B0 <b>{stylize_text('Item Sold')}</b>\n\n"
        f"\U0001F392 <b>Item:</b> {item['name']}\n"
        f"\U0001F4B5 <b>Received:</b> <code>{format_money(payout)}</code>",
        parse_mode=ParseMode.HTML,
    )

async def flex(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = ensure_user_exists(update.effective_user)
    flex_items = [
        item for item in (user.get("inventory") or [])
        if isinstance(item, dict) and item.get("type") == "flex"
    ]
    if not flex_items:
        shop_flex = [i for i in SHOP_ITEMS if i.get("type") == "flex"][-8:]
        lines = "\n".join(f"• <code>{i['id']}</code> — {i['name']} — <code>{format_money(i['price'])}</code>" for i in shop_flex)
        return await update.message.reply_text(
            f"\U0001F48E <b>{stylize_text('Flex Collection')}</b>\n\n"
            f"<i>No flex items yet. Buy one with /shop or /buy.</i>\n\n{lines}",
            parse_mode=ParseMode.HTML,
        )
    lines = "\n".join(f"• {i.get('name', i.get('id', 'Flex Item'))}" for i in flex_items[:25])
    await update.message.reply_text(
        f"\U0001F48E <b>{stylize_text('Your Flex Items')}</b>\n\n{lines}",
        parse_mode=ParseMode.HTML,
    )
