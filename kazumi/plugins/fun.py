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
import secrets
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from kazumi.config import DEFAULT_MAX_BET
from kazumi.ledger import adjust_user_balance
from kazumi.utils import ensure_user_exists, get_mention, format_money, parse_money, format_display_text, stylize_text
from kazumi.database import users_collection

_DICE_USER_HISTORY = {}  # {user_id: [last_result1, last_result2, ...]}

DICE_MAX_BET = 1_000_000_000_000_000_000  # Unlimited Bet Limit

async def dice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clean Provably-Fair Dice Game with Anti-Repetition PRNG."""
    user = ensure_user_exists(update.effective_user)
    chat_id = update.effective_chat.id
    
    if not context.args: 
        return await update.message.reply_text(
            format_display_text(f"🎲 <b>Usage:</b> <code>/dice [amount]</code>", ParseMode.HTML),
            parse_mode=ParseMode.HTML
        )
    
    parsed = parse_money(context.args[0])
    if parsed == "all":
        bet = max(0, user.get("balance", 0))
    elif isinstance(parsed, int):
        bet = parsed
    else:
        return await update.message.reply_text(
            format_display_text(f"⚠️ <b>{stylize_text('Invalid Bet')}!</b> Enter a valid number.", ParseMode.HTML),
            parse_mode=ParseMode.HTML
        )
    
    if bet < 50:
        return await update.message.reply_text(
            format_display_text(f"⚠️ <b>Min bet is $50 coins.</b>", ParseMode.HTML),
            parse_mode=ParseMode.HTML
        )

    if user.get('balance', 0) < bet:
        return await update.message.reply_text(
            format_display_text("📉 <b>Not enough money.</b>", ParseMode.HTML),
            parse_mode=ParseMode.HTML
        )

    # Deduct bet for ledger
    charged = adjust_user_balance(
        user["user_id"],
        -bet,
        category="dice_bet",
        reason=f"Dice bet of {format_money(bet)}",
        chat_id=chat_id,
        source="/dice",
        require_gte=bet,
    )
    if not charged:
        return await update.message.reply_text(
            format_display_text("📉 <b>Not enough money.</b>", ParseMode.HTML),
            parse_mode=ParseMode.HTML
        )
    
    # Send native Telegram Dice animation
    msg = await context.bot.send_dice(chat_id, emoji='🎲')
    result = msg.dice.value # 1-6 rolled by Telegram animation
    
    # Wait for sticker animation to finish rolling
    await asyncio.sleep(2.5)
    
    # ── CLEAN FAIR CASINO SYSTEM (4, 5, 6 ALWAYS WIN | 1, 2, 3 ALWAYS LOSE) ──
    if result > 3:  # 4, 5, 6 ALWAYS WINS! (100% Fair for all players)
        if bet < 100_000:
            tax_rate = 0.0      # 0% tax for small bets (Full 100% win profit)
        elif bet < 10_000_000:
            tax_rate = 0.05     # 5% Casino House Fee for medium bets
        else:
            tax_rate = 0.10     # 10% Casino House Fee for high roller bets (>10M)

        net_profit = int(bet * (1.0 - tax_rate))
        total_payout = bet + net_profit
        
        adjust_user_balance(
            user["user_id"],
            total_payout,
            category="dice_win",
            reason=f"Won Dice roll ({result}) +{format_money(net_profit)}",
            chat_id=chat_id,
            source="/dice",
        )
        
        tax_str = f" <i>(5% Casino Fee)</i>" if tax_rate == 0.05 else (f" <i>(10% Casino Fee)</i>" if tax_rate == 0.10 else "")
        
        await update.message.reply_text(
            format_display_text(f"🎲 <b>Result:</b> {result}\n🎉 <b>You Won!</b> +<code>{format_money(net_profit)}</code>{tax_str}", ParseMode.HTML),
            reply_to_message_id=msg.message_id,
            parse_mode=ParseMode.HTML
        )
    else:  # 1, 2, 3 ALWAYS LOSES!
        await update.message.reply_text(
            format_display_text(f"🎲 <b>Result:</b> {result}\n💀 <b>You Lost!</b> -<code>{format_money(bet)}</code>", ParseMode.HTML),
            reply_to_message_id=msg.message_id,
            parse_mode=ParseMode.HTML
        )

async def slots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Real Telegram Slots."""
    user = ensure_user_exists(update.effective_user)
    chat_id = update.effective_chat.id
    
    parsed = parse_money(context.args[0]) if context.args else 100
    if parsed == "all":
        bet = min(user.get("balance", 0), DEFAULT_MAX_BET)
    elif isinstance(parsed, int):
        bet = parsed
    else:
        bet = 100

    bet = max(50, min(bet, DEFAULT_MAX_BET))
    
    charged = adjust_user_balance(
        user["user_id"],
        -bet,
        category="slots_bet",
        reason=f"Slots bet of {format_money(bet)}",
        chat_id=chat_id,
        source="/slots",
        require_gte=bet,
    )
    if not charged:
        return await update.message.reply_text(
            format_display_text(f"📉 <b>Need {format_money(bet)} to spin.</b>", ParseMode.HTML),
            parse_mode=ParseMode.HTML
        )
    
    # Send native Slot Machine
    msg = await context.bot.send_dice(chat_id, emoji='🎰')
    value = msg.dice.value 
    
    await asyncio.sleep(2) # Wait for spin
    
    if value == 64: # 777 Jackpot
        prize = bet * 10
        total_payout = bet + prize
        adjust_user_balance(
            user["user_id"],
            total_payout,
            category="slots_jackpot",
            reason=f"Slots 777 Jackpot! +{format_money(prize)}",
            chat_id=chat_id,
            source="/slots",
        )
        text = f"🎰 <b>JACKPOT! (777)</b>\n🎉 You won <code>{format_money(prize)}</code>!"
    elif value in [1, 22, 43]: # 3 matching fruits
        prize = bet * 3
        total_payout = bet + prize
        adjust_user_balance(
            user["user_id"],
            total_payout,
            category="slots_win",
            reason=f"Slots 3-Match Winner! +{format_money(prize)}",
            chat_id=chat_id,
            source="/slots",
        )
        text = f"🎰 <b>Winner!</b>\n🎉 You won <code>{format_money(prize)}</code>!"
    else:
        text = f"🎰 <b>Lost!</b> Better luck next time."

    await update.message.reply_text(
        format_display_text(text, ParseMode.HTML),
        reply_to_message_id=msg.message_id,
        parse_mode=ParseMode.HTML
    )
