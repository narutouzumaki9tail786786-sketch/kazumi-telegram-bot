# 🌸 Kazumi — Premium & Telegram Stars (XTR) Monetization Plugin (2026)

import time
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, MessageEntity, LabeledPrice
from telegram.ext import ContextTypes
from telegram.constants import ChatType, ParseMode
from telegram.error import TelegramError
from pymongo.errors import DuplicateKeyError

from kazumi.utils import ensure_user_exists, get_mention, stylize_text, resolve_target, get_active_protection, format_time, Button, get_icon_id, custom_emoji_html, format_money, premium_is_active_doc
from kazumi.database import users_collection, stars_purchases_collection
from kazumi.ledger import adjust_user_balance
from kazumi.config import OWNER_ID, OWNER_LINK, PREMIUM_LIFETIME_USDT, PREMIUM_MONTHLY_USDT, WEBAPP_URL

STAR_PRODUCT_PRICES = {
    "coins_10": 25,
    "coins_50": 100,
    "coins_100": 250,
    "vip_silver": 75,
    "vip_gold": 200,
    "vip_diamond": 500,
    "bless_5": 15,
    "shield_10": 30,
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🌟 TELEGRAPH & HELP CALLBACKS FOR WEB ARCADE & STARS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def help_webarcade_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Rich menu for Web Arcade Games."""
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except Exception:
            pass

    text = (
        f"🌐 <b>{stylize_text('KAZUMI CYBER WEB ARCADE')}</b> 🕹️\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<i>Play high-graphics 3D mini games directly inside Telegram!</i>\n\n"
        f"🎡 <b>Spin Wheel:</b> <code>/wspin 2000</code> — 3D Canvas wheel (Up to 10x Jackpot!)\n"
        f"🚀 <b>Aviator Crash:</b> <code>/wav 1000</code> — Real-time rising flight multiplier.\n"
        f"💣 <b>Mines 5x5:</b> <code>/wmines 1000</code> — Reveal gems, dodge plasma mines.\n"
        f"🔴🟢 <b>Color Bet:</b> <code>/wcolor 500</code> — High-rate card color predictions.\n"
        f"🎲 <b>Ludo Duel:</b> <code>/wludo 1000</code> — Real-time 3D board match.\n\n"
        f"🔗 <b>Master Guide:</b> <a href='https://telegra.ph/Kazumi-Cyber-Web-Arcade---A-to-Z-Master-Guide-Index-07-24'>Click Here for All Game Guides</a>"
    )

    keyboard = InlineKeyboardMarkup([
        [
            Button("📖 A-Z Web Arcade Master Guide", url="https://telegra.ph/Kazumi-Cyber-Web-Arcade---A-to-Z-Master-Guide-Index-07-24", style="success"),
        ],
        [
            Button("⬅️ Back to Help", callback_data="help_main", style="danger"),
        ]
    ])

    if query and query.message:
        try:
            await query.message.edit_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        except Exception:
            try:
                await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard, disable_web_page_preview=True)
            except Exception:
                await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard, disable_web_page_preview=True)
    elif update.effective_message:
        await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard, disable_web_page_preview=True)


async def help_stars_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Rich menu for Telegram Stars & VIP Plans."""
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except Exception:
            pass

    text = (
        f"⭐️ <b>{stylize_text('STARS STORE & VIP TIERS')}</b> 🌟\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Pay with Telegram Stars (XTR) — instant delivery!</i>\n\n"
        f"🪙 <b>Coin Top-Up Packs:</b>\n"
        f"  ⭐️ <b>25 Stars</b> → <code>+50,000 Coins</code> in your wallet\n"
        f"  ⭐️ <b>100 Stars</b> → <code>+300,000 Coins</code> in your wallet\n"
        f"  ⭐️ <b>250 Stars</b> → <code>+750,000 Coins</code> in your wallet\n\n"
        f"👑 <b>VIP Membership (30 Days):</b>\n"
        f"  🥈 <b>Silver — ⭐️75:</b>\n"
            f"    • Premium daily rewards and higher /kill & /rob limits\n"
        f"    • +50,000 bonus coins on purchase\n\n"
        f"  🥇 <b>Gold — ⭐️200:</b>\n"
            f"    • Premium daily rewards and higher /kill & /rob limits\n"
            f"    • 7-day Anti-Rob Guard included\n"
        f"    • +250,000 bonus coins on purchase\n\n"
        f"  💎 <b>Diamond — ⭐️500:</b>\n"
            f"    • Premium daily rewards and higher /kill & /rob limits\n"
            f"    • 7-day Anti-Rob Guard included\n"
        f"    • +1,000,000 bonus coins on purchase\n\n"
        f"🛡️ <b>One-Time Perks (Instant Activation):</b>\n"
        f"  🔥 <b>Phoenix Blessing — ⭐️15:</b>\n"
        f"    • Instantly revives you if you are Dead\n"
        f"    • 48h full immortality shield (no one can kill/rob you)\n"
            f"    • Use <code>/check</code> to see your shield timer after purchase\n\n"
        f"  🛡️ <b>Anti-Rob Guard — ⭐️30:</b>\n"
        f"    • 7-day complete immunity from /rob & /bounty\n"
        f"    • Visible in your <code>/bal</code> profile\n\n"
        f"  ⚔️ <b>Gang Overdrive — ⭐️45:</b>\n"
            f"    • This perk is currently unavailable while its gang-war bonus is completed"
    )

    keyboard = InlineKeyboardMarkup([
        [
            Button("🪙 Buy Coins", callback_data="stars_buy_coins_menu", style="success"),
            Button("👑 VIP Memberships", callback_data="stars_buy_vip_menu", style="primary"),
        ],
        [
            Button("🔥 Phoenix Blessing (⭐️15)", callback_data="buy_invoice_bless_5", style="danger"),
            Button("🛡️ Anti-Rob Guard (⭐️30)", callback_data="buy_invoice_shield_10", style="success"),
        ],
        [
            Button("⚔️ Gang Overdrive (Coming Soon)", callback_data="gang_overdrive_unavailable", style="primary"),
        ],
        [
            Button("📖 Full VIP Guide", url="https://telegra.ph/How-Cyber-Ludo--Mega-Updates-Work---Kazumi-Guide-07-24-2", style="primary"),
            Button("⬅️ Back to Help", callback_data="help_main", style="danger"),
        ]
    ])

    if query and query.message:
        try:
            await query.message.edit_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        except Exception:
            try:
                await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard, disable_web_page_preview=True)
            except Exception:
                await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard, disable_web_page_preview=True)
    elif update.effective_message:
        await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard, disable_web_page_preview=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ⭐️ TELEGRAM STARS INVOICE GENERATOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def send_stars_invoice(update: Update, context: ContextTypes.DEFAULT_TYPE, title: str, description: str, payload: str, stars_amount: int):
    chat_id = update.effective_chat.id
    try:
        await context.bot.send_invoice(
            chat_id=chat_id,
            title=title,
            description=description,
            payload=payload,
            provider_token="",  # Required empty string for Telegram Stars
            currency="XTR",    # Telegram Stars Currency Symbol
            prices=[LabeledPrice(label=title, amount=stars_amount)],
            start_parameter=f"kazumi-stars-{stars_amount}"
        )
    except Exception as exc:
        err_msg = str(exc)
        if "flood" in err_msg.lower() or "retry after" in err_msg.lower():
            print(f"[STARS INVOICE RATE-LIMIT] chat={chat_id}: {exc}", flush=True)
            if update.effective_message:
                await update.effective_message.reply_text(
                    "⏳ <b>Please wait a few seconds before clicking buy again!</b>",
                    parse_mode=ParseMode.HTML
                )
        else:
            print(f"[STARS INVOICE ERROR] {exc}", flush=True)
            if update.effective_message:
                await update.effective_message.reply_text(
                    f"❌ <b>Invoice Error:</b> Unable to launch Telegram Stars invoice.\n<code>{exc}</code>",
                    parse_mode=ParseMode.HTML
                )


async def buy_stars_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    data = query.data or ""

    if data == "gang_overdrive_unavailable":
        return await query.answer(
            "Gang Overdrive is temporarily unavailable while its battle bonus is being completed.",
            show_alert=True,
        )

    if data == "stars_buy_coins_menu":
        text = (
            "🪙 <b>SELECT A COIN PACK TO BUY WITH TELEGRAM STARS (XTR):</b>\n\n"
            "• ⭐️ <b>25 Stars</b> ➔ 50,000 Kazumi Coins\n"
            "• ⭐️ <b>100 Stars</b> ➔ 300,000 Kazumi Coins\n"
            "• ⭐️ <b>250 Stars</b> ➔ 750,000 Kazumi Coins"
        )
        kb = InlineKeyboardMarkup([
            [
                Button("⭐️ 25 Stars (50k)", callback_data="buy_invoice_coins_10", style="success"),
                Button("⭐️ 100 Stars (300k)", callback_data="buy_invoice_coins_50", style="success"),
            ],
            [
                Button("⭐️ 250 Stars (750k)", callback_data="buy_invoice_coins_100", style="success"),
            ],
            [
                Button("⬅️ Back to Store", callback_data="help_stars", style="danger"),
            ]
        ])
        return await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

    if data == "stars_buy_vip_menu":
        text = (
            "👑 <b>SELECT A KAZUMI VIP MEMBERSHIP TIER (XTR):</b>\n\n"
            "• 🥈 <b>Silver (⭐️ 75 Stars / 30 Days):</b> Premium rewards + 50,000 Coins\n"
            "• 🥇 <b>Gold (⭐️ 200 Stars / 30 Days):</b> Premium + 7-Day Anti-Rob + 250,000 Coins\n"
            "• 💎 <b>Diamond (⭐️ 500 Stars / 30 Days):</b> Premium + 7-Day Anti-Rob + 1,000,000 Coins"
        )
        kb = InlineKeyboardMarkup([
            [
                Button("🥈 Silver VIP (⭐️75)", callback_data="buy_invoice_vip_silver", style="primary"),
                Button("🥇 Gold VIP (⭐️200)", callback_data="buy_invoice_vip_gold", style="success"),
            ],
            [
                Button("💎 Diamond VIP (⭐️500)", callback_data="buy_invoice_vip_diamond", style="primary"),
            ],
            [
                Button("⬅️ Back to Store", callback_data="help_stars", style="danger"),
            ]
        ])
        return await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

    # Invoices
    if data == "buy_invoice_coins_10":
        await send_stars_invoice(update, context, "⭐️ 25 Stars Coin Pack", "50,000 Kazumi Coins credited instantly!", "coins_10", 25)
    elif data == "buy_invoice_coins_50":
        await send_stars_invoice(update, context, "⭐️ 100 Stars Coin Pack", "300,000 Kazumi Coins credited instantly!", "coins_50", 100)
    elif data == "buy_invoice_coins_100":
        await send_stars_invoice(update, context, "⭐️ 250 Stars Mega Coin Pack", "750,000 Kazumi Coins credited instantly!", "coins_100", 250)
    elif data == "buy_invoice_vip_silver":
        await send_stars_invoice(update, context, "🥈 Silver VIP Membership", "30-Day Premium rewards + 50,000 Bonus Coins!", "vip_silver", 75)
    elif data == "buy_invoice_vip_gold":
        await send_stars_invoice(update, context, "🥇 Gold VIP Membership", "30-Day Premium + 7-Day Anti-Rob + 250,000 Coins!", "vip_gold", 200)
    elif data == "buy_invoice_vip_diamond":
        await send_stars_invoice(update, context, "💎 Diamond Sovereign VIP", "30-Day Premium + 7-Day Anti-Rob + 1M Coins!", "vip_diamond", 500)
    elif data == "buy_invoice_bless_5":
        await send_stars_invoice(update, context, "🔥 Phoenix Blessing", "Revive if needed + 48h Divine Shield!", "bless_5", 15)
    elif data == "buy_invoice_shield_10":
        await send_stars_invoice(update, context, "🛡️ Anti-Rob Guard", "7-Day Complete Immunity from Robs and Bounties!", "shield_10", 30)
    elif data == "buy_invoice_gang_15":
        await query.answer("Gang Overdrive is temporarily unavailable.", show_alert=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 💳 PAYMENT CHECKOUT & SUCCESS FULFILLMENT HANDLERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def precheckout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Answer Telegram PreCheckout Query for Telegram Stars immediately."""
    query = update.pre_checkout_query
    if query:
        try:
            payload = query.invoice_payload or ""
            expected_price = STAR_PRODUCT_PRICES.get(payload)
            if expected_price is None and not payload.startswith("kazumi_support"):
                return await query.answer(ok=False, error_message="This Kazumi item is unavailable.")
            if expected_price is not None and query.total_amount != expected_price:
                return await query.answer(ok=False, error_message="The item price could not be verified. Please try again.")
            await query.answer(ok=True)
        except Exception as exc:
            print(f"[PRECHECKOUT QUERY ANSWER ERROR] {exc}", flush=True)


async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fulfill purchased digital goods upon successful payment."""
    msg = update.effective_message
    if not msg or not msg.successful_payment:
        return

    payment = msg.successful_payment
    payload = payment.invoice_payload
    user_id = update.effective_user.id
    user = ensure_user_exists(update.effective_user)

    now = datetime.utcnow()

    # ── Item label map for readable purchase log ──
    ITEM_LABELS = {
        "coins_10":   ("Coin Pack 50K",      25),
        "coins_50":   ("Coin Pack 300K",    100),
        "coins_100":  ("Coin Pack 750K",    250),
        "vip_silver": ("Silver VIP 30d",     75),
        "vip_gold":   ("Gold VIP 30d",      200),
        "vip_diamond":("Diamond VIP 30d",   500),
        "bless_5":    ("Phoenix Blessing",   15),
        "shield_10":  ("Anti-Rob Guard 7d",  30),
        "gang_15":    ("Gang Overdrive 24h", 45),
    }

    def log_purchase(pl, uid, uname):
        label, _ = ITEM_LABELS.get(pl, (pl, payment.total_amount or 0))
        charge_id = getattr(payment, "telegram_payment_charge_id", None)
        purchase = {
            "user_id": uid,
            "username": uname,
            "payload": pl,
            "item_name": label,
            "stars_paid": int(payment.total_amount or 0),
            "purchased_at": now,
        }
        if charge_id:
            purchase["telegram_payment_charge_id"] = charge_id
        stars_purchases_collection.insert_one(purchase)

    uname = update.effective_user.username or update.effective_user.first_name or str(user_id)
    try:
        log_purchase(payload, user_id, uname)
    except DuplicateKeyError:
        return await msg.reply_text(
            "✅ <b>Payment already processed.</b> Your Kazumi purchase was credited earlier.",
            parse_mode=ParseMode.HTML,
        )
    except Exception as exc:
        print(f"[PURCHASE LOG ERROR] {exc}", flush=True)

    if payload and payload.startswith("kazumi_support"):
        from kazumi.plugins.support import parse_support_payload
        supp_data = parse_support_payload(payload)
        amount = int(payment.total_amount or (supp_data["amount"] if supp_data else 10))
        return await msg.reply_text(
            f"🌸 <b>{stylize_text('THANK YOU FOR YOUR SUPPORT')}!</b> 🤍\n\n"
            f"Your support of <code>{amount} Stars</code> reached Kazumi.\n"
            f"It will help fund faster servers, updates & new games! ✨",
            parse_mode=ParseMode.HTML
        )

    if payload == "coins_10":
        adjust_user_balance(user_id, 50000, category="stars_shop", reason="25 Stars Purchase")
        await msg.reply_text("🎉 <b>PAYMENT SUCCESSFUL!</b>\n50,000 Kazumi Coins credited to your wallet!\nCheck your updated balance with <code>/bal</code>", parse_mode=ParseMode.HTML)

    elif payload == "coins_50":
        adjust_user_balance(user_id, 300000, category="stars_shop", reason="100 Stars Purchase")
        await msg.reply_text("🎉 <b>PAYMENT SUCCESSFUL!</b>\n300,000 Kazumi Coins credited to your wallet!\nCheck your updated balance with <code>/bal</code>", parse_mode=ParseMode.HTML)

    elif payload == "coins_100":
        adjust_user_balance(user_id, 750000, category="stars_shop", reason="250 Stars Purchase")
        await msg.reply_text("🎉 <b>MEGA PAYMENT SUCCESSFUL!</b>\n750,000 Kazumi Coins credited to your wallet!\nCheck your updated balance with <code>/bal</code>", parse_mode=ParseMode.HTML)

    elif payload == "vip_silver":
        expiry = now + timedelta(days=30)
        users_collection.update_one({"user_id": user_id}, {"$set": {"is_premium": True, "vip_tier": "silver", "vip_expiry": expiry, "premium_until": expiry, "custom_emoji": "🥈"}})
        adjust_user_balance(user_id, 50000, category="vip_reward", reason="Silver VIP Bonus Coins")
        await msg.reply_text("🥈 <b>SILVER VIP ACTIVATED!</b>\n30-Day Premium rewards & 50,000 Bonus Coins activated!\nCheck your profile with <code>/vip</code> or <code>/profile</code>", parse_mode=ParseMode.HTML)

    elif payload == "vip_gold":
        expiry = now + timedelta(days=30)
        guard_expiry = now + timedelta(days=7)
        users_collection.update_one({"user_id": user_id}, {"$set": {"is_premium": True, "vip_tier": "gold", "vip_expiry": expiry, "premium_until": expiry, "custom_emoji": "🥇", "anti_rob_until": guard_expiry, "protection_expiry": guard_expiry}})
        adjust_user_balance(user_id, 250000, category="vip_reward", reason="Gold VIP Bonus Coins")
        await msg.reply_text("🥇 <b>GOLD VIP ACTIVATED!</b>\n30-Day Premium, 7-Day Anti-Rob Guard & 250,000 Coins activated!\nCheck your status with <code>/check</code>", parse_mode=ParseMode.HTML)

    elif payload == "vip_diamond":
        expiry = now + timedelta(days=30)
        guard_expiry = now + timedelta(days=7)
        users_collection.update_one({"user_id": user_id}, {"$set": {"is_premium": True, "vip_tier": "diamond", "vip_expiry": expiry, "premium_until": expiry, "custom_emoji": "💎", "anti_rob_until": guard_expiry, "protection_expiry": guard_expiry}})
        adjust_user_balance(user_id, 1000000, category="vip_reward", reason="Diamond VIP Bonus Coins")
        await msg.reply_text("💎 <b>DIAMOND SOVEREIGN ACTIVATED!</b>\n30-Day Premium, 7-Day Anti-Rob Guard & 1,000,000 Coins activated!\nCheck your status with <code>/check</code>", parse_mode=ParseMode.HTML)

    elif payload == "bless_5":
        expiry = now + timedelta(hours=48)
        users_collection.update_one({"user_id": user_id}, {"$set": {"status": "alive", "death_time": None, "protection_expiry": expiry}})
        await msg.reply_text("🔥 <b>PHOENIX BLESSING GRANTED!</b>\nResurrected if needed + 48-Hour Divine Shield active!\nCheck your protection timer with <code>/check</code>", parse_mode=ParseMode.HTML)

    elif payload == "shield_10":
        expiry = now + timedelta(days=7)
        users_collection.update_one({"user_id": user_id}, {"$set": {"protection_expiry": expiry, "anti_rob_until": expiry}})
        await msg.reply_text("🛡️ <b>ANTI-ROB GUARD ACTIVATED!</b>\nYou are 100% immune to Robs & Bounties for 7 Days!\nCheck your protection timer with <code>/check</code>", parse_mode=ParseMode.HTML)

    elif payload == "gang_15":
        expiry = now + timedelta(days=1)
        users_collection.update_one({"user_id": user_id}, {"$set": {"gang_overdrive_until": expiry}})
        await msg.reply_text("⚔️ <b>GANG OVERDRIVE ACTIVATED!</b>\n2x Damage Multiplier active in Raids & Gang Wars for 24 Hours!", parse_mode=ParseMode.HTML)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📌 COMMAND HANDLERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def stars_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command /stars or /buycoins to open Telegram Stars Store."""
    await help_stars_callback(update, context)


async def bless_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command /bless to buy Phoenix Blessing."""
    await send_stars_invoice(update, context, "🔥 Phoenix Blessing", "Revive if needed + 48h Divine Shield!", "bless_5", STAR_PRODUCT_PRICES["bless_5"])


async def shield_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command /shield to buy Anti-Rob Guard."""
    await send_stars_invoice(update, context, "🛡️ Anti-Rob Guard", "7-Day Complete Immunity from Robs and Bounties!", "shield_10", STAR_PRODUCT_PRICES["shield_10"])


async def gangboost_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command /gangboost to buy 24h Overdrive."""
    await update.effective_message.reply_text(
        "⚠️ <b>Gang Overdrive is temporarily unavailable.</b> Its gang-war bonus is being completed.",
        parse_mode=ParseMode.HTML,
    )


async def add_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner Only: Add premium to a user."""
    if update.effective_user.id != OWNER_ID:
        return await update.message.reply_text("❌ <b>Nice try!</b> Only Owner can grant Premium.", parse_mode=ParseMode.HTML)
    
    target, error = await resolve_target(update, context)
    if not target:
        return await update.message.reply_text(error if error else "⚠️ Tag or Reply to grant Premium!", parse_mode=ParseMode.HTML)
    
    users_collection.update_one({"user_id": target["user_id"]}, {"$set": {"is_premium": True, "vip_tier": "gold"}})
    await update.message.reply_text(f"🌟 <b>{stylize_text('Premium Activated')}!</b>\n{get_mention(target)} is now a Gold Premium User! 💓", parse_mode=ParseMode.HTML)


async def remove_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner Only: Remove premium from a user."""
    if update.effective_user.id != OWNER_ID:
        return await update.message.reply_text("❌ Only Owner can revoke Premium.", parse_mode=ParseMode.HTML)
    
    target, error = await resolve_target(update, context)
    if not target:
        return await update.message.reply_text(error if error else "⚠️ Tag or Reply to revoke Premium!", parse_mode=ParseMode.HTML)
    
    users_collection.update_one({"user_id": target["user_id"]}, {"$set": {"is_premium": False, "vip_tier": None, "custom_emoji": None, "custom_emoji_id": None}})
    await update.message.reply_text(f"💔 <b>{stylize_text('Premium Revoked')}!</b>\n{get_mention(target)} is no longer a Premium User.", parse_mode=ParseMode.HTML)


async def set_emoji(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Premium Only: Set custom profile badge."""
    user = ensure_user_exists(update.effective_user)
    if not premium_is_active_doc(user):
        return await update.message.reply_text("❌ <b>Premium Only!</b> Get VIP Premium to set a custom badge. Type /vip", parse_mode=ParseMode.HTML)
    
    if not context.args:
        return await update.message.reply_text(f"✨ <b>Usage:</b> <code>/setemoji 🔥</code>\nTo reset: <code>/setemoji reset</code>", parse_mode=ParseMode.HTML)
    
    emoji = context.args[0]
    if emoji.lower() == "reset":
        users_collection.update_one({"user_id": user["user_id"]}, {"$set": {"custom_emoji": None, "custom_emoji_id": None}})
        return await update.message.reply_text("✅ <b>Badge reset to default!</b>", parse_mode=ParseMode.HTML)
    
    custom_emoji_id = None
    for entity in update.message.entities or []:
        if entity.type == MessageEntity.CUSTOM_EMOJI and entity.custom_emoji_id:
            custom_emoji_id = entity.custom_emoji_id
            emoji = update.message.parse_entity(entity) or emoji
            break

    if not custom_emoji_id:
        mapped_id, raw_emoji = get_icon_id(emoji)
        custom_emoji_id = mapped_id
        emoji = raw_emoji or emoji

    if not custom_emoji_id and len(emoji) > 5:
        return await update.message.reply_text("⚠️ <b>Invalid!</b> Please send one emoji or one premium custom emoji.", parse_mode=ParseMode.HTML)
    
    users_collection.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"custom_emoji": emoji, "custom_emoji_id": custom_emoji_id}},
    )
    preview = custom_emoji_html(custom_emoji_id, emoji) if custom_emoji_id else emoji
    await update.message.reply_text(f"✨ <b>Badge Updated!</b> Your new badge: {preview}", parse_mode=ParseMode.HTML)


async def check_protection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check protection time of any user (VIP Premium Only)."""
    user = ensure_user_exists(update.effective_user)
    if not premium_is_active_doc(user):
        return await update.message.reply_text(
            f"🌟 <b>{stylize_text('VIP Premium Required')}!</b>\n"
            f"The <code>/check</code> command is reserved exclusively for VIP Premium members.\n\n"
            f"<i>Type /vip or /premium to upgrade your tier!</i>",
            parse_mode=ParseMode.HTML
        )
        
    target, error = await resolve_target(update, context)
    if not target:
        target = user
    
    expiry = get_active_protection(target)
    if not expiry:
        return await update.message.reply_text(f"🛡️ {get_mention(target)} is <b>Not Protected</b>.", parse_mode=ParseMode.HTML)
    
    rem = expiry - datetime.utcnow()
    exact_text = f"\U0001f6e1\ufe0f {get_mention(target)} is protected for <code>{format_time(rem)}</code>."
    if update.effective_chat.type == ChatType.PRIVATE:
        return await update.message.reply_text(exact_text, parse_mode=ParseMode.HTML)

    public_text = f"\U0001f6e1\ufe0f {get_mention(target)} is <b>Protected</b>. Exact timer sent privately."
    try:
        await context.bot.send_message(chat_id=update.effective_user.id, text=exact_text, parse_mode=ParseMode.HTML)
    except TelegramError:
        public_text = f"\U0001f6e1\ufe0f {get_mention(target)} is <b>Protected</b>. Start me in DM to view exact timer."
    await update.message.reply_text(public_text, parse_mode=ParseMode.HTML)


async def premium_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show premium benefits & Telegram Stars Store."""
    await help_stars_callback(update, context)
