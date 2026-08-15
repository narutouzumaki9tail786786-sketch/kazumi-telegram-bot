import asyncio
from datetime import datetime, timedelta

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from kazumi.database import missions_collection, users_collection
from kazumi.ledger import adjust_user_balance
from kazumi.utils import ensure_user_exists, format_money, stylize_text


MISSION_DEFS = [
    {
        "id": "daily_claim",
        "title": "Claim daily reward",
        "desc": "Use /daily or claim from the Mini App.",
        "target": 1,
        "reward": 1200,
        "xp": 20,
    },
    {
        "id": "play_game",
        "title": "Play one game",
        "desc": "Play TTT, Tap Race, High-Low, RPS, blackjack, or any group game.",
        "target": 1,
        "reward": 1500,
        "xp": 25,
    },
    {
        "id": "group_challenge",
        "title": "Start a group challenge",
        "desc": "Start /ttt, /taprace, gang war, or another group challenge.",
        "target": 1,
        "reward": 1500,
        "xp": 25,
    },
    {
        "id": "taprace",
        "title": "Join a Tap Race",
        "desc": "Start or play /taprace in a group.",
        "target": 1,
        "reward": 1000,
        "xp": 15,
    },
    {
        "id": "loan_action",
        "title": "Use the loan system",
        "desc": "Ask, give, or repay a loan.",
        "target": 1,
        "reward": 1300,
        "xp": 20,
    },
    {
        "id": "chat_xp",
        "title": "Keep chat active",
        "desc": "Send 10 group messages.",
        "target": 10,
        "reward": 2000,
        "xp": 35,
    },
]

MISSION_MAP = {mission["id"]: mission for mission in MISSION_DEFS}
FULL_CLEAR_REWARD = 7500
FULL_CLEAR_XP = 120


def today_key():
    return datetime.utcnow().strftime("%Y-%m-%d")


def _blank_progress():
    return {mission["id"]: {"count": 0, "completed": False} for mission in MISSION_DEFS}


def get_mission_doc(user_id):
    key = today_key()
    doc = missions_collection.find_one({"user_id": user_id, "date": key})
    if doc:
        progress = doc.get("progress", {})
        missing = {mid: data for mid, data in _blank_progress().items() if mid not in progress}
        if missing:
            progress.update(missing)
            missions_collection.update_one({"_id": doc["_id"]}, {"$set": {"progress": progress}})
            doc["progress"] = progress
        return doc

    missions_collection.update_one(
        {"user_id": user_id, "date": key},
        {
            "$setOnInsert": {
                "user_id": user_id,
                "date": key,
                "progress": _blank_progress(),
                "reward_claimed": False,
                "created_at": datetime.utcnow(),
            }
        },
        upsert=True,
    )
    return missions_collection.find_one({"user_id": user_id, "date": key})


def track_mission(user_id, mission_id, amount=1):
    if not user_id or mission_id not in MISSION_MAP:
        return None
    doc = get_mission_doc(int(user_id))
    progress = doc.get("progress", {})
    entry = progress.get(mission_id, {"count": 0, "completed": False})
    if entry.get("completed"):
        return doc

    target = int(MISSION_MAP[mission_id]["target"])
    entry["count"] = min(target, int(entry.get("count", 0)) + int(amount))
    entry["completed"] = entry["count"] >= target
    progress[mission_id] = entry
    missions_collection.update_one(
        {"_id": doc["_id"]},
        {"$set": {f"progress.{mission_id}": entry, "updated_at": datetime.utcnow()}},
    )
    doc["progress"] = progress
    return doc


def track_many(user_id, mission_ids):
    doc = None
    for mission_id in mission_ids:
        doc = track_mission(user_id, mission_id)
    return doc


async def async_track_mission(user_id, mission_id, amount=1):
    """Non-blocking version of track_mission — runs DB calls in a thread."""
    return await asyncio.to_thread(track_mission, user_id, mission_id, amount)


def mission_payload(user_id):
    doc = get_mission_doc(int(user_id))
    progress = doc.get("progress", {})
    today = []
    completed = 0
    for mission in MISSION_DEFS:
        entry = progress.get(mission["id"], {"count": 0, "completed": False})
        is_done = bool(entry.get("completed"))
        completed += 1 if is_done else 0
        today.append({
            "id": mission["id"],
            "title": mission["title"],
            "desc": mission["desc"],
            "target": mission["target"],
            "count": min(int(entry.get("count", 0)), int(mission["target"])),
            "completed": is_done,
            "reward": mission["reward"],
            "xp": mission["xp"],
        })
    return {
        "date": doc["date"],
        "today": today,
        "completed": completed,
        "total": len(MISSION_DEFS),
        "rewardReady": completed == len(MISSION_DEFS) and not doc.get("reward_claimed", False),
        "rewardClaimed": bool(doc.get("reward_claimed", False)),
        "fullReward": FULL_CLEAR_REWARD,
        "fullXp": FULL_CLEAR_XP,
    }


def claim_mission_reward(user_id):
    user_id = int(user_id)
    payload = mission_payload(user_id)
    if not payload["rewardReady"]:
        return False, payload, 0, 0

    claim_lock = missions_collection.update_one(
        {"user_id": user_id, "date": today_key(), "reward_claimed": False},
        {"$set": {"reward_claimed": True, "claimed_at": datetime.utcnow()}},
    )
    if claim_lock.modified_count == 0:
        return False, mission_payload(user_id), 0, 0

    user = users_collection.find_one({"user_id": user_id}) or {}
    last_claim = user.get("last_mission_claim")
    streak = int(user.get("mission_streak", 0))
    if last_claim and isinstance(last_claim, datetime) and datetime.utcnow() - last_claim <= timedelta(hours=48):
        streak += 1
    else:
        streak = 1

    bonus = min(streak * 250, 5000)
    coins = FULL_CLEAR_REWARD + bonus
    xp = FULL_CLEAR_XP
    adjust_user_balance(
        user_id,
        coins,
        "missions",
        f"Claimed daily plan reward streak {streak}",
        source="/missions claim",
        extra_inc={"xp": xp},
        extra_set={"last_mission_claim": datetime.utcnow(), "mission_streak": streak},
        meta={"streak": streak, "xp": xp},
    )
    return True, mission_payload(user_id), coins, xp


async def missions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = ensure_user_exists(update.effective_user)
    if context.args and context.args[0].lower() in ("claim", "reward"):
        ok, payload, coins, xp = claim_mission_reward(user["user_id"])
        if not ok:
            return await update.message.reply_text(
                "\U000023F3 <b>Finish all missions first.</b>\n"
                f"Progress: <code>{payload['completed']}/{payload['total']}</code>",
                parse_mode=ParseMode.HTML,
            )
        return await update.message.reply_text(
            f"\U00002705 <b>{stylize_text('Daily Plan Complete')}</b>\n"
            f"Reward: <code>{format_money(coins)}</code> + <code>{xp} XP</code>",
            parse_mode=ParseMode.HTML,
        )

    payload = mission_payload(user["user_id"])
    lines = [
        f"\U0001F4CB <b>{stylize_text('Today Plan')}</b>",
        f"Progress: <code>{payload['completed']}/{payload['total']}</code>",
        "",
    ]
    for mission in payload["today"]:
        mark = "\U00002705" if mission["completed"] else "\U000023F3"
        lines.append(f"{mark} <b>{mission['title']}</b> <code>{mission['count']}/{mission['target']}</code>")
    lines.append("")
    if payload["rewardReady"]:
        lines.append("Reward ready: <code>/missions claim</code>")
    elif payload["rewardClaimed"]:
        lines.append("\U0001F3C6 Reward claimed for today.")
    else:
        lines.append("Finish all tasks to unlock the full reward.")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
