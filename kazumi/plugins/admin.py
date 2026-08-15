# Copyright (c) 2025 Telegram:- @WTF_Phantom <DevixOP>
# Location: Supaul, Bihar 
#
# All rights reserved.
#
# This code is the intellectual property of @WTF_Phantom.
# You are not allowed to copy, modify, redistribute, or use this
# code for commercial or personal projects without explicit permission.
#
# Allowed:
# - Forking for personal learning
# - Submitting improvements via pull requests
#
# Not Allowed:
# - Claiming this code as your own
# - Re-uploading without credit or permission
# - Selling or using commercially
#
# Contact for permissions:
# Email: king25258069@gmail.com


import html
import os
import re
import sys
import time
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from kazumi.config import OWNER_ID, OWNER_LINK, SUPPORT_GROUP, UPSTREAM_REPO, GIT_TOKEN
from kazumi.utils import SUDO_USERS, Button, get_mention, resolve_target, format_money, reload_sudoers
from kazumi.database import (
    db,
    users_collection,
    sudoers_collection,
    groups_collection,
    missions_collection,
    balance_logs_collection,
    loans_collection,
    premium_payments_collection,
    gacha_messages_collection,
    waifu_drops_collection,
    stars_purchases_collection,
)

ADMIN_STARTED_AT = time.time()


def _utc_start(days=0):
    base = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    return base - timedelta(days=days)


def _fmt_int(value):
    return f"{int(value or 0):,}"


def _fmt_delta(seconds):
    seconds = max(0, int(seconds))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    mins, _ = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {mins}m"
    return f"{mins}m"


def _safe_count(collection, query=None):
    try:
        return collection.count_documents(query or {})
    except Exception:
        return 0


def _distinct_users_since(start):
    ids = set()
    try:
        ids.update(users_collection.distinct("user_id", {"last_active_at": {"$gte": start}}))
    except Exception:
        pass
    try:
        ids.update(balance_logs_collection.distinct("user_id", {"created_at": {"$gte": start}}))
    except Exception:
        pass
    try:
        ids.update(missions_collection.distinct("user_id", {"$or": [{"created_at": {"$gte": start}}, {"updated_at": {"$gte": start}}]}))
    except Exception:
        pass
    return ids


def _sum_field(collection, field, query=None):
    try:
        rows = list(collection.aggregate([
            {"$match": query or {}},
            {"$group": {"_id": None, "total": {"$sum": f"${field}"}}},
        ]))
        return int(rows[0].get("total", 0)) if rows else 0
    except Exception:
        return 0


def _admin_overview_text():
    today = _utc_start()
    week = _utc_start(7)
    total_users = _safe_count(users_collection)
    blocked_users = _safe_count(users_collection, {"bot_blocked": True})
    reachable_users = _safe_count(users_collection, {"bot_blocked": {"$ne": True}})
    total_groups = _safe_count(groups_collection)
    blocked_groups = _safe_count(groups_collection, {"bot_blocked": True})
    reachable_groups = _safe_count(groups_collection, {"bot_blocked": {"$ne": True}})
    new_users = _safe_count(users_collection, {"registered_at": {"$gte": today}})
    new_groups = _safe_count(groups_collection, {"created_at": {"$gte": today}})
    active_today = len(_distinct_users_since(today))
    active_week = len(_distinct_users_since(week))
    active_groups = _safe_count(groups_collection, {"last_active_at": {"$gte": today}})
    missions = list(missions_collection.find({"date": today.strftime("%Y-%m-%d")}).limit(2000))
    full_done = 0
    partial = 0
    for doc in missions:
        progress = doc.get("progress", {})
        done = sum(1 for item in progress.values() if item.get("completed"))
        if done:
            partial += 1
        if progress and done == len(progress):
            full_done += 1

    return (
        "\U0001F4CA <b>Kazumi Growth Stats</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"\U0001F464 <b>Users:</b> <code>{_fmt_int(total_users)}</code> total | <code>{_fmt_int(reachable_users)}</code> reachable | <code>{_fmt_int(blocked_users)}</code> blocked | <code>+{_fmt_int(new_users)}</code> today\n"
        f"\U0001F465 <b>Active:</b> <code>{_fmt_int(active_today)}</code> today | <code>{_fmt_int(active_week)}</code> 7d\n"
        f"\U0001F3D8 <b>Groups:</b> <code>{_fmt_int(total_groups)}</code> total | <code>{_fmt_int(reachable_groups)}</code> reachable | <code>{_fmt_int(blocked_groups)}</code> blocked | <code>{_fmt_int(active_groups)}</code> active today | <code>+{_fmt_int(new_groups)}</code> new\n"
        f"\U0001F4CB <b>Missions:</b> <code>{_fmt_int(partial)}</code> touched | <code>{_fmt_int(full_done)}</code> full clears\n\n"
        "<b>Use next:</b>\n"
        "<code>/admin groups</code> top active groups\n"
        "<code>/admin games</code> games demand\n"
        "<code>/admin economy</code> coin health"
    )


def _admin_health_text():
    started = time.time()
    ok = "OK"
    try:
        db.command("ping")
    except Exception as exc:
        ok = f"ERROR: {html.escape(str(exc)[:80])}"
    ping_ms = int((time.time() - started) * 1000)
    pending_payments = _safe_count(premium_payments_collection, {"status": {"$in": ["pending", "waiting"]}})
    pending_gacha = _safe_count(gacha_messages_collection, {"expires_at": {"$gte": datetime.utcnow()}})
    active_drops = _safe_count(waifu_drops_collection, {"expires_at": {"$gte": datetime.utcnow()}})
    return (
        "\U0001F6E0 <b>Kazumi Health</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"\U000023F1 <b>Uptime:</b> <code>{_fmt_delta(time.time() - ADMIN_STARTED_AT)}</code>\n"
        f"\U0001F5C4 <b>Mongo:</b> <code>{ok}</code> | <code>{ping_ms}ms</code>\n"
        f"\U0001F4B3 <b>Premium invoices:</b> <code>{_fmt_int(pending_payments)}</code> pending\n"
        f"\U0001F5BC <b>Timed media:</b> <code>{_fmt_int(pending_gacha)}</code> gacha cards | <code>{_fmt_int(active_drops)}</code> drops\n"
        f"\U0001F511 <b>Sudo users:</b> <code>{_fmt_int(len(SUDO_USERS))}</code>\n\n"
        "<i>Tip: if replies feel slow, check API provider logs and Mongo latency first.</i>"
    )


def _admin_economy_text():
    today = _utc_start()
    total_wallet = _sum_field(users_collection, "balance")
    total_bank = _sum_field(users_collection, "bank")
    credits = _sum_field(balance_logs_collection, "delta", {"created_at": {"$gte": today}, "delta": {"$gt": 0}})
    debits_raw = _sum_field(balance_logs_collection, "delta", {"created_at": {"$gte": today}, "delta": {"$lt": 0}})
    active_loans = _safe_count(loans_collection, {"status": {"$in": ["active", "approved"]}})
    pending_loans = _safe_count(loans_collection, {"status": "pending"})
    overdue = _safe_count(loans_collection, {"status": {"$in": ["active", "approved"]}, "due_at": {"$lt": datetime.utcnow()}})
    return (
        "\U0001F4B0 <b>Economy Control</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"\U0001F45B <b>Wallet supply:</b> <code>{format_money(total_wallet)}</code>\n"
        f"\U0001F3E6 <b>Bank supply:</b> <code>{format_money(total_bank)}</code>\n"
        f"\U0001F4C8 <b>Today earned:</b> <code>{format_money(credits)}</code>\n"
        f"\U0001F4C9 <b>Today spent/lost:</b> <code>{format_money(abs(debits_raw))}</code>\n"
        f"\U0001F4B3 <b>Loans:</b> <code>{_fmt_int(active_loans)}</code> active | <code>{_fmt_int(pending_loans)}</code> pending | <code>{_fmt_int(overdue)}</code> overdue\n\n"
        "<b>Use next:</b> <code>/loan</code>, <code>/top</code>, <code>/admin users</code>"
    )


def _admin_games_text():
    today = _utc_start()
    game_categories = ["game", "games", "blackjack", "rps", "highlow", "taprace", "kill", "rob", "gacha", "crate", "missions"]
    pipeline = [
        {"$match": {"created_at": {"$gte": today}, "category": {"$in": game_categories}}},
        {"$group": {"_id": "$category", "count": {"$sum": 1}, "volume": {"$sum": "$delta"}}},
        {"$sort": {"count": -1}},
        {"$limit": 8},
    ]
    rows = []
    try:
        rows = list(balance_logs_collection.aggregate(pipeline))
    except Exception:
        rows = []
    text = "\U0001F3AE <b>Game Demand Today</b>\n━━━━━━━━━━━━━━━━━━\n\n"
    if rows:
        for idx, row in enumerate(rows, 1):
            text += f"{idx}. <b>{html.escape(str(row['_id']).title())}</b> — <code>{_fmt_int(row['count'])}</code> actions | net <code>{format_money(row.get('volume', 0))}</code>\n"
    else:
        text += "No game ledger activity yet today.\n"
    top_wins = list(users_collection.find({"game_wins": {"$gt": 0}}).sort("game_wins", -1).limit(3))
    if top_wins:
        text += "\n\U0001F3C6 <b>Top winners:</b>\n"
        for i, user in enumerate(top_wins, 1):
            text += f"{i}. {get_mention(user)} — <code>{_fmt_int(user.get('game_wins'))}</code>\n"
    return text


def _admin_groups_text():
    today_key = datetime.utcnow().strftime("%Y-%m-%d")
    rows = list(groups_collection.find().sort([(f"daily_activity.{today_key}", -1), ("activity_ticks", -1)]).limit(10))
    text = "\U0001F3D8 <b>Top Active Groups</b>\n━━━━━━━━━━━━━━━━━━\n\n"
    if not rows:
        return text + "No groups tracked yet."
    for idx, group in enumerate(rows, 1):
        title = html.escape(str(group.get("title") or group.get("chat_id") or "Unknown"))
        today_count = int((group.get("daily_activity") or {}).get(today_key, 0))
        total = int(group.get("activity_ticks", 0))
        text += f"{idx}. <b>{title}</b>\n   today <code>{_fmt_int(today_count)}</code> ticks | total <code>{_fmt_int(total)}</code>\n"
    return text


def _admin_users_text():
    today_key = datetime.utcnow().strftime("%Y-%m-%d")
    rows = list(users_collection.find().sort([(f"daily_activity.{today_key}", -1), ("activity_ticks", -1)]).limit(10))
    text = "\U0001F465 <b>Top Active Users</b>\n━━━━━━━━━━━━━━━━━━\n\n"
    if not rows:
        return text + "No users tracked yet."
    for idx, user in enumerate(rows, 1):
        today_count = int((user.get("daily_activity") or {}).get(today_key, 0))
        total = int(user.get("activity_ticks", 0))
        wins = int(user.get("game_wins", 0))
        text += f"{idx}. {get_mention(user)}\n   today <code>{_fmt_int(today_count)}</code> ticks | total <code>{_fmt_int(total)}</code> | wins <code>{_fmt_int(wins)}</code>\n"
    return text


def _admin_promo_text(bot_username=None):
    bot_link = f"https://t.me/{bot_username}?startgroup=true" if bot_username else OWNER_LINK
    return (
        "\U0001F4E3 <b>Promo Caption</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "\U0001F338 <b>KAZUMI RPG BOT</b>\n"
        "A full Telegram group activity bot with RPG battles, economy, games, loans, gacha cards, AI chat and Mini App dashboard.\n\n"
        "\U0001F3AE Games: TTT, Tap Race, Word Bomb, RPS, Blackjack, High-Low\n"
        "\U00002694 RPG: Kill, Rob, Bounty, Gang Wars, Protection\n"
        "\U0001F4B0 Economy: Daily, Claim, Loans, Shop, P2P, Ledger\n"
        "\U0001F9E0 AI: Smart replies, memory, reactions, image tools\n"
        "\U0001F4F1 Mini App: Wallet, missions, profile, leaderboard, premium\n\n"
        f"\U0001F338 <a href=\"{html.escape(bot_link)}\"><b>Add Kazumi Via Direct</b></a>\n"
        "Make your group active again with Kazumi."
    )


async def _send_admin_section(update: Update, context: ContextTypes.DEFAULT_TYPE, section: str):
    section = (section or "home").lower()
    if section in {"stats", "growth", "dashboard"}:
        text = _admin_overview_text()
    elif section == "health":
        text = _admin_health_text()
    elif section == "economy":
        text = _admin_economy_text()
    elif section == "games":
        text = _admin_games_text()
    elif section == "groups":
        text = _admin_groups_text()
    elif section == "users":
        text = _admin_users_text()
    elif section == "promo":
        me = await context.bot.get_me()
        text = _admin_promo_text(me.username)
    else:
        text = None
    if text:
        return await update.message.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    return None

async def sudo_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in SUDO_USERS: return
    if context.args:
        handled = await _send_admin_section(update, context, context.args[0])
        if handled:
            return
    msg = (
        "🔐 <b>𝐊𝐚𝐳𝐮𝐦𝐢 𝐀𝐝𝐦𝐢𝐧 𝐏𝐚𝐧𝐞𝐥</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "<b>📊 Growth</b>\n"
        "• <code>/admin stats</code> — users, groups, missions\n"
        "• <code>/admin users</code> — top active users\n"
        "• <code>/admin groups</code> — top active groups\n"
        "• <code>/admin games</code> — games demand today\n"
        "• <code>/admin economy</code> — coins, bank, loans\n"
        "• <code>/admin health</code> — Mongo, uptime, pending jobs\n"
        "• <code>/admin promo</code> — ready promo caption\n\n"
        "<b>💰 Economy</b>\n"
        "• <code>/addcoins 5000 @user</code> — add wallet coins\n"
        "• <code>/rmcoins 5000 @user</code> — remove wallet coins\n"
        "• <code>/freerevive @user</code> — revive without fee\n"
        "• <code>/unprotect @user</code> — remove active shield\n\n"
        "<b>💎 Premium</b>\n"
        "• <code>/addpremium @user</code> — manual premium grant\n"
        "• <code>/rmpremium @user</code> — revoke premium\n"
        "• <code>/premium</code> / <code>/plan</code> — buyer payment panel\n"
        "• <code>/setemoji</code> — premium user badge command\n\n"
        "<b>📢 Broadcast</b>\n"
        "• Reply + <code>/broadcast -user</code> — DM users\n"
        "• Reply + <code>/broadcast -group</code> — send to groups\n"
        "• Add <code>-clean</code> — no forwarded tag\n\n"
        "<b>👥 Users & Lookup</b>\n"
        "• <code>/sudolist</code> — owner and sudo list\n"
        "• <code>/addsudo @user</code> — owner only\n"
        "• <code>/rmsudo @user</code> — owner only\n"
        "• Reply + <code>/getid</code> — media file id\n\n"
        "<b>🗄 Database & Deploy</b>\n"
        "• <code>/update</code> — pull Git changes and restart\n"
        "• <code>/cleandb</code> — owner-only dangerous wipe\n\n"
        "<i>Tip:</i> coin, premium, sudo and DB commands ask confirmation before action."
    )
    kb = InlineKeyboardMarkup([
        [Button("📊 Stats", callback_data="admin_panel_stats"), Button("🛠 Health", callback_data="admin_panel_health")],
        [Button("👥 Users", callback_data="admin_panel_users"), Button("🏘 Groups", callback_data="admin_panel_groups")],
        [Button("🎮 Games", callback_data="admin_panel_games"), Button("💰 Economy", callback_data="admin_panel_economy")],
        [Button("📣 Promo", callback_data="admin_panel_promo")],
        [Button("👑 Sudo List", callback_data="admin_panel_sudolist"), Button("💎 Premium Guide", callback_data="admin_panel_premium")],
        [Button("🔄 Update Guide", callback_data="admin_panel_update"), Button("🛟 Support", url=SUPPORT_GROUP)],
    ])
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=kb)


async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in SUDO_USERS:
        return
    await _send_admin_section(update, context, "stats")


async def admin_health(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in SUDO_USERS:
        return
    await _send_admin_section(update, context, "health")


async def admin_games(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in SUDO_USERS:
        return
    await _send_admin_section(update, context, "games")


async def admin_economy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in SUDO_USERS:
        return
    await _send_admin_section(update, context, "economy")


async def admin_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in SUDO_USERS:
        return
    await _send_admin_section(update, context, "groups")


async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in SUDO_USERS:
        return
    await _send_admin_section(update, context, "users")


async def admin_promo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in SUDO_USERS:
        return
    await _send_admin_section(update, context, "promo")


async def admin_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id not in SUDO_USERS:
        return await q.answer("Admin only.", show_alert=True)
    await q.answer()
    action = q.data.replace("admin_panel_", "", 1)
    if action == "stats":
        return await q.message.reply_text(_admin_overview_text(), parse_mode=ParseMode.HTML)
    if action == "health":
        return await q.message.reply_text(_admin_health_text(), parse_mode=ParseMode.HTML)
    if action == "economy":
        return await q.message.reply_text(_admin_economy_text(), parse_mode=ParseMode.HTML)
    if action == "games":
        return await q.message.reply_text(_admin_games_text(), parse_mode=ParseMode.HTML)
    if action == "groups":
        return await q.message.reply_text(_admin_groups_text(), parse_mode=ParseMode.HTML)
    if action == "users":
        return await q.message.reply_text(_admin_users_text(), parse_mode=ParseMode.HTML)
    if action == "promo":
        me = await context.bot.get_me()
        return await q.message.reply_text(_admin_promo_text(me.username), parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    if action == "sudolist":
        docs = list(sudoers_collection.find().sort("user_id", 1))
        text = "👑 <b>Owner & Sudoers</b>\n\n"
        text += f"Owner: <code>{OWNER_ID}</code>\n"
        for row in docs:
            text += f"Sudo: <code>{row.get('user_id')}</code>\n"
        return await q.message.reply_text(text, parse_mode=ParseMode.HTML)
    if action == "premium":
        return await q.message.reply_text(
            "💎 <b>Premium Admin Guide</b>\n\n"
            "• <code>/addpremium @user</code> manual grant\n"
            "• <code>/rmpremium @user</code> revoke\n"
            "• <code>/premium</code> buyer panel\n"
            f"• Manual buyers contact: {OWNER_LINK}",
            parse_mode=ParseMode.HTML,
        )
    if action == "update":
        return await q.message.reply_text(
            "🔄 <b>Deploy Guide</b>\n\n"
            "Use <code>/update</code> only after GitHub has the pushed fix.\n"
            "VPS PM2 fallback: <code>pm2 restart kazumi-bot --update-env</code>",
            parse_mode=ParseMode.HTML,
        )

# --- UPDATER LOGIC (Unchanged) ---
async def update_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not UPSTREAM_REPO: return await update.message.reply_text("❌ <b>UPSTREAM_REPO</b> missing!", parse_mode=ParseMode.HTML)
    msg = await update.message.reply_text("🔄 <b>Checking for updates...</b>", parse_mode=ParseMode.HTML)
    try:
        import git
        try: repo = git.Repo()
        except: 
            repo = git.Repo.init()
            origin = repo.create_remote('origin', UPSTREAM_REPO)
            origin.fetch()
            repo.create_head('master', origin.refs.master).set_tracking_branch(origin.refs.master).checkout()
    except ImportError: return await msg.edit_text("❌ <b>Git Error:</b> Library missing.", parse_mode=ParseMode.HTML)
    except Exception as e: return await msg.edit_text(f"❌ <b>Git Error:</b> <code>{e}</code>", parse_mode=ParseMode.HTML)
    repo_url = UPSTREAM_REPO
    if GIT_TOKEN and "https://github.com" in repo_url: repo_url = repo_url.replace("https://", f"https://{GIT_TOKEN}@")
    try:
        repo.remotes.origin.set_url(repo_url)
        repo.remotes.origin.pull()
        await msg.edit_text("✅ <b>Update Found!</b>\nRestarting bot now... 🚀", parse_mode=ParseMode.HTML)
        args = [sys.executable, "main.py"]
        os.execl(sys.executable, *args)
    except Exception as e: await msg.edit_text(f"❌ <b>Update Failed!</b>\nError: <code>{e}</code>", parse_mode=ParseMode.HTML)

# --- ADMIN COMMANDS ---

async def sudolist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = "👑 <b>𝐎𝐰𝐧𝐞𝐫 & 𝐒𝐮𝐝𝐨𝐞𝐫𝐬:</b>\n\n"
    owner_doc = users_collection.find_one({"user_id": OWNER_ID})
    if not owner_doc:
        try: 
            u = await context.bot.get_chat(OWNER_ID)
            owner_name = u.first_name
        except: owner_name = "Owner"
        msg += f"👑 <a href='tg://user?id={OWNER_ID}'><b>{html.escape(owner_name)}</b></a> (Owner)\n"
    else: msg += f"👑 {get_mention(owner_doc)} (Owner)\n"
    for uid in SUDO_USERS:
        if uid == OWNER_ID: continue
        u_doc = users_collection.find_one({"user_id": uid})
        if u_doc: msg += f"👮 {get_mention(u_doc)}\n"
        else: msg += f"👮 <code>{uid}</code>\n"
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

# --- CONFIRMATION ---

def get_kb(requester_id, act, arg):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ 𝐘𝐞𝐬", callback_data=f"cnf|{requester_id}|{act}|{arg}"),
        InlineKeyboardButton("❌ 𝐍𝐨", callback_data=f"cnf|{requester_id}|cancel|0"),
    ]])

async def ask(update, text, act, arg):
    await update.message.reply_text(
        f"⚠️ <b>Wait!</b> {text}\nAre you sure?",
        parse_mode=ParseMode.HTML,
        reply_markup=get_kb(update.effective_user.id, act, arg),
    )

def _money_token(arg):
    cleaned = re.sub(r"[$,\s_]", "", arg.strip())
    if cleaned.isdigit():
        return int(cleaned), cleaned
    return None, None

def _looks_like_user_id(cleaned):
    return cleaned and cleaned.isdigit() and len(cleaned) >= 7

def parse_amount_and_target(args):
    """
    Accepts both formats:
    /rmcoins 100 @user
    /rmcoins @user 100
    /rmcoins 260,248 8267676849
    /rmcoins 8267676849 $260,248
    """
    amount = None
    target_str = None
    numeric = []

    for arg in args:
        value, cleaned = _money_token(arg)
        if value is None:
            target_str = arg
            continue
        numeric.append((arg, cleaned, value))

    if target_str:
        if numeric:
            amount = numeric[0][2]
        return amount, target_str

    if len(numeric) == 1:
        return numeric[0][2], None

    if len(numeric) >= 2:
        target_index = None

        for i, (_, _, value) in enumerate(numeric):
            if users_collection.find_one({"user_id": value}):
                target_index = i
                break

        if target_index is None:
            for i, (raw, cleaned, _) in enumerate(numeric[:2]):
                other = numeric[1 - i]
                if _looks_like_user_id(cleaned) and (
                    not _looks_like_user_id(other[1]) or any(ch in other[0] for ch in "$, _")
                ):
                    target_index = i
                    break

        if target_index is not None:
            target_str = numeric[target_index][1]
            amount = next(value for i, (_, _, value) in enumerate(numeric) if i != target_index)
        else:
            amount = numeric[0][2]
            target_str = numeric[1][1]

    return amount, target_str

# --- HANDLERS ---

async def addsudo(update, context):
    if update.effective_user.id != OWNER_ID: return
    target_arg = context.args[0] if context.args else None
    target, err = await resolve_target(update, context, specific_arg=target_arg)
    if not target: return await update.message.reply_text(err or "Usage: /addsudo <target>", parse_mode=ParseMode.HTML)
    if target['user_id'] in SUDO_USERS: return await update.message.reply_text("⚠️ Already Sudoer.", parse_mode=ParseMode.HTML)
    await ask(update, f"Promote {get_mention(target)}?", "addsudo", str(target['user_id']))

async def rmsudo(update, context):
    if update.effective_user.id != OWNER_ID: return
    target_arg = context.args[0] if context.args else None
    target, err = await resolve_target(update, context, specific_arg=target_arg)
    if not target: return await update.message.reply_text(err or "Usage: /rmsudo <target>", parse_mode=ParseMode.HTML)
    if target['user_id'] not in SUDO_USERS: return await update.message.reply_text("⚠️ Not a Sudoer.", parse_mode=ParseMode.HTML)
    await ask(update, f"Demote {get_mention(target)}?", "rmsudo", str(target['user_id']))

async def addcoins(update, context):
    if update.effective_user.id not in SUDO_USERS: return
    if not context.args: return await update.message.reply_text("⚠️ Usage: <code>/addcoins 100 @user</code>", parse_mode=ParseMode.HTML)
    amount, target_str = parse_amount_and_target(context.args)
    if amount is None or amount <= 0: return await update.message.reply_text("⚠️ Invalid Amount!", parse_mode=ParseMode.HTML)
    target, err = await resolve_target(update, context, specific_arg=target_str)
    if not target: return await update.message.reply_text(err or "⚠️ Reply or Tag user.", parse_mode=ParseMode.HTML)
    await ask(update, f"Give <b>{format_money(amount)}</b> to {get_mention(target)}?", "addcoins", f"{target['user_id']}|{amount}")

async def rmcoins(update, context):
    if update.effective_user.id not in SUDO_USERS: return
    if not context.args: return await update.message.reply_text("⚠️ Usage: <code>/rmcoins 100 @user</code>", parse_mode=ParseMode.HTML)
    amount, target_str = parse_amount_and_target(context.args)
    if amount is None or amount <= 0: return await update.message.reply_text("⚠️ Invalid Amount!", parse_mode=ParseMode.HTML)
    target, err = await resolve_target(update, context, specific_arg=target_str)
    if not target: return await update.message.reply_text(err or "⚠️ Reply or Tag user.", parse_mode=ParseMode.HTML)
    await ask(update, f"Remove <b>{format_money(amount)}</b> from {get_mention(target)}?", "rmcoins", f"{target['user_id']}|{amount}")

async def freerevive(update, context):
    if update.effective_user.id not in SUDO_USERS: return
    target_arg = context.args[0] if context.args else None
    target, err = await resolve_target(update, context, specific_arg=target_arg)
    if not target: return await update.message.reply_text(err or "Usage: /freerevive <target>", parse_mode=ParseMode.HTML)
    await ask(update, f"Free Revive {get_mention(target)}?", "freerevive", str(target['user_id']))

async def unprotect(update, context):
    """Remove protection from a user."""
    if update.effective_user.id not in SUDO_USERS: return
    target_arg = context.args[0] if context.args else None
    target, err = await resolve_target(update, context, specific_arg=target_arg)
    if not target: return await update.message.reply_text(err or "Usage: /unprotect <target>", parse_mode=ParseMode.HTML)
    await ask(update, f"Remove 🛡️ from {get_mention(target)}?", "unprotect", str(target['user_id']))

async def cleandb(update, context):
    if update.effective_user.id != OWNER_ID: return
    await ask(update, "<b>WIPE DATABASE?</b> 🗑️", "cleandb", "0")

async def confirm_handler(update, context):
    q = update.callback_query
    await q.answer()
    if q.from_user.id not in SUDO_USERS: return await q.message.edit_text("❌ <b>Kazumi says nope!</b> Not for you.", parse_mode=ParseMode.HTML)
    
    data = q.data.split("|")
    if len(data) >= 4 and data[1].isdigit():
        requester_id = int(data[1])
        act = data[2]
        args = data[3:]
    else:
        requester_id = q.from_user.id
        act = data[1]
        args = data[2:]

    if q.from_user.id != requester_id:
        return await q.answer("Only the command starter can confirm this.", show_alert=True)
    if act == "cleandb" and q.from_user.id != OWNER_ID:
        return await q.message.edit_text("❌ <b>Owner confirmation required.</b>", parse_mode=ParseMode.HTML)
    if act == "cancel": return await q.message.edit_text("❌ <b>Cancelled.</b>", parse_mode=ParseMode.HTML)

    if act == "addsudo":
        uid = int(args[0])
        sudoers_collection.insert_one({"user_id": uid})
        reload_sudoers()
        await q.message.edit_text(f"✅ User <code>{uid}</code> promoted.", parse_mode=ParseMode.HTML)
    elif act == "rmsudo":
        uid = int(args[0])
        sudoers_collection.delete_one({"user_id": uid})
        reload_sudoers()
        await q.message.edit_text(f"🗑️ User <code>{uid}</code> demoted.", parse_mode=ParseMode.HTML)
    elif act == "addcoins":
        uid, amt = int(args[0]), int(args[1])
        users_collection.update_one({"user_id": uid}, {"$inc": {"balance": amt}})
        await q.message.edit_text(f"✅ Added <b>{format_money(amt)}</b> to <code>{uid}</code>.", parse_mode=ParseMode.HTML)
    elif act == "rmcoins":
        uid, amt = int(args[0]), int(args[1])
        users_collection.update_one({"user_id": uid}, {"$inc": {"balance": -amt}})
        await q.message.edit_text(f"✅ Removed <b>{format_money(amt)}</b> from <code>{uid}</code>.", parse_mode=ParseMode.HTML)
    elif act == "freerevive":
        uid = int(args[0])
        users_collection.update_one({"user_id": uid}, {"$set": {"status": "alive", "death_time": None}})
        await q.message.edit_text(f"✅ User <code>{uid}</code> revived.", parse_mode=ParseMode.HTML)
    elif act == "unprotect":
        uid = int(args[0])
        # Set expiry to past
        users_collection.update_one({"user_id": uid}, {"$set": {"protection_expiry": datetime.utcnow()}}) 
        await q.message.edit_text(f"🛡️ Protection <b>REMOVED</b> from <code>{uid}</code>.", parse_mode=ParseMode.HTML)
    elif act == "cleandb":
        users_collection.delete_many({})
        groups_collection.delete_many({})
        await q.message.edit_text("🗑️ <b>DATABASE WIPED!</b>", parse_mode=ParseMode.HTML)

# ━━━━ GET FILE ID ━━━━
async def getid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reply to any media to get its file_id."""
    uid = update.effective_user.id
    if uid != OWNER_ID and uid not in SUDO_USERS:
        return
    
    reply = update.message.reply_to_message
    if not reply:
        return await update.message.reply_text("⚠️ ʀᴇᴘʟʏ ᴛᴏ ᴀ ɢɪғ/ᴘʜᴏᴛᴏ/ᴠɪᴅᴇᴏ!", parse_mode=ParseMode.HTML)
    
    file_id = None
    media_type = "Unknown"
    
    if reply.animation:
        file_id = reply.animation.file_id
        media_type = "GIF/Animation"
    elif reply.photo:
        file_id = reply.photo[-1].file_id
        media_type = "Photo"
    elif reply.video:
        file_id = reply.video.file_id
        media_type = "Video"
    elif reply.sticker:
        file_id = reply.sticker.file_id
        media_type = "Sticker"
    elif reply.document:
        file_id = reply.document.file_id
        media_type = "Document"
    
    if file_id:
        await update.message.reply_text(
            f"📎 <b>{media_type} File ID:</b>\n\n<code>{file_id}</code>\n\n<i>ᴄᴏᴘʏ & ᴘᴀsᴛᴇ ɪɴ ᴄᴏɴғɪɢ.ᴘʏ</i>",
            parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text("❌ ɴᴏ ᴍᴇᴅɪᴀ ғᴏᴜɴᴅ!", parse_mode=ParseMode.HTML)


async def admin_purchases(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner/Sudo Only: View last 20 Telegram Stars purchases."""
    if update.effective_user.id not in {OWNER_ID, *SUDO_USERS}:
        return await update.message.reply_text("❌ Sudo only.", parse_mode=ParseMode.HTML)

    # Optional filter: /adminpurchases @username or user_id
    filter_uid = None
    if context.args:
        arg = context.args[0].lstrip("@")
        try:
            filter_uid = int(arg)
        except ValueError:
            u = users_collection.find_one({"username": {"$regex": f"^{arg}$", "$options": "i"}})
            if u:
                filter_uid = u["user_id"]

    query = {"user_id": filter_uid} if filter_uid else {}
    docs = list(stars_purchases_collection.find(query).sort("purchased_at", -1).limit(20))

    if not docs:
        return await update.message.reply_text(
            "📭 <b>No Stars purchase history found.</b>", parse_mode=ParseMode.HTML
        )

    lines = [f"⭐️ <b>Last {len(docs)} Stars Purchases:</b>\n"]
    for d in docs:
        ts = d.get("purchased_at")
        ts_str = ts.strftime("%b %d %H:%M") if ts else "?"
        uname = d.get("username") or str(d.get("user_id", "?"))
        lines.append(
            f"• <code>{ts_str}</code> — <b>{d.get('item_name', d.get('payload', '?'))}</b> "
            f"(⭐️{d.get('stars_paid', '?')}) by @{uname} [<code>{d.get('user_id', '?')}</code>]"
        )

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
