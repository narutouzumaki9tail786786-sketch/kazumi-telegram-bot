from datetime import datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from kazumi.database import db, users_collection
from kazumi.utils import ensure_user_exists, format_money, get_mention, stylize_text


gangs_collection = db["gangs"]


def season_window(now=None):
    now = now or datetime.utcnow()
    start = datetime(now.year, now.month, 1)
    if now.month == 12:
        end = datetime(now.year + 1, 1, 1)
    else:
        end = datetime(now.year, now.month + 1, 1)
    season_id = f"{now.year}-{now.month:02d}"
    season_name = now.strftime("%B %Y")
    return season_id, season_name, start, end


def time_left_text(end):
    remaining = end - datetime.utcnow()
    if remaining.total_seconds() <= 0:
        return "ending now"
    days = remaining.days
    hours = remaining.seconds // 3600
    return f"{days}d {hours}h"


def rank_for(field, value):
    return users_collection.count_documents({field: {"$gt": value}}) + 1


def top_rows(field, limit=5):
    rows = list(users_collection.find({field: {"$gt": 0}}).sort(field, -1).limit(limit))
    if not rows:
        rows = list(users_collection.find({}).sort("balance", -1).limit(limit))
    return rows


def leaderboard_text(title, rows, field, money_mode=False):
    text = f"\n<b>{title}</b>\n"
    if not rows:
        return text + "<i>No players yet.</i>\n"
    for index, user in enumerate(rows, 1):
        value = user.get(field, 0)
        shown = format_money(value) if money_mode else str(value)
        text += f"<code>{index}.</code> {get_mention(user)} - <b>{shown}</b>\n"
    return text


def build_season_top_text():
    season_id, season_name, start, end = season_window()
    text = (
        f"\U0001F3C6 <b>{stylize_text('Season Leaderboard')}</b>\n"
        f"<b>{season_name}</b> | <code>{season_id}</code>\n"
        f"<i>Ends in {time_left_text(end)}.</i>\n"
    )
    text += leaderboard_text("\U0001F4B0 Richest", top_rows("balance"), "balance", True)
    text += leaderboard_text("\U0001F5E1 Top Killers", top_rows("kills"), "kills")
    text += leaderboard_text("\U0001F3AE Game Winners", top_rows("game_wins"), "game_wins")
    gangs = list(gangs_collection.find({}).sort([("rating", -1), ("wins", -1), ("bank", -1)]).limit(5))
    text += "\n<b>\U0001F451 Gang Rating</b>\n"
    if gangs:
        for index, gang in enumerate(gangs, 1):
            text += (
                f"<code>{index}.</code> <b>{gang.get('name', 'Gang')}</b> - "
                f"{gang.get('rating', 1000)} rating | {gang.get('wins', 0)}W\n"
            )
    else:
        text += "<i>No gangs yet.</i>\n"
    return text


def build_season_rewards_text():
    return (
        f"\U0001F381 <b>{stylize_text('Season Rewards')}</b>\n\n"
        "<b>Top Richest:</b> bragging rank + future coin prize\n"
        "<b>Top Killer:</b> war title + future badge\n"
        "<b>Top Game Winner:</b> game title + future badge\n"
        "<b>Top Gang:</b> gang title + future bank bonus\n\n"
        "<i>Current season tracks live stats. Snapshot rewards can be automated next.</i>"
    )


def build_season_status_text(user):
    season_id, season_name, start, end = season_window()
    balance_rank = rank_for("balance", user.get("balance", 0))
    kill_rank = rank_for("kills", user.get("kills", 0))
    win_rank = rank_for("game_wins", user.get("game_wins", 0))
    return (
        f"\U0001F3C6 <b>{stylize_text('Kazumi Season')}</b>\n\n"
        f"<b>Season:</b> {season_name} (<code>{season_id}</code>)\n"
        f"<b>Ends in:</b> <code>{time_left_text(end)}</code>\n\n"
        f"\U0001F464 <b>Your ranks</b>\n"
        f"\U0001F4B0 Richest: <code>#{balance_rank}</code> | {format_money(user.get('balance', 0))}\n"
        f"\U0001F5E1 Killer: <code>#{kill_rank}</code> | {user.get('kills', 0)} kills\n"
        f"\U0001F3AE Games: <code>#{win_rank}</code> | {user.get('game_wins', 0)} wins\n\n"
        "<b>Use:</b> <code>/season top</code> or <code>/season rewards</code>"
    )


async def season_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = ensure_user_exists(update.effective_user)
    action = context.args[0].lower() if context.args else "status"

    if action in ("top", "leaderboard", "lb"):
        return await update.message.reply_text(build_season_top_text(), parse_mode=ParseMode.HTML)

    if action in ("rewards", "reward"):
        return await update.message.reply_text(build_season_rewards_text(), parse_mode=ParseMode.HTML)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Leaderboard", callback_data="season_top")],
        [InlineKeyboardButton("Rewards", callback_data="season_rewards")],
    ])
    await update.message.reply_text(
        build_season_status_text(user),
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )


async def season_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "season_top":
        text = build_season_top_text()
    elif query.data == "season_rewards":
        text = build_season_rewards_text()
    else:
        user = ensure_user_exists(query.from_user)
        text = build_season_status_text(user)
    await query.message.reply_text(text, parse_mode=ParseMode.HTML)
