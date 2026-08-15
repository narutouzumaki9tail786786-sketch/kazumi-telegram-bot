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

import random
import asyncio
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode, ChatType
from telegram.error import TelegramError
from kazumi.config import PROTECT_1D_COST, PROTECT_2D_COST, REVIVE_COST, AUTO_REVIVE_HOURS, OWNER_ID
from kazumi.utils import ensure_user_exists, resolve_target, is_protected, get_active_protection, get_own_protection_expiry, format_time, format_money, get_mention, check_auto_revive, stylize_text, remove_one_inventory_item, protection_max_duration
from kazumi.database import users_collection
from kazumi.game_rules import resolve_target_source
from kazumi.ledger import adjust_user_balance
from kazumi.plugins.chatbot import ask_mistral_raw

PROTECTION_REMINDERS = (
    ("2h", timedelta(hours=2)),
    ("30m", timedelta(minutes=30)),
)
PROTECTION_REMINDER_INTERVAL = 300
PROTECTION_RENEW_WINDOW = timedelta(hours=2)

def _fresh_user_doc(user_id, fallback=None):
    return users_collection.find_one({"user_id": user_id}) or fallback


def _unprotected_query(now):
    return {
        "$or": [
            {"protection_expiry": {"$exists": False}},
            {"protection_expiry": None},
            {"protection_expiry": {"$lte": now}},
        ]
    }

# --- AI NARRATION ---
async def get_narrative(action_type, attacker_mention, target_mention):
    if action_type == 'kill':
        prompt = "Write a funny, savage kill message where 'P1' kills 'P2'. Max 15 words. Use Hinglish."
    elif action_type == 'rob':
        prompt = "Write a funny robbery message where 'P1' steals from 'P2'. Max 15 words. Use Hinglish."
    else: return "P1 interaction P2."
    res = await ask_mistral_raw("Game Narrator", prompt, 50)
    text = res if res and "P1" in res else f"P1 {action_type} P2!"
    return text.replace("P1", attacker_mention).replace("P2", target_mention)

# --- KILL ---
async def kill(update: Update, context: ContextTypes.DEFAULT_TYPE):
    attacker = ensure_user_exists(update.effective_user)
    explicit_target = context.args[0] if context.args else None
    target_source = resolve_target_source(
        has_reply=bool(update.effective_message and update.effective_message.reply_to_message),
        explicit_target=explicit_target,
    )
    if target_source == "conflict":
        return await update.message.reply_text(
            "⚠️ <b>Choose one target only.</b>\n"
            "Either reply with <code>/kill</code> or use <code>/kill @username</code>.",
            parse_mode=ParseMode.HTML,
        )
    target, error = await resolve_target(update, context)
    if not target: return await update.message.reply_text(error if error else "⚠️ <b>Reply</b> or <b>Tag</b> to kill!", parse_mode=ParseMode.HTML)

    # Checks
    if target.get('is_bot'): return await update.message.reply_text("🤖 <b>Bot Shield!</b> Can't kill robots.", parse_mode=ParseMode.HTML)
    if target['user_id'] == OWNER_ID: return await update.message.reply_text("🙊 <b>Senpai Shield!</b> Can't kill the Owner.", parse_mode=ParseMode.HTML)
    if attacker['status'] == 'dead': return await update.message.reply_text("💀 <b>You are dead!</b> Wait 6h or /revive.", parse_mode=ParseMode.HTML)
    if target['user_id'] == attacker['user_id']: return await update.message.reply_text("🤔 Don't kill yourself.", parse_mode=ParseMode.HTML)
    if target['status'] == 'dead': return await update.message.reply_text("⚰️ <b>Already dead!</b>", parse_mode=ParseMode.HTML)
    
    expiry = get_active_protection(target)
    if expiry:
        return await update.message.reply_text("\U0001f6e1\ufe0f <b>Blocked!</b> Target is protected.", parse_mode=ParseMode.HTML)

    # Daily Limit Check
    is_prem = attacker.get("is_premium", False)
    limit = 400 if is_prem else 200
    today = datetime.utcnow().strftime("%Y-%m-%d")
    
    kill_data = attacker.get("kill_limit", {})
    if kill_data.get("date") != today:
        attacker_kills_today = 0
    else:
        attacker_kills_today = kill_data.get("count", 0)
        
    if attacker_kills_today >= limit:
        return await update.message.reply_text(f"⚠️ <b>Limit Reached!</b> You can only kill {limit} users per day.", parse_mode=ParseMode.HTML)

    target = _fresh_user_doc(target["user_id"], target)
    if target.get('status') == 'dead': return await update.message.reply_text("⚰️ <b>Already dead!</b>", parse_mode=ParseMode.HTML)
    expiry = get_active_protection(target)
    if expiry:
        return await update.message.reply_text("\U0001f6e1\ufe0f <b>Blocked!</b> Target is protected.", parse_mode=ParseMode.HTML)

    # Logic
    base_reward = random.randint(200, 400) if is_prem else random.randint(100, 200)
    buff = sum(i['buff'] for i in attacker.get('inventory', []) if i['type'] == 'weapon')
    final_reward = int(base_reward * (1 + buff))

    # Execute
    now = datetime.utcnow()
    killed = users_collection.update_one(
        {"user_id": target["user_id"], "status": {"$ne": "dead"}, **_unprotected_query(now)},
        {"$set": {"status": "dead", "death_time": datetime.utcnow()}, "$inc": {"deaths": 1}},
    )
    if not killed.modified_count:
        target = _fresh_user_doc(target["user_id"], target)
        if get_active_protection(target):
            return await update.message.reply_text("\U0001f6e1\ufe0f <b>Blocked!</b> Target is protected.", parse_mode=ParseMode.HTML)
        return await update.message.reply_text("⚰️ <b>Already dead!</b>", parse_mode=ParseMode.HTML)

    # Loot Item (50%)
    stolen_item_text = ""
    t_inv = target.get('inventory', [])
    if t_inv and random.random() < 0.50:
        item = random.choice(t_inv)
        item = remove_one_inventory_item(target, item.get("id"))
        if item:
            users_collection.update_one({"user_id": attacker["user_id"]}, {"$push": {"inventory": item}})
            stolen_item_text = f"\n🎒 <b>{stylize_text('Looted')}:</b> {item['name']}"

    adjust_user_balance(
        attacker["user_id"],
        final_reward,
        "kill",
        f"Killed {target.get('name', 'user')}",
        chat_id=update.effective_chat.id if update.effective_chat else None,
        target_user_id=target["user_id"],
        source="/kill",
        extra_inc={"kills": 1},
        extra_set={"kill_limit": {"date": today, "count": attacker_kills_today + 1}},
        meta={"base_reward": base_reward, "buff": buff},
    )

    narration = await get_narrative("kill", get_mention(attacker), get_mention(target))
    buff_text = f"(+{int(buff*100)}% Buff)" if buff > 0 else ""

    await update.message.reply_text(
        f"🔪 <b>{stylize_text('MURDER')}!</b>\n\n"
        f"📝 <i>{narration}</i>\n\n"
        f"😈 <b>{stylize_text('Killer')}:</b> {get_mention(attacker)}\n"
        f"💀 <b>{stylize_text('Victim')}:</b> {get_mention(target)}\n"
        f"💵 <b>{stylize_text('Loot')}:</b> <code>{format_money(final_reward)}</code> {buff_text}{stolen_item_text}", 
        parse_mode=ParseMode.HTML
    )

# --- ROB ---
async def rob(update: Update, context: ContextTypes.DEFAULT_TYPE):
    attacker = ensure_user_exists(update.effective_user)
    if not context.args: return await update.message.reply_text("⚠️ <code>/rob 100 @user</code>", parse_mode=ParseMode.HTML)
    try: amount = int(context.args[0])
    except: return await update.message.reply_text("⚠️ Invalid Amount", parse_mode=ParseMode.HTML)

    target_arg = context.args[1] if len(context.args) > 1 else None
    target, error = await resolve_target(update, context, specific_arg=target_arg)
    if not target: return await update.message.reply_text(error or "⚠️ Tag victim", parse_mode=ParseMode.HTML)

    if target.get('is_bot') or target['user_id'] == OWNER_ID: return await update.message.reply_text("🛡️ Protected Entity.", parse_mode=ParseMode.HTML)
    if attacker['status'] == 'dead': return await update.message.reply_text("💀 Dead men steal no coins.", parse_mode=ParseMode.HTML)
    if target['user_id'] == attacker['user_id']: return await update.message.reply_text("🤦‍♂️ No.", parse_mode=ParseMode.HTML)
    
    expiry = get_active_protection(target)
    if expiry:
        return await update.message.reply_text("\U0001f6e1\ufe0f <b>Shielded!</b> Target is protected.", parse_mode=ParseMode.HTML)

    if target['balance'] < amount: return await update.message.reply_text("📉 Too poor.", parse_mode=ParseMode.HTML)

    # Daily Limit Check
    is_prem = attacker.get("is_premium", False)
    limit = 300 if is_prem else 150 # Following the image mockup values
    today = datetime.utcnow().strftime("%Y-%m-%d")
    
    rob_data = attacker.get("rob_limit", {})
    if rob_data.get("date") != today:
        attacker_robs_today = 0
    else:
        attacker_robs_today = rob_data.get("count", 0)
        
    if attacker_robs_today >= limit:
        return await update.message.reply_text(f"⚠️ <b>Limit Reached!</b> You can only rob {limit} users per day.", parse_mode=ParseMode.HTML)

    target = _fresh_user_doc(target["user_id"], target)
    expiry = get_active_protection(target)
    if expiry:
        return await update.message.reply_text("\U0001f6e1\ufe0f <b>Shielded!</b> Target is protected.", parse_mode=ParseMode.HTML)

    # Tax logic
    tax_rate = 0.05 if is_prem else 0.10
    tax = int(amount * tax_rate)
    stolen_amount = amount - tax

    # Block
    block_chance = sum(i['buff'] for i in target.get('inventory', []) if i['type'] == 'armor')
    if random.random() < block_chance:
        return await update.message.reply_text(f"🛡️ <b>BLOCKED!</b> {get_mention(target)}'s armor stopped you!", parse_mode=ParseMode.HTML)

    # Execute
    now = datetime.utcnow()
    robbed = adjust_user_balance(
        target["user_id"],
        -amount,
        "robbed",
        f"Robbed by {attacker.get('name', 'user')}",
        chat_id=update.effective_chat.id if update.effective_chat else None,
        target_user_id=attacker["user_id"],
        source="/rob",
        require_gte=amount,
        extra_query=_unprotected_query(now),
        meta={"gross_amount": amount, "tax": tax},
    )
    if not robbed:
        target = _fresh_user_doc(target["user_id"], target)
        if get_active_protection(target):
            return await update.message.reply_text("\U0001f6e1\ufe0f <b>Shielded!</b> Target is protected.", parse_mode=ParseMode.HTML)
        return await update.message.reply_text("📉 Too poor.", parse_mode=ParseMode.HTML)

    # Loot Item (Dead Only)
    stolen_item_text = ""
    if target['status'] == 'dead':
        t_inv = target.get('inventory', [])
        if t_inv and random.random() < 0.20:
            item = random.choice(t_inv)
            item = remove_one_inventory_item(target, item.get("id"))
            if item:
                users_collection.update_one({"user_id": attacker["user_id"]}, {"$push": {"inventory": item}})
                stolen_item_text = f"\n🎒 <b>{stylize_text('Looted Corpse')}:</b> {item['name']}"

    adjust_user_balance(
        attacker["user_id"],
        stolen_amount,
        "rob",
        f"Robbed {target.get('name', 'user')}",
        chat_id=update.effective_chat.id if update.effective_chat else None,
        target_user_id=target["user_id"],
        source="/rob",
        extra_set={"rob_limit": {"date": today, "count": attacker_robs_today + 1}},
        meta={"gross_amount": amount, "tax": tax},
    )
    if tax > 0:
        adjust_user_balance(
            OWNER_ID,
            tax,
            "tax",
            f"Collected rob tax from {attacker.get('name', 'user')}",
            chat_id=update.effective_chat.id if update.effective_chat else None,
            target_user_id=attacker["user_id"],
            source="/rob",
            meta={"gross_amount": amount},
        )
    
    att_link = get_mention(attacker)
    tar_link = get_mention(target)
    narration = await get_narrative("rob", att_link, tar_link)
    
    header = f"🧟 <b>{stylize_text('GRAVE ROBBERY')}!</b>" if target['status'] == 'dead' else f"💰 <b>{stylize_text('ROBBERY')}!</b>"

    await update.message.reply_text(
        f"{header}\n\n"
        f"📝 <i>{narration}</i>\n\n"
        f"😈 <b>{stylize_text('Thief')}:</b> {att_link}\n"
        f"💸 <b>{stylize_text('Stolen')}:</b> <code>{format_money(amount)}</code>{stolen_item_text}", 
        parse_mode=ParseMode.HTML
    )

# --- PROTECT ---
def _own_protection_status_text(user):
    expiry = _cap_protection_expiry(get_active_protection(user), user=user)
    if not expiry:
        return (
            "\U0001f6e1\ufe0f <b>Shield Status</b>\n"
            "━━━━━━━━━━━━\n\n"
            "Status: <b>Not protected</b>\n"
            f"Use <code>/protect 1d</code> to activate for <code>{format_money(PROTECT_1D_COST)}</code>."
        )
    rem = expiry - datetime.utcnow()
    return (
        "\U0001f6e1\ufe0f <b>Shield Status</b>\n"
        "━━━━━━━━━━━━\n\n"
        "Status: <b>Protected</b>\n"
        f"Ends in: <code>{format_time(rem)}</code>\n"
        f"Ends at UTC: <code>{expiry.strftime('%d %b %Y %H:%M')}</code>\n\n"
        "<i>You can renew during the final 2 hours. Free users can hold 24h; premium users 48h.</i>"
    )


def _cap_protection_expiry(expiry_dt, now=None, user=None):
    if not expiry_dt:
        return None
    now = now or datetime.utcnow()
    if expiry_dt <= now:
        return None
    return min(expiry_dt, now + protection_max_duration(user))


def _requested_protection_expiry(days, user=None):
    now = datetime.utcnow()
    requested_duration = timedelta(days=days)
    return now + min(requested_duration, protection_max_duration(user))


def _set_protection_expiry(user_id, expiry_dt):
    now = datetime.utcnow()
    current = users_collection.find_one(
        {"user_id": user_id},
        {"user_id": 1, "is_premium": 1, "premium_until": 1, "premium_lifetime": 1, "protection_expiry": 1},
    ) or {"user_id": user_id}
    current_expiry = _cap_protection_expiry(get_own_protection_expiry(current), now, current)
    desired_expiry = _cap_protection_expiry(expiry_dt, now, current) or (now + protection_max_duration(current))
    final_expiry = max(current_expiry, desired_expiry) if current_expiry else desired_expiry
    final_expiry = _cap_protection_expiry(final_expiry, now, current) or desired_expiry
    users_collection.update_one(
        {"user_id": user_id},
        {"$set": {"protection_expiry": final_expiry, "protection_alerts": {}}},
    )
    return final_expiry


async def protection_reminder_loop(bot):
    while True:
        try:
            now = datetime.utcnow()
            max_window = max(window for _, window in PROTECTION_REMINDERS)
            query = {
                "protection_expiry": {
                    "$gt": now,
                    "$lte": now + max_window + timedelta(minutes=PROTECTION_REMINDER_INTERVAL // 60 + 2),
                }
            }
            projection = {"user_id": 1, "name": 1, "partner_id": 1, "protection_expiry": 1, "protection_alerts": 1}
            rows = await asyncio.to_thread(
                lambda: list(users_collection.find(query, projection).limit(500))
            )
            for user in rows:
                expiry = get_own_protection_expiry(user)
                if not expiry:
                    continue
                active_expiry = get_active_protection(user)
                if active_expiry and active_expiry > expiry + timedelta(seconds=30):
                    continue
                remaining = expiry - now
                alerts = user.get("protection_alerts") or {}
                for key, window in PROTECTION_REMINDERS:
                    lower_bound = window - timedelta(seconds=PROTECTION_REMINDER_INTERVAL + 30)
                    if alerts.get(key) or remaining > window or remaining < lower_bound:
                        continue
                    text = (
                        "\U000026A0\ufe0f <b>Shield Ending Soon</b>\n"
                        "━━━━━━━━━━━━\n\n"
                        f"Your protection ends in <code>{format_time(remaining)}</code>.\n"
                        "Renew in DM with <code>/protect 1d</code> before the timer ends."
                    )
                    try:
                        await bot.send_message(chat_id=user["user_id"], text=text, parse_mode=ParseMode.HTML)
                    except TelegramError:
                        pass
                    await asyncio.to_thread(
                        users_collection.update_one,
                        {"user_id": user["user_id"]},
                        {"$set": {f"protection_alerts.{key}": True}},
                    )
        except Exception as exc:
            print(f"[PROTECT REMINDER ERROR] {exc}", flush=True)
        await asyncio.sleep(PROTECTION_REMINDER_INTERVAL)


async def protect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Acknowledge immediately; perform the Mongo-backed protection flow in background."""
    message = update.effective_message
    if not message:
        return

    await message.reply_text("⏳ <i>Checking protection…</i>", parse_mode=ParseMode.HTML)
    context.application.create_task(_protect_after_acknowledgement(update, context), update=update)


async def _protect_after_acknowledgement(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # PyMongo is synchronous. Keep its network round-trips out of PTB's event
    # loop so other updates can continue while this command is being processed.
    sender = await asyncio.to_thread(ensure_user_exists, update.effective_user)
    if not context.args or context.args[0].lower() in {"status", "check", "time", "timer"}:
        if update.effective_chat.type == ChatType.PRIVATE:
            return await update.message.reply_text(_own_protection_status_text(sender), parse_mode=ParseMode.HTML)
        return await update.message.reply_text(
            "\U0001f6e1\ufe0f <b>Protection</b>\n"
            "Use <code>/protect 1d</code> to buy shield.\n"
            "DM me <code>/protect</code> to check your private timer.",
            parse_mode=ParseMode.HTML,
        )

    dur = context.args[0].lower()
    is_prem = sender.get("is_premium", False)
    
    if dur == '1d': cost, days = PROTECT_1D_COST, 1
    elif dur == '2d': 
        if not is_prem: return await update.message.reply_text("❌ <b>Premium Only!</b> Normal users can only protect for 1 day.", parse_mode=ParseMode.HTML)
        cost, days = PROTECT_2D_COST, 2
    else: return await update.message.reply_text("⚠️ 1d or 2d only!", parse_mode=ParseMode.HTML)

    target_arg = context.args[1] if len(context.args) > 1 else None
    target, _ = await resolve_target(update, context, specific_arg=target_arg)
    if not target: target = sender
    is_self = target['user_id'] == sender['user_id']

    if not is_self and sender.get("partner_id") != target["user_id"]:
         return await update.message.reply_text("⛔ You can only protect yourself or your partner!", parse_mode=ParseMode.HTML)

    now = datetime.utcnow()
    own_expiry = get_own_protection_expiry(target)
    capped_own_expiry = _cap_protection_expiry(own_expiry, now, target)
    if own_expiry and capped_own_expiry and own_expiry > capped_own_expiry:
        await asyncio.to_thread(_set_protection_expiry, target["user_id"], capped_own_expiry)

    previous_expiry = _cap_protection_expiry(
        await asyncio.to_thread(get_active_protection, target),
        now,
        target,
    )
    if previous_expiry:
        remaining = previous_expiry - now
        if remaining > PROTECTION_RENEW_WINDOW:
            renew_in = remaining - PROTECTION_RENEW_WINDOW
            return await update.message.reply_text(
                "\U0001f6e1\ufe0f <b>Already Safe!</b> "
                f"Expires in <code>{format_time(remaining)}</code>.\n"
                f"Renewal opens in <code>{format_time(renew_in)}</code>.\n"
                "<tg-spoiler><i>Renew means buying the next shield near expiry; protection cannot stack beyond your 24h/48h cap.</i></tg-spoiler>",
                parse_mode=ParseMode.HTML,
            )
    if sender['balance'] < cost: return await update.message.reply_text(f"❌ <b>Poor!</b> Need <code>{format_money(cost)}</code>.", parse_mode=ParseMode.HTML)

    charged = await asyncio.to_thread(
        adjust_user_balance,
        sender["user_id"],
        -cost,
        "protect",
        f"Protection purchase for {target.get('name', 'self')}",
        chat_id=update.effective_chat.id if update.effective_chat else None,
        target_user_id=target["user_id"],
        source="/protect",
        require_gte=cost,
        meta={"days": days, "cost": cost},
    )
    if not charged:
        return await update.message.reply_text(f"❌ <b>Poor!</b> Need <code>{format_money(cost)}</code>.", parse_mode=ParseMode.HTML)
    expiry_dt = _requested_protection_expiry(days, target)
    final_expiry = await asyncio.to_thread(_set_protection_expiry, target["user_id"], expiry_dt)
    
    partner_id = target.get("partner_id")
    extra = ""
    if partner_id:
        await asyncio.to_thread(_set_protection_expiry, partner_id, final_expiry)
        extra = "\n💞 <b>Bonus:</b> Partner also protected!"

    rem = final_expiry - datetime.utcnow()
    title = stylize_text("Shield Renewed" if previous_expiry else "Shield Active")
    if is_self:
        if update.effective_chat.type == ChatType.PRIVATE:
            msg = f"\U0001f6e1\ufe0f <b>{title}!</b> Safe for <code>{format_time(rem)}</code>.{extra}"
        else:
            msg = f"\U0001f6e1\ufe0f <b>{title}!</b> Protection enabled.{extra}"
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(f"\U0001f6e1\ufe0f <b>{title}!</b> You protected {get_mention(target)} for <code>{format_time(rem)}</code>.{extra}", parse_mode=ParseMode.HTML)

async def revive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reviver = ensure_user_exists(update.effective_user)
    target, _ = await resolve_target(update, context)
    if not target: target = reviver

    if target['status'] == 'alive': return await update.message.reply_text("✨ Alive!", parse_mode=ParseMode.HTML)
    
    if check_auto_revive(target):
        return await update.message.reply_text("✨ <b>Miracle!</b> Auto-revived just now.", parse_mode=ParseMode.HTML)

    if reviver['balance'] < REVIVE_COST: return await update.message.reply_text(f"❌ Need <code>{format_money(REVIVE_COST)}</code>.", parse_mode=ParseMode.HTML)

    charged = adjust_user_balance(
        reviver["user_id"],
        -REVIVE_COST,
        "revive",
        f"Revived {target.get('name', 'user')}",
        chat_id=update.effective_chat.id if update.effective_chat else None,
        target_user_id=target["user_id"],
        source="/revive",
        require_gte=REVIVE_COST,
        meta={"cost": REVIVE_COST},
    )
    if not charged:
        return await update.message.reply_text(f"❌ Need <code>{format_money(REVIVE_COST)}</code>.", parse_mode=ParseMode.HTML)
    adjust_user_balance(
        OWNER_ID,
        REVIVE_COST,
        "tax",
        f"Collected revive fee from {reviver.get('name', 'user')}",
        chat_id=update.effective_chat.id if update.effective_chat else None,
        target_user_id=reviver["user_id"],
        source="/revive",
        meta={"gross_amount": REVIVE_COST},
    )
    users_collection.update_one({"user_id": target["user_id"]}, {"$set": {"status": "alive", "death_time": None}})
    await update.message.reply_text(f"💖 <b>{stylize_text('Revived')}!</b> Paid {format_money(REVIVE_COST)}.", parse_mode=ParseMode.HTML)
