# 🌸 Kazumi — Achievements System

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from kazumi.utils import ensure_user_exists, get_mention, format_money, stylize_text, get_level_info
from kazumi.database import users_collection
from kazumi.config import ACHIEVEMENTS

def _condition_met(user_doc, condition):
    if "kills >=" in condition:
        value = int(condition.split(">=")[1].strip())
        return int(user_doc.get("kills", 0)) >= value
    if "balance >=" in condition:
        value = int(condition.split(">=")[1].strip())
        return int(user_doc.get("balance", 0)) >= value
    if "has_partner" in condition:
        return user_doc.get("partner_id") is not None
    if "waifus >=" in condition:
        value = int(condition.split(">=")[1].strip())
        return len(user_doc.get("waifus", [])) >= value
    if "inventory >=" in condition:
        value = int(condition.split(">=")[1].strip())
        return len(user_doc.get("inventory", [])) >= value
    if "daily_streak >=" in condition:
        value = int(condition.split(">=")[1].strip())
        return int(user_doc.get("daily_streak", 0)) >= value
    if "game_wins >=" in condition:
        value = int(condition.split(">=")[1].strip())
        return int(user_doc.get("game_wins", 0)) >= value
    if "rr_wins >=" in condition:
        value = int(condition.split(">=")[1].strip())
        return int(user_doc.get("rr_wins", 0)) >= value
    if "heists >=" in condition:
        value = int(condition.split(">=")[1].strip())
        return int(user_doc.get("heists_completed", 0)) >= value
    if "bounties_claimed >=" in condition:
        value = int(condition.split(">=")[1].strip())
        return int(user_doc.get("bounties_claimed", 0)) >= value
    if "level >=" in condition:
        value = int(condition.split(">=")[1].strip())
        level, _, _ = get_level_info(int(user_doc.get("xp", 0)))
        return level >= value
    return False

def get_eligible_achievements(user_doc):
    unlocked = set(user_doc.get("achievements", []))
    newly_unlocked = []

    for achievement_id, achievement in ACHIEVEMENTS.items():
        if achievement_id in unlocked:
            continue
        if _condition_met(user_doc, achievement.get("condition", "")):
            newly_unlocked.append(achievement_id)

    return newly_unlocked

def sync_user_achievements(user_doc):
    eligible = get_eligible_achievements(user_doc)
    if not eligible:
        return user_doc, [], 0

    newly_unlocked = []
    reward_total = 0
    for achievement_id in eligible:
        reward = int(ACHIEVEMENTS[achievement_id].get("reward", 0))
        result = users_collection.update_one(
            {"user_id": user_doc["user_id"], "achievements": {"$ne": achievement_id}},
            {
                "$addToSet": {"achievements": achievement_id},
                "$inc": {"balance": reward},
            },
        )
        if result.modified_count:
            newly_unlocked.append(achievement_id)
            reward_total += reward

    refreshed = users_collection.find_one({"user_id": user_doc["user_id"]}) or user_doc
    return refreshed, newly_unlocked, reward_total

async def achievements_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = ensure_user_exists(update.effective_user)
    user, newly_unlocked, reward_total = sync_user_achievements(user)
    unlocked = user.get("achievements", [])
    
    msg = f"🏅 <b>{stylize_text('Achievements')}</b> — {get_mention(user)}\n"
    msg += f"━━━━━━━━━━━━━━━━━━\n\n"
    msg += f"🔓 <b>Unlocked:</b> {len(unlocked)}/{len(ACHIEVEMENTS)}\n\n"
    if newly_unlocked:
        msg += (
            f"✨ <b>{stylize_text('Synced')}:</b> "
            f"+{len(newly_unlocked)} badges | +<code>{format_money(reward_total)}</code>\n\n"
        )
    
    for aid, ach in ACHIEVEMENTS.items():
        if aid in unlocked:
            msg += f"✅ {ach['name']} — <i>{ach['desc']}</i>\n"
        else:
            msg += f"🔒 <s>{ach['name']}</s> — <i>{ach['desc']}</i>\n"
    
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

async def grant_achievement(bot, user_id, achievement_id, chat_id=None):
    """Grants an achievement and notifies the user."""
    if achievement_id not in ACHIEVEMENTS: return False
    
    user = users_collection.find_one({"user_id": user_id})
    if not user: return False
    
    if achievement_id in user.get("achievements", []):
        return False  # Already has it
    
    ach = ACHIEVEMENTS[achievement_id]
    users_collection.update_one(
        {"user_id": user_id},
        {
            "$addToSet": {"achievements": achievement_id},
            "$inc": {"balance": ach["reward"]}
        }
    )
    
    if chat_id:
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    f"🏅 <b>{stylize_text('Achievement Unlocked')}!</b>\n\n"
                    f"👤 <a href='tg://user?id={user_id}'>Player</a>\n"
                    f"🎖️ {ach['name']}\n"
                    f"📝 <i>{ach['desc']}</i>\n"
                    f"💰 +<code>{format_money(ach['reward'])}</code>"
                ),
                parse_mode=ParseMode.HTML
            )
        except: pass
    
    return True
