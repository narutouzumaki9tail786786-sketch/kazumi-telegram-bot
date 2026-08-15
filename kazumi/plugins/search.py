# 🌸 Kazumi — Search Users

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from kazumi.utils import ensure_user_exists, get_mention, format_money, stylize_text
from kazumi.database import users_collection
from kazumi.plugins.profile import get_level, get_rank_title

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text(
            f"🔍 <b>{stylize_text('Search')}</b>\n\n"
            f"<b>Usage:</b>\n"
            f"<code>/search @username</code>\n"
            f"<code>/search 123456789</code>\n"
            f"<code>/search top</code> — Top 5 players",
            parse_mode=ParseMode.HTML
        )
    
    query = context.args[0]
    user = ensure_user_exists(update.effective_user)
    is_prem = user.get("is_premium", False)
    
    # Top Players (Allowed for everyone)
    if query.lower() == "top":
        results = list(users_collection.find().sort("xp", -1).limit(5))
        if not results:
            return await update.message.reply_text("📭 No users found.", parse_mode=ParseMode.HTML)
        
        msg = f"🔍 <b>{stylize_text('Top Players by XP')}</b>\n━━━━━━━━━━━━━━━━━━\n\n"
        for i, u in enumerate(results, 1):
            level, _, _ = get_level(u.get("xp", 0))
            badges = ["🥇","🥈","🥉","4️⃣","5️⃣"]
            msg += f"{badges[i-1]} {get_mention(u)} — Lv.{level}\n"
        
        return await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
    
    # Premium Check for Specific Search
    if not is_prem:
        return await update.message.reply_text(
            f"❌ <b>{stylize_text('Premium Only')}!</b>\n"
            f"Normal users can only use <code>/search top</code>.\n"
            f"Premium users can search anyone by ID or Username.",
            parse_mode=ParseMode.HTML
        )
    
    # Search by ID
    if query.isdigit():
        doc = users_collection.find_one({"user_id": int(query)})
    else:
        clean = query.replace("@", "").lower()
        doc = users_collection.find_one({"username": clean})
    
    if not doc:
        return await update.message.reply_text(f"❌ User <code>{query}</code> not found.", parse_mode=ParseMode.HTML)
    
    level, _, _ = get_level(doc.get("xp", 0))
    rank_title = get_rank_title(level)
    status = "Alive" if doc.get("status", "alive") == "alive" else "Dead"
    
    msg = (
        f"🔍 <b>{stylize_text('Player Found')}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 {get_mention(doc)}\n"
        f"🏷️ {rank_title} | Lv.{level}\n"
        f"👛 {format_money(doc.get('balance', 0))} | {status}\n"
        f"⚔️ {doc.get('kills', 0)} Kills | 🎮 {doc.get('game_wins', 0)} Wins\n"
        f"🏅 {len(doc.get('achievements', []))} Badges"
    )
    
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
