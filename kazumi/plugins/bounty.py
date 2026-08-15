# 🌸 Kazumi — Bounty System

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from kazumi.utils import ensure_user_exists, resolve_target, get_mention, format_money, stylize_text
from kazumi.database import users_collection
from kazumi.config import BOUNTY_MIN_AMOUNT, BOUNTY_MAX_AMOUNT
from kazumi.ledger import adjust_user_balance

# In-memory bounty board (persisted in DB via user docs)
# Bounties stored in a separate collection for simplicity
from kazumi.database import db
bounties_collection = db["bounties"]

async def bounty_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = ensure_user_exists(update.effective_user)
    
    if not context.args:
        # Show bounty board
        bounties = list(bounties_collection.find().sort("amount", -1).limit(10))
        if not bounties:
            return await update.message.reply_text(
                f"🎯 <b>{stylize_text('Bounty Board')}</b>\n\n"
                f"📭 No active bounties!\n\n"
                f"<b>Place one:</b> <code>/bounty 5000 @user</code>",
                parse_mode=ParseMode.HTML
            )
        
        msg = f"🎯 <b>{stylize_text('Bounty Board')}</b>\n━━━━━━━━━━━━━━━━━━\n\n"
        for b in bounties:
            target = users_collection.find_one({"user_id": b['target_id']})
            t_name = get_mention(target) if target else f"ID:{b['target_id']}"
            msg += f"💀 {t_name} — <code>{format_money(b['amount'])}</code>\n"
        
        msg += f"\n<i>Kill a bounty target to claim the reward!</i>\n<code>/claimbounty @user</code>"
        return await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
    
    return await place_bounty(update, context)

async def place_bounty(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = ensure_user_exists(update.effective_user)
    
    if not context.args or len(context.args) < 2:
        return await update.message.reply_text("🎯 <b>Usage:</b> <code>/bounty [amount] [@user/reply]</code>", parse_mode=ParseMode.HTML)
    
    try: amount = int(context.args[0])
    except: return await update.message.reply_text("⚠️ Invalid amount.", parse_mode=ParseMode.HTML)
    
    if amount < BOUNTY_MIN_AMOUNT or amount > BOUNTY_MAX_AMOUNT:
        return await update.message.reply_text(f"⚠️ Bounty: ${BOUNTY_MIN_AMOUNT:,} - ${BOUNTY_MAX_AMOUNT:,}", parse_mode=ParseMode.HTML)
    
    target, err = await resolve_target(update, context, specific_arg=context.args[1])
    if not target: return await update.message.reply_text(err or "⚠️ Tag someone.", parse_mode=ParseMode.HTML)
    
    if target['user_id'] == user['user_id']:
        return await update.message.reply_text("🤦 Can't bounty yourself!", parse_mode=ParseMode.HTML)
    
    charged = adjust_user_balance(
        user['user_id'],
        -amount,
        category="bounty_place",
        reason=f"Placed bounty on {target.get('name', 'user')}",
        chat_id=update.effective_chat.id if update.effective_chat else None,
        target_user_id=target['user_id'],
        source="/bounty",
        require_gte=amount,
    )
    if not charged:
        return await update.message.reply_text("📉 Not enough coins!", parse_mode=ParseMode.HTML)
    
    # Check existing bounty
    existing = bounties_collection.find_one({"target_id": target['user_id']})
    if existing:
        bounties_collection.update_one(
            {"target_id": target['user_id']},
            {"$inc": {"amount": amount}}
        )
    else:
        bounties_collection.insert_one({
            "target_id": target['user_id'],
            "amount": amount,
            "placed_by": user['user_id']
        })
    
    total = (existing['amount'] + amount) if existing else amount
    
    await update.message.reply_text(
        f"🎯 <b>{stylize_text('Bounty Placed')}!</b>\n\n"
        f"💀 Target: {get_mention(target)}\n"
        f"💰 Bounty: <code>{format_money(total)}</code>\n\n"
        f"<i>Anyone who kills them gets the reward!</i>",
        parse_mode=ParseMode.HTML
    )

async def claim_bounty(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = ensure_user_exists(update.effective_user)
    
    target, err = await resolve_target(update, context)
    if not target: return await update.message.reply_text(err or "⚠️ Tag/reply to the killed target.", parse_mode=ParseMode.HTML)
    
    # Check if target is dead
    if target.get('status') != 'dead':
        return await update.message.reply_text("⚠️ Target is still alive! Kill them first.", parse_mode=ParseMode.HTML)
    
    bounty = bounties_collection.find_one({"target_id": target['user_id']})
    if not bounty:
        return await update.message.reply_text("❌ No bounty on this user.", parse_mode=ParseMode.HTML)
    
    # Claim
    amount = bounty['amount']
    adjust_user_balance(
        user['user_id'],
        amount,
        category="bounty_claim",
        reason=f"Claimed bounty for killing {target.get('name', 'user')}",
        chat_id=update.effective_chat.id if update.effective_chat else None,
        target_user_id=target['user_id'],
        source="/claimbounty",
        extra_inc={"bounties_claimed": 1},
    )
    bounties_collection.delete_one({"target_id": target['user_id']})
    
    await update.message.reply_text(
        f"🎯 <b>{stylize_text('Bounty Claimed')}!</b>\n\n"
        f"👤 Hunter: {get_mention(user)}\n"
        f"💀 Target: {get_mention(target)}\n"
        f"💰 Reward: <code>{format_money(amount)}</code>",
        parse_mode=ParseMode.HTML
    )
