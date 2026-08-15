import asyncio
import random
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from kazumi.ledger import adjust_user_balance
from kazumi.utils import apply_custom_emojis, format_money, stylize_text

GROUP_MESSAGE_COUNTS = {}
ACTIVE_AIRDROPS = {}
AIRDROP_INTERVAL = 65  # Spawn every ~65 messages in group


async def check_airdrop_spawns(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not chat or chat.type == "private":
        return

    count = GROUP_MESSAGE_COUNTS.get(chat.id, 0) + 1
    GROUP_MESSAGE_COUNTS[chat.id] = count

    if count >= AIRDROP_INTERVAL:
        GROUP_MESSAGE_COUNTS[chat.id] = 0

        # Don't spawn double airdrops
        if chat.id in ACTIVE_AIRDROPS:
            return

        reward = random.randint(2000, 10000)
        airdrop_id = f"ad_{chat.id}_{reward}"
        ACTIVE_AIRDROPS[chat.id] = {"reward": reward, "claimed": False, "airdrop_id": airdrop_id}

        text = (
            f"📦 <b>{stylize_text('SPECIAL AIRDROP SPOTTED!')}</b>\n\n"
            "A rare supply crate dropped in this group chat!\n"
            f"💰 <b>Reward:</b> <code>{format_money(reward)}</code> coins!\n\n"
            "<i>First active member to click Claim wins the loot!</i>"
        )

        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎁 CLAIM AIRDROP", callback_data=f"claim_ad|{airdrop_id}")]
        ])

        await update.effective_message.reply_text(apply_custom_emojis(text), parse_mode=ParseMode.HTML, reply_markup=markup)


async def airdrop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()

    data = (query.data or "").split("|")
    if len(data) != 2 or data[0] != "claim_ad":
        return

    airdrop_id = data[1]
    chat_id = query.message.chat_id
    airdrop = ACTIVE_AIRDROPS.get(chat_id)

    if not airdrop or airdrop["airdrop_id"] != airdrop_id or airdrop["claimed"]:
        return await query.answer("❌ This AirDrop has already been claimed or expired!", show_alert=True)

    airdrop["claimed"] = True
    reward = airdrop["reward"]
    user = query.from_user

    ACTIVE_AIRDROPS.pop(chat_id, None)

    await asyncio.to_thread(
        adjust_user_balance,
        user.id,
        reward,
        category="airdrop_claim",
        reason="Claimed group AirDrop crate",
        chat_id=chat_id,
    )

    claimed_text = (
        f"🎉 <b>{stylize_text('AIRDROP CLAIMED!')}</b>\n\n"
        f"👤 {user.mention_html()} opened the supply crate and scored <code>{format_money(reward)}</code> coins!"
    )
    try:
        await query.message.edit_text(apply_custom_emojis(claimed_text), parse_mode=ParseMode.HTML)
    except Exception:
        pass
