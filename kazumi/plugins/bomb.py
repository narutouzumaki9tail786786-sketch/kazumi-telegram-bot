import asyncio
import time
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from kazumi.ledger import adjust_user_balance
from kazumi.utils import format_display_text, format_money, get_mention, resolve_target, stylize_text

ACTIVE_BOMBS = {}


async def bomb_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    if chat.type == "private":
        return await update.message.reply_text(
            format_display_text("💣 <b>Hot Bomb Tag can only be played in group chats!</b>", ParseMode.HTML),
            parse_mode=ParseMode.HTML,
        )

    if chat.id in ACTIVE_BOMBS:
        return await update.message.reply_text(
            format_display_text("💣 <b>A Hot Bomb is already ticking in this chat!</b>", ParseMode.HTML),
            parse_mode=ParseMode.HTML,
        )

    target_doc, _ = await resolve_target(update, context)

    target_id = target_doc.get("user_id") if isinstance(target_doc, dict) else None
    holder_id = target_id if target_id and target_id != user.id else user.id
    holder_mention = get_mention(target_doc) if target_id and target_id != user.id else get_mention(user)

    bomb_state = {
        "chat_id": chat.id,
        "holder_id": holder_id,
        "holder_mention": holder_mention,
        "expires_at": time.time() + 25,
        "active": True,
    }
    ACTIVE_BOMBS[chat.id] = bomb_state

    text = (
        f"💣 <b>{stylize_text('HOT BOMB ACTIVATED!')}</b>\n\n"
        f"🔥 The ticking bomb is currently held by {bomb_state['holder_mention']}!\n"
        "⏱️ <b>Time remaining:</b> <code>25 seconds</code>!\n\n"
        "👉 <b>QUICK!</b> Pass it to someone else by typing:\n"
        "<code>/pass @username</code> (or reply with <code>/pass</code>)"
    )
    sent_msg = await update.message.reply_text(format_display_text(text, ParseMode.HTML), parse_mode=ParseMode.HTML)

    # Spawn bomb timer task
    asyncio.create_task(run_bomb_timer(context, chat.id, sent_msg))


async def pass_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    bomb = ACTIVE_BOMBS.get(chat.id)
    if not bomb or not bomb["active"]:
        return

    if user.id != bomb["holder_id"]:
        return await update.message.reply_text(
            format_display_text("❌ <b>You don't have the bomb!</b> Run /bomb to start one.", ParseMode.HTML),
            parse_mode=ParseMode.HTML,
        )

    target_doc, _ = await resolve_target(update, context)
    target_id = target_doc.get("user_id") if isinstance(target_doc, dict) else None

    if not target_doc or not target_id or target_id == user.id:
        return await update.message.reply_text(
            format_display_text("❌ Reply to someone or tag `@username` to pass the bomb!", ParseMode.HTML),
            parse_mode=ParseMode.HTML,
        )

    bomb["holder_id"] = target_id
    bomb["holder_mention"] = get_mention(target_doc)

    pass_text = f"💣 💥 <b>BOMB PASSED!</b>\n{get_mention(user)} passed the bomb to {get_mention(target_doc)}!\nRun <code>/pass @username</code> quickly!"
    await update.message.reply_text(format_display_text(pass_text, ParseMode.HTML), parse_mode=ParseMode.HTML)


async def run_bomb_timer(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message):
    await asyncio.sleep(25)

    bomb = ACTIVE_BOMBS.pop(chat_id, None)
    if not bomb or not bomb["active"]:
        return

    victim_id = bomb["holder_id"]
    victim_mention = bomb["holder_mention"]

    # Penalty for holding bomb: lose 5,000 coins
    adjust_user_balance(victim_id, -5000, category="bomb_penalty", reason="Exploded in Hot Bomb Tag", chat_id=chat_id)

    boom_text = (
        f"💥 💥 <b>{stylize_text('BOOOOOOM!')}</b>\n\n"
        f"💣 The bomb exploded on {victim_mention}!\n"
        f"💸 <b>Penalty:</b> Lost <code>{format_money(5000)}</code> coins!"
    )
    try:
        await message.reply_text(format_display_text(boom_text, ParseMode.HTML), parse_mode=ParseMode.HTML)
    except Exception:
        pass
