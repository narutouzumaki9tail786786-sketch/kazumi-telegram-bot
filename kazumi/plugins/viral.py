# 🌸 Kazumi — Spin Wheel + Crate + Bank + Fortune + Confess + Wanted + Titles + Polls + Stocks
import random, time
from datetime import datetime, timedelta
import httpx
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode, ChatType
from kazumi.utils import ensure_user_exists, get_mention, format_money, stylize_text, add_xp
from kazumi.database import db, users_collection
from kazumi.ledger import adjust_user_balance
from kazumi.config import XP_PER_GAME_WIN
from kazumi.game_rules import (
    BANK_INTEREST_COOLDOWN_SECONDS,
    MAX_BANK_BALANCE,
    MAX_INVEST_BUY_AMOUNT,
    bank_interest_payout,
    safe_invest_sell_value,
    safe_market_price,
)

# ━━━━ 🎰 SPIN WHEEL ━━━━
SPIN_PRIZES = [100, 200, 500, 1000, 2000, 5000, 10000, 50000, 0, 0]
SPIN_EMOJIS = ["🍒","🍊","🍋","🍇","💎","🌟","🔥","👑","💀","💀"]

async def spin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = ensure_user_exists(update.effective_user)
    last = user.get("last_spin")
    if last and (datetime.utcnow() - last).total_seconds() < 86400:
        remaining = 86400 - (datetime.utcnow() - last).total_seconds()
        h, m = int(remaining // 3600), int((remaining % 3600) // 60)
        return await update.message.reply_text(f"⏳ ɴᴇxᴛ sᴘɪɴ ɪɴ <b>{h}ʜ {m}ᴍ</b>", parse_mode=ParseMode.HTML)
    
    idx = random.randint(0, len(SPIN_PRIZES)-1)
    prize = SPIN_PRIZES[idx]
    emoji = SPIN_EMOJIS[idx]
    
    users_collection.update_one({"user_id": user['user_id']}, {"$set": {"last_spin": datetime.utcnow()}})
    if prize > 0:
        adjust_user_balance(
            user['user_id'],
            prize,
            category="spin_reward",
            reason=f"Won Daily Spin Wheel +{format_money(prize)}",
            chat_id=update.effective_chat.id if update.effective_chat else None,
            source="/spin",
        )
        await add_xp(user['user_id'], 15)
    
    result = f"💰 +<code>{format_money(prize)}</code>!" if prize > 0 else "💀 ʙᴇᴛᴛᴇʀ ʟᴜᴄᴋ ᴛᴏᴍᴏʀʀᴏᴡ!"
    await update.message.reply_text(
        f"🎰 <b>{stylize_text('Spin Wheel')}</b>\n━━━━━━━━━━━━\n\n"
        f"[ {emoji} ] {emoji} [ {emoji} ]\n\n{result}", parse_mode=ParseMode.HTML)

# ━━━━ 📦 CRATE/LOOT BOX ━━━━
CRATE_COST = 2000
CRATE_USER_COOLDOWN = 10 * 60
CRATE_CHAT_COOLDOWN = 2.5
CRATE_SPAM_WINDOW = 15 * 60
CRATE_SPAM_PENALTIES = [10 * 60, 20 * 60, 45 * 60, 2 * 60 * 60, 6 * 60 * 60]
_CRATE_USER_LAST = {}
_CRATE_CHAT_LAST = {}
_CRATE_NOTICE_LAST = {}
_CRATE_SPAM_STATE = {}
CRATE_ITEMS = [
    {"name": "🗑️ ᴊᴜɴᴋ", "rarity": "Common", "value": 100, "chance": 30},
    {"name": "🪵 ᴡᴏᴏᴅ", "rarity": "Common", "value": 500, "chance": 25},
    {"name": "⚙️ ɢᴇᴀʀ", "rarity": "Uncommon", "value": 1500, "chance": 20},
    {"name": "💎 ɢᴇᴍ", "rarity": "Rare", "value": 5000, "chance": 12},
    {"name": "🌟 sᴛᴀʀ", "rarity": "Epic", "value": 15000, "chance": 8},
    {"name": "👑 ᴄʀᴏᴡɴ", "rarity": "Legendary", "value": 50000, "chance": 4},
    {"name": "🏆 ᴛʀᴏᴘʜʏ", "rarity": "Mythic", "value": 100000, "chance": 1},
]

def _crate_time_left(seconds: float) -> str:
    seconds = max(1, int(seconds))
    if seconds >= 60:
        mins = seconds // 60
        secs = seconds % 60
        return f"{mins}m {secs}s" if secs else f"{mins}m"
    return f"{seconds}s"


def _crate_spam_penalty(uid: int, now_ts: float) -> int:
    state = _CRATE_SPAM_STATE.get(uid) or {"count": 0, "window_until": now_ts + CRATE_SPAM_WINDOW}
    if now_ts > state.get("window_until", 0):
        state = {"count": 0, "window_until": now_ts + CRATE_SPAM_WINDOW}
    state["count"] = int(state.get("count", 0)) + 1
    _CRATE_SPAM_STATE[uid] = state
    idx = min(max(0, state["count"] - 1), len(CRATE_SPAM_PENALTIES) - 1)
    return CRATE_SPAM_PENALTIES[idx]


def _crate_datetime(value):
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        return datetime.utcfromtimestamp(value)
    return None


async def _send_crate_message(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    message = update.effective_message
    chat = update.effective_chat
    if not chat:
        return
    kwargs = {}
    thread_id = getattr(message, "message_thread_id", None) if message else None
    if thread_id:
        kwargs["message_thread_id"] = thread_id
    await context.bot.send_message(
        chat_id=chat.id,
        text=text,
        parse_mode=ParseMode.HTML,
        **kwargs,
    )


async def crate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message:
        return
    now_ts = time.time()
    uid = update.effective_user.id if update.effective_user else 0
    cid = update.effective_chat.id if update.effective_chat else 0
    user = ensure_user_exists(update.effective_user)
    now_dt = datetime.utcnow()
    cooldown_until = _crate_datetime(user.get("crate_cooldown_until"))
    user_last = _CRATE_USER_LAST.get(uid, 0)
    memory_cooldown_left = CRATE_USER_COOLDOWN - (now_ts - user_last)
    db_cooldown_left = (cooldown_until - now_dt).total_seconds() if cooldown_until and cooldown_until > now_dt else 0
    remaining = max(memory_cooldown_left, db_cooldown_left)
    if remaining > 0:
        penalty = _crate_spam_penalty(uid, now_ts)
        extended_seconds = max(remaining, penalty)
        extended_until = now_dt + timedelta(seconds=extended_seconds)
        _CRATE_USER_LAST[uid] = now_ts + extended_seconds - CRATE_USER_COOLDOWN
        users_collection.update_one(
            {"user_id": user["user_id"]},
            {
                "$set": {"crate_cooldown_until": extended_until},
                "$inc": {"crate_spam_hits": 1},
            },
        )
        if now_ts - _CRATE_NOTICE_LAST.get(uid, 0) > 20:
            _CRATE_NOTICE_LAST[uid] = now_ts
            await _send_crate_message(
                update,
                context,
                f"\U000023F3 <b>ᴄʀᴀᴛᴇ ᴄᴏᴏʟᴅᴏᴡɴ:</b> <code>{_crate_time_left((extended_until - now_dt).total_seconds())}</code>\n"
                "<i>Spam karoge to timer aur badhega.</i>",
            )
        return
    if cid and now_ts - _CRATE_CHAT_LAST.get(cid, 0) < CRATE_CHAT_COOLDOWN:
        return
    _CRATE_USER_LAST[uid] = now_ts
    _CRATE_SPAM_STATE.pop(uid, None)
    if cid:
        _CRATE_CHAT_LAST[cid] = now_ts

    charged = adjust_user_balance(
        user['user_id'],
        -CRATE_COST,
        category="crate_buy",
        reason="Opened Loot Crate",
        chat_id=update.effective_chat.id if update.effective_chat else None,
        source="/crate",
        require_gte=CRATE_COST,
    )
    if not charged:
        return await _send_crate_message(
            update,
            context,
            f"\U0001F4C9 ɴᴇᴇᴅ <code>{format_money(CRATE_COST)}</code>!",
        )
    
    roll = random.randint(1, 100)
    cumulative = 0
    item = CRATE_ITEMS[0]
    for i in CRATE_ITEMS:
        cumulative += i['chance']
        if roll <= cumulative: item = i; break
    
    next_crate_at = datetime.utcnow() + timedelta(seconds=CRATE_USER_COOLDOWN)
    users_collection.update_one(
        {"user_id": user['user_id']},
        {
            "$set": {
                "last_crate": datetime.utcnow(),
                "crate_cooldown_until": next_crate_at,
                "crate_spam_hits": 0,
            },
        },
    )
    if item['value'] > 0:
        adjust_user_balance(
            user['user_id'],
            item['value'],
            category="crate_reward",
            reason=f"Loot Crate item: {item['name']} (+{format_money(item['value'])})",
            chat_id=update.effective_chat.id if update.effective_chat else None,
            source="/crate",
        )
    rarity_colors = {"Common": "⬜", "Uncommon": "🟩", "Rare": "🟦", "Epic": "🟪", "Legendary": "🟨", "Mythic": "🟥"}
    rc = rarity_colors.get(item['rarity'], "⬜")
    
    await _send_crate_message(
        update,
        context,
        f"\U0001F4E6 <b>{stylize_text('Loot Crate')}</b>\n━━━━━━━━━━━━\n\n"
        f"\U0001F381 ᴏᴘᴇɴɪɴɢ...\n\n"
        f"{rc} <b>[{item['rarity'].upper()}]</b>\n"
        f"{item['name']}\n"
        f"\U0001F4B0 +<code>{format_money(item['value'])}</code>\n"
        f"\n\U000023F3 ɴᴇxᴛ ᴄʀᴀᴛᴇ: <code>{_crate_time_left(CRATE_USER_COOLDOWN)}</code>",
    )

# ━━━━ 🏦 BANK + INTEREST ━━━━
INTEREST_RATE = 0.05

async def bank_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = ensure_user_exists(update.effective_user)
    bank_bal = int(user.get("bank", 0) or 0)
    
    if not context.args:
        # Collect interest
        last_interest = user.get("last_interest")
        interest = 0
        if last_interest and bank_bal > 0:
            seconds = (datetime.utcnow() - last_interest).total_seconds()
            if seconds >= BANK_INTEREST_COOLDOWN_SECONDS:
                interest = bank_interest_payout(bank_bal, rate=INTEREST_RATE)
                if interest > 0:
                    applied = adjust_user_balance(
                        user["user_id"],
                        0,
                        "bank_interest",
                        "Collected bank interest",
                        chat_id=update.effective_chat.id if update.effective_chat else None,
                        source="/bank",
                        extra_query={"bank": {"$gt": 0}},
                        extra_inc={"bank": interest},
                        extra_set={"last_interest": datetime.utcnow()},
                        meta={"bank_delta": interest, "bank_before": bank_bal, "bank_after": bank_bal + interest},
                    )
                    if applied:
                        bank_bal += interest
        
        msg = (f"🏦 <b>{stylize_text('Bank')}</b>\n━━━━━━━━━━━━\n\n"
               f"👛 ᴡᴀʟʟᴇᴛ: <code>{format_money(user['balance'])}</code>\n"
               f"🏦 ʙᴀɴᴋ: <code>{format_money(bank_bal)}</code>\n"
               f"📈 ʀᴀᴛᴇ: 5% ᴇᴠᴇʀʏ 48ʜ\n")
        if interest > 0: msg += f"\n💰 ɪɴᴛᴇʀᴇsᴛ ᴄᴏʟʟᴇᴄᴛᴇᴅ: +{format_money(interest)}!"
        msg += f"\n\n/bank deposit [amt]\n/bank withdraw [amt]"
        return await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
    
    act = context.args[0].lower()
    if len(context.args) < 2: return
    try: amt = int(context.args[1])
    except: return
    if amt <= 0: return
    
    if act == "deposit":
        if user['balance'] < amt: return await update.message.reply_text("📉 ɴᴏᴛ ᴇɴᴏᴜɢʜ!", parse_mode=ParseMode.HTML)
        deposited = adjust_user_balance(
            user["user_id"],
            -amt,
            "bank_deposit",
            "Deposited to bank",
            chat_id=update.effective_chat.id if update.effective_chat else None,
            source="/bank deposit",
            require_gte=amt,
            extra_inc={"bank": amt},
            extra_set={"last_interest": datetime.utcnow()},
            meta={"bank_delta": amt, "bank_before": bank_bal, "bank_after": bank_bal + amt},
        )
        if not deposited:
            return await update.message.reply_text("📉 ᴅᴇᴘᴏsɪᴛ ꜰᴀɪʟᴇᴅ!", parse_mode=ParseMode.HTML)
        await update.message.reply_text(f"🏦 ᴅᴇᴘᴏsɪᴛᴇᴅ <code>{format_money(amt)}</code>!", parse_mode=ParseMode.HTML)
    elif act == "withdraw":
        if bank_bal < amt: return await update.message.reply_text("📉 ɴᴏᴛ ᴇɴᴏᴜɢʜ ɪɴ ʙᴀɴᴋ!", parse_mode=ParseMode.HTML)
        withdrawn = adjust_user_balance(
            user["user_id"],
            amt,
            "bank_withdraw",
            "Withdrew from bank",
            chat_id=update.effective_chat.id if update.effective_chat else None,
            source="/bank withdraw",
            extra_query={"bank": {"$gte": amt}},
            extra_inc={"bank": -amt},
            meta={"bank_delta": -amt, "bank_before": bank_bal, "bank_after": bank_bal - amt},
        )
        if not withdrawn:
            return await update.message.reply_text("📉 ᴡɪᴛʜᴅʀᴀᴡ ꜰᴀɪʟᴇᴅ!", parse_mode=ParseMode.HTML)
        await update.message.reply_text(f"🏦 ᴡɪᴛʜᴅʀᴀᴡɴ <code>{format_money(amt)}</code>!", parse_mode=ParseMode.HTML)

# ━━━━ 🔮 FORTUNE ━━━━
FORTUNES = [
    "🌟 ᴛᴏᴅᴀʏ ʏᴏᴜ ᴡɪʟʟ ғɪɴᴅ ᴜɴᴇxᴘᴇᴄᴛᴇᴅ ᴡᴇᴀʟᴛʜ!", "💀 ᴅᴏɴ'ᴛ ɢᴀᴍʙʟᴇ ᴛᴏᴅᴀʏ... ᴊᴜsᴛ ᴅᴏɴ'ᴛ.",
    "💕 ʟᴏᴠᴇ ɪs ᴄᴏᴍɪɴɢ ʏᴏᴜʀ ᴡᴀʏ!", "⚔️ ᴀ ɢʀᴇᴀᴛ ʙᴀᴛᴛʟᴇ ᴀᴡᴀɪᴛs ʏᴏᴜ!",
    "🍀 ʟᴜᴄᴋ ɪs ᴏɴ ʏᴏᴜʀ sɪᴅᴇ — ᴏᴘᴇɴ ᴀ ᴄʀᴀᴛᴇ!", "🔥 ʏᴏᴜ ᴡɪʟʟ ᴅᴏᴍɪɴᴀᴛᴇ ᴛᴏᴅᴀʏ!",
    "🌙 ᴛᴀᴋᴇ ɪᴛ ᴇᴀsʏ ᴛᴏᴅᴀʏ, ʀᴇsᴛ ɪs ᴘᴏᴡᴇʀ.", "👑 ʏᴏᴜ ᴀʀᴇ ᴅᴇsᴛɪɴᴇᴅ ғᴏʀ ɢʀᴇᴀᴛɴᴇss!",
    "💎 ᴀ ʟᴇɢᴇɴᴅᴀʀʏ ᴅʀᴏᴘ ɪs ɴᴇᴀʀ...", "🦋 sᴏᴍᴇᴏɴᴇ sᴇᴄʀᴇᴛʟʏ ᴀᴅᴍɪʀᴇs ʏᴏᴜ!",
]

async def fortune_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = ensure_user_exists(update.effective_user)
    last = user.get("last_fortune")
    if last and (datetime.utcnow() - last).total_seconds() < 86400:
        return await update.message.reply_text("⏳ ᴏɴᴇ ғᴏʀᴛᴜɴᴇ ᴘᴇʀ ᴅᴀʏ!", parse_mode=ParseMode.HTML)
    
    f = random.choice(FORTUNES)
    bonus = random.choice([0, 0, 100, 200, 500, 1000])
    users_collection.update_one({"user_id": user['user_id']}, {"$set": {"last_fortune": datetime.utcnow()}})
    if bonus > 0:
        adjust_user_balance(
            user['user_id'],
            bonus,
            category="fortune_bonus",
            reason=f"Daily Fortune lucky bonus +{format_money(bonus)}",
            chat_id=update.effective_chat.id if update.effective_chat else None,
            source="/fortune",
        )
    
    msg = f"🔮 <b>{stylize_text('Fortune')}</b>\n━━━━━━━━━━━━\n\n{f}\n"
    if bonus > 0: msg += f"\n🍀 ʟᴜᴄᴋ ɪs ᴏɴ ʏᴏᴜʀ sɪᴅᴇ: +{format_money(bonus)}!"
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

# ━━━━ 💌 CONFESS ━━━━
async def confess_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("💌 <code>/confess @user I like you</code>", parse_mode=ParseMode.HTML)
    user = ensure_user_exists(update.effective_user)
    text = " ".join(context.args)
    
    try: await update.message.delete()
    except: pass
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"💌 <b>{stylize_text('Anonymous Confession')}</b>\n━━━━━━━━━━━━\n\n<i>\"{text}\"</i>\n\n— ᴀɴᴏɴʏᴍᴏᴜs 🎭",
        parse_mode=ParseMode.HTML)

# ━━━━ 💀 WANTED ━━━━
async def wanted_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    top_killed = list(
        users_collection.find(
            {"$or": [{"deaths": {"$gt": 0}}, {"status": "dead"}]}
        ).sort("deaths", -1).limit(5)
    )
    top_killers = list(users_collection.find().sort("kills", -1).limit(5))
    
    msg = f"💀 <b>{stylize_text('Wanted Board')}</b>\n━━━━━━━━━━━━\n\n"
    msg += f"🔪 <b>ᴛᴏᴘ ᴋɪʟʟᴇʀs:</b>\n"
    for i, u in enumerate(top_killers[:5], 1):
        msg += f"{i}. {get_mention(u)} — ⚔️{u.get('kills',0)}\n"
    
    msg += f"\n💀 <b>ᴍᴏsᴛ ᴅᴇᴀᴅ:</b>\n"
    if top_killed:
        for i, u in enumerate(top_killed[:3], 1):
            deaths = int(u.get("deaths") or (1 if u.get("status") == "dead" else 0))
            msg += f"{i}. {get_mention(u)} — 🪦{deaths}\n"
    else: msg += "ɴᴏ ᴏɴᴇ ᴅᴇᴀᴅ ʏᴇᴛ!\n"
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

# ━━━━ 🏷️ TITLES ━━━━
TITLES = {
    "newbie": {"name": "「ɴᴇᴡʙɪᴇ」", "cost": 0},
    "warrior": {"name": "「ᴡᴀʀʀɪᴏʀ」", "cost": 5000},
    "king": {"name": "「ᴋɪɴɢ」", "cost": 25000},
    "legend": {"name": "「ʟᴇɢᴇɴᴅ」", "cost": 100000},
    "newbie": {"name": "「ɴᴇᴡʙɪᴇ」", "cost": 0},
    "warrior": {"name": "「ᴡᴀʀʀɪᴏʀ」", "cost": 5000},
    "king": {"name": "「ᴋɪɴɢ」", "cost": 25000},
    "legend": {"name": "「ʟᴇɢᴇɴᴅ」", "cost": 100000},
    "god": {"name": "「ɢᴏᴅ」", "cost": 500000},
    "demon": {"name": "「ᴅᴇᴍᴏɴ」", "cost": 50000},
    "angel": {"name": "「ᴀɴɢᴇʟ」", "cost": 50000},
    "phantom": {"name": "「ᴘʜᴀɴᴛᴏᴍ」", "cost": 75000},
    "shadow": {"name": "「sʜᴀᴅᴏᴡ」", "cost": 30000},
    "queen": {"name": "「ǫᴜᴇᴇɴ」", "cost": 25000},
}

async def title_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = ensure_user_exists(update.effective_user)
    if not context.args:
        cur = user.get("title", "ɴᴏɴᴇ")
        msg = f"🏷️ <b>{stylize_text('Titles')}</b>\n━━━━━━━━━━━━\n\nᴄᴜʀʀᴇɴᴛ: <b>{cur}</b>\n\n"
        for tid, t in TITLES.items():
            msg += f"<code>/title {tid}</code> — {t['name']} ({format_money(t['cost'])})\n"
        return await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
    
    tid = context.args[0].lower()
    if tid not in TITLES: return await update.message.reply_text("❌ ɪɴᴠᴀʟɪᴅ ᴛɪᴛʟᴇ!", parse_mode=ParseMode.HTML)
    t = TITLES[tid]
    if user['balance'] < t['cost']: return await update.message.reply_text("📉 ɴᴏᴛ ᴇɴᴏᴜɢʜ!", parse_mode=ParseMode.HTML)
    users_collection.update_one({"user_id": user['user_id']}, {"$inc": {"balance": -t['cost']}, "$set": {"title": t['name']}})
    await update.message.reply_text(f"🏷️ ᴛɪᴛʟᴇ sᴇᴛ: <b>{t['name']}</b>", parse_mode=ParseMode.HTML)

# ━━━━ 🗳️ POLLS ━━━━
POLL_QUESTIONS = [
    "ᴡʜᴏ ᴡᴏᴜʟᴅ sᴜʀᴠɪᴠᴇ ᴀ ᴢᴏᴍʙɪᴇ ᴀᴘᴏᴄᴀʟʏᴘsᴇ?", "ᴡʜᴏ ɪs ᴛʜᴇ ᴍᴏsᴛ ᴅᴀɴɢᴇʀᴏᴜs ʜᴇʀᴇ?",
    "ᴡʜᴏ ᴡᴏᴜʟᴅ ʙᴇ ᴛʜᴇ ᴡᴏʀsᴛ ʙᴏss?", "ᴡʜᴏ ᴛᴀʟᴋs ᴛᴏᴏ ᴍᴜᴄʜ?",
    "ᴡʜᴏ ɪs sᴇᴄʀᴇᴛʟʏ ᴀ ɢᴇɴɪᴜs?", "ᴡʜᴏ ᴡᴏᴜʟᴅ ᴡɪɴ ɪɴ ᴀ ғɪɢʜᴛ?",
]

async def funpoll_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == ChatType.PRIVATE: return await update.message.reply_text("❌ ɢʀᴏᴜᴘ ᴏɴʟʏ!")
    q = random.choice(POLL_QUESTIONS)
    await update.message.reply_text(f"🗳️ <b>{stylize_text('Fun Poll')}</b>\n━━━━━━━━━━━━\n\n❓ <b>{q}</b>\n\n<i>ʀᴇᴘʟʏ ᴡɪᴛʜ ʏᴏᴜʀ ᴀɴsᴡᴇʀ!</i>", parse_mode=ParseMode.HTML)

# ━━━━ 📈 LIVE MARKET ━━━━
MARKET_SYMBOLS = {
    "BTC": {"type": "binance", "pair": "BTCUSDT", "yahoo": "BTC-USD"},
    "ETH": {"type": "binance", "pair": "ETHUSDT", "yahoo": "ETH-USD"},
    "SOL": {"type": "binance", "pair": "SOLUSDT", "yahoo": "SOL-USD"},
    "DOGE": {"type": "binance", "pair": "DOGEUSDT", "yahoo": "DOGE-USD"},
    "PEPE": {"type": "binance", "pair": "PEPEUSDT", "yahoo": "PEPE-USD"},
    "BNB": {"type": "binance", "pair": "BNBUSDT", "yahoo": "BNB-USD"},
    "GOLD": {"type": "yahoo", "pair": "GC=F"},
    "CRUDE": {"type": "yahoo", "pair": "CL=F"},
    "NIFTY": {"type": "yahoo", "pair": "^NSEI"},
    "SENSEX": {"type": "yahoo", "pair": "^BSESN"},
    "USDINR": {"type": "yahoo", "pair": "INR=X"},
}
MARKET_FALLBACKS = {
    "BTC": 64000.0,
    "ETH": 1850.0,
    "SOL": 74.0,
    "DOGE": 0.07,
    "PEPE": 0.000008,
    "BNB": 560.0,
    "NIFTY": 23750.0,
    "SENSEX": 76000.0,
    "USDINR": 83.5,
    "GOLD": 2400.0,
    "CRUDE": 85.0,
}

_QUOTE_CACHE = {}  # {symbol: {"price": float, "change": float, "ts": float}}
_QUOTE_CACHE_TTL = 30.0  # 30s cache


async def fetch_market_quotes(symbols=None):
    requested = [sym.upper() for sym in (symbols or MARKET_SYMBOLS.keys()) if sym.upper() in MARKET_SYMBOLS]
    if not requested:
        requested = list(MARKET_SYMBOLS.keys())

    now = time.time()
    quotes = {}
    missing_symbols = []

    for sym in requested:
        cached = _QUOTE_CACHE.get(sym)
        if cached and (now - cached["ts"]) < _QUOTE_CACHE_TTL:
            quotes[sym] = {"price": cached["price"], "change": cached["change"], "live": True}
        else:
            missing_symbols.append(sym)

    if missing_symbols:
        # 1. Fetch Binance Crypto Pairs
        binance_requested = [sym for sym in missing_symbols if MARKET_SYMBOLS[sym]["type"] == "binance"]
        if binance_requested:
            pairs = [MARKET_SYMBOLS[sym]["pair"] for sym in binance_requested]
            pairs_param = "[" + ",".join(f'"{p}"' for p in pairs) + "]"
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get("https://api.binance.com/api/v3/ticker/24hr", params={"symbols": pairs_param})
                    if resp.status_code == 200:
                        rows = resp.json()
                        pair_map = {r["symbol"]: r for r in rows if isinstance(r, dict)}
                        for sym in binance_requested:
                            pair = MARKET_SYMBOLS[sym]["pair"]
                            data = pair_map.get(pair, {})
                            price = float(data.get("lastPrice", MARKET_FALLBACKS.get(sym, 1000)))
                            change = float(data.get("priceChangePercent", 0.0))
                            _QUOTE_CACHE[sym] = {"price": price, "change": change, "ts": now}
                            quotes[sym] = {"price": price, "change": change, "live": True}
            except Exception as bin_exc:
                print(f"[BINANCE FETCH ERROR] {bin_exc}", flush=True)

        # 2. Fetch Yahoo Chart Symbols (Stocks, Gold, Forex, Nifty)
        yahoo_requested = [sym for sym in missing_symbols if sym not in quotes]
        if yahoo_requested:
            async with httpx.AsyncClient(timeout=5.0) as client:
                for sym in yahoo_requested:
                    yahoo_pair = MARKET_SYMBOLS[sym]["pair"]
                    try:
                        resp = await client.get(
                            f"https://query2.finance.yahoo.com/v8/finance/chart/{yahoo_pair}",
                            params={"interval": "1d"},
                            headers={"User-Agent": "Mozilla/5.0 KazumiBot/2.0"},
                        )
                        if resp.status_code == 200:
                            meta = resp.json().get("chart", {}).get("result", [{}])[0].get("meta", {})
                            price = float(meta.get("regularMarketPrice") or MARKET_FALLBACKS.get(sym, 1000))
                            prev_close = float(meta.get("chartPreviousClose") or price)
                            change = round(((price - prev_close) / prev_close) * 100, 2) if prev_close else 0.0
                            _QUOTE_CACHE[sym] = {"price": price, "change": change, "ts": now}
                            quotes[sym] = {"price": price, "change": change, "live": True}
                    except Exception:
                        fb_price = MARKET_FALLBACKS.get(sym, 1000.0)
                        _QUOTE_CACHE[sym] = {"price": fb_price, "change": 0.0, "ts": now}
                        quotes[sym] = {"price": fb_price, "change": 0.0, "live": False}

    return quotes


async def invest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = ensure_user_exists(update.effective_user)
    portfolio = user.get("stocks", {})

    if not context.args:
        quotes = await fetch_market_quotes()
        msg = f"📈 <b>{stylize_text('Live Market')}</b>\n━━━━━━━━━━━━\n\n"
        for sym, data in quotes.items():
            change = data["change"]
            price = data["price"]
            arrow = "📈" if change >= 0 else "📉"
            fmt_price = f"{price:,.4f}" if price < 1 else f"{price:,.2f}"
            msg += f"{arrow} <b>{sym}</b>: <code>${fmt_price}</code> ({change:+.2f}%) 🟢 <i>live</i>\n"
        msg += f"\n💡 <i>Hold stocks for +1.5% HODL Yield Bonus every 15m!</i>\n"
        msg += f"<code>/invest buy BTC 1000</code>\n<code>/invest sell BTC</code>\n<code>/invest portfolio</code>"
        return await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

    act = context.args[0].lower()
    if act == "portfolio":
        if not portfolio:
            return await update.message.reply_text("📭 <b>Your portfolio is empty!</b>\nUse <code>/invest buy BTC 1000</code> to invest.", parse_mode=ParseMode.HTML)
        msg = f"💼 <b>{stylize_text('My Portfolio')}</b>\n━━━━━━━━━━━━\n\n"
        total_val = 0
        total_invested = 0
        quotes = await fetch_market_quotes(portfolio.keys())
        for sym, data in portfolio.items():
            cur_price = safe_market_price(quotes.get(sym, {}).get("price"), MARKET_FALLBACKS.get(sym, 1000))
            cur_val = safe_invest_sell_value(data['amount'], data.get('buy_price'), cur_price, data.get('bought_at'))
            pnl = cur_val - data['amount']
            pnl_pct = (pnl / data['amount']) * 100 if data['amount'] > 0 else 0.0
            total_val += cur_val
            total_invested += data['amount']
            arrow = "📈" if pnl >= 0 else "📉"
            msg += (
                f"{arrow} <b>{sym}</b>: <code>{format_money(cur_val)}</code> "
                f"({'+' if pnl>=0 else ''}{format_money(pnl)} | {pnl_pct:+.1f}%)\n"
            )
        total_pnl = total_val - total_invested
        total_pct = (total_pnl / total_invested * 100) if total_invested > 0 else 0.0
        msg += f"\n💰 <b>Total Value:</b> <code>{format_money(total_val)}</code> ({'+' if total_pnl>=0 else ''}{format_money(total_pnl)} | {total_pct:+.1f}%)"
        return await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

    if act == "buy" and len(context.args) >= 3:
        sym = context.args[1].upper()
        try:
            amt = int(context.args[2])
        except (ValueError, TypeError):
            return await update.message.reply_text("❌ <b>Invalid amount!</b> Example: <code>/invest buy BTC 5000</code>", parse_mode=ParseMode.HTML)
        if sym not in MARKET_SYMBOLS:
            return await update.message.reply_text(f"❌ <b>Invalid symbol!</b> Available: {', '.join(MARKET_SYMBOLS.keys())}", parse_mode=ParseMode.HTML)
        if amt < 100:
            return await update.message.reply_text("📉 <b>Min investment is 100 coins!</b>", parse_mode=ParseMode.HTML)
        existing = portfolio.get(sym)
        prev_amt = int(existing.get("amount", 0)) if existing else 0
        if (prev_amt + amt) > MAX_INVEST_BUY_AMOUNT:
            rem = max(0, MAX_INVEST_BUY_AMOUNT - prev_amt)
            return await update.message.reply_text(
                f"📉 <b>Max holding limit for {sym} is</b> <code>{format_money(MAX_INVEST_BUY_AMOUNT)}</code>!\n"
                f"Currently holding: <code>{format_money(prev_amt)}</code>. Max allowed buy: <code>{format_money(rem)}</code>.",
                parse_mode=ParseMode.HTML,
            )

        quotes = await fetch_market_quotes([sym])
        price = safe_market_price(quotes.get(sym, {}).get("price"), MARKET_FALLBACKS.get(sym, 1000))
        now_dt = datetime.utcnow()

        if existing:
            prev_price = float(existing.get("buy_price", price))
            new_amt = prev_amt + amt
            avg_price = ((prev_amt * prev_price) + (amt * price)) / new_amt
            bought_at = existing.get("bought_at") or now_dt
            stock_data = {"amount": new_amt, "buy_price": avg_price, "symbol": sym, "bought_at": bought_at}
        else:
            new_amt = amt
            stock_data = {"amount": amt, "buy_price": price, "symbol": sym, "bought_at": now_dt}

        charged = adjust_user_balance(
            user["user_id"],
            -amt,
            "invest_buy",
            f"Bought {sym}",
            chat_id=update.effective_chat.id if update.effective_chat else None,
            source="/invest buy",
            require_gte=amt,
            extra_set={f"stocks.{sym}": stock_data},
            meta={"symbol": sym, "price": price},
        )
        if not charged:
            return await update.message.reply_text("📉 <b>Not enough coins in wallet!</b>", parse_mode=ParseMode.HTML)
        fmt_p = f"{price:,.4f}" if price < 1 else f"{price:,.2f}"
        msg = f"🚀 <b>Invested in {sym}!</b>\n"
        msg += f"Bought: <code>{format_money(amt)}</code> at <code>${fmt_p}</code>\n"
        if existing:
            msg += f"💼 Total Holding: <code>{format_money(new_amt)}</code>\n"
        msg += f"💡 <i>Tip: Hold for 15m+ to unlock extra HODL Yield Bonuses!</i>"
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
    
    elif act == "sell" and len(context.args) >= 2:
        sym = context.args[1].upper()
        if sym not in portfolio: return await update.message.reply_text("❌ ᴅᴏɴ'ᴛ ᴏᴡɴ!", parse_mode=ParseMode.HTML)
        data = portfolio[sym]
        quotes = await fetch_market_quotes([sym])
        cur_price = safe_market_price(quotes.get(sym, {}).get("price"), MARKET_FALLBACKS.get(sym, 1000))
        sell_val = safe_invest_sell_value(data['amount'], data.get('buy_price'), cur_price, data.get('bought_at'))
        users_collection.update_one({"user_id": user['user_id']}, {"$unset": {f"stocks.{sym}": ""}})
        adjust_user_balance(
            user["user_id"],
            sell_val,
            "invest_sell",
            f"Sold {sym}",
            chat_id=update.effective_chat.id if update.effective_chat else None,
            source="/invest sell",
            meta={"symbol": sym, "price": cur_price, "buy_price": data.get("buy_price")},
        )
        pnl = sell_val - data['amount']
        await update.message.reply_text(f"📈 sᴏʟᴅ <b>{sym}</b> ғᴏʀ {format_money(sell_val)} ({'📈+' if pnl>=0 else '📉'}{format_money(abs(pnl))})", parse_mode=ParseMode.HTML)


async def p2p_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user_exists(update.effective_user)
    msg = (
        f"\U0001F91D <b>{stylize_text('P2P Desk')}</b>\n"
        "━━━━━━━━━━━━\n\n"
        "<b>Safe peer actions:</b>\n"
        "• <code>/give 500 @user</code> - instant coins with tax\n"
        "• <code>/loan 500 @user</code> - ask loan, lender must accept\n"
        "• <code>/loan give 500 @user</code> - give tracked loan\n"
        "• <code>/loan pay 500</code> - repay oldest active debt\n\n"
        "• <code>/loan collect @user</code> - lender vasuli for overdue loans\n\n"
        "<i>Wallet history is private, so transaction trails stay between the user and Kazumi.</i>"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
