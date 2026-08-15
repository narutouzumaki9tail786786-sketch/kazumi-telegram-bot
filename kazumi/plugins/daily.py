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
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode, ChatType
from kazumi.utils import ensure_user_exists, format_money, daily_streak_bonus
from kazumi.ledger import adjust_user_balance
from kazumi.missions import track_mission

async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != ChatType.PRIVATE:
        bot_username = context.bot.username or "KazumiRpgBot"
        return await update.message.reply_text(
            "\U0001F512 <b>Daily rewards are DM only.</b>\n\n"
            "<i>Open my private chat to claim your streak safely.</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "Claim in DM",
                    url=f"https://t.me/{bot_username}?start=daily"
                )
            ]])
        )

    user = await asyncio.to_thread(ensure_user_exists, update.effective_user)
    now = datetime.utcnow()
    last = user.get("last_daily")
    
    if last and (now - last) < timedelta(hours=24):
        rem = timedelta(hours=24) - (now - last)
        return await update.message.reply_text(f"⏳ <b>Cooldown!</b> Wait {int(rem.total_seconds()//3600)}h.", parse_mode=ParseMode.HTML)
    
    streak = user.get("daily_streak", 0)
    if last and (now - last) > timedelta(hours=48): streak = 0 # Reset
    
    streak += 1
    is_prem = user.get("is_premium", False)
    reward = 5000 if is_prem else 2000
    streak_bonus = daily_streak_bonus(streak)
    weekly_bonus = 10000 if streak % 7 == 0 else 0
    bonus = streak_bonus + weekly_bonus
    
    msg = f"📅 <b>Day {streak}!</b>\nReceived: <code>{format_money(reward)}</code>"
    if streak_bonus: msg += f"\n🔥 <b>Streak Bonus:</b> <code>{format_money(streak_bonus)}</code>"
    if weekly_bonus: msg += f"\n🎉 <b>Weekly Bonus:</b> <code>{format_money(weekly_bonus)}</code>"
    if bonus: msg += f"\n💰 <b>Total:</b> <code>{format_money(reward + bonus)}</code>"

    cutoff = now - timedelta(hours=24)
    claimed = await asyncio.to_thread(
        adjust_user_balance,
        user["user_id"],
        reward + bonus,
        "daily",
        f"Claimed daily reward streak {streak}",
        chat_id=update.effective_chat.id if update.effective_chat else None,
        source="/daily",
        extra_query={
            "$or": [{"last_daily": {"$exists": False}}, {"last_daily": None}, {"last_daily": {"$lte": cutoff}}],
        },
        extra_set={"last_daily": now, "daily_streak": streak},
        meta={"streak": streak, "base_reward": reward, "streak_bonus": streak_bonus, "weekly_bonus": weekly_bonus, "bonus": bonus},
    )
    if not claimed:
        return await update.message.reply_text("⏳ <b>Cooldown!</b> Daily was already claimed.", parse_mode=ParseMode.HTML)
    asyncio.create_task(asyncio.to_thread(track_mission, user["user_id"], "daily_claim"))
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
