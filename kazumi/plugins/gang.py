import html
import random
import re
import uuid
from datetime import datetime, timedelta

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from kazumi.database import db, users_collection
from kazumi.missions import track_many
from kazumi.utils import ensure_user_exists, format_money, stylize_text


gangs_col = db["gangs"]
gang_wars_col = db["gang_wars"]

CREATE_COST = 5000
WAR_COOLDOWN = timedelta(hours=2)
PENDING_TTL = timedelta(minutes=30)
WITHDRAW_DAILY_LIMIT = 999_999_999_999_999
WITHDRAW_FEE_RATE = 0.10


def parse_money(value):
    cleaned = re.sub(r"[$,\s_]", "", str(value or "").strip())
    return int(cleaned) if cleaned.isdigit() else None


def clean_name(parts):
    return " ".join(parts).strip()[:24]


def find_gang_by_name(name):
    if not name:
        return None
    return gangs_col.find_one({"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}})


def user_gang(user_id):
    return gangs_col.find_one({"members": int(user_id)})


def is_leader(gang, user_id):
    return gang and int(gang.get("leader_id", 0)) == int(user_id)


def ensure_gang_shape(gang):
    if not gang:
        return None
    updates = {}
    defaults = {
        "wins": 0,
        "losses": 0,
        "rating": 1000,
        "bank": 0,
        "members": [],
    }
    for key, value in defaults.items():
        if key not in gang:
            updates[key] = value
            gang[key] = value
    if updates:
        gangs_col.update_one({"_id": gang["_id"]}, {"$set": updates})
    return gang


def cooldown_left(gang):
    until = gang.get("war_cooldown_until")
    if not until or until <= datetime.utcnow():
        return None
    return until - datetime.utcnow()


def active_war(gang_id):
    return gang_wars_col.find_one({
        "status": "pending",
        "$or": [{"challenger_id": gang_id}, {"target_id": gang_id}],
        "expires_at": {"$gt": datetime.utcnow()},
    })


def format_gang(gang):
    return html.escape(gang.get("name", "Gang"))


def gang_power(gang):
    gang = ensure_gang_shape(gang)
    members = list(gang.get("members", []))
    docs = list(users_collection.find({"user_id": {"$in": members}})) if members else []
    activity = 0
    for doc in docs:
        activity += min(int(doc.get("xp", 0)) // 90, 500)
        activity += min(int(doc.get("game_wins", 0)) * 8, 420)
        activity += min(int(doc.get("kills", 0)) * 3, 320)
        activity += min(int(doc.get("daily_streak", 0)) * 6, 240)
    member_power = len(members) * 140
    bank_power = min(int(gang.get("bank", 0)) // 1000, 1200)
    rating_power = max(0, int(gang.get("rating", 1000)) - 900)
    leader_bonus = 180
    luck = random.randint(0, 260)
    return member_power + activity + bank_power + rating_power + leader_bonus + luck


def war_help(my_gang=None):
    if my_gang:
        return (
            f"\U0001F451 <b>{stylize_text(my_gang['name'])}</b>\n"
            f"\U0001F465 Members: <b>{len(my_gang.get('members', []))}</b>\n"
            f"\U0001F3E6 Bank: <code>{format_money(my_gang.get('bank', 0))}</code>\n"
            f"\U00002694 Rating: <b>{my_gang.get('rating', 1000)}</b> | "
            f"W/L: <b>{my_gang.get('wins', 0)}/{my_gang.get('losses', 0)}</b>\n\n"
            "<b>Commands</b>\n"
            "<code>/gang status</code>\n"
            "<code>/gang deposit 5000</code>\n"
            "<code>/gang withdraw 5000</code> - leader only\n"
            "<code>/gang war Enemy 5000</code>\n"
            "<code>/gang accept</code> | <code>/gang decline</code>\n"
            "<code>/gang top</code> | <code>/gang leave</code>"
        )
    return (
        f"\U0001F451 <b>{stylize_text('Gang System')}</b>\n\n"
        "<code>/gang create Wolves</code> - costs 5k\n"
        "<code>/gang join Wolves</code>\n"
        "<code>/gang top</code>\n"
        "<code>/gang status</code>"
    )


async def create_gang(update, user, args):
    if len(args) < 2:
        return await update.message.reply_text("\U000026A0\ufe0f <code>/gang create Wolves</code>", parse_mode=ParseMode.HTML)
    uid = user["user_id"]
    name = clean_name(args[1:])
    if user.get("balance", 0) < CREATE_COST:
        return await update.message.reply_text(f"\U0001F4C9 Need <code>{format_money(CREATE_COST)}</code>.", parse_mode=ParseMode.HTML)
    if user_gang(uid):
        return await update.message.reply_text("\U000026A0\ufe0f Leave your current gang first.", parse_mode=ParseMode.HTML)
    if find_gang_by_name(name):
        return await update.message.reply_text("\U000026A0\ufe0f Gang name already taken.", parse_mode=ParseMode.HTML)
    users_collection.update_one({"user_id": uid}, {"$inc": {"balance": -CREATE_COST}})
    gangs_col.insert_one({
        "name": name,
        "leader_id": uid,
        "members": [uid],
        "bank": 0,
        "wins": 0,
        "losses": 0,
        "rating": 1000,
        "created_at": datetime.utcnow(),
    })
    await update.message.reply_text(f"\U0001F451 Gang <b>{html.escape(name)}</b> created.", parse_mode=ParseMode.HTML)


async def join_gang(update, user, args):
    if len(args) < 2:
        return await update.message.reply_text("\U000026A0\ufe0f <code>/gang join Wolves</code>", parse_mode=ParseMode.HTML)
    uid = user["user_id"]
    if user_gang(uid):
        return await update.message.reply_text("\U000026A0\ufe0f Leave your current gang first.", parse_mode=ParseMode.HTML)
    gang = find_gang_by_name(clean_name(args[1:]))
    if not gang:
        return await update.message.reply_text("\U0000274C Gang not found.", parse_mode=ParseMode.HTML)
    gangs_col.update_one({"_id": gang["_id"]}, {"$addToSet": {"members": uid}})
    await update.message.reply_text(f"\U00002705 Joined <b>{format_gang(gang)}</b>.", parse_mode=ParseMode.HTML)


async def leave_gang(update, user):
    uid = user["user_id"]
    gang = user_gang(uid)
    if not gang:
        return await update.message.reply_text("\U0000274C You are not in a gang.", parse_mode=ParseMode.HTML)
    if active_war(gang["_id"]):
        return await update.message.reply_text("\U000026A0\ufe0f Finish or decline the pending war first.", parse_mode=ParseMode.HTML)
    members = list(gang.get("members", []))
    if gang.get("leader_id") == uid and len(members) > 1:
        next_leader = next(member for member in members if member != uid)
        gangs_col.update_one({"_id": gang["_id"]}, {"$pull": {"members": uid}, "$set": {"leader_id": next_leader}})
    elif gang.get("leader_id") == uid:
        gangs_col.delete_one({"_id": gang["_id"]})
    else:
        gangs_col.update_one({"_id": gang["_id"]}, {"$pull": {"members": uid}})
    await update.message.reply_text("\U0001F6AA Left gang.", parse_mode=ParseMode.HTML)


async def deposit(update, user, args):
    if len(args) < 2:
        return await update.message.reply_text("\U000026A0\ufe0f <code>/gang deposit 5000</code>", parse_mode=ParseMode.HTML)
    amount = parse_money(args[1])
    gang = user_gang(user["user_id"])
    if not gang or not amount or amount <= 0 or user.get("balance", 0) < amount:
        return await update.message.reply_text("\U0000274C Deposit failed.", parse_mode=ParseMode.HTML)
    users_collection.update_one({"user_id": user["user_id"]}, {"$inc": {"balance": -amount}})
    gangs_col.update_one({"_id": gang["_id"]}, {"$inc": {"bank": amount}})
    await update.message.reply_text(f"\U0001F4B0 Added <code>{format_money(amount)}</code> to gang bank.", parse_mode=ParseMode.HTML)


def withdraw_used_today(gang):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    if gang.get("withdraw_day") != today:
        return 0, today
    return int(gang.get("withdraw_used", 0)), today


async def withdraw(update, user, args):
    if len(args) < 2:
        return await update.message.reply_text("\U000026A0\ufe0f <code>/gang withdraw 5000</code>", parse_mode=ParseMode.HTML)
    amount = parse_money(args[1])
    gang = ensure_gang_shape(user_gang(user["user_id"]))
    if not gang:
        return await update.message.reply_text("\U0000274C Join a gang first.", parse_mode=ParseMode.HTML)
    if not is_leader(gang, user["user_id"]):
        return await update.message.reply_text("\U0001F512 Only the gang leader can withdraw.", parse_mode=ParseMode.HTML)
    if active_war(gang["_id"]):
        return await update.message.reply_text("\U000026A0\ufe0f Withdraw blocked during pending war.", parse_mode=ParseMode.HTML)
    if not amount or amount <= 0:
        return await update.message.reply_text("\U0000274C Withdraw failed.", parse_mode=ParseMode.HTML)

    bank = int(gang.get("bank", 0))
    used, today = withdraw_used_today(gang)
    if amount > bank:
        return await update.message.reply_text("\U0001F4C9 Gang bank cannot cover that amount.", parse_mode=ParseMode.HTML)
    if used + amount > WITHDRAW_DAILY_LIMIT:
        left = max(0, WITHDRAW_DAILY_LIMIT - used)
        return await update.message.reply_text(
            f"\U000023F3 Daily withdraw limit left: <code>{format_money(left)}</code>.",
            parse_mode=ParseMode.HTML,
        )

    fee = int(amount * WITHDRAW_FEE_RATE)
    payout = amount - fee
    update_doc = {
        "$inc": {"bank": -amount},
        "$set": {"withdraw_day": today, "last_withdraw_at": datetime.utcnow(), "last_withdraw_by": user["user_id"]},
    }
    if gang.get("withdraw_day") == today:
        update_doc["$inc"]["withdraw_used"] = amount
    else:
        update_doc["$set"]["withdraw_used"] = amount

    result = gangs_col.update_one(
        {"_id": gang["_id"], "bank": {"$gte": amount}},
        update_doc,
    )
    if result.modified_count == 0:
        return await update.message.reply_text("\U0000274C Withdraw failed. Try again.", parse_mode=ParseMode.HTML)

    users_collection.update_one({"user_id": user["user_id"]}, {"$inc": {"balance": payout}})
    await update.message.reply_text(
        f"\U0001F3E6 <b>{stylize_text('Gang Withdraw')}</b>\n\n"
        f"Leader: <b>{html.escape(user.get('name') or 'User')}</b>\n"
        f"Gang: <b>{format_gang(gang)}</b>\n"
        f"Withdraw: <code>{format_money(amount)}</code>\n"
        f"Fee: <code>{format_money(fee)}</code>\n"
        f"Received: <code>{format_money(payout)}</code>",
        parse_mode=ParseMode.HTML,
    )


async def declare_war(update, user, args):
    gang = ensure_gang_shape(user_gang(user["user_id"]))
    if not gang:
        return await update.message.reply_text("\U0000274C Join a gang first.", parse_mode=ParseMode.HTML)
    if not is_leader(gang, user["user_id"]):
        return await update.message.reply_text("\U0001F512 Only the gang leader can declare war.", parse_mode=ParseMode.HTML)
    if len(args) < 2:
        return await update.message.reply_text("\U000026A0\ufe0f <code>/gang war Enemy 5000</code>", parse_mode=ParseMode.HTML)
    cooldown = cooldown_left(gang)
    if cooldown:
        mins = max(1, int(cooldown.total_seconds() // 60))
        return await update.message.reply_text(f"\U000023F3 War cooldown: <b>{mins}m</b>.", parse_mode=ParseMode.HTML)
    if active_war(gang["_id"]):
        return await update.message.reply_text("\U000026A0\ufe0f Your gang already has a pending war.", parse_mode=ParseMode.HTML)

    stake = 0
    target_parts = args[1:]
    last_amount = parse_money(args[-1])
    if last_amount is not None and len(args) > 2:
        stake = last_amount
        target_parts = args[1:-1]
    target = find_gang_by_name(clean_name(target_parts))
    if not target:
        return await update.message.reply_text("\U0000274C Enemy gang not found.", parse_mode=ParseMode.HTML)
    target = ensure_gang_shape(target)
    if target["_id"] == gang["_id"]:
        return await update.message.reply_text("\U0000274C You cannot war your own gang.", parse_mode=ParseMode.HTML)
    if cooldown_left(target):
        return await update.message.reply_text("\U000023F3 Enemy gang is on war cooldown.", parse_mode=ParseMode.HTML)
    if active_war(target["_id"]):
        return await update.message.reply_text("\U000026A0\ufe0f Enemy gang already has a pending war.", parse_mode=ParseMode.HTML)
    if stake < 0 or stake > int(gang.get("bank", 0)) or stake > int(target.get("bank", 0)):
        return await update.message.reply_text("\U0001F4C9 Both gang banks must cover the stake.", parse_mode=ParseMode.HTML)

    war_id = str(uuid.uuid4())[:10]
    gang_wars_col.insert_one({
        "war_id": war_id,
        "status": "pending",
        "challenger_id": gang["_id"],
        "challenger_name": gang["name"],
        "target_id": target["_id"],
        "target_name": target["name"],
        "stake": stake,
        "created_by": user["user_id"],
        "chat_id": update.effective_chat.id if update.effective_chat else None,
        "created_at": datetime.utcnow(),
        "expires_at": datetime.utcnow() + PENDING_TTL,
    })
    track_many(user["user_id"], ["group_challenge"])
    await update.message.reply_text(
        f"\U00002694 <b>{stylize_text('War Declared')}</b>\n\n"
        f"<b>{format_gang(gang)}</b> challenged <b>{format_gang(target)}</b>.\n"
        f"Stake: <code>{format_money(stake)}</code>\n\n"
        f"Enemy leader must use <code>/gang accept</code> or <code>/gang decline</code>.",
        parse_mode=ParseMode.HTML,
    )


def resolve_war(war, target_gang, challenger_gang):
    challenger_score = gang_power(challenger_gang)
    target_score = gang_power(target_gang)
    challenger_wins = challenger_score >= target_score
    winner = challenger_gang if challenger_wins else target_gang
    loser = target_gang if challenger_wins else challenger_gang
    stake = int(war.get("stake", 0))
    rating_gain = 25 + min(25, abs(challenger_score - target_score) // 80)

    winner_inc = {"wins": 1, "rating": rating_gain}
    loser_inc = {"losses": 1, "rating": -rating_gain}
    if stake > 0:
        winner_inc["bank"] = stake
        loser_inc["bank"] = -stake
    cooldown_until = datetime.utcnow() + WAR_COOLDOWN
    gangs_col.update_one({"_id": winner["_id"]}, {"$inc": winner_inc, "$set": {"last_war": datetime.utcnow(), "war_cooldown_until": cooldown_until}})
    gangs_col.update_one({"_id": loser["_id"]}, {"$inc": loser_inc, "$set": {"last_war": datetime.utcnow(), "war_cooldown_until": cooldown_until}})
    users_collection.update_many({"user_id": {"$in": winner.get("members", [])}}, {"$inc": {"xp": 35, "game_wins": 1}})
    gang_wars_col.update_one(
        {"_id": war["_id"]},
        {
            "$set": {
                "status": "resolved",
                "resolved_at": datetime.utcnow(),
                "winner_id": winner["_id"],
                "winner_name": winner["name"],
                "loser_id": loser["_id"],
                "loser_name": loser["name"],
                "challenger_score": challenger_score,
                "target_score": target_score,
                "rating_gain": rating_gain,
            }
        },
    )
    return winner, loser, challenger_score, target_score, rating_gain


async def accept_war(update, user):
    gang = ensure_gang_shape(user_gang(user["user_id"]))
    if not gang:
        return await update.message.reply_text("\U0000274C Join a gang first.", parse_mode=ParseMode.HTML)
    if not is_leader(gang, user["user_id"]):
        return await update.message.reply_text("\U0001F512 Only the gang leader can accept wars.", parse_mode=ParseMode.HTML)
    war = gang_wars_col.find_one({"target_id": gang["_id"], "status": "pending", "expires_at": {"$gt": datetime.utcnow()}}, sort=[("created_at", -1)])
    if not war:
        return await update.message.reply_text("\U0000274C No incoming war found.", parse_mode=ParseMode.HTML)
    challenger = ensure_gang_shape(gangs_col.find_one({"_id": war["challenger_id"]}))
    if not challenger:
        gang_wars_col.update_one({"_id": war["_id"]}, {"$set": {"status": "cancelled"}})
        return await update.message.reply_text("\U0000274C Challenger gang no longer exists.", parse_mode=ParseMode.HTML)
    stake = int(war.get("stake", 0))
    if stake > int(gang.get("bank", 0)) or stake > int(challenger.get("bank", 0)):
        return await update.message.reply_text("\U0001F4C9 A gang bank cannot cover the stake now.", parse_mode=ParseMode.HTML)
    winner, loser, challenger_score, target_score, rating_gain = resolve_war(war, gang, challenger)
    track_many(user["user_id"], ["play_game", "group_challenge"])
    track_many(challenger.get("leader_id"), ["play_game", "group_challenge"])
    await update.message.reply_text(
        f"\U00002694 <b>{stylize_text('Gang War Result')}</b>\n\n"
        f"<b>{format_gang(challenger)}</b> power: <code>{challenger_score}</code>\n"
        f"<b>{format_gang(gang)}</b> power: <code>{target_score}</code>\n\n"
        f"\U0001F3C6 Winner: <b>{format_gang(winner)}</b>\n"
        f"\U0001F4C8 Rating: <code>+{rating_gain}</code>\n"
        f"\U0001F4B0 Stake swing: <code>{format_money(stake)}</code>",
        parse_mode=ParseMode.HTML,
    )


async def decline_war(update, user):
    gang = user_gang(user["user_id"])
    if not gang:
        return await update.message.reply_text("\U0000274C Join a gang first.", parse_mode=ParseMode.HTML)
    if not is_leader(gang, user["user_id"]):
        return await update.message.reply_text("\U0001F512 Only the gang leader can decline wars.", parse_mode=ParseMode.HTML)
    war = gang_wars_col.find_one({"target_id": gang["_id"], "status": "pending", "expires_at": {"$gt": datetime.utcnow()}}, sort=[("created_at", -1)])
    if not war:
        return await update.message.reply_text("\U0000274C No incoming war found.", parse_mode=ParseMode.HTML)
    gang_wars_col.update_one({"_id": war["_id"]}, {"$set": {"status": "declined", "resolved_at": datetime.utcnow()}})
    await update.message.reply_text("\U0000274C War declined.", parse_mode=ParseMode.HTML)


async def status(update, user):
    gang = user_gang(user["user_id"])
    if not gang:
        return await update.message.reply_text(war_help(None), parse_mode=ParseMode.HTML)
    gang = ensure_gang_shape(gang)
    pending = active_war(gang["_id"])
    cooldown = cooldown_left(gang)
    text = war_help(gang)
    if pending:
        direction = "Incoming" if pending["target_id"] == gang["_id"] else "Outgoing"
        enemy = pending["challenger_name"] if direction == "Incoming" else pending["target_name"]
        text += f"\n\n\U000026A0 <b>{direction} war:</b> {html.escape(enemy)} | <code>{format_money(pending.get('stake', 0))}</code>"
    elif cooldown:
        text += f"\n\n\U000023F3 Cooldown: <b>{max(1, int(cooldown.total_seconds() // 60))}m</b>"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def top_gangs(update):
    gangs = list(gangs_col.find().sort([("rating", -1), ("wins", -1), ("bank", -1)]).limit(10))
    if not gangs:
        return await update.message.reply_text("\U0001F4ED No gangs yet.", parse_mode=ParseMode.HTML)
    lines = [f"\U0001F451 <b>{stylize_text('Gang Rankings')}</b>\n"]
    for index, gang in enumerate(gangs, 1):
        gang = ensure_gang_shape(gang)
        lines.append(
            f"<code>{index}.</code> <b>{format_gang(gang)}</b> "
            f"\U00002694 {gang.get('rating', 1000)} | "
            f"W/L <b>{gang.get('wins', 0)}/{gang.get('losses', 0)}</b> | "
            f"\U0001F465 {len(gang.get('members', []))} | "
            f"\U0001F3E6 {format_money(gang.get('bank', 0))}"
        )
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def gang_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = ensure_user_exists(update.effective_user)
    args = context.args
    if not args:
        gang = user_gang(user["user_id"])
        return await update.message.reply_text(war_help(ensure_gang_shape(gang) if gang else None), parse_mode=ParseMode.HTML)

    action = args[0].lower()
    if action == "create":
        return await create_gang(update, user, args)
    if action == "join":
        return await join_gang(update, user, args)
    if action == "leave":
        return await leave_gang(update, user)
    if action == "deposit":
        return await deposit(update, user, args)
    if action == "withdraw":
        return await withdraw(update, user, args)
    if action == "war":
        return await declare_war(update, user, args)
    if action == "accept":
        return await accept_war(update, user)
    if action == "decline":
        return await decline_war(update, user)
    if action in ("status", "me"):
        return await status(update, user)
    if action in ("list", "top"):
        return await top_gangs(update)
    return await update.message.reply_text(war_help(user_gang(user["user_id"])), parse_mode=ParseMode.HTML)
