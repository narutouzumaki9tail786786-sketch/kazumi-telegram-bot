from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from kazumi.database import users_collection
from kazumi.ledger import adjust_user_balance
from kazumi.utils import ensure_user_exists, format_display_text, format_money, stylize_text


async def refer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = ensure_user_exists(update.effective_user)
    bot_username = context.bot.username or "KazumiRpgBot"
    ref_link = f"https://t.me/{bot_username}?start=ref_{user['user_id']}"

    text = (
        f"📣 <b>{stylize_text('Kazumi Group Referral Program')}</b>\n\n"
        "Earn huge rewards by introducing Kazumi Bot to new Telegram groups!\n\n"
        "🎁 <b>Reward Per Active Group:</b>\n"
        "• <code>50,000</code> Gold Coins\n"
        "• <code>1x</code> Free Mythic Gacha Pull\n\n"
        f"🔗 <b>Your Invite Link:</b>\n<code>{ref_link}</code>\n\n"
        "<i>Add Kazumi to any active group with 50+ members to claim your bonus!</i>"
    )
    await update.message.reply_text(format_display_text(text, ParseMode.HTML), parse_mode=ParseMode.HTML, disable_web_page_preview=True)


async def addbonus_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = ensure_user_exists(update.effective_user)
    chat = update.effective_chat

    if chat.type == "private":
        return await update.message.reply_text(
            format_display_text("❌ Run <code>/addbonus</code> inside the group chat where you added Kazumi!", ParseMode.HTML),
            parse_mode=ParseMode.HTML,
        )

    # Check member count
    try:
        count = await context.bot.get_chat_member_count(chat.id)
    except Exception:
        count = 0

    if count < 20:
        return await update.message.reply_text(
            format_display_text("❌ Group must have at least 20 members to claim the referral bonus!", ParseMode.HTML),
            parse_mode=ParseMode.HTML,
        )

    # Reward 50k balance
    res = adjust_user_balance(user["user_id"], 50000, category="referral_bonus", reason="Added Kazumi to group chat", chat_id=chat.id)

    bonus_text = (
        f"🎉 <b>{stylize_text('REFERRAL BONUS CLAIMED!')}</b>\n\n"
        f"👤 {update.effective_user.mention_html()} received:\n"
        "💰 <code>50,000</code> Gold Coins!\n"
        "🌟 <code>1x</code> Free Gacha Pull bonus!\n\n"
        "<i>Thank you for supporting Kazumi Bot growth!</i>"
    )
    await update.message.reply_text(format_display_text(bonus_text, ParseMode.HTML), parse_mode=ParseMode.HTML)
