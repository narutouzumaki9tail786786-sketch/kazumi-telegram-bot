import asyncio
import random
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.constants import ChatType, ParseMode
from telegram.ext import ContextTypes
from kazumi.config import DEFAULT_MAX_BET, WEBAPP_URL
from kazumi.database import users_collection
from kazumi.ledger import adjust_user_balance
from kazumi.utils import ensure_user_exists, format_display_text, format_money, parse_money, stylize_text


async def colorbet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    user_doc = ensure_user_exists(user)

    args = context.args
    if len(args) < 2:
        help_txt = (
            f"🔴🟢 <b>{stylize_text('Color Prediction Game')}</b>\n\n"
            "Bet on Red (2x), Green (2x), or Violet (4.5x)!\n\n"
            "<b>Chat Command:</b> <code>/colorbet [red|green|violet] [amount]</code>\n"
            "<b>Example:</b> <code>/colorbet red 1000</code>\n\n"
            "🌐 <b>Web Mini App Direct Mode:</b> <code>/wcolor [bet]</code> (Interactive Color Wheel!)"
        )
        return await update.message.reply_text(
            format_display_text(help_txt, ParseMode.HTML),
            parse_mode=ParseMode.HTML,
        )

    choice = args[0].lower()
    if choice not in {"red", "green", "violet"}:
        return await update.message.reply_text(
            format_display_text("❌ Choose a valid color: <code>red</code>, <code>green</code>, or <code>violet</code>.", ParseMode.HTML),
            parse_mode=ParseMode.HTML,
        )

    parsed = parse_money(args[1])
    if parsed == "all":
        amount = min(user_doc.get("balance", 0), DEFAULT_MAX_BET)
    elif isinstance(parsed, int):
        amount = parsed
    else:
        return await update.message.reply_text(
            format_display_text(
                f"❌ <b>{stylize_text('Invalid Bet Amount')}!</b>\nPlease enter a valid number (Example: <code>/colorbet red 1000</code>).",
                ParseMode.HTML
            ),
            parse_mode=ParseMode.HTML
        )

    if amount < 100:
        return await update.message.reply_text(
            format_display_text(
                f"⚠️ <b>{stylize_text('Minimum Bet Limit')}!</b>\nMinimum bet is <code>$100</code> coins.",
                ParseMode.HTML
            ),
            parse_mode=ParseMode.HTML
        )

    if amount > DEFAULT_MAX_BET:
        return await update.message.reply_text(
            format_display_text(
                f"⚠️ <b>{stylize_text('Maximum Wager Limit')}!</b>\n━━━━━━━━━━━━━━━━━━━\nMaximum allowed bet for Colorbet is <code>{format_money(DEFAULT_MAX_BET)}</code> coins.",
                ParseMode.HTML
            ),
            parse_mode=ParseMode.HTML
        )

    user_doc = users_collection.find_one({"user_id": user.id})
    if (user_doc.get("balance", 0)) < amount:
        return await update.message.reply_text(
            format_display_text(f"❌ Insufficient balance! Balance: <code>{format_money(user_doc.get('balance', 0))}</code>", ParseMode.HTML),
            parse_mode=ParseMode.HTML,
        )

    # Debit bet
    res = adjust_user_balance(user.id, -amount, category="colorbet_bet", reason=f"Colorbet bet on {choice}", chat_id=chat.id, require_gte=amount)
    if not res:
        return await update.message.reply_text("❌ Bet processing failed.")

    color_emoji = "🔴" if choice == "red" else ("🟢" if choice == "green" else "🟣")
    spin_text = f"🎰 <b>Spinning the Color Wheel for {user.mention_html()}...</b>\nChoice: {color_emoji} <b>{choice.upper()}</b> | Bet: <code>{format_money(amount)}</code>"
    sent_msg = await update.message.reply_text(format_display_text(spin_text, ParseMode.HTML), parse_mode=ParseMode.HTML)

    await asyncio.sleep(2.0)

    # Determine winning color (Red 45%, Green 45%, Violet 10%)
    roll = random.random()
    if roll < 0.45:
        winning_color = "red"
        winning_emoji = "🔴"
        multiplier = 2.0
    elif roll < 0.90:
        winning_color = "green"
        winning_emoji = "🟢"
        multiplier = 2.0
    else:
        winning_color = "violet"
        winning_emoji = "🟣"
        multiplier = 4.5

    if choice == winning_color:
        win_amount = int(amount * multiplier)
        profit = win_amount - amount
        adjust_user_balance(user.id, win_amount, category="colorbet_win", reason=f"Colorbet win on {choice}", chat_id=chat.id)

        result_text = (
            f"🎉 <b>{stylize_text('COLOR WIN!')}</b>\n\n"
            f"🎯 <b>Result:</b> {winning_emoji} <b>{winning_color.upper()}</b>\n"
            f"👤 <b>Player:</b> {user.mention_html()}\n"
            f"💰 <b>Payout:</b> <code>{format_money(win_amount)}</code> (+<code>{format_money(profit)}</code> profit)!"
        )
    else:
        result_text = (
            f"💥 <b>{stylize_text('COLOR LOSS!')}</b>\n\n"
            f"🎯 <b>Result:</b> {winning_emoji} <b>{winning_color.upper()}</b>\n"
            f"👤 <b>Player:</b> {user.mention_html()}\n"
            f"💸 <b>Loss:</b> <code>{format_money(amount)}</code>."
        )

    try:
        await sent_msg.edit_text(format_display_text(result_text, ParseMode.HTML), parse_mode=ParseMode.HTML)
    except Exception:
        pass
