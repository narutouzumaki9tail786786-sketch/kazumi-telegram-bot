# 🌸 Kazumi — Bank Heist System

import random
import asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.error import TelegramError
from telegram.ext import ContextTypes
from telegram.constants import ParseMode, ChatType
from kazumi.utils import ensure_user_exists, get_mention, format_money, stylize_text, add_xp
from kazumi.config import HEIST_MIN_PLAYERS, HEIST_MAX_PLAYERS, HEIST_BASE_REWARD, HEIST_JOIN_TIME, XP_PER_GAME_WIN
from kazumi.game_rules import FARM_GAME_DAILY_CAP, capped_daily_payout
from kazumi.ledger import adjust_user_balance, positive_credit_total_today

active_heists = {}  # {chat_id: {players: [], start_time, msg_id}}
HEIST_STALE_AFTER = timedelta(seconds=max(HEIST_JOIN_TIME + 60, 120))
HEIST_MAX_SHARE = 5_000
FARM_LIMIT_CATEGORIES = ("wordgame_win", "wordbomb_win", "heist_success")


async def _safe_send(bot, chat_id, text):
    try:
        return await bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML)
    except TelegramError as exc:
        print(f"[HEIST SEND SKIPPED] chat={chat_id}: {exc}", flush=True)
        return None


def _clear_stale_heist(chat_id: int) -> bool:
    heist = active_heists.get(chat_id)
    if not heist:
        return False
    started = heist.get("start_time")
    if isinstance(started, datetime) and datetime.utcnow() - started <= HEIST_STALE_AFTER:
        return False
    active_heists.pop(chat_id, None)
    return True

async def heist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type == ChatType.PRIVATE:
        return await update.message.reply_text("❌ Group Only!", parse_mode=ParseMode.HTML)
    
    user = ensure_user_exists(update.effective_user)
    uid = user['user_id']
    
    _clear_stale_heist(chat.id)
    if chat.id in active_heists:
        h = active_heists[chat.id]
        if uid in h['players']:
            return await update.message.reply_text("⚠️ Already joined!", parse_mode=ParseMode.HTML)
        if len(h['players']) >= HEIST_MAX_PLAYERS:
            return await update.message.reply_text("⚠️ Heist full!", parse_mode=ParseMode.HTML)
        
        h['players'].append(uid)
        count = len(h['players'])
        success_pct = min(30 + (count * 12), 90)
        
        await update.message.reply_text(
            f"⚡ {get_mention(user)} joined the heist!\n"
            f"👥 <b>{count}/{HEIST_MAX_PLAYERS}</b> | 🎯 Success: <b>{success_pct}%</b>",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Start new heist
    active_heists[chat.id] = {"players": [uid], "start_time": datetime.utcnow()}
    
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton(f"⚡ {stylize_text('Join Heist')}", callback_data=f"heist_join|{chat.id}")
    ]])
    
    msg = await update.message.reply_text(
        f"⚡ <b>{stylize_text('BANK HEIST')}</b>\n\n"
        f"🏛️ {get_mention(user)} is planning a heist!\n"
        f"👥 <b>1/{HEIST_MAX_PLAYERS}</b> | 🎯 Success: <b>42%</b>\n"
        f"💰 Pot: <code>{format_money(HEIST_BASE_REWARD)}</code>\n\n"
        f"⏳ <b>{HEIST_JOIN_TIME}s</b> to join! Type /heist or click below.",
        parse_mode=ParseMode.HTML, reply_markup=kb
    )
    
    # Auto-execute after timer
    async def execute_heist():
        await asyncio.sleep(HEIST_JOIN_TIME)
        h = active_heists.get(chat.id)
        if not h:
            return

        try:
            players = h['players']
            count = len(players)

            if count < HEIST_MIN_PLAYERS:
                await _safe_send(context.bot, chat.id, f"❌ <b>Heist cancelled!</b> Need {HEIST_MIN_PLAYERS}+ players.")
                return

            # Calculate success
            success_chance = min(30 + (count * 12), 90)
            total_reward = HEIST_BASE_REWARD * count

            if random.randint(1, 100) <= success_chance:
                # SUCCESS
                share = min(HEIST_MAX_SHARE, total_reward // count)
                capped_players = 0
                for pid in players:
                    earned_today = positive_credit_total_today(pid, categories=FARM_LIMIT_CATEGORIES)
                    payout = capped_daily_payout(share, earned_today, FARM_GAME_DAILY_CAP)
                    if payout < share:
                        capped_players += 1
                    if payout > 0:
                        adjust_user_balance(
                            pid,
                            payout,
                            "heist_success",
                            "Completed bank heist",
                            chat_id=chat.id,
                            source="/heist",
                            extra_inc={"heists_completed": 1, "game_wins": 1},
                            meta={"players": count, "raw_share": share},
                        )
                    else:
                        adjust_user_balance(
                            pid,
                            0,
                            "heist_success",
                            "Completed bank heist with capped payout",
                            chat_id=chat.id,
                            source="/heist",
                            extra_inc={"heists_completed": 1, "game_wins": 1},
                            meta={"players": count, "raw_share": share, "daily_cap_reached": True},
                        )
                    await add_xp(pid, XP_PER_GAME_WIN)

                cap_note = "" if capped_players == 0 else f"\n⚠️ Daily cap adjusted payout for <b>{capped_players}</b> player(s)."
                result = (
                    f"⚡ <b>{stylize_text('HEIST SUCCESS')}!</b> 🎉\n\n"
                    f"🏛️ The crew robbed the bank!\n"
                    f"💰 Max crew payout: <code>{format_money(share * count)}</code>\n"
                    f"👥 Each gets up to: <code>{format_money(share)}</code>{cap_note}"
                )
            else:
                # FAIL — lose some coins
                penalty = 500
                for pid in players:
                    adjust_user_balance(
                        pid,
                        -penalty,
                        "heist_fail",
                        "Failed bank heist",
                        chat_id=chat.id,
                        source="/heist",
                        require_gte=penalty,
                    )

                result = (
                    f"🚨 <b>{stylize_text('HEIST FAILED')}!</b>\n\n"
                    f"👮 Police caught everyone!\n"
                    f"💸 Each lost: <code>{format_money(penalty)}</code>"
                )

            await _safe_send(context.bot, chat.id, result)
        finally:
            active_heists.pop(chat.id, None)
    
    asyncio.create_task(execute_heist())

async def heist_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data.split("|")
    chat_id = int(data[1])
    uid = query.from_user.id
    
    _clear_stale_heist(chat_id)
    if chat_id not in active_heists:
        return await query.answer("❌ Heist ended!", show_alert=True)
    
    h = active_heists[chat_id]
    if uid in h['players']:
        return await query.answer("⚠️ Already joined!", show_alert=True)
    if len(h['players']) >= HEIST_MAX_PLAYERS:
        return await query.answer("⚠️ Heist full!", show_alert=True)
    
    ensure_user_exists(query.from_user)
    h['players'].append(uid)
    count = len(h['players'])
    success_pct = min(30 + (count * 12), 90)
    
    await query.answer(f"✅ Joined! {count} players now.", show_alert=True)
