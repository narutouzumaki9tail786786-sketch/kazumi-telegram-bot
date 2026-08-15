from datetime import datetime, timedelta

from telegram import Update
from telegram.constants import ParseMode, ChatType
from telegram.ext import ContextTypes

from kazumi.database import users_collection
from kazumi.game_rules import BANK_INTEREST_COOLDOWN_SECONDS
from kazumi.missions import mission_payload
from kazumi.utils import ensure_user_exists, format_time, stylize_text, protection_max_duration


def seconds_until(last_value, cooldown_seconds):
    if not last_value:
        return 0
    remaining = int(cooldown_seconds - (datetime.utcnow() - last_value).total_seconds())
    return max(0, remaining)


def cooldown_row(label, seconds):
    if seconds <= 0:
        return f"\U00002705 <b>{label}:</b> Ready"
    return f"\U000023F3 <b>{label}:</b> {format_time(timedelta(seconds=seconds))}"


def daily_limits(user):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    kill_limit = 400 if user.get("is_premium", False) else 200
    rob_limit = 300 if user.get("is_premium", False) else 150
    kill_data = user.get("kill_limit", {}) or {}
    rob_data = user.get("rob_limit", {}) or {}
    kills_used = int(kill_data.get("count", 0)) if kill_data.get("date") == today else 0
    robs_used = int(rob_data.get("count", 0)) if rob_data.get("date") == today else 0
    return kills_used, kill_limit, robs_used, rob_limit


async def cooldowns_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = ensure_user_exists(update.effective_user)
    protection = user.get("protection_expiry")
    protection_seconds = 0
    if protection and protection > datetime.utcnow():
        max_seconds = int(protection_max_duration(user).total_seconds())
        protection_seconds = min(int((protection - datetime.utcnow()).total_seconds()), max_seconds)

    kills_used, kill_limit, robs_used, rob_limit = daily_limits(user)
    missions = mission_payload(user["user_id"])

    protection_row = cooldown_row("Protection", protection_seconds)
    if update.effective_chat.type != ChatType.PRIVATE:
        protection_row = "\U0001f6e1\ufe0f <b>Protection:</b> Active" if protection_seconds > 0 else "\U00002705 <b>Protection:</b> Ready"

    text = (
        f"\U000023F1 <b>{stylize_text('Cooldowns')}</b>\n\n"
        f"{cooldown_row('Daily', seconds_until(user.get('last_daily'), 86400))}\n"
        f"{cooldown_row('Spin', seconds_until(user.get('last_spin'), 86400))}\n"
        f"{cooldown_row('Fortune', seconds_until(user.get('last_fortune'), 86400))}\n"
        f"{cooldown_row('Bank Interest', seconds_until(user.get('last_interest'), BANK_INTEREST_COOLDOWN_SECONDS) if user.get('bank', 0) > 0 else 0)}\n"
        f"{protection_row}\n\n"
        f"\U0001F5E1 <b>Kills Today:</b> <code>{kills_used}/{kill_limit}</code>\n"
        f"\U0001F4B0 <b>Robs Today:</b> <code>{robs_used}/{rob_limit}</code>\n"
        f"\U0001F4CB <b>Today Plan:</b> <code>{missions['completed']}/{missions['total']}</code>"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)
