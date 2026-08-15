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

import asyncio
import time
from datetime import datetime
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from telegram.constants import ChatType, ParseMode
from kazumi.config import REGISTER_BONUS, OWNER_ID, TAX_RATE, CLAIM_BONUS, MARRIED_TAX_RATE, SHOP_ITEMS, MIN_CLAIM_MEMBERS
from kazumi.utils import ensure_user_exists, get_mention, format_money, resolve_target, log_to_channel, stylize_text, track_group, Button, is_channel_sender, get_active_protection, format_time
from kazumi.database import users_collection, groups_collection
from kazumi.ledger import adjust_user_balance, balance_summary, format_history_time, get_balance_history
from kazumi.game_rules import leaderboard_filter
from kazumi.plugins.chatbot import ask_mistral_raw


def is_self_or_owner(requester_id, target_id):
    return int(requester_id) == int(target_id) or int(requester_id) == int(OWNER_ID)


def claim_bonus_for_members(count):
    if count >= 1000:
        return 20000
    if count >= 500:
        return 10000
    return CLAIM_BONUS


def parse_plain_amount(value):
    cleaned = str(value or "").replace(",", "").replace("$", "").strip()
    return int(cleaned) if cleaned.isdecimal() else None


# --- INVENTORY CALLBACK ---
async def inventory_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data.split("|")
    item_id = data[1]
    
    item = next((i for i in SHOP_ITEMS if i['id'] == item_id), None)
    if not item: return await query.answer("❌ Error", show_alert=True)

    rarity = "⚪ Common"
    if item['price'] > 50000: rarity = "🔵 Rare"
    if item['price'] > 500000: rarity = "🟡 Legendary"
    if item['price'] > 10000000: rarity = "🔴 Godly"

    text = f"💎 {stylize_text(item['name'])}\n💰 {format_money(item['price'])}\n🌟 {rarity}\n🛡️ Safe (Until Death)"
    await query.answer(text, show_alert=True)

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if await asyncio.to_thread(users_collection.find_one, {"user_id": user.id}):
        return await update.message.reply_text(f"✨ <b>Ara?</b> {get_mention(user)}, already registered!", parse_mode=ParseMode.HTML)
    
    await asyncio.to_thread(ensure_user_exists, user)
    await asyncio.to_thread(users_collection.update_one, {"user_id": user.id}, {"$set": {"balance": REGISTER_BONUS}})
    await update.message.reply_text(f"🎉 <b>Yayy!</b> {get_mention(user)} Registered!\n🎁 <b>Bonus:</b> <code>+{format_money(REGISTER_BONUS)}</code>", parse_mode=ParseMode.HTML)

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_channel_sender(update):
        return await update.message.reply_text(
            "⚠️ <b>Channel Identity Not Supported!</b>\n"
            "Please switch from <i>Channel</i> mode to your <b>Personal Telegram Account</b> to view balance.",
            parse_mode=ParseMode.HTML
        )
    target, error = await resolve_target(update, context)
    if not target and error == "No target": target = await asyncio.to_thread(ensure_user_exists, update.effective_user)
    elif not target: return await update.message.reply_text(error, parse_mode=ParseMode.HTML)

    rank_query = {"$and": [leaderboard_filter(), {"balance": {"$gt": target["balance"]}}]}
    rank = await asyncio.to_thread(users_collection.count_documents, rank_query) + 1
    status = "💖 Alive" if target['status'] == 'alive' else "💀 Dead"
    
    inventory = target.get('inventory', [])
    weapons = [i for i in inventory if i['type'] == 'weapon']
    armors = [i for i in inventory if i['type'] == 'armor']
    flex = [i for i in inventory if i['type'] == 'flex']
    
    best_w = max(weapons, key=lambda x: x['buff'])['name'] if weapons else "None"
    best_a = max(armors, key=lambda x: x['buff'])['name'] if armors else "None"
    
    kb = []
    row = []
    for item in flex:
        row.append(Button(item['name'], callback_data=f"inv_view|{item['id']}"))
        if len(row) == 2:
            kb.append(row)
            row = []
    if row: kb.append(row)
    
    # ── VIP / Premium Badge ──
    now = datetime.utcnow()
    vip_tier = target.get("vip_tier")
    is_prem = target.get("is_premium") or target.get("premium_lifetime")
    vip_expiry = target.get("vip_expiry")
    vip_tier_map = {
        "silver": "🥈 Silver VIP",
        "gold": "🥇 Gold VIP",
        "diamond": "💎 Diamond Sovereign",
    }
    vip_line = ""
    if vip_tier and is_prem:
        tier_label = vip_tier_map.get(vip_tier, f"👑 {vip_tier.title()} VIP")
        if vip_expiry:
            try:
                exp_dt = vip_expiry if isinstance(vip_expiry, datetime) else datetime.utcnow()
                rem = exp_dt - now
                if rem.total_seconds() > 0:
                    vip_line = f"\n{tier_label} | ⏳ <code>{format_time(rem)}</code> left"
                else:
                    vip_line = f"\n{tier_label} | <i>Expired</i>"
            except Exception:
                vip_line = f"\n{tier_label}"
        else:
            vip_line = f"\n{tier_label} (Lifetime)"

    # ── Active Perks (timer visible only in DM, not group) ──
    is_private = update.effective_chat.type == ChatType.PRIVATE
    perks_public = []   # shown in group (no timers)
    perks_private = []  # shown in DM (with exact timers)

    prot_expiry = get_active_protection(target)
    if prot_expiry:
        rem = prot_expiry - now
        perks_public.append("🛡️ Protected")
        perks_private.append(f"🛡️ Shield active — <code>{format_time(rem)}</code>")

    anti_rob = target.get("anti_rob_until")
    if anti_rob:
        try:
            ar_dt = anti_rob if isinstance(anti_rob, datetime) else None
            if ar_dt and ar_dt > now:
                rem = ar_dt - now
                perks_public.append("🔒 Anti-Rob Guard")
                perks_private.append(f"🔒 Anti-Rob Guard — <code>{format_time(rem)}</code>")
        except Exception:
            pass

    overdrive = target.get("gang_overdrive_until")
    if overdrive:
        try:
            od_dt = overdrive if isinstance(overdrive, datetime) else None
            if od_dt and od_dt > now:
                rem = od_dt - now
                perks_public.append("⚔️ Gang Overdrive")
                perks_private.append(f"⚔️ Gang Overdrive — <code>{format_time(rem)}</code>")
        except Exception:
            pass

    if is_private:
        # DM: show exact timers
        perks_line = ("\n\n✨ <b>" + stylize_text("Active Perks") + "</b>:\n" + "\n".join(perks_private)) if perks_private else ""
    else:
        # Group: show only icons, no timers (privacy protection)
        perks_line = ("\n\n✨ <b>" + stylize_text("Active Perks") + "</b>: " + "  ".join(perks_public)) if perks_public else ""

    msg = (
        f"<b>{get_mention(target, include_badge=True)}</b>{vip_line}\n"
        f"👛 <b>{format_money(target['balance'])}</b> | 🏆 <b>#{rank}</b>\n"
        f"❤️ <b>{status}</b> | ⚔️ <b>{target['kills']} Kills</b>"
        f"{perks_line}\n\n"
        f"🎒 <b>{stylize_text('Active Gear')}</b>:\n"
        f"🗡️ {best_w}\n🛡️ {best_a}\n\n"
        f"💎 <b>{stylize_text('Flex Collection')}</b>:"
    )
    if not flex: msg += "\n<i>Empty...</i>"
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(kb) if kb else None)

_TOP_CACHE = {"ts": 0, "msg": ""}

async def ranking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = time.time()
    if _TOP_CACHE["msg"] and (now - _TOP_CACHE["ts"]) < 60:
        return await update.message.reply_text(_TOP_CACHE["msg"], parse_mode=ParseMode.HTML)

    try:
        def fetch_leaderboards():
            try:
                eligible = leaderboard_filter()
                rich = list(users_collection.find(eligible).sort("balance", -1).limit(10))
                kills = list(users_collection.find(eligible).sort("kills", -1).limit(10))
            except Exception:
                rich = list(users_collection.find({"balance": {"$gt": 0}}).sort("balance", -1).limit(10))
                kills = list(users_collection.find({"kills": {"$gt": 0}}).sort("kills", -1).limit(10))
            return rich, kills

        rich, kills = await asyncio.to_thread(fetch_leaderboards)
        def get_badge(i): return ["🥇", "🥈", "🥉"][i-1] if i <= 3 else f"<code>{i}.</code>"

        msg = f"🏆 <b>{stylize_text('GLOBAL LEADERBOARD')}</b> 🏆\n\n💰 <b>{stylize_text('Top Richest')}</b>:\n"
        for i, d in enumerate(rich, 1):
            msg += f"{get_badge(i)} {get_mention(d, include_badge=True)} » <b>{format_money(d.get('balance', 0))}</b>\n"
        
        msg += f"\n🩸 <b>{stylize_text('Top Killers')}</b>:\n"
        for i, d in enumerate(kills, 1):
            msg += f"{get_badge(i)} {get_mention(d, include_badge=True)} » <b>{d.get('kills', 0)} Kills</b>\n"
        
        _TOP_CACHE["ts"] = now
        _TOP_CACHE["msg"] = msg
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
    except Exception as exc:
        print(f"[RANKING ERROR] {exc}", flush=True)
        if _TOP_CACHE["msg"]:
            return await update.message.reply_text(_TOP_CACHE["msg"], parse_mode=ParseMode.HTML)
        await update.message.reply_text(
            "🏆 <b>GLOBAL LEADERBOARD</b> 🏆\n\n<i>Leaderboard data is syncing. Please try again in a moment!</i>",
            parse_mode=ParseMode.HTML
        )

# ... (Keep claim and give functions from previous version, they are fine) ...
# I am re-pasting them below for completeness.

async def claim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message:
        return
    chat = update.effective_chat
    user = update.effective_user
    ensure_user_exists(user)

    if chat.type == ChatType.PRIVATE:
        return await message.reply_text(
            f"\U0001F381 <b>{stylize_text('Group Claim Bonus')}</b>\n\n"
            f"<b>/claim</b> works only in groups where Kazumi was added.\n"
            f"The first eligible user gets a size-based reward.\n\n"
            f"<b>Rewards:</b>\n"
            f"100+ members: <code>{format_money(CLAIM_BONUS)}</code>\n"
            f"500+ members: <code>{format_money(10000)}</code>\n"
            f"1000+ members: <code>{format_money(20000)}</code>",
            parse_mode=ParseMode.HTML,
        )

    group_doc = groups_collection.find_one({"chat_id": chat.id})
    if not group_doc:
        groups_collection.update_one(
            {"chat_id": chat.id},
            {"$setOnInsert": {"chat_id": chat.id, "title": chat.title, "claimed": False}},
            upsert=True,
        )
        group_doc = groups_collection.find_one({"chat_id": chat.id}) or {}

    if group_doc.get("claimed"):
        claimed_by = group_doc.get("claimed_by_name") or "someone"
        claimed_at = group_doc.get("claimed_at")
        when = claimed_at.strftime("%d %b %Y") if claimed_at else "earlier"
        return await message.reply_text(
            f"\U0000274C <b>{stylize_text('Already Claimed')}</b>\n\n"
            f"This group bonus was claimed by <b>{claimed_by}</b> on <code>{when}</code>.\n"
            f"<b>Tip:</b> use <code>/daily</code>, <code>/missions</code>, <code>/spin</code>, and games for more coins.",
            parse_mode=ParseMode.HTML,
        )
    
    try:
        count = await context.bot.get_chat_member_count(chat.id)
    except Exception:
        return await message.reply_text(
            "\U000026A0\ufe0f <b>Can not check group size.</b>\n"
            "Make Kazumi admin or try again in a moment.",
            parse_mode=ParseMode.HTML,
        )

    if count < MIN_CLAIM_MEMBERS:
        roast = await ask_mistral_raw("Roaster", f"Roast {user.first_name} for claiming in a group with only {count} members.")
        return await message.reply_text(
            f"\U0000274C <b>{stylize_text('Claim Locked')}</b>\n\n"
            f"<b>Current members:</b> <code>{count}</code>\n"
            f"<b>Required:</b> <code>{MIN_CLAIM_MEMBERS}</code>\n"
            f"<b>Reward starts:</b> <code>{format_money(CLAIM_BONUS)}</code>\n\n"
            f"\U0001F525 {stylize_text(roast or 'Bring more members first.')}",
            parse_mode=ParseMode.HTML,
        )
    claim_bonus = claim_bonus_for_members(count)
    
    claimed = groups_collection.update_one(
        {"chat_id": chat.id, "claimed": {"$ne": True}},
        {
            "$set": {
                "claimed": True,
                "claimed_by": user.id,
                "claimed_by_name": user.first_name,
                "claimed_at": message.date.replace(tzinfo=None) if message.date else None,
                "title": chat.title,
            }
        },
    )
    if claimed.modified_count == 0:
        return await message.reply_text(
            f"\U0000274C <b>{stylize_text('Too Late')}</b>\n"
            "Someone claimed this group bonus just before you.",
            parse_mode=ParseMode.HTML,
        )

    adjust_user_balance(
        user.id,
        claim_bonus,
        "claim_bonus",
        f"Claimed group bonus in {chat.title or 'group'}",
        chat_id=chat.id,
        source="/claim",
        meta={"member_count": count},
    )
    await message.reply_text(
        f"\U00002705 <b>{stylize_text('Group Bonus Claimed')}</b>\n\n"
        f"{get_mention(user)} received <code>{format_money(claim_bonus)}</code>.\n"
        f"<b>Group:</b> {chat.title or 'This group'}\n"
        f"<b>Members checked:</b> <code>{count}</code>\n\n"
        "<i>This bonus can be claimed only once per group.</i>",
        parse_mode=ParseMode.HTML,
    )

async def give(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender = ensure_user_exists(update.effective_user)
    args = context.args
    if not args: return await update.message.reply_text("⚠️ <b>Usage:</b> <code>/give 100 @user</code>", parse_mode=ParseMode.HTML)
    amount = None
    target_str = None
    for arg in args:
        parsed = parse_plain_amount(arg)
        if parsed is not None and amount is None:
            amount = parsed
        else:
            target_str = arg
    if amount is None: return await update.message.reply_text("⚠️ Invalid Amount", parse_mode=ParseMode.HTML)

    target, error = await resolve_target(update, context, specific_arg=target_str)
    if not target: return await update.message.reply_text(error or "⚠️ Tag someone.", parse_mode=ParseMode.HTML)

    if amount <= 0 or sender['balance'] < amount or sender['user_id'] == target['user_id']: return await update.message.reply_text("⚠️ Invalid Transaction.", parse_mode=ParseMode.HTML)

    # Tax Calculation
    is_premium_sender = sender.get("is_premium", False)
    tax_rate = 0.05 if is_premium_sender else (MARRIED_TAX_RATE if sender.get("partner_id") == target["user_id"] else TAX_RATE)
    
    tax = int(amount * tax_rate)
    final = amount - tax
    
    charged = adjust_user_balance(
        sender["user_id"],
        -amount,
        "give",
        f"Sent coins to {target.get('name', 'user')}",
        chat_id=update.effective_chat.id if update.effective_chat else None,
        target_user_id=target["user_id"],
        source="/give",
        require_gte=amount,
        meta={"gross_amount": amount, "tax": tax, "final_amount": final},
    )
    if not charged:
        return await update.message.reply_text("⚠️ Invalid Transaction.", parse_mode=ParseMode.HTML)
    adjust_user_balance(
        target["user_id"],
        final,
        "receive",
        f"Received coins from {sender.get('name', 'user')}",
        chat_id=update.effective_chat.id if update.effective_chat else None,
        target_user_id=sender["user_id"],
        source="/give",
        meta={"gross_amount": amount, "tax": tax},
    )
    if tax > 0:
        adjust_user_balance(
            OWNER_ID,
            tax,
            "tax",
            f"Collected give tax from {sender.get('name', 'user')}",
            chat_id=update.effective_chat.id if update.effective_chat else None,
            target_user_id=sender["user_id"],
            source="/give",
            meta={"gross_amount": amount},
        )

    msg = f"💸 <b>{stylize_text('Transfer Complete')}!</b>\n👤 From: {get_mention(sender)}\n👤 To: {get_mention(target)}\n💰 Sent: <code>{format_money(final)}</code>\n🏦 Tax: <code>{format_money(tax)}</code>"
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
    await log_to_channel(context.bot, "transfer", {"user": sender['name'], "action": f"Sent {amount} to {target['name']}", "chat": "Economy"})


async def ledger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target, error = await resolve_target(update, context)
    if not target and error == "No target":
        target = ensure_user_exists(update.effective_user)
    elif not target:
        return await update.message.reply_text(error, parse_mode=ParseMode.HTML)
    if not is_self_or_owner(update.effective_user.id, target["user_id"]):
        return await update.message.reply_text(
            "\U0001F512 <b>Wallet history is private.</b>\n"
            "Only your own ledger can be opened from Telegram or the Mini App.",
            parse_mode=ParseMode.HTML,
        )

    category = context.args[0].lower() if context.args else None
    rows = get_balance_history(target["user_id"], limit=10, category=category)
    summary = balance_summary(target["user_id"])

    lines = [
        f"📒 <b>{stylize_text('Wallet History')}</b>",
        f"{get_mention(target, include_badge=True)}",
        f"Today: <code>+{format_money(summary['earned'])}</code> in | <code>-{format_money(summary['spent'])}</code> out | Net <code>{format_money(summary['net'])}</code>",
        "",
    ]
    if not rows:
        lines.append("<i>No balance logs yet.</i>")
    else:
        for row in rows:
            delta = int(row.get("delta", 0))
            sign = "+" if delta >= 0 else "-"
            amount = format_money(abs(delta))
            category_name = str(row.get("category", "general")).replace("_", " ").title()
            reason = row.get("reason", "Balance update")
            stamp = row.get("created_at")
            when = format_history_time(stamp)
            lines.extend([
                f"{sign} <b>{amount}</b> • <code>{category_name}</code>",
                f"{reason}",
                f"<i>{format_money(row.get('old_balance', 0))} → {format_money(row.get('new_balance', 0))} • {when}</i>",
                "",
            ])
    await update.message.reply_text("\n".join(lines).strip(), parse_mode=ParseMode.HTML)
