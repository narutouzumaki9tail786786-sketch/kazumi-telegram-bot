# 🌸 Kazumi — Profile Card System

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from kazumi.utils import ensure_user_exists, get_mention, format_money, stylize_text
from kazumi.database import users_collection
from kazumi.config import ACHIEVEMENTS, LEVEL_UP_BASE, LEVEL_UP_MULTIPLIER
from kazumi.config import OWNER_ID
from kazumi.plugins.achievements import sync_user_achievements
from kazumi.game_rules import leaderboard_filter

def get_level(xp):
    level = 0
    needed = LEVEL_UP_BASE
    while xp >= needed:
        xp -= needed
        level += 1
        needed = int(LEVEL_UP_BASE * (LEVEL_UP_MULTIPLIER ** level))
    return level, xp, needed

def get_xp_bar(current, needed):
    pct = min(current / needed, 1.0) if needed > 0 else 0
    filled = int(pct * 15)
    return "█" * filled + "░" * (15 - filled)

def get_rank_title(level):
    if level >= 100: return "🏆 𝐆𝐎𝐃"
    if level >= 75: return "💎 𝐋𝐄𝐆𝐄𝐍𝐃"
    if level >= 50: return "🌟 𝐌𝐀𝐒𝐓𝐄𝐑"
    if level >= 30: return "⭐ 𝐕𝐄𝐓𝐄𝐑𝐀𝐍"
    if level >= 15: return "🔥 𝐏𝐑𝐎"
    if level >= 5: return "🌱 𝐑𝐎𝐎𝐊𝐈𝐄"
    return "🥚 𝐍𝐄𝐖𝐁𝐈𝐄"

def check_achievements(user_doc):
    """Check and return list of unlocked achievement IDs."""
    unlocked = user_doc.get("achievements", [])
    newly_unlocked = []
    
    for aid, ach in ACHIEVEMENTS.items():
        if aid in unlocked: continue
        cond = ach["condition"]
        met = False
        
        if "kills >=" in cond:
            val = int(cond.split(">=")[1].strip())
            met = user_doc.get("kills", 0) >= val
        elif "balance >=" in cond:
            val = int(cond.split(">=")[1].strip())
            met = user_doc.get("balance", 0) >= val
        elif "has_partner" in cond:
            met = user_doc.get("partner_id") is not None
        elif "waifus >=" in cond:
            val = int(cond.split(">=")[1].strip())
            met = len(user_doc.get("waifus", [])) >= val
        elif "inventory >=" in cond:
            val = int(cond.split(">=")[1].strip())
            met = len(user_doc.get("inventory", [])) >= val
        elif "daily_streak >=" in cond:
            val = int(cond.split(">=")[1].strip())
            met = user_doc.get("daily_streak", 0) >= val
        elif "game_wins >=" in cond:
            val = int(cond.split(">=")[1].strip())
            met = user_doc.get("game_wins", 0) >= val
        elif "rr_wins >=" in cond:
            val = int(cond.split(">=")[1].strip())
            met = user_doc.get("rr_wins", 0) >= val
        elif "heists >=" in cond:
            val = int(cond.split(">=")[1].strip())
            met = user_doc.get("heists_completed", 0) >= val
        elif "bounties_claimed >=" in cond:
            val = int(cond.split(">=")[1].strip())
            met = user_doc.get("bounties_claimed", 0) >= val
        elif "level >=" in cond:
            val = int(cond.split(">=")[1].strip())
            level, _, _ = get_level(user_doc.get("xp", 0))
            met = level >= val
        
        if met:
            newly_unlocked.append(aid)
    
    return newly_unlocked

async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from kazumi.utils import resolve_target
    
    target, error = await resolve_target(update, context)
    if not target and error == "No target":
        target = ensure_user_exists(update.effective_user)
    elif not target:
        return await update.message.reply_text(error, parse_mode=ParseMode.HTML)

    if target.get("user_id") == update.effective_user.id:
        target, _, _ = sync_user_achievements(target)

    # Stats
    xp = target.get("xp", 0)
    level, curr_xp, needed_xp = get_level(xp)
    rank = users_collection.count_documents(
        {"$and": [leaderboard_filter(), {"balance": {"$gt": target["balance"]}}]}
    ) + 1
    rank_title = get_rank_title(level)
    status = "💖 Alive" if target['status'] == 'alive' else "💀 Dead"
    
    # Partner
    pid = target.get("partner_id")
    partner_text = "🦅 Single"
    if pid:
        p = users_collection.find_one({"user_id": pid})
        partner_text = f"💍 {get_mention(p)}" if p else f"💍 ID:{pid}"
    
    # Gear
    inventory = target.get('inventory', [])
    weapons = [i for i in inventory if i['type'] == 'weapon']
    armors = [i for i in inventory if i['type'] == 'armor']
    best_w = max(weapons, key=lambda x: x['buff'])['name'] if weapons else "None"
    best_a = max(armors, key=lambda x: x['buff'])['name'] if armors else "None"
    
    # Achievements
    achv = target.get("achievements", [])
    badge_text = " ".join([ACHIEVEMENTS[a]["name"].split()[0] for a in achv[:8]]) if achv else "None yet"
    
    # Waifus
    waifu_count = len(target.get("waifus", []))
    
    msg = (
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>{get_mention(target, include_badge=True)}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"🏷️ <b>{rank_title}</b>\n"
        f"📈 <b>Level {level}</b> | XP: {curr_xp}/{needed_xp}\n"
        f"<code>{get_xp_bar(curr_xp, needed_xp)}</code>\n\n"
        f"👛 <b>{format_money(target['balance'])}</b> | 🏆 <b>#{rank}</b>\n"
        f"❤️ <b>{status}</b> | ⚔️ <b>{target.get('kills', 0)} Kills</b>\n"
        f"🎮 <b>{target.get('game_wins', 0)} Wins</b> | 🔥 <b>{target.get('daily_streak', 0)}d Streak</b>\n\n"
        f"💞 <b>{partner_text}</b>\n"
        f"👧 <b>Waifus:</b> {waifu_count}\n\n"
        f"🎒 <b>{stylize_text('Gear')}:</b>\n"
        f"🗡️ {best_w} | 🛡️ {best_a}\n\n"
        f"🏅 <b>{stylize_text('Badges')}:</b>\n"
        f"{badge_text}\n"
        f"━━━━━━━━━━━━━━━━━━"
    )
    
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
