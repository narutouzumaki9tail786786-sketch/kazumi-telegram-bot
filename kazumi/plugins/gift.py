# 🌸 Kazumi — Gift System

from telegram.constants import ParseMode
from telegram import Update
from telegram.ext import ContextTypes

from kazumi.config import SHOP_ITEMS
from kazumi.database import run_db, users_collection
from kazumi.ledger import adjust_user_balance
from kazumi.plugins.shop import find_shop_item
from kazumi.utils import ensure_user_exists, format_money, get_mention, remove_one_inventory_item, resolve_target, stylize_text

async def gift_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender = await run_db(ensure_user_exists, update.effective_user)
    message = getattr(update, "effective_message", None) or getattr(update, "message", None)
    has_reply_target = bool(getattr(message, "reply_to_message", None))
    
    if not context.args:
        return await update.message.reply_text(
            f"🎁 <b>{stylize_text('Gift System')}</b>\n\n"
            f"<b>Gift an item:</b> <code>/gift knife @user</code> or reply <code>/gift knife</code>\n"
            f"<b>Gift coins:</b> <code>/gift coins 1000 @user</code> or reply <code>/gift coins 1000</code>",
            parse_mode=ParseMode.HTML
        )
    
    item_or_type = context.args[0].lower()
    
    # Gift Coins
    if item_or_type == "coins":
        if len(context.args) < 2:
            return await update.message.reply_text(
                "⚠️ <code>/gift coins 1000 @user</code> or reply <code>/gift coins 1000</code>",
                parse_mode=ParseMode.HTML,
            )
        
        try:
            amount = int(context.args[1])
        except Exception:
            return await update.message.reply_text("⚠️ Invalid amount.", parse_mode=ParseMode.HTML)
        
        target_arg = None if has_reply_target else (context.args[2] if len(context.args) > 2 else None)
        target, err = await resolve_target(update, context, specific_arg=target_arg)
        if not target:
            return await update.message.reply_text(err or "⚠️ Tag someone or reply to them.", parse_mode=ParseMode.HTML)
        
        if sender['user_id'] == target['user_id']:
            return await update.message.reply_text("🤦 Can't gift yourself!", parse_mode=ParseMode.HTML)
        
        paid = adjust_user_balance(
            sender["user_id"],
            -amount,
            "gift",
            f"Gifted to {target.get('name', 'user')}",
            chat_id=update.effective_chat.id if update.effective_chat else None,
            source="/gift coins",
            require_gte=amount,
            meta={"target_id": target["user_id"]},
        )
        if not paid:
            return await update.message.reply_text("❌ You don't have enough coins!", parse_mode=ParseMode.HTML)
        
        adjust_user_balance(
            target["user_id"],
            amount,
            "gift_receive",
            f"Received gift from {sender.get('name', 'user')}",
            chat_id=update.effective_chat.id if update.effective_chat else None,
            source="/gift coins",
            meta={"sender_id": sender["user_id"]},
        )
        
        return await update.message.reply_text(
            f"🎁 <b>{stylize_text('Gift Sent')}!</b>\n\n"
            f"👤 From: {get_mention(sender)}\n"
            f"👤 To: {get_mention(target)}\n"
            f"💰 Amount: <code>{format_money(amount)}</code>",
            parse_mode=ParseMode.HTML
        )
    
    # Gift Item
    if has_reply_target:
        item_query = " ".join(context.args).strip()
        target_arg = None
    else:
        if len(context.args) < 2:
            return await update.message.reply_text(
                f"⚠️ <code>/gift item_name @user</code> or reply <code>/gift item_name</code>",
                parse_mode=ParseMode.HTML,
            )
        target_arg = context.args[-1]
        item_query = " ".join(context.args[:-1]).strip()

    target, err = await resolve_target(update, context, specific_arg=target_arg)
    if not target:
        return await update.message.reply_text(err or "⚠️ Tag someone or reply to them.", parse_mode=ParseMode.HTML)
    
    if sender['user_id'] == target['user_id']:
        return await update.message.reply_text("🤦 Can't gift yourself!", parse_mode=ParseMode.HTML)
    
    sender_inv = [i for i in (sender.get("inventory") or []) if isinstance(i, dict)]
    item_to_gift = find_shop_item(item_query, sender_inv)
    
    if not item_to_gift:
        return await update.message.reply_text(f"❌ You don't own <b>{item_query}</b>!", parse_mode=ParseMode.HTML)
    
    # Transfer only one copy.
    item_to_gift = await run_db(remove_one_inventory_item, sender, item_to_gift["id"])
    if not item_to_gift:
        return await update.message.reply_text(f"❌ You don't own <b>{item_query}</b> anymore.", parse_mode=ParseMode.HTML)
    await run_db(users_collection.update_one, {"user_id": target["user_id"]}, {"$push": {"inventory": item_to_gift}})
    
    await update.message.reply_text(
        f"🎁 <b>{stylize_text('Gift Delivered')}!</b>\n\n"
        f"👤 From: {get_mention(sender)}\n"
        f"👤 To: {get_mention(target)}\n"
        f"🎒 Item: <b>{item_to_gift['name']}</b>\n\n"
        f"✨ <i>What a nice person!</i>",
        parse_mode=ParseMode.HTML
    )
